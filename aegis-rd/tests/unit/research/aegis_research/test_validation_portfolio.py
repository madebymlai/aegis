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
from tests.support.research.aegis_research.market_data_fixtures import (
    native_data_config_payload,
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
        'def run(bundle):\n    """Fixture strategy, never executed."""\n'
        "    raise RuntimeError('not executed during config tests')\n"
    )
    return discover_component_registry(root=root, repo_root=tmp_path)


def _resolve(portfolio: dict[str, Any], *, tmp_path: Path):
    """Resolve a minimal valid Run Config with the given portfolio section."""
    raw: dict[str, Any] = {
        "schema_version": CONFIG_SCHEMA_VERSION,
        "name": "val-test",
        "data": native_data_config_payload(instruments=["SYN.XNAS"], end="2024-04-30"),
        "portfolio": portfolio,
        "strategy": {"id": "demo.strategy"},
        "indicators": [{"id": "demo.returns"}],
        "ranking": {"metric": "total_return"},
        "optimization": {"search": "grid", "observation_block_bars": 20},
    }
    return resolve_run_config(raw, component_registry=_component_registry(tmp_path))


def _get_issues(path: str, error: ValidationError) -> list[dict[str, Any]]:
    """Return pydantic error dicts matching the given dotted path."""
    return [e for e in error.errors() if e["loc"] == tuple(path.split("."))]


# ── smoke tests (constants, defaults, calculator) ────────────────────────────


def test_schema_version_is_eleven() -> None:
    assert CONFIG_SCHEMA_VERSION == 11


def test_portfolio_directions_admit_signed_book() -> None:
    assert {"longonly", "shortonly", "both"} == PORTFOLIO_DIRECTIONS


def test_report_periods_per_year_shares_metric_annualization_calendar() -> None:
    # Carry annualizes on the same freq/year_freq the Sharpe ratio uses (one calendar):
    # daily defaults give 252, and a weekly book gives 52.
    assert make_report_config().periods_per_year == 252
    assert make_report_config(freq="7D", year_freq="364D").periods_per_year == 52


def test_short_financing_rate_defaults_carry_on() -> None:
    # Non-zero borrow default = carry ON by default; rebate defaults to 0.0.
    config = make_portfolio_config(direction="longonly")
    assert config.short_borrow_rate == 0.005
    assert config.short_rebate_rate == 0.0


def test_margin_interest_rate_defaults_priced_leverage_on() -> None:
    # Construct directly: the factory pins margin_interest_rate explicitly, so it
    # cannot witness the SCHEMA default this test exists to pin.
    config = PortfolioConfig(direction="longonly")

    assert config.margin_interest_rate == 0.0367


# ── construction validates (pydantic dataclass) ──────────────────────────────


def test_portfolio_construction_requires_direction() -> None:
    with pytest.raises(ValidationError) as e:
        _PORTFOLIO_ADAPTER.validate_python({})
    assert any(err["loc"] == ("direction",) for err in e.value.errors())
    dir_errors = _get_issues("direction", e.value)
    assert dir_errors[0]["msg"] == "Field required"


@pytest.mark.parametrize("removed_key", ["gross_cap", "net_cap"])
def test_portfolio_construction_rejects_removed_cap_keys(removed_key: str) -> None:
    # The exposure envelope is the fixed unit-gross sleeve contract
    # (aegis-rd-ui1m); a config still declaring a cap fails like any unknown key.
    with pytest.raises(ValidationError) as e:
        _PORTFOLIO_ADAPTER.validate_python({removed_key: 1.0, "direction": "longonly"})
    removed_errors = _get_issues(removed_key, e.value)
    assert removed_errors[0]["msg"] == "Unexpected keyword argument"


def test_portfolio_construction_defaults_directional_bands_to_zero() -> None:
    config = _PORTFOLIO_ADAPTER.validate_python({"direction": "longonly"})
    assert config.band_up == 0.0
    assert config.band_down == 0.0
    assert config.band_overrides == {}


def test_portfolio_construction_accepts_asymmetric_directional_band_pair() -> None:
    config = _PORTFOLIO_ADAPTER.validate_python(
        {
            "direction": "longonly",
            "band_up": 0.01,
            "band_down": 0.05,
        }
    )
    assert config.band_up == 0.01
    assert config.band_down == 0.05


