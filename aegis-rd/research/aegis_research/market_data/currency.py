"""Convert per-symbol price panels into a single portfolio base currency.

Research and locked execution share the conversion rules in ``aegis_runtime.currency``.
This module wraps the converted panels back into the kernel ``MarketDataBundle``
so the arithmetic lives in one place.
"""

from __future__ import annotations

from collections.abc import Mapping

import pandas as pd
from aegis_runtime import MarketDataBundle
from aegis_runtime.currency import (
    assemble_fx_rates,
    convert_arrays_to_base,
    convert_prices_to_base,
    required_fx_currencies,
    requires_conversion,
)


def convert_bundle_to_base(
    bundle: MarketDataBundle,
    currency_by_symbol: Mapping[str, str],
    base_currency: str,
    fx_rates: pd.DataFrame,
) -> MarketDataBundle:
    """Re-express a bundle's price panels in ``base_currency``."""
    return MarketDataBundle(
        arrays=convert_arrays_to_base(
            bundle.arrays, currency_by_symbol, base_currency, fx_rates
        )
    )


__all__ = [
    "assemble_fx_rates",
    "convert_bundle_to_base",
    "convert_prices_to_base",
    "required_fx_currencies",
    "requires_conversion",
]
