"""Portfolio and Report validation — pydantic v2 structural tests.

Tests for structural validation are driven through pydantic construction
(``TypeAdapter.validate_python``) and the coordinator (``resolve_run_config`` for
tombstone prepass tests). Assertions use pydantic's structural wording.

Smoke tests for constants, defaults, and the ``periods_per_year`` calculator are
unchanged — they don't hit validation codepaths.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

from research.aegis_research.component_registry import discover_component_registry
from research.aegis_research.configuration import (
    CONFIG_SCHEMA_VERSION,
    PORTFOLIO_DIRECTIONS,
    ConfigValidationError,
    PortfolioConfig,
    ReportConfig,
    resolve_run_config,
)
from tests.support.research.aegis_research.component_fixtures import (
    write_indicator_component,
)
from tests.support.research.aegis_research.factories import (
    make_portfolio_config,
    make_report_config,
)

# ── helpers ──────────────────────────────────────────────────────────────────

_PORTFOLIO_ADAPTER = TypeAdapter(PortfolioConfig)
_REPORT_ADAPTER = TypeAdapter(ReportConfig)


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


def _resolve(portfolio: dict[str, Any], *, tmp_path: Path):
    """Resolve a minimal valid Run Config with the given portfolio section."""
    raw: dict[str, Any] = {
        "schema_version": CONFIG_SCHEMA_VERSION,
        "name": "val-test",
        "data": {"source": "synthetic", "symbols": [{"ticker": "SYN", "ccy": "EUR"}], "rows": 120, "arrays": ["OHLCV"]},
        "portfolio": portfolio,
        "strategy": {"id": "demo.strategy"},
        "indicators": [{"id": "demo.returns"}],
        "ranking": {"metric": "total_return"},
        "optimization": {
            "search": "grid",
            "split": {"method": "from_rolling", "params": {"length": 20, "split": 0.5}, "max_splits": 10},
        },
    }
    return resolve_run_config(raw, component_registry=_component_registry(tmp_path))


def _get_issues(path: str, error: ValidationError) -> list[dict[str, Any]]:
    """Return pydantic error dicts matching the given dotted path."""
    return [e for e in error.errors() if e["loc"] == tuple(path.split("."))]


# ── smoke tests (constants, defaults, calculator) ────────────────────────────


def test_schema_version_is_ten() -> None:
    assert CONFIG_SCHEMA_VERSION == 10


def test_portfolio_directions_admit_signed_book() -> None:
    assert {"longonly", "shortonly", "both"} == PORTFOLIO_DIRECTIONS


def test_report_periods_per_year_shares_metric_annualization_calendar() -> None:
    # Carry annualizes on the same freq/year_freq the Sharpe ratio uses (one calendar):
    # daily defaults give 252, and a weekly book gives 52.
    assert make_report_config().periods_per_year == 252
    assert make_report_config(freq="7D", year_freq="364D").periods_per_year == 52


def test_short_financing_rate_defaults_carry_on() -> None:
    # Non-zero borrow default = carry ON by default; rebate defaults to 0.0.
    config = make_portfolio_config(gross_cap=1.0, direction="longonly")
    assert config.short_borrow_rate == 0.005
    assert config.short_rebate_rate == 0.0


# ── construction validates (pydantic dataclass) ──────────────────────────────


def test_portfolio_construction_requires_gross_cap() -> None:
    with pytest.raises(ValidationError) as e:
        _PORTFOLIO_ADAPTER.validate_python({"direction": "longonly"})
    assert any(err["loc"] == ("gross_cap",) for err in e.value.errors())
    gross_errors = _get_issues("gross_cap", e.value)
    assert gross_errors[0]["msg"] == "Field required"


def test_portfolio_construction_requires_direction() -> None:
    with pytest.raises(ValidationError) as e:
        _PORTFOLIO_ADAPTER.validate_python({"gross_cap": 1.0})
    assert any(err["loc"] == ("direction",) for err in e.value.errors())
    dir_errors = _get_issues("direction", e.value)
    assert dir_errors[0]["msg"] == "Field required"


def test_portfolio_construction_accepts_gross_cap_above_one_no_ceiling() -> None:
    config = _PORTFOLIO_ADAPTER.validate_python({"gross_cap": 2.0, "direction": "longonly"})
    assert config.gross_cap == 2.0


def test_portfolio_construction_rejects_non_positive_gross_cap() -> None:
    with pytest.raises(ValidationError) as e:
        _PORTFOLIO_ADAPTER.validate_python({"gross_cap": 0.0, "direction": "longonly"})
    gross_errors = _get_issues("gross_cap", e.value)
    assert gross_errors[0]["msg"] == "Input should be greater than 0"


def test_portfolio_construction_accepts_net_cap_zero() -> None:
    config = _PORTFOLIO_ADAPTER.validate_python(
        {"gross_cap": 2.0, "net_cap": 0.0, "direction": "longonly"}
    )
    assert config.net_cap == 0.0


def test_portfolio_construction_admits_direction_both() -> None:
    config = _PORTFOLIO_ADAPTER.validate_python({"gross_cap": 2.0, "direction": "both"})
    assert config.direction == "both"


def test_portfolio_construction_admits_direction_shortonly() -> None:
    config = _PORTFOLIO_ADAPTER.validate_python({"gross_cap": 2.0, "direction": "shortonly"})
    assert config.direction == "shortonly"


def test_portfolio_construction_rejects_unknown_direction() -> None:
    with pytest.raises(ValidationError) as e:
        _PORTFOLIO_ADAPTER.validate_python({"gross_cap": 1.0, "direction": "sideways"})
    dir_errors = _get_issues("direction", e.value)
    assert "longonly" in dir_errors[0]["msg"] or dir_errors[0]["type"] == "literal_error"


def test_portfolio_construction_accepts_short_financing_rates() -> None:
    config = _PORTFOLIO_ADAPTER.validate_python(
        {"gross_cap": 2.0, "direction": "longonly", "short_borrow_rate": 0.01, "short_rebate_rate": 0.002}
    )
    assert config.short_borrow_rate == 0.01
    assert config.short_rebate_rate == 0.002


def test_portfolio_construction_rejects_negative_short_borrow_rate() -> None:
    with pytest.raises(ValidationError) as e:
        _PORTFOLIO_ADAPTER.validate_python(
            {"gross_cap": 1.0, "direction": "longonly", "short_borrow_rate": -0.001}
        )
    assert any(err["loc"] == ("short_borrow_rate",) for err in e.value.errors())


def test_portfolio_construction_rejects_negative_short_rebate_rate() -> None:
    with pytest.raises(ValidationError) as e:
        _PORTFOLIO_ADAPTER.validate_python(
            {"gross_cap": 1.0, "direction": "longonly", "short_rebate_rate": -0.001}
        )
    assert any(err["loc"] == ("short_rebate_rate",) for err in e.value.errors())


def test_portfolio_construction_rejects_unknown_key() -> None:
    with pytest.raises(ValidationError) as e:
        _PORTFOLIO_ADAPTER.validate_python(
            {"gross_cap": 1.0, "direction": "longonly", "bogus": 42}
        )
    assert any(err["type"] == "unexpected_keyword_argument" for err in e.value.errors())


# ── report structural validation ─────────────────────────────────────────────


def test_report_construction_rejects_out_of_range_drawdown() -> None:
    with pytest.raises(ValidationError) as e:
        _REPORT_ADAPTER.validate_python({"max_oos_drawdown": 2.0})
    dd_errors = _get_issues("max_oos_drawdown", e.value)
    assert dd_errors[0]["msg"] == "Input should be less than or equal to 1"


def test_report_construction_accepts_defaults() -> None:
    config = _REPORT_ADAPTER.validate_python({})
    assert config.min_oos_sharpe == 0.5
    assert config.max_oos_drawdown == 0.35
    assert config.min_oos_trades == 5


# ── removed fields (no tombstones: rejected as fields that never existed) ─────


@pytest.mark.parametrize("removed", ["entry_budget", "target_exposure_cap", "size", "size_type"])
def test_portfolio_rejects_removed_field_as_unknown_key(tmp_path: Path, removed: str) -> None:
    with pytest.raises(ConfigValidationError) as e:
        _resolve(
            {"gross_cap": 1.0, "direction": "longonly", removed: 1.0},
            tmp_path=tmp_path,
        )
    messages = [i.message for i in e.value.issues if i.path == f"portfolio.{removed}"]
    assert messages == ["Unexpected keyword argument"]


# ── all-errors-at-once (unknown key + structural co-reported) ─────────────────


def test_portfolio_co_reports_unknown_key_and_structural_error(tmp_path: Path) -> None:
    """A removed field *and* a missing gross_cap are both reported."""
    with pytest.raises(ConfigValidationError) as e:
        _resolve({"entry_budget": 0.6, "direction": "longonly"}, tmp_path=tmp_path)
    paths = {i.path for i in e.value.issues}
    assert "portfolio.entry_budget" in paths
    assert "portfolio.gross_cap" in paths


# ── report annualization calendar (Timedelta-string frequencies) ─────────────


def test_report_construction_rejects_non_timedelta_freq() -> None:
    with pytest.raises(ValidationError) as e:
        _REPORT_ADAPTER.validate_python({"freq": "banana"})
    assert _get_issues("freq", e.value)


def test_report_construction_rejects_non_timedelta_year_freq() -> None:
    with pytest.raises(ValidationError) as e:
        _REPORT_ADAPTER.validate_python({"year_freq": "twelve parsecs"})
    assert _get_issues("year_freq", e.value)


def test_report_construction_rejects_negative_min_oos_trades() -> None:
    with pytest.raises(ValidationError) as e:
        _REPORT_ADAPTER.validate_python({"min_oos_trades": -3})
    assert _get_issues("min_oos_trades", e.value)


def test_report_construction_rejects_string_min_oos_trades() -> None:
    with pytest.raises(ValidationError) as e:
        _REPORT_ADAPTER.validate_python({"min_oos_trades": "5"})
    assert _get_issues("min_oos_trades", e.value)
