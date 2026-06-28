"""Unit tests for the pure-domain rebalancer — zero Nautilus.

The rebalancer works in dimensionless weight space: it nets sleeve targets,
applies bands/caps, and emits signed ``WeightDelta``s.  Turning a delta into a
native share count is the sizing step's job (``sizing.size_deltas``), covered in
test_sizing.py; the composition is exercised by ``TestRebalancePipeline`` below.
"""

import pandas as pd
import pytest

from aegis_runtime import DriftBand
from aegis_trader.domain.book_config import BookConfig, DrawdownDeleverCurve, SleeveConfig
from aegis_trader.domain.rebalancer import (
    _gate_book_caps,
    rebalance as _rebalance,
    rebalance_plan as _rebalance_plan,
)
from aegis_trader.domain.sizing import InstrumentSizing, size_deltas
from aegis_trader.domain.types import OrderSide, SleeveName, WeightDelta
from nautilus_trader.model.identifiers import InstrumentId


def _iid(symbol: str) -> InstrumentId:
    return InstrumentId.from_str(f"{symbol}.TEST")



def make_book(sleeves: list[tuple[str, str, float]], **kwargs) -> BookConfig:
    return BookConfig(
        sleeves=tuple(
            SleeveConfig(name=SleeveName(n), wheel_filename=w, risk_share=b)
            for n, w, b in sleeves
        ),
        **kwargs,
    )


def _target(figi_to_weight: dict[str, float]) -> pd.DataFrame:
    """Build a one-row target-weight DataFrame."""
    df = pd.DataFrame(
        {_iid(k): [v] for k, v in figi_to_weight.items()},
        index=pd.DatetimeIndex(["2025-06-01"], name="timestamp"),
    )
    df.columns.name = "instrument_id"
    return df


def _band_map(
    sleeve_targets: dict[SleeveName, pd.DataFrame],
    realized_weights: dict[InstrumentId, float] | None,
    band: DriftBand,
) -> dict[InstrumentId, DriftBand]:
    instrument_ids: set[InstrumentId] = set()
    for target in sleeve_targets.values():
        instrument_ids.update(target.columns)
    if realized_weights is not None:
        instrument_ids.update(realized_weights)
    return {instrument_id: band for instrument_id in instrument_ids}


def _bands(*instrument_ids: InstrumentId, up: float, down: float) -> dict[InstrumentId, DriftBand]:
    return {instrument_id: DriftBand(up=up, down=down) for instrument_id in instrument_ids}


def rebalance(
    sleeve_targets: dict[SleeveName, pd.DataFrame],
    book: BookConfig,
    *,
    instrument_bands: dict[InstrumentId, DriftBand] | None = None,
    realized_weights: dict[InstrumentId, float] | None = None,
    **kwargs,
) -> tuple[WeightDelta, ...]:
    if instrument_bands is None:
        instrument_bands = _band_map(sleeve_targets, realized_weights, DriftBand.symmetric(0.0))
    return _rebalance(
        sleeve_targets,
        book,
        instrument_bands=instrument_bands,
        realized_weights=realized_weights,
        **kwargs,
    )


def rebalance_plan(
    sleeve_targets: dict[SleeveName, pd.DataFrame],
    book: BookConfig,
    *,
    instrument_bands: dict[InstrumentId, DriftBand] | None = None,
    realized_weights: dict[InstrumentId, float] | None = None,
    **kwargs,
):
    if instrument_bands is None:
        instrument_bands = _band_map(sleeve_targets, realized_weights, DriftBand.symmetric(0.0))
    return _rebalance_plan(
        sleeve_targets,
        book,
        instrument_bands=instrument_bands,
        realized_weights=realized_weights,
        **kwargs,
    )


