"""Unit tests for locked-run behavior in the pipeline setup stage.

A Run Config carrying a top-level ``lock: {run_id, candidate_id}`` reproduces one prior
Candidate: setup resolves every Component's params from that Candidate and performs no
optimization (a single pinned Candidate, zero free params).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from research.aegis_research.candidates.identity import (
    CANDIDATE_STORE_PROVENANCE_SCHEMA_VERSION,
    candidate_store_path,
)
from research.aegis_research.candidates.models import CandidateSet
from research.aegis_research.candidates.records import candidate_rows_from_result
from research.aegis_research.candidates.store import CandidateStore
from research.aegis_research.configuration import resolve_run_config
from research.aegis_research.optimization.param_namespace import FIXED_CANDIDATE_PARAM
from research.aegis_research.optimization.ranking import (
    EvaluatedCandidate,
    OptimizationResult,
)
from research.aegis_research.run._stages.setup import run_pipeline_setup
from research.aegis_research.run.identity import RunId
from tests.support.research.aegis_research.component_fixtures import (
    write_indicator_component,
)
from tests.support.research.aegis_research.factories import (
    make_run_data,
    make_selection_identity,
)
from tests.support.research.aegis_research.market_data_fixtures import (
    native_data_config_payload,
)
from tests.support.research.aegis_research.run_config_fixtures import (
    build_resolved_run_config,
)

_DATA_IDENTITY = {
    "schema_version": "candidate_data_identity.v3",
    "requested_instrument_ids": ["SYN.XNAS"],
    "instrument_ids": ["SYN.XNAS"],
    "timeframe": "1D",
}


def _run_data() -> Any:
    import pandas as pd

    frame = pd.DataFrame({0: [float(i) for i in range(120)]})
    return make_run_data(close=frame, open_=frame)


def _locked_raw_config(candidate_key: str) -> dict[str, Any]:
    from research.aegis_research.configuration import CONFIG_SCHEMA_VERSION

    return {
        "schema_version": CONFIG_SCHEMA_VERSION,
        "name": "locked_run_fixture",
        "data": native_data_config_payload(instruments=["SYN.XNAS"], end="2024-04-30"),
        "portfolio": {"direction": "longonly"},
        "strategy": {"id": "demo.strategy"},
        "indicators": [{"id": "demo.returns"}],
        "ranking": {"metric": "total_return"},
        "optimization": {
            "search": "grid",
            "observation_block_bars": 20,
        },
        "lock": {"run_id": "run-a", "candidate_id": candidate_key},
    }


def _seed_candidate_store(config: Any) -> str:
    store_path = candidate_store_path(config)
    candidate = EvaluatedCandidate(
        params={},
        score=0.25,
        observation_block_metrics={"block-000": {"total_return": 0.25}},
        metrics={"total_return": 0.25},
    )
    selection_identity = make_selection_identity()
    rows = candidate_rows_from_result(
        OptimizationResult(best=candidate, median=candidate, worst=candidate),
        source_identity=_source_evidence(),
        data_identity=_DATA_IDENTITY,
        selection_identity=selection_identity,
        book_settings={"target_exposure_cap": 1.0},
        store_namespace={"kind": "local_sqlite", "name": "default"},
    )
    candidate_key = rows[0]["candidate_key"]
    with CandidateStore(store_path) as store:
        store.commit_candidates(
            CandidateSet.create(
                run_id=RunId("run-a"),
                candidates=rows,
                provenance={
                    "schema_version": CANDIDATE_STORE_PROVENANCE_SCHEMA_VERSION,
                    "run_id": "run-a",
                    "source": _source_evidence(),
                    "selection_identity": selection_identity,
                },
            )
        )
    return candidate_key


def _source_evidence() -> dict[str, Any]:
    return {
        "schema_version": "component_optimization_source.v2",
        "source": "component",
        "strategy": {
            "family": "strategies",
            "slot": "strategy",
            "id": "demo.strategy",
            "version": "1.0.0",
            "fixed_params": {},
            "param_keys": {},
        },
        "indicators": [
            {
                "family": "indicators",
                "slot": "demo.returns",
                "id": "demo.returns",
                "version": "1.0.0",
                "fixed_params": {},
                "param_keys": {},
            }
        ],
    }


def _resolved_locked_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)
    base = build_resolved_run_config(tmp_path)
    candidate_key = _seed_candidate_store(base.config)
    raw = _locked_raw_config(candidate_key)
    return resolve_run_config(raw, component_registry=base.component_registry)


def test_locked_setup_resolves_every_component_from_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Locked setup resolves every Component's params from the candidate store.

    Observe Lock application through the optimization source's evidence
    (param_mode == "locked") instead of reading a relayed copy.
    """
    resolved = _resolved_locked_config(tmp_path, monkeypatch)
    config = resolved.config
    result = run_pipeline_setup(
        config=config,
        component_registry=resolved.component_registry,
        run_data=_run_data(),
    )

    evidence = result.optimization_source.evidence
    assert evidence["strategy"]["param_mode"] == "locked"
    assert all(indicator["param_mode"] == "locked" for indicator in evidence["indicators"])
    assert evidence["strategy"]["id"] == "demo.strategy"
    assert any(indicator["id"] == "demo.returns" for indicator in evidence["indicators"])


