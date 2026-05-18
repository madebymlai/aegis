import sys
import traceback
from pathlib import Path
from typing import ClassVar

import pytest
import yaml

from research.aegis_research import cli
from research.aegis_research import config as config_module
from research.aegis_research.config import (
    ConfigValidationError,
    DataConfig,
    load_experiment_config,
    resolve_experiment_config,
    resolve_secret_refs,
)
from research.aegis_research.data import RemoteDataPullError, _pull_remote
from research.aegis_research.experiments import run_experiment
from research.aegis_research.indicator_registry import IndicatorDefinition, indicator_registry
from research.aegis_research.model_contracts import ModelPluginDeclaration, ModelPluginDefinition
from research.aegis_research.model_registry import ModelRegistry, ModelRegistryError
from tests.support.research.aegis_research.experiment_config_fixtures import (
    SYNTHETIC_ML_SCAFFOLD_CONFIG,
    SYNTHETIC_PURGED_FIXLB_SCAFFOLD_CONFIG,
)
from tests.support.research.aegis_research.model_plugin_fixtures import (
    SklearnLogisticTestPlugin,
    make_model_registry,
    model_config_dict,
)


def test_scaffold_fixture_configs_load_with_schema_metadata() -> None:
    for path in [
        SYNTHETIC_ML_SCAFFOLD_CONFIG,
        SYNTHETIC_PURGED_FIXLB_SCAFFOLD_CONFIG,
    ]:
        config = load_experiment_config(path)

        assert config.config.schema_version == config_module.CONFIG_SCHEMA_VERSION
        assert "baseline" not in config.config.name
        assert config.config.signals.policy == "long_only_hysteresis"
        assert config.config.signals.long_entry_threshold == 0.55
        assert config.config.signals.long_exit_threshold == 0.50
        assert config.config.signals.execution_timing == "next_open"
        assert config.config.portfolio.entry_budget == 1.0
        assert config.raw_config_hash
        assert config.redacted_resolved_config()["report"]["freq"] == "1D"


def test_minimal_dict_config_uses_report_defaults() -> None:
    config = resolve_experiment_config(
        {
            "schema_version": config_module.CONFIG_SCHEMA_VERSION,
            "name": "minimal_defaults",
            "portfolio": {"entry_budget": 1.0},
        }
    )

    assert config.config.report.freq == "1D"
    assert config.config.report.year_freq == "252D"
    assert config.config.split.kind == "purged_kfold"


def test_minimal_dict_config_uses_signal_contract_defaults() -> None:
    config = resolve_experiment_config(
        {
            "schema_version": config_module.CONFIG_SCHEMA_VERSION,
            "name": "signal_defaults",
            "portfolio": {"entry_budget": 1.0},
        }
    )

    assert config.config.signals.policy == "long_only_hysteresis"
    assert config.config.signals.long_entry_threshold == 0.55
    assert config.config.signals.long_exit_threshold == 0.50
    assert config.config.signals.execution_timing == "next_open"


def test_signal_config_allows_explicit_same_close_timing(tmp_path: Path) -> None:
    path = _write_config(tmp_path, signals={"execution_timing": "same_close"})

    config = load_experiment_config(path).config

    assert config.signals.execution_timing == "same_close"


def test_signal_threshold_ordering_uses_action_specific_paths(tmp_path: Path) -> None:
    path = _write_config(
        tmp_path,
        signals={"long_entry_threshold": 0.50, "long_exit_threshold": 0.50},
    )

    with pytest.raises(ConfigValidationError) as error:
        load_experiment_config(path)

    assert "signals.long_exit_threshold" in str(error.value)
    assert "signals.long_entry_threshold" in str(error.value)


@pytest.mark.parametrize("removed_field", ["long_threshold", "exit_threshold"])
def test_removed_signal_threshold_fields_fail_as_unknown_fields(
    tmp_path: Path,
    removed_field: str,
) -> None:
    path = _write_config(tmp_path, signals={removed_field: 0.5})

    with pytest.raises(ConfigValidationError) as error:
        load_experiment_config(path)

    assert f"signals.{removed_field}" in str(error.value)
    assert "unknown field" in str(error.value)