class TestRebalanceSingleSleeve:
    """Tracer slice: one sleeve, simple weight → WeightDelta, no bands/gates."""

    @staticmethod
    def _call(target: pd.DataFrame, book: BookConfig) -> tuple[WeightDelta, ...]:
        return rebalance({book.sleeves[0].name: target}, book)

    def test_single_figi_buy(self):
        book = make_book([("trend", "trend_lse-abc123.whl", 1.0)])
        result = self._call(_target({"BBG000B9XRY4": 0.5}), book)
        assert len(result) == 1
        assert result[0].instrument_id == _iid("BBG000B9XRY4")
        assert result[0].side == OrderSide.BUY
        assert result[0].delta == pytest.approx(0.5)

    def test_single_figi_sell(self):
        book = make_book([("trend", "trend_lse-abc123.whl", 1.0)])
        result = self._call(_target({"BBG000B9XRY4": -0.3}), book)
        assert len(result) == 1
        assert result[0].side == OrderSide.SELL
        assert result[0].delta == pytest.approx(-0.3)

    def test_budget_scales_delta(self):
        book = make_book([("trend", "trend_lse-abc123.whl", 0.5)])
        result = self._call(_target({"BBG000B9XRY4": 0.5}), book)
        assert result[0].delta == pytest.approx(0.25)

    def test_zero_weight_yields_no_delta(self):
        book = make_book([("trend", "trend_lse-abc123.whl", 1.0)])
        assert self._call(_target({"BBG000B9XRY4": 0.0}), book) == ()

    def test_near_zero_weight_filtered(self):
        book = make_book([("trend", "trend_lse-abc123.whl", 1.0)])
        assert self._call(_target({"BBG000B9XRY4": 1e-13}), book) == ()

    def test_multiple_figis(self):
        book = make_book([("trend", "trend_lse-abc123.whl", 1.0)])
        result = self._call(_target({"FIGI_A": 0.4, "FIGI_B": -0.2}), book)
        assert len(result) == 2
        by_figi = {d.instrument_id.symbol.value: d for d in result}
        assert by_figi["FIGI_A"].side == OrderSide.BUY
        assert by_figi["FIGI_A"].delta == pytest.approx(0.4)
        assert by_figi["FIGI_B"].side == OrderSide.SELL
        assert by_figi["FIGI_B"].delta == pytest.approx(-0.2)

    def test_uses_latest_row(self):
        book = make_book([("trend", "trend_lse-abc123.whl", 1.0)])
        target = pd.DataFrame(
            {_iid("FIGI_A"): [0.1, 0.2, 0.5]},
            index=pd.DatetimeIndex(["2025-06-01", "2025-06-02", "2025-06-03"], name="timestamp"),
        )
        target.columns.name = "instrument_id"
        result = self._call(target, book)
        assert len(result) == 1
        assert result[0].delta == pytest.approx(0.5)

    def test_empty_target_returns_empty(self):
        book = make_book([("trend", "trend_lse-abc123.whl", 1.0)])
        target = pd.DataFrame(
            {_iid("FIGI_A"): pd.Series([], dtype=float)},
            index=pd.DatetimeIndex([], name="timestamp"),
        )
        target.columns.name = "instrument_id"
        assert self._call(target, book) == ()


