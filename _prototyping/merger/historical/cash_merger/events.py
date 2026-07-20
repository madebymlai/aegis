"""Causal fixed-cash merger observations shared by historical adapters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

EventStatus = Literal["pending", "completed", "terminated"]


@dataclass(frozen=True)
class CashMergerEvent:
    """One fixed-cash deal fact at the instant it became public."""

    target_cik: str
    target_name: str
    target_symbol: str
    status: EventStatus
    available_at: str
    offer_price: float | None
    source_form: str
    source_url: str
    accession: str
