"""Run: python -m pytest -q   (or python tests/test_relkit.py)"""
import csv
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from relkit import steps  # noqa: E402
from relkit.adapters.search import _json_path  # noqa: E402
from relkit.judges.llm import LLMJudge  # noqa: E402
from relkit.metrics import auc_of_chosen, query_metrics, weighted_kappa  # noqa: E402
from relkit.project import Project  # noqa: E402
from relkit.report import build_report  # noqa: E402


def _project(tmp):
    p = Project(str(ROOT / "config" / "mock.yaml"))
    p.out = Path(tmp)
    p.out.mkdir(parents=True, exist_ok=True)
    p.cfg["judge"] = {"type": "rules"}
    return p


def test_metrics():
    # shown: 4 results, 2 relevant; pool holds 5 relevant products in total
    m = query_metrics([3, 0, 2, 1], [3, 0, 2, 1, 3, 2, 2], k=4)
    assert m["precision"] == 0.5 and m["recall"] == 2 / 5 and m["recall_capped"] == 2 / 4
    assert m["mrr"] == 1.0 and m["hit_exact"] == 1 and m["irrelevant_rate"] == 0.25
    z = query_metrics([], [0, 1], k=10)
    assert z["zero_results"] == 1 and z["precision"] == 0 and z["recall"] != z["recall"]  # nan: nothing relevant
    assert weighted_kappa([0, 1, 2, 3], [0, 1, 2, 3]) == 1.0
    assert auc_of_chosen({"a": 3, "b": 1, "c": 3}, "a") == 0.75


def test_llm_parsing():
    assert LLMJudge._parse('{"grade": 2, "reason": "ok"}').grade == 2
    assert LLMJudge._parse('Sure! {"grade": 5, "reason": "x"}').grade == 3
    assert LLMJudge._parse("grade 1").grade == 1


def test_json_path():
    assert _json_path({"results": [{"p": {"id": 1}}, {"p": {"id": 2}}]}, "results[].p.id") == ["1", "2"]


class _CountingBatchJudge:
    """Fake judge: records batch calls."""
    signature, workers, batch_size = "fake", 2, 5

    def __init__(self):
        self.calls = 0

    def grade(self, q, prod, ctx):
        from relkit.schema import Judgment
        self.calls += 1
        return Judgment(2, "single")

    def grade_batch(self, q, prods, ctx):
        from relkit.schema import Judgment
        self.calls += 1
        return [Judgment(3, "batch") for _ in prods]


def test_batching_and_cache(tmp_path):
    from relkit.judges.base import CachedJudge
    from relkit.judges.context import ShopperContext
    p = _project(tmp_path)
    prods = list(p.catalog.values())[:12]
    fj = _CountingBatchJudge()
    cj = CachedJudge(fj, tmp_path / "c.jsonl")
    items = [("phone case", pr, ShopperContext("generic")) for pr in prods]
    js = cj.grade_many(items)
    assert fj.calls == 3 and all(j.grade == 3 for j in js)  # 12 products in batches of 5
    cj2 = CachedJudge(_CountingBatchJudge(), tmp_path / "c.jsonl")
    cj2.grade_many(items)
    assert cj2.judge.calls == 0  # all cached on disk


def test_large_config_loads(tmp_path):
    p = Project(str(ROOT / "config" / "mock_large.yaml"))
    assert len(p.queries) == 4000 and set(p.profiles) == set(p.segments)
    assert all(q.segment for q in p.queries)


def test_end_to_end(tmp_path):
    p = _project(tmp_path)
    val = steps.validate(p)
    assert val["passed"]
    cal = steps.calibrate(p)
    assert cal["ALL"]["history"]["mean"] > cal["ALL"]["generic"]["mean"]
    res = steps.measure(p)
    assert len(res["scorecard"]) > 0
    ok = [r for r in res["scorecard"] if r["segment"] == "ALL"]
    assert all(0 <= r["precision"] <= 1 and 0 <= r["recall_capped"] <= 1 for r in ok)
    html = build_report(p).read_text()
    assert "Scorecard by judge" in html


def test_results_file_engine(tmp_path):
    p = _project(tmp_path)
    f = tmp_path / "logged.csv"
    with open(f, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["query_id", "rank", "product_id"])
        w.writerows([["Q001", 1, "CASE-IP15-SIL"], ["Q001", 2, "CASE-S24-SIL"]])
    p.cfg["engines"] = [{"name": "logged", "type": "results_file", "path": str(f)}]
    p.queries = p.queries[:1]
    res = steps.measure(p)
    grades = {r["product_id"]: r["grade"] for r in res["rows"] if r["mode"] == "history"}
    assert grades["CASE-IP15-SIL"] == 3 and grades["CASE-S24-SIL"] == 0  # U01 owns an iPhone 15


if __name__ == "__main__":
    import tempfile
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            with tempfile.TemporaryDirectory() as d:
                fn(Path(d)) if fn.__code__.co_argcount else fn()
            print("ok", name)
