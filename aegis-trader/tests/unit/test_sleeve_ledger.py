"""Unit tests for SleeveLedger — pure event-time book analytics."""

from __future__ import annotations

import numpy as np
import pytest

import aegis_trader.domain.sleeve_ledger as sleeve_ledger_module
from aegis_trader.domain.analytics_horizon import derive_horizon
from aegis_trader.domain.sleeve_ledger import (
    EWMA_COVARIANCE_ALPHA,
    BookObservation,
    DecreasingTimestampError,
    SleeveLedger,
    _ewma_covariance,
    _ledoit_wolf_intensity,
    _shrink_covariance,
)
from aegis_trader.domain.types import SleeveName
from nautilus_trader.model.identifiers import InstrumentId


def _iid(symbol: str) -> InstrumentId:
    return InstrumentId.from_str(f"{symbol}.TEST")


_TREND = SleeveName("trend")
_CARRY = SleeveName("carry")
_TAIL = SleeveName("tail")
_A = _iid("A")
_B = _iid("B")
_C = _iid("C")
_DAY_NS = 86_400_000_000_000
_HOUR_NS = 3_600_000_000_000
_WEEK_NS = 7 * _DAY_NS
_DAILY = derive_horizon(("1D",))
_WEEKLY = derive_horizon(("1W",))


def _weekday_ns(index: int) -> int:
    """The *index*-th weekday since Monday 1970-01-05, as a UTC day timestamp.

    Daily bars never stamp weekends; mapping test day indices onto weekdays
    keeps the fixtures realistic under the weekend fold (aegis-rd-cy7l)."""
    weeks, weekday = divmod(index, 5)
    return (4 + weeks * 7 + weekday) * _DAY_NS


def _observe(
    ledger: SleeveLedger,
    *,
    timestamp_ns: int,
    closes: dict[InstrumentId, float],
    sleeve_targets: dict[SleeveName, dict[InstrumentId, float]] | None = None,
    nav: float = 100_000.0,
    realized_weights: dict[InstrumentId, float] | None = None,
) -> None:
    ledger.record(
        BookObservation(
            timestamp_ns=timestamp_ns,
            nav=nav,
            realized_weights=realized_weights or {},
            sleeve_targets=(
                sleeve_targets
                if sleeve_targets is not None
                else {_TREND: {_A: 1.0}, _CARRY: {_B: 1.0}}
            ),
            marks=closes,
        )
    )


def _record_three_sleeve_history(ledger: SleeveLedger, observations: int) -> None:
    """Deterministic noisy closes for three single-instrument sleeves, one per day."""
    rng = np.random.default_rng(3)
    closes = np.array([100.0, 100.0, 100.0])
    for day in range(observations):
        _observe(
            ledger,
            timestamp_ns=_weekday_ns(day),
            sleeve_targets={_TREND: {_A: 1.0}, _CARRY: {_B: 1.0}, _TAIL: {_C: 1.0}},
            closes={_A: closes[0], _B: closes[1], _C: closes[2]},
        )
        closes = closes * (1.0 + rng.normal(0.0, 0.01, size=3))


def test_realized_covariance_uses_complete_daily_sleeve_return_rows():
    ledger = SleeveLedger(horizon=_DAILY)
    _observe(ledger, timestamp_ns=_weekday_ns(0), closes={_A: 100.0, _B: 100.0})
    _observe(ledger, timestamp_ns=_weekday_ns(1), closes={_A: 110.0, _B: 95.0})
    _observe(ledger, timestamp_ns=_weekday_ns(2), closes={_A: 88.0, _B: 104.5})
    # A later day's timestamp proves day 2 complete; day 3 itself stays open.
    _observe(ledger, timestamp_ns=_weekday_ns(3), closes={_A: 88.0, _B: 104.5})

    covariance = ledger.realized_covariance((_TREND, _CARRY), min_returns=2)

    assert covariance == {
        _TREND: {_TREND: pytest.approx(1.3608), _CARRY: pytest.approx(-0.6804)},
        _CARRY: {_TREND: pytest.approx(-0.6804), _CARRY: pytest.approx(0.3402)},
    }


