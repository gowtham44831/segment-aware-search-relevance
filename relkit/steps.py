"""The three steps: validate the judge, calibrate it on behaviour, measure search."""
from __future__ import annotations

import csv
import json
import statistics
from collections import Counter, defaultdict

from .adapters.data import _rows
from .judges.context import context_from_key, make_context
from .metrics import auc_of_chosen, keyword_table, mean_ci, paired_diff, query_metrics, scorecard, weighted_kappa
from .schema import Query


def _progress(total, label):
    state = {"n": 0}

    def tick():
        state["n"] += 1
        if state["n"] % max(1, total // 10) == 0 or state["n"] == total:
            print(f"  {label}: {state['n']}/{total}", flush=True)
    return tick


def write_csv(path, rows):
    if not rows:
        return
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


# ---------------------------------------------------------------- 1. validate
def validate(p) -> dict:
    """Agreement between the judge and hand-labelled golden cases."""
    path = p.path("golden")
    if not path or not path.exists():
        print("No golden file configured; skipping validation.")
        return {}
    gold = list(_rows(path))
    items = []
    for g in gold:
        ctx = context_from_key(g["context"], p.users, p.segments, p.catalog, p.history_items)
        items.append((g["query"], p.catalog[g["product_id"]], ctx))
    print(f"Validating judge on {len(items)} golden cases")
    js = p.judge.grade_many(items, _progress(len(items), "golden"))
    rows = []
    for g, j in zip(gold, js):
        kind = g["context"].split(":")[0]
        kind = {"user": "history"}.get(kind, kind)
        rows.append({"mode": kind, "context": g["context"], "query": g["query"], "product_id": g["product_id"],
                     "expected": int(g["grade"]), "judge": j.grade, "reason": j.reason, "note": g.get("note", "")})
    write_csv(p.out / "validation.csv", rows)
    summary = {}
    for mode in ["ALL"] + sorted({r["mode"] for r in rows}):
        rs = [r for r in rows if mode in ("ALL", r["mode"])]
        e, j = [r["expected"] for r in rs], [r["judge"] for r in rs]
        summary[mode] = {"n": len(rs),
                         "exact": sum(a == b for a, b in zip(e, j)) / len(rs),
                         "within1": sum(abs(a - b) <= 1 for a, b in zip(e, j)) / len(rs),
                         "relevant_agree": sum((a >= 2) == (b >= 2) for a, b in zip(e, j)) / len(rs),
                         "kappa": weighted_kappa(e, j)}
    conf = Counter((r["expected"], r["judge"]) for r in rows)
    gate = float(p.cfg.get("gate", {}).get("min_kappa", 0.6))
    result = {"summary": summary, "confusion": {f"{a}->{b}": n for (a, b), n in conf.items()},
              "gate_min_kappa": gate, "passed": summary["ALL"]["kappa"] >= gate,
              "disagreements": [r for r in rows if abs(r["expected"] - r["judge"]) >= 2]}
    (p.out / "validation.json").write_text(json.dumps(result, indent=2))
    s = summary["ALL"]
    print(f"  exact {s['exact']:.0%} | within 1 grade {s['within1']:.0%} | weighted kappa {s['kappa']:.2f} "
          f"-> {'PASS' if result['passed'] else 'FAIL'} (gate {gate})")
    return result


# ---------------------------------------------------------------- 2. calibrate
def calibrate(p) -> dict:
    """Does the judge prefer what real shoppers chose? AUC of the chosen item
    among the items shown, per mode and segment (0.5 = chance)."""
    path = p.path("interactions")
    if not path or not path.exists():
        print("No interactions file configured; skipping calibration.")
        return {}
    imps = list(_rows(path))
    items, keys = [], []
    for i, r in enumerate(imps):
        user = p.users.get(str(r["user_id"]))
        shown = [x for x in str(r["shown"]).split(";") if x in p.catalog]
        for mode in p.modes:
            ctx = make_context(mode, user, p.segments, p.catalog, p.history_items)
            for pid in shown:
                items.append((r["query"], p.catalog[pid], ctx))
                keys.append((i, mode, pid))
    print(f"Calibrating on {len(imps)} shopper choices ({len(items)} judgments)")
    js = p.judge.grade_many(items, _progress(len(items), "choices"))
    grades = defaultdict(dict)
    for (i, mode, pid), j in zip(keys, js):
        grades[(i, mode)][pid] = j.grade
    per = []
    for i, r in enumerate(imps):
        user = p.users.get(str(r["user_id"]))
        for mode in p.modes:
            per.append({"impression": i, "mode": mode, "segment": user.segment if user else "",
                        "auc": auc_of_chosen(grades[(i, mode)], str(r["chosen"]))})
    write_csv(p.out / "calibration_per_choice.csv", per)
    out = {}
    for seg in ["ALL"] + sorted({x["segment"] for x in per}):
        out[seg] = {mode: mean_ci([x["auc"] for x in per if x["mode"] == mode and seg in ("ALL", x["segment"])])
                    for mode in p.modes}
    (p.out / "calibration.json").write_text(json.dumps(out, indent=2))
    for mode in p.modes:
        m = out["ALL"][mode]
        print(f"  {mode:8s} AUC {m['mean']:.3f} [{m['lo']:.3f}, {m['hi']:.3f}]")
    return out


# ---------------------------------------------------------------- 0. judges
def build_judges(p) -> dict:
    """Write each segment judge's data-built profile and keyword set."""
    from .judges.profiles import build_profiles, write_profiles
    prof = p.profiles or build_profiles(p.catalog, p.users, p.segments, p.queries, p.devices)
    write_profiles(prof, p.out)
    for pr in prof.values():
        print(f"  {pr['name']}: {pr['shoppers']} shoppers, {pr['searches']} searches "
              f"({pr['distinct_keywords']} distinct keywords)")
    print(f"  profiles: {p.out / 'judges.md'}")
    return prof


# ---------------------------------------------------------------- 3. measure
def _searches(p):
    """Searches to run, optionally capped per judge for cost control."""
    cap = p.cfg.get("max_searches_per_judge")
    if not cap:
        return p.queries
    import random
    rng = random.Random(0)
    by = defaultdict(list)
    for q in p.queries:
        by[q.segment].append(q)
    out = []
    for seg, qs in by.items():
        out += qs if len(qs) <= cap else rng.sample(qs, int(cap))
    return out


def _retrieve(p, searches):
    depth = max(p.k, int(p.cfg.get("pool_depth", 20)))
    results = {}  # (engine, query_id) -> [pid]
    pool = defaultdict(list)  # query_id -> pids (ordered, unique)
    for eng in p.engines:
        for q in searches:
            user = p.users.get(q.user_id)
            try:
                ids = eng.search(q, user, depth)
            except Exception as e:  # keep going; record as no results
                print(f"  ! {eng.name} failed on '{q.query}': {e}")
                ids = []
            ids = [i for i in dict.fromkeys(ids) if i in p.catalog][:depth]
            results[(eng.name, q.query_id)] = ids
            for i in ids:
                if i not in pool[q.query_id]:
                    pool[q.query_id].append(i)
    return results, pool


def _pool_items(p, searches, pool):
    items, keys = [], []
    for q in searches:
        user = p.users.get(q.user_id)
        for mode in p.modes:
            ctx = make_context(mode, user, p.segments, p.catalog, p.history_items)
            if mode == "segment" and q.segment in p.segments and ctx.mode != "segment":
                from .judges.context import ShopperContext
                ctx = ShopperContext("segment", segment=p.segments[q.segment])
            for pid in pool[q.query_id]:
                items.append((q.query, p.catalog[pid], ctx))
                keys.append((q.query_id, pid, mode))
    return items, keys


def estimate(p) -> dict:
    """How many judgments and LLM calls a measure run needs (nothing is graded)."""
    searches = _searches(p)
    _, pool = _retrieve(p, searches)
    items, _ = _pool_items(p, searches, pool)
    todo = p.judge.missing(items)
    groups = defaultdict(int)
    uniq = set()
    for q, prod, ctx in todo:
        k = (q.lower().strip(), ctx.mode, ctx.describe(p.judge.include_segment), prod.product_id)
        if k in uniq:
            continue
        uniq.add(k)
        groups[k[:3]] += 1
    bs = int(getattr(p.judge.judge, "batch_size", 1) or 1)
    calls = sum(-(-n // bs) for n in groups.values())
    jc = p.cfg.get("judge", {})
    tin = calls * (450 + 120 * min(bs, 10) + 40 * p.history_items)
    tout = len(uniq) * 35
    cost = tin / 1e6 * float(jc.get("price_in_per_m", 0.40)) + tout / 1e6 * float(jc.get("price_out_per_m", 1.60))
    res = {"searches": len(searches), "pooled_products_per_search": round(sum(map(len, pool.values())) / max(1, len(pool)), 1),
           "judgments_needed": len(uniq), "already_cached": len(items) - len(todo), "llm_calls": calls,
           "est_input_tokens": tin, "est_output_tokens": tout, "est_cost_usd": round(cost, 2)}
    for k, v in res.items():
        print(f"  {k}: {v}")
    return res


def measure(p) -> dict:
    """Run every judge's searches through every engine, grade the pooled results
    for the shopper who searched, and compute precision / recall / nDCG / MRR."""
    searches = _searches(p)
    results, pool = _retrieve(p, searches)
    write_csv(p.out / "search_results.csv", [{"engine": e, "query_id": qid, "rank": r, "product_id": pid}
                                             for (e, qid), ids in results.items() for r, pid in enumerate(ids, 1)])
    items, keys = _pool_items(p, searches, pool)
    print(f"Measuring {len(p.engines)} engines x {len(searches)} searches x {len(p.modes)} judge modes "
          f"({len(items)} pooled judgments, {sum(map(len, pool.values())) / max(1, len(pool)):.1f} products per search)")
    js = dict(zip(keys, p.judge.grade_many(items, _progress(len(items), "graded"))))
    write_csv(p.out / "pool_judgments.csv", [
        {"query_id": qid, "mode": mode, "product_id": pid, "grade": j.grade, "reason": j.reason}
        for (qid, pid, mode), j in js.items()])
    rel = int(p.cfg.get("relevant_grade", 2))
    rows, pq = [], []
    for q in searches:
        for mode in p.modes:
            pool_g = [js[(q.query_id, pid, mode)].grade for pid in pool[q.query_id]]
            for eng in p.engines:
                ids = results[(eng.name, q.query_id)]
                grades = [js[(q.query_id, pid, mode)].grade for pid in ids[:p.k]]
                m = query_metrics(grades, pool_g, p.k, rel)
                pq.append({"engine": eng.name, "mode": mode, "query_id": q.query_id, "query": q.query,
                           "user_id": q.user_id, "segment": q.segment, **m})
                for rank, pid in enumerate(ids[:p.k], 1):
                    j = js[(q.query_id, pid, mode)]
                    rows.append({"engine": eng.name, "mode": mode, "query_id": q.query_id, "query": q.query,
                                 "user_id": q.user_id, "segment": q.segment, "rank": rank, "product_id": pid,
                                 "title": p.catalog[pid].title, "price": p.catalog[pid].price,
                                 "grade": j.grade, "reason": j.reason})
    write_csv(p.out / "judgments.csv", rows)
    write_csv(p.out / "per_query.csv", pq)
    jc = p.cfg.get("judge", {})
    (p.out / "run.json").write_text(json.dumps({
        "judge_type": jc.get("type", "rules"), "judge_model": jc.get("model"), "judge_signature": p.judge.judge.signature,
        "searches": len(searches), "top_k": p.k, "pool_depth": int(p.cfg.get("pool_depth", 20)), "modes": p.modes}, indent=2))
    sc = scorecard(pq)
    write_csv(p.out / "scorecard.csv", sc)
    write_csv(p.out / "keywords.csv", keyword_table(pq))
    base = p.cfg.get("baseline_engine") or (p.engines[0].name if p.engines else None)
    comps = []
    for eng in p.engines:
        if eng.name == base:
            continue
        for mode in p.modes:
            for seg in ["ALL"] + sorted(p.segments):
                for metric in ("recall_capped", "precision", "ndcg"):
                    d = paired_diff(pq, eng.name, base, mode, seg, metric)
                    comps.append({"engine": eng.name, "baseline": base, "mode": mode, "segment": seg, **d})
    write_csv(p.out / "engine_vs_baseline.csv", comps)
    mode = p.cfg.get("report_mode", "history" if "history" in p.modes else p.modes[0])
    print(f"\nRecall@{p.k} / Precision@{p.k} by judge ({mode} grading):")
    segs = ["ALL"] + sorted(p.segments)
    print("  " + "engine".ljust(20) + "".join(s[:14].rjust(16) for s in segs))
    cell = {(r["engine"], r["segment"]): r for r in sc if r["mode"] == mode}
    for eng in p.engines:
        print("  " + eng.name.ljust(20) + "".join(
            f"{cell[(eng.name, s)]['recall_capped']:7.2f} / {cell[(eng.name, s)]['precision']:.2f}".rjust(16)
            if (eng.name, s) in cell else "".rjust(16) for s in segs))
    return {"rows": rows, "per_query": pq, "scorecard": sc, "comparisons": comps, "baseline": base}
