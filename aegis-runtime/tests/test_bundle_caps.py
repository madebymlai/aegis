"""ExecutionBundle exposes its LockedExecutionPlan's exposure caps read-only.

The Trader's cap-provenance check (aegis-trader Wave B / B13) asserts a Book
Config's gross/net caps never exceed what research validated — and the only
manifest-grounded source of those validated caps is the bundle's
``LockedExecutionPlan``.  These accessors are that public seam.
"""

from __future__ import annotations

from aegis_runtime import (
    BundleManifest,
    ComponentSpec,
    DataContract,
    DriftBand,
    ExecutionBundle,
    LockedExecutionPlan,
)
from nautilus_trader.model.identifiers import InstrumentId

_INSTRUMENT_ID = InstrumentId.from_str("AAPL.NASDAQ")


def _bundle(*, gross_cap: float, net_cap: float | None) -> ExecutionBundle:
    contract = DataContract(
        instrument_ids=(_INSTRUMENT_ID,), required_arrays=("Close",), base_currency="EUR",
        timeframe="1D", lookback_bars=1,
    )
    manifest = BundleManifest(
        run_id="r", role="x", candidate_key="k",
        component_source_hashes={}, instrument_ids=(_INSTRUMENT_ID,),
    )
    plan = LockedExecutionPlan(
        strategy=ComponentSpec(
            family="strategy", component_id="s", module="m",
            input_names=(), output_names=(), params={},
        ),
        indicators=(),
        instrument_bands={_INSTRUMENT_ID: DriftBand.symmetric(0.0)},
        gross_cap=gross_cap,
        net_cap=net_cap,
        direction="both",
    )
    return ExecutionBundle(contract=contract, manifest=manifest, plan=plan)


def test_gross_cap_exposes_plan_gross_cap():
    assert _bundle(gross_cap=0.30, net_cap=0.10).gross_cap == 0.30


def test_net_cap_exposes_plan_net_cap():
    assert _bundle(gross_cap=0.30, net_cap=0.10).net_cap == 0.10


def test_net_cap_may_be_absent():
    assert _bundle(gross_cap=0.30, net_cap=None).net_cap is None
