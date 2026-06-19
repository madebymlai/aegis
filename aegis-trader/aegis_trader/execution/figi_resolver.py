"""Futures-only InstrumentRef → Nautilus InstrumentId resolver shell.

ListedRef resolution is no longer implemented here: live/paper loads listed
instruments by FIGI through IB's InstrumentProvider, and backtests inject their
local InstrumentSpec bimap directly.  This shell remains only for the futures
slice until futures are also resolved vendor-natively at IBKR and the resolver
husk can be deleted.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

from aegis_runtime import FuturesRef, InstrumentRef, ListedRef
from nautilus_trader.model.identifiers import InstrumentId


class FigiResolutionError(ValueError):
    """An InstrumentRef could not be resolved to a Nautilus InstrumentId."""


@dataclass(frozen=True)
class FuturesContract:
    """Dated futures contract selected by the roll calendar."""

    symbol: str
    exchange: str


FuturesCalendar = Callable[[FuturesRef, date], FuturesContract]
FuturesContractResolver = Callable[[FuturesContract], InstrumentId]


class FigiInstrumentResolver:
    """Temporary futures-only resolver.

    ListedRefs are resolved outside this class by IB's InstrumentProvider.  A
    FuturesRef still uses injected adapters in this slice; the next futures slice
    replaces those adapters with IBKR-native contract qualification.
    """

    def __init__(
        self,
        *,
        futures_calendar: FuturesCalendar | None = None,
        futures_contract_resolver: FuturesContractResolver | None = None,
    ) -> None:
        self._futures_calendar = futures_calendar
        self._futures_contract_resolver = futures_contract_resolver
        self._contract_to_ref: dict[InstrumentId, InstrumentRef] = {}

    def resolve(
        self,
        ref: InstrumentRef,
        as_of: date | None = None,
    ) -> InstrumentId:
        """Resolve a FuturesRef as-of a date.

        ListedRef resolution is handled by the IB InstrumentProvider boot bimap,
        not by this resolver.
        """
        if isinstance(ref, ListedRef):
            raise FigiResolutionError(
                "ListedRef resolution is handled by the IB InstrumentProvider"
            )
        if not isinstance(ref, FuturesRef):
            raise FigiResolutionError(f"unsupported InstrumentRef variant {type(ref).__name__}")
        if as_of is None:
            raise FigiResolutionError("as_of is required to resolve a FuturesRef")
        return self._resolve_future(ref, as_of)

    def resolve_many(self, refs: set[InstrumentRef]) -> dict[InstrumentRef, InstrumentId]:
        if not refs:
            return {}
        raise FigiResolutionError(
            "batch ListedRef resolution is handled by the IB InstrumentProvider"
        )

    def ref_for(self, instrument_id: InstrumentId) -> InstrumentRef:
        """Fold a resolved dated contract back to its canonical InstrumentRef."""
        try:
            return self._contract_to_ref[instrument_id]
        except KeyError:
            raise FigiResolutionError(
                f"InstrumentId {instrument_id!r} has no resolved InstrumentRef inverse"
            ) from None

    def _resolve_future(self, ref: FuturesRef, as_of: date) -> InstrumentId:
        if self._futures_calendar is None or self._futures_contract_resolver is None:
            raise FigiResolutionError("FuturesRef resolution requires injected futures adapters")
        contract = self._futures_calendar(ref, as_of)
        instrument_id = self._futures_contract_resolver(contract)
        self._contract_to_ref[instrument_id] = ref
        return instrument_id
