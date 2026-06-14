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
    major_currency, _ = _MINOR_UNITS.get(quote_currency, (quote_currency, 1.0))
    return major_currency != base_currency


def assemble_fx_rates(
    pair_series_by_currency: Mapping[str, pd.Series],
    index: pd.Index,
) -> pd.DataFrame:
    """Align supplied ``base->ccy`` FX series onto the price ``index``."""
    return pd.DataFrame(
        {
            currency: series.reindex(index).ffill()
            for currency, series in pair_series_by_currency.items()
        },
        index=index,
    )


def required_fx_currencies(
    currency_by_symbol: Mapping[str, str],
    base_currency: str,
) -> set[str]:
    """Major quote currencies that need an FX series to reach ``base_currency``."""
    needed: set[str] = set()
    for quote_currency in currency_by_symbol.values():
        major_currency, _ = _MINOR_UNITS.get(quote_currency, (quote_currency, 1.0))
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
    return {
        name: (
            convert_prices_to_base(panel, currency_by_symbol, base_currency, fx_rates)
            if name in _PRICE_ARRAYS
            else panel
        )
        for name, panel in arrays.items()
    }


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
    major_currency, scale = _MINOR_UNITS.get(quote_currency, (quote_currency, 1.0))
    major = series * scale
    if major_currency == base_currency:
        return major
    if major_currency not in fx_rates.columns:
        raise ValueError(
            f"no FX series for quote currency {major_currency!r}, needed to "
            f"convert {series.name!r} to base {base_currency!r}"
        )
    return major / fx_rates[major_currency]
