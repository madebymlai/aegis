"""Per-root roll-sensitivity check (aegis-rd-tkj5.2).

A continuous future is re-based at every roll under the contract-declared
adjustment mode: ratio re-basing scales prior history, spread re-basing shifts
it. The check is a deterministic *metamorphic* detector — it perturbs each
continuous root's NATIVE price columns under the declared algebra, recomputes
through the same currency-conversion/Component path, and requires the decided
weights to be unchanged. Roots roll independently, so each root is probed
independently: cross-root features that survive a common transform are still
rejected.

Tests exercise the public seams only — ``ExecutionBundle.compute_weights`` for
the feature matrix and ``compute_roll_checked_weights`` for the module
contract — and never encode the private perturbation constants.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from nautilus_trader.model.enums import ContinuousFutureAdjustmentType
from nautilus_trader.model.identifiers import InstrumentId

from aegis_runtime.bundle import (
    BundleManifest,
    ComponentSpec,
    DataContract,
    ExecutionBundle,
    LockedExecutionPlan,
    MarketDataBundle,
    MissingIndexPolicy,
)
from aegis_runtime.currency import CurrencyConversion
from aegis_runtime.drift_band import DriftBand
from aegis_runtime.roll_sensitivity import (
    RollSensitivityError,
    compute_roll_checked_weights,
)

_ES = InstrumentId.from_str("ES.XCME")
_NQ = InstrumentId.from_str("NQ.XCME")
_AAPL = InstrumentId.from_str("AAPL.NASDAQ")

_RATIO = ContinuousFutureAdjustmentType.BACKWARD_RATIO
_SPREAD = ContinuousFutureAdjustmentType.BACKWARD_SPREAD


def _index(n: int) -> pd.DatetimeIndex:
    return pd.date_range("2024-01-01", periods=n, freq="D")


def _contract(
    *,
    instrument_ids: tuple[InstrumentId, ...],
    futures: tuple[str, ...],
    adjustment_mode: ContinuousFutureAdjustmentType | None,
) -> DataContract:
    return DataContract(
        instrument_ids=instrument_ids,
        required_arrays=("Close",),
        base_currency="USD",
        timeframe="1D",
        missing_index=MissingIndexPolicy.DROP,
        lookback_bars=0,
        futures=futures,
        adjustment_mode=adjustment_mode,
    )


def _bundle(
    strategy_module: str,
    *,
    instrument_ids: tuple[InstrumentId, ...] = (_ES, _AAPL),
    futures: tuple[str, ...] = ("ES",),
    adjustment_mode: ContinuousFutureAdjustmentType | None = _RATIO,
) -> ExecutionBundle:
    contract = _contract(
        instrument_ids=instrument_ids,
        futures=futures,
        adjustment_mode=adjustment_mode,
    )
    plan = LockedExecutionPlan(
        strategy=ComponentSpec(
            family="strategies",
            component_id=f"test.{strategy_module}",
            module=strategy_module,
            input_names=("Close",),
            output_names=("target_weights",),
            params={},
        ),
        indicators=(),
        instrument_bands={
            instrument_id: DriftBand.symmetric(0.0) for instrument_id in contract.instrument_ids
        },
        gross_cap=1.0,
        net_cap=1.0,
        direction="longonly",
    )
    manifest = BundleManifest(
        run_id="r",
        role="best",
        candidate_key="k",
        component_source_hashes={},
        instrument_ids=contract.instrument_ids,
    )
    return ExecutionBundle(contract=contract, manifest=manifest, plan=plan)


def _window(
    instrument_ids: tuple[InstrumentId, ...] = (_ES, _AAPL),
) -> MarketDataBundle:
    # Non-degenerate so a level-reading strategy's weights actually move under a
    # perturbation: distinct trends per column.
    columns = {
        instrument_ids[0]: [10.0, 12.0, 15.0],
        instrument_ids[1]: [20.0, 19.0, 25.0],
    }
    close = pd.DataFrame(columns, index=_index(3))
    return MarketDataBundle({"Close": close})


# --- single-root feature matrix through ExecutionBundle.compute_weights ---------


def test_ratio_accepts_a_return_based_allocation() -> None:
    bundle = _bundle("return_proportional_strategy", adjustment_mode=_RATIO)

    weights = bundle.compute_weights(_window(), currency_conversion=None)

    assert weights.iloc[-1].sum() == pytest.approx(1.0)


def test_ratio_rejects_a_raw_difference_allocation() -> None:
    bundle = _bundle("momentum_strategy", adjustment_mode=_RATIO)

    with pytest.raises(RollSensitivityError, match="ES"):
        bundle.compute_weights(_window(), currency_conversion=None)


def test_ratio_accepts_equal_weight() -> None:
    bundle = _bundle("equal_weight_strategy", adjustment_mode=_RATIO)

    weights = bundle.compute_weights(_window(), currency_conversion=None)

    assert (weights.to_numpy() == 0.5).all()


def test_spread_accepts_a_difference_allocation() -> None:
    bundle = _bundle("momentum_strategy", adjustment_mode=_SPREAD)

    weights = bundle.compute_weights(_window(), currency_conversion=None)

    assert weights.iloc[-1].sum() == pytest.approx(1.0)


def test_spread_rejects_a_percentage_allocation() -> None:
    bundle = _bundle("return_proportional_strategy", adjustment_mode=_SPREAD)

    with pytest.raises(RollSensitivityError, match="ES"):
        bundle.compute_weights(_window(), currency_conversion=None)


def test_spread_accepts_equal_weight() -> None:
    bundle = _bundle("equal_weight_strategy", adjustment_mode=_SPREAD)

    weights = bundle.compute_weights(_window(), currency_conversion=None)

    assert (weights.to_numpy() == 0.5).all()


def test_absolute_levels_are_allowed_without_continuous_roots() -> None:
    # Native equities never re-base; the check must not over-reject an ETF book.
    bundle = _bundle(
        "price_proportional_strategy",
        instrument_ids=(_AAPL, InstrumentId.from_str("MSFT.NASDAQ")),
        futures=(),
        adjustment_mode=None,
    )
    window = _window((_AAPL, InstrumentId.from_str("MSFT.NASDAQ")))

    weights = bundle.compute_weights(window, currency_conversion=None)

    assert weights.iloc[-1].sum() == pytest.approx(1.0)


# --- moving-FX composition -------------------------------------------------------


def _moving_fx() -> CurrencyConversion:
    return CurrencyConversion(
        rate_by_instrument={_ES: pd.Series([1.0, 1.2, 1.4], index=_index(3))},
        currency_by_instrument_id={_ES: "USD", _AAPL: "EUR"},
    )


def test_spread_with_moving_fx_rejects_a_base_currency_difference() -> None:
    """The probed path is ``(price + shift) * FX(t)``: the shift acquires
    ``shift * ΔFX`` in base currency, so an ordinary difference correctly fails —
    spread invariance is NOT promised under moving FX."""
    bundle = _bundle("momentum_strategy", adjustment_mode=_SPREAD)

    with pytest.raises(RollSensitivityError, match="currency"):
        bundle.compute_weights(_window(), currency_conversion=_moving_fx())


def test_ratio_with_moving_fx_keeps_return_stability() -> None:
    """A per-root scale cancels inside ``(k * price) * FX(t)`` returns, so a
    return-based allocation stays stable through the same composition."""
    bundle = _bundle("return_proportional_strategy", adjustment_mode=_RATIO)

    weights = bundle.compute_weights(_window(), currency_conversion=_moving_fx())

    assert weights.iloc[-1].sum() == pytest.approx(1.0)


# --- independent-root probing: cross-root cancellation regressions ---------------


def test_ratio_rejects_a_two_root_ratio_cancellation() -> None:
    """ES/NQ survives a common scale but roots roll independently: perturbing one
    root alone changes the ratio, so both probes fail and both roots are named."""
    bundle = _bundle(
        "ratio_pair_strategy",
        instrument_ids=(_ES, _NQ),
        futures=("ES", "NQ"),
        adjustment_mode=_RATIO,
    )

    with pytest.raises(RollSensitivityError, match=r"(?s)ES.*NQ"):
        bundle.compute_weights(_window((_ES, _NQ)), currency_conversion=None)


def test_spread_rejects_a_two_root_spread_cancellation() -> None:
    """ES-NQ survives a common shift but roots roll independently: shifting one
    root alone changes the level spread, so the probes fail."""
    bundle = _bundle(
        "spread_pair_strategy",
        instrument_ids=(_ES, _NQ),
        futures=("ES", "NQ"),
        adjustment_mode=_SPREAD,
    )

    with pytest.raises(RollSensitivityError, match=r"(?s)ES.*NQ"):
        bundle.compute_weights(_window((_ES, _NQ)), currency_conversion=None)


# --- module contract: evaluation counts, comparison, error causes ----------------


class _CountingDecide:
    def __init__(self, weights_from) -> None:
        self.calls: list[MarketDataBundle] = []
        self._weights_from = weights_from

    def __call__(self, native: MarketDataBundle) -> pd.DataFrame:
        self.calls.append(native)
        return self._weights_from(native)


def _equal_weights(native: MarketDataBundle) -> pd.DataFrame:
    close = native.array("Close")
    return pd.DataFrame(0.5, index=close.index, columns=close.columns)


def test_no_futures_contract_evaluates_exactly_once() -> None:
    contract = _contract(
        instrument_ids=(_AAPL,), futures=(), adjustment_mode=None
    )
    decide = _CountingDecide(_equal_weights)

    compute_roll_checked_weights(
        contract=contract,
        native_window=MarketDataBundle(
            {"Close": pd.DataFrame({_AAPL: [1.0, 2.0]}, index=_index(2))}
        ),
        decide=decide,
    )

    assert len(decide.calls) == 1


@pytest.mark.parametrize(
    ("futures", "instrument_ids", "expected_calls"),
    [
        (("ES",), (_ES, _AAPL), 2),
        (("ES", "NQ"), (_ES, _NQ), 3),
    ],
)
def test_r_roots_evaluate_exactly_one_plus_r_times(
    futures: tuple[str, ...],
    instrument_ids: tuple[InstrumentId, ...],
    expected_calls: int,
) -> None:
    contract = _contract(
        instrument_ids=instrument_ids, futures=futures, adjustment_mode=_RATIO
    )
    decide = _CountingDecide(_equal_weights)

    compute_roll_checked_weights(
        contract=contract,
        native_window=_window(instrument_ids),
        decide=decide,
    )

    assert len(decide.calls) == expected_calls


def test_label_mismatch_fails_the_probe() -> None:
    contract = _contract(
        instrument_ids=(_ES, _AAPL), futures=("ES",), adjustment_mode=_RATIO
    )
    calls = {"n": 0}

    def relabeling_decide(native: MarketDataBundle) -> pd.DataFrame:
        calls["n"] += 1
        weights = _equal_weights(native)
        if calls["n"] > 1:  # probe recomputation returns re-ordered columns
            return weights[list(weights.columns)[::-1]]
        return weights

    with pytest.raises(RollSensitivityError, match="ES"):
        compute_roll_checked_weights(
            contract=contract,
            native_window=_window(),
            decide=relabeling_decide,
        )


def test_matching_warmup_nans_pass() -> None:
    contract = _contract(
        instrument_ids=(_ES, _AAPL), futures=("ES",), adjustment_mode=_RATIO
    )

    def nan_head_equal_weights(native: MarketDataBundle) -> pd.DataFrame:
        weights = _equal_weights(native)
        weights.iloc[0] = np.nan
        return weights

    result = compute_roll_checked_weights(
        contract=contract,
        native_window=_window(),
        decide=nan_head_equal_weights,
    )

    assert result.iloc[0].isna().all()


def test_recomputation_exception_is_wrapped_with_root_and_mode() -> None:
    contract = _contract(
        instrument_ids=(_ES, _AAPL), futures=("ES",), adjustment_mode=_SPREAD
    )
    calls = {"n": 0}

    def exploding_decide(native: MarketDataBundle) -> pd.DataFrame:
        calls["n"] += 1
        if calls["n"] > 1:
            raise RuntimeError("component blew up")
        return _equal_weights(native)

    with pytest.raises(RollSensitivityError, match=r"(?s)ES.*backward_spread") as excinfo:
        compute_roll_checked_weights(
            contract=contract,
            native_window=_window(),
            decide=exploding_decide,
        )

    assert isinstance(excinfo.value.__cause__, RuntimeError)


def test_failure_names_the_mode_and_hedges_its_claim() -> None:
    bundle = _bundle("momentum_strategy", adjustment_mode=_RATIO)

    with pytest.raises(RollSensitivityError) as excinfo:
        bundle.compute_weights(_window(), currency_conversion=None)

    message = str(excinfo.value)
    assert "backward_ratio" in message
    assert "metamorphic check failed" in message
    assert "observed roll sensitivity" in message
    assert "proved" not in message
    assert "certified" not in message
    assert "guaranteed" not in message