def test_unknown_signal_policy_fails_with_config_path(tmp_path: Path) -> None:
    path = _write_config(tmp_path, signals={"policy": "long_short"})

    with pytest.raises(ConfigValidationError) as error:
        load_experiment_config(path)

    assert "signals.policy" in str(error.value)


@pytest.mark.parametrize(
    "execution_timing",
    ["next_close", "next_valid_open", "NextValidOpen", "custom"],
)
def test_unsupported_signal_timing_modes_fail_closed(
    tmp_path: Path,
    execution_timing: str,
) -> None:
    path = _write_config(tmp_path, signals={"execution_timing": execution_timing})

    with pytest.raises(ConfigValidationError) as error:
        load_experiment_config(path)

    assert "signals.execution_timing" in str(error.value)


@pytest.mark.parametrize("direction", ["both", "shortonly"])
def test_portfolio_direction_is_long_only_for_v1_signal_contract(
    tmp_path: Path,
    direction: str,
) -> None:
    path = _write_config(tmp_path, portfolio={"direction": direction})

    with pytest.raises(ConfigValidationError) as error:
        load_experiment_config(path)

    assert "portfolio.direction" in str(error.value)
    assert "long-only" in str(error.value)


def test_unknown_fields_fail_with_config_path(tmp_path: Path) -> None:
    path = _write_config(tmp_path, data={"source": "synthetic", "unexpected": True})

    with pytest.raises(ConfigValidationError) as error:
        load_experiment_config(path)

    assert "data.unexpected" in str(error.value)


def test_wrong_collection_shape_fails_without_coercion(tmp_path: Path) -> None:
    path = _write_config(tmp_path, data={"source": "synthetic", "symbols": "SYN"})

    with pytest.raises(ConfigValidationError) as error:
        load_experiment_config(path)

    assert "data.symbols" in str(error.value)


def test_csv_source_requires_path(tmp_path: Path) -> None:
    path = _write_config(tmp_path, data={"source": "csv"})

    with pytest.raises(ConfigValidationError) as error:
        load_experiment_config(path)

    assert "data.path" in str(error.value)


def test_portfolio_requires_explicit_entry_budget(tmp_path: Path) -> None:
    path = _write_config(tmp_path, portfolio=None)

    with pytest.raises(ConfigValidationError) as error:
        load_experiment_config(path)

    assert "portfolio.entry_budget" in str(error.value)
    assert "is required" in str(error.value)


@pytest.mark.parametrize(
    ("entry_budget", "expected_message"),
    [
        (0, "positive"),
        (-0.1, "positive"),
        (1.1, "at most 1"),
        ("1.0", "must be a number"),
        (float("nan"), "finite"),
        (float("inf"), "finite"),
    ],
)
def test_portfolio_entry_budget_must_be_valid_share(
    tmp_path: Path,
    entry_budget: object,
    expected_message: str,
) -> None:
    path = _write_config(tmp_path, portfolio={"entry_budget": entry_budget})

    with pytest.raises(ConfigValidationError) as error:
        load_experiment_config(path)

    assert "portfolio.entry_budget" in str(error.value)
    assert expected_message in str(error.value)


@pytest.mark.parametrize("field", ["size", "size_type"])
def test_portfolio_rejects_removed_public_sizing_fields(
    tmp_path: Path,
    field: str,
) -> None:
    value = 1.0 if field == "size" else "valuepercent"
    path = _write_config(tmp_path, portfolio={field: value})

    with pytest.raises(ConfigValidationError) as error:
        load_experiment_config(path)

    assert f"portfolio.{field}" in str(error.value)
    assert "was removed" in str(error.value)


def test_portfolio_rejects_target_size_types(tmp_path: Path) -> None:
    path = _write_config(tmp_path, portfolio={"size_type": "targetpercent"})

    with pytest.raises(ConfigValidationError) as error:
        load_experiment_config(path)

    assert "portfolio.size_type" in str(error.value)
    assert "target allocation sizing is deferred" in str(error.value)


@pytest.mark.parametrize(
    "mode",
    ["binary", "binary_cont", "binary_cont_sat", "pct_change", "pct_change_norm"],
)
def test_trendlb_canonical_mode_names_reach_evaluation_oracle_gate(
    tmp_path: Path, mode: str
) -> None:
    path = _write_config(
        tmp_path,
        labels={
            "generator": {"kind": "trendlb", "params": {"mode": mode}},
            "target": {"transform": {"name": _expected_trendlb_transform(mode)}},
        },
    )

    with pytest.raises(ConfigValidationError) as error:
        load_experiment_config(path)

    assert "labels.generator.kind" in str(error.value)
    assert "labels.generator.params.mode" not in str(error.value)