def test_portfolio_construction_accepts_per_instrument_band_overrides() -> None:
    config = _PORTFOLIO_ADAPTER.validate_python(
        {
            "direction": "longonly",
            "band_up": 0.01,
            "band_down": 0.02,
            "band_overrides": {"SYN.XNAS": {"up": 0.03, "down": 0.07}},
        }
    )

    assert config.band_overrides["SYN.XNAS"].up == 0.03
    assert config.band_overrides["SYN.XNAS"].down == 0.07


def test_portfolio_construction_rejects_negative_band_override_width() -> None:
    with pytest.raises(ValidationError) as e:
        _PORTFOLIO_ADAPTER.validate_python(
            {
                "direction": "longonly",
                "band_overrides": {"SYN.XNAS": {"up": -0.01, "down": 0.07}},
            }
        )

    assert any(err["loc"] == ("band_overrides", "SYN.XNAS", "up") for err in e.value.errors())


def test_portfolio_construction_rejects_removed_rebalance_band() -> None:
    with pytest.raises(ValidationError) as e:
        _PORTFOLIO_ADAPTER.validate_python({"direction": "longonly", "rebalance_band": 0.02})
    assert any(
        err["loc"] == ("rebalance_band",) and err["type"] == "unexpected_keyword_argument"
        for err in e.value.errors()
    )


def test_portfolio_construction_accepts_one_directional_width_with_other_defaulted() -> None:
    config = _PORTFOLIO_ADAPTER.validate_python({"direction": "longonly", "band_up": 0.01})
    assert config.band_up == 0.01
    assert config.band_down == 0.0


def test_portfolio_construction_admits_direction_both() -> None:
    config = _PORTFOLIO_ADAPTER.validate_python({"direction": "both"})
    assert config.direction == "both"


def test_portfolio_construction_admits_direction_shortonly() -> None:
    config = _PORTFOLIO_ADAPTER.validate_python({"direction": "shortonly"})
    assert config.direction == "shortonly"


def test_portfolio_construction_rejects_unknown_direction() -> None:
    with pytest.raises(ValidationError) as e:
        _PORTFOLIO_ADAPTER.validate_python({"direction": "sideways"})
    dir_errors = _get_issues("direction", e.value)
    assert "longonly" in dir_errors[0]["msg"] or dir_errors[0]["type"] == "literal_error"


def test_portfolio_construction_accepts_short_financing_rates() -> None:
    config = _PORTFOLIO_ADAPTER.validate_python(
        {"direction": "longonly", "short_borrow_rate": 0.01, "short_rebate_rate": 0.002}
    )
    assert config.short_borrow_rate == 0.01
    assert config.short_rebate_rate == 0.002


def test_portfolio_construction_accepts_explicit_zero_margin_interest_rate() -> None:
    config = _PORTFOLIO_ADAPTER.validate_python(
        {"direction": "longonly", "margin_interest_rate": 0.0}
    )
    assert config.margin_interest_rate == 0.0


def test_portfolio_construction_rejects_negative_short_borrow_rate() -> None:
    with pytest.raises(ValidationError) as e:
        _PORTFOLIO_ADAPTER.validate_python({"direction": "longonly", "short_borrow_rate": -0.001})
    assert any(err["loc"] == ("short_borrow_rate",) for err in e.value.errors())


def test_portfolio_construction_rejects_negative_short_rebate_rate() -> None:
    with pytest.raises(ValidationError) as e:
        _PORTFOLIO_ADAPTER.validate_python({"direction": "longonly", "short_rebate_rate": -0.001})
    assert any(err["loc"] == ("short_rebate_rate",) for err in e.value.errors())


def test_portfolio_construction_rejects_negative_margin_interest_rate() -> None:
    with pytest.raises(ValidationError) as e:
        _PORTFOLIO_ADAPTER.validate_python(
            {"direction": "longonly", "margin_interest_rate": -0.001}
        )
    assert any(err["loc"] == ("margin_interest_rate",) for err in e.value.errors())


