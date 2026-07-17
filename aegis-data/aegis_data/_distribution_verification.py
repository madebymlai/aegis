"""Distribution-specific facts plugged into generic Custom Data verification."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, cast

import pandas as pd
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.instruments import CurrencyPair, FuturesContract

from aegis_data.bar_type import raw_bar_type
from aegis_data._ensure_coverage import CoverageInterval
from aegis_data.catalog import (
    CatalogCoverageGapError,
    DistributionDataProviderPort,
    catalog_definitions,
    continuous_instrument_legs,
)
from aegis_data.distributions import Distribution, request_distribution_data
from aegis_data.ohlcv import bars_to_ohlcv

_NANOS_PER_DAY = 86_400_000_000_000


@dataclass(frozen=True)
class DistributionApplicability:
    """Whether a Custom Data kind applies, plus its resolved definition."""

    applicable: bool
    definition: Any | None = None


class DistributionVerification:
    """The domain hook for adjusted-last Distribution verification.

    Coverage intervals, marker persistence, corrections, and reports belong to
    the generic Custom Data module.  This hook owns only Distribution facts.
    """

    subject = "distribution"

    def provider_for(
        self, providers: Sequence[object]
    ) -> DistributionDataProviderPort | None:
        return next(
            (
                cast(DistributionDataProviderPort, provider)
                for provider in providers
                if hasattr(provider, "request_adjusted_last")
            ),
            None,
        )

    def applicability(
        self, catalog: Any, instrument_id: InstrumentId
    ) -> DistributionApplicability:
        definition = catalog_definitions(catalog, [instrument_id]).get(instrument_id)
        if definition is not None:
            if isinstance(definition, (FuturesContract, CurrencyPair)):
                return DistributionApplicability(False)
            return DistributionApplicability(True, definition)
        if continuous_instrument_legs(catalog, instrument_id):
            return DistributionApplicability(False)
        raise CatalogCoverageGapError(
            "distribution coverage cannot resolve catalog definitions for "
            f"{instrument_id.value}"
        )

    def coverage_end(
        self,
        catalog: Any,
        mark_bars: Callable[[InstrumentId, str], tuple[BarType, ...]],
        instrument_id: InstrumentId,
        interval: CoverageInterval,
    ) -> int:
        bars = [
            bar
            for bar_type in mark_bars(instrument_id, "1D")
            for bar in _bars_for(catalog, bar_type, interval.start_ns, interval.end_ns)
        ]
        if not bars:
            return interval.end_ns
        return min(
            interval.end_ns,
            max(bar.ts_event for bar in bars) + _NANOS_PER_DAY,
        )

    def verify(
        self,
        catalog: Any,
        provider: object,
        instrument_id: InstrumentId,
        definition: Any,
        interval: CoverageInterval,
        *,
        ensure_bar_coverage: Callable[[BarType, int, int], None],
    ) -> tuple[Distribution, ...]:
        decode_start_ns = pd.Timestamp(interval.start_ns, tz="UTC").normalize().value
        trade_type = raw_bar_type(instrument_id, "1D")
        try:
            ensure_bar_coverage(trade_type, decode_start_ns, interval.end_ns)
        except CatalogCoverageGapError as exc:
            raise CatalogCoverageGapError(
                f"distribution verification needs {instrument_id.value}'s raw "
                f"daily closes; seed {trade_type} or gap-fill it with a "
                f"provider-backed load ({exc})"
            ) from exc
        trades = bars_to_ohlcv(
            _bars_for(catalog, trade_type, decode_start_ns, interval.end_ns)
        )["Close"]
        if len(trades) < 2:
            raise CatalogCoverageGapError(
                "distribution coverage cannot verify "
                f"{instrument_id.value}: fewer than two TRADES closes in "
                f"{_range_text(interval.start_ns, interval.end_ns)}"
            )
        return request_distribution_data(
            provider,
            instrument_id,
            trades=trades,
            start=pd.Timestamp(decode_start_ns, tz="UTC"),
            end=pd.Timestamp(interval.end_ns, tz="UTC"),
            currency=_definition_currency(definition, instrument_id),
        )

    def provider_missing_message(
        self, instrument_id: InstrumentId, missing: Sequence[CoverageInterval]
    ) -> str:
        ranges = [
            _range_text(interval.start_ns, interval.end_ns) for interval in missing
        ]
        return f"{instrument_id.value} missing={ranges}"

    def force_provider_message(self) -> str:
        return "distribution force-reverify requires an adjusted-last provider"


def _bars_for(catalog: Any, bar_type: BarType, start_ns: int, end_ns: int) -> list[Bar]:
    return list(
        catalog.query(
            Bar,
            identifiers=[str(bar_type)],
            start=start_ns,
            end=end_ns,
        )
    )


def _definition_currency(definition: Any, instrument_id: InstrumentId) -> str:
    currency = getattr(definition, "currency", None)
    if currency is None:
        currency = getattr(definition, "quote_currency", None)
    if currency is None:
        raise CatalogCoverageGapError(
            f"distribution coverage needs a currency on {instrument_id.value}"
        )
    return str(currency).upper()


def _range_text(start_ns: int, end_ns: int) -> str:
    return (
        f"{pd.Timestamp(start_ns, tz='UTC').isoformat()}.."
        f"{pd.Timestamp(end_ns, tz='UTC').isoformat()}"
    )
