"""Core data types. Everything company-specific is mapped onto these in adapters/."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

GRADE_LABELS = {
    3: "Exact: what this shopper is looking for",
    2: "Relevant, but a weaker fit (brand, price, can't confirm fit)",
    1: "Related or complementary, not what they meant",
    0: "Irrelevant, or won't work for this shopper",
}

MODES = ("generic", "segment", "history")


@dataclass
class Product:
    product_id: str
    title: str
    description: str = ""
    category: str = ""
    brand: str = ""
    price: Optional[float] = None
    rating: Optional[float] = None
    review_count: Optional[int] = None
    fits: List[str] = field(default_factory=list)  # device models; ["any"] = universal
    extra: Dict[str, Any] = field(default_factory=dict)

    def text(self) -> str:
        return " ".join([self.title, self.description, self.category.replace("_", " "), self.brand])

    def card(self) -> str:
        """Plain-text product card shown to an LLM judge."""
        lines = [f"Title: {self.title}"]
        if self.brand:
            lines.append(f"Brand: {self.brand}")
        if self.category:
            lines.append(f"Category: {self.category.replace('_', ' ')}")
        if self.price is not None:
            lines.append(f"Price: ${self.price:.2f}")
        if self.rating is not None:
            rc = f" from {self.review_count:,} reviews" if self.review_count else ""
            lines.append(f"Rating: {self.rating}/5{rc}")
        if self.fits and self.fits != ["any"]:
            lines.append(f"Compatible with: {', '.join(self.fits)}")
        if self.description:
            lines.append(f"Description: {self.description}")
        for k, v in self.extra.items():
            if v not in (None, ""):
                lines.append(f"{k.replace('_', ' ').capitalize()}: {v}")
        return "\n".join(lines)


@dataclass
class Segment:
    segment_id: str
    name: str
    description: str = ""
    attrs: Dict[str, Any] = field(default_factory=dict)


@dataclass
class User:
    user_id: str
    segment: str = ""
    devices: List[str] = field(default_factory=list)
    history: List[str] = field(default_factory=list)  # product ids, oldest first
    attrs: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Query:
    query_id: str
    query: str
    user_id: str = ""
    segment: str = ""  # judge the search belongs to (defaults to the user's segment)


@dataclass
class Judgment:
    grade: int
    reason: str = ""