def test_realized_covariance_returns_none_until_history_is_sufficient():
    ledger = SleeveLedger(horizon=_DAILY)
    _observe(ledger, timestamp_ns=_weekday_ns(0), closes={_A: 100.0})
    _observe(ledger, timestamp_ns=_weekday_ns(1), closes={_A: 101.0})

    covariance = ledger.realized_covariance((_TREND,), min_returns=2)

    assert covariance is None


def test_realized_covariance_excludes_the_open_day():
    """Three completed days would suffice, but the newest day is not yet
    proven complete, so covariance stays undefined."""
    ledger = SleeveLedger(horizon=_DAILY)
    _observe(ledger, timestamp_ns=_weekday_ns(0), closes={_A: 100.0, _B: 100.0})
    _observe(ledger, timestamp_ns=_weekday_ns(1), closes={_A: 110.0, _B: 95.0})
    _observe(ledger, timestamp_ns=_weekday_ns(2), closes={_A: 88.0, _B: 104.5})

    covariance = ledger.realized_covariance((_TREND, _CARRY), min_returns=2)

    assert covariance is None


def test_intraday_observations_compound_to_the_daily_covariance_input():
    """Many intraday observations within a day produce the same covariance as
    one end-of-day observation on the equivalent economic path; duplicate and
    zero-effect observations change nothing (aegis-rd-9qkr.7)."""
    daily = SleeveLedger(horizon=_DAILY)
    _observe(daily, timestamp_ns=_weekday_ns(0), closes={_A: 100.0, _B: 100.0})
    _observe(daily, timestamp_ns=_weekday_ns(1), closes={_A: 110.0, _B: 95.0})
    _observe(daily, timestamp_ns=_weekday_ns(2), closes={_A: 88.0, _B: 104.5})
    _observe(daily, timestamp_ns=_weekday_ns(3), closes={_A: 88.0, _B: 104.5})

    intraday = SleeveLedger(horizon=_DAILY)
    _observe(intraday, timestamp_ns=_weekday_ns(0), closes={_A: 100.0, _B: 100.0})
    _observe(
        intraday,
        timestamp_ns=_weekday_ns(1) + 3 * _HOUR_NS,
        closes={_A: 104.0, _B: 99.0},
    )
    _observe(
        intraday,
        timestamp_ns=_weekday_ns(1) + 9 * _HOUR_NS,
        closes={_A: 110.0, _B: 95.0},
    )
    # Zero-effect repeat of the same marks later in the day.
    _observe(
        intraday,
        timestamp_ns=_weekday_ns(1) + 10 * _HOUR_NS,
        closes={_A: 110.0, _B: 95.0},
    )
    _observe(intraday, timestamp_ns=_weekday_ns(2), closes={_A: 88.0, _B: 104.5})
    _observe(intraday, timestamp_ns=_weekday_ns(3), closes={_A: 88.0, _B: 104.5})

    assert intraday.realized_covariance(
        (_TREND, _CARRY), min_returns=2
    ) == daily.realized_covariance((_TREND, _CARRY), min_returns=2)


def test_partial_marks_hold_the_previous_valid_mark():
    """A non-advancing instrument keeps its held mark: the hourly stream moves
    while the daily sleeve's instrument stays marked at its last close."""
    ledger = SleeveLedger(horizon=_DAILY)
    _observe(ledger, timestamp_ns=_weekday_ns(0), closes={_A: 100.0, _B: 100.0})
    _observe(ledger, timestamp_ns=_weekday_ns(1), closes={_A: 110.0})
    _observe(ledger, timestamp_ns=_weekday_ns(2), closes={_A: 88.0, _B: 104.5})
    _observe(ledger, timestamp_ns=_weekday_ns(3), closes={_A: 88.0, _B: 104.5})

    covariance = ledger.realized_covariance((_TREND, _CARRY), min_returns=2)

    # Day 1: B held at 100.0 (zero movement); day 2 realizes the gap return.
    assert covariance is not None
    assert covariance[_CARRY][_CARRY] > 0.0


