from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum, auto
from typing import Generic, TypeVar

import pandas as pd


RecordT = TypeVar("RecordT", covariant=True)


class _AnswerCase(Enum):
    VERIFIED = auto()
    NOT_RESPONSIBLE = auto()


@dataclass(frozen=True)
class ProviderAnswer(Generic[RecordT]):
    """One provider response for a requested record window.

    ``oldest_verified`` is the provider's sole coverage signal. A verified
    answer may contain no records and still proves checked emptiness from that
    frontier onward. A not-responsible answer proves nothing and therefore has
    neither records nor a frontier.
    """

    records: tuple[RecordT, ...]
    oldest_verified: pd.Timestamp | None
    _case: _AnswerCase = _AnswerCase.VERIFIED

    @classmethod
    def verified(
        cls,
        records: Sequence[RecordT],
        *,
        oldest_verified: pd.Timestamp,
    ) -> ProviderAnswer[RecordT]:
        return cls(tuple(records), oldest_verified, _AnswerCase.VERIFIED)

    @classmethod
    def not_responsible(cls) -> ProviderAnswer[RecordT]:
        return cls((), None, _AnswerCase.NOT_RESPONSIBLE)

    @property
    def is_responsible(self) -> bool:
        return self._case is _AnswerCase.VERIFIED


__all__ = ["ProviderAnswer"]
