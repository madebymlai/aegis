"""Convert per-symbol price panels into a single portfolio base currency.

The pipeline is otherwise currency-naive: each symbol's prices arrive in their
native quote currency. This module is the one place that re-expresses them in
the book's base currency, so FX-sourced (haven/tail) convexity becomes visible
and a mixed-currency book is combined coherently.

The converter is pure (no I/O): it takes the FX rates as an aligned frame and
leaves fetching to the caller.
"""

from __future__ import annotations

from collections.abc import Mapping

import pandas as pd

from research.aegis_research.market_data.contracts import (
    LOGICAL_ARRAYS,
    MarketDataBundle,
)

# Price panels are converted to base; Volume is a share count, not a price, so it
# passes through untouched. Derived from the array taxonomy to stay in step with it.
_PRICE_ARRAYS = frozenset(
    name for key, name in LOGICAL_ARRAYS.items() if key != "volume"
)

# Minor units quote in a fraction of their major currency (e.g. GBp = pence =
# GBP / 100). The FX series only carries the major currency, so a minor unit is
# scaled to its major before the rate is applied. This is a currency-system fact,
# not a per-instrument one, so it lives here rather than in the config record.
_MINOR_UNITS: dict[str, tuple[str, float]] = {"GBp": ("GBP", 0.01)}


def requires_conversion(quote_currency: str, base_currency: str) -> bool:
    """Whether a leg quoted in ``quote_currency`` needs FX conversion to base.

    A minor unit (``GBp``) inherits its major currency's foreign-ness, so the
    decision normalises through the same minor-unit map the converter uses.
    """
    major_currency, _ = _MINOR_UNITS.get(quote_currency, (quote_currency, 1.0))
    return major_currency != base_currency


def assemble_fx_rates(
    pair_series_by_currency: Mapping[str, pd.Series],
    index: pd.Index,
) -> pd.DataFrame:
    """Align fetched ``base->ccy`` FX series onto the price ``index``.

    Each series is reindexed to ``index`` and forward-filled, so an FX-calendar
    gap (a holiday the equity venue trades through) carries the last rate rather
    than puncturing a price with NaN. Leading gaps - FX history shorter than the
    price history - stay NaN and are left for the data-quality gate to catch
    (back-filling would leak future rates).
    """
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
    """The set of major currencies that need an FX series to reach base.

    Minor units are normalised to their major (``GBp`` -> ``GBP``), the base is
    excluded, and duplicates collapse - so the result is exactly the set of
    ``base->ccy`` rates the converter will divide by.
    """
    needed: set[str] = set()
    for quote_currency in currency_by_symbol.values():
        major_currency, _ = _MINOR_UNITS.get(quote_currency, (quote_currency, 1.0))
        if major_currency != base_currency:
            needed.add(major_currency)
    return needed


def convert_bundle_to_base(
    bundle: MarketDataBundle,
    currency_by_symbol: Mapping[str, str],
    base_currency: str,
    fx_rates: pd.DataFrame,
) -> MarketDataBundle:
    """Re-express a bundle's price panels in ``base_currency``.

    Every price array (Open/High/Low/Close) is converted; Volume passes through
    unchanged, since dividing a share count by an FX rate is meaningless.
    """
    converted = {
        name: (
            convert_prices_to_base(panel, currency_by_symbol, base_currency, fx_rates)
            if name in _PRICE_ARRAYS
            else panel
        )
        for name, panel in bundle.arrays.items()
    }
    return MarketDataBundle(arrays=converted)


def convert_prices_to_base(
    prices: pd.DataFrame,
    currency_by_symbol: Mapping[str, str],
    base_currency: str,
    fx_rates: pd.DataFrame,
) -> pd.DataFrame:
    """Re-express ``prices`` (columns = symbols) in ``base_currency``.

    ``fx_rates`` columns are quote currencies carrying the native base quote -
    units of the quote currency per 1 unit of base (e.g. ``EURUSD`` under an EUR
    base) - so a quote-currency price is converted to base by *dividing*.
    """
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