class TestRebalanceMultiSleeve:
    """Slice 2: multi-sleeve netting + budget scaling (weight space)."""

    def test_overlapping_sleeves_net(self):
        book = make_book([("trend", "trend-abc.whl", 0.6), ("carry", "carry-def.whl", 0.4)])
        # 0.6*0.5 - 0.4*0.2 = 0.30 - 0.08 = 0.22
        result = rebalance(
            {book.sleeves[0].name: _target({"FIGI_A": 0.5}),
             book.sleeves[1].name: _target({"FIGI_A": -0.2})},
            book,
        )
        assert len(result) == 1
        assert result[0].instrument_id == _iid("FIGI_A")
        assert result[0].side == OrderSide.BUY
        assert result[0].delta == pytest.approx(0.22)

    def test_overlap_cancels_to_zero(self):
        book = make_book([("trend", "trend-abc.whl", 0.5), ("carry", "carry-def.whl", 0.5)])
        result = rebalance(
            {book.sleeves[0].name: _target({"FIGI_A": 0.4}),
             book.sleeves[1].name: _target({"FIGI_A": -0.4})},
            book,
        )
        assert result == ()

    def test_overlap_both_positive_sum(self):
        book = make_book([("trend", "trend-abc.whl", 0.6), ("carry", "carry-def.whl", 0.4)])
        # 0.30 + 0.10 = 0.40
        result = rebalance(
            {book.sleeves[0].name: _target({"FIGI_A": 0.5}),
             book.sleeves[1].name: _target({"FIGI_A": 0.25})},
            book,
        )
        assert len(result) == 1
        assert result[0].delta == pytest.approx(0.40)

    def test_disjoint_sleeves_concatenate(self):
        book = make_book([("trend", "trend-abc.whl", 0.6), ("carry", "carry-def.whl", 0.4)])
        result = rebalance(
            {book.sleeves[0].name: _target({"FIGI_A": 0.5}),
             book.sleeves[1].name: _target({"FIGI_B": -0.3})},
            book,
        )
        assert len(result) == 2
        by_figi = {d.instrument_id.symbol.value: d for d in result}
        assert by_figi["FIGI_A"].delta == pytest.approx(0.30)
        assert by_figi["FIGI_B"].delta == pytest.approx(-0.12)

    def test_mixed_overlap_and_disjoint(self):
        book = make_book([("trend", "trend-abc.whl", 0.5), ("carry", "carry-def.whl", 0.5)])
        result = rebalance(
            {book.sleeves[0].name: _target({"FIGI_A": 0.4, "FIGI_C": 0.3}),
             book.sleeves[1].name: _target({"FIGI_A": -0.1, "FIGI_B": 0.2})},
            book,
        )
        assert len(result) == 3
        by_figi = {d.instrument_id.symbol.value: d for d in result}
        assert by_figi["FIGI_A"].delta == pytest.approx(0.15)
        assert by_figi["FIGI_B"].delta == pytest.approx(0.10)
        assert by_figi["FIGI_C"].delta == pytest.approx(0.15)
        for d in result:
            assert d.side == OrderSide.BUY

    def test_risk_share_scales_before_netting_during_warmup(self):
        book = make_book([("trend", "trend-abc.whl", 0.6), ("carry", "carry-def.whl", 0.0)])
        result = rebalance(
            {book.sleeves[0].name: _target({"FIGI_A": 0.5}),
             book.sleeves[1].name: _target({"FIGI_A": 0.8})},
            book,
        )
        assert len(result) == 1
        assert result[0].delta == pytest.approx(0.30)

    def test_realized_vols_scale_high_vol_sleeve_down_before_netting(self):
        book = BookConfig(
            sleeves=(
                SleeveConfig(name=SleeveName("low"), wheel_filename="low.whl", risk_share=0.5),
                SleeveConfig(name=SleeveName("high"), wheel_filename="high.whl", risk_share=0.5),
            ),
            book_vol_target=0.10,
        )
        result = rebalance(
            {book.sleeves[0].name: _target({"LOW": 1.0}),
             book.sleeves[1].name: _target({"HIGH": 1.0})},
            book,
            realized_vols={book.sleeves[0].name: 0.10, book.sleeves[1].name: 0.20},
        )
        by_figi = {d.instrument_id.symbol.value: d.delta for d in result}
        assert by_figi["HIGH"] == pytest.approx(by_figi["LOW"] / 2.0)

    def test_sleeve_weight_bands_use_previous_applied_weight(self):
        book = BookConfig(
            sleeves=(
                SleeveConfig(
                    name=SleeveName("trend"),
                    wheel_filename="trend.whl",
                    risk_share=0.5,
                    weight_band_down=0.01,
                    weight_band_up=0.01,
                ),
                SleeveConfig(
                    name=SleeveName("carry"),
                    wheel_filename="carry.whl",
                    risk_share=0.5,
                    weight_band_down=0.01,
                    weight_band_up=0.01,
                ),
            ),
            book_vol_target=0.09,
            sleeve_reversion_fraction=0.5,
            max_book_gross=2.0,  # headroom: isolate the band logic from the gross clamp
        )
        previous = {book.sleeves[0].name: 0.6363961030678927, book.sleeves[1].name: 0.6363961030678927}

        plan = rebalance_plan(
            {book.sleeves[0].name: _target({"TREND": 1.0}),
             book.sleeves[1].name: _target({"CARRY": 1.0})},
            book,
            realized_vols={book.sleeves[0].name: 0.10, book.sleeves[1].name: 0.102},
            previous_sleeve_weights=previous,
        )

        assert plan.applied_sleeve_weights[book.sleeves[0].name] == pytest.approx(previous[book.sleeves[0].name])
        assert plan.applied_sleeve_weights[book.sleeves[1].name] == pytest.approx(0.630156925586835)
        by_figi = {d.instrument_id.symbol.value: d.delta for d in plan.deltas}
        assert by_figi["TREND"] == pytest.approx(previous[book.sleeves[0].name])
        assert by_figi["CARRY"] == pytest.approx(0.630156925586835)

    def test_covariance_scales_correlated_sleeves_before_netting(self):
        book = make_book([("trend", "trend.whl", 0.5), ("carry", "carry.whl", 0.5)])
        uncorrelated = rebalance(
            {book.sleeves[0].name: _target({"TREND": 1.0}),
             book.sleeves[1].name: _target({"CARRY": 1.0})},
            book,
            realized_covariance={
                book.sleeves[0].name: {book.sleeves[0].name: 0.10**2, book.sleeves[1].name: 0.0},
                book.sleeves[1].name: {book.sleeves[0].name: 0.0, book.sleeves[1].name: 0.10**2},
            },
        )
        correlated = rebalance(
            {book.sleeves[0].name: _target({"TREND": 1.0}),
             book.sleeves[1].name: _target({"CARRY": 1.0})},
            book,
            realized_covariance={
                book.sleeves[0].name: {
                    book.sleeves[0].name: 0.10**2,
                    book.sleeves[1].name: 0.90 * 0.10 * 0.10,
                },
                book.sleeves[1].name: {
                    book.sleeves[0].name: 0.90 * 0.10 * 0.10,
                    book.sleeves[1].name: 0.10**2,
                },
            },
        )

        assert sum(abs(d.delta) for d in correlated) < sum(abs(d.delta) for d in uncorrelated)

    def test_three_sleeves_complex_netting(self):
        book = make_book(
            [("a", "a.whl", 0.4), ("b", "b.whl", 0.3), ("c", "c.whl", 0.3)],
        )
        result = rebalance(
            {book.sleeves[0].name: _target({"X": 0.5, "Y": -0.2}),
             book.sleeves[1].name: _target({"X": -0.3, "Z": 0.4}),
             book.sleeves[2].name: _target({"Y": 0.3, "Z": -0.1})},
            book,
        )
        by_figi = {d.instrument_id.symbol.value: d for d in result}
        assert by_figi["X"].delta == pytest.approx(0.11)
        assert by_figi["Y"].delta == pytest.approx(0.01)
        assert by_figi["Z"].delta == pytest.approx(0.09)

    def test_sleeve_missing_from_targets_skipped(self):
        book = make_book([("trend", "trend.whl", 0.5), ("carry", "carry.whl", 0.5)])
        result = rebalance({book.sleeves[0].name: _target({"FIGI_A": 0.4})}, book)
        assert len(result) == 1
        assert result[0].delta == pytest.approx(0.20)

    def test_sleeve_empty_target_skipped(self):
        book = make_book([("trend", "trend.whl", 0.5), ("carry", "carry.whl", 0.5)])
        empty = pd.DataFrame(
            {_iid("FIGI_B"): pd.Series([], dtype=float)},
            index=pd.DatetimeIndex([], name="timestamp"),
        )
        empty.columns.name = "instrument_id"
        result = rebalance(
            {book.sleeves[0].name: _target({"FIGI_A": 0.4}), book.sleeves[1].name: empty},
            book,
        )
        assert len(result) == 1
        assert result[0].delta == pytest.approx(0.20)


