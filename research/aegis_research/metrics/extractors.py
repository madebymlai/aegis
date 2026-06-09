"""Registry-driven vectorised metric extractors.

Each extractor is a pure ``read(pf, config) -> Series`` making exactly
one VBT accessor call over the whole grouped batch.  Transforms (scale,
abs) are declared as flags and applied by the loop in
``central_metrics_from_grouped_accessors`` — they are NOT baked into the
reads themselves.

The ``EXTRACTORS`` map is deliberately separate from
``MetricDefinition`` so that callables stay out of the evidence
fingerprint payload (``public_snapshot`` / ``fingerprint_payload``).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Literal

import pandas as pd

from research.aegis_research.configuration.schema import ReportConfig
from research.aegis_research.metrics.contracts import MetricRegistryError


@dataclass(frozen=True)
class ExtractorSpec:
    """Declarative spec for a single metric's vectorised batch read."""

    read: Callable[[Any, ReportConfig], Any]
    scale: Literal["percent", "identity"] = "identity"
    abs_: bool = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_series(value: Any) -> pd.Series:
    """Normalise a VBT MaybeSeries return to a plain Series."""
    if isinstance(value, pd.Series):
        return value
    return pd.Series([value])


# ---------------------------------------------------------------------------
# Vectorised read functions (one VBT accessor call each)
# ---------------------------------------------------------------------------


def _read_total_return(pf: Any, config: ReportConfig) -> pd.Series:
    return _to_series(pf.get_total_return())


def _read_max_dd(pf: Any, config: ReportConfig) -> pd.Series:
    return _to_series(pf.get_max_drawdown())


def _read_total_trades(pf: Any, config: ReportConfig) -> pd.Series:
    return _to_series(pf.exit_trades.count())


def _read_win_rate(pf: Any, config: ReportConfig) -> pd.Series:
    return _to_series(pf.exit_trades.get_win_rate())


def _read_total_fees_paid(pf: Any, config: ReportConfig) -> pd.Series:
    return _to_series(pf.orders.fees.sum())


def _read_sharpe_ratio(pf: Any, config: ReportConfig) -> pd.Series:
    return _to_series(
        pf.get_sharpe_ratio(
            freq=pd.Timedelta(config.freq),
            year_freq=pd.Timedelta(config.year_freq),
        )
    )


# ---------------------------------------------------------------------------
# Registry map
# ---------------------------------------------------------------------------

EXTRACTORS: dict[str, ExtractorSpec] = {
    "total_return": ExtractorSpec(_read_total_return, scale="percent"),
    "max_dd": ExtractorSpec(_read_max_dd, scale="percent", abs_=True),
    "total_trades": ExtractorSpec(_read_total_trades),
    "win_rate": ExtractorSpec(_read_win_rate, scale="percent"),
    "total_fees_paid": ExtractorSpec(_read_total_fees_paid),
    "sharpe_ratio": ExtractorSpec(_read_sharpe_ratio),
}

# ---------------------------------------------------------------------------
# Custom extractor registration (populated by register_custom_metrics)
# ---------------------------------------------------------------------------

_custom_extractors: dict[str, ExtractorSpec] = {}


def register_custom_extractors(extractors: Mapping[str, ExtractorSpec]) -> None:
    """Register custom metric extractors (called by register_custom_metrics).

    Raises MetricRegistryError if any custom metric id conflicts with a built-in
    or already-registered custom id.
    """
    conflicts = set(extractors) & set(EXTRACTORS)
    if conflicts:
        raise MetricRegistryError(
            f"custom extractor ids conflict with built-in metrics: {sorted(conflicts)}"
        )
    duplicates = set(extractors) & set(_custom_extractors)
    if duplicates:
        raise MetricRegistryError(
            f"custom extractor ids already registered: {sorted(duplicates)}"
        )
    _custom_extractors.update(extractors)


def get_extractors() -> dict[str, ExtractorSpec]:
    """Return the merged view of built-in and custom extractors."""
    return {**EXTRACTORS, **_custom_extractors}


def get_custom_extractor_keys() -> tuple[str, ...]:
    """Return the ids of all registered custom extractors."""
    return tuple(_custom_extractors)


def clear_custom_extractors() -> None:
    """Clear all registered custom extractors (for test isolation)."""
    _custom_extractors.clear()