def test_same_timestamp_recording_replaces_without_a_new_interval():
    ledger = SleeveLedger(horizon=_DAILY)
    _observe(ledger, timestamp_ns=_weekday_ns(0), closes={_A: 100.0})
    _observe(ledger, timestamp_ns=_weekday_ns(1), closes={_A: 999.0})
    _observe(ledger, timestamp_ns=_weekday_ns(1), closes={_A: 101.0})

    assert ledger.observation_count == 2
    assert ledger.nav_history == (100_000.0, 100_000.0)


def test_decreasing_timestamps_fail_fast():
    ledger = SleeveLedger(horizon=_DAILY)
    _observe(ledger, timestamp_ns=_weekday_ns(1), closes={_A: 100.0})

    with pytest.raises(DecreasingTimestampError):
        _observe(ledger, timestamp_ns=0, closes={_A: 101.0})


def test_realized_covariance_without_shrinkage_is_the_plain_ewma_estimate(monkeypatch):
    """Nesting control: intensity forced to zero reproduces the pre-shrinkage pipeline."""
    ledger = SleeveLedger(horizon=_DAILY)
    _record_three_sleeve_history(ledger, observations=25)
    monkeypatch.setattr(sleeve_ledger_module, "_ledoit_wolf_intensity", lambda rows: 0.0)

    covariance = ledger.realized_covariance((_TREND, _CARRY, _TAIL), min_returns=20)

    periods = ledger._completed_bucket_snapshots()[-21:]
    rows = sleeve_ledger_module._complete_sleeve_return_rows(periods, (_TREND, _CARRY, _TAIL))
    expected = (
        _ewma_covariance(rows, alpha=EWMA_COVARIANCE_ALPHA)
        * 252.0  # golden: the daily weekday convention, re-derived independently
    )
    names = (_TREND, _CARRY, _TAIL)
    for i, left in enumerate(names):
        for j, right in enumerate(names):
            assert covariance[left][right] == expected[i, j]


def test_realized_covariance_shrinkage_engages_but_preserves_sleeve_variances():
    """With 3+ sleeves and real history the correlations shrink; the vols never move."""
    ledger = SleeveLedger(horizon=_DAILY)
    _record_three_sleeve_history(ledger, observations=25)

    covariance = ledger.realized_covariance((_TREND, _CARRY, _TAIL), min_returns=20)

    periods = ledger._completed_bucket_snapshots()[-21:]
    rows = sleeve_ledger_module._complete_sleeve_return_rows(periods, (_TREND, _CARRY, _TAIL))
    raw = (
        _ewma_covariance(rows, alpha=EWMA_COVARIANCE_ALPHA)
        * 252.0  # golden: the daily weekday convention, re-derived independently
    )
    assert _ledoit_wolf_intensity(rows) > 0.0
    names = (_TREND, _CARRY, _TAIL)
    for i, name in enumerate(names):
        assert covariance[name][name] == pytest.approx(raw[i, i])
    assert any(
        covariance[left][right] != pytest.approx(raw[i, j])
        for i, left in enumerate(names)
        for j, right in enumerate(names)
        if i != j
    )


def test_shrink_covariance_interpolates_correlations_toward_their_mean():
    vols = np.array([0.10, 0.20, 0.15])
    correlation = np.array(
        [
            [1.0, 0.8, 0.0],
            [0.8, 1.0, 0.4],
            [0.0, 0.4, 1.0],
        ]
    )
    covariance = correlation * np.outer(vols, vols)

    shrunk = _shrink_covariance(covariance, 0.5)

    shrunk_correlation = shrunk / np.outer(vols, vols)
    assert np.allclose(np.diag(shrunk), np.diag(covariance))
    # mean off-diagonal correlation is 0.4; each pair moves halfway toward it.
    assert shrunk_correlation[0, 1] == pytest.approx(0.6)
    assert shrunk_correlation[0, 2] == pytest.approx(0.2)
    assert shrunk_correlation[1, 2] == pytest.approx(0.4)


def test_ledoit_wolf_intensity_is_zero_when_history_cannot_support_it():
    assert _ledoit_wolf_intensity([[0.01, 0.02], [0.02, 0.01]]) == 0.0  # two rows
    assert _ledoit_wolf_intensity([[0.01], [0.02], [0.01], [0.03]]) == 0.0  # one sleeve