def test_trendlb_mode_rejects_legacy_spellings(tmp_path: Path) -> None:
    path = _write_config(
        tmp_path,
        labels={"generator": {"kind": "trendlb", "params": {"mode": "pctchange"}}},
    )

    with pytest.raises(ConfigValidationError) as error:
        load_experiment_config(path)

    assert "labels.generator.params.mode" in str(error.value)


def test_purged_kfold_split_config_resolves_explicit_contract(tmp_path: Path) -> None:
    path = _write_config(
        tmp_path,
        split={
            "kind": "purged_kfold",
            "n_folds": 5,
            "n_test_folds": 1,
            "purge_td": "2D",
            "embargo_td": "1D",
            "max_splits": 20,
            "max_estimated_output_cells": 100_000,
            "max_public_artifact_bytes": 1_000_000,
        },
    )

    config = load_experiment_config(path).config

    assert config.split.kind == "purged_kfold"
    assert config.split.n_folds == 5
    assert config.split.n_test_folds == 1
    assert config.split.purge_td == "2D"
    assert config.split.embargo_td == "1D"
    assert config.split.max_splits == 20


@pytest.mark.parametrize(
    ("split", "expected_path"),
    [
        ({"kind": "purged_kfold", "n_folds": 1}, "split.n_folds"),
        (
            {"kind": "purged_kfold", "n_folds": 5, "n_test_folds": 0},
            "split.n_test_folds",
        ),
        (
            {"kind": "purged_kfold", "n_folds": 5, "n_test_folds": 2},
            "split.n_test_folds",
        ),
        (
            {"kind": "purged_kfold", "n_folds": 5, "n_test_folds": 5},
            "split.n_test_folds",
        ),
        ({"kind": "purged_kfold", "purge_td": "not-a-duration"}, "split.purge_td"),
        ({"kind": "purged_kfold", "embargo_td": "-1D"}, "split.embargo_td"),
        (
            {"kind": "purged_kfold", "n_folds": 6, "n_test_folds": 1, "max_splits": 5},
            "split.max_splits",
        ),
    ],
)
def test_purged_kfold_split_config_fails_closed(
    tmp_path: Path,
    split: dict[str, object],
    expected_path: str,
) -> None:
    path = _write_config(tmp_path, split=split)

    with pytest.raises(ConfigValidationError) as error:
        load_experiment_config(path)

    assert expected_path in str(error.value)


def test_purged_kfold_rejects_removed_bar_embargo_field(tmp_path: Path) -> None:
    path = _write_config(
        tmp_path,
        split={"kind": "purged_kfold", "embargo_bars": 2},
    )

    with pytest.raises(ConfigValidationError) as error:
        load_experiment_config(path)

    assert "split.embargo_bars" in str(error.value)
    assert "unknown field" in str(error.value)


@pytest.mark.parametrize("split_kind", ["holdout", "rolling"])
def test_non_purged_split_kinds_are_not_in_schema_v2(tmp_path: Path, split_kind: str) -> None:
    path = _write_config(tmp_path, split={"kind": split_kind})

    with pytest.raises(ConfigValidationError) as error:
        load_experiment_config(path)

    assert "split.kind" in str(error.value)
    assert "must be one of ['purged_kfold']" in str(error.value)


@pytest.mark.parametrize("label_kind", ["trendlb", "pivotlb"])
def test_purged_kfold_rejects_labels_without_evaluation_oracle(
    tmp_path: Path,
    label_kind: str,
) -> None:
    path = _write_config(
        tmp_path,
        labels={"generator": {"kind": label_kind}},
        split={"kind": "purged_kfold"},
    )

    with pytest.raises(ConfigValidationError) as error:
        load_experiment_config(path)

    assert "labels.generator.kind" in str(error.value)
    assert "exact evaluation-time evidence" in str(error.value)


