"""Distribution verification owned by the catalog data port."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

import pandas as pd
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.instruments import CurrencyPair, Equity, FuturesContract

from aegis_data.definitions import (
    catalog_definitions,
    continuous_instrument_legs,
)
from aegis_data.raw_bars import RawBars
from aegis_data.distributions import (
    AdjustedClose,
    Distribution,
    adjusted_close_records,
    adjusted_close_series,
    query_distribution_data,
    replace_distribution_data,
    recover_distributions_from_adjusted_last,
)
from aegis_data.marking import MarkMode, marking_for_mode
from aegis_data.storage import Catalog, CatalogInterval, CatalogKey
from aegis_data.provider_errors import gap_fill_boundary

_NANOS_PER_DAY = 86_400_000_000_000


class DistributionDataProviderPort(Protocol):
    """Fetch the adjusted-last series needed to verify distributions."""

    def request_adjusted_last(
        self,
        instrument_id: InstrumentId,
        *,
        start: pd.Timestamp,
        end: pd.Timestamp,
        currency: str = "USD",
    ) -> pd.Series: ...


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


def ensure_distribution_window(
    catalog: Catalog,
    instrument_ids: Sequence[InstrumentId],
    *,
    start: str | int | pd.Timestamp,
    end: str | int | pd.Timestamp,
    provider: DistributionDataProviderPort | None,
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
            provider=provider,
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
    provider: DistributionDataProviderPort | None,
    raw_bars: RawBars,
) -> None:
    subject = CatalogKey.for_instrument(Distribution, assessment.instrument_id)

    if not assessment.applicability.applicable:
        return

    def commit(
        interval: CatalogInterval,
        records: tuple[Distribution, ...],
    ) -> None:
        replace_distribution_data(
            catalog,
            assessment.instrument_id,
            records,
            start=interval.start_ns,
            end=interval.end_ns,
        )

    if provider is None:
        return
    fetch = _distribution_fetcher(
        catalog,
        provider,
        assessment.instrument_id,
        assessment.applicability.definition,
        raw_bars=raw_bars,
    )
    missing_intervals = catalog.missing(subject, assessment.interval)
    for missing in missing_intervals:
        with gap_fill_boundary(f"distributions for {assessment.instrument_id.value}"):
            records = fetch(missing.start, missing.end)
        commit(missing, tuple(records))
    if missing_intervals and not catalog.missing(subject, assessment.interval):
        catalog.compact(subject, assessment.interval)


def _distribution_fetcher(
    catalog: Catalog,
    provider: DistributionDataProviderPort,
    instrument_id: InstrumentId,
    definition: Any,
    *,
    raw_bars: RawBars,
) -> Callable[[pd.Timestamp, pd.Timestamp], Sequence[Distribution]]:
    def fetch(start: pd.Timestamp, end: pd.Timestamp) -> Sequence[Distribution]:
        interval = CatalogInterval(start.value, end.value)
        records = _verify_interval(
            catalog,
            provider,
            instrument_id,
            definition,
            interval,
            raw_bars=raw_bars,
        )
        return records

    return fetch


def _verify_interval(
    catalog: Catalog,
    provider: DistributionDataProviderPort,
    instrument_id: InstrumentId,
    definition: Any,
    interval: CatalogInterval,
    *,
    raw_bars: RawBars,
) -> tuple[Distribution, ...]:
    decode_start_ns = pd.Timestamp(interval.start_ns, tz="UTC").normalize().value
    trade_marking = marking_for_mode(instrument_id, "1D", MarkMode.LAST)
    bar_interval = CatalogInterval(decode_start_ns, interval.end_ns)
    raw_bars.ensure(trade_marking, bar_interval)
    trades = raw_bars.covered(trade_marking, bar_interval).ohlcv["Close"]
    if len(trades) < 2:
        return ()
    adjusted_last = _stored_adjusted_last(
        catalog,
        provider,
        instrument_id,
        CatalogInterval(decode_start_ns, interval.end_ns),
        currency=_definition_currency(definition, instrument_id, interval),
    )
    return tuple(
        recover_distributions_from_adjusted_last(
            instrument_id=instrument_id,
            trades=trades,
            adjusted_last=adjusted_last,
            currency=_definition_currency(definition, instrument_id, interval),
        )
    )


def _stored_adjusted_last(
    catalog: Catalog,
    provider: DistributionDataProviderPort,
    instrument_id: InstrumentId,
    interval: CatalogInterval,
    *,
    currency: str,
) -> pd.Series:
    """Read adjusted closes from the Catalog, fetching only missing windows."""
    subject = CatalogKey.for_instrument(AdjustedClose, instrument_id)

    def fetch(start: pd.Timestamp, end: pd.Timestamp) -> Sequence[AdjustedClose]:
        return adjusted_close_records(
            instrument_id,
            provider.request_adjusted_last(
                instrument_id=instrument_id,
                start=start,
                end=end,
                currency=currency,
            ),
        )

    missing_intervals = catalog.missing(subject, interval)
    for missing in missing_intervals:
        records = fetch(missing.start, missing.end)
        catalog.replace(subject, missing, tuple(records))
    if missing_intervals and not catalog.missing(subject, interval):
        catalog.compact(subject, interval)
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
    "DistributionDataProviderPort",
    "distribution_coverage_report",
    "ensure_distribution_window",
    "read_distribution_window",
]