def test_portfolio_construction_rejects_unknown_key() -> None:
    with pytest.raises(ValidationError) as e:
        _PORTFOLIO_ADAPTER.validate_python({"direction": "longonly", "bogus": 42})
    assert any(err["type"] == "unexpected_keyword_argument" for err in e.value.errors())


def test_portfolio_band_override_key_must_be_in_tradeable_universe(tmp_path: Path) -> None:
    with pytest.raises(ConfigValidationError) as e:
        _resolve(
            {
                "direction": "longonly",
                "band_overrides": {"OTHER.XNAS": {"up": 0.03, "down": 0.07}},
            },
            tmp_path=tmp_path,
        )

    assert any(
        i.path == "portfolio.band_overrides"
        and "OTHER.XNAS" in i.message
        and "SYN.XNAS" in i.message
        for i in e.value.issues
    )


def test_resolved_config_carries_margin_interest_default(tmp_path: Path) -> None:
    config = _resolve({"direction": "longonly"}, tmp_path=tmp_path)

    assert config.config.portfolio.margin_interest_rate == 0.0367


def test_portfolio_band_override_key_accepts_configured_future_root(tmp_path: Path) -> None:
    raw = {
        "schema_version": CONFIG_SCHEMA_VERSION,
        "name": "val-test",
        "data": native_data_config_payload(
            instruments=[],
            futures=["ES"],
            path="/catalog",
            end="2024-04-30",
        ),
        "portfolio": {
            "direction": "longonly",
            "band_overrides": {"ES": {"up": 0.03, "down": 0.07}},
        },
        "strategy": {"id": "demo.strategy"},
        "indicators": [{"id": "demo.returns"}],
        "ranking": {"metric": "total_return"},
        "optimization": {
            "search": "grid",
            "observation_block_bars": 20,
        },
    }

    resolved = resolve_run_config(raw, component_registry=_component_registry(tmp_path))

    assert resolved.config.portfolio.band_overrides["ES"].up == 0.03


# ── report structural validation ─────────────────────────────────────────────


def test_report_construction_accepts_defaults() -> None:
    config = _REPORT_ADAPTER.validate_python({})
    assert config.freq == "1D"
    assert config.year_freq == "252D"


# ── removed fields (no tombstones: rejected as fields that never existed) ─────


@pytest.mark.parametrize("removed", ["entry_budget", "target_exposure_cap", "size", "size_type"])
def test_portfolio_rejects_removed_field_as_unknown_key(tmp_path: Path, removed: str) -> None:
    with pytest.raises(ConfigValidationError) as e:
        _resolve(
            {"direction": "longonly", removed: 1.0},
            tmp_path=tmp_path,
        )
    messages = [i.message for i in e.value.issues if i.path == f"portfolio.{removed}"]
    assert messages == ["Unexpected keyword argument"]


# ── all-errors-at-once (unknown key + structural co-reported) ─────────────────


def test_portfolio_co_reports_unknown_key_and_structural_error(tmp_path: Path) -> None:
    """A removed field *and* a missing direction are both reported."""
    with pytest.raises(ConfigValidationError) as e:
        _resolve({"entry_budget": 0.6}, tmp_path=tmp_path)
    paths = {i.path for i in e.value.issues}
    assert "portfolio.entry_budget" in paths
    assert "portfolio.direction" in paths


# ── report annualization calendar (Timedelta-string frequencies) ─────────────


def test_report_construction_rejects_non_timedelta_freq() -> None:
    with pytest.raises(ValidationError) as e:
        _REPORT_ADAPTER.validate_python({"freq": "banana"})
    assert _get_issues("freq", e.value)


def test_report_construction_rejects_non_timedelta_year_freq() -> None:
    with pytest.raises(ValidationError) as e:
        _REPORT_ADAPTER.validate_python({"year_freq": "twelve parsecs"})
    assert _get_issues("year_freq", e.value)


@pytest.mark.parametrize(
    "removed",
    ["min_oos_sharpe", "max_oos_drawdown", "min_oos_trades"],
)
def test_report_construction_rejects_removed_oos_gate(removed: str) -> None:
    with pytest.raises(ValidationError) as e:
        _REPORT_ADAPTER.validate_python({removed: 0})
    assert _get_issues(removed, e.value)