def test_label_target_selection_rejects_default_scalar_mismatch(tmp_path: Path) -> None:
    path = _write_config(
        tmp_path,
        labels={"target": {"select": {"params": {"n": 6}}}},
    )

    with pytest.raises(ConfigValidationError) as error:
        load_experiment_config(path)

    assert "labels.target.select.params.n" in str(error.value)
    assert "must be 5" in str(error.value)


def test_label_target_selection_rejects_scalar_type_mismatch(tmp_path: Path) -> None:
    path = _write_config(
        tmp_path,
        labels={
            "generator": {"kind": "fixlb", "params": {"n": 5}},
            "target": {"select": {"params": {"n": "5"}}},
        },
    )

    with pytest.raises(ConfigValidationError) as error:
        load_experiment_config(path)

    assert "labels.target.select.params.n" in str(error.value)
    assert "must be 5" in str(error.value)


def test_label_target_selection_requires_multi_value_coordinate(tmp_path: Path) -> None:
    path = _write_config(
        tmp_path,
        labels={"generator": {"kind": "fixlb", "params": {"n": [1, 2]}}},
    )

    with pytest.raises(ConfigValidationError) as error:
        load_experiment_config(path)

    assert "labels.target.select.params.n" in str(error.value)
    assert "multiple values" in str(error.value)


def test_report_frequency_must_be_timedelta_compatible(tmp_path: Path) -> None:
    path = _write_config(tmp_path, report={"freq": "not-a-frequency"})

    with pytest.raises(ConfigValidationError) as error:
        load_experiment_config(path)

    assert "report.freq" in str(error.value)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("min_oos_sharpe", float("nan")),
        ("max_oos_drawdown", float("inf")),
        ("max_oos_drawdown", float("-inf")),
    ],
)
def test_report_numeric_gates_must_be_finite(tmp_path: Path, field: str, value: float) -> None:
    path = _write_config(tmp_path, report={field: value})

    with pytest.raises(ConfigValidationError) as error:
        load_experiment_config(path)

    assert f"report.{field}" in str(error.value)
    assert "finite" in str(error.value)


def test_report_frequency_must_be_positive(tmp_path: Path) -> None:
    path = _write_config(tmp_path, report={"freq": "0D"})

    with pytest.raises(ConfigValidationError) as error:
        load_experiment_config(path)

    assert "report.freq" in str(error.value)
    assert "positive" in str(error.value)


@pytest.mark.parametrize(
    ("section", "override", "expected_path"),
    [
        ("data", {"source": "SYNTHETIC"}, "data.source"),
        ("labels", {"generator": {"kind": "FIXLB"}}, "labels.generator.kind"),
        ("split", {"kind": "Holdout"}, "split.kind"),
        ("model", {"kind": "Logistic_Regression"}, "model.kind"),
        ("portfolio", {"direction": "LongOnly"}, "portfolio.direction"),
        ("portfolio", {"size_type": "ValuePercent"}, "portfolio.size_type"),
    ],
)
def test_enum_values_must_use_canonical_casing(
    tmp_path: Path,
    section: str,
    override: dict[str, object],
    expected_path: str,
) -> None:
    path = _write_config(tmp_path, **{section: override})

    with pytest.raises(ConfigValidationError) as error:
        load_experiment_config(path)

    assert expected_path in str(error.value)


def test_unknown_model_plugin_id_fails_with_registered_bootstrap(tmp_path: Path) -> None:
    path = _write_config(
        tmp_path,
        model={**model_config_dict(), "plugin_id": "unknown.model"},
    )

    with pytest.raises(ConfigValidationError) as error:
        load_experiment_config(path, model_registry=make_model_registry())

    assert "model.plugin_id" in str(error.value)
    assert "unknown" in str(error.value)


def test_model_plugin_params_are_validated_by_registered_plugin(tmp_path: Path) -> None:
    path = _write_config(
        tmp_path,
        model={**model_config_dict(), "params": {"max_iter": 0, "extra": True}},
    )

    with pytest.raises(ConfigValidationError) as error:
        load_experiment_config(path, model_registry=make_model_registry())

    assert "model.params.max_iter" in str(error.value)
    assert "model.params.extra" in str(error.value)


