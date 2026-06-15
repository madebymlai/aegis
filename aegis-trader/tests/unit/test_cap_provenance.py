"""Cap provenance (Wave B / B13) — a Book Config's operator-entered exposure
caps must never exceed what research validated for the backing bundles.

The manifest-grounded source of the validated caps is each sleeve's
``ExecutionBundle`` plan (gross_cap / net_cap) — *not* a second operator field
(the old self-referential ``research_validated_cap`` compared config to itself).
``check_cap_provenance`` is the load-time gate; it is pure (no Nautilus, no I/O).
"""

from __future__ import annotations

import pytest

from aegis_runtime import (
    BundleManifest,
    ComponentSpec,
    DataContract,
    ExecutionBundle,
    LockedExecutionPlan,
)

from aegis_trader.bundles.provenance import (
    CapProvenanceError,
    check_cap_provenance,
)
from aegis_trader.domain.book_config import BookConfig, SleeveConfig
from aegis_trader.domain.types import SleeveName

_FIGI = "BBG000B9XRY4"


def _bundle(*, gross_cap: float, net_cap: float | None = None) -> ExecutionBundle:
    contract = DataContract(
        figis=(_FIGI,), required_arrays=("Close",), base_currency="EUR",
        required_fx_currencies=(), timeframe="1D", lookback_bars=1,
    )
    manifest = BundleManifest(
        run_id="r", role="x", candidate_key="k",
        component_source_hashes={}, figis=(_FIGI,),
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


def _book(**caps) -> BookConfig:
    return BookConfig(
        sleeves=(SleeveConfig(name=SleeveName("trend"), wheel_filename="trend.whl", risk_share=1.0),),
        **caps,
    )


def test_book_gross_cap_above_bundle_is_rejected():
    """gross_cap looser than the bundle's validated gross → rejected at load."""
    bundles = {SleeveName("trend"): _bundle(gross_cap=0.30)}
    book = _book(gross_cap=0.50)

    with pytest.raises(CapProvenanceError, match="gross"):
        check_cap_provenance(book, bundles)


def test_book_net_cap_above_bundle_is_rejected():
    """net_cap looser than the bundle's validated net → rejected."""
    bundles = {SleeveName("trend"): _bundle(gross_cap=1.0, net_cap=0.10)}
    book = _book(net_cap=0.20)

    with pytest.raises(CapProvenanceError, match="net"):
        check_cap_provenance(book, bundles)


def test_book_per_name_cap_above_bundle_gross_is_rejected():
    """The bundle has no per-name research cap, so a single name's exposure is
    ceilinged by the validated gross — repurposes research_validated_cap (a4)."""
    bundles = {SleeveName("trend"): _bundle(gross_cap=0.15)}
    book = _book(per_name_cap=0.20)

    with pytest.raises(CapProvenanceError, match="per_name_cap"):
        check_cap_provenance(book, bundles)


def test_caps_within_bundle_pass():
    """All caps at or under the validated ceilings → no error."""
    bundles = {SleeveName("trend"): _bundle(gross_cap=0.30, net_cap=0.20)}
    book = _book(gross_cap=0.30, net_cap=0.20, per_name_cap=0.10)

    check_cap_provenance(book, bundles)  # does not raise


def test_no_book_caps_pass():
    """A book that sets no caps grounds nothing — vacuously valid."""
    bundles = {SleeveName("trend"): _bundle(gross_cap=0.30)}

    check_cap_provenance(_book(), bundles)  # does not raise


def test_missing_bundle_for_sleeve_fails_closed():
    """A sleeve with no loaded bundle cannot be grounded → rejected."""
    with pytest.raises(CapProvenanceError, match="no bundle loaded"):
        check_cap_provenance(_book(gross_cap=0.10), bundles={})
