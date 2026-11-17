"""Relevance metrics.

For each search, the engine's top k results are graded 0-3 for the shopper. The
set of all relevant products for that search comes from pooling: every engine's
top `pool_depth` results are graded, and anything graded >= relevant_grade is
relevant. Recall is therefore measured against all relevant products found by
any engine (standard TREC-style pooling), not against the whole catalog.

Order-free: precision, recall, F1, relevance score, irrelevant rate, hit rate.
Order-aware: nDCG, MRR.
"""
from __future__ import annotations

import math
import statistics
from collections import defaultdict
from typing import Dict, List

NAN = float("nan")


def query_metrics(grades: List[int], pool_grades: List[int], k: int, rel: int = 2) -> dict:
    """grades: the engine's results in order (may be shorter than k; empty = no results).
    pool_grades: grades of every pooled product for this search and shopper."""
    g = grades[:k]
    n_rel_pool = sum(x >= rel for x in pool_grades)
    hits = sum(x >= rel for x in g)
    p = hits / k
    r = hits / n_rel_pool if n_rel_pool else NAN
    rc = hits / min(k, n_rel_pool) if n_rel_pool else NAN  # capped recall: 1.0 is reachable
    f1 = 2 * p * r / (p + r) if n_rel_pool and (p + r) else (0.0 if n_rel_pool else NAN)
    first = next((i for i, x in enumerate(g) if x >= rel), None)
    dcg = sum((2 ** x - 1) / math.log2(i + 2) for i, x in enumerate(g))
    ideal = sorted(pool_grades, reverse=True)[:k]
    idcg = sum((2 ** x - 1) / math.log2(i + 2) for i, x in enumerate(ideal))
    return {
        "precision": p,
        "recall": r,
        "recall_capped": rc,
        "f1": f1,
        "ndcg": dcg / idcg if idcg else NAN,
        "mrr": 1 / (first + 1) if first is not None else 0.0,
        "hit_exact": int(any(x == 3 for x in g)),
        "score": 100 * statistics.mean(g) / 3 if g else 0.0,
        "irrelevant_rate": sum(x == 0 for x in g) / len(g) if g else NAN,
        "zero_results": int(not g),
        "relevant_in_pool": n_rel_pool,
        "n_results": len(g),
    }


METRICS = ["precision", "recall", "recall_capped", "f1", "ndcg", "mrr", "hit_exact", "score", "irrelevant_rate", "zero_results",
           "relevant_in_pool", "n_results"]


def _mean(xs):
    xs = [x for x in xs if not (isinstance(x, float) and math.isnan(x))]
    return sum(xs) / len(xs) if xs else NAN


def scorecard(pq: List[dict]) -> List[dict]:
    """Average per-search metrics by engine x mode x judge (segment), plus ALL."""
    groups = defaultdict(list)
    for r in pq:
        groups[(r["engine"], r["mode"], r["segment"])].append(r)
        groups[(r["engine"], r["mode"], "ALL")].append(r)
    out = []
    for (eng, mode, seg), rs in sorted(groups.items()):
        row = {"engine": eng, "mode": mode, "segment": seg, "searches": len(rs)}
        for m in METRICS:
            row[m] = _mean([r[m] for r in rs])
        row["no_relevant_product"] = _mean([float(r["relevant_in_pool"] == 0) for r in rs])
        out.append(row)
    return out


def keyword_table(pq: List[dict]) -> List[dict]:
    """Aggregate by judge x keyword (searches of the same text), weighted by frequency."""
    groups = defaultdict(list)
    for r in pq:
        groups[(r["engine"], r["mode"], r["segment"], r["query"].lower().strip())].append(r)
    out = []
    for (eng, mode, seg, kw), rs in groups.items():
        row = {"engine": eng, "mode": mode, "segment": seg, "keyword": kw, "searches": len(rs)}
        for m in ("precision", "recall", "recall_capped", "ndcg", "mrr", "score", "zero_results", "relevant_in_pool"):
            row[m] = _mean([r[m] for r in rs])
        out.append(row)
    return out


def paired_diff(pq: List[dict], engine: str, baseline: str, mode: str, segment: str,
                metric="recall", n_boot=2000, seed=0) -> dict:
    """Engine minus baseline on the same searches, with a 95% bootstrap CI."""
    def pick(e):
        return {r["query_id"]: r[metric] for r in pq if r["engine"] == e and r["mode"] == mode
                and segment in ("ALL", r["segment"]) and not (isinstance(r[metric], float) and math.isnan(r[metric]))}
    a, b = pick(engine), pick(baseline)
    d = [a[q] - b[q] for q in a if q in b]
    if not d:
        return {"metric": metric, "diff": NAN, "lo": NAN, "hi": NAN, "n": 0}
    lo, hi = _boot_ci(d, n_boot, seed)
    return {"metric": metric, "diff": sum(d) / len(d), "lo": lo, "hi": hi, "n": len(d)}


def _boot_ci(xs, n_boot=2000, seed=0):
    """95% percentile bootstrap interval of the mean."""
    import numpy as np
    a = np.asarray(xs, dtype=float)
    rng = np.random.default_rng(seed)
    means = np.empty(n_boot)
    step = max(1, 2_000_000 // max(1, len(a)))  # chunk to bound memory
    for i in range(0, n_boot, step):
        m = min(step, n_boot - i)
        means[i:i + m] = a[rng.integers(0, len(a), size=(m, len(a)))].mean(axis=1)
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def weighted_kappa(a: List[int], b: List[int], n_cls=4) -> float:
    """Quadratic-weighted Cohen's kappa between two graders."""
    if not a:
        return NAN
    O = [[0] * n_cls for _ in range(n_cls)]
    for x, y in zip(a, b):
        O[x][y] += 1
    n = len(a)
    ra = [sum(O[i]) for i in range(n_cls)]
    cb = [sum(O[i][j] for i in range(n_cls)) for j in range(n_cls)]
    num = den = 0.0
    for i in range(n_cls):
        for j in range(n_cls):
            w = (i - j) ** 2 / (n_cls - 1) ** 2
            num += w * O[i][j]
            den += w * ra[i] * cb[j] / n
    return 1 - num / den if den else 1.0


def auc_of_chosen(grades: Dict[str, int], chosen: str) -> float:
    """Share of not-chosen items the chosen item out-grades (ties count half)."""
    if chosen not in grades or len(grades) < 2:
        return NAN
    c = grades[chosen]
    others = [g for p, g in grades.items() if p != chosen]
    return sum(1.0 if c > g else 0.5 if c == g else 0.0 for g in others) / len(others)


def mean_ci(xs: List[float], n_boot=2000, seed=0) -> dict:
    xs = [x for x in xs if not math.isnan(x)]
    if not xs:
        return {"mean": NAN, "lo": NAN, "hi": NAN, "n": 0}
    lo, hi = _boot_ci(xs, n_boot, seed)
    return {"mean": sum(xs) / len(xs), "lo": lo, "hi": hi, "n": len(xs)}
