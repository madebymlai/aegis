"""Shared native-to-base currency conversion for locked execution.

FX rates are supplied as base->quote series (for example EURUSD when the
portfolio base is EUR). Price panels quoted in a foreign currency are converted
to the base by dividing by the aligned FX rate. Symbols already quoted in the
base currency pass through unchanged.
"""

from __future__ import annotations

from collections.abc import Mapping

import pandas as pd

_PRICE_ARRAYS = frozenset({"Open", "High", "Low", "Close"})
_MINOR_UNITS: dict[str, tuple[str, float]] = {"GBp": ("GBP", 0.01)}


def requires_conversion(quote_currency: str, base_currency: str) -> bool:
    """Whether a leg quoted in ``quote_currency`` needs FX conversion to base."""
    major_currency, _ = _major_currency_and_scale(quote_currency)
    return major_currency != base_currency


def major_currency(quote_currency: str) -> str:
    """The ISO major currency for a quote token (``GBp`` pence -> ``GBP``)."""
    major, _ = _major_currency_and_scale(quote_currency)
    return major


def assemble_fx_rates(
    pair_series_by_currency: Mapping[str, pd.Series],
    index: pd.Index,
) -> pd.DataFrame:
    """Align supplied ``base->ccy`` FX series onto the price ``index``.

    Calendar gaps are forward-filled; leading gaps remain NaN so the caller's
    data-quality checks can catch insufficient FX history without backfilling.
    A tz-aware/naive mismatch between a series and the index is reconciled here
    (see :func:`_reindex_onto`) — aligning the FX series onto the index is this
    function's job, and a silent all-NaN reindex is the opposite of alignment.
    """
    return pd.DataFrame(
        {
            currency: _reindex_onto(series, index).ffill()
            for currency, series in pair_series_by_currency.items()
        },
        index=index,
    )


def _reindex_onto(series: pd.Series, index: pd.Index) -> pd.Series:
    """Reindex an FX series onto ``index``, reconciling a tz-aware/naive mismatch.

    The futures panel index is tz-aware (databento UTC) while a store FX series
    read from parquet is tz-naive; a plain reindex across that boundary matches
    nothing and silently drops every row. Daily FX timestamps sit at midnight, so
    localizing (or stripping) the tz is a pure label change that lines the series
    up with the index.
    """
    target_tz = getattr(index, "tz", None)
    source_tz = getattr(series.index, "tz", None)
    if source_tz is None and target_tz is not None:
        series = series.tz_localize(target_tz)
    elif source_tz is not None and target_tz is None:
        series = series.tz_localize(None)
    elif source_tz is not None and target_tz is not None and source_tz != target_tz:
        series = series.tz_convert(target_tz)
    return series.reindex(index)


def required_fx_currencies(
    currency_by_symbol: Mapping[str, str],
    base_currency: str,
) -> set[str]:
    """Major quote currencies that need an FX series to reach ``base_currency``."""
    needed: set[str] = set()
    for quote_currency in currency_by_symbol.values():
        major_currency, _ = _major_currency_and_scale(quote_currency)
        if major_currency != base_currency:
            needed.add(major_currency)
    return needed


def convert_arrays_to_base(
    arrays: Mapping[str, pd.DataFrame],
    currency_by_symbol: Mapping[str, str],
    base_currency: str,
    fx_rates: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    """Re-express all price arrays in ``base_currency``; leave non-prices alone."""
    converted: dict[str, pd.DataFrame] = {}
    for name, panel in arrays.items():
        if name in _PRICE_ARRAYS:
            converted[name] = convert_prices_to_base(
                panel, currency_by_symbol, base_currency, fx_rates
            )
            continue
        converted[name] = panel
    return converted


def convert_prices_to_base(
    prices: pd.DataFrame,
    currency_by_symbol: Mapping[str, str],
    base_currency: str,
    fx_rates: pd.DataFrame,
) -> pd.DataFrame:
    """Re-express ``prices`` (columns = symbols) in ``base_currency``."""
    converted = {
        symbol: _convert_column(
            prices[symbol], currency_by_symbol[symbol], base_currency, fx_rates
        )
        for symbol in prices.columns
    }
    return pd.DataFrame(converted, index=prices.index)


def _convert_column(
    series: pd.Series,
    quote_currency: str,
    base_currency: str,
    fx_rates: pd.DataFrame,
) -> pd.Series:
    major_currency, scale = _major_currency_and_scale(quote_currency)
    major = series * scale
    if major_currency == base_currency:
        return major
    if major_currency not in fx_rates.columns:
        raise ValueError(
            f"no FX series for quote currency {major_currency!r}, needed to "
            f"convert {series.name!r} to base {base_currency!r}"
        )
    return major / fx_rates[major_currency]


def _major_currency_and_scale(quote_currency: str) -> tuple[str, float]:
    return _MINOR_UNITS.get(quote_currency, (quote_currency, 1.0))


__all__ = [
    "assemble_fx_rates",
    "convert_arrays_to_base",
    "convert_prices_to_base",
    "major_currency",
    "required_fx_currencies",
    "requires_conversion",
]
