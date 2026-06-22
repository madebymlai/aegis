from __future__ import annotations

from pathlib import Path

import pytest

from research.aegis_research import configuration as config_module
from research.aegis_research.component_registry import discover_component_registry
from research.aegis_research.configuration import (
    CONFIG_SCHEMA_VERSION,
    OHLCV_ARRAYS,
    ConfigValidationError,
    load_run_config,
    resolve_env_refs,
    resolve_run_config,
)
from tests.support.research.aegis_research.component_fixtures import write_indicator_component


def test_public_config_exports_only_run_config_contract() -> None:
    removed = {
        "ExperimentConfig",
        "ResolvedExperimentConfig",
        "load_experiment_config",
        "resolve_experiment_config",
        "LaneConfig",
        "ResolvedLaneConfig",
        "StrategyRunLaneConfig",
        "TrainLaneConfig",
        "TrainModelConfig",
        "LabelerConfig",
        "LANES",
    }

    for name in removed:
        assert not hasattr(config_module, name)
    assert hasattr(config_module, "RunConfig")
    assert hasattr(config_module, "OptimizationConfig")
    assert hasattr(config_module, "ResolvedRunConfig")
    assert hasattr(config_module, "load_run_config")
    assert hasattr(config_module, "resolve_run_config")


def test_resolve_rejects_non_mapping_input(tmp_path: Path) -> None:
    with pytest.raises(ConfigValidationError) as error:
        resolve_run_config(
            ["not", "a", "mapping"],  # type: ignore[arg-type]
            component_registry=_component_registry(tmp_path),
        )

    issues = error.value.issues
    assert any(issue.path == "$" and "must be a mapping" in issue.message for issue in issues)


def test_removed_entry_budget_field_fails_as_unknown_field(tmp_path: Path) -> None:
    raw = _run_config()
    raw["portfolio"] = {"entry_budget": 0.6, "gross_cap": 1.0}

    with pytest.raises(ConfigValidationError) as error:
        resolve_run_config(
            raw,
            component_registry=_component_registry(tmp_path),
        )

    paths = [issue.path for issue in error.value.issues]
    assert "portfolio.entry_budget" in paths
    entry_budget_issue = next(
        issue for issue in error.value.issues if issue.path == "portfolio.entry_budget"
    )
    assert "Unexpected keyword argument" in entry_budget_issue.message


def test_removed_target_exposure_cap_field_is_rejected(tmp_path: Path) -> None:
    raw = _run_config()
    raw["portfolio"] = {"target_exposure_cap": 0.8, "gross_cap": 1.0}

    with pytest.raises(ConfigValidationError) as error:
        resolve_run_config(
            raw,
            component_registry=_component_registry(tmp_path),
        )

    issue = next(
        issue
        for issue in error.value.issues
        if issue.path == "portfolio.target_exposure_cap"
    )
    assert "Unexpected keyword argument" in issue.message


def test_portfolio_gross_cap_validates(tmp_path: Path) -> None:
    raw = _run_config()
    raw["portfolio"] = {"gross_cap": 0.8, "direction": "longonly"}

    resolved = resolve_run_config(
        raw,
        component_registry=_component_registry(tmp_path),
    )

    assert resolved.config.portfolio.gross_cap == 0.8


def test_portfolio_gross_cap_above_one_is_accepted_as_leverage(tmp_path: Path) -> None:
    raw = _run_config()
    raw["portfolio"] = {"gross_cap": 2.0, "direction": "both"}

    resolved = resolve_run_config(
        raw,
        component_registry=_component_registry(tmp_path),
    )

    assert resolved.config.portfolio.gross_cap == 2.0
    assert resolved.config.portfolio.direction == "both"


@pytest.mark.parametrize("value", [0.0, -0.1])
def test_portfolio_gross_cap_non_positive_fails(
    tmp_path: Path,
    value: float,
) -> None:
    raw = _run_config()
    raw["portfolio"] = {"gross_cap": value}

    with pytest.raises(ConfigValidationError) as error:
        resolve_run_config(
            raw,
            component_registry=_component_registry(tmp_path),
        )

    assert "portfolio.gross_cap" in str(error.value)


