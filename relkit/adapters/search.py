"""Search engines under test.

Built-in demo engines run over the catalog (bm25, bm25_personal, popularity).
For real use, plug in your own engine with one of:
  - type: results_file  -> results you already logged (query_id, rank, product_id)
  - type: http          -> call your search API per query
  - type: python        -> any class with search(query, user, k) -> list of ids
"""
from __future__ import annotations

import importlib
import json
import math
import os
import re
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Optional

from ..schema import Product, Query, User

TOKEN = re.compile(r"[a-z0-9]+")


def tokens(text: str) -> List[str]:
    return TOKEN.findall(text.lower())


class Engine:
    name = "engine"

    def search(self, query: Query, user: Optional[User], k: int) -> List[str]:
        raise NotImplementedError


class BM25(Engine):
    """Plain lexical search over title, description, category and brand."""

    def __init__(self, catalog: Dict[str, Product], k1=1.2, b=0.75, **_):
        self.catalog = catalog
        self.docs = {pid: tokens(p.text()) for pid, p in catalog.items()}
        self.avgdl = sum(map(len, self.docs.values())) / max(1, len(self.docs))
        df = Counter(t for d in self.docs.values() for t in set(d))
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - c + 0.5) / (c + 0.5)) for t, c in df.items()}
        self.tf = {pid: Counter(d) for pid, d in self.docs.items()}
        self.k1, self.b = k1, b

    def scores(self, q: str) -> Dict[str, float]:
        qt = tokens(q)
        out = {}
        for pid, tf in self.tf.items():
            dl = len(self.docs[pid])
            s = 0.0
            for t in qt:
                if t in tf:
                    f = tf[t]
                    s += self.idf[t] * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * dl / self.avgdl))
            if s > 0:
                out[pid] = s
        return out

    def search(self, query, user, k):
        s = self.scores(query.query)
        return [pid for pid, _ in sorted(s.items(), key=lambda x: -x[1])[:k]]


class PersonalBM25(BM25):
    """BM25 plus a boost for items that fit the shopper's devices and a
    penalty for device-specific items that don't (a simple personalised ranker)."""

    def __init__(self, catalog, device_boost=2.0, **kw):
        super().__init__(catalog, **kw)
        self.boost = float(device_boost)

    def search(self, query, user, k):
        s = self.scores(query.query)
        devices = set(user.devices) if user else set()
        for pid in s:
            fits = set(self.catalog[pid].fits)
            if not devices or not fits or fits & {"any"}:
                continue
            s[pid] += self.boost if fits & devices else -self.boost
        return [pid for pid, _ in sorted(s.items(), key=lambda x: -x[1])[:k]]


class Popularity(BM25):
    """Best-sellers: any lexical match, ordered by review count (ignores the shopper)."""

    def search(self, query, user, k):
        cand = list(self.scores(query.query))
        cand.sort(key=lambda pid: -(self.catalog[pid].review_count or 0))
        return cand[:k]


DEFAULT_SYNONYMS = {
    "cover": "case", "screen guard": "screen protector", "charging block": "charger", "power adapter": "charger",
    "charger cord": "charging cable", "bluetooth headphones": "wireless earbuds", "portable charger": "power bank",
    "battery pack": "power bank", "watch strap": "watch band", "car phone holder": "car mount",
    "desk phone holder": "phone stand", "popsocket": "phone grip", "charging pad": "wireless charger",
}


class ExpandedBM25(BM25):
    """Stand-in for a semantic / hybrid engine: fixes typos against the catalog
    vocabulary and expands synonyms before BM25. Optional device boost."""

    def __init__(self, catalog, synonyms=None, device_boost=0.0, **kw):
        super().__init__(catalog, **kw)
        self.syn = synonyms or DEFAULT_SYNONYMS
        self.boost = float(device_boost)
        self.vocab = sorted(self.idf)

    def expand(self, q: str) -> str:
        import difflib
        toks = []
        for t in tokens(q):
            if t not in self.idf and len(t) > 3:
                m = difflib.get_close_matches(t, self.vocab, n=1, cutoff=0.8)
                t = m[0] if m else t
            toks.append(t)
        q2 = " ".join(toks)
        for a, b in self.syn.items():
            if re.search(rf"\b{re.escape(a)}\b", q2):
                q2 += " " + b
        return q2

    def search(self, query, user, k):
        s = self.scores(self.expand(query.query))
        devices = set(user.devices) if (user and self.boost) else set()
        for pid in s:
            fits = set(self.catalog[pid].fits)
            if devices and fits and not fits & {"any"}:
                s[pid] += self.boost if fits & devices else -self.boost
        return [pid for pid, _ in sorted(s.items(), key=lambda x: -x[1])[:k]]


class ResultsFile(Engine):
    """Precomputed results: columns query_id, rank, product_id (optionally engine)."""

    def __init__(self, catalog, path, root: Path, engine_filter=None, **_):
        from .data import _rows
        self.res = defaultdict(list)
        for r in _rows(root / path):
            if engine_filter and r.get("engine") != engine_filter:
                continue
            self.res[str(r["query_id"])].append((int(r["rank"]), str(r["product_id"])))

    def search(self, query, user, k):
        return [pid for _, pid in sorted(self.res.get(query.query_id, []))[:k]]


def _json_path(obj, path: str):
    """Tiny path syntax: 'results[].product.id' -> list of values."""
    vals = [obj]
    for part in path.split("."):
        nxt = []
        many = part.endswith("[]")
        key = part[:-2] if many else part
        for v in vals:
            v = v.get(key) if key else v
            if v is None:
                continue
            nxt.extend(v if many else [v])
        vals = nxt
    return [str(v) for v in vals]


class HTTP(Engine):
    """Calls your search API. url can use {query}, {user_id}, {segment}, {k}.
    headers values like '$ENV_VAR' are read from the environment."""

    def __init__(self, catalog, url, ids_path, method="GET", headers=None, body=None, timeout=20, **_):
        self.url, self.ids_path, self.method = url, ids_path, method.upper()
        self.headers = {k: os.environ.get(v[1:], "") if str(v).startswith("$") else v for k, v in (headers or {}).items()}
        self.body, self.timeout = body, timeout

    def search(self, query, user, k):
        vals = {"query": urllib.parse.quote(query.query), "user_id": user.user_id if user else "",
                "segment": user.segment if user else "", "k": k}
        url = self.url.format(**vals)
        data = None
        if self.method == "POST":
            body = json.dumps(self.body or {}).replace("{query}", query.query).replace("{user_id}", vals["user_id"]).replace('"{k}"', str(k))
            data = body.encode()
        req = urllib.request.Request(url, data=data, method=self.method, headers={"Content-Type": "application/json", **self.headers})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return _json_path(json.load(r), self.ids_path)[:k]


BUILTIN = {"bm25": BM25, "bm25_personal": PersonalBM25, "popularity": Popularity, "expanded": ExpandedBM25,
           "results_file": ResultsFile, "http": HTTP}


def build_engine(spec: dict, catalog: Dict[str, Product], root: Path) -> Engine:
    spec = dict(spec)
    name, typ = spec.pop("name"), spec.pop("type")
    if typ == "python":  # class: "my_module:MySearch"
        mod, cls = spec.pop("class").split(":")
        eng = getattr(importlib.import_module(mod), cls)(catalog=catalog, **spec)
    else:
        if typ not in BUILTIN:
            raise ValueError(f"Unknown engine type '{typ}'. Use one of {list(BUILTIN)} or python")
        eng = BUILTIN[typ](catalog, root=root, **spec)
    eng.name = name
    return eng
