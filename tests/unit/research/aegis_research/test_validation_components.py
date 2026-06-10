"""Component (strategy + indicators) validation — pydantic v2 structural tests.

Structural validation is driven through pydantic construction
(``TypeAdapter.validate_python``) and the coordinator (``resolve_run_config`` for
membership + output-contract checks). Assertions use pydantic's structural wording.

Structural checks are now owned by the pydantic models, validated in the
coordinator in ``resolution._build_resolved_run_config``.
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
    RunIndicatorSourceConfig,
    RunSourceRefConfig,
    resolve_run_config,
)
from tests.support.research.aegis_research.component_fixtures import (
    write_indicator_component,
)

# ── helpers ──────────────────────────────────────────────────────────────────

_STRATEGY_ADAPTER = TypeAdapter(RunSourceRefConfig)
_INDICATOR_ADAPTER = TypeAdapter(RunIndicatorSourceConfig)


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
        "'wide_callable': 'run_wide'}\n"
        "COMPONENT_CALLABLE = 'run'\n\n# %% main compute\n"
        "def run(bundle):\n    \"\"\"Fixture strategy, never executed.\"\"\"\n"
        "    raise RuntimeError('not executed during config tests')\n"
    )
    return discover_component_registry(root=root, repo_root=tmp_path)


def _resolve(
    *,
    tmp_path: Path,
    strategy: dict[str, Any] | None = None,
    indicators: list[dict[str, Any]] | None = None,
) -> None:
    """Resolve a minimal valid Run Config, optionally overriding components.

    ``strategy=None`` and ``indicators=None`` use valid defaults.
    """
    raw: dict[str, Any] = {
        "schema_version": CONFIG_SCHEMA_VERSION,
        "name": "comp-val-test",
        "data": {"source": "synthetic", "symbols": ["SYN"], "rows": 120, "arrays": ["OHLCV"]},
        "portfolio": {"gross_cap": 1.0, "direction": "longonly"},
        "strategy": strategy if strategy is not None else {"id": "demo.strategy"},
        "indicators": indicators if indicators is not None else [{"id": "demo.returns"}],
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


# ── structural: strategy pydantic validation ─────────────────────────────────


def test_strategy_construction_requires_id() -> None:
    with pytest.raises(ValidationError) as e:
        _STRATEGY_ADAPTER.validate_python({})
    assert any(err["loc"] == ("id",) for err in e.value.errors())
    id_errors = _get_issues("id", e.value)
    assert id_errors[0]["msg"] == "Field required"


def test_strategy_construction_rejects_empty_id() -> None:
    with pytest.raises(ValidationError) as e:
        _STRATEGY_ADAPTER.validate_python({"id": ""})
    assert any(err["loc"] == ("id",) for err in e.value.errors())
    id_errors = _get_issues("id", e.value)
    assert "at least 1 character" in id_errors[0]["msg"]


def test_strategy_construction_rejects_bad_id_pattern() -> None:
    with pytest.raises(ValidationError) as e:
        _STRATEGY_ADAPTER.validate_python({"id": "bad id!"})
    assert any(err["loc"] == ("id",) for err in e.value.errors())
    id_errors = _get_issues("id", e.value)
    assert "pattern" in id_errors[0]["msg"]


def test_strategy_construction_rejects_extra_key() -> None:
    with pytest.raises(ValidationError) as e:
        _STRATEGY_ADAPTER.validate_python({"id": "demo.strategy", "lock_id": "abc"})
    assert any(err["type"] == "unexpected_keyword_argument" for err in e.value.errors())


def test_strategy_construction_rejects_non_mapping_params() -> None:
    with pytest.raises(ValidationError) as e:
        _STRATEGY_ADAPTER.validate_python({"id": "demo.strategy", "params": "not_a_dict"})
    assert any(err["loc"] == ("params",) for err in e.value.errors())


def test_strategy_construction_accepts_valid_id_and_params() -> None:
    config = _STRATEGY_ADAPTER.validate_python({"id": "demo.strategy", "params": {"lookback": 20}})
    assert config.id == "demo.strategy"
    assert config.params == {"lookback": 20}


# ── structural: indicator pydantic validation ────────────────────────────────


def test_indicator_construction_requires_id() -> None:
    with pytest.raises(ValidationError) as e:
        _INDICATOR_ADAPTER.validate_python({})
    assert any(err["loc"] == ("id",) for err in e.value.errors())
    id_errors = _get_issues("id", e.value)
    assert id_errors[0]["msg"] == "Field required"


def test_indicator_construction_rejects_empty_id() -> None:
    with pytest.raises(ValidationError) as e:
        _INDICATOR_ADAPTER.validate_python({"id": ""})
    assert any(err["loc"] == ("id",) for err in e.value.errors())


def test_indicator_construction_rejects_bad_id_pattern() -> None:
    with pytest.raises(ValidationError) as e:
        _INDICATOR_ADAPTER.validate_python({"id": "bad id!"})
    assert any(err["loc"] == ("id",) for err in e.value.errors())


def test_indicator_construction_rejects_extra_key() -> None:
    with pytest.raises(ValidationError) as e:
        _INDICATOR_ADAPTER.validate_python({"id": "demo.returns", "candidate_id": "abc"})
    assert any(err["type"] == "unexpected_keyword_argument" for err in e.value.errors())


def test_indicator_construction_rejects_non_mapping_params() -> None:
    with pytest.raises(ValidationError) as e:
        _INDICATOR_ADAPTER.validate_python({"id": "demo.returns", "params": 42})
    assert any(err["loc"] == ("params",) for err in e.value.errors())


# ── coordinator: strategy membership ─────────────────────────────────────────


def test_strategy_accepts_known_id(tmp_path: Path) -> None:
    resolved = _resolve(tmp_path=tmp_path)
    assert resolved.config.strategy.id == "demo.strategy"


def test_strategy_rejects_unknown_id(tmp_path: Path) -> None:
    with pytest.raises(ConfigValidationError) as e:
        _resolve(tmp_path=tmp_path, strategy={"id": "missing.one"})
    issues = {(i.path, i.message) for i in e.value.issues}
    assert ("strategy.id", "unknown strategy component id") in issues


def test_strategy_rejects_all_id(tmp_path: Path) -> None:
    with pytest.raises(ConfigValidationError) as e:
        _resolve(tmp_path=tmp_path, strategy={"id": "all"})
    issues = {(i.path, i.message) for i in e.value.issues}
    assert ("strategy.id", "must select one component id") in issues


def test_strategy_rejects_per_component_lock_reference_fields(tmp_path: Path) -> None:
    # ADR-0006: per-Component lock_id/candidate_id/run_id are gone.
    # pydantic extra=forbid catches them as Unexpected keyword argument.
    with pytest.raises(ConfigValidationError) as e:
        _resolve(
            tmp_path=tmp_path,
            strategy={"id": "demo.strategy", "lock_id": "L", "candidate_id": "C", "run_id": "R"},
        )
    message = str(e.value)
    assert "strategy.lock_id" in message
    assert "strategy.candidate_id" in message
    assert "strategy.run_id" in message
    assert "Unexpected keyword argument" in message


# ── coordinator: indicator membership ────────────────────────────────────────


def test_indicators_accept_known_id(tmp_path: Path) -> None:
    resolved = _resolve(tmp_path=tmp_path, indicators=[{"id": "demo.returns"}])
    assert resolved.config.indicators[0].id == "demo.returns"


def test_indicator_rejects_unknown_id(tmp_path: Path) -> None:
    with pytest.raises(ConfigValidationError) as e:
        _resolve(tmp_path=tmp_path, indicators=[{"id": "missing.indicator"}])
    issues = {(i.path, i.message) for i in e.value.issues}
    assert ("indicators[0].id", "unknown indicator component id") in issues


def test_indicator_rejects_all_id(tmp_path: Path) -> None:
    with pytest.raises(ConfigValidationError) as e:
        _resolve(tmp_path=tmp_path, indicators=[{"id": "all"}])
    issues = {(i.path, i.message) for i in e.value.issues}
    assert ("indicators[0].id", "must select one component id") in issues


def test_indicators_flag_duplicate_component_id(tmp_path: Path) -> None:
    with pytest.raises(ConfigValidationError) as e:
        _resolve(
            tmp_path=tmp_path,
            indicators=[{"id": "demo.returns"}, {"id": "demo.returns"}],
        )
    assert any(
        "duplicates indicator component id" in i.message for i in e.value.issues
    )


def test_indicators_reject_extra_keys_on_item(tmp_path: Path) -> None:
    with pytest.raises(ConfigValidationError) as e:
        _resolve(
            tmp_path=tmp_path,
            indicators=[{"id": "demo.returns", "candidate_id": "C", "run_id": "R"}],
        )
    message = str(e.value)
    assert "indicators[0].candidate_id" in message
    assert "indicators[0].run_id" in message
    assert "Unexpected keyword argument" in message


# ── coordinator: output-contract cross-check ─────────────────────────────────


def test_strategy_rejects_missing_consumed_indicator_output(tmp_path: Path) -> None:
    with pytest.raises(ConfigValidationError) as e:
        _resolve(tmp_path=tmp_path, indicators=[])
    assert "strategy.consumes_outputs" in str(e.value)
    assert "not produced" in str(e.value)


def test_strategy_accepts_indicators_producing_consumed_outputs(tmp_path: Path) -> None:
    resolved = _resolve(tmp_path=tmp_path, indicators=[{"id": "demo.returns"}])
    assert resolved.config.strategy.id == "demo.strategy"


# ── coordinator: strategy structural errors reported at coordinator level ────


def test_strategy_not_a_mapping_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ConfigValidationError) as e:
        _resolve(tmp_path=tmp_path, strategy="not_a_dict")  # type: ignore[arg-type]
    assert any(i.path == "strategy" and "Input should be a dictionary" in i.message for i in e.value.issues)


def test_strategy_missing_id_reported_with_pydantic_wording(tmp_path: Path) -> None:
    with pytest.raises(ConfigValidationError) as e:
        _resolve(tmp_path=tmp_path, strategy={})
    issues = {(i.path, i.message) for i in e.value.issues}
    assert ("strategy.id", "Field required") in issues


def test_strategy_bad_id_pattern_reported_with_pydantic_wording(tmp_path: Path) -> None:
    with pytest.raises(ConfigValidationError) as e:
        _resolve(tmp_path=tmp_path, strategy={"id": "bad id!"})
    issues = {(i.path, i.message) for i in e.value.issues}
    assert any(path == "strategy.id" and "pattern" in msg for path, msg in issues)


def test_indicators_not_a_list_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ConfigValidationError) as e:
        _resolve(tmp_path=tmp_path, indicators="not_a_list")  # type: ignore[arg-type]
    assert any(
        i.path == "indicators" and "Input should be a valid list" in i.message for i in e.value.issues
    )


def test_indicator_item_not_a_mapping_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ConfigValidationError) as e:
        _resolve(tmp_path=tmp_path, indicators=["not_a_dict"])  # type: ignore[list-item]
    assert any(
        "indicators[0]" in i.path and "Input should be a dictionary" in i.message
        for i in e.value.issues
    )


def test_indicator_missing_id_reported_with_pydantic_wording(tmp_path: Path) -> None:
    with pytest.raises(ConfigValidationError) as e:
        _resolve(tmp_path=tmp_path, indicators=[{}])
    issues = {(i.path, i.message) for i in e.value.issues}
    assert ("indicators[0].id", "Field required") in issues


# ── coordinator: all-errors-at-once ──────────────────────────────────────────


def test_co_reports_strategy_structural_and_indicator_membership_errors(
    tmp_path: Path,
) -> None:
    """Structural errors and membership errors are both reported."""
    with pytest.raises(ConfigValidationError) as e:
        _resolve(
            tmp_path=tmp_path,
            strategy={"id": "bad id!"},
            indicators=[{"id": "missing.one"}],
        )
    paths = {i.path for i in e.value.issues}
    assert "strategy.id" in paths
    assert "indicators[0].id" in paths


def test_co_reports_indicator_duplicate_and_membership_errors(
    tmp_path: Path,
) -> None:
    with pytest.raises(ConfigValidationError) as e:
        _resolve(
            tmp_path=tmp_path,
            indicators=[
                {"id": "demo.returns"},
                {"id": "demo.returns"},
                {"id": "missing.one"},
            ],
        )
    paths = {i.path for i in e.value.issues}
    # duplicate detected in the coordinator after pydantic validation
    assert any("duplicates indicator component id" in i.message for i in e.value.issues)
    assert "indicators[2].id" in paths  # membership error


def test_source_selectors_and_indicator_ids_rejected_by_pydantic(
    tmp_path: Path,
) -> None:
    """Old ``source`` / ``ids`` keys are rejected by pydantic extra=forbid."""
    with pytest.raises(ConfigValidationError) as e:
        _resolve(
            tmp_path=tmp_path,
            strategy={"source": "component", "id": "demo.strategy"},
            indicators=[{"source": "component", "ids": ["demo.returns"]}],
        )
    message = str(e.value)
    assert "strategy.source" in message
    assert "indicators[0].ids" in message
    assert "Unexpected keyword argument" in message