def test_run_config_rejects_removed_labeler_field(tmp_path: Path) -> None:
    raw = _run_config()
    raw["labeler"] = {"id": "demo.fixlb"}

    with pytest.raises(ConfigValidationError) as error:
        resolve_run_config(
            raw,
            component_registry=_component_registry(tmp_path),
        )

    assert "labeler" in str(error.value)
    assert "Unexpected keyword argument" in str(error.value)


def test_data_arrays_single_ohlcv_resolves_effective_set(tmp_path: Path) -> None:
    resolved = resolve_run_config(
        _run_config(),
        component_registry=_component_registry(tmp_path),
    )

    assert resolved.config.data.arrays == ["OHLCV"]
    assert resolved.config.data.effective_arrays == OHLCV_ARRAYS


def test_data_arrays_mixed_shortcut_dedupes_deterministically(tmp_path: Path) -> None:
    raw = _run_config()
    raw["data"] = {
        "instruments": ["AAPL.NASDAQ"],
        "start": "2024-01-01",
        "end": "2024-02-01",
        "timeframe": "1D",
        "arrays": ["FundingRate", "OHLCV", "Close", "FundingRate"],
    }

    resolved = resolve_run_config(
        raw,
        component_registry=_component_registry(tmp_path),
    )

    assert resolved.config.data.effective_arrays == (
        "FundingRate",
        "Open",
        "High",
        "Low",
        "Close",
        "Volume",
    )


def test_data_arrays_accept_source_specific_vbt_feature_names(tmp_path: Path) -> None:
    raw = _run_config()
    raw["data"] = {
        "instruments": ["AAPL.NASDAQ"],
        "start": "2024-01-01",
        "end": "2024-02-01",
        "timeframe": "1D",
        "arrays": ["Close", "Stock Splits", "close"],
    }

    resolved = resolve_run_config(
        raw,
        component_registry=_component_registry(tmp_path),
    )

    assert resolved.config.data.effective_arrays == ("Close", "Stock Splits", "close")


def test_run_config_requires_explicit_data_arrays(tmp_path: Path) -> None:
    raw = _run_config()
    raw["data"] = {
        "instruments": ["AAPL.NASDAQ"],
        "start": "2024-01-01",
        "end": "2024-02-01",
        "timeframe": "1D",
    }

    with pytest.raises(ConfigValidationError) as error:
        resolve_run_config(
            raw,
            component_registry=_component_registry(tmp_path),
        )

    assert "data.arrays" in str(error.value)
    assert "required" in str(error.value)


def test_data_rejects_removed_source_symbols_and_provider(tmp_path: Path) -> None:
    raw = _run_config()
    raw["data"] = {
        "source": "synthetic",
        "symbols": [{"ticker": "SYN", "ccy": "EUR"}],
        "provider": "yfinance",
        "arrays": ["OHLCV"],
        "instruments": ["AAPL.NASDAQ"],
        "start": "2024-01-01",
        "end": "2024-02-01",
        "timeframe": "1D",
    }

    with pytest.raises(ConfigValidationError) as error:
        resolve_run_config(raw, component_registry=_component_registry(tmp_path))

    assert "data.source" in str(error.value)
    assert "data.symbols" in str(error.value)
    assert "data.provider" in str(error.value)
    assert "Unexpected keyword argument" in str(error.value)


def test_run_config_rejects_removed_feature_map(tmp_path: Path) -> None:
    raw = _run_config()
    raw["data"] = {
        "instruments": ["AAPL.NASDAQ"],
        "start": "2024-01-01",
        "end": "2024-02-01",
        "timeframe": "1D",
        "arrays": ["OHLCV"],
        "feature_map": {"close": "price"},
    }

    with pytest.raises(ConfigValidationError) as error:
        resolve_run_config(
            raw,
            component_registry=_component_registry(tmp_path),
        )

    assert "data.feature_map" in str(error.value)
    assert "Unexpected keyword argument" in str(error.value)


