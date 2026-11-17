"""relkit command line.

  python -m relkit judges    --config config/mock.yaml   # build segment judges from data
  python -m relkit validate  --config config/mock.yaml   # judge vs golden labels
  python -m relkit calibrate --config config/mock.yaml   # judge vs real shopper choices
  python -m relkit estimate  --config config/mock.yaml   # judgments / LLM calls / cost before a run
  python -m relkit measure   --config config/mock.yaml   # grade every engine's results
  python -m relkit report    --config config/mock.yaml   # HTML report from saved outputs
  python -m relkit all       --config config/mock.yaml   # everything, in order
"""
import argparse
import json
import sys

from .project import Project


def main(argv=None):
    ap = argparse.ArgumentParser(prog="relkit", description="Segment-aware search relevance measurement")
    ap.add_argument("command", choices=["judges", "validate", "calibrate", "estimate", "measure", "report", "all"])
    ap.add_argument("--config", required=True)
    ap.add_argument("--judge", choices=["rules", "llm"], help="override judge.type from the config")
    ap.add_argument("--strict", action="store_true", help="exit 1 if the judge fails the validation gate (for CI)")
    a = ap.parse_args(argv)

    p = Project(a.config)
    if a.judge:
        p.cfg.setdefault("judge", {})["type"] = a.judge
    from . import steps
    from .report import build_report

    val = cal = None
    if a.command in ("judges", "all"):
        print("Segment judges (built from data)")
        steps.build_judges(p)
    if a.command == "estimate":
        print("Estimating a measure run")
        steps.estimate(p)
        return
    if a.command in ("validate", "all"):
        val = steps.validate(p)
        if a.strict and val and not val["passed"]:
            print("Judge failed the validation gate; stopping.")
            sys.exit(1)
    if a.command in ("calibrate", "all"):
        cal = steps.calibrate(p)
    if a.command in ("measure", "all"):
        steps.measure(p)
    if a.command in ("report", "all", "measure"):
        path = build_report(p)
        print(f"\nReport: {path}")


if __name__ == "__main__":
    main()