class TestRebalanceSlice4:
    """Slice 4: realised-book gate, asymmetric bands, caps, aggregate drift."""

    @staticmethod
    def _book(name: str = "trend", budget: float = 1.0, **kwargs) -> BookConfig:
        return BookConfig(
            sleeves=(SleeveConfig(name=SleeveName(name), wheel_filename=f"{name}.whl", risk_share=budget),),
            **kwargs,
        )

    @staticmethod
    def _bands(width: float, *symbols: str) -> dict[InstrumentId, DriftBand]:
        return _bands(*(_iid(symbol) for symbol in symbols), up=width, down=width)

    def test_band_gate_suppresses_small_drift(self):
        book = self._book()
        result = rebalance({book.sleeves[0].name: _target({"FIGI_A": 0.50})}, book,
                           instrument_bands=self._bands(0.02, "FIGI_A"),
                           realized_weights={_iid("FIGI_A"): 0.51})
        assert result == ()

    def test_band_gate_holds_at_inclusive_boundary(self):
        book = self._book()
        result = rebalance({book.sleeves[0].name: _target({"FIGI_A": 0.50})}, book,
                           instrument_bands=self._bands(0.02, "FIGI_A"),
                           realized_weights={_iid("FIGI_A"): 0.52})
        assert result == ()

    def test_band_gate_trades_when_outside_band(self):
        book = self._book()
        result = rebalance({book.sleeves[0].name: _target({"FIGI_A": 0.50})}, book,
                           instrument_bands=self._bands(0.02, "FIGI_A"),
                           realized_weights={_iid("FIGI_A"): 0.55})
        assert len(result) == 1
        assert result[0].side == OrderSide.SELL
        assert result[0].delta == pytest.approx(-0.05)

    def test_deltas_emitted_in_deterministic_figi_order(self):
        """Reproducibility (aegis-rd-10d): deltas come out in a stable figi-sorted
        order, not the hash-seed-dependent order of the netted-vs-realised figi
        union — otherwise the order-submission sequence (and the backtest) varies
        run-to-run."""
        book = self._book()
        target = _target({"FIGI_C": 0.20, "FIGI_A": 0.20, "FIGI_D": 0.20})
        result = rebalance(
            {book.sleeves[0].name: target}, book,
            realized_weights={_iid("FIGI_B"): 0.20, _iid("FIGI_A"): 0.05},
        )
        figis = [d.instrument_id.symbol.value for d in result]
        assert figis == ["FIGI_A", "FIGI_B", "FIGI_C", "FIGI_D"]  # sorted, stable

    def test_asymmetric_band_tail(self):
        book = self._book()
        target = _target({"FIGI_TAIL": 0.50})
        result_up = rebalance({book.sleeves[0].name: target}, book,
                              instrument_bands=_bands(_iid("FIGI_TAIL"), up=0.01, down=0.05),
                              realized_weights={_iid("FIGI_TAIL"): 0.52})
        assert len(result_up) == 1
        assert result_up[0].side == OrderSide.SELL
        result_down = rebalance({book.sleeves[0].name: target}, book,
                                instrument_bands=_bands(_iid("FIGI_TAIL"), up=0.01, down=0.05),
                                realized_weights={_iid("FIGI_TAIL"): 0.48})
        assert result_down == ()

    def test_sub_band_new_position_is_gated(self):
        book = self._book()
        result = rebalance({book.sleeves[0].name: _target({"FIGI_A": 0.01})}, book,
                           instrument_bands=self._bands(0.02, "FIGI_A"),
                           realized_weights=None)
        assert result == ()

    def test_new_position_opens_when_outside_band(self):
        book = self._book()
        result = rebalance({book.sleeves[0].name: _target({"FIGI_A": 0.03})}, book,
                           instrument_bands=self._bands(0.02, "FIGI_A"),
                           realized_weights=None)
        assert len(result) == 1
        assert result[0].delta == pytest.approx(0.03)

    def test_unowned_realized_position_trades_straight_to_flat(self):
        book = self._book()
        result = rebalance(
            {book.sleeves[0].name: _target({"FIGI_A": 0.50})},
            book,
            instrument_bands=self._bands(0.02, "FIGI_A"),
            realized_weights={_iid("FIGI_Z"): 0.04},
        )

        by_figi = {delta.instrument_id.symbol.value: delta for delta in result}
        assert by_figi["FIGI_Z"].delta == pytest.approx(-0.04)

    def test_per_name_cap_breach_band_creates_corrective_verified(self):
        book = self._book(per_name_cap=0.10)
        result = rebalance({book.sleeves[0].name: _target({"FIGI_A": 0.08})}, book,
                           instrument_bands=self._bands(0.02, "FIGI_A"),
                           realized_weights={_iid("FIGI_A"): 0.12})
        assert len(result) == 1
        assert result[0].side == OrderSide.SELL
        assert result[0].delta == pytest.approx(-0.04)

    def test_per_name_cap_breach_band_suppressed_corrective_order(self):
        book = self._book(per_name_cap=0.10)
        result = rebalance({book.sleeves[0].name: _target({"FIGI_A": 0.08})}, book,
                           instrument_bands=self._bands(0.10, "FIGI_A"),
                           realized_weights={_iid("FIGI_A"): 0.12})
        assert len(result) == 1
        assert result[0].side == OrderSide.SELL
        assert result[0].delta == pytest.approx(-0.02)  # widen to cap 0.10

    def test_per_name_cap_breach_unfixable_fails_closed(self):
        book = self._book(per_name_cap=0.10)
        with pytest.raises(ValueError, match="unfixable"):
            rebalance({book.sleeves[0].name: _target({"FIGI_A": 0.15})}, book,
                      instrument_bands=self._bands(0.10, "FIGI_A"),
                      realized_weights={_iid("FIGI_A"): 0.15})

    def test_per_name_cap_breach_short_position(self):
        book = self._book(per_name_cap=0.10)
        result = rebalance({book.sleeves[0].name: _target({"FIGI_A": -0.08})}, book,
                           instrument_bands=self._bands(0.10, "FIGI_A"),
                           realized_weights={_iid("FIGI_A"): -0.12})
        assert len(result) == 1
        assert result[0].side == OrderSide.BUY
        assert result[0].delta == pytest.approx(0.02)  # -0.10 - (-0.12)

    def test_gross_within_ceiling_after_drawdown_delever(self):
        """The down-only clamp keeps gross within the ceiling through the
        drawdown-delever path: the delevered target is still clamped to
        max_book_gross (== gross_cap), so the post-book never breaches the cap."""
        book = self._book(
            max_book_gross=0.20, gross_cap=0.20,
            drawdown_delever=DrawdownDeleverCurve(
                start_drawdown=0.05,
                end_drawdown=0.25,
                floor_multiplier=0.50,
            ),
        )
        result = rebalance(
            {book.sleeves[0].name: _target({"FIGI_A": 0.50})},
            book,
            realized_drawdown=0.25,
        )
        gross = sum(abs(d.delta) for d in result)  # realized empty -> delta == post weight
        assert gross <= book.max_book_gross + 1e-9

    def test_max_book_gross_above_gross_cap_rejected(self):
        """A soft clamp ceiling above the hard gross cap is incoherent — the
        down-only clamp could never make such a book compliant — so it is
        rejected at config construction, not 13 months into a backtest."""
        with pytest.raises(ValueError, match="exceeds gross_cap"):
            self._book(max_book_gross=1.0, gross_cap=0.8)

    def test_gate_book_caps_gross_breach_defensive(self):
        """The gross gate is a defensive backstop: the schema rule keeps gross
        within cap for any constructable book, but the gate still fails closed if
        a post-book ever reaches it over the cap (e.g. a future path bypassing the
        clamp).  Exercised directly because rebalance() can no longer reach it."""
        book = self._book(max_book_gross=0.50, gross_cap=0.50)
        with pytest.raises(ValueError, match="Gross exposure"):
            _gate_book_caps({_iid("FIGI_A"): 0.6, _iid("FIGI_B"): 0.6}, book)

    def test_within_band_drift_over_ceiling_clamped_not_failed(self):
        """Within-band drift can push the projected book over max_book_gross even
        when the target is within it.  The down-only clamp scales the projection
        back to the ceiling (bands yield) instead of tripping the hard gross gate."""
        book = self._book(
            max_book_gross=1.0, gross_cap=1.0,
        )
        result = rebalance(
            {book.sleeves[0].name: _target({"FIGI_A": 0.5, "FIGI_B": 0.5})},
            book,
            instrument_bands=self._bands(0.05, "FIGI_A", "FIGI_B"),
            realized_weights={_iid("FIGI_A"): 0.53, _iid("FIGI_B"): 0.53},
        )
        # Drift 0.03 <= band 0.05, so without the projected clamp the book sits at
        # gross 1.06 and fails closed.  With it, both names get a corrective sell
        # and the resulting book lands on the ceiling.
        after = {d.instrument_id.symbol.value: 0.53 + d.delta for d in result}
        gross_after = sum(abs(w) for w in after.values())
        assert gross_after == pytest.approx(1.0)
        assert gross_after <= book.gross_cap + 1e-9

    def test_net_cap_breach_fails_closed(self):
        book = self._book(net_cap=0.10)
        with pytest.raises(ValueError, match="Net exposure"):
            rebalance({book.sleeves[0].name: _target({"FIGI_A": 0.15, "FIGI_B": -0.01})}, book)

    def test_aggregate_drift_within_threshold_no_error(self):
        book = self._book(aggregate_drift_threshold=0.05)
        result = rebalance({book.sleeves[0].name: _target({"FIGI_A": 0.50, "FIGI_B": 0.30})}, book,
                           instrument_bands=self._bands(0.10, "FIGI_A", "FIGI_B"),
                           realized_weights={_iid("FIGI_A"): 0.52, _iid("FIGI_B"): 0.28})
        assert result == ()

    def test_aggregate_drift_triggers_full_cleanup(self):
        """Drift over threshold → ignore bands, trade everything back to target."""
        book = self._book(aggregate_drift_threshold=0.03)
        # Drift = |0.50-0.52| + |0.30-0.28| = 0.04 > 0.03.  Bands (0.10) would
        # normally suppress both; the trip forces a fuller cleanup.
        result = rebalance({book.sleeves[0].name: _target({"FIGI_A": 0.50, "FIGI_B": 0.30})}, book,
                           instrument_bands=self._bands(0.10, "FIGI_A", "FIGI_B"),
                           realized_weights={_iid("FIGI_A"): 0.52, _iid("FIGI_B"): 0.28})
        by_figi = {d.instrument_id.symbol.value: d for d in result}
        assert by_figi["FIGI_A"].delta == pytest.approx(-0.02)
        assert by_figi["FIGI_B"].delta == pytest.approx(0.02)

    def test_cleanup_gross_clamped_to_ceiling(self):
        """The force-cleanup path stays subordinate to the gross ceiling: cleanup
        trades every name back to target (gross 0.70), then the down-only clamp
        pulls the projected book to max_book_gross (== gross_cap), so the cleanup
        never breaches the cap."""
        book = self._book(aggregate_drift_threshold=0.03, max_book_gross=0.50, gross_cap=0.50,
                          )
        # Drift trips; cleanup targets 0.40+0.30 (gross 0.70) > ceiling 0.50 -> clamped.
        result = rebalance({book.sleeves[0].name: _target({"FIGI_A": 0.40, "FIGI_B": 0.30})}, book,
                           instrument_bands=self._bands(0.10, "FIGI_A", "FIGI_B"),
                           realized_weights={_iid("FIGI_A"): 0.36, _iid("FIGI_B"): 0.26})
        after = {_iid("FIGI_A"): 0.36, _iid("FIGI_B"): 0.26}
        for d in result:
            after[d.instrument_id] = after.get(d.instrument_id, 0.0) + d.delta
        gross = sum(abs(w) for w in after.values())
        assert gross == pytest.approx(0.50)
        assert gross <= book.gross_cap + 1e-9

    def test_correlated_drift_triggers_cleanup(self):
        """N small within-band drifts trip the aggregate threshold → cleanup all."""
        book = self._book(per_name_cap=0.25, aggregate_drift_threshold=0.03)
        # Each drifts +0.01 (within 0.02 band); aggregate 0.04 > 0.03 → cleanup.
        result = rebalance(
            {book.sleeves[0].name: _target(
                {"FIGI_A": 0.20, "FIGI_B": 0.20, "FIGI_C": 0.20, "FIGI_D": 0.20})},
            book,
            instrument_bands=self._bands(0.02, "FIGI_A", "FIGI_B", "FIGI_C", "FIGI_D"),
            realized_weights={_iid("FIGI_A"): 0.21, _iid("FIGI_B"): 0.21, _iid("FIGI_C"): 0.21, _iid("FIGI_D"): 0.21},
        )
        assert len(result) == 4
        for d in result:
            assert d.delta == pytest.approx(-0.01)

    def test_cap_gate_sees_realized_not_target(self):
        book = self._book(per_name_cap=0.10)
        result = rebalance({book.sleeves[0].name: _target({"FIGI_A": 0.08})}, book,
                           instrument_bands=self._bands(0.10, "FIGI_A"),
                           realized_weights={_iid("FIGI_A"): 0.12})
        assert len(result) == 1
        assert result[0].side == OrderSide.SELL
        assert result[0].delta == pytest.approx(-0.02)


