"""Constructor tests for ``prepare_run_arrays`` — the module's one test surface.

Every Array-preparation fact and invariant is asserted through the constructor
alone: no test imports the module's private helpers.
"""

from __future__ import annotations

import dataclasses
from typing import Any

import pandas as pd
import pytest
from aegis_data.distributions import Distribution
from aegis_runtime.currency import CurrencyConversion
from nautilus_trader.model.identifiers import InstrumentId

from research.aegis_research.data import (
    MarketDataQuality,
    MarketDataQualityError,
    MarketDataResult,
    RunArrayAlignmentError,
    prepare_run_arrays,
)
from tests.support.research.aegis_research.test_doubles import default_metadata

_AAPL = InstrumentId.from_str("AAPL.XNAS")
_INDEX = pd.date_range("2024-01-01", periods=3, freq="D")
_SIGNAL_CLOSE = [1.0, 2.0, 3.0]
_SIGNAL_OPEN = [1.5, 2.5, 3.5]
_PNL_CLOSE = [10.0, 20.0, 30.0]
_PNL_OPEN = [10.5, 20.5, 30.5]


class _Native:
    """Stand-in for a loaded source: ``get(feature=...)`` returns the named Array's frame.

    The ``feature`` kwarg mirrors the real accessor's signature; the minted noun
    for what it returns is Array.
    """

    def __init__(self, frames: dict[str, pd.DataFrame]) -> None:
        self._frames = frames

    def get(self, feature: str, **_kwargs: Any) -> pd.DataFrame:
        return self._frames[feature]


def _frame(
    values: list[float],
    *,
    index: pd.Index | None = None,
    column: InstrumentId = _AAPL,
) -> pd.DataFrame:
    return pd.DataFrame({column: values}, index=_INDEX if index is None else index)


def _result(**overrides: Any) -> MarketDataResult:
    defaults: dict[str, Any] = {
        "native_data": _Native(
            {"Close": _frame(_SIGNAL_CLOSE), "Open": _frame(_SIGNAL_OPEN)}
        ),
        "metadata": default_metadata(instrument_ids=[_AAPL]),
        "diagnostics": (),
        "quality": MarketDataQuality(state="healthy"),
    }
    defaults.update(overrides)
    return MarketDataResult(**defaults)


def _dual_result(
    pnl_close: pd.DataFrame | None = None,
    pnl_open: pd.DataFrame | None = None,
    **overrides: Any,
) -> MarketDataResult:
    pnl_close = _frame(_PNL_CLOSE) if pnl_close is None else pnl_close
    pnl_open = _frame(_PNL_OPEN) if pnl_open is None else pnl_open
    return _result(
        pnl_native_data=_Native({"Close": pnl_close, "Open": pnl_open}),
        **overrides,
    )


def test_single_series_pnl_frames_are_the_signal_frames() -> None:
    arrays = prepare_run_arrays(_result())

    assert arrays.pnl_close is arrays.signal.array("Close")
    assert arrays.pnl_open is arrays.signal.array("Open")


def test_dual_series_conversion_applies_to_both_views() -> None:
    conversion = CurrencyConversion(
        rate_by_instrument={_AAPL: pd.Series(2.0, index=_INDEX)}
    )

    arrays = prepare_run_arrays(_dual_result(currency_conversion=conversion))

    pd.testing.assert_frame_equal(arrays.signal.array("Close"), _frame([2.0, 4.0, 6.0]))
    pd.testing.assert_frame_equal(arrays.signal.array("Open"), _frame([3.0, 5.0, 7.0]))
    pd.testing.assert_frame_equal(arrays.pnl_close, _frame([20.0, 40.0, 60.0]))
    pd.testing.assert_frame_equal(arrays.pnl_open, _frame([21.0, 41.0, 61.0]))


