"""Unit tests for the book.toml loader — pure, zero Nautilus.

``load_book_config`` is the operator-facing surface: a declarative TOML file
deserializes to the same ``BookConfig`` the e2e tests build by hand.  The TOML
format lives only in this loader (information hiding); the domain ``BookConfig``
stays a plain dataclass and keeps its own invariants (``__post_init__``).
"""

from __future__ import annotations

import pytest

from aegis_trader.config import (
    BookConfigError,
    find_book_config,
    load_book_config,
)
from aegis_trader.domain.book_config import (
    BookConfig,
    ConvexityBudgetCandidate,
    DrawdownDeleverCurve,
    RiskGroup,
    SleeveConfig,
    TailConvexityBudget,
)
from aegis_trader.domain.types import SleeveName

_MINIMAL = """
[[sleeves]]
name = "trend"
wheel_filename = "trend.whl"
risk_share = 1.0
group = "Floor"
"""


def _write(tmp_path, text: str):
    path = tmp_path / "book.toml"
    path.write_text(text)
    return path


def test_minimal_book_loads(tmp_path):
    """base_currency + one sleeve -> a BookConfig with those values."""
    path = _write(tmp_path, """
        base_currency = "EUR"
        book_vol_target = 0.09

        [[sleeves]]
        name = "trend_lse"
        wheel_filename = "trend_lse-abc123.whl"
        risk_share = 1.0
        group = "Floor"
    """)

    book = load_book_config(path)

    assert isinstance(book, BookConfig)
    assert book.base_currency == "EUR"
    assert book.book_vol_target == 0.09
    assert book.sleeve_count == 1
    assert book.sleeves[0].name == SleeveName("trend_lse")
    assert book.sleeves[0].wheel_filename == "trend_lse-abc123.whl"
    assert book.sleeves[0].risk_share == 1.0
    assert book.sleeves[0].group == RiskGroup.FLOOR


def test_full_book_round_trips_to_hand_built_config(tmp_path):
    """Every field the e2e tests build by hand survives the TOML round-trip."""
    path = _write(tmp_path, """
        base_currency = "EUR"
        book_vol_target = 0.12
        sleeve_reversion_fraction = 0.5
        max_book_gross = 1.0
        gross_cap = 2.0
        net_cap = 0.5
        per_name_cap = 0.1
        default_band_up = 0.03
        default_band_down = 0.01
        aggregate_drift_threshold = 0.5

        [drawdown_delever]
        start_drawdown = 0.05
        end_drawdown = 0.25
        floor_multiplier = 0.4

        [[sleeves]]
        name = "trend_lse"
        wheel_filename = "trend_lse-abc123.whl"
        risk_share = 0.6
        group = "Floor"
        weight_band_down = 0.01
        weight_band_up = 0.03

        [[sleeves]]
        name = "trend_xetra"
        wheel_filename = "trend_xetra-def456.whl"
        risk_share = 0.4
        group = "Target"
        weight_band_down = 0.02
        weight_band_up = 0.04

        [[band_overrides]]
        figi = "BBG000B9XRY4"
        band_up = 0.05
        band_down = 0.02
    """)

    book = load_book_config(path)

    assert book == BookConfig(
        sleeves=(
            SleeveConfig(name=SleeveName("trend_lse"),
                         wheel_filename="trend_lse-abc123.whl", risk_share=0.6,
                         group=RiskGroup.FLOOR, weight_band_down=0.01,
                         weight_band_up=0.03),
            SleeveConfig(name=SleeveName("trend_xetra"),
                         wheel_filename="trend_xetra-def456.whl", risk_share=0.4,
                         group=RiskGroup.TARGET, weight_band_down=0.02,
                         weight_band_up=0.04),
        ),
        base_currency="EUR",
        book_vol_target=0.12,
        sleeve_reversion_fraction=0.5,
        max_book_gross=1.0,
        gross_cap=2.0,
        net_cap=0.5,
        per_name_cap=0.1,
        default_band_up=0.03,
        default_band_down=0.01,
        band_overrides=(("BBG000B9XRY4", 0.05, 0.02),),
        aggregate_drift_threshold=0.5,
        drawdown_delever=DrawdownDeleverCurve(
            start_drawdown=0.05,
            end_drawdown=0.25,
            floor_multiplier=0.4,
        ),
    )


def test_malformed_drawdown_delever_fails_closed(tmp_path):
    path = _write(tmp_path, """
        [drawdown_delever]
        start_drawdown = 0.25
        end_drawdown = 0.05
        floor_multiplier = 0.4

        [[sleeves]]
        name = "trend"
        wheel_filename = "trend.whl"
        risk_share = 1.0
        group = "Floor"
    """)
    with pytest.raises(ValueError, match="drawdown"):
        load_book_config(path)


