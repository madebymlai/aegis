from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Generic, TypeVar

import pandas as pd


RecordT = TypeVar("RecordT", covariant=True)


@dataclass(frozen=True)
class ProviderAnswer(Generic[RecordT]):
    """One provider response for a requested record window.

    ``oldest_verified`` is the provider's sole coverage signal. A verified
    answer may contain no records and still proves checked emptiness from that
    frontier onward.
    """

    records: tuple[RecordT, ...]
    oldest_verified: pd.Timestamp

    @classmethod
    def verified(
        cls,
        records: Sequence[RecordT],
        *,
        oldest_verified: pd.Timestamp,
    ) -> ProviderAnswer[RecordT]:
        return cls(tuple(records), oldest_verified)


__all__ = ["ProviderAnswer"]