class TestRebalancePipeline:
    """Composition: rebalance (weight deltas) → size_deltas (native shares).

    Sizing edge cases are covered exhaustively in test_sizing.py; here we verify
    the two pure steps compose, including multi-currency netting.
    """

    def test_eur_pipeline_to_shares(self):
        book = make_book([("trend", "trend.whl", 1.0)])
        deltas = rebalance({book.sleeves[0].name: _target({"EUR_ETF": 0.5})}, book)
        orders = size_deltas(
            deltas, nav=100_000.0,
            instrument_metas={_iid("EUR_ETF"): InstrumentSizing(currency="EUR", size_increment=1.0)},
            fx_rates={"EUR": 1.0},
            prices={_iid("EUR_ETF"): 100.0},
        )
        assert len(orders) == 1
        assert orders[0].quantity == pytest.approx(500.0)  # 50_000 / 100
        assert orders[0].side == OrderSide.BUY

    def test_multi_ccy_netting_then_sizing(self):
        book = make_book([("trend", "trend.whl", 0.6), ("carry", "carry.whl", 0.4)])
        deltas = rebalance(
            {book.sleeves[0].name: _target({"EUR_ETF": 0.5, "US_STOCK": 0.3}),
             book.sleeves[1].name: _target({"EUR_ETF": -0.2, "US_STOCK": 0.1})},
            book,
        )
        # EUR_ETF net 0.22, US_STOCK net 0.22
        orders = size_deltas(
            deltas, nav=100_000.0,
            instrument_metas={
                _iid("EUR_ETF"): InstrumentSizing(currency="EUR", size_increment=1.0),
                _iid("US_STOCK"): InstrumentSizing(currency="USD", size_increment=1.0),
            },
            fx_rates={"EUR": 1.0, "USD": 1.10},
            prices={_iid("EUR_ETF"): 100.0, _iid("US_STOCK"): 110.0},
        )
        by_figi = {o.instrument_id.symbol.value: o for o in orders}
        assert by_figi["EUR_ETF"].quantity == pytest.approx(220.0)   # 22_000 / 100
        assert by_figi["US_STOCK"].quantity == pytest.approx(220.0)  # 22_000·1.10 / 110
        for o in orders:
            assert o.side == OrderSide.BUY


