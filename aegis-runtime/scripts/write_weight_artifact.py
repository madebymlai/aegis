#!/usr/bin/env python3
"""Write deterministic bytes for the locked weight-decision path."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd
from nautilus_trader.model.identifiers import InstrumentId

from aegis_runtime import (
    BundleManifest,
    ComponentSpec,
    DataContract,
    DriftBand,
    ExecutionBundle,
    LockedExecutionPlan,
    MarketDataBundle,
    MissingIndexPolicy,
)
from aegis_runtime.domain.currency import CurrencyConversion

_COMPONENTS = Path(__file__).parents[1] / "tests" / "_components"
_AAPL = InstrumentId.from_str("AAPL.NASDAQ")
_MSFT = InstrumentId.from_str("MSFT.NASDAQ")


def _bundle() -> ExecutionBundle:
    instrument_ids = (_AAPL, _MSFT)
    contract = DataContract(
        instrument_ids=instrument_ids,
        required_arrays=("Close",),
        base_currency="EUR",
        timeframe="1D",
        missing_index=MissingIndexPolicy.DROP,
        lookback_bars=0,
    )
    strategy = ComponentSpec(
        family="strategies",
        component_id="byte-safety.price-proportional",
        module="price_proportional_strategy",
        input_names=("Close",),
        output_names=("target_weights",),
        params={},
    )
    plan = LockedExecutionPlan(
        strategy=strategy,
        indicators=(),
        instrument_bands={
            instrument_id: DriftBand.symmetric(0.0) for instrument_id in instrument_ids
        },
        direction="longonly",
    )
    manifest = BundleManifest(
        run_id="byte-safety",
        role="best",
        candidate_key="deterministic-fixture",
        component_source_hashes={},
        instrument_ids=instrument_ids,
    )
    return ExecutionBundle(contract=contract, manifest=manifest, plan=plan)


def _weights() -> pd.DataFrame:
    index = pd.date_range("2020-01-01", periods=3, tz="UTC")
    native_close = pd.DataFrame(
        {_AAPL: [10.0, 11.0, 12.0], _MSFT: [20.0, 21.0, 22.0]},
        index=index,
    )
    conversion = CurrencyConversion(
        rate_by_instrument={_AAPL: pd.Series([0.9, 1.0, 1.1], index=index)},
        currency_by_instrument_id={_AAPL: "USD", _MSFT: "EUR"},
    )
    return _bundle().compute_weights(
        MarketDataBundle({"Close": native_close}),
        currency_conversion=conversion,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path, help="artifact path to write")
    args = parser.parse_args()

    sys.path.insert(0, str(_COMPONENTS))
    artifact = _weights().to_csv(float_format="%.17g", lineterminator="\n").encode()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(artifact)


if __name__ == "__main__":
    main()