def test_model_config_rejects_import_like_payloads(tmp_path: Path) -> None:
    path = _write_config(
        tmp_path,
        model={**model_config_dict(), "params": {"module": "unsafe.import.path"}},
    )

    with pytest.raises(ConfigValidationError) as error:
        load_experiment_config(path)

    assert "model.params.module" in str(error.value)
    assert "register trusted plugin code" in str(error.value)


def test_duplicate_model_plugin_ids_fail_before_config_resolution() -> None:
    registry = ModelRegistry()
    definition = ModelPluginDefinition(
        declaration=ModelPluginDeclaration(id="duplicate.model", version="1.0.0"),
        plugin=SklearnLogisticTestPlugin(),
    )
    registry.register(definition)

    with pytest.raises(ModelRegistryError, match="duplicate"):
        registry.register(definition)


def test_malformed_model_plugin_declaration_fails_before_config_resolution() -> None:
    registry = ModelRegistry()

    with pytest.raises(ModelRegistryError, match="positive_class_probability"):
        registry.register(
            ModelPluginDefinition(
                declaration=ModelPluginDeclaration(
                    id="bad.model",
                    version="1.0.0",
                    prediction_outputs=(),
                ),
                plugin=SklearnLogisticTestPlugin(),
            )
        )


def test_missing_model_registry_fails_before_run_directory(tmp_path: Path) -> None:
    config = resolve_experiment_config(
        {
            "schema_version": config_module.CONFIG_SCHEMA_VERSION,
            "name": "missing_registry",
            "output_dir": str(tmp_path),
            "model": model_config_dict(),
            "portfolio": {"entry_budget": 1.0},
        }
    )

    with pytest.raises(ConfigValidationError) as error:
        run_experiment(config, run_id="missing-registry-run")

    assert "model.plugin_id" in str(error.value)
    assert not (tmp_path / "missing-registry-run").exists()


def test_cli_rejects_unregistered_model_before_run_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = _write_config(
        tmp_path,
        model={**model_config_dict(), "plugin_id": "unknown.model"},
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["aegis-research", "run", str(path), "--run-id", "cli-missing-registry"],
    )

    with pytest.raises(SystemExit) as error:
        cli.main()

    assert error.value.code == 2
    assert "unknown registered model plugin id" in capsys.readouterr().err
    assert not (tmp_path / "runs" / "cli-missing-registry").exists()


def test_duplicate_yaml_keys_fail_validation(tmp_path: Path) -> None:
    path = tmp_path / "experiment.yaml"
    path.write_text(
        "\n".join(
            [
                f"schema_version: {config_module.CONFIG_SCHEMA_VERSION}",
                "name: duplicate_key_test",
                "data:",
                "  source: synthetic",
                "data:",
                "  source: synthetic",
                "report:",
                "  freq: 1D",
                "  year_freq: 252D",
                "",
            ]
        )
    )

    with pytest.raises(ConfigValidationError) as error:
        load_experiment_config(path)

    assert "data" in str(error.value)
    assert "duplicate mapping key" in str(error.value)


@pytest.mark.parametrize("name", ["../escape", "nested/name", "nested\\name", ".", ".."])
def test_experiment_name_must_be_path_safe(tmp_path: Path, name: str) -> None:
    path = _write_config(tmp_path, name=name)

    with pytest.raises(ConfigValidationError) as error:
        load_experiment_config(path)

    assert "name" in str(error.value)


def test_local_sources_reject_ignored_wrapper_kwargs(tmp_path: Path) -> None:
    path = _write_config(tmp_path, data={"source": "synthetic", "wrapper_kwargs": {"freq": "1D"}})

    with pytest.raises(ConfigValidationError) as error:
        load_experiment_config(path)

    assert "data.wrapper_kwargs" in str(error.value)


def test_inline_provider_secrets_fail_validation(tmp_path: Path) -> None:
    path = _write_config(
        tmp_path,
        data={
            "source": "binance",
            "symbols": ["BTCUSDT"],
            "start": "2020-01-01",
            "end": "2020-02-01",
            "timeframe": "1D",
            "provider_kwargs": {"api_key": "plain-secret"},
        },
    )

    with pytest.raises(ConfigValidationError) as error:
        load_experiment_config(path)

    assert "data.provider_kwargs.api_key" in str(error.value)


