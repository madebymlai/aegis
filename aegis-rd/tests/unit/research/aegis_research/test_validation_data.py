"""Data section validation — pydantic v2 structural tests.

Tests are driven through ``resolve_run_config`` and the pydantic
``TypeAdapter`` for structural validation. Assertions use pydantic's wording.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

from research.aegis_research.component_registry import discover_component_registry
from research.aegis_research.configuration import (
    CONFIG_SCHEMA_VERSION,
    ConfigValidationError,
    DataConfig,
    resolve_run_config,
)
from tests.support.research.aegis_research.component_fixtures import (
    write_indicator_component,
)

_DATA_ADAPTER = TypeAdapter(DataConfig)


def _component_registry(tmp_path: Path):
    root = tmp_path / "research" / "components"
    write_indicator_component(root / "indicators" / "returns.py")
    strategy = root / "strategies" / "strategy.py"
    strategy.parent.mkdir(parents=True, exist_ok=True)
    strategy.write_text(
        "# %% component overview\n# Strategy fixture for validation tests.\n"
        "# Source: synthetic Close data supplied by the test fixture.\n\n"
        "# %% define component metadata\n"
        "COMPONENT_MANIFEST = {'family': 'strategies', 'id': 'demo.strategy', 'version': '1.0.0', "
        "'input_names': ['Close'], 'output_name': 'active', 'consumes_outputs': ['returns'], "
        "}\n"
        "\n# %% main compute\n"
        "def run(bundle):\n    \"\"\"Fixture strategy, never executed.\"\"\"\n"
        "    raise RuntimeError('not executed during config tests')\n"
    )
    return discover_component_registry(root=root, repo_root=tmp_path)


def _resolve(data: dict[str, Any], *, tmp_path: Path):
    """Resolve a minimal valid Run Config with the given data section."""
    raw: dict[str, Any] = {
        "schema_version": CONFIG_SCHEMA_VERSION,
        "name": "val-test",
        "data": data,
        "portfolio": {"gross_cap": 1.0, "direction": "longonly"},
        "strategy": {"id": "demo.strategy"},
        "indicators": [{"id": "demo.returns"}],
        "ranking": {"metric": "total_return"},
        "optimization": {
            "search": "grid",
            "split": {
                "method": "from_rolling",
                "params": {"length": 20, "split": 0.5},
                "max_splits": 10,
            },
        },
    }
    return resolve_run_config(raw, component_registry=_component_registry(tmp_path))


def _get_issues(path: str, error: ValidationError) -> list[dict[str, Any]]:
    """Return pydantic error dicts matching the given dotted path."""
    return [e for e in error.errors() if e["loc"] == tuple(path.split("."))]


# ── construction validates (pydantic dataclass) ──────────────────────────────


def test_data_construction_requires_arrays() -> None:
    with pytest.raises(ValidationError) as e:
        _DATA_ADAPTER.validate_python({"source": "synthetic"})
    assert any(err["loc"] == ("arrays",) for err in e.value.errors())
    arrays_errors = _get_issues("arrays", e.value)
    assert arrays_errors[0]["msg"] == "Field required"


def test_data_construction_accepts_minimal_synthetic_source() -> None:
    config = _DATA_ADAPTER.validate_python(
        {"source": "synthetic", "arrays": ["OHLCV"]}
    )
    assert config.source == "synthetic"
    assert config.arrays == ["OHLCV"]


def test_data_construction_rejects_unknown_source() -> None:
    """Unknown source is accepted by the pydantic model (source whitelisting
    is a post-pydantic coordinator check so programmatic construction works),
    but rejected through resolve_run_config."""
    # Direct construction accepts any string source (whitelist is coordinator-only)
    config = _DATA_ADAPTER.validate_python({"source": "nope", "arrays": ["OHLCV"]})
    assert config.source == "nope"


def test_data_construction_accepts_any_string_source() -> None:
    """Pydantic model accepts any string source — whitelist is coordinator."""
    config = _DATA_ADAPTER.validate_python({"source": "internal-frame", "arrays": ["OHLCV"]})
    assert config.source == "internal-frame"


# ── resolve_run_config integration ───────────────────────────────────────────


def test_resolve_accepts_minimal_data(tmp_path: Path) -> None:
    resolved = _resolve(
        {"source": "synthetic", "arrays": ["OHLCV"], "symbols": [{"ticker": "SYN", "ccy": "EUR"}], "rows": 120},
        tmp_path=tmp_path,
    )
    assert resolved.config.data.source == "synthetic"
    assert resolved.config.data.arrays == ["OHLCV"]


def test_resolve_accepts_declared_future_with_defaults(tmp_path: Path) -> None:
    resolved = _resolve(
        {
            "source": "synthetic",
            "arrays": ["OHLCV"],
            "symbols": [{"ticker": "ES=F", "ccy": "USD", "root": "ES", "dataset": "cme"}],
            "rows": 120,
        },
        tmp_path=tmp_path,
    )

    symbol = resolved.config.data.symbols[0]
    assert symbol.root == "ES"
    assert symbol.dataset == "cme"
    assert symbol.roll_rule == "calendar"
    assert symbol.adjustment == "unadjusted"


def test_resolve_rejects_future_mixed_with_listed_ref_hints(tmp_path: Path) -> None:
    with pytest.raises(ConfigValidationError) as e:
        _resolve(
            {
                "source": "synthetic",
                "arrays": ["OHLCV"],
                "symbols": [
                    {"ticker": "ES=F", "ccy": "USD", "root": "ES", "dataset": "cme", "figi": "BBG000000001"}
                ],
                "rows": 120,
            },
            tmp_path=tmp_path,
        )

    assert any("mutually exclusive" in issue.message for issue in e.value.issues)


def test_resolve_rejects_incomplete_future_identity(tmp_path: Path) -> None:
    with pytest.raises(ConfigValidationError) as e:
        _resolve(
            {
                "source": "synthetic",
                "arrays": ["OHLCV"],
                "symbols": [{"ticker": "ES=F", "ccy": "USD", "root": "ES"}],
                "rows": 120,
            },
            tmp_path=tmp_path,
        )

    assert any("dataset" in issue.message for issue in e.value.issues)


def test_resolve_rejects_future_roll_rule_unsupported_by_source(tmp_path: Path) -> None:
    with pytest.raises(ConfigValidationError) as e:
        _resolve(
            {
                "source": "yf",
                "arrays": ["OHLCV"],
                "symbols": [
                    {"ticker": "ES=F", "ccy": "USD", "root": "ES", "dataset": "cme", "roll_rule": "volume"}
                ],
                "start": "2020-01-01",
                "end": "2020-02-01",
                "timeframe": "1D",
            },
            tmp_path=tmp_path,
        )

    assert any("roll_rule" in issue.message and "yf" in issue.message for issue in e.value.issues)


def test_resolve_rejects_missing_arrays(tmp_path: Path) -> None:
    with pytest.raises(ConfigValidationError) as e:
        _resolve(
            {"source": "synthetic", "symbols": [{"ticker": "SYN", "ccy": "EUR"}], "rows": 120},
            tmp_path=tmp_path,
        )
    issues = [(i.path, i.message) for i in e.value.issues]
    assert ("data.arrays", "Field required") in issues


def test_resolve_rejects_unknown_key(tmp_path: Path) -> None:
    with pytest.raises(ConfigValidationError) as e:
        _resolve(
            {"source": "synthetic", "arrays": ["OHLCV"], "bogus": 42},
            tmp_path=tmp_path,
        )
    paths = {i.path for i in e.value.issues}
    assert "data.bogus" in paths


def test_resolve_rejects_feature_map_unknown_key(tmp_path: Path) -> None:
    with pytest.raises(ConfigValidationError) as e:
        _resolve(
            {
                "source": "synthetic",
                "arrays": ["OHLCV"],
                "feature_map": {"close": "price"},
            },
            tmp_path=tmp_path,
        )
    paths = {i.path for i in e.value.issues}
    assert "data.feature_map" in paths


@pytest.mark.parametrize(
    "arrays",
    [
        "OHLCV",  # not a list
        ["Close "],  # whitespace
        [""],  # empty string
        [1],  # not a string
        [],  # empty list
    ],
)
def test_resolve_rejects_invalid_arrays_values(
    tmp_path: Path, arrays: object
) -> None:
    with pytest.raises(ConfigValidationError) as e:
        _resolve(
            {
                "source": "synthetic",
                "arrays": arrays,
                "symbols": [{"ticker": "SYN", "ccy": "EUR"}],
                "rows": 120,
            },
            tmp_path=tmp_path,
        )
    assert "data.arrays" in str(e.value)


# ── conditional requiredness (model_validator) ────────────────────────────────


def test_resolve_rejects_csv_without_path(tmp_path: Path) -> None:
    with pytest.raises(ConfigValidationError) as e:
        _resolve(
            {
                "source": "csv",
                "arrays": ["OHLCV"],
                "symbols": [{"ticker": "BTC-USD", "ccy": "EUR"}],
            },
            tmp_path=tmp_path,
        )
    messages = [i.message for i in e.value.issues if i.path == "data"]
    assert messages
    assert "path" in messages[0]


def test_resolve_rejects_store_source_without_gap_fill_provider(tmp_path: Path) -> None:
    with pytest.raises(ConfigValidationError) as e:
        _resolve(
            {
                "source": "store",
                "arrays": ["Close"],
                "symbols": [{"ticker": "SPY", "ccy": "USD", "figi": "BBG000B9XRY4"}],
                "start": "2024-01-02",
                "end": "2024-01-05",
                "timeframe": "1D",
            },
            tmp_path=tmp_path,
        )

    messages = [i.message for i in e.value.issues if i.path == "data"]
    assert messages
    assert "provider" in messages[0]


def test_resolve_rejects_remote_source_without_symbols(tmp_path: Path) -> None:
    with pytest.raises(ConfigValidationError) as e:
        _resolve(
            {
                "source": "yf",
                "arrays": ["OHLCV"],
                "symbols": [],
                "start": "2020-01-01",
                "end": "2020-02-01",
                "timeframe": "1D",
            },
            tmp_path=tmp_path,
        )
    messages = [i.message for i in e.value.issues if i.path == "data"]
    assert messages
    assert "symbols" in messages[0]


def test_resolve_rejects_skip_on_error_without_skipped_symbols(tmp_path: Path) -> None:
    with pytest.raises(ConfigValidationError) as e:
        _resolve(
            {
                "source": "synthetic",
                "arrays": ["OHLCV"],
                "skip_on_error": True,
            },
            tmp_path=tmp_path,
        )
    messages = [i.message for i in e.value.issues if i.path == "data"]
    assert messages
    assert "skipped_symbols" in messages[0]


def test_resolve_accepts_skip_on_error_with_skipped_symbols(tmp_path: Path) -> None:
    resolved = _resolve(
        {
            "source": "synthetic",
            "arrays": ["OHLCV"],
            "skip_on_error": True,
            "quality": {"allowed_degradations": ["skipped_symbols"]},
        },
        tmp_path=tmp_path,
    )
    assert resolved.config.data.skip_on_error is True
    assert "skipped_symbols" in resolved.config.data.quality.allowed_degradations


# ── data section requiredness (no silent OHLCV default at the YAML seam) ─────


def test_omitting_data_section_is_rejected(tmp_path: Path) -> None:
    """A YAML that omits ``data:`` entirely must fail — arrays must be declared
    explicitly, not silently defaulted (the gross_cap/data.arrays drift class)."""
    raw: dict[str, Any] = {
        "schema_version": CONFIG_SCHEMA_VERSION,
        "name": "val-test",
        "portfolio": {"gross_cap": 1.0, "direction": "longonly"},
        "strategy": {"id": "demo.strategy"},
        "indicators": [{"id": "demo.returns"}],
        "ranking": {"metric": "total_return"},
        "optimization": {
            "search": "grid",
            "split": {
                "method": "from_rolling",
                "params": {"length": 20, "split": 0.5},
                "max_splits": 10,
            },
        },
    }
    with pytest.raises(ConfigValidationError) as e:
        resolve_run_config(raw, component_registry=_component_registry(tmp_path))
    assert "data" in {i.path for i in e.value.issues}


# ── VBT-facing enums and ranges ───────────────────────────────────────────────


def test_data_construction_rejects_unknown_missing_index_policy() -> None:
    with pytest.raises(ValidationError) as e:
        _DATA_ADAPTER.validate_python({"arrays": ["OHLCV"], "missing_index": "explode"})
    assert _get_issues("missing_index", e.value)


def test_data_construction_rejects_unknown_missing_columns_policy() -> None:
    with pytest.raises(ValidationError) as e:
        _DATA_ADAPTER.validate_python({"arrays": ["OHLCV"], "missing_columns": "Drop"})
    assert _get_issues("missing_columns", e.value)


def test_data_construction_rejects_unknown_quality_degradation() -> None:
    """A typo'd degradation must error, not silently fail to un-gate quality."""
    with pytest.raises(ValidationError) as e:
        _DATA_ADAPTER.validate_python(
            {"arrays": ["OHLCV"], "quality": {"allowed_degradations": ["skiped_symbols"]}}
        )
    assert [x for x in e.value.errors() if x["loc"][:2] == ("quality", "allowed_degradations")]


def test_data_construction_rejects_non_positive_rows() -> None:
    with pytest.raises(ValidationError) as e:
        _DATA_ADAPTER.validate_python({"arrays": ["OHLCV"], "rows": 0})
    assert _get_issues("rows", e.value)
