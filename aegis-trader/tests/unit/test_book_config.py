"""Unit tests for BookConfig — zero Nautilus."""

import pytest

from aegis_trader.domain.book_config import (
    BookConfig,
    CostModelConfig,
    BorrowConfig,
    MarginInterestConfig,
    ConvexityBudgetCandidate,
    DrawdownDeleverCurve,
    RiskGroup,
    SleeveConfig,
    TailConvexityBudget,
)
from aegis_trader.domain.types import SleeveName


def make_sleeve(
    name: str,
    wheel: str = "test.whl",
    risk_share: float = 1.0,
    group: RiskGroup = RiskGroup.FLOOR,
    weight_band_down: float = 0.0,
    weight_band_up: float = 0.0,
) -> SleeveConfig:
    return SleeveConfig(
        name=SleeveName(name),
        wheel_filename=wheel,
        risk_share=risk_share,
        group=group,
        weight_band_down=weight_band_down,
        weight_band_up=weight_band_up,
    )


class TestCostModelConfig:
    def test_zero_cost_default_has_no_friction(self):
        book = BookConfig(sleeves=(make_sleeve("trend"),))

        assert book.costs == CostModelConfig.zero()

    def test_populated_cost_model_records_declared_friction(self):
        costs = CostModelConfig(
            per_share_commission=0.0035,
            min_commission_per_order=1.0,
            max_commission_pct=0.01,
            slippage_probability=0.25,
            slippage_seed=42,
            margin_interest=MarginInterestConfig((('GBP', 0.06), ('usd', 0.05))),
            borrow=BorrowConfig(0.015),
        )

        assert costs.per_share_commission == 0.0035
        assert costs.min_commission_per_order == 1.0
        assert costs.max_commission_pct == 0.01
        assert costs.slippage_probability == 0.25
        assert costs.slippage_seed == 42
        assert costs.margin_interest.annual_rate_for("GBP") == 0.06
        assert costs.margin_interest.annual_rate_for("USD") == 0.05
        assert costs.margin_interest.annual_rate_for("EUR") == 0.0
        assert costs.borrow.annual_rate == 0.015

    @pytest.mark.parametrize(
        ("field", "value", "message"),
        (
            ("per_share_commission", -0.01, "per_share_commission"),
            ("min_commission_per_order", -0.01, "min_commission_per_order"),
            ("max_commission_pct", -0.01, "max_commission_pct"),
            ("slippage_probability", -0.01, "slippage_probability"),
            ("slippage_probability", 1.01, "slippage_probability"),
            ("slippage_seed", -1, "slippage_seed"),
            ("slippage_seed", 1.5, "slippage_seed"),
            ("borrow", {"rate": -0.01}, "borrow"),
            ("borrow", {"rate": float("nan")}, "borrow"),
        ),
    )
    def test_invalid_cost_values_rejected(self, field, value, message):
        with pytest.raises(ValueError, match=message):
            CostModelConfig(**{field: value})

    @pytest.mark.parametrize(
        "rates",
        (
            (("GBP", -0.01),),
            (("GBP", float("nan")),),
            (("GBP", 0.05), ("gbp", 0.06)),
        ),
    )
    def test_invalid_margin_interest_rates_rejected(self, rates):
        with pytest.raises(ValueError, match="margin_interest"):
            MarginInterestConfig(rates)


