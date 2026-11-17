"""Loads a config file and wires catalog, users, engines and judge together."""
from __future__ import annotations

import os
from pathlib import Path

import yaml

from .adapters.data import load_catalog, load_devices, load_queries, load_segments, load_users
from .adapters.search import build_engine
from .judges.base import CachedJudge


def _load_dotenv(path: Path):
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


class Project:
    def __init__(self, config_path: str):
        cfg_path = Path(config_path).resolve()
        self.cfg = yaml.safe_load(cfg_path.read_text())
        self.root = (cfg_path.parent / self.cfg.get("root", "..")).resolve()
        _load_dotenv(self.root / ".env")
        c = self.cfg
        self.name = c.get("project", cfg_path.stem)
        self.k = int(c.get("top_k", 10))
        self.modes = c.get("modes", ["generic", "segment", "history"])
        self.out = self.root / c.get("output_dir", f"out/{cfg_path.stem}")
        self.out.mkdir(parents=True, exist_ok=True)

        self.catalog = load_catalog(c["catalog"], self.root)
        self.segments = load_segments(c["segments"], self.root) if c.get("segments") else {}
        self.users = load_users(c["users"], self.root, self.catalog) if c.get("users") else {}
        self.queries = load_queries(c["queries"], self.root) if c.get("queries") else []
        for q in self.queries:
            if not q.segment and q.user_id in self.users:
                q.segment = self.users[q.user_id].segment
        self.devices = load_devices(c.get("devices"), self.root)
        self.profiles = {}
        if c.get("segment_profiles", "manual") == "auto" and self.users:
            from .judges.profiles import apply_profiles, build_profiles
            self.profiles = build_profiles(self.catalog, self.users, self.segments, self.queries, self.devices)
            apply_profiles(self.segments, self.profiles)
        self._engines = None
        self._judge = None

    @property
    def engines(self):
        if self._engines is None:
            self._engines = [build_engine(e, self.catalog, self.root) for e in self.cfg.get("engines", [])]
        return self._engines

    @property
    def judge(self) -> CachedJudge:
        if self._judge is None:
            j = dict(self.cfg.get("judge", {"type": "rules"}))
            typ = j.pop("type", "rules")
            if typ == "rules":
                from .judges.rules import RulesJudge
                judge = RulesJudge(self.catalog, devices=self.devices, **j.get("rules", {}))
            elif typ == "llm":
                from .judges.llm import LLMJudge
                judge = LLMJudge(store=self.cfg.get("store", self.name), **j)
            else:
                raise ValueError(f"Unknown judge type {typ}")
            safe = judge.signature.replace(":", "_").replace("/", "_")
            self._judge = CachedJudge(judge, self.out / "cache" / f"{safe}.jsonl", j.get("include_segment", False))
        return self._judge

    @property
    def history_items(self) -> int:
        return int(self.cfg.get("judge", {}).get("history_items", 5))

    def path(self, key):
        v = self.cfg.get(key)
        return (self.root / v) if v else None