@pytest.mark.parametrize("arrays", ["OHLCV", ["Close "], [""], [1], []])
def test_run_config_rejects_invalid_data_arrays(tmp_path: Path, arrays: object) -> None:
    raw = _run_config()
    raw["data"] = {
        "instruments": ["AAPL.NASDAQ"],
        "start": "2024-01-01",
        "end": "2024-02-01",
        "timeframe": "1D",
        "arrays": arrays,
    }

    with pytest.raises(ConfigValidationError) as error:
        resolve_run_config(
            raw,
            component_registry=_component_registry(tmp_path),
        )

    assert "data.arrays" in str(error.value)


def test_legacy_train_shape_is_not_a_run_config(tmp_path: Path) -> None:
    with pytest.raises(ConfigValidationError) as error:
        resolve_run_config(
            {
                "schema_version": CONFIG_SCHEMA_VERSION,
                "name": "legacy_shape",
                "labels": {"generator": {"kind": "fixlb"}},
                "model": {"plugin_id": "aegis.sklearn_logistic"},
                "portfolio": {"gross_cap": 1.0},
            },
            component_registry=_component_registry(tmp_path),
        )

    assert "labels" in str(error.value)
    assert "model" in str(error.value)
    assert "Unexpected keyword argument" in str(error.value)


def test_load_run_config_rejects_duplicate_yaml_keys(tmp_path: Path) -> None:
    path = tmp_path / "run.yaml"
    path.write_text(
        "\n".join(
            [
                f"schema_version: {CONFIG_SCHEMA_VERSION}",
                "name: duplicate_key_test",
                "data:",
                "  instruments: [AAPL.NASDAQ]",
                "data:",
                "  instruments: [MSFT.NASDAQ]",
                "portfolio:",
                "  gross_cap: 1.0",
                "strategy: {}",
                "indicators: []",
                "",
            ]
        )
    )

    with pytest.raises(ConfigValidationError) as error:
        load_run_config(path, component_registry=_component_registry(tmp_path))

    assert "data" in str(error.value)
    assert "duplicate mapping key" in str(error.value)