def test_locked_setup_performs_no_optimization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    resolved = _resolved_locked_config(tmp_path, monkeypatch)
    config = resolved.config
    result = run_pipeline_setup(
        config=config,
        component_registry=resolved.component_registry,
        run_data=_run_data(),
    )

    # A locked run pins a single Candidate: no free parameters remain to sweep.
    assert list(result.optimization_source.params) == [FIXED_CANDIDATE_PARAM]


def _write_parameterized_strategy(path: Path) -> None:
    """A strategy whose manifest declares a single ``threshold`` param (override target)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# %% component overview\n"
        "# Parameterized strategy fixture for lock-overlay tests.\n"
        "# Source: synthetic Close data supplied by the test fixture.\n"
        "\n# %% define component metadata\n"
        "import numpy as np\n"
        "import pandas as pd\n"
        "from vectorbtpro import vbt\n"
        "COMPONENT_MANIFEST = {"
        "'family': 'strategies', 'id': 'demo.strategy', 'version': '1.0.0', "
        "'input_names': ['Close'], 'param_names': ['threshold'], "
        "'output_name': 'active', 'owns_portfolio': False, "
        "'defaults': {'threshold': 1.0}, "
        "}\n"
        "\n# %% param space\n"
        "def param_space():\n"
        '    """Return the searchable threshold param space."""\n'
        "    return {'threshold': vbt.Param([1.0, 2.0])}\n"
        "\n# %% main compute\n"
        "def run(inputs, *, threshold=1.0):\n"
        '    """Emit a deterministic active allocation frame for fixture runs."""\n'
        "    close = inputs.data.array('Close')\n"
        "    return close.gt(close.shift(1)).fillna(False).astype(object)\n"
        "\n# %% wide compute\n"
        "def run(inputs, *, n_candidates, **param_lists):\n"
        '    """Return wide strategy output."""\n'
        "    close = inputs.data.array('Close')\n"
        "    T, S = close.shape\n"
        "    return np.full((T, n_candidates * S), np.nan)\n"
    )


def _parameterized_source_evidence() -> dict[str, Any]:
    """Provenance whose strategy runtime pins ``threshold`` as a fixed candidate param."""
    evidence = _source_evidence()
    evidence["strategy"]["fixed_params"] = {"threshold": 1.0}
    return evidence


def _seed_parameterized_candidate(config: Any) -> str:
    store_path = candidate_store_path(config)
    candidate = EvaluatedCandidate(
        params={},
        score=0.25,
        observation_block_metrics={"block-000": {"total_return": 0.25}},
        metrics={"total_return": 0.25},
    )
    selection_identity = make_selection_identity()
    rows = candidate_rows_from_result(
        OptimizationResult(best=candidate, median=candidate, worst=candidate),
        source_identity=_parameterized_source_evidence(),
        data_identity=_DATA_IDENTITY,
        selection_identity=selection_identity,
        book_settings={"target_exposure_cap": 1.0},
        store_namespace={"kind": "local_sqlite", "name": "default"},
    )
    candidate_key = rows[0]["candidate_key"]
    with CandidateStore(store_path) as store:
        store.commit_candidates(
            CandidateSet.create(
                run_id=RunId("run-a"),
                candidates=rows,
                provenance={
                    "schema_version": CANDIDATE_STORE_PROVENANCE_SCHEMA_VERSION,
                    "run_id": "run-a",
                    "source": _parameterized_source_evidence(),
                    "selection_identity": selection_identity,
                },
            )
        )
    return candidate_key


def _resolved_locked_overlay_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """A locked config whose strategy also declares an (overridden) ``threshold`` param."""
    from research.aegis_research.component_registry import discover_component_registry

    monkeypatch.chdir(tmp_path)
    root = tmp_path / "research" / "components"
    write_indicator_component(root / "indicators" / "returns.py")
    _write_parameterized_strategy(root / "strategies" / "strategy.py")
    component_registry = discover_component_registry(root=root, repo_root=tmp_path)

    base = build_resolved_run_config(tmp_path)
    candidate_key = _seed_parameterized_candidate(base.config)
    raw = _locked_raw_config(candidate_key)
    raw["strategy"] = {"id": "demo.strategy", "params": {"threshold": 2.0}}
    return resolve_run_config(raw, component_registry=component_registry)


def test_locked_setup_applies_locked_params_over_authored_params(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Lock-wins (ADR-0006): the locked Candidate pins threshold=1.0 despite the config.
    resolved = _resolved_locked_overlay_config(tmp_path, monkeypatch)
    config = resolved.config
    result = run_pipeline_setup(
        config=config,
        component_registry=resolved.component_registry,
        run_data=_run_data(),
    )

    assert resolved.config.strategy.params == {"threshold": 2.0}
    assert result.optimization_source.evidence["strategy"]["param_mode"] == "locked"
