import pandas as pd
import pytest

from aegis_runtime.bundle import (
    BundleManifest,
    ComponentSpec,
    DataContract,
    ExecutionBundle,
    LockedExecutionPlan,
    MarketDataBundle,
)


def _index(n: int) -> pd.DatetimeIndex:
    return pd.date_range("2024-01-01", periods=n, freq="D")


def _spec(module: str, family: str, output: str) -> ComponentSpec:
    return ComponentSpec(
        family=family,
        component_id=f"test.{module}",
        module=module,
        input_names=("Close",),
        output_names=(output,),
        params={},
    )


def _bundle(
    strategy_module: str,
    *,
    contract: DataContract,
    indicators: tuple[ComponentSpec, ...] = (),
    direction: str = "longonly",
) -> ExecutionBundle:
    plan = LockedExecutionPlan(
        strategy=_spec(strategy_module, "strategies", "target_weights"),
        indicators=indicators,
        gross_cap=1.0,
        net_cap=1.0,
        direction=direction,
    )
    manifest = BundleManifest(run_id="r", role="best", candidate_key="k", component_source_hashes={})
    return ExecutionBundle(contract=contract, manifest=manifest, plan=plan)


def _eur_contract(symbols=("A", "B"), lookback_bars=0) -> DataContract:
    return DataContract(
        symbols=symbols,
        required_arrays=("Close",),
        base_currency="EUR",
        required_fx_currencies=(),
        currency_by_symbol={s: "EUR" for s in symbols},
        timeframe="1D",
        lookback_bars=lookback_bars,
    )


def test_compute_weights_equal_weight_fidelity_through_indicator_path() -> None:
    idx = _index(3)
    close = pd.DataFrame({"A": [10.0, 11.0, 12.0], "B": [20.0, 21.0, 22.0]}, index=idx)
    bundle = _bundle(
        "equal_weight_strategy",
        contract=_eur_contract(),
        indicators=(_spec("echo_indicator", "indicators", "echo"),),
    )

    weights = bundle.compute_weights(MarketDataBundle({"Close": close}))

    assert list(weights.columns) == ["A", "B"]
    assert weights.index.equals(idx)
    assert (weights.to_numpy() == 0.5).all()


def test_compute_weights_converts_foreign_prices_before_the_strategy_sees_them() -> None:
    idx = _index(2)
    # A quoted in USD, B in EUR (base). EURUSD = 1.25 => A_eur = A_usd / 1.25.
    close = pd.DataFrame({"A": [100.0, 125.0], "B": [20.0, 20.0]}, index=idx)
    contract = DataContract(
        symbols=("A", "B"),
        required_arrays=("Close",),
        base_currency="EUR",
        required_fx_currencies=("USD",),
        currency_by_symbol={"A": "USD", "B": "EUR"},
        timeframe="1D",
    )
    bundle = _bundle("price_proportional_strategy", contract=contract)

    weights = bundle.compute_weights(
        MarketDataBundle({"Close": close}),
        fx_series={"USD": pd.Series([1.25, 1.25], index=idx)},
    )

    # Converted closes: A=[80,100], B=[20,20]; row sums [100,120].
    # wA reflects CONVERTED prices (0.80), not native (which would be 100/120≈0.833).
    assert weights["A"].tolist() == pytest.approx([80 / 100, 100 / 120])
    assert weights["B"].tolist() == pytest.approx([20 / 100, 20 / 120])


def test_compute_weights_raises_when_window_shorter_than_lookback_bars() -> None:
    idx = _index(3)
    close = pd.DataFrame({"A": [1.0, 1.0, 1.0], "B": [1.0, 1.0, 1.0]}, index=idx)
    bundle = _bundle("equal_weight_strategy", contract=_eur_contract(lookback_bars=5))

    with pytest.raises(ValueError, match="at least 5 lookback bars"):
        bundle.compute_weights(MarketDataBundle({"Close": close}))


def test_compute_weights_raises_when_latest_weight_row_is_non_finite() -> None:
    idx = _index(3)
    close = pd.DataFrame({"A": [1.0, 1.0, 1.0], "B": [1.0, 1.0, 1.0]}, index=idx)
    bundle = _bundle("nan_tail_strategy", contract=_eur_contract())

    with pytest.raises(ValueError, match="latest weight row contains NaN"):
        bundle.compute_weights(MarketDataBundle({"Close": close}))


def test_compute_weights_fails_closed_when_required_fx_series_is_missing() -> None:
    idx = _index(2)
    close = pd.DataFrame({"A": [100.0, 125.0], "B": [20.0, 20.0]}, index=idx)
    contract = DataContract(
        symbols=("A", "B"),
        required_arrays=("Close",),
        base_currency="EUR",
        required_fx_currencies=("USD",),
        currency_by_symbol={"A": "USD", "B": "EUR"},
        timeframe="1D",
    )
    bundle = _bundle("price_proportional_strategy", contract=contract)

    with pytest.raises(ValueError, match=r"missing=\['USD'\]"):
        bundle.compute_weights(MarketDataBundle({"Close": close}))  # no fx_series
