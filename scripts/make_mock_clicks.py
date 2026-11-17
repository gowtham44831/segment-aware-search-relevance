"""Simulate a click/purchase log for the mock store.

Each simulated shopper sees the lexical top 8 for their search and picks one
item using hidden preferences (device fit, price taste, quality, brand) plus
random noise. The judge never sees these preferences, only the shopper's
history, so calibration tests whether it can infer them.

This is a demo of the calibration step. Real use: export impressions from your
search logs (what was shown, what was clicked or bought).

Run after make_mock.py:        python scripts/make_mock_clicks.py
Run after make_mock_large.py:  python scripts/make_mock_clicks.py large
"""
import csv
import math
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from relkit.adapters.search import BM25  # noqa: E402
from relkit.judges.rules import RulesJudge  # noqa: E402
from relkit.project import Project  # noqa: E402

PRICE_TASTE = {"budget": -1.6, "apple_premium": 0.4, "samsung_loyal": -0.3, "multi_device": -0.2}
BRAND_LOVE = {"apple_premium": "Apple", "samsung_loyal": "Samsung"}


def utility(p, user, intent, median, rng):
    u = 0.0
    if intent and p.category not in intent["primary"]:
        u -= 3.0
    fits = set(p.fits)
    if fits and not fits & {"any", "self"}:
        u += 1.5 if fits & set(user.devices) else -4.0
    if p.price and median.get(p.category):
        u += PRICE_TASTE.get(user.segment, 0) * math.log(p.price / median[p.category])
    u += 1.2 * ((p.rating or 4.3) - 4.3) + 0.15 * math.log1p(p.review_count or 0)
    if BRAND_LOVE.get(user.segment) == p.brand:
        u += 1.0
    return u + rng.gumbel(0, 1.0) if hasattr(rng, "gumbel") else u - math.log(-math.log(rng.random()))


def main(config="config/mock.yaml", out="data/mock/interactions.csv", repeats=2, shown_n=8, seed=11, max_n=None):
    proj = Project(str(ROOT / config))
    eng = BM25(proj.catalog)
    rules = RulesJudge(proj.catalog)
    rng = random.Random(seed)
    rows = []
    for rep in range(repeats):
        qs = proj.queries if not max_n else random.Random(seed).sample(proj.queries, max_n)
        for q in qs:
            user = proj.users[q.user_id]
            shown = eng.search(q, user, shown_n)
            if len(shown) < 2:
                continue
            intent = rules._intent(rules._fix_typos(q.query.lower()))
            chosen = max(shown, key=lambda pid: utility(proj.catalog[pid], user, intent, rules.median, rng))
            rows.append({"impression_id": f"I{len(rows)+1:04d}", "user_id": q.user_id, "query": q.query,
                         "shown": ";".join(shown), "chosen": chosen})
    out = ROOT / out
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {len(rows)} simulated choices to {out}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "large":
        main("config/mock_large.yaml", "data/mock_large/interactions.csv", repeats=1, max_n=800)
    else:
        main()