class TestBookConfig:
    def test_single_sleeve_defaults(self):
        book = BookConfig(sleeves=(make_sleeve("trend"),))
        assert book.sleeve_count == 1
        assert book.base_currency == "EUR"
        assert book.book_vol_target == 0.09
        assert book.sleeve_reversion_fraction == 1.0
        assert book.sleeves[0].name == SleeveName("trend")
        assert book.sleeves[0].risk_share == 1.0
        assert book.sleeves[0].group == RiskGroup.FLOOR
        assert book.sleeves[0].weight_band_down == 0.0
        assert book.sleeves[0].weight_band_up == 0.0

    def test_duplicate_sleeve_names_rejected(self):
        with pytest.raises(ValueError, match="duplicate"):
            BookConfig(sleeves=(make_sleeve("a"), make_sleeve("a")))

    def test_empty_sleeves_rejected(self):
        with pytest.raises(ValueError, match="at least one sleeve"):
            BookConfig(sleeves=())

    def test_custom_base_currency_and_vol_target(self):
        book = BookConfig(
            sleeves=(make_sleeve("trend"),),
            base_currency="USD",
            book_vol_target=0.12,
        )
        assert book.base_currency == "USD"
        assert book.book_vol_target == 0.12

    def test_risk_groups_are_domain_values(self):
        sleeve = make_sleeve("tail", group=RiskGroup.TARGET)
        assert sleeve.group == RiskGroup.TARGET

    def test_positive_total_risk_share_required(self):
        with pytest.raises(ValueError, match="positive total risk_share"):
            BookConfig(sleeves=(make_sleeve("a", risk_share=0.0),))

    def test_negative_risk_share_rejected(self):
        with pytest.raises(ValueError, match="risk_share"):
            make_sleeve("a", risk_share=-0.1)

    def test_invalid_vol_target_rejected(self):
        with pytest.raises(ValueError, match="book_vol_target"):
            BookConfig(sleeves=(make_sleeve("a"),), book_vol_target=0.0)

    def test_sleeve_weight_bands_and_reversion_fraction_configured(self):
        book = BookConfig(
            sleeves=(make_sleeve("a", weight_band_down=0.01, weight_band_up=0.03),),
            sleeve_reversion_fraction=0.5,
        )

        assert book.sleeve_reversion_fraction == 0.5
        assert book.sleeves[0].weight_band_down == 0.01
        assert book.sleeves[0].weight_band_up == 0.03

    def test_invalid_sleeve_weight_band_rejected(self):
        with pytest.raises(ValueError, match="weight_band_down"):
            make_sleeve("a", weight_band_down=-0.01)

    def test_invalid_sleeve_reversion_fraction_rejected(self):
        with pytest.raises(ValueError, match="sleeve_reversion_fraction"):
            BookConfig(sleeves=(make_sleeve("a"),), sleeve_reversion_fraction=0.0)

    def test_drawdown_delever_curve_maps_drawdown_to_exposure_multiplier(self):
        curve = DrawdownDeleverCurve(
            start_drawdown=0.05,
            end_drawdown=0.25,
            floor_multiplier=0.4,
        )
        assert curve.multiplier_for(0.00) == pytest.approx(1.0)
        assert curve.multiplier_for(0.15) == pytest.approx(0.7)
        assert curve.multiplier_for(0.25) == pytest.approx(0.4)

    def test_invalid_drawdown_delever_curve_rejected(self):
        with pytest.raises(ValueError, match="drawdown"):
            DrawdownDeleverCurve(
                start_drawdown=0.25,
                end_drawdown=0.05,
                floor_multiplier=0.4,
            )
        with pytest.raises(ValueError, match="floor_multiplier"):
            DrawdownDeleverCurve(
                start_drawdown=0.05,
                end_drawdown=0.25,
                floor_multiplier=1.2,
            )

    def test_tail_convexity_budget_sets_target_shares_and_expansion_defaults_zero(self):
        book = BookConfig(
            sleeves=(
                make_sleeve("trend", risk_share=0.6, group=RiskGroup.FLOOR),
                make_sleeve("cheap_tail", risk_share=0.9, group=RiskGroup.TARGET),
                make_sleeve("dear_tail", risk_share=0.9, group=RiskGroup.TARGET),
                make_sleeve("market_neutral", risk_share=0.4, group=RiskGroup.EXPANSION),
            ),
            tail_convexity_budget=TailConvexityBudget(
                attachment=-0.20,
                coverage_target=0.03,
                candidates=(
                    ConvexityBudgetCandidate(
                        sleeve=SleeveName("dear_tail"),
                        payoff_at_attachment=0.10,
                        annual_carry=0.10,
                        crisis_reliability=0.5,
                        capacity_risk_share=0.20,
                    ),
                    ConvexityBudgetCandidate(
                        sleeve=SleeveName("cheap_tail"),
                        payoff_at_attachment=0.20,
                        annual_carry=0.10,
                        crisis_reliability=0.9,
                        capacity_risk_share=0.10,
                    ),
                ),
            ),
        )

        shares = book.allocator_risk_shares()

        assert shares[SleeveName("trend")] == pytest.approx(0.6)
        assert shares[SleeveName("cheap_tail")] == pytest.approx(0.10)
        assert shares[SleeveName("dear_tail")] == pytest.approx(0.10)
        assert shares[SleeveName("market_neutral")] == 0.0

    def test_tail_convexity_annual_carry_budget_caps_the_fill(self):
        cheap = ConvexityBudgetCandidate(
            sleeve=SleeveName("tail"),
            payoff_at_attachment=0.20,
            annual_carry=0.10,
            crisis_reliability=1.0,
            capacity_risk_share=0.50,
        )
        # Coverage alone wants 0.15 risk share (0.03 / 0.20); the premium budget
        # of 0.01 NAV/yr at 0.10 carry per risk share caps the fill at 0.10.
        budgeted = TailConvexityBudget(
            attachment=-0.20,
            coverage_target=0.03,
            annual_carry_budget=0.01,
            candidates=(cheap,),
        )
        assert budgeted.risk_shares()[SleeveName("tail")] == pytest.approx(0.10)

        # Without the premium ceiling the same budget fills coverage to 0.15.
        uncapped = TailConvexityBudget(
            attachment=-0.20,
            coverage_target=0.03,
            candidates=(cheap,),
        )
        assert uncapped.risk_shares()[SleeveName("tail")] == pytest.approx(0.15)

    def test_tail_convexity_attachment_must_be_a_downside_move(self):
        with pytest.raises(ValueError, match="attachment"):
            TailConvexityBudget(
                attachment=0.20,
                coverage_target=0.0,
                candidates=(),
            )


