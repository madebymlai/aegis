import traceback
from pathlib import Path
from typing import ClassVar

import pytest
import yaml

from research.aegis_research import config as config_module
from research.aegis_research.config import (
    ConfigValidationError,
    DataConfig,
    load_experiment_config,
    resolve_experiment_config,
    resolve_secret_refs,
)
from research.aegis_research.data import RemoteDataPullError, _pull_remote
from research.aegis_research.indicator_registry import IndicatorDefinition, indicator_registry


def test_baseline_configs_load_with_schema_metadata() -> None:
    for path in [
        "research/configs/experiments/synthetic_ml_baseline.yaml",
        "research/configs/experiments/synthetic_walkforward_baseline.yaml",
        "research/configs/experiments/synthetic_trendlb_baseline.yaml",
    ]:
        config = load_experiment_config(path)

        assert config.config.schema_version == config_module.CONFIG_SCHEMA_VERSION
        assert config.raw_config_hash
        assert config.redacted_resolved_config()["report"]["freq"] == "1D"


def test_minimal_dict_config_uses_report_defaults() -> None:
    config = resolve_experiment_config(
        {"schema_version": config_module.CONFIG_SCHEMA_VERSION, "name": "minimal_defaults"}
    )

    assert config.config.report.freq == "1D"
    assert config.config.report.year_freq == "252D"
    assert config.config.split.diagnostic_validation_allowed is False


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


def test_portfolio_rejects_target_size_types(tmp_path: Path) -> None:
    path = _write_config(tmp_path, portfolio={"size_type": "targetpercent"})

    with pytest.raises(ConfigValidationError) as error:
        load_experiment_config(path)

    assert "portfolio.size_type" in str(error.value)
    assert "target size types" in str(error.value)


@pytest.mark.parametrize(
    "mode",
    ["binary", "binary_cont", "binary_cont_sat", "pct_change", "pct_change_norm"],
)
def test_trendlb_accepts_canonical_mode_names(tmp_path: Path, mode: str) -> None:
    path = _write_config(
        tmp_path,
        labels={
            "generator": {"kind": "trendlb", "params": {"mode": mode}},
            "target": {"transform": {"name": _expected_trendlb_transform(mode)}},
        },
    )

    config = load_experiment_config(path)

    assert config.config.labels.generator.params["mode"] == mode


def test_trendlb_mode_rejects_legacy_spellings(tmp_path: Path) -> None:
    path = _write_config(
        tmp_path,
        labels={"generator": {"kind": "trendlb", "params": {"mode": "pctchange"}}},
    )

    with pytest.raises(ConfigValidationError) as error:
        load_experiment_config(path)

    assert "labels.generator.params.mode" in str(error.value)


def test_split_diagnostic_validation_allowed_must_be_boolean(tmp_path: Path) -> None:
    path = _write_config(tmp_path, split={"diagnostic_validation_allowed": "yes"})

    with pytest.raises(ConfigValidationError) as error:
        load_experiment_config(path)

    assert "split.diagnostic_validation_allowed" in str(error.value)


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
        "report": {"freq": "1D", "year_freq": "252D"},
    }
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(config.get(key), dict):
            config[key] = {**config[key], **value}
        else:
            config[key] = value
    path = tmp_path / "experiment.yaml"
    path.write_text(yaml.safe_dump(config, sort_keys=False))
    return path


def _expected_trendlb_transform(mode: str) -> str:
    return "identity_binary" if mode == "binary" else "continuous_identity"
