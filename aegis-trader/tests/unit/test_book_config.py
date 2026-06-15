"""Unit tests for BookConfig — zero Nautilus."""

import pytest

from aegis_trader.domain.book_config import (
    BookConfig,
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
                coverage_target_units=3.0,
                unit_payoff_fraction_at_20_down=0.01,
                candidates=(
                    ConvexityBudgetCandidate(
                        sleeve=SleeveName("dear_tail"),
                        expected_annual_payoff=0.20,
                        annual_carry=0.10,
                        crisis_reliability=0.5,
                        convexity_units_per_risk_share=10.0,
                        capacity_risk_share=0.20,
                    ),
                    ConvexityBudgetCandidate(
                        sleeve=SleeveName("cheap_tail"),
                        expected_annual_payoff=0.30,
                        annual_carry=0.10,
                        crisis_reliability=0.9,
                        convexity_units_per_risk_share=20.0,
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


class TestBookConfigCapsAndBands:
    """Caps and bands declaration.

    Cap *provenance* (caps never exceeding the bundles' research-validated
    ceilings) is bundle-grounded and lives in test_cap_provenance.py — it is no
    longer a self-referential check on BookConfig.
    """

    def test_default_bands(self):
        """Default bands are 0.02 symmetric."""
        book = BookConfig(sleeves=(make_sleeve("trend"),))
        assert book.band_for("ANY_FIGI") == (0.02, 0.02)

    def test_band_override(self):
        """Per-FIGI asymmetric band override."""
        book = BookConfig(
            sleeves=(make_sleeve("trend"),),
            band_overrides=(("FIGI_TAIL", 0.01, 0.05),),
        )
        assert book.band_for("FIGI_TAIL") == (0.01, 0.05)
        assert book.band_for("OTHER") == (0.02, 0.02)

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
