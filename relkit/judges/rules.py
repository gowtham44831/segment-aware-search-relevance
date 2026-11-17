"""Offline rule-based judge.

Runs with no API key, so the whole pipeline can be tested for free and in CI.
It encodes simple, explicit store rules (query intent -> category, device fit,
price fit, brand affinity). It is a stand-in and a baseline, not a model of
customers: use the LLM judge for real measurement, and keep rules for
must-never-happen checks (e.g. an iPhone case shown to a Galaxy owner).

Intents are configurable under judge.rules.intents in the config.
"""
from __future__ import annotations

import re
import statistics
from collections import defaultdict
from typing import Dict, List

from ..schema import Judgment, Product
from .base import Judge
from .context import ShopperContext

DEFAULT_INTENTS = [
    # phrase -> primary (can be 3), related (max 2), complement (max 1)
    {"match": ["wireless charger", "magsafe charger", "charging pad", "wireless charging stand"], "primary": ["wireless_charger"], "related": ["car_mount"], "complement": ["charger", "power_bank", "cable"]},
    {"match": ["fast charger", "wall charger", "charger", "charging block", "power adapter"], "primary": ["charger"], "related": ["wireless_charger"], "complement": ["cable", "power_bank"]},
    {"match": ["charging cable", "usb c cable", "lightning cable", "cable", "charger cord"], "primary": ["cable"], "related": [], "complement": ["charger"]},
    {"match": ["screen protector", "tempered glass", "screen guard", "camera lens protector"], "primary": ["screen_protector"], "related": [], "complement": ["phone_case"]},
    {"match": ["phone case", "case", "cover", "protective case"], "primary": ["phone_case"], "related": ["tablet_case"], "complement": ["phone_charm", "screen_protector", "phone_grip"]},
    {"match": ["earbuds", "earphones", "headphones", "airpods", "bluetooth headphones"], "primary": ["earbuds"], "related": [], "complement": []},
    {"match": ["power bank", "portable charger", "battery pack"], "primary": ["power_bank"], "related": [], "complement": ["charger", "cable"]},
    {"match": ["watch band", "watch strap", "band"], "primary": ["watch_band"], "related": [], "complement": []},
    {"match": ["car mount", "car holder", "phone holder", "car phone holder"], "primary": ["car_mount"], "related": ["phone_stand"], "complement": ["phone_grip"]},
    {"match": ["phone grip", "popsocket", "grip"], "primary": ["phone_grip"], "related": ["phone_stand"], "complement": ["phone_case"]},
    {"match": ["phone stand", "stand", "desk phone holder"], "primary": ["phone_stand"], "related": ["phone_grip", "wireless_charger"], "complement": []},
]

# query term -> text the product must contain (hard: grade 0 if missing)
DEFAULT_CONSTRAINTS = {
    "usb c": ["usb-c", "usb c"], "lightning": ["lightning"], "magsafe": ["magsafe", "magnetic"],
}
# used only when no devices file is configured
FALLBACK_DEVICES = {"iphone15": ["iphone 15"], "iphone14": ["iphone 14"], "galaxys24": ["galaxy s24"], "pixel8": ["pixel 8"]}
# query attributes the product should have (soft: grade capped at 2 if missing)
DEFAULT_ATTRIBUTES = ["clear", "rugged", "wallet", "slim", "leather", "silicone", "privacy", "camera lens", "nylon",
                      "metal", "sports", "noise cancelling", "65w", "45w", "20w", "3 port", "6ft", "10ft", "3ft",
                      "20000mah", "10000mah", "magnetic"]

ECOSYSTEM_PREFIX = {"apple": ("iphone", "applewatch", "ipad"), "samsung": ("galaxy",), "google": ("pixel",)}
ECOSYSTEM_BRAND = {"apple": "Apple", "samsung": "Samsung", "google": "Google"}
CHEAP_WORDS = ("cheap", "budget", "affordable", "under")


def ecosystem_of(device: str) -> str:
    for eco, prefixes in ECOSYSTEM_PREFIX.items():
        if device.startswith(prefixes):
            return eco
    return ""


