from __future__ import annotations

import pandas as pd
import pytest
from aegis_runtime.currency import CurrencyConversion
from nautilus_trader.model.identifiers import InstrumentId

_USD_LEG = InstrumentId.from_str("AAPL.XNAS")
_BASE_LEG = InstrumentId.from_str("BMW.XETR")


def test_apply_converts_price_arrays_by_aligned_rate_and_leaves_volume() -> None:
    index = pd.date_range("2024-01-01", periods=3, freq="D")
    close = pd.DataFrame(
        {_USD_LEG: [100.0, 110.0, 120.0], _BASE_LEG: [10.0, 11.0, 12.0]},
        index=index,
    )
    volume = pd.DataFrame(
        {_USD_LEG: [5.0, 5.0, 5.0], _BASE_LEG: [7.0, 7.0, 7.0]},
        index=index,
    )
    # Only the USD leg carries a native->base rate (EUR per 1 USD); the base leg is
    # absent from the map and must pass through untouched.
    conversion = CurrencyConversion({_USD_LEG: pd.Series([0.90, 0.92, 0.94], index=index)})

    out = conversion.apply({"Close": close, "Volume": volume})

    assert out["Close"][_USD_LEG].tolist() == pytest.approx([90.0, 101.2, 112.8])
    assert out["Close"][_BASE_LEG].tolist() == pytest.approx([10.0, 11.0, 12.0])
    # Volume is a share count, not a price — it must never be scaled by FX.
    assert out["Volume"][_USD_LEG].tolist() == pytest.approx([5.0, 5.0, 5.0])


def test_apply_forward_fills_a_sparser_fx_calendar_onto_the_bar_index() -> None:
    bars = pd.date_range("2024-01-01", periods=4, freq="D")
    close = pd.DataFrame({_USD_LEG: [100.0, 100.0, 100.0, 100.0]}, index=bars)
    # FX quotes only on day 1 and day 3 — the rate that stands at each bar is the
    # most recent quote at or before it (Nautilus holds the last mark xrate).
    rate = pd.Series([0.90, 0.95], index=bars[[0, 2]])
    conversion = CurrencyConversion({_USD_LEG: rate})

    out = conversion.apply({"Close": close})

    assert out["Close"][_USD_LEG].tolist() == pytest.approx([90.0, 90.0, 95.0, 95.0])


def test_rate_for_returns_aligned_native_to_base_rate_or_identity() -> None:
    bars = pd.date_range("2024-01-01", periods=4, freq="D")
    rate = pd.Series([0.90, 0.95], index=bars[[0, 2]])
    conversion = CurrencyConversion({_USD_LEG: rate})

    assert conversion.rate_for(_USD_LEG, bars).tolist() == pytest.approx(
        [0.90, 0.90, 0.95, 0.95]
    )
    assert conversion.rate_for(_BASE_LEG, bars).tolist() == pytest.approx(
        [1.0, 1.0, 1.0, 1.0]
    )


def test_apply_fails_loud_when_the_rate_starts_after_the_first_bar() -> None:
    bars = pd.date_range("2024-01-01", periods=3, freq="D")
    close = pd.DataFrame({_USD_LEG: [100.0, 100.0, 100.0]}, index=bars)
    # No quote at or before the first bar — there is no rate to mark it with.
    rate = pd.Series([0.90, 0.95], index=bars[[1, 2]])
    conversion = CurrencyConversion({_USD_LEG: rate})

    with pytest.raises(ValueError, match="does not cover every bar"):
        conversion.apply({"Close": close})
