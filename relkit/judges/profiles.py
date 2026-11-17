"""Build each segment judge's profile from data.

A judge = one customer segment. Its profile is computed from the segment's
shoppers (devices, price position, brands, categories, typical purchases) and
its keyword set is the searches those shoppers ran. In `segment` mode the LLM
judge is given this profile; in `history` mode each search is graded with the
searching shopper's own history.
"""
from __future__ import annotations

import json
import statistics
from collections import Counter, defaultdict
from typing import Dict


def build_profiles(catalog, users, segments, queries, devices=None) -> Dict[str, dict]:
    med = defaultdict(list)
    for pr in catalog.values():
        if pr.price:
            med[pr.category].append(pr.price)
    med = {c: statistics.median(v) for c, v in med.items()}
    dev_name = {d: v.get("name", d) for d, v in (devices or {}).items()}
    dev_eco = {d: v.get("ecosystem", "") for d, v in (devices or {}).items()}

    by_seg = defaultdict(list)
    for u in users.values():
        by_seg[u.segment].append(u)
    q_by_seg = defaultdict(list)
    for q in queries:
        q_by_seg[q.segment].append(q.query)

    out = {}
    for sid, seg in segments.items():
        members = by_seg.get(sid, [])
        devs, ecos, brands, cats, items, ratios = Counter(), Counter(), Counter(), Counter(), Counter(), []
        n_purchases = 0
        for u in members:
            for d in set(u.devices):
                devs[d] += 1
                if dev_eco.get(d):
                    ecos[dev_eco[d]] += 1
            for pid in u.history:
                pr = catalog.get(pid)
                if not pr:
                    continue
                n_purchases += 1
                brands[pr.brand] += 1
                cats[pr.category] += 1
                items[pr.title] += 1
                if pr.price and med.get(pr.category):
                    ratios.append(pr.price / med[pr.category])
        n = max(1, len(members))
        ratio = statistics.median(ratios) if ratios else 1.0
        cheap_share = sum(r < 0.6 for r in ratios) / len(ratios) if ratios else 0
        sens = "high" if ratio < 0.75 else "low" if ratio > 1.4 else "medium"
        top_eco, eco_n = (ecos.most_common(1)[0] if ecos else ("mixed", 0))
        multi = sum(1 for u in members if len({dev_eco.get(d) for d in u.devices if dev_eco.get(d)}) > 1) / n
        ecosystem = top_eco if eco_n / n >= 0.8 and multi < 0.3 else "mixed"
        kw = Counter(q_by_seg.get(sid, []))

        def pct(c, total, k=4, names=None):
            return ", ".join(f"{(names or {}).get(x, x).replace('_', ' ')} {v / total:.0%}" for x, v in c.most_common(k))

        lines = [f"{seg.name}: {len(members)} shoppers, {n_purchases} purchases analysed."]
        if devs:
            lines.append(f"Devices owned: {pct(devs, n, 5, dev_name)}.")
        if multi:
            lines.append(f"{multi:.0%} own devices from more than one brand ecosystem.")
        lines.append(f"Price: typically pays {ratio:.2f}x the category median price; {cheap_share:.0%} of purchases are "
                     f"budget-priced (price sensitivity: {sens}).")
        if brands:
            lines.append(f"Brands bought most: {pct(brands, max(1, n_purchases))}.")
        if cats:
            lines.append(f"Buys most: {pct(cats, max(1, n_purchases), 5)}.")
        if items:
            lines.append("Typical purchases: " + "; ".join(t for t, _ in items.most_common(4)) + ".")
        if seg.description:
            lines.append(f"Analyst note: {seg.description}")
        out[sid] = {
            "segment_id": sid, "name": seg.name, "shoppers": len(members), "purchases": n_purchases,
            "searches": sum(kw.values()), "distinct_keywords": len(kw),
            "top_keywords": kw.most_common(25), "devices": dict(devs.most_common()),
            "price_ratio": round(ratio, 2), "price_sensitivity": sens, "ecosystem": ecosystem,
            "profile": " ".join(lines),
        }
    return out


def apply_profiles(segments, profiles):
    """Use the data-built profile as the segment judge's persona."""
    for sid, pr in profiles.items():
        s = segments[sid]
        s.description = pr["profile"]
        s.attrs.update({"price_sensitivity": pr["price_sensitivity"], "ecosystem": pr["ecosystem"]})


def write_profiles(profiles, out_dir):
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "judges.json").write_text(json.dumps(profiles, indent=2))
    md = ["# Segment judges\n"]
    for pr in profiles.values():
        md.append(f"## {pr['name']}\n\n{pr['profile']}\n\n**Keyword set:** {pr['searches']} searches, "
                  f"{pr['distinct_keywords']} distinct. Top: " + ", ".join(f"{k} ({v})" for k, v in pr["top_keywords"][:10]) + "\n")
    (out_dir / "judges.md").write_text("\n".join(md))
