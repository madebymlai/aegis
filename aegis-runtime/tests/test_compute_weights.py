import pandas as pd
import pytest
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
from aegis_runtime.drift_band import DriftBand


def _index(n: int) -> pd.DatetimeIndex:
    return pd.date_range("2024-01-01", periods=n, freq="D")


def _id(value: str) -> InstrumentId:
    return InstrumentId.from_str(value)


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
        instrument_bands={
            instrument_id: DriftBand.symmetric(0.0) for instrument_id in contract.instrument_ids
        },
        gross_cap=1.0,
        net_cap=1.0,
        direction=direction,
    )
    manifest = BundleManifest(
        run_id="r",
        role="best",
        candidate_key="k",
        component_source_hashes={},
        instrument_ids=contract.instrument_ids,
    )
    return ExecutionBundle(contract=contract, manifest=manifest, plan=plan)


def _eur_contract(
    instrument_ids: tuple[InstrumentId, ...] = (_id("AAPL.NASDAQ"), _id("MSFT.NASDAQ")),
    lookback_bars=0,
) -> DataContract:
    return DataContract(
        instrument_ids=instrument_ids,
        required_arrays=("Close",),
        base_currency="EUR",
        timeframe="1D",
        missing_index=MissingIndexPolicy.DROP,
        lookback_bars=lookback_bars,
    )


def test_compute_weights_equal_weight_fidelity_through_indicator_path() -> None:
    idx = _index(3)
    instrument_ids = (_id("AAPL.NASDAQ"), _id("MSFT.NASDAQ"))
    close = pd.DataFrame(
        {instrument_ids[0]: [10.0, 11.0, 12.0], instrument_ids[1]: [20.0, 21.0, 22.0]},
        index=idx,
    )
    bundle = _bundle(
        "equal_weight_strategy",
        contract=_eur_contract(),
        indicators=(_spec("echo_indicator", "indicators", "echo"),),
    )

    weights = bundle.compute_weights(MarketDataBundle({"Close": close}))

    assert list(weights.columns) == list(instrument_ids)
    assert weights.index.equals(idx)
    assert (weights.to_numpy() == 0.5).all()


def test_compute_weights_keys_output_by_native_instrument_id() -> None:
    idx = _index(3)
    instrument_ids = (_id("AAPL.NASDAQ"), _id("MSFT.NASDAQ"))
    close = pd.DataFrame(
        {instrument_ids[0]: [10.0, 11.0, 12.0], instrument_ids[1]: [20.0, 21.0, 22.0]},
        index=idx,
    )
    bundle = _bundle(
        "label_select_strategy",
        contract=_eur_contract(instrument_ids=instrument_ids),
    )

    weights = bundle.compute_weights(MarketDataBundle({"Close": close}))

    assert list(weights.columns) == list(instrument_ids)
    assert weights.columns.name == "instrument_id"
    assert weights[instrument_ids[0]].tolist() == [1.0, 1.0, 1.0]
    assert weights[instrument_ids[1]].tolist() == [0.0, 0.0, 0.0]


def test_compute_weights_raises_when_window_shorter_than_lookback_bars() -> None:
    idx = _index(3)
    instrument_ids = (_id("AAPL.NASDAQ"), _id("MSFT.NASDAQ"))
    close = pd.DataFrame(
        {instrument_ids[0]: [1.0, 1.0, 1.0], instrument_ids[1]: [1.0, 1.0, 1.0]},
        index=idx,
    )
    bundle = _bundle("equal_weight_strategy", contract=_eur_contract(lookback_bars=5))

    with pytest.raises(ValueError, match="at least 5 lookback bars"):
        bundle.compute_weights(MarketDataBundle({"Close": close}))


def test_compute_weights_raises_when_latest_weight_row_is_non_finite() -> None:
    idx = _index(3)
    instrument_ids = (_id("AAPL.NASDAQ"), _id("MSFT.NASDAQ"))
    close = pd.DataFrame(
        {instrument_ids[0]: [1.0, 1.0, 1.0], instrument_ids[1]: [1.0, 1.0, 1.0]},
        index=idx,
    )
    bundle = _bundle("nan_tail_strategy", contract=_eur_contract())

    with pytest.raises(ValueError, match="latest weight row contains NaN"):
        bundle.compute_weights(MarketDataBundle({"Close": close}))
