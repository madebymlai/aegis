"""Unit tests for SleeveLedger — pure cross-period book analytics."""

from __future__ import annotations

import numpy as np
import pytest

import aegis_trader.domain.sleeve_ledger as sleeve_ledger_module
from aegis_trader.domain.sleeve_ledger import (
    EWMA_COVARIANCE_ALPHA,
    TRADING_DAYS_PER_YEAR,
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


def _record_three_sleeve_history(ledger: SleeveLedger, observations: int) -> None:
    """Deterministic noisy closes for three single-instrument sleeves."""
    rng = np.random.default_rng(3)
    closes = np.array([100.0, 100.0, 100.0])
    for _ in range(observations):
        ledger.record(
            nav=100_000.0,
            realized_weights={},
            sleeve_targets={_TREND: {_A: 1.0}, _CARRY: {_B: 1.0}, _TAIL: {_C: 1.0}},
            closes={_A: closes[0], _B: closes[1], _C: closes[2]},
        )
        closes = closes * (1.0 + rng.normal(0.0, 0.01, size=3))


def test_realized_covariance_uses_complete_sleeve_return_rows():
    ledger = SleeveLedger()
    ledger.record(
        nav=100_000.0,
        realized_weights={},
        sleeve_targets={_TREND: {_A: 1.0}, _CARRY: {_B: 1.0}},
        closes={_A: 100.0, _B: 100.0},
    )
    ledger.record(
        nav=100_000.0,
        realized_weights={},
        sleeve_targets={_TREND: {_A: 1.0}, _CARRY: {_B: 1.0}},
        closes={_A: 110.0, _B: 95.0},
    )
    ledger.record(
        nav=100_000.0,
        realized_weights={},
        sleeve_targets={_TREND: {_A: 1.0}, _CARRY: {_B: 1.0}},
        closes={_A: 88.0, _B: 104.5},
    )

    covariance = ledger.realized_covariance((_TREND, _CARRY), min_returns=2)

    assert covariance == {
        _TREND: {_TREND: pytest.approx(1.3608), _CARRY: pytest.approx(-0.6804)},
        _CARRY: {_TREND: pytest.approx(-0.6804), _CARRY: pytest.approx(0.3402)},
    }


def test_realized_covariance_returns_none_until_history_is_sufficient():
    ledger = SleeveLedger()
    ledger.record(
        nav=100_000.0,
        realized_weights={},
        sleeve_targets={_TREND: {_A: 1.0}},
        closes={_A: 100.0},
    )
    ledger.record(
        nav=100_000.0,
        realized_weights={},
        sleeve_targets={_TREND: {_A: 1.0}},
        closes={_A: 101.0},
    )

    covariance = ledger.realized_covariance((_TREND,), min_returns=2)

    assert covariance is None


def test_realized_covariance_without_shrinkage_is_the_plain_ewma_estimate(monkeypatch):
    """Nesting control: intensity forced to zero reproduces the pre-shrinkage pipeline."""
    ledger = SleeveLedger()
    _record_three_sleeve_history(ledger, observations=25)
    monkeypatch.setattr(sleeve_ledger_module, "_ledoit_wolf_intensity", lambda rows: 0.0)

    covariance = ledger.realized_covariance((_TREND, _CARRY, _TAIL), min_returns=20)

    periods = ledger._observations[-21:]
    rows = sleeve_ledger_module._complete_sleeve_return_rows(periods, (_TREND, _CARRY, _TAIL))
    expected = _ewma_covariance(rows, alpha=EWMA_COVARIANCE_ALPHA) * TRADING_DAYS_PER_YEAR
    names = (_TREND, _CARRY, _TAIL)
    for i, left in enumerate(names):
        for j, right in enumerate(names):
            assert covariance[left][right] == expected[i, j]


def test_realized_covariance_shrinkage_engages_but_preserves_sleeve_variances():
    """With 3+ sleeves and real history the correlations shrink; the vols never move."""
    ledger = SleeveLedger()
    _record_three_sleeve_history(ledger, observations=25)

    covariance = ledger.realized_covariance((_TREND, _CARRY, _TAIL), min_returns=20)

    periods = ledger._observations[-21:]
    rows = sleeve_ledger_module._complete_sleeve_return_rows(periods, (_TREND, _CARRY, _TAIL))
    raw = _ewma_covariance(rows, alpha=EWMA_COVARIANCE_ALPHA) * TRADING_DAYS_PER_YEAR
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


def test_realized_book_skew_measures_the_weighted_return_stream():
    ledger = SleeveLedger()
    ledger.record(
        nav=100_000.0,
        realized_weights={},
        sleeve_targets={_TREND: {_A: 1.0}},
        closes={_A: 100.0},
    )
    ledger.record(
        nav=100_000.0,
        realized_weights={},
        sleeve_targets={_TREND: {_A: 1.0}},
        closes={_A: 101.0},
    )
    ledger.record(
        nav=100_000.0,
        realized_weights={},
        sleeve_targets={_TREND: {_A: 1.0}},
        closes={_A: 102.01},
    )
    ledger.record(
        nav=100_000.0,
        realized_weights={},
        sleeve_targets={_TREND: {_A: 1.0}},
        closes={_A: 103.0301},
    )
    ledger.record(
        nav=100_000.0,
        realized_weights={},
        sleeve_targets={_TREND: {_A: 1.0}},
        closes={_A: 82.42408},
    )

    skew = ledger.realized_book_skew({_TREND: 1.0}, (_TREND,), min_returns=4)

    assert skew is not None
    assert skew < 0.0


def test_attribution_decomposes_realized_book_pnl_by_sleeve_targets():
    ledger = SleeveLedger()
    ledger.record(
        nav=100_000.0,
        realized_weights={_A: 0.8},
        sleeve_targets={_TREND: {_A: 1.0}, _CARRY: {_A: 0.5}},
        closes={_A: 100.0},
    )
    ledger.record(
        nav=100_000.0,
        realized_weights={_A: 0.8},
        sleeve_targets={_TREND: {_A: 1.0}, _CARRY: {_A: 0.5}},
        closes={_A: 110.0},
    )

    attribution = ledger.attribution({_TREND: 0.6, _CARRY: 0.4})

    assert attribution == {_TREND: pytest.approx(6_000.0), _CARRY: pytest.approx(2_000.0)}


def test_current_drawdown_uses_the_recorded_nav_peak_plus_current_nav():
    ledger = SleeveLedger()
    ledger.record(nav=100.0, realized_weights={}, sleeve_targets={}, closes={})
    ledger.record(nav=120.0, realized_weights={}, sleeve_targets={}, closes={})
    ledger.record(nav=90.0, realized_weights={}, sleeve_targets={}, closes={})

    drawdown = ledger.current_drawdown(96.0)

    assert drawdown == pytest.approx(0.20)