class TestBookConfigCaps:
    """Caps declaration.

    Cap *provenance* (caps never exceeding the bundles' research-validated
    ceilings) is bundle-grounded and lives in test_cap_provenance.py — it is no
    longer a self-referential check on BookConfig.
    """

    def test_caps_default_none(self):
        """Caps default to None (unlimited)."""
        book = BookConfig(sleeves=(make_sleeve("trend"),))
        assert book.gross_cap is None
        assert book.net_cap is None
        assert book.per_name_cap is None
        assert book.aggregate_drift_threshold is None

    def test_custom_caps(self):
        """All caps can be set."""
        book = BookConfig(
            sleeves=(make_sleeve("trend"),),
            gross_cap=1.5,
            net_cap=0.8,
            per_name_cap=0.15,
            aggregate_drift_threshold=0.05,
        )
        assert book.gross_cap == 1.5
        assert book.net_cap == 0.8
        assert book.per_name_cap == 0.15
        assert book.aggregate_drift_threshold == 0.05


def test_starting_balances_normalize_currency_and_sort():
    """Per-currency starting balances are upper-cased and sorted for determinism."""
    book = BookConfig(
        sleeves=(make_sleeve("trend"),),
        starting_balances=(("usd", 500_000.0), ("EUR", 1_000_000.0)),
    )
    assert book.starting_balances == (("EUR", 1_000_000.0), ("USD", 500_000.0))


def test_starting_balances_reject_duplicate_currency():
    with pytest.raises(ValueError, match="unique"):
        BookConfig(
            sleeves=(make_sleeve("trend"),),
            starting_balances=(("EUR", 1.0), ("eur", 2.0)),
        )


def test_starting_balances_reject_negative_amount():
    with pytest.raises(ValueError, match="non-negative"):
        BookConfig(
            sleeves=(make_sleeve("trend"),),
            starting_balances=(("EUR", -1.0),),
        )
