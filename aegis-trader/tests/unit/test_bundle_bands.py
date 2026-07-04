from __future__ import annotations

import pytest

from aegis_runtime import (
    BundleManifest,
    ComponentSpec,
    DataContract,
    DriftBand,
    ExecutionBundle,
    InstrumentId,
    LockedExecutionPlan,
    MissingIndexPolicy,
)

from aegis_trader.bundles.bands import InstrumentBandError, build_instrument_bands
from aegis_trader.domain.types import SleeveName


def _id(value: str) -> InstrumentId:
    return InstrumentId.from_str(value)


def _bundle(instrument_id: InstrumentId, band: DriftBand) -> ExecutionBundle:
    contract = DataContract(
        instrument_ids=(instrument_id,),
        required_arrays=("Close",),
        base_currency="EUR",
        timeframe="1D",
        missing_index=MissingIndexPolicy.DROP,
        lookback_bars=1,
    )
    manifest = BundleManifest(
        run_id="r",
        role="best",
        candidate_key="k",
        component_source_hashes={},
        instrument_ids=(instrument_id,),
    )
    plan = LockedExecutionPlan(
        strategy=ComponentSpec(
            family="strategy",
            component_id="s",
            module="m",
            input_names=(),
            output_names=(),
            params={},
        ),
        indicators=(),
        instrument_bands={instrument_id: band},
        gross_cap=1.0,
        net_cap=None,
        direction="both",
    )
    return ExecutionBundle(contract=contract, manifest=manifest, plan=plan)


def test_build_instrument_bands_merges_disjoint_sleeves() -> None:
    aapl = _id("AAPL.NASDAQ")
    msft = _id("MSFT.NASDAQ")

    bundle_bands = build_instrument_bands(
        {
            SleeveName("trend"): _bundle(aapl, DriftBand(up=0.10, down=0.20)),
            SleeveName("carry"): _bundle(msft, DriftBand(up=0.0, down=0.0)),
        }
    )

    assert bundle_bands.bands[aapl] == DriftBand(up=0.10, down=0.20)
    assert bundle_bands.bands[msft] == DriftBand(up=0.0, down=0.0)
    # Ownership feeds the rebalancer's sleeve-scale band scaling (aegis-rd-reyj):
    # each band gates at its owning sleeve's allocator multiplier.
    assert bundle_bands.owner_by_instrument[aapl] == SleeveName("trend")
    assert bundle_bands.owner_by_instrument[msft] == SleeveName("carry")


def test_build_instrument_bands_rejects_overlapping_sleeves() -> None:
    aapl = _id("AAPL.NASDAQ")

    with pytest.raises(InstrumentBandError, match="AAPL.NASDAQ.*carry.*trend"):
        build_instrument_bands(
            {
                SleeveName("trend"): _bundle(aapl, DriftBand(up=0.10, down=0.20)),
                SleeveName("carry"): _bundle(aapl, DriftBand(up=0.0, down=0.0)),
            }
        )