class RulesJudge(Judge):
    signature = "rules-v2"

    def __init__(self, catalog: Dict[str, Product], intents=None, constraints=None, attributes=None,
                 devices=None, **_):
        self.intents = intents or DEFAULT_INTENTS
        self.constraints = constraints or DEFAULT_CONSTRAINTS
        self.attributes = attributes or DEFAULT_ATTRIBUTES
        aliases = {d: v.get("aliases", [v.get("name", d).lower()]) for d, v in devices.items()} if devices else FALLBACK_DEVICES
        self.device_aliases = sorted(((a.lower(), d) for d, al in aliases.items() for a in al), key=lambda x: -len(x[0]))
        self.brands = {p.brand.lower() for p in catalog.values() if p.brand and p.brand.lower() != "generic"}
        words = {w for p in catalog.values() for w in re.findall(r"[a-z0-9]+", p.text().lower())}
        words |= {w for it in self.intents for m in it["match"] for w in m.split()}
        self.vocab = sorted(words)
        self.vocab_set = set(words)
        by_cat = defaultdict(list)
        for p in catalog.values():
            if p.price is not None:
                by_cat[p.category].append(p.price)
        self.median = {c: statistics.median(v) for c, v in by_cat.items()}

    # --- helpers
    def _fix_typos(self, q: str) -> str:
        if not hasattr(self, "_typo_cache"):
            self._typo_cache = {}
        if q not in self._typo_cache:
            self._typo_cache[q] = self._fix_typos_uncached(q)
        return self._typo_cache[q]

    def _fix_typos_uncached(self, q: str) -> str:
        import difflib
        out = []
        for t in q.split():
            if t.isalpha() and len(t) > 3 and t not in self.vocab_set:
                m = difflib.get_close_matches(t, self.vocab, n=1, cutoff=0.8)
                t = m[0] if m else t
            out.append(t)
        return " ".join(out)

    def _query_device(self, q: str):
        for alias, dev in self.device_aliases:
            if re.search(rf"\b{re.escape(alias)}\b", q):
                return dev
        return None

    def _intent(self, q: str):
        best, best_len = None, 0
        for it in self.intents:
            for m in it["match"]:
                if re.search(rf"\b{re.escape(m)}\b", q) and len(m) > best_len:
                    best, best_len = it, len(m)
        return best

    def _price_sensitivity(self, ctx: ShopperContext) -> str:
        if ctx.mode == "segment" and ctx.segment:
            return ctx.segment.attrs.get("price_sensitivity", "medium")
        if ctx.mode == "history" and ctx.recent:
            ratios = [p.price / self.median[p.category] for p in ctx.recent
                      if p.price and self.median.get(p.category)]
            if ratios:
                r = statistics.median(ratios)
                return "high" if r < 0.75 else "low" if r > 1.4 else "medium"
        return "medium"

    def _ecosystems(self, ctx: ShopperContext) -> set:
        if ctx.mode == "segment" and ctx.segment:
            eco = ctx.segment.attrs.get("ecosystem", "mixed")
            return {eco} if eco != "mixed" else set()
        if ctx.mode == "history" and ctx.user:
            return {ecosystem_of(d) for d in ctx.user.devices} - {""}
        return set()

    # --- main
    def grade(self, query, product, ctx) -> Judgment:
        q = self._fix_typos(query.lower())
        intent = self._intent(q)
        cat = product.category
        if intent is None:
            hit = any(t in product.text().lower() for t in q.split())
            return Judgment(2 if hit else 0, "No intent rule for this query; lexical check only")
        if cat in intent["primary"]:
            grade, why = 3, "Right kind of product"
        elif cat in intent.get("related", []):
            grade, why = 2, f"Related product ({cat.replace('_', ' ')})"
        elif cat in intent.get("complement", []):
            return Judgment(1, f"Complementary item ({cat.replace('_', ' ')}), not what was searched")
        else:
            return Judgment(0, f"Wrong kind of product ({cat.replace('_', ' ') or 'unknown'})")

        text = product.text().lower()
        for term, needs in self.constraints.items():
            if re.search(rf"\b{re.escape(term)}\b", q) and not any(re.search(rf"\b{re.escape(n)}\b", text) for n in needs):
                return Judgment(0, f"Query asks for '{term}', product doesn't match")

        fits = set(product.fits)
        specific = bool(fits) and not fits & {"any", "self"}
        if "legacy" in fits:
            grade, why = min(grade, 1), "Legacy connector"
        qdev = self._query_device(q)
        if qdev and specific:
            if qdev not in fits:
                return Judgment(0, f"Search names {qdev}; this item doesn't fit it")
            why += f"; fits {qdev}"
        elif qdev and not specific:
            why += "; universal item"
        elif specific and ctx.mode == "history" and ctx.user and ctx.user.devices:
            if not fits & set(ctx.user.devices):
                return Judgment(0, f"Doesn't fit their devices ({', '.join(ctx.user.devices)})")
            why += "; fits their device"
        elif specific and ctx.mode == "segment":
            ecos = self._ecosystems(ctx)
            item_ecos = {ecosystem_of(d) for d in fits} - {""}
            if ecos and item_ecos and not ecos & item_ecos:
                return Judgment(0, f"Made for {', '.join(sorted(item_ecos))} devices; segment uses {', '.join(sorted(ecos))}")
            if not ecos:
                grade, why = min(grade, 2), why + "; device fit can't be confirmed"

        qbrand = next((b for b in self.brands if re.search(rf"\b{re.escape(b)}\b", q)), None)
        if qbrand and product.brand.lower() != qbrand:
            grade, why = min(grade, 2), why + f"; searched for {qbrand}, this is {product.brand}"
        for a in self.attributes:
            if re.search(rf"\b{re.escape(a)}\b", q) and a not in text:
                grade, why = min(grade, 2), why + f"; lacks '{a}'"
                break

        ecos = self._ecosystems(ctx)
        rivals = {ECOSYSTEM_BRAND[e] for e in ECOSYSTEM_BRAND if e not in ecos} if ecos else set()
        if product.brand in rivals and len(ecos) == 1:
            grade, why = grade - 1, why + f"; rival-ecosystem brand ({product.brand})"

        med = self.median.get(cat)
        if product.price and med:
            ratio = product.price / med
            sens = self._price_sensitivity(ctx)
            if any(w in q for w in CHEAP_WORDS) and ratio > 1.0:
                grade, why = min(grade, 1), why + "; too expensive for a 'cheap' search"
            elif sens == "high" and ratio > 1.5:
                grade, why = grade - 2, why + f"; price {ratio:.1f}x typical, too high for a budget shopper"
            elif sens == "low" and ratio < 0.35:
                grade, why = grade - 2, why + "; very cheap item for a premium shopper"
            elif sens == "low" and ratio < 0.6:
                grade, why = grade - 1, why + "; budget item for a premium shopper"
        return Judgment(max(0, min(3, grade)), why)