def test_ledoit_wolf_intensity_stays_within_the_unit_interval():
    rng = np.random.default_rng(5)
    rows = rng.normal(0.0, 0.01, size=(40, 4))
    intensity = _ledoit_wolf_intensity(rows.tolist())
    assert 0.0 <= intensity <= 1.0


def test_realized_book_skew_measures_the_weighted_daily_return_stream():
    ledger = SleeveLedger(horizon=_DAILY)
    trend_only = {_TREND: {_A: 1.0}}
    for day, close in enumerate([100.0, 101.0, 102.01, 103.0301, 82.42408]):
        _observe(
            ledger,
            timestamp_ns=_weekday_ns(day),
            sleeve_targets=trend_only,
            closes={_A: close},
        )
    # Prove the crash day complete without adding a new return row.
    _observe(
        ledger,
        timestamp_ns=_weekday_ns(5),
        sleeve_targets=trend_only,
        closes={_A: 82.42408},
    )

    skew = ledger.realized_book_skew({_TREND: 1.0}, (_TREND,), min_returns=4)

    assert skew is not None
    assert skew < 0.0


def test_attribution_decomposes_realized_book_pnl_by_sleeve_targets():
    ledger = SleeveLedger(horizon=_DAILY)
    targets = {_TREND: {_A: 1.0}, _CARRY: {_A: 0.5}}
    _observe(
        ledger,
        timestamp_ns=_weekday_ns(0),
        sleeve_targets=targets,
        realized_weights={_A: 0.8},
        closes={_A: 100.0},
    )
    _observe(
        ledger,
        timestamp_ns=_weekday_ns(1),
        sleeve_targets=targets,
        realized_weights={_A: 0.8},
        closes={_A: 110.0},
    )

    attribution = ledger.attribution({_TREND: 0.6, _CARRY: 0.4})

    assert attribution == {_TREND: pytest.approx(6_000.0), _CARRY: pytest.approx(2_000.0)}


def test_attribution_keeps_event_time_intervals_for_intraday_weight_changes():
    """An intraday de-risk is attributed at its actual event cadence: the
    second interval's loss lands on the reduced weight, not the day-open one."""
    ledger = SleeveLedger(horizon=_DAILY)
    _observe(
        ledger,
        timestamp_ns=_weekday_ns(1),
        sleeve_targets={_TREND: {_A: 1.0}},
        realized_weights={_A: 1.0},
        closes={_A: 100.0},
    )
    _observe(
        ledger,
        timestamp_ns=_weekday_ns(1) + 3 * _HOUR_NS,
        sleeve_targets={_TREND: {_A: 1.0}},
        realized_weights={_A: 0.5},
        closes={_A: 110.0},
    )
    _observe(
        ledger,
        timestamp_ns=_weekday_ns(1) + 9 * _HOUR_NS,
        sleeve_targets={_TREND: {_A: 1.0}},
        realized_weights={_A: 0.5},
        closes={_A: 99.0},
    )

    attribution = ledger.attribution({_TREND: 1.0})

    # +10% at weight 1.0, then -10% at the de-risked weight 0.5:
    # 10_000 - 5_000.  A daily-collapsed view would report -1_000.
    assert attribution == {_TREND: pytest.approx(5_000.0)}


def test_current_drawdown_uses_every_event_nav_plus_current_nav():
    ledger = SleeveLedger(horizon=_DAILY)
    _observe(ledger, timestamp_ns=0, nav=100.0, sleeve_targets={}, closes={})
    _observe(
        ledger,
        timestamp_ns=3 * _HOUR_NS,
        nav=120.0,
        sleeve_targets={},
        closes={},
    )
    _observe(ledger, timestamp_ns=6 * _HOUR_NS, nav=90.0, sleeve_targets={}, closes={})

    drawdown = ledger.current_drawdown(96.0)

    assert drawdown == pytest.approx(0.20)