def test_inline_secret_values_under_benign_keys_fail_validation(tmp_path: Path) -> None:
    path = _write_config(
        tmp_path,
        data={
            "source": "binance",
            "symbols": ["BTCUSDT"],
            "start": "2020-01-01",
            "end": "2020-02-01",
            "timeframe": "1D",
            "provider_kwargs": {"endpoint": "https://api.example.test/prices?password=hunter2"},
        },
    )

    with pytest.raises(ConfigValidationError) as error:
        load_experiment_config(path)

    assert "data.provider_kwargs.endpoint" in str(error.value)
    assert "secret-like values" in str(error.value)


@pytest.mark.parametrize("denied_key", ["auth", "headers", "cookies", "cache"])
def test_nested_denied_passthrough_keys_fail_validation(
    tmp_path: Path,
    denied_key: str,
) -> None:
    path = _write_config(
        tmp_path,
        data={
            "source": "binance",
            "symbols": ["BTCUSDT"],
            "start": "2020-01-01",
            "end": "2020-02-01",
            "timeframe": "1D",
            "provider_kwargs": {"nested": {denied_key: "enabled"}},
        },
    )

    with pytest.raises(ConfigValidationError) as error:
        load_experiment_config(path)

    assert f"data.provider_kwargs.nested.{denied_key}" in str(error.value)


def test_feature_map_accepts_only_logical_ohlcv_keys(tmp_path: Path) -> None:
    path = _write_config(
        tmp_path,
        data={"source": "synthetic", "feature_map": {"close": "Adj Close"}},
    )

    config = load_experiment_config(path)

    assert config.config.data.feature_map == {"close": "Adj Close"}


def test_unknown_feature_map_key_fails_validation(tmp_path: Path) -> None:
    path = _write_config(
        tmp_path,
        data={"source": "synthetic", "feature_map": {"settlement": "Settle"}},
    )

    with pytest.raises(ConfigValidationError) as error:
        load_experiment_config(path)

    assert "data.feature_map.settlement" in str(error.value)


def test_quality_policy_rejects_unknown_degradation(tmp_path: Path) -> None:
    path = _write_config(
        tmp_path,
        data={"source": "synthetic", "quality": {"allowed_degradations": ["anything"]}},
    )

    with pytest.raises(ConfigValidationError) as error:
        load_experiment_config(path)

    assert "data.quality.allowed_degradations[0]" in str(error.value)


def test_skip_on_error_requires_skipped_symbol_quality_policy(tmp_path: Path) -> None:
    path = _write_config(
        tmp_path,
        data={"source": "synthetic", "skip_on_error": True},
    )

    with pytest.raises(ConfigValidationError) as error:
        load_experiment_config(path)

    assert "data.skip_on_error" in str(error.value)


def test_indicator_specs_validate_builtin_and_custom_registry_ids(tmp_path: Path) -> None:
    path = _write_config(
        tmp_path,
        indicators={
            "invalid_value_policy": "drop_rows",
            "specs": [
                {
                    "id": "ma",
                    "params": {"window": [10, 30], "wtype": "simple"},
                    "outputs": ["ma"],
                    "model_features": [
                        {"output": "ma", "transform": "distance_to_close"},
                    ],
                },
                {
                    "id": "custom_retvol",
                    "params": {"window": [5]},
                    "outputs": ["retvol"],
                    "model_features": [{"output": "retvol"}],
                },
            ],
        },
    )

    config = load_experiment_config(path).config

    assert config.indicators.invalid_value_policy == "drop_rows"
    assert [spec.id for spec in config.indicators.specs] == ["ma", "custom_retvol"]
    assert config.indicators.specs[0].model_features[0].transform == "distance_to_close"


def test_indicator_specs_reject_inline_code_fields(tmp_path: Path) -> None:
    path = _write_config(
        tmp_path,
        indicators={
            "specs": [
                {
                    "id": "ma",
                    "params": {"window": [10]},
                    "outputs": ["ma"],
                    "formula": "close.rolling(10).mean()",
                },
            ],
        },
    )

    with pytest.raises(ConfigValidationError) as error:
        load_experiment_config(path)

    assert "indicators.specs[0].formula" in str(error.value)
    assert "inline code" in str(error.value)