def test_env_refs_are_resolved_at_runtime(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("BINANCE_API_KEY", "super-secret-token")
    resolved_kwargs = resolve_env_refs({"api_key": {"env": "BINANCE_API_KEY"}})

    assert resolved_kwargs == {"api_key": "super-secret-token"}


def test_run_rejects_candidate_grid_policy(tmp_path: Path) -> None:
    raw = _run_config()
    raw["candidate_grid"] = {"max_candidates": 100, "max_estimated_cells": 10_000, "batch_size": 25}

    with pytest.raises(ConfigValidationError) as error:
        resolve_run_config(
            raw,
            component_registry=_component_registry(tmp_path),
        )

    assert "candidate_grid" in str(error.value)
    assert "Unexpected keyword argument" in str(error.value)


def test_run_requires_native_optimization_contract(tmp_path: Path) -> None:
    raw = _run_config()
    raw.pop("optimization")

    with pytest.raises(ConfigValidationError) as error:
        resolve_run_config(
            raw,
            component_registry=_component_registry(tmp_path),
        )

    assert "optimization" in str(error.value)
    assert "fixed/non-optimized strategy runs are removed" in str(error.value)


def test_run_accepts_grid_optimization_with_nested_split(tmp_path: Path) -> None:
    raw = _run_config()
    raw["optimization"] = _optimization_block(search="grid")

    resolved = resolve_run_config(
        raw,
        component_registry=_component_registry(tmp_path),
    )

    assert resolved.config.optimization is not None
    assert resolved.config.optimization.search == "grid"
    assert resolved.config.optimization.random_subset is None
    assert resolved.config.optimization.seed is None
    assert resolved.config.optimization.execute == {}
    assert resolved.config.optimization.split.method == "from_rolling"
    assert "set_labels" not in resolved.config.optimization.split.params


def test_run_accepts_random_optimization_policy(tmp_path: Path) -> None:
    raw = _run_config()
    raw["optimization"] = _optimization_block(
        search="random",
        random_subset=5,
        seed=42,
        execute={"engine": "threadpool", "chunk_len": "auto"},
    )

    resolved = resolve_run_config(
        raw,
        component_registry=_component_registry(tmp_path),
    )

    assert resolved.config.optimization is not None
    assert resolved.config.optimization.search == "random"
    assert resolved.config.optimization.random_subset == 5
    assert resolved.config.optimization.seed == 42
    assert resolved.config.optimization.execute == {"engine": "threadpool", "chunk_len": "auto"}


def test_run_rejects_per_component_lock_reference_fields(tmp_path: Path) -> None:
    # ADR-0006 (aegis-rd-396.4): per-Component lock_id/candidate_id/run_id are gone;
    # whole-Candidate reproduction lives on the top-level lock:. These are now unknown
    # fields on a component ref.
    raw = _run_config()
    raw["strategy"] = {"id": "demo.strategy", "lock_id": "lock_strategy_best"}
    raw["indicators"] = [
        {"id": "demo.returns", "candidate_id": "cand_indicator_row", "run_id": "source-run"}
    ]

    with pytest.raises(ConfigValidationError) as error:
        resolve_run_config(
            raw,
            component_registry=_component_registry(tmp_path),
        )

    message = str(error.value)
    assert "strategy.lock_id" in message
    assert "indicators[0].candidate_id" in message
    assert "indicators[0].run_id" in message
    assert "Unexpected keyword argument" in message


def test_run_rejects_missing_strategy_consumed_indicator_output(tmp_path: Path) -> None:
    raw = _run_config()
    raw["indicators"] = []

    with pytest.raises(ConfigValidationError) as error:
        resolve_run_config(
            raw,
            component_registry=_component_registry(tmp_path),
        )

    assert "strategy.consumes_outputs" in str(error.value)
    assert "not produced" in str(error.value)


@pytest.mark.parametrize(
    ("optimization", "expected_path", "expected_message"),
    [
        (
            {
                "search": "grid",
                "split": {
                    "method": "from_rolling",
                    "params": {
                        "length": 20,
                        "split": 0.5,
                    },
                },
                "engine": "custom",
            },
            "optimization.engine",
            "Unexpected keyword argument",
        ),
        (
            {
                "search": "grid",
                "split": {
                    "method": "from_rolling",
                    "params": {
                        "length": 20,
                        "split": 0.5,
                    },
                },
                "mode": "native",
            },
            "optimization.mode",
            "Unexpected keyword argument",
        ),
        (
            {
                "search": "random",
                "split": {
                    "method": "from_rolling",
                    "params": {
                        "length": 20,
                        "split": 0.5,
                    },
                },
            },
            "optimization",
            "Value error, random_subset is required when optimization.search is 'random'",
        ),
        (
            {
                "search": "random",
                "split": {
                    "method": "from_rolling",
                    "params": {
                        "length": 20,
                        "split": 0.5,
                    },
                },
                "random_subset": 5,
            },
            "optimization",
            "Value error, seed is required when optimization.search is 'random' so sampled evidence is deterministic",
        ),
        (
            {
                "search": "grid",
                "split": {
                    "method": "from_rolling",
                    "params": {
                        "length": 20,
                        "split": 0.5,
                    },
                },
                "random_subset": 5,
            },
            "optimization",
            "Value error, random_subset is only valid when optimization.search is 'random'",
        ),
        (
            {"search": "grid"},
            "optimization.split",
            "Field required",
        ),
    ],
)
def test_run_rejects_invalid_optimization_policy(
    tmp_path: Path,
    optimization: dict[str, object],
    expected_path: str,
    expected_message: str,
) -> None:
    raw = _run_config()
    raw["optimization"] = optimization

    with pytest.raises(ConfigValidationError) as error:
        resolve_run_config(
            raw,
            component_registry=_component_registry(tmp_path),
        )

    assert expected_path in str(error.value)
    assert expected_message in str(error.value)


def test_run_rejects_set_labels_in_optimization_split_params(tmp_path: Path) -> None:
    raw = _run_config()
    raw["optimization"] = {
        "search": "grid",
        "split": {
            "method": "from_rolling",
            "params": {
                "length": 20,
                "split": 0.5,
                "set_labels": ["selection", "held_out"],
            },
            "max_splits": 10,
        },
    }

    with pytest.raises(ConfigValidationError) as error:
        resolve_run_config(
            raw,
            component_registry=_component_registry(tmp_path),
        )

    assert "optimization.split" in str(error.value)
    assert "owned by Aegis" in str(error.value)


def test_run_rejects_top_level_split_as_unknown_field(tmp_path: Path) -> None:
    raw = _run_config()
    raw["optimization"] = {"search": "grid"}
    raw["split"] = _optimization_split()

    with pytest.raises(ConfigValidationError) as error:
        resolve_run_config(
            raw,
            component_registry=_component_registry(tmp_path),
        )

    assert "split" in str(error.value)
    assert "Unexpected keyword argument" in str(error.value)


def test_run_rejects_candidate_grid_on_optimization_config(tmp_path: Path) -> None:
    raw = _run_config()
    raw["optimization"] = _optimization_block(search="grid")
    raw["candidate_grid"] = {"max_candidates": 100, "max_estimated_cells": 10_000}

    with pytest.raises(ConfigValidationError) as error:
        resolve_run_config(
            raw,
            component_registry=_component_registry(tmp_path),
        )

    assert "candidate_grid" in str(error.value)
    assert "Unexpected keyword argument" in str(error.value)


def test_run_rejects_source_selectors_and_indicator_ids_as_unknown_fields(tmp_path: Path) -> None:
    raw = _run_config()
    raw["strategy"] = {"source": "component", "id": "demo.strategy"}
    raw["indicators"] = [{"source": "component", "ids": ["demo.returns"]}]

    with pytest.raises(ConfigValidationError) as error:
        resolve_run_config(
            raw,
            component_registry=_component_registry(tmp_path),
        )

    assert "strategy.source" in str(error.value)
    assert "indicators[0].ids" in str(error.value)
    assert "Unexpected keyword argument" in str(error.value)


def test_run_rejects_playbook_source_selectors(tmp_path: Path) -> None:
    raw = _run_config()
    raw["strategy"] = {"source": "playbook", "id": "ma_cross"}
    raw["indicators"] = [{"source": "playbook", "ids": ["ma_explore"]}]

    with pytest.raises(ConfigValidationError) as error:
        resolve_run_config(
            raw,
            component_registry=_component_registry(tmp_path),
        )

    assert "strategy.source" in str(error.value)
    assert "indicators[0].source" in str(error.value)
    assert "Unexpected keyword argument" in str(error.value)


def _run_config() -> dict[str, object]:
    return {
        "schema_version": CONFIG_SCHEMA_VERSION,
        "name": "canonical_run",
        "data": {
            "instruments": ["AAPL.NASDAQ"],
            "start": "2024-01-01",
            "end": "2024-02-01",
            "timeframe": "1D",
            "arrays": ["OHLCV"],
        },
        "portfolio": {"gross_cap": 1.0, "direction": "longonly"},
        "strategy": {"id": "demo.strategy"},
        "indicators": [{"id": "demo.returns"}],
        "ranking": {"metric": "total_return"},
        "optimization": _optimization_block(search="grid"),
    }


def _optimization_block(search: str, **overrides: object) -> dict[str, object]:
    return {"search": search, "split": _optimization_split(), **overrides}


def _optimization_split() -> dict[str, object]:
    return {
        "method": "from_rolling",
        "params": {"length": 20, "split": 0.5},
        "max_splits": 10,
    }


def _component_registry(tmp_path: Path):
    root = tmp_path / "research" / "components"
    write_indicator_component(root / "indicators" / "returns.py")
    _write_strategy_component(root / "strategies" / "strategy.py")
    return discover_component_registry(root=root, repo_root=tmp_path)


def _write_strategy_component(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# %% component overview\n"
        "# Strategy fixture component used by config tests.\n"
        "# Source: synthetic Close data supplied by the test fixture.\n"
        "\n"
        "# %% define component metadata\n"
        "COMPONENT_MANIFEST = {"
        "'family': 'strategies', 'id': 'demo.strategy', 'version': '1.0.0', "
        "'input_names': ['Close'], 'output_name': 'active', "
        "'consumes_outputs': ['returns']}\n"
        "\n# %% main compute\n"
        "def run(bundle):\n"
        '    """Return fixed strategy signals for config validation tests."""\n'
        "    raise RuntimeError('not executed during config tests')\n"
    )
