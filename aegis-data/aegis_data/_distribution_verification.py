"""Distribution verification owned by the catalog data port."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

import pandas as pd
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.instruments import CurrencyPair, Equity, FuturesContract

from aegis_data._coverage_markers import CoverageMarkerLedger
from aegis_data._ensure_coverage import (
    CatalogCoverageGapError,
    CoverageInterval,
    ensure_coverage,
)
from aegis_data.definitions import (
    catalog_definitions,
    continuous_instrument_legs,
)
from aegis_data.raw_bars import RawBars
from aegis_data.distributions import (
    Distribution,
    query_distribution_data,
    replace_distribution_data,
    request_distribution_data,
)
from aegis_data.marking import MarkMode, marking_for_mode
from aegis_data.storage import Catalog, CatalogInterval, CatalogKey
from aegis_data.provider import ProviderAnswer

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
    catalog: Catalog,
    instrument_ids: Sequence[InstrumentId],
    *,
    start: str | int | pd.Timestamp,
    end: str | int | pd.Timestamp,
    provider: DistributionDataProviderPort | None,
    clock_ns: Callable[[], int],
    raw_bars: RawBars,
) -> None:
    """Ensure Distribution coverage for one catalog window."""
    assessments = _assessments(
        catalog,
        instrument_ids,
        CoverageInterval(_timestamp_ns(start), _timestamp_ns(end)),
        raw_bars=raw_bars,
    )
    markers = CoverageMarkerLedger(catalog)
    missing_by_assessment = tuple(
        (
            assessment,
            markers.missing(
                CatalogKey.for_instrument(
                    Distribution, assessment.instrument_id
                ),
                assessment.interval,
            ),
        )
        for assessment in assessments
    )
    failures = [
        (assessment, missing)
        for assessment, missing in missing_by_assessment
        if missing and assessment.applicability.applicable and provider is None
    ]
    if failures:
        assessment, _ = failures[0]
        raise _coverage_gap(
            assessment.instrument_id,
            tuple(interval for _, missing in failures for interval in missing),
            message=(
                "distribution coverage is missing for "
                + "; ".join(
                    sorted(
                        _provider_missing_message(item.instrument_id, missing)
                        for item, missing in failures
                    )
                )
            ),
        )
    for assessment, _missing in missing_by_assessment:
        _ensure_assessment(
            catalog,
            assessment,
            provider=provider,
            clock_ns=clock_ns,
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
            CoverageInterval(_timestamp_ns(start), _timestamp_ns(end)),
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
        CoverageInterval(_timestamp_ns(start), _timestamp_ns(end)),
        raw_bars=raw_bars,
    )
    return tuple(_coverage_row(catalog, assessment) for assessment in assessments)


def _ensure_assessment(
    catalog: Catalog,
    assessment: _Assessment,
    *,
    provider: DistributionDataProviderPort | None,
    clock_ns: Callable[[], int],
    raw_bars: RawBars,
) -> None:
    markers = CoverageMarkerLedger(catalog)
    subject = CatalogKey.for_instrument(Distribution, assessment.instrument_id)

    if not assessment.applicability.applicable:
        _mark_not_applicable(
            markers,
            subject,
            assessment.interval,
            clock_ns=clock_ns,
        )
        return

    checked_at_ns = clock_ns()

    def commit(
        interval: CoverageInterval,
        records: tuple[Distribution, ...],
    ) -> None:
        replace_distribution_data(
            catalog,
            assessment.instrument_id,
            records,
            start=interval.start_ns,
            end=interval.end_ns,
        )
        markers.mark(
            subject,
            interval,
            checked_at_ns=checked_at_ns,
            applicable=True,
        )

    ensure_coverage(
        subject=f"distributions for {assessment.instrument_id.value}",
        provider=(
            _distribution_fetcher(
                catalog,
                provider,
                assessment.instrument_id,
                assessment.applicability.definition,
                raw_bars=raw_bars,
            )
            if provider is not None
            else None
        ),
        missing_intervals=lambda: markers.missing(subject, assessment.interval),
        commit=commit,
        coverage_error=lambda missing: _coverage_gap(
            assessment.instrument_id,
            missing,
            message=(
                "distribution coverage is missing for "
                + _provider_missing_message(assessment.instrument_id, missing)
            ),
        ),
        on_filled=lambda: markers.consolidate(subject, assessment.interval),
    )


def _mark_not_applicable(
    markers: CoverageMarkerLedger,
    subject: CatalogKey[Distribution],
    window: CoverageInterval,
    *,
    clock_ns: Callable[[], int],
) -> None:
    """Record that a window was checked for an instrument that pays none.

    Nothing streams or fetches distributions here, so there is no window to
    fill — only the fact that it was checked, which needs neither a provider
    nor a fill loop. Exactly the missing intervals are marked: a claim over
    part of the same window predates this answer and must survive it. A window
    already covered is left untouched, so reading it twice stays a pure read.
    """
    missing = markers.missing(subject, window)
    if not missing:
        return
    checked_at_ns = clock_ns()
    for interval in missing:
        markers.mark(
            subject,
            interval,
            checked_at_ns=checked_at_ns,
            applicable=False,
        )
    markers.consolidate(subject, window)


def _distribution_fetcher(
    catalog: Catalog,
    provider: DistributionDataProviderPort,
    instrument_id: InstrumentId,
    definition: Any,
    *,
    raw_bars: RawBars,
) -> Callable[[pd.Timestamp, pd.Timestamp], ProviderAnswer[Distribution]]:
    def fetch(start: pd.Timestamp, end: pd.Timestamp) -> ProviderAnswer[Distribution]:
        interval = CoverageInterval(start.value, end.value)
        records = _verify_interval(
            catalog,
            provider,
            instrument_id,
            definition,
            interval,
            raw_bars=raw_bars,
        )
        return ProviderAnswer.verified(records, oldest_verified=start)

    return fetch


def _verify_interval(
    catalog: Catalog,
    provider: DistributionDataProviderPort,
    instrument_id: InstrumentId,
    definition: Any,
    interval: CoverageInterval,
    *,
    raw_bars: RawBars,
) -> tuple[Distribution, ...]:
    decode_start_ns = pd.Timestamp(interval.start_ns, tz="UTC").normalize().value
    trade_marking = marking_for_mode(instrument_id, "1D", MarkMode.LAST)
    bar_interval = CatalogInterval(decode_start_ns, interval.end_ns)
    try:
        raw_bars.ensure(trade_marking, bar_interval)
    except CatalogCoverageGapError as exc:
        raise _coverage_gap(
            instrument_id,
            (interval,),
            message=(
                f"distribution verification needs {instrument_id.value}'s raw "
                f"daily closes; seed {trade_marking.mark_bars[0]} or gap-fill it "
                f"with a provider-backed load ({exc})"
            ),
        ) from exc
    trades = raw_bars.covered(trade_marking, bar_interval).ohlcv["Close"]
    if len(trades) < 2:
        raise _coverage_gap(
            instrument_id,
            (interval,),
            message=(
                "distribution coverage cannot verify "
                f"{instrument_id.value}: fewer than two TRADES closes in "
                f"{_range_text(interval.start_ns, interval.end_ns)}"
            ),
        )
    return request_distribution_data(
        provider,
        instrument_id,
        trades=trades,
        start=pd.Timestamp(decode_start_ns, tz="UTC"),
        end=pd.Timestamp(interval.end_ns, tz="UTC"),
        currency=_definition_currency(definition, instrument_id, interval),
    )


def _assessments(
    catalog: Catalog,
    instrument_ids: Sequence[InstrumentId],
    interval: CoverageInterval,
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
    interval: CoverageInterval,
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
        CoverageInterval(interval.start_ns, coverage_end),
    )


def _applicability(
    catalog: Catalog,
    instrument_id: InstrumentId,
    interval: CoverageInterval,
) -> _Applicability:
    definition = catalog_definitions(catalog, [instrument_id]).get(instrument_id)
    if definition is not None:
        if isinstance(definition, (FuturesContract, CurrencyPair)):
            return _Applicability(False)
        if isinstance(definition, Equity):
            return _Applicability(True, definition)
        raise _coverage_gap(
            instrument_id,
            (interval,),
            message=(
                "distribution coverage does not classify instrument type "
                f"{type(definition).__name__} for {instrument_id.value}"
            ),
        )
    if continuous_instrument_legs(catalog, instrument_id):
        return _Applicability(False)
    raise _coverage_gap(
        instrument_id,
        (interval,),
        message=(
            "distribution coverage cannot resolve catalog definitions for "
            f"{instrument_id.value}"
        ),
    )


def _coverage_end(
    catalog: Catalog,
    raw_bars: RawBars,
    instrument_id: InstrumentId,
    interval: CoverageInterval,
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
        coverage.append(
            _coverage_row(catalog, assessment, event_count=len(selected))
        )
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
    checked = CoverageMarkerLedger(catalog).checked_at_values(
        CatalogKey.for_instrument(Distribution, assessment.instrument_id),
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


def _definition_currency(
    definition: Any,
    instrument_id: InstrumentId,
    interval: CoverageInterval,
) -> str:
    currency = getattr(definition, "currency", None)
    if currency is None:
        currency = getattr(definition, "quote_currency", None)
    if currency is None:
        raise _coverage_gap(
            instrument_id,
            (interval,),
            message=(
                f"distribution coverage needs a currency on {instrument_id.value}"
            ),
        )
    return str(currency).upper()


def _provider_missing_message(
    instrument_id: InstrumentId,
    missing: Sequence[CoverageInterval],
) -> str:
    ranges = [_range_text(interval.start_ns, interval.end_ns) for interval in missing]
    return f"{instrument_id.value} missing={ranges}"


def _coverage_gap(
    instrument_id: InstrumentId,
    missing: Sequence[CoverageInterval],
    *,
    message: str,
) -> CatalogCoverageGapError:
    return CatalogCoverageGapError(
        CatalogKey.for_instrument(Distribution, instrument_id),
        missing,
        message=message,
    )


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
    "DistributionDataProviderPort",
    "distribution_coverage_report",
    "ensure_distribution_window",
    "read_distribution_window",
]
