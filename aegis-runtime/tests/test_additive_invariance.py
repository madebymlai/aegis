"""Additive-invariance enforcement for continuous-future roots (r8b.9 Slice F, part a).

A continuous future is re-based by a *uniform additive shift* of all prior history at
every roll (``BACKWARD_SPREAD``). A bundle that allocates off the **absolute price level**
of a continuous root therefore computes a different signal before vs after a roll — it
silently desyncs live-vs-research (the ``live@T ≡ research`` contract). A bundle that
allocates off **differences** is invariant: the shift cancels.

This is asserted as a behavioural property, not a documented hope: shift the continuous-root
price columns by a constant and the decided weights must not move. ``compute_weights``
enforces it for any contract that declares ``futures`` — a non-invariant continuous-root
bundle fails loudly at the allocation boundary instead of drifting at the next roll.

The teeth: ``price_proportional_strategy`` (``Close / ΣClose``) is absolute-level and is
rejected; ``momentum_strategy`` (``Close − Close[0]``) and ``equal_weight_strategy`` are
difference-/level-free and are accepted. Native equities are never re-based, so a bundle
without ``futures`` is not checked even with an absolute-level strategy.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from nautilus_trader.model.enums import ContinuousFutureAdjustmentType
from nautilus_trader.model.identifiers import InstrumentId

from aegis_runtime.additive_invariance import AbsolutePriceLevelError
from aegis_runtime.currency import CurrencyConversion
from aegis_runtime.bundle import (
    BundleManifest,
    ComponentSpec,
    DataContract,
    ExecutionBundle,
    LockedExecutionPlan,
    MarketDataBundle,
    MissingIndexPolicy,
)
from aegis_runtime.drift_band import DriftBand

_ES = InstrumentId.from_str("ES.XCME")  # a materialised continuous-future root column
_AAPL = InstrumentId.from_str("AAPL.NASDAQ")  # a native equity (never re-based)


def _index(n: int) -> pd.DatetimeIndex:
    return pd.date_range("2024-01-01", periods=n, freq="D")


def _strategy_spec(module: str) -> ComponentSpec:
    return ComponentSpec(
        family="strategies",
        component_id=f"test.{module}",
        module=module,
        input_names=("Close",),
        output_names=("target_weights",),
        params={},
    )


def _contract(*, futures: tuple[str, ...]) -> DataContract:
    return DataContract(
        instrument_ids=(_ES, _AAPL),
        required_arrays=("Close",),
        base_currency="USD",
        timeframe="1D",
        missing_index=MissingIndexPolicy.DROP,
        lookback_bars=0,
        futures=futures,
        adjustment_mode=(
            ContinuousFutureAdjustmentType.BACKWARD_SPREAD if futures else None
        ),
    )


def _bundle(strategy_module: str, *, futures: tuple[str, ...]) -> ExecutionBundle:
    contract = _contract(futures=futures)
    plan = LockedExecutionPlan(
        strategy=_strategy_spec(strategy_module),
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


def _window() -> MarketDataBundle:
    # Non-degenerate so an absolute-level strategy's weights actually move under a shift:
    # ES rises, AAPL dips then jumps.
    close = pd.DataFrame(
        {_ES: [10.0, 12.0, 15.0], _AAPL: [20.0, 19.0, 25.0]},
        index=_index(3),
    )
    return MarketDataBundle({"Close": close})


def test_absolute_price_strategy_is_rejected_for_a_continuous_root() -> None:
    """``Close / ΣClose`` reads absolute levels: shifting the ES column changes the
    proportions, so the bundle would desync at a roll → rejected at allocation."""
    bundle = _bundle("price_proportional_strategy", futures=("ES",))
    with pytest.raises(AbsolutePriceLevelError, match="ES"):
        bundle.compute_weights(_window(), currency_conversion=None)


def test_difference_strategy_is_accepted_for_a_continuous_root() -> None:
    """``Close − Close[0]`` is invariant to the re-base, so the continuous-root bundle
    computes weights without tripping the guard."""
    bundle = _bundle("momentum_strategy", futures=("ES",))
    weights = bundle.compute_weights(_window(), currency_conversion=None)
    assert list(weights.columns) == [_ES, _AAPL]
    # latest row: ES change +5, AAPL change +5 → equal split, summing to 1.0
    assert weights.iloc[-1].to_numpy() == pytest.approx([0.5, 0.5])


def test_equal_weight_strategy_is_accepted_for_a_continuous_root() -> None:
    bundle = _bundle("equal_weight_strategy", futures=("ES",))
    weights = bundle.compute_weights(_window(), currency_conversion=None)
    assert (weights.to_numpy() == 0.5).all()


def test_absolute_price_strategy_allowed_without_continuous_roots() -> None:
    """Native equities never re-base, so the same absolute-level strategy is fine when no
    continuous root is declared — the guard must not over-reject."""
    bundle = _bundle("price_proportional_strategy", futures=())
    weights = bundle.compute_weights(_window(), currency_conversion=None)  # no raise
    assert weights.iloc[-1].sum() == pytest.approx(1.0)


def test_probe_survives_a_constant_conversion_for_a_difference_strategy() -> None:
    """The probe re-bases NATIVE prices and recomputes through the same conversion:
    under a constant FX rate, ``(price + shift) * c`` keeps differences uniformly
    scaled, so a difference strategy still passes."""
    bundle = _bundle("momentum_strategy", futures=("ES",))
    conversion = CurrencyConversion(
        rate_by_instrument={_ES: pd.Series([1.1, 1.1, 1.1], index=_index(3))},
        currency_by_instrument_id={_ES: "USD", _AAPL: "EUR"},
    )

    weights = bundle.compute_weights(_window(), currency_conversion=conversion)

    assert weights.iloc[-1].sum() == pytest.approx(1.0)


def test_probe_composes_native_rebase_before_a_moving_conversion() -> None:
    """With time-varying FX the probed path is ``(price + shift) * FX(t)`` — the shift
    acquires ``shift * ΔFX`` in base currency, so an ordinary base-currency difference
    correctly fails. This pins the probe to the native side of the conversion: a
    post-conversion probe would let this exact bundle pass."""
    bundle = _bundle("momentum_strategy", futures=("ES",))
    conversion = CurrencyConversion(
        rate_by_instrument={_ES: pd.Series([1.0, 1.2, 1.4], index=_index(3))},
        currency_by_instrument_id={_ES: "USD", _AAPL: "EUR"},
    )

    with pytest.raises(AbsolutePriceLevelError, match="ES"):
        bundle.compute_weights(_window(), currency_conversion=conversion)


def test_root_colliding_with_a_same_symbol_native_is_rejected() -> None:
    """A native instrument sharing a declared root's bare symbol (a stock ``ES`` beside the
    ``ES.XCME`` continuous root) makes the continuous id ambiguous. The guard must refuse to
    guess — re-basing the wrong column would corrupt the invariance check — so it raises rather
    than matching by bare symbol alone."""
    es_native = InstrumentId.from_str("ES.NASDAQ")  # same symbol, not the continuous root
    with pytest.raises(ValueError, match="ambiguous"):
        DataContract(
            instrument_ids=(_ES, es_native),
            required_arrays=("Close",),
            base_currency="USD",
            timeframe="1D",
            missing_index=MissingIndexPolicy.DROP,
            lookback_bars=0,
            futures=("ES",),
        )


def test_difference_weights_are_byte_stable_across_a_rebase() -> None:
    """The integration-level property: a fully-built difference bundle reproduces its
    allocation exactly when the continuous-root price column is re-based — live ≡ research
    across the roll's additive shift."""
    bundle = _bundle("momentum_strategy", futures=("ES",))
    window = _window()
    base = bundle.compute_weights(window, currency_conversion=None)

    shifted_close = window.array("Close").copy()
    shifted_close[_ES] = shifted_close[_ES] + 137.0  # a roll's uniform additive re-base of ES
    rebased = bundle.compute_weights(
        MarketDataBundle({"Close": shifted_close}), currency_conversion=None
    )

    assert np.allclose(base.to_numpy(), rebased.to_numpy(), atol=1e-9, equal_nan=True)
