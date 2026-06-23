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
from nautilus_trader.model.identifiers import InstrumentId

from aegis_runtime.additive_invariance import AbsolutePriceLevelError
from aegis_runtime.bundle import (
    BundleManifest,
    ComponentSpec,
    DataContract,
    ExecutionBundle,
    LockedExecutionPlan,
    MarketDataBundle,
)

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
        lookback_bars=0,
        futures=futures,
    )


def _bundle(strategy_module: str, *, futures: tuple[str, ...]) -> ExecutionBundle:
    contract = _contract(futures=futures)
    plan = LockedExecutionPlan(
        strategy=_strategy_spec(strategy_module),
        indicators=(),
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
        bundle.compute_weights(_window())


def test_difference_strategy_is_accepted_for_a_continuous_root() -> None:
    """``Close − Close[0]`` is invariant to the re-base, so the continuous-root bundle
    computes weights without tripping the guard."""
    bundle = _bundle("momentum_strategy", futures=("ES",))
    weights = bundle.compute_weights(_window())
    assert list(weights.columns) == [_ES, _AAPL]
    # latest row: ES change +5, AAPL change +5 → equal split, summing to 1.0
    assert weights.iloc[-1].to_numpy() == pytest.approx([0.5, 0.5])


def test_equal_weight_strategy_is_accepted_for_a_continuous_root() -> None:
    bundle = _bundle("equal_weight_strategy", futures=("ES",))
    weights = bundle.compute_weights(_window())
    assert (weights.to_numpy() == 0.5).all()


def test_absolute_price_strategy_allowed_without_continuous_roots() -> None:
    """Native equities never re-base, so the same absolute-level strategy is fine when no
    continuous root is declared — the guard must not over-reject."""
    bundle = _bundle("price_proportional_strategy", futures=())
    weights = bundle.compute_weights(_window())  # no raise
    assert weights.iloc[-1].sum() == pytest.approx(1.0)


def test_difference_weights_are_byte_stable_across_a_rebase() -> None:
    """The integration-level property: a fully-built difference bundle reproduces its
    allocation exactly when the continuous-root price column is re-based — live ≡ research
    across the roll's additive shift."""
    bundle = _bundle("momentum_strategy", futures=("ES",))
    window = _window()
    base = bundle.compute_weights(window)

    shifted_close = window.array("Close").copy()
    shifted_close[_ES] = shifted_close[_ES] + 137.0  # a roll's uniform additive re-base of ES
    rebased = bundle.compute_weights(MarketDataBundle({"Close": shifted_close}))

    assert np.allclose(base.to_numpy(), rebased.to_numpy(), atol=1e-9, equal_nan=True)
