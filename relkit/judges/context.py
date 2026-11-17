"""Who the judge is grading for. Three modes:

generic  - a typical shopper; nothing known
segment  - the shopper's segment persona (cheap, coarse)
history  - this shopper's own devices and recent purchases (best in our study)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from ..schema import Product, Segment, User


@dataclass
class ShopperContext:
    mode: str
    segment: Optional[Segment] = None
    user: Optional[User] = None
    recent: List[Product] = field(default_factory=list)  # newest first

    @property
    def key(self) -> str:
        if self.mode == "generic":
            return "generic"
        if self.mode == "segment":
            return f"segment:{self.segment.segment_id if self.segment else ''}"
        return f"user:{self.user.user_id if self.user else ''}"

    def describe(self, include_segment: bool = False) -> str:
        if self.mode == "generic":
            return "Nothing is known about this shopper. Judge for a typical customer of this store."
        if self.mode == "segment":
            s = self.segment
            return f"The shopper belongs to the customer segment \"{s.name}\". {s.description}".strip()
        parts = []
        if include_segment and self.segment:
            parts.append(f"Segment: {self.segment.name}. {self.segment.description}")
        if self.user and self.user.devices:
            parts.append("Devices this shopper buys accessories for: " + ", ".join(self.user.devices) + ".")
        if self.recent:
            lines = []
            for p in self.recent:
                price = f" (${p.price:.2f})" if p.price is not None else ""
                lines.append(f"- {p.title}{price}")
            parts.append("Their most recent purchases, newest first:\n" + "\n".join(lines))
        if not parts:
            return "This shopper has no purchase history. Judge for a typical customer of this store."
        return "\n".join(parts)


def make_context(mode: str, user: Optional[User], segments: Dict[str, Segment],
                 catalog: Dict[str, Product], history_items: int = 5) -> ShopperContext:
    seg = segments.get(user.segment) if user else None
    if mode == "generic":
        return ShopperContext("generic")
    if mode == "segment":
        if seg is None:
            return ShopperContext("generic")
        return ShopperContext("segment", segment=seg, user=user)
    recent = [catalog[p] for p in reversed(user.history) if p in catalog][:history_items] if user else []
    return ShopperContext("history", segment=seg, user=user, recent=recent)


def context_from_key(key: str, users, segments, catalog, history_items=5) -> ShopperContext:
    """Parse 'generic' / 'segment:<id>' / 'user:<id>' (used by golden labels)."""
    if key == "generic":
        return ShopperContext("generic")
    kind, _, ident = key.partition(":")
    if kind == "segment":
        return ShopperContext("segment", segment=segments[ident])
    if kind == "user":
        return make_context("history", users[ident], segments, catalog, history_items)
    raise ValueError(f"Bad context '{key}'")