class TestDownOnlyGrossClamp:
    """ADR-0004 amendment: vol-targeting is down-only.  When the vol-target solve
    over-levers an unlevered book, the netted book is clamped down to
    ``max_book_gross`` instead of failing closed at the gross cap.
    """

    @staticmethod
    def _book(**kwargs) -> BookConfig:
        return BookConfig(
            sleeves=(
                SleeveConfig(name=SleeveName("low"), wheel_filename="low.whl", risk_share=0.5),
                SleeveConfig(name=SleeveName("high"), wheel_filename="high.whl", risk_share=0.5),
            ),
            book_vol_target=0.09,
            max_book_gross=1.0,
            gross_cap=1.0,
            **kwargs,
        )

    def test_overlevered_book_clamped_not_failed_closed(self):
        book = self._book()
        # Low realized vols -> diagonal vol-targeting wants gross well above 1.0.
        plan = rebalance_plan(
            {book.sleeves[0].name: _target({"A": 1.0}),
             book.sleeves[1].name: _target({"B": 1.0})},
            book,
            realized_vols={book.sleeves[0].name: 0.03, book.sleeves[1].name: 0.03},
        )
        gross = sum(abs(d.delta) for d in plan.deltas)
        assert gross <= book.max_book_gross + 1e-9

    def test_underlevered_book_is_not_scaled_up_to_the_cap(self):
        book = self._book()
        # High realized vols -> vol-targeting de-levers below the cap; the clamp
        # must leave it there (down-only), never peg it up to max_book_gross.
        plan = rebalance_plan(
            {book.sleeves[0].name: _target({"A": 1.0}),
             book.sleeves[1].name: _target({"B": 1.0})},
            book,
            realized_vols={book.sleeves[0].name: 0.40, book.sleeves[1].name: 0.40},
        )
        gross = sum(abs(d.delta) for d in plan.deltas)
        assert gross < book.max_book_gross

    def test_clamp_lands_exactly_on_the_cap(self):
        book = self._book()
        plan = rebalance_plan(
            {book.sleeves[0].name: _target({"A": 1.0}),
             book.sleeves[1].name: _target({"B": 1.0})},
            book,
            realized_vols={book.sleeves[0].name: 0.03, book.sleeves[1].name: 0.03},
        )
        gross = sum(abs(d.delta) for d in plan.deltas)
        assert gross == pytest.approx(book.max_book_gross)

    def test_clamp_preserves_relative_weights(self):
        book = self._book()
        # Equal vols + shares -> equal sleeve multipliers, so the netted weights
        # carry the raw 1.0 : 0.5 ratio.  A uniform clamp must keep that 2:1.
        plan = rebalance_plan(
            {book.sleeves[0].name: _target({"A": 1.0}),
             book.sleeves[1].name: _target({"B": 0.5})},
            book,
            realized_vols={book.sleeves[0].name: 0.03, book.sleeves[1].name: 0.03},
        )
        by_figi = {d.instrument_id.symbol.value: d.delta for d in plan.deltas}
        assert by_figi["A"] / by_figi["B"] == pytest.approx(2.0)

    def test_clamp_composes_with_drawdown_delever(self):
        book = self._book(
            drawdown_delever=DrawdownDeleverCurve(
                start_drawdown=0.05, end_drawdown=0.25, floor_multiplier=0.5,
            ),
        )
        # Drawdown de-lever (in the allocator) halves the book, but the solve
        # still over-levers; the post-netting clamp brings it under the cap.
        plan = rebalance_plan(
            {book.sleeves[0].name: _target({"A": 1.0}),
             book.sleeves[1].name: _target({"B": 1.0})},
            book,
            realized_vols={book.sleeves[0].name: 0.03, book.sleeves[1].name: 0.03},
            realized_drawdown=0.25,
        )
        gross = sum(abs(d.delta) for d in plan.deltas)
        assert gross <= book.max_book_gross + 1e-9
