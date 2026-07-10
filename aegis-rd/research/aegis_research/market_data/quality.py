"""Judge: a pure verdict over typed diagnostics.

``evaluate`` reads only the :class:`DataDiagnostics` records, the
observation-level index evidence, and the config's quality policy — never the
raw native data — and returns a :class:`MarketDataQuality` verdict. It
re-walks nothing the observe pass already saw.
"""

from __future__ import annotations

from typing import Any

from nautilus_trader.model.identifiers import InstrumentId

from research.aegis_research.configuration import DataConfig
from research.aegis_research.market_data.contracts import (
    QUALITY_DATA_UNAVAILABLE,
    QUALITY_DEGRADED_ALLOWED,
    QUALITY_HEALTHY,
    QUALITY_REJECTED,
    UNAVAILABLE_REASON_KEY,
    DataDiagnostics,
    MarketDataQuality,
)


def evaluate(
    config: DataConfig,
    diagnostics: tuple[DataDiagnostics, ...],
    *,
    required_arrays: tuple[str, ...],
    index_evidence: dict[str, Any],
) -> MarketDataQuality:
    reasons: list[str] = []
    warnings: list[str] = []
    degradations: set[str] = set()
    allowed: set[str] = set(config.quality.allowed_degradations)

    unavailable = [
        diagnostic
        for diagnostic in diagnostics
        if diagnostic.configured
        and diagnostic.provider_status == QUALITY_DATA_UNAVAILABLE
    ]
    if unavailable:
        return MarketDataQuality(
            state=QUALITY_DATA_UNAVAILABLE,
            reasons=(
                index_evidence.get(UNAVAILABLE_REASON_KEY)
                or "market data is unavailable for the requested window",
            ),
            allowed_degradations=tuple(config.quality.allowed_degradations),
        )

    skipped_instrument_ids = [
        diagnostic.instrument_id
        for diagnostic in diagnostics
        if diagnostic.configured and diagnostic.provider_status == "skipped"
    ]
    allowed_skipped_instrument_ids = (
        set(skipped_instrument_ids)
        if (config.skip_on_error and "skipped_instrument_ids" in allowed)
        else set()
    )
    if skipped_instrument_ids:
        skipped_values = _instrument_id_values(skipped_instrument_ids)
        if allowed_skipped_instrument_ids:
            _record_quality_issue(
                "skipped_instrument_ids",
                f"configured instrument IDs missing from loaded data: {skipped_values}",
                allowed,
                reasons,
                warnings,
                degradations,
            )
        else:
            reasons.append(
                f"configured instrument IDs missing from loaded data: {skipped_values}"
            )

    if index_evidence.get("raw_index_has_duplicates"):
        _record_quality_issue(
            "duplicate_index",
            "raw data index contains duplicate timestamps",
            allowed,
            reasons,
            warnings,
            degradations,
        )
    if index_evidence.get("raw_index_monotonic_increasing") is False:
        _record_quality_issue(
            "non_monotonic_index",
            "raw data index is not monotonic increasing",
            allowed,
            reasons,
            warnings,
            degradations,
        )

    configured_diagnostics = [
        diagnostic
        for diagnostic in diagnostics
        if diagnostic.configured
        and diagnostic.instrument_id not in allowed_skipped_instrument_ids
    ]
    for name in required_arrays:
        array_diagnostics = [
            (diagnostic, diagnostic.arrays.get(name))
            for diagnostic in configured_diagnostics
        ]
        available = [
            (diagnostic, array_diag)
            for diagnostic, array_diag in array_diagnostics
            if array_diag is not None and array_diag.available
        ]
        if not available:
            reasons.append(f"required array {name!r} is unavailable")
            continue
        if all(array_diag.rows == 0 for _, array_diag in available):
            reasons.append(f"required array {name!r} is empty")
            continue
        missing_required_instrument_ids = [
            diagnostic.instrument_id
            for diagnostic, array_diag in array_diagnostics
            if array_diag is None or not array_diag.available
        ]
        if missing_required_instrument_ids:
            missing_required_values = _instrument_id_values(missing_required_instrument_ids)
            reasons.append(
                "required array "
                f"{name!r} is missing instrument IDs {missing_required_values}"
            )
        if any(array_diag.missing > 0 for _, array_diag in available):
            _record_quality_issue(
                "missing_rows",
                f"required array {name!r} contains missing values",
                allowed,
                reasons,
                warnings,
                degradations,
            )
        non_numeric = [
            diagnostic.instrument_id
            for diagnostic, array_diag in available
            if array_diag.numeric is False
        ]
        if non_numeric:
            reasons.append(
                "required array "
                f"{name!r} has non-numeric instrument IDs {_instrument_id_values(non_numeric)}"
            )

    if reasons:
        state = QUALITY_REJECTED
    elif degradations & allowed:
        state = QUALITY_DEGRADED_ALLOWED
    else:
        state = QUALITY_HEALTHY
    return MarketDataQuality(
        state=state,
        reasons=tuple(reasons),
        warnings=tuple(warnings),
        allowed_degradations=tuple(config.quality.allowed_degradations),
    )


def _record_quality_issue(
    degradation: str,
    message: str,
    allowed: set[str],
    reasons: list[str],
    warnings: list[str],
    degradations: set[str],
) -> None:
    degradations.add(degradation)
    if degradation in allowed:
        warnings.append(message)
    else:
        reasons.append(message)


def _instrument_id_values(instrument_ids: list[InstrumentId]) -> list[str]:
    return [instrument_id.value for instrument_id in instrument_ids]