def test_defaults_applied_when_keys_omitted(tmp_path):
    """Omitted optional keys fall back to BookConfig's defaults."""
    path = _write(tmp_path, """
        [[sleeves]]
        name = "trend"
        wheel_filename = "trend.whl"
        risk_share = 1.0
        group = "Floor"
    """)

    book = load_book_config(path)

    assert book.base_currency == "EUR"
    assert book.book_vol_target == 0.09
    assert book.sleeve_reversion_fraction == 1.0
    assert book.max_book_gross == 1.0
    assert book.gross_cap is None
    assert book.default_band_up == 0.02
    assert book.sleeves[0].weight_band_down == 0.0
    assert book.sleeves[0].weight_band_up == 0.0
    assert book.band_overrides == ()
    assert book.tail_convexity_budget is None


def test_tail_convexity_budget_loads(tmp_path):
    path = _write(tmp_path, """
        [[sleeves]]
        name = "trend"
        wheel_filename = "trend.whl"
        risk_share = 0.6
        group = "Floor"

        [[sleeves]]
        name = "tail"
        wheel_filename = "tail.whl"
        risk_share = 0.0
        group = "Target"

        [tail_convexity_budget]
        attachment = -0.20
        coverage_target = 0.01
        annual_carry_budget = 0.0075

        [[tail_convexity_budget.candidates]]
        sleeve = "tail"
        payoff_at_attachment = 0.20
        annual_carry = 0.08
        crisis_reliability = 0.75
        capacity_risk_share = 0.05
    """)

    book = load_book_config(path)

    assert book.tail_convexity_budget == TailConvexityBudget(
        attachment=-0.20,
        coverage_target=0.01,
        annual_carry_budget=0.0075,
        candidates=(
            ConvexityBudgetCandidate(
                sleeve=SleeveName("tail"),
                payoff_at_attachment=0.20,
                annual_carry=0.08,
                crisis_reliability=0.75,
                capacity_risk_share=0.05,
            ),
        ),
    )
    assert book.allocator_risk_shares()[SleeveName("tail")] == pytest.approx(0.05)


def test_tail_convexity_budget_must_be_table(tmp_path):
    path = _write(tmp_path, """
        tail_convexity_budget = 1.0

        [[sleeves]]
        name = "trend"
        wheel_filename = "trend.whl"
        risk_share = 1.0
        group = "Floor"
    """)

    with pytest.raises(BookConfigError, match="tail_convexity_budget must be a table"):
        load_book_config(path)


def test_missing_file_fails_closed(tmp_path):
    with pytest.raises(BookConfigError, match="cannot read"):
        load_book_config(tmp_path / "nope.toml")


def test_malformed_toml_fails_closed(tmp_path):
    path = _write(tmp_path, "this is = = not valid toml [[[")
    with pytest.raises(BookConfigError, match="malformed"):
        load_book_config(path)


def test_missing_required_sleeve_key_fails_closed(tmp_path):
    """A sleeve without wheel_filename is a malformed entry, not a silent skip."""
    path = _write(tmp_path, """
        [[sleeves]]
        name = "trend"
        risk_share = 1.0
        group = "Floor"
    """)
    with pytest.raises(BookConfigError, match="malformed sleeve"):
        load_book_config(path)


def test_legacy_budget_key_fails_closed(tmp_path):
    """Forward-first schema: static capital budget is removed, no shim."""
    path = _write(tmp_path, """
        [[sleeves]]
        name = "trend"
        wheel_filename = "trend.whl"
        budget = 1.0
        group = "Floor"
    """)
    with pytest.raises(BookConfigError, match="malformed sleeve"):
        load_book_config(path)


def test_no_sleeves_surfaces_book_invariant(tmp_path):
    """An empty book hits BookConfig's own 'at least one sleeve' guard."""
    path = _write(tmp_path, 'base_currency = "EUR"\n')
    with pytest.raises(ValueError, match="at least one sleeve"):
        load_book_config(path)


class TestFindBookConfig:
    """Discovery: walk up from a start dir to find book.toml."""

    def test_found_in_start_dir(self, tmp_path):
        (tmp_path / "book.toml").write_text(_MINIMAL)
        assert find_book_config(tmp_path) == tmp_path / "book.toml"

    def test_walks_up_to_a_parent(self, tmp_path):
        (tmp_path / "book.toml").write_text(_MINIMAL)
        nested = tmp_path / "deploy" / "eu"
        nested.mkdir(parents=True)
        assert find_book_config(nested) == tmp_path / "book.toml"

    def test_missing_everywhere_fails_closed(self, tmp_path):
        nested = tmp_path / "a" / "b"
        nested.mkdir(parents=True)
        with pytest.raises(BookConfigError, match="no book.toml"):
            find_book_config(nested)
