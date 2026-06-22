"""Unit tests for SleeveLedger — pure cross-period book analytics."""

from __future__ import annotations

import pytest

from aegis_trader.domain.sleeve_ledger import SleeveLedger
from aegis_trader.domain.types import SleeveName
from nautilus_trader.model.identifiers import InstrumentId


def _iid(symbol: str) -> InstrumentId:
    return InstrumentId.from_str(f"{symbol}.TEST")


_TREND = SleeveName("trend")
_CARRY = SleeveName("carry")
_A = _iid("A")
_B = _iid("B")


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