def test_the_same_conversion_produced_both_views() -> None:
    # FX-equivalence: one non-constant rate series ([1.1, 1.2, 1.3]) applied to
    # both native views (signal [1, 2, 3]; pnl [10, 20, 30]) — the coherence
    # claim on the value, pinned as literal per-bar products.
    rate = pd.Series([1.1, 1.2, 1.3], index=_INDEX)
    conversion = CurrencyConversion(rate_by_instrument={_AAPL: rate})

    arrays = prepare_run_arrays(_dual_result(currency_conversion=conversion))

    pd.testing.assert_frame_equal(arrays.signal.array("Close"), _frame([1.1, 2.4, 3.9]))
    pd.testing.assert_frame_equal(arrays.pnl_close, _frame([11.0, 24.0, 39.0]))


def test_pnl_calendar_with_divergent_values_fails_construction() -> None:
    shifted = pd.date_range("2024-01-02", periods=3, freq="D")

    with pytest.raises(RunArrayAlignmentError) as excinfo:
        prepare_run_arrays(
            _dual_result(
                pnl_close=_frame(_PNL_CLOSE, index=shifted),
                pnl_open=_frame(_PNL_OPEN, index=shifted),
            )
        )

    error = excinfo.value
    assert error.array_name == "Close"
    assert (error.signal_rows, error.pnl_rows) == (3, 3)
    assert error.first_divergent == ("2024-01-01 00:00:00", "2024-01-02 00:00:00")
    assert error.last_divergent == ("2024-01-03 00:00:00", "2024-01-04 00:00:00")


def test_pnl_calendar_out_of_order_fails_construction() -> None:
    reversed_index = _INDEX[::-1]

    with pytest.raises(RunArrayAlignmentError) as excinfo:
        prepare_run_arrays(
            _dual_result(
                pnl_close=_frame(_PNL_CLOSE, index=reversed_index),
                pnl_open=_frame(_PNL_OPEN, index=reversed_index),
            )
        )

    error = excinfo.value
    assert error.array_name == "Close"
    assert error.first_divergent == ("2024-01-01 00:00:00", "2024-01-03 00:00:00")
    assert error.last_divergent == ("2024-01-03 00:00:00", "2024-01-01 00:00:00")


def test_pnl_calendar_with_missing_rows_fails_construction() -> None:
    truncated = _INDEX[:2]

    with pytest.raises(RunArrayAlignmentError) as excinfo:
        prepare_run_arrays(
            _dual_result(
                pnl_close=_frame(_PNL_CLOSE[:2], index=truncated),
                pnl_open=_frame(_PNL_OPEN[:2], index=truncated),
            )
        )

    error = excinfo.value
    assert (error.signal_rows, error.pnl_rows) == (3, 2)
    assert error.first_divergent is None


def test_pnl_column_set_divergence_fails_construction() -> None:
    other = InstrumentId.from_str("MSFT.XNAS")

    with pytest.raises(RunArrayAlignmentError) as excinfo:
        prepare_run_arrays(
            _dual_result(
                pnl_close=_frame(_PNL_CLOSE, column=other),
                pnl_open=_frame(_PNL_OPEN, column=other),
            )
        )

    error = excinfo.value
    assert error.array_name == "Close"
    assert error.missing_columns == (str(_AAPL),)
    assert error.extra_columns == (str(other),)


def test_unusable_market_data_fails_construction() -> None:
    rejected = MarketDataQuality(state="rejected", reasons=("synthetic failure",))

    with pytest.raises(MarketDataQualityError):
        prepare_run_arrays(_result(quality=rejected))


def test_conversion_and_distributions_are_carried_on_the_value() -> None:
    conversion = CurrencyConversion(rate_by_instrument={})
    distribution = Distribution.from_ex_date(
        _AAPL, "2024-01-02", amount=0.42, currency="USD"
    )

    arrays = prepare_run_arrays(
        _result(currency_conversion=conversion, distributions=(distribution,))
    )

    assert arrays.currency_conversion is conversion
    assert arrays.distributions == (distribution,)


def test_instrument_size_increment_is_not_an_array_coherence_fact() -> None:
    arrays = prepare_run_arrays(
        _result(size_increment_by_instrument={_AAPL: 0.01})
    )

    assert not hasattr(arrays, "size_increment_by_instrument")


def test_run_arrays_is_frozen() -> None:
    arrays = prepare_run_arrays(_result())

    with pytest.raises(dataclasses.FrozenInstanceError):
        arrays.pnl_close = arrays.pnl_open  # type: ignore[misc]
