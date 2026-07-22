from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from aegis_runtime import ComponentSpec

from research.aegis_research.execution_bundle import assemble_bundle
from research.aegis_research.optimization.candidate_evidence import (
    candidate_rows_from_result,
)
from research.aegis_research.optimization.candidate_store import CandidateStore
from research.aegis_research.optimization.candidate_store_identity import (
    CANDIDATE_STORE_PROVENANCE_SCHEMA_VERSION,
)
from research.aegis_research.optimization.ranking import (
    EvaluatedCandidate,
    OptimizationResult,
)
from tests.support.research.aegis_research.factories import make_selection_identity

_RUN_ID = "export-fixture-run"


def test_locked_fixture_pins_exported_component_hashes_and_specs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = _locked_workspace(tmp_path)
    monkeypatch.chdir(workspace)

    artifact = assemble_bundle(workspace / "config.yaml")

    assert artifact.manifest.component_source_hashes == {
        "indicators/tests.export_indicator": (
            "ad97a38f4264529d2f0c805694c98c4b0a4e26dfc60268b64f5001fc6b54ae1f"
        ),
        "strategies/tests.export_strategy": (
            "efc5b220dd2cbbd00a194146135057ea0d9334863695278054dfbab4ca5ec93d"
        ),
    }
    assert artifact.plan.indicators == (
        ComponentSpec(
            family="indicators",
            component_id="tests.export_indicator",
            module="aegis_exec_tests_export_strategy_cand_991.indicator_0",
            input_names=("Close",),
            output_names=("signal",),
            params={"window": 5},
        ),
    )
    assert artifact.plan.strategy == ComponentSpec(
        family="strategies",
        component_id="tests.export_strategy",
        module="aegis_exec_tests_export_strategy_cand_991.strategy",
        input_names=("Close",),
        output_names=(),
        params={"holding_period": 2},
    )


def test_export_rejects_module_level_research_import(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = _locked_workspace(tmp_path)
    strategy_path = workspace / "research" / "components" / "strategies" / "export_strategy.py"
    strategy_path.write_text(
        "from vectorbtpro import vbt\n" + strategy_path.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    monkeypatch.chdir(workspace)

    with pytest.raises(
        ValueError,
        match=r"research-only dependency at module level.*Move the import inside param_space",
    ):
        assemble_bundle(workspace / "config.yaml")


def test_export_requires_every_component_to_declare_warmup_bars(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = _locked_workspace(tmp_path)
    strategy_path = workspace / "research" / "components" / "strategies" / "export_strategy.py"
    source = strategy_path.read_text(encoding="utf-8")
    strategy_path.write_text(
        source.replace(
            "# %% lookback\ndef lookback(**params):\n"
            '    """Return the strategy holding-period warmup."""\n'
            '    return int(params["holding_period"])\n\n\n',
            "",
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(workspace)

    with pytest.raises(
        ValueError,
        match=r"strategy 'tests\.export_strategy' lacks lookback\(\) entrypoint; "
        r"every bundled component must declare its warmup bars",
    ):
        assemble_bundle(workspace / "config.yaml")


def _locked_workspace(tmp_path: Path) -> Path:
    fixture_root = Path(__file__).parents[4] / "tests" / "fixtures" / "execution_bundle"
    workspace = tmp_path / "workspace"
    shutil.copytree(fixture_root, workspace)
    _seed_candidate_store(
        workspace / "runs" / "export_registry_seam" / ".candidate_store" / "candidates.sqlite3"
    )
    return workspace


def _seed_candidate_store(store_path: Path) -> None:
    candidate = EvaluatedCandidate(
        params={},
        score=1.0,
        observation_block_metrics={"block-000": {"sharpe_ratio": 1.0}},
        metrics={"sharpe_ratio": 1.0},
    )
    result = OptimizationResult(best=candidate, median=candidate, worst=candidate)
    selection_identity = make_selection_identity()
    candidate_rows = candidate_rows_from_result(
        result,
        source_identity={
            "source": "component",
            "id": "tests.export_strategy",
            "source_hash": "fixture-source",
        },
        data_identity={"schema_version": "candidate_data_identity.fixture"},
        selection_identity=selection_identity,
        book_settings={"net_cap": 1.0},
        store_namespace={"kind": "local_sqlite", "name": "default"},
    )
    with CandidateStore(store_path) as store:
        store.insert_completed_run(
            run_id=_RUN_ID,
            candidate_rows=candidate_rows,
            provenance={
                "schema_version": CANDIDATE_STORE_PROVENANCE_SCHEMA_VERSION,
                "run_id": _RUN_ID,
                "source": _source_evidence(),
                "selection_identity": selection_identity,
            },
        )


def _source_evidence() -> dict[str, object]:
    return {
        "schema_version": "component_optimization_source.v2",
        "source": "component",
        "strategy": {
            "family": "strategies",
            "slot": "strategy",
            "id": "tests.export_strategy",
            "version": "1.0.0",
            "fixed_params": {"holding_period": 2},
            "param_keys": {},
        },
        "indicators": [
            {
                "family": "indicators",
                "slot": "tests.export_indicator",
                "id": "tests.export_indicator",
                "version": "1.0.0",
                "fixed_params": {"window": 5},
                "param_keys": {},
            }
        ],
    }
