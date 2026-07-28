"""Distribution verification owned by the catalog data port."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

import pandas as pd
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.instruments import CurrencyPair, FuturesContract

from aegis_data._coverage_markers import CoverageMarkerLedger
from aegis_data._ensure_coverage import CoverageInterval, ServedRecords, ensure_coverage
from aegis_data.bar_type import raw_bar_type
from aegis_data.catalog import (
    CatalogCoverageGapError,
    DistributionDataProviderPort,
    catalog_definitions,
    continuous_instrument_legs,
    gap_fill_boundary,
)
from aegis_data.distributions import (
    Distribution,
    query_distribution_data,
    replace_distribution_data,
    request_distribution_data,
)
from aegis_data.ohlcv import bars_to_ohlcv

_NANOS_PER_DAY = 86_400_000_000_000


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
    interval: CoverageInterval


def ensure_distribution_window(
    catalog: Any,
    instrument_ids: Sequence[InstrumentId],
    *,
    start: str | int | pd.Timestamp,
    end: str | int | pd.Timestamp,
    provider: DistributionDataProviderPort | None,
    clock_ns: Callable[[], int],
    mark_bars: Callable[[InstrumentId, str], tuple[BarType, ...]],
    ensure_bar_coverage: Callable[[BarType, int, int], None],
) -> None:
    """Ensure Distribution coverage for one catalog window."""
    assessments = _assessments(
        catalog,
        instrument_ids,
        CoverageInterval(_timestamp_ns(start), _timestamp_ns(end)),
        mark_bars=mark_bars,
    )
    markers = CoverageMarkerLedger(catalog)
    missing_by_assessment = tuple(
        (
            assessment,
            markers.missing(
                Distribution,
                assessment.instrument_id,
                assessment.interval,
            ),
        )
        for assessment in assessments
    )
    failures = [
        _provider_missing_message(assessment.instrument_id, missing)
        for assessment, missing in missing_by_assessment
        if missing and assessment.applicability.applicable and provider is None
    ]
    if failures:
        raise CatalogCoverageGapError(
            "distribution coverage is missing for " + "; ".join(sorted(failures))
        )
    for assessment, _missing in missing_by_assessment:
        _ensure_assessment(
            catalog,
            assessment,
            provider=provider,
            clock_ns=clock_ns,
            ensure_bar_coverage=ensure_bar_coverage,
        )


def read_distribution_window(
    catalog: Any,
    instrument_ids: Sequence[InstrumentId],
    *,
    start: str | int | pd.Timestamp,
    end: str | int | pd.Timestamp,
    mark_bars: Callable[[InstrumentId, str], tuple[BarType, ...]],
) -> VerifiedDistributions:
    """Read Distribution records and coverage after the ensure command."""
    return _read_assessments(
        catalog,
        _assessments(
            catalog,
            instrument_ids,
            CoverageInterval(_timestamp_ns(start), _timestamp_ns(end)),
            mark_bars=mark_bars,
        ),
    )


def distribution_coverage_report(
    catalog: Any,
    instrument_ids: Sequence[InstrumentId],
    *,
    start: str | int | pd.Timestamp | None,
    end: str | int | pd.Timestamp | None,
    mark_bars: Callable[[InstrumentId, str], tuple[BarType, ...]],
) -> tuple[dict[str, Any], ...]:
    """Report Distribution coverage without fetching or mutating."""
    if start is None or end is None:
        return ()
    assessments = _assessments(
        catalog,
        instrument_ids,
        CoverageInterval(_timestamp_ns(start), _timestamp_ns(end)),
        mark_bars=mark_bars,
    )
    return tuple(_coverage_row(catalog, assessment) for assessment in assessments)


def force_reverify_distribution_window(
    catalog: Any,
    instrument_ids: Sequence[InstrumentId],
    *,
    start: str | int | pd.Timestamp,
    end: str | int | pd.Timestamp,
    provider: DistributionDataProviderPort | None,
    clock_ns: Callable[[], int],
    mark_bars: Callable[[InstrumentId, str], tuple[BarType, ...]],
    ensure_bar_coverage: Callable[[BarType, int, int], None],
) -> None:
    """Replace and freshly verify one bounded Distribution window."""
    if provider is None:
        raise CatalogCoverageGapError(
            "distribution force-reverify requires an adjusted-last provider"
        )
    requested = CoverageInterval(_timestamp_ns(start), _timestamp_ns(end))
    markers = CoverageMarkerLedger(catalog)
    for instrument_id in _dedupe(instrument_ids):
        markers.delete(Distribution, instrument_id, requested)
        assessment = _assessment(
            catalog,
            instrument_id,
            requested,
            mark_bars=mark_bars,
            clamp=False,
        )
        _ensure_assessment(
            catalog,
            assessment,
            provider=provider,
            clock_ns=clock_ns,
            ensure_bar_coverage=ensure_bar_coverage,
        )


def _ensure_assessment(
    catalog: Any,
    assessment: _Assessment,
    *,
    provider: DistributionDataProviderPort | None,
    clock_ns: Callable[[], int],
    ensure_bar_coverage: Callable[[BarType, int, int], None],
) -> None:
    markers = CoverageMarkerLedger(catalog)
    if not markers.missing(
        Distribution,
        assessment.instrument_id,
        assessment.interval,
    ):
        return
    checked_at_ns = clock_ns()

    def commit(
        interval: CoverageInterval,
        records: tuple[Distribution, ...],
    ) -> None:
        if assessment.applicability.applicable:
            replace_distribution_data(
                catalog,
                assessment.instrument_id,
                records,
                start=interval.start_ns,
                end=interval.end_ns,
            )
        markers.mark(
            Distribution,
            assessment.instrument_id,
            interval,
            checked_at_ns=checked_at_ns,
            applicable=assessment.applicability.applicable,
        )

    fetchers: tuple[
        Callable[[pd.Timestamp, pd.Timestamp], ServedRecords[Distribution]], ...
    ] = (_empty_fetcher,)
    if assessment.applicability.applicable:
        if provider is None:
            raise CatalogCoverageGapError(
                "distribution coverage is missing for "
                + _provider_missing_message(
                    assessment.instrument_id,
                    markers.missing(
                        Distribution,
                        assessment.instrument_id,
                        assessment.interval,
                    ),
                )
            )
        fetchers = (
            _distribution_fetcher(
                catalog,
                provider,
                assessment.instrument_id,
                assessment.applicability.definition,
                ensure_bar_coverage=ensure_bar_coverage,
            ),
        )

    ensure_coverage(
        subject=f"distributions for {assessment.instrument_id.value}",
        fetchers=fetchers,
        missing_intervals=lambda: markers.missing(
            Distribution,
            assessment.instrument_id,
            assessment.interval,
        ),
        commit=commit,
        finalize=lambda: markers.consolidate(
            Distribution,
            assessment.instrument_id,
            assessment.interval,
        ),
        coverage_error=lambda missing: CatalogCoverageGapError(
            "distribution coverage is missing for "
            + _provider_missing_message(assessment.instrument_id, missing)
        ),
        provider_boundary=gap_fill_boundary,
    )


def _distribution_fetcher(
    catalog: Any,
    provider: DistributionDataProviderPort,
    instrument_id: InstrumentId,
    definition: Any,
    *,
    ensure_bar_coverage: Callable[[BarType, int, int], None],
) -> Callable[[pd.Timestamp, pd.Timestamp], ServedRecords[Distribution]]:
    def fetch(start: pd.Timestamp, end: pd.Timestamp) -> ServedRecords[Distribution]:
        interval = CoverageInterval(start.value, end.value)
        records = _verify_interval(
            catalog,
            provider,
            instrument_id,
            definition,
            interval,
            ensure_bar_coverage=ensure_bar_coverage,
        )
        return ServedRecords(records, start)

    return fetch


def _empty_fetcher(
    start: pd.Timestamp,
    _end: pd.Timestamp,
) -> ServedRecords[Distribution]:
    return ServedRecords((), start)


def _verify_interval(
    catalog: Any,
    provider: DistributionDataProviderPort,
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


def _assessments(
    catalog: Any,
    instrument_ids: Sequence[InstrumentId],
    interval: CoverageInterval,
    *,
    mark_bars: Callable[[InstrumentId, str], tuple[BarType, ...]],
) -> tuple[_Assessment, ...]:
    return tuple(
        _assessment(
            catalog,
            instrument_id,
            interval,
            mark_bars=mark_bars,
        )
        for instrument_id in _dedupe(instrument_ids)
    )


def _assessment(
    catalog: Any,
    instrument_id: InstrumentId,
    interval: CoverageInterval,
    *,
    mark_bars: Callable[[InstrumentId, str], tuple[BarType, ...]],
    clamp: bool = True,
) -> _Assessment:
    applicability = _applicability(catalog, instrument_id)
    coverage_end = interval.end_ns
    if clamp and applicability.applicable:
        coverage_end = _coverage_end(
            catalog,
            mark_bars,
            instrument_id,
            interval,
        )
    return _Assessment(
        instrument_id,
        applicability,
        CoverageInterval(interval.start_ns, coverage_end),
    )


def _applicability(catalog: Any, instrument_id: InstrumentId) -> _Applicability:
    definition = catalog_definitions(catalog, [instrument_id]).get(instrument_id)
    if definition is not None:
        if isinstance(definition, (FuturesContract, CurrencyPair)):
            return _Applicability(False)
        return _Applicability(True, definition)
    if continuous_instrument_legs(catalog, instrument_id):
        return _Applicability(False)
    raise CatalogCoverageGapError(
        "distribution coverage cannot resolve catalog definitions for "
        f"{instrument_id.value}"
    )


def _coverage_end(
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
    return min(interval.end_ns, max(bar.ts_event for bar in bars) + _NANOS_PER_DAY)


def _read_assessments(
    catalog: Any,
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
        coverage.append(
            _coverage_row(catalog, assessment, event_count=len(selected))
        )
    return VerifiedDistributions(
        records=tuple(records),
        coverage=tuple(coverage),
    )


def _coverage_row(
    catalog: Any,
    assessment: _Assessment,
    *,
    event_count: int | None = None,
) -> dict[str, Any]:
    checked = CoverageMarkerLedger(catalog).checked_at_values(
        Distribution,
        assessment.instrument_id,
        assessment.interval,
    )
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
    return {
        "instrument_id": assessment.instrument_id.value,
        "applicable": assessment.applicability.applicable,
        "verified_start": _timestamp_text(assessment.interval.start_ns),
        "verified_end": _timestamp_text(assessment.interval.end_ns),
        "event_count": event_count,
        "checked_at": _timestamp_text(min(checked)) if checked else None,
    }


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


def _provider_missing_message(
    instrument_id: InstrumentId,
    missing: Sequence[CoverageInterval],
) -> str:
    ranges = [_range_text(interval.start_ns, interval.end_ns) for interval in missing]
    return f"{instrument_id.value} missing={ranges}"


def _range_text(start_ns: int, end_ns: int) -> str:
    return (
        f"{pd.Timestamp(start_ns, tz='UTC').isoformat()}.."
        f"{pd.Timestamp(end_ns, tz='UTC').isoformat()}"
    )


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
    "force_reverify_distribution_window",
    "read_distribution_window",
]
