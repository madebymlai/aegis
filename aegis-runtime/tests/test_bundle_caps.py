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
    ExecutionBundle,
    ListedRef,
    LockedExecutionPlan,
)

_FIGI = "BBG000B9XRY4"
_REF = ListedRef(_FIGI)


def _bundle(*, gross_cap: float, net_cap: float | None) -> ExecutionBundle:
    contract = DataContract(
        refs=(_REF,), required_arrays=("Close",), base_currency="EUR",
        required_fx_currencies=(), timeframe="1D", lookback_bars=1,
    )
    manifest = BundleManifest(
        run_id="r", role="x", candidate_key="k",
        component_source_hashes={}, refs=(_REF,),
    )
    plan = LockedExecutionPlan(
        strategy=ComponentSpec(
            family="strategy", component_id="s", module="m",
            input_names=(), output_names=(), params={},
        ),
        indicators=(), gross_cap=gross_cap, net_cap=net_cap, direction="both",
        symbols=(_FIGI,), currency_by_symbol={_FIGI: "EUR"},
    )
    return ExecutionBundle(contract=contract, manifest=manifest, plan=plan)


def test_gross_cap_exposes_plan_gross_cap():
    assert _bundle(gross_cap=0.30, net_cap=0.10).gross_cap == 0.30


def test_net_cap_exposes_plan_net_cap():
    assert _bundle(gross_cap=0.30, net_cap=0.10).net_cap == 0.10


def test_net_cap_may_be_absent():
    assert _bundle(gross_cap=0.30, net_cap=None).net_cap is None


def test_symbols_expose_plan_symbols():
    assert _bundle(gross_cap=0.30, net_cap=None).symbols == (_FIGI,)


def test_currency_by_symbol_exposes_plan_currency_by_symbol():
    assert _bundle(gross_cap=0.30, net_cap=None).currency_by_symbol == {_FIGI: "EUR"}