def test_indicator_specs_report_registry_paths_for_invalid_values(tmp_path: Path) -> None:
    path = _write_config(
        tmp_path,
        indicators={
            "specs": [
                {
                    "id": "ma",
                    "params": {"unknown": 10, "window": [10, 30], "wtype": "not-a-type"},
                    "outputs": ["not_ma"],
                    "model_features": [
                        {"output": "ma", "transform": "not_a_transform"},
                    ],
                },
            ],
        },
    )

    with pytest.raises(ConfigValidationError) as error:
        load_experiment_config(path)

    message = str(error.value)
    assert "indicators.specs[0].params.unknown" in message
    assert "indicators.specs[0].params.wtype" in message
    assert "indicators.specs[0].outputs[0]" in message
    assert "indicators.specs[0].model_features[0].transform" in message


def test_indicator_specs_require_non_default_params_at_config_boundary(tmp_path: Path) -> None:
    path = _write_config(
        tmp_path,
        indicators={
            "specs": [
                {
                    "id": "returns",
                    "params": {},
                    "outputs": ["returns"],
                    "model_features": [{"output": "returns"}],
                },
                {
                    "id": "ma",
                    "params": {"window": []},
                    "outputs": ["ma"],
                    "model_features": [{"output": "ma", "transform": "distance_to_close"}],
                },
            ],
        },
    )

    with pytest.raises(ConfigValidationError) as error:
        load_experiment_config(path)

    message = str(error.value)
    assert "indicators.specs[0].params.window" in message
    assert "is required" in message
    assert "indicators.specs[1].params.window" in message
    assert "must not be empty" in message


def test_indicator_specs_require_explicit_product_grid(tmp_path: Path) -> None:
    path = _write_config(
        tmp_path,
        indicators={
            "specs": [
                {
                    "id": "ma",
                    "grid": "product",
                    "params": {"window": [10, 30], "wtype": ["simple", "wilder"]},
                    "outputs": ["ma"],
                    "model_features": [{"output": "ma", "transform": "distance_to_close"}],
                },
            ],
        },
    )

    with pytest.raises(ConfigValidationError) as error:
        load_experiment_config(path)

    assert "indicators.specs[0].param_product" in str(error.value)


def test_indicator_specs_reject_mismatched_zipped_param_lengths(tmp_path: Path) -> None:
    path = _write_config(
        tmp_path,
        indicators={
            "specs": [
                {
                    "id": "ma",
                    "params": {"window": [10, 30], "wtype": ["simple", "wilder", "exp"]},
                    "outputs": ["ma"],
                    "model_features": [{"output": "ma", "transform": "distance_to_close"}],
                },
            ],
        },
    )

    with pytest.raises(ConfigValidationError) as error:
        load_experiment_config(path)

    assert "indicators.specs[0].params" in str(error.value)
    assert "zipped" in str(error.value)


def test_indicator_specs_reject_non_bar_aligned_custom_definitions(monkeypatch) -> None:
    registry = indicator_registry()
    registry["shape_changing_test"] = IndicatorDefinition(
        id="shape_changing_test",
        kind="custom",
        input_names=("close",),
        param_names=("window",),
        output_names=("events",),
        default_outputs=("events",),
        default_model_features=({"output": "events", "transform": "identity"},),
        supported_transforms=("identity",),
        bar_aligned=False,
    )
    monkeypatch.setattr(config_module, "indicator_registry", lambda: registry)

    with pytest.raises(ConfigValidationError) as error:
        resolve_experiment_config(
            {
                "schema_version": config_module.CONFIG_SCHEMA_VERSION,
                "name": "shape_changing_indicator",
                "indicators": {
                    "specs": [
                        {
                            "id": "shape_changing_test",
                            "params": {"window": [10]},
                            "outputs": ["events"],
                            "model_features": [{"output": "events"}],
                        }
                    ]
                },
                "report": {"freq": "1D", "year_freq": "252D"},
            }
        )

    assert "indicators.specs[0].id" in str(error.value)
    assert "bar-aligned" in str(error.value)