def test_simultaneous_partial_marks_accumulate_within_one_timestamp():
    """Two instruments' bars land at the same event time as separate partial
    observations: both marks survive into the day's snapshot."""
    ledger = SleeveLedger(horizon=_DAILY)
    _observe(ledger, timestamp_ns=_weekday_ns(0), closes={_A: 100.0, _B: 100.0})
    _observe(ledger, timestamp_ns=_weekday_ns(1), closes={_A: 110.0})
    _observe(ledger, timestamp_ns=_weekday_ns(1), closes={_B: 95.0})
    _observe(ledger, timestamp_ns=_weekday_ns(2), closes={_A: 88.0, _B: 104.5})
    _observe(ledger, timestamp_ns=_weekday_ns(3), closes={_A: 88.0, _B: 104.5})

    covariance = ledger.realized_covariance((_TREND, _CARRY), min_returns=2)

    assert covariance == {
        _TREND: {_TREND: pytest.approx(1.3608), _CARRY: pytest.approx(-0.6804)},
        _CARRY: {_TREND: pytest.approx(-0.6804), _CARRY: pytest.approx(0.3402)},
    }


def test_weekly_horizon_buckets_weekly_and_annualizes_at_52():
    """The same close path on a weekly grid yields the daily ledger's
    covariance rescaled by 52/252 — the bucket rule and the annualization
    count move together (aegis-rd-cy7l)."""
    closes = [
        {_A: 100.0, _B: 100.0},
        {_A: 110.0, _B: 95.0},
        {_A: 88.0, _B: 104.5},
        {_A: 88.0, _B: 104.5},
    ]
    daily = SleeveLedger(horizon=_DAILY)
    weekly = SleeveLedger(horizon=_WEEKLY)
    for index, marks in enumerate(closes):
        _observe(daily, timestamp_ns=_weekday_ns(index), closes=marks)
        _observe(weekly, timestamp_ns=index * _WEEK_NS, closes=marks)

    daily_covariance = daily.realized_covariance((_TREND, _CARRY), min_returns=2)
    weekly_covariance = weekly.realized_covariance((_TREND, _CARRY), min_returns=2)

    assert daily_covariance is not None and weekly_covariance is not None
    assert weekly_covariance[_TREND][_TREND] == pytest.approx(
        daily_covariance[_TREND][_TREND] * 52.0 / 252.0
    )
    assert weekly_covariance[_TREND][_CARRY] == pytest.approx(
        daily_covariance[_TREND][_CARRY] * 52.0 / 252.0
    )


def test_sunday_session_spillover_joins_mondays_bucket():
    """A Globex-style Sunday-evening observation folds into Monday's row: the
    ledger behaves as if the marks had arrived Monday, so no sixth weekly
    row dilutes the variance (aegis-rd-cy7l weekend fold)."""
    friday, monday, tuesday, wednesday = (
        _weekday_ns(4) + 20 * _HOUR_NS,
        _weekday_ns(5) + 21 * _HOUR_NS,
        _weekday_ns(6) + 21 * _HOUR_NS,
        _weekday_ns(7) + 21 * _HOUR_NS,
    )
    sunday_evening = _weekday_ns(5) - 2 * _HOUR_NS

    with_spillover = SleeveLedger(horizon=_DAILY)
    _observe(with_spillover, timestamp_ns=friday, closes={_A: 100.0, _B: 100.0})
    _observe(with_spillover, timestamp_ns=sunday_evening, closes={_A: 104.0, _B: 98.0})
    _observe(with_spillover, timestamp_ns=monday, closes={_A: 110.0, _B: 95.0})
    _observe(with_spillover, timestamp_ns=tuesday, closes={_A: 88.0, _B: 104.5})
    _observe(with_spillover, timestamp_ns=wednesday, closes={_A: 88.0, _B: 104.5})

    weekdays_only = SleeveLedger(horizon=_DAILY)
    _observe(weekdays_only, timestamp_ns=friday, closes={_A: 100.0, _B: 100.0})
    _observe(weekdays_only, timestamp_ns=monday, closes={_A: 110.0, _B: 95.0})
    _observe(weekdays_only, timestamp_ns=tuesday, closes={_A: 88.0, _B: 104.5})
    _observe(weekdays_only, timestamp_ns=wednesday, closes={_A: 88.0, _B: 104.5})

    assert with_spillover.realized_covariance(
        (_TREND, _CARRY), min_returns=2
    ) == weekdays_only.realized_covariance((_TREND, _CARRY), min_returns=2)
