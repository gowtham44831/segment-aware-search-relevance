from __future__ import annotations

import hashlib
import json
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import List, Optional, Tuple

from ..schema import Judgment, Product
from .context import ShopperContext


class Judge:
    """Grades one (query, product, shopper) at a time: 0-3 plus a reason.
    Each result is graded on its own, so position on the page doesn't matter."""

    signature = "judge"
    workers = 1
    batch_size = 1

    def grade(self, query: str, product: Product, ctx: ShopperContext) -> Judgment:
        raise NotImplementedError

    def grade_batch(self, query: str, products: List[Product], ctx: ShopperContext) -> List[Judgment]:
        return [self.grade(query, p, ctx) for p in products]


class CachedJudge:
    """Wraps a judge with an on-disk cache so reruns cost nothing."""

    def __init__(self, judge: Judge, cache_path: Optional[Path], include_segment=False):
        self.judge = judge
        self.include_segment = include_segment
        self.path = cache_path
        self.cache = {}
        self.lock = threading.Lock()
        self._fh = None
        if cache_path and cache_path.exists():
            with open(cache_path) as f:
                for line in f:
                    try:
                        r = json.loads(line)
                        self.cache[r["key"]] = Judgment(r["grade"], r.get("reason", ""))
                    except (json.JSONDecodeError, KeyError):
                        pass

    def _key(self, query, product, ctx):
        blob = json.dumps([self.judge.signature, query.lower().strip(), product.card(),
                           ctx.mode, ctx.describe(self.include_segment)])
        return hashlib.sha1(blob.encode()).hexdigest()

    def grade(self, query, product, ctx) -> Judgment:
        k = self._key(query, product, ctx)
        if k in self.cache:
            return self.cache[k]
        j = self.judge.grade(query, product, ctx)
        self._store(k, j)
        return j

    def _store(self, k, j):
        with self.lock:
            self.cache[k] = j
            if self.path:
                if self._fh is None:
                    self.path.parent.mkdir(parents=True, exist_ok=True)
                    self._fh = open(self.path, "a")
                self._fh.write(json.dumps({"key": k, "grade": j.grade, "reason": j.reason}) + "\n")
                self._fh.flush()

    def missing(self, items):
        """Items not yet cached (for cost estimates)."""
        return [it for it in items if self._key(*it) not in self.cache]

    def grade_many(self, items: List[Tuple[str, Product, ShopperContext]], progress=None) -> List[Judgment]:
        """Grades many items. With a batching judge (batch_size > 1), uncached items
        for the same search and shopper are sent together in one call."""
        out = [None] * len(items)
        keys = [self._key(*it) for it in items]
        todo = []
        for i, k in enumerate(keys):
            if k in self.cache:
                out[i] = self.cache[k]
                if progress:
                    progress()
            else:
                todo.append(i)
        bs = int(getattr(self.judge, "batch_size", 1) or 1)
        groups = defaultdict(list)
        for i in todo:
            q, _, ctx = items[i]
            groups[(q.lower().strip(), ctx.mode, ctx.describe(self.include_segment))].append(i)
        chunks = []
        seen = {}
        for idx in groups.values():
            uniq = []
            for i in idx:  # same key twice in one run -> grade once
                if keys[i] in seen:
                    continue
                seen[keys[i]] = i
                uniq.append(i)
            chunks += [uniq[j:j + bs] for j in range(0, len(uniq), bs)]

        def work(chunk):
            q, _, ctx = items[chunk[0]]
            prods = [items[i][1] for i in chunk]
            if len(chunk) > 1:
                js = self.judge.grade_batch(q, prods, ctx)
            else:
                js = [self.judge.grade(q, prods[0], ctx)]
            for i, j in zip(chunk, js):
                self._store(keys[i], j)
                out[i] = j
                if progress:
                    progress()

        with ThreadPoolExecutor(max_workers=max(1, self.judge.workers)) as ex:
            list(ex.map(work, chunks))
        for i in todo:  # duplicates within the run
            if out[i] is None:
                out[i] = self.cache[keys[i]]
                if progress:
                    progress()
        return out