def test_env_secret_refs_are_redacted_and_resolved_at_runtime(tmp_path: Path, monkeypatch) -> None:
    path = _write_config(
        tmp_path,
        data={
            "source": "binance",
            "symbols": ["BTCUSDT"],
            "start": "2020-01-01",
            "end": "2020-02-01",
            "timeframe": "1D",
            "provider_kwargs": {"api_key": {"env": "BINANCE_API_KEY"}},
        },
    )
    monkeypatch.setenv("BINANCE_API_KEY", "super-secret-token")

    config = load_experiment_config(path)
    resolved_kwargs, secrets = resolve_secret_refs(config.config.data.provider_kwargs)

    assert resolved_kwargs == {"api_key": "super-secret-token"}
    assert secrets == ["super-secret-token"]
    assert config.redacted_authored_config()["data"]["provider_kwargs"]["api_key"] == {
        "env": "<redacted>"
    }
    assert "super-secret-token" not in yaml.safe_dump(config.redacted_resolved_config())


def test_missing_env_secret_ref_fails_at_runtime_resolution(tmp_path: Path, monkeypatch) -> None:
    path = _write_config(
        tmp_path,
        data={
            "source": "binance",
            "symbols": ["BTCUSDT"],
            "start": "2020-01-01",
            "end": "2020-02-01",
            "timeframe": "1D",
            "provider_kwargs": {"api_key": {"env": "BINANCE_API_KEY"}},
        },
    )
    monkeypatch.delenv("BINANCE_API_KEY", raising=False)
    config = load_experiment_config(path)

    with pytest.raises(ConfigValidationError) as error:
        resolve_secret_refs(config.config.data.provider_kwargs)

    assert "BINANCE_API_KEY" in str(error.value)


def test_remote_passthrough_secret_refs_are_resolved_and_redacted(monkeypatch) -> None:
    monkeypatch.setenv("WRAPPER_SECRET", "wrapper-secret")
    monkeypatch.setenv("PROVIDER_SECRET", "provider-secret")
    monkeypatch.setenv("EXECUTION_SECRET", "execution-secret")

    config = DataConfig(
        source="binance",
        symbols=["BTCUSDT"],
        start="2020-01-01",
        end="2020-02-01",
        timeframe="1D",
        wrapper_kwargs={"token": {"env": "WRAPPER_SECRET"}},
        provider_kwargs={"api_key": {"env": "PROVIDER_SECRET"}},
        execution_kwargs={"password": {"env": "EXECUTION_SECRET"}},
    )

    with pytest.raises(RemoteDataPullError) as error:
        _pull_remote(_FailingData, config)

    formatted_traceback = "".join(
        traceback.format_exception(type(error.value), error.value, error.value.__traceback__)
    )

    assert _FailingData.kwargs["wrapper_kwargs"] == {"token": "wrapper-secret"}
    assert _FailingData.kwargs["api_key"] == "provider-secret"
    assert _FailingData.kwargs["execute_kwargs"] == {"password": "execution-secret"}
    assert error.value.__cause__ is None
    assert error.value.__context__ is None
    assert "wrapper-secret" not in str(error.value)
    assert "provider-secret" not in str(error.value)
    assert "execution-secret" not in str(error.value)
    assert "wrapper-secret" not in formatted_traceback
    assert "provider-secret" not in formatted_traceback
    assert "execution-secret" not in formatted_traceback


class _FailingData:
    kwargs: ClassVar[dict[str, object]] = {}

    @classmethod
    def pull(cls, *args, **kwargs):
        cls.kwargs = kwargs
        raise RuntimeError("wrapper-secret provider-secret execution-secret")


def _write_config(tmp_path: Path, **overrides) -> Path:
    config = {
        "schema_version": config_module.CONFIG_SCHEMA_VERSION,
        "name": "contract_test",
        "output_dir": str(tmp_path / "runs"),
        "data": {"source": "synthetic", "symbols": ["SYN"], "rows": 50, "timeframe": "1D"},
        "portfolio": {"entry_budget": 1.0},
        "report": {"freq": "1D", "year_freq": "252D"},
    }
    for key, value in overrides.items():
        if value is None:
            config.pop(key, None)
            continue
        if isinstance(value, dict) and isinstance(config.get(key), dict):
            config[key] = {**config[key], **value}
        else:
            config[key] = value
    path = tmp_path / "experiment.yaml"
    path.write_text(yaml.safe_dump(config, sort_keys=False))
    return path


def _expected_trendlb_transform(mode: str) -> str:
    return "identity_binary" if mode == "binary" else "continuous_identity"
