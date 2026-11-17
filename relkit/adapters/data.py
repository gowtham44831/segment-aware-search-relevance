"""Loaders for catalog, segments, users and queries.

Companies usually only touch the config: point `path` at your file and map your
column names with `columns: {our_name: your_name}`. Unmapped columns are kept as
extra product attributes and shown to the LLM judge.
"""
from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path
from typing import Dict, Iterable, List

import yaml

from ..schema import Product, Query, Segment, User

PRODUCT_FIELDS = ["product_id", "title", "description", "category", "brand", "price", "rating", "review_count", "fits"]


def _rows(path: Path) -> Iterable[dict]:
    path = Path(path)
    if path.suffix in (".jsonl", ".ndjson"):
        with open(path) as f:
            for line in f:
                if line.strip():
                    yield json.loads(line)
    elif path.suffix == ".json":
        with open(path) as f:
            yield from json.load(f)
    elif path.suffix in (".csv", ".tsv"):
        with open(path, newline="") as f:
            yield from csv.DictReader(f, delimiter="\t" if path.suffix == ".tsv" else ",")
    elif path.suffix == ".parquet":
        import pandas as pd  # optional dependency
        yield from pd.read_parquet(path).to_dict("records")
    else:
        raise ValueError(f"Unsupported file type: {path}")


def _remap(row: dict, columns: Dict[str, str]) -> dict:
    """columns maps our field name -> your column name."""
    out = dict(row)
    for ours, theirs in (columns or {}).items():
        if theirs in row:
            out[ours] = row[theirs]
            if theirs != ours:
                out.pop(theirs, None)
    return out


def _num(v, cast=float):
    if v in (None, ""):
        return None
    try:
        return cast(float(str(v).replace("$", "").replace(",", "")))
    except ValueError:
        return None


def _list(v) -> List[str]:
    if v in (None, ""):
        return []
    if isinstance(v, list):
        return [str(x) for x in v]
    return [x.strip() for x in str(v).replace("|", ";").split(";") if x.strip()]


def load_catalog(spec: dict, root: Path) -> Dict[str, Product]:
    keep_extra = spec.get("extra_fields")  # None = keep all unmapped columns
    out = {}
    for raw in _rows(root / spec["path"]):
        r = _remap(raw, spec.get("columns", {}))
        extra = {k: v for k, v in r.items() if k not in PRODUCT_FIELDS}
        if keep_extra is not None:
            extra = {k: v for k, v in extra.items() if k in keep_extra}
        p = Product(
            product_id=str(r["product_id"]),
            title=str(r.get("title") or ""),
            description=str(r.get("description") or ""),
            category=str(r.get("category") or ""),
            brand=str(r.get("brand") or ""),
            price=_num(r.get("price")),
            rating=_num(r.get("rating")),
            review_count=_num(r.get("review_count"), int),
            fits=_list(r.get("fits")),
            extra=extra,
        )
        out[p.product_id] = p
    return out


def load_devices(path, root: Path) -> Dict[str, dict]:
    """Optional devices file: id -> {name, ecosystem, aliases}. Lets judges and
    engines recognise device names typed in searches ("iphone 15 pro case")."""
    if not path:
        return {}
    with open(root / path) as f:
        return yaml.safe_load(f) or {}


def load_segments(path, root: Path) -> Dict[str, Segment]:
    with open(root / path) as f:
        raw = yaml.safe_load(f)
    out = {}
    for sid, s in raw.items():
        attrs = {k: v for k, v in s.items() if k not in ("name", "description")}
        out[sid] = Segment(sid, s.get("name", sid), s.get("description", ""), attrs)
    return out


def load_users(spec: dict, root: Path, catalog: Dict[str, Product]) -> Dict[str, User]:
    """Users file: user_id, segment, optional devices, optional history (list of ids).
    Or give `purchases: {path, columns}` (user_id, product_id, timestamp) and the
    last `history_len` purchases become the history."""
    users = {}
    for raw in _rows(root / spec["path"]):
        r = _remap(raw, spec.get("columns", {}))
        uid = str(r["user_id"])
        users[uid] = User(
            user_id=uid,
            segment=str(r.get("segment") or ""),
            devices=_list(r.get("devices")),
            history=_list(r.get("history")),
            attrs={k: v for k, v in r.items() if k not in ("user_id", "segment", "devices", "history")},
        )
    if spec.get("purchases"):
        ps = spec["purchases"]
        events = {}
        for raw in _rows(root / ps["path"]):
            r = _remap(raw, ps.get("columns", {}))
            events.setdefault(str(r["user_id"]), []).append((str(r.get("timestamp", "")), str(r["product_id"])))
        n = int(spec.get("history_len", 20))
        for uid, ev in events.items():
            u = users.setdefault(uid, User(uid))
            u.history = [pid for _, pid in sorted(ev)][-n:]
    for u in users.values():
        if not u.devices:
            u.devices = infer_devices(u, catalog)
    return users


def infer_devices(user: User, catalog: Dict[str, Product], min_count: int = 1) -> List[str]:
    """Devices a shopper buys for = device models their past purchases fit."""
    c = Counter()
    for pid in user.history:
        p = catalog.get(pid)
        if p:
            for d in p.fits:
                if d not in ("any", "self", "legacy"):
                    c[d] += 1
    return [d for d, n in c.most_common() if n >= min_count]


def load_queries(spec: dict, root: Path) -> List[Query]:
    out = []
    for i, raw in enumerate(_rows(root / spec["path"])):
        r = _remap(raw, spec.get("columns", {}))
        out.append(Query(str(r.get("query_id") or f"Q{i+1:05d}"), str(r["query"]), str(r.get("user_id") or ""),
                         str(r.get("segment") or "")))
    return out
