"""Distribution verification owned by the catalog data port."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import pandas as pd
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.instruments import CurrencyPair, Equity, FuturesContract

from aegis_data.definitions import (
    catalog_definitions,
    continuous_instrument_legs,
)
from aegis_data.custom_data import (
    CustomDataWarmer,
    provider_backed_custom_data_client_factory,
)
from aegis_data.raw_bars import RawBars
from aegis_data.distributions import (
    AdjustedClose,
    AdjustedCloseRequestMetadata,
    Distribution,
    adjusted_close_series,
    query_distribution_data,
    recover_distributions_from_adjusted_last,
)
from aegis_data.marking import MarkMode, marking_for_mode
from aegis_data.storage import Catalog, CatalogInterval, CatalogKey

_NANOS_PER_DAY = 86_400_000_000_000


class UnknownDistributionInstrumentTypeError(ValueError):
    """A definition has no Distribution applicability rule."""


class MissingDistributionDefinitionError(ValueError):
    """Distribution applicability cannot resolve an instrument definition."""


class MissingDistributionCurrencyError(ValueError):
    """A Distribution-bearing definition has no currency."""


@dataclass(frozen=True)
class VerifiedDistributions:
    """Distribution records and coverage rows from one coherent verification."""

    records: tuple[Distribution, ...]
    coverage: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class _Applicability:
    applicable: bool
    definition: Any | None = None


@dataclass(frozen=True)
class _Assessment:
    instrument_id: InstrumentId
    applicability: _Applicability
    interval: CatalogInterval


@dataclass(frozen=True)
class _DerivedDistributionProvider:
    catalog: Catalog
    adjusted_close_warmer: CustomDataWarmer
    definition: Any
    raw_bars: RawBars

    def request_records(
        self,
        instrument_id: InstrumentId,
        *,
        start: pd.Timestamp,
        end: pd.Timestamp,
    ) -> tuple[Distribution, ...]:
        interval = CatalogInterval(start.value, end.value)
        decode_start_ns = pd.Timestamp(interval.start_ns, tz="UTC").normalize().value
        trade_marking = marking_for_mode(instrument_id, "1D", MarkMode.LAST)
        bar_interval = CatalogInterval(decode_start_ns, interval.end_ns)
        self.raw_bars.ensure(trade_marking, bar_interval)
        trades = self.raw_bars.stored(trade_marking, bar_interval).ohlcv["Close"]
        if len(trades) < 2:
            return ()
        currency = _definition_currency(self.definition, instrument_id, interval)
        adjusted_last = _stored_adjusted_last(
            self.catalog,
            self.adjusted_close_warmer,
            instrument_id,
            bar_interval,
            currency=currency,
        )
        return tuple(
            record
            for record in recover_distributions_from_adjusted_last(
                instrument_id=instrument_id,
                trades=trades,
                adjusted_last=adjusted_last,
                currency=currency,
            )
            if interval.start_ns <= record.ts_event <= interval.end_ns
        )


def ensure_distribution_window(
    catalog: Catalog,
    instrument_ids: Sequence[InstrumentId],
    *,
    start: str | int | pd.Timestamp,
    end: str | int | pd.Timestamp,
    custom_data_warmer: CustomDataWarmer | None,
    raw_bars: RawBars,
) -> None:
    """Ensure Distribution coverage for one catalog window."""
    assessments = _assessments(
        catalog,
        instrument_ids,
        CatalogInterval(_timestamp_ns(start), _timestamp_ns(end)),
        raw_bars=raw_bars,
    )
    for assessment in assessments:
        _ensure_assessment(
            catalog,
            assessment,
            custom_data_warmer=custom_data_warmer,
            raw_bars=raw_bars,
        )


def read_distribution_window(
    catalog: Catalog,
    instrument_ids: Sequence[InstrumentId],
    *,
    start: str | int | pd.Timestamp,
    end: str | int | pd.Timestamp,
    raw_bars: RawBars,
) -> VerifiedDistributions:
    """Read Distribution records and coverage after the ensure command."""
    return _read_assessments(
        catalog,
        _assessments(
            catalog,
            instrument_ids,
            CatalogInterval(_timestamp_ns(start), _timestamp_ns(end)),
            raw_bars=raw_bars,
        ),
    )


def distribution_coverage_report(
    catalog: Catalog,
    instrument_ids: Sequence[InstrumentId],
    *,
    start: str | int | pd.Timestamp | None,
    end: str | int | pd.Timestamp | None,
    raw_bars: RawBars,
) -> tuple[dict[str, Any], ...]:
    """Report Distribution coverage without fetching or mutating."""
    if start is None or end is None:
        return ()
    assessments = _assessments(
        catalog,
        instrument_ids,
        CatalogInterval(_timestamp_ns(start), _timestamp_ns(end)),
        raw_bars=raw_bars,
    )
    return tuple(_coverage_row(catalog, assessment) for assessment in assessments)


def _ensure_assessment(
    catalog: Catalog,
    assessment: _Assessment,
    *,
    custom_data_warmer: CustomDataWarmer | None,
    raw_bars: RawBars,
) -> None:
    if not assessment.applicability.applicable or custom_data_warmer is None:
        return
    provider = _DerivedDistributionProvider(
        catalog,
        custom_data_warmer,
        assessment.applicability.definition,
        raw_bars,
    )
    warmer = CustomDataWarmer(
        catalog,
        provider_backed_custom_data_client_factory({Distribution: provider}),
    )
    warmer.warm(
        Distribution,
        (assessment.instrument_id,),
        start=assessment.interval.start,
        end=assessment.interval.end,
    )


def _stored_adjusted_last(
    catalog: Catalog,
    custom_data_warmer: CustomDataWarmer,
    instrument_id: InstrumentId,
    interval: CatalogInterval,
    *,
    currency: str,
) -> pd.Series:
    """Warm adjusted closes through Nautilus, then read them from the Catalog."""
    subject = CatalogKey.for_instrument(AdjustedClose, instrument_id)
    custom_data_warmer.warm(
        AdjustedClose,
        (instrument_id,),
        start=interval.start,
        end=interval.end,
        metadata=AdjustedCloseRequestMetadata(currency),
    )
    return adjusted_close_series(catalog.read(subject, interval))


def _assessments(
    catalog: Catalog,
    instrument_ids: Sequence[InstrumentId],
    interval: CatalogInterval,
    *,
    raw_bars: RawBars,
) -> tuple[_Assessment, ...]:
    return tuple(
        _assessment(
            catalog,
            instrument_id,
            interval,
            raw_bars=raw_bars,
        )
        for instrument_id in _dedupe(instrument_ids)
    )


def _assessment(
    catalog: Catalog,
    instrument_id: InstrumentId,
    interval: CatalogInterval,
    *,
    raw_bars: RawBars,
    clamp: bool = True,
) -> _Assessment:
    applicability = _applicability(catalog, instrument_id, interval)
    coverage_end = interval.end_ns
    if clamp and applicability.applicable:
        coverage_end = _coverage_end(
            catalog,
            raw_bars,
            instrument_id,
            interval,
        )
    return _Assessment(
        instrument_id,
        applicability,
        CatalogInterval(interval.start_ns, coverage_end),
    )


def _applicability(
    catalog: Catalog,
    instrument_id: InstrumentId,
    interval: CatalogInterval,
) -> _Applicability:
    definition = catalog_definitions(catalog, [instrument_id]).get(instrument_id)
    if definition is not None:
        if isinstance(definition, (FuturesContract, CurrencyPair)):
            return _Applicability(False)
        if isinstance(definition, Equity):
            return _Applicability(True, definition)
        raise UnknownDistributionInstrumentTypeError(
            "distribution coverage does not classify instrument type "
            f"{type(definition).__name__} for {instrument_id.value}"
        )
    if continuous_instrument_legs(catalog, instrument_id):
        return _Applicability(False)
    raise MissingDistributionDefinitionError(
        "distribution coverage cannot resolve catalog definitions for "
        f"{instrument_id.value}"
    )


def _coverage_end(
    catalog: Catalog,
    raw_bars: RawBars,
    instrument_id: InstrumentId,
    interval: CatalogInterval,
) -> int:
    marking = raw_bars.marking(instrument_id, "1D")
    bars = raw_bars.stored(
        marking,
        CatalogInterval(interval.start_ns, interval.end_ns),
    ).bars
    if not bars:
        return interval.end_ns
    return min(interval.end_ns, max(bar.ts_event for bar in bars) + _NANOS_PER_DAY)


def _read_assessments(
    catalog: Catalog,
    assessments: Sequence[_Assessment],
) -> VerifiedDistributions:
    records: list[Distribution] = []
    coverage: list[dict[str, Any]] = []
    for assessment in assessments:
        selected: tuple[Distribution, ...] = ()
        if assessment.applicability.applicable:
            selected = query_distribution_data(
                catalog,
                (assessment.instrument_id,),
                start=assessment.interval.start_ns,
                end=assessment.interval.end_ns,
            )
            records.extend(selected)
        coverage.append(_coverage_row(catalog, assessment, event_count=len(selected)))
    return VerifiedDistributions(
        records=tuple(records),
        coverage=tuple(coverage),
    )


def _coverage_row(
    catalog: Catalog,
    assessment: _Assessment,
    *,
    event_count: int | None = None,
) -> dict[str, Any]:
    if event_count is None and assessment.applicability.applicable:
        event_count = len(
            query_distribution_data(
                catalog,
                (assessment.instrument_id,),
                start=assessment.interval.start_ns,
                end=assessment.interval.end_ns,
            )
        )
    if event_count is None:
        event_count = 0
    subject = CatalogKey.for_instrument(Distribution, assessment.instrument_id)
    fully_stored = assessment.applicability.applicable and not catalog.missing(
        subject, assessment.interval
    )
    return {
        "instrument_id": assessment.instrument_id.value,
        "applicable": assessment.applicability.applicable,
        "verified_start": (
            _timestamp_text(assessment.interval.start_ns) if fully_stored else None
        ),
        "verified_end": (
            _timestamp_text(assessment.interval.end_ns) if fully_stored else None
        ),
        "event_count": event_count,
    }


def _definition_currency(
    definition: Any,
    instrument_id: InstrumentId,
    interval: CatalogInterval,
) -> str:
    currency = getattr(definition, "currency", None)
    if currency is None:
        currency = getattr(definition, "quote_currency", None)
    if currency is None:
        raise MissingDistributionCurrencyError(
            f"distribution coverage needs a currency on {instrument_id.value}"
        )
    return str(currency).upper()


def _timestamp_ns(value: str | int | pd.Timestamp) -> int:
    if isinstance(value, int):
        return value
    timestamp = pd.Timestamp(value)
    if timestamp.tz is None:
        timestamp = timestamp.tz_localize("UTC")
    else:
        timestamp = timestamp.tz_convert("UTC")
    return timestamp.value


def _timestamp_text(value: int) -> str:
    return pd.Timestamp(value, tz="UTC").isoformat()


def _dedupe(instrument_ids: Sequence[InstrumentId]) -> tuple[InstrumentId, ...]:
    return tuple(dict.fromkeys(instrument_ids))


__all__ = [
    "VerifiedDistributions",
    "distribution_coverage_report",
    "ensure_distribution_window",
    "read_distribution_window",
]
