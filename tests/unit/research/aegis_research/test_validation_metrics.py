"""Ranking validation — structural tests + thin coordinator net.

Structural checks (min_weight ∈ 0..1, min_trades non-negative, extra keys)
live on the ``RankingConfig`` pydantic dataclass.  Metric membership is
covered at the registry cross-check seam in ``test_cross_checks.py``; this
file keeps the thin coordinator net (structural wording through resolve,
structural + membership co-reporting).
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
    RankingConfig,
    resolve_run_config,
)
from tests.support.research.aegis_research.component_fixtures import (
    write_indicator_component,
)

# ── helpers ──────────────────────────────────────────────────────────────────

_RANKING_ADAPTER = TypeAdapter(RankingConfig)


def _component_registry(tmp_path: Path):
    root = tmp_path / "research" / "components"
    write_indicator_component(root / "indicators" / "returns.py")
    strategy = root / "strategies" / "strategy.py"
    strategy.parent.mkdir(parents=True, exist_ok=True)
    strategy.write_text(
        "# %% component overview\n# Strategy fixture for ranking validation tests.\n"
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


def _resolve(ranking: dict[str, Any], *, tmp_path: Path):
    """Resolve a minimal valid Run Config with the given ranking section."""
    raw: dict[str, Any] = {
        "schema_version": CONFIG_SCHEMA_VERSION,
        "name": "rank-val-test",
        "data": {"source": "synthetic", "symbols": ["SYN"], "rows": 120, "arrays": ["OHLCV"]},
        "portfolio": {"gross_cap": 1.0, "direction": "longonly"},
        "strategy": {"id": "demo.strategy"},
        "indicators": [{"id": "demo.returns"}],
        "ranking": ranking,
        "optimization": {
            "search": "grid",
            "split": {"method": "from_rolling", "params": {"length": 20, "split": 0.5}, "max_splits": 10},
        },
    }
    return resolve_run_config(raw, component_registry=_component_registry(tmp_path))


def _get_issues(path: str, error: ValidationError) -> list[dict[str, Any]]:
    """Return pydantic error dicts matching the given dotted path."""
    return [e for e in error.errors() if e["loc"] == tuple(path.split("."))]


# ── construction validates (pydantic dataclass) ──────────────────────────────


def test_ranking_construction_accepts_valid_defaults() -> None:
    config = _RANKING_ADAPTER.validate_python({"metric": "total_return"})
    assert config.metric == "total_return"
    assert config.min_weight == 0.3
    assert config.min_trades == 0


def test_ranking_construction_requires_metric() -> None:
    with pytest.raises(ValidationError) as e:
        _RANKING_ADAPTER.validate_python({})
    assert any(err["loc"] == ("metric",) for err in e.value.errors())
    metric_errors = _get_issues("metric", e.value)
    assert metric_errors[0]["msg"] == "Field required"


def test_ranking_construction_accepts_custom_min_weight() -> None:
    config = _RANKING_ADAPTER.validate_python({"metric": "sharpe_ratio", "min_weight": 0.5})
    assert config.min_weight == 0.5


def test_ranking_construction_rejects_min_weight_out_of_range() -> None:
    with pytest.raises(ValidationError) as e:
        _RANKING_ADAPTER.validate_python({"metric": "sharpe_ratio", "min_weight": 1.5})
    mw_errors = _get_issues("min_weight", e.value)
    assert mw_errors[0]["msg"] == "Input should be less than or equal to 1"


def test_ranking_construction_rejects_bool_min_weight() -> None:
    """pydantic strict float rejects bool (bool is a subclass of int)."""
    with pytest.raises(ValidationError) as e:
        _RANKING_ADAPTER.validate_python({"metric": "sharpe_ratio", "min_weight": True})
    mw_errors = _get_issues("min_weight", e.value)
    assert mw_errors, "bool min_weight should be rejected"


def test_ranking_construction_rejects_negative_min_trades() -> None:
    with pytest.raises(ValidationError) as e:
        _RANKING_ADAPTER.validate_python({"metric": "sharpe_ratio", "min_trades": -1})
    mt_errors = _get_issues("min_trades", e.value)
    assert mt_errors[0]["msg"] == "Input should be greater than or equal to 0"


def test_ranking_construction_rejects_float_min_trades() -> None:
    with pytest.raises(ValidationError) as e:
        _RANKING_ADAPTER.validate_python({"metric": "sharpe_ratio", "min_trades": 1.5})
    mt_errors = _get_issues("min_trades", e.value)
    assert mt_errors, "float min_trades should be rejected"


def test_ranking_construction_rejects_unknown_key() -> None:
    with pytest.raises(ValidationError) as e:
        _RANKING_ADAPTER.validate_python(
            {"metric": "sharpe_ratio", "bogus": 42}
        )
    assert any(err["type"] == "unexpected_keyword_argument" for err in e.value.errors())


# ── coordinator net ───────────────────────────────────────────────────────────


def test_ranking_not_a_dict_fails(tmp_path: Path) -> None:
    raw: dict[str, Any] = {
        "schema_version": CONFIG_SCHEMA_VERSION,
        "name": "rank-val-test",
        "data": {"source": "synthetic", "symbols": ["SYN"], "rows": 120, "arrays": ["OHLCV"]},
        "portfolio": {"gross_cap": 1.0, "direction": "longonly"},
        "strategy": {"id": "demo.strategy"},
        "indicators": [{"id": "demo.returns"}],
        "ranking": "not_a_dict",
        "optimization": {
            "search": "grid",
            "split": {"method": "from_rolling", "params": {"length": 20, "split": 0.5}, "max_splits": 10},
        },
    }
    with pytest.raises(ConfigValidationError) as e:
        resolve_run_config(raw, component_registry=_component_registry(tmp_path))
    assert any(i.path == "ranking" and "Input should be a dictionary" in i.message for i in e.value.issues)


# ── no duplicate issues ──────────────────────────────────────────────────────


def test_ranking_unknown_metric_plus_unknown_key_co_reports(tmp_path: Path) -> None:
    """Structural error (unknown key) and membership error co-reported."""
    with pytest.raises(ConfigValidationError) as e:
        _resolve({"metric": "not_a_metric", "bogus": 42}, tmp_path=tmp_path)
    paths = {i.path for i in e.value.issues}
    assert "ranking.bogus" in paths
    assert "ranking.metric" in paths


def test_ranking_single_structural_problem_no_duplicate(tmp_path: Path) -> None:
    """A single structural problem (min_weight out of range) produces exactly one issue."""
    with pytest.raises(ConfigValidationError) as e:
        _resolve({"metric": "total_return", "min_weight": 1.5}, tmp_path=tmp_path)
    mw_issues = [i for i in e.value.issues if i.path == "ranking.min_weight"]
    assert len(mw_issues) == 1, f"expected 1 issue for min_weight, got {len(mw_issues)}"
