"""Integration tests for NautilusBookState (Wave B / B11).

The adapter is a *deep* module: it collapses the Demeter train-wrecks the
Strategy used to inline (``portfolio.equity(venue)[base].as_double()``,
``account.balances().get(base).total.as_double()``) into a narrow
``BookStatePort`` (nav / cash / health / realized_weights), delegating the
marking + base-currency conversion of realized exposure to Nautilus's own
``PortfolioFacade.net_exposure``.

Tested against fakes that quack like Nautilus's PortfolioFacade / CacheFacade
(the abstractions the kernel itself depends on), using real Money / Currency /
InstrumentId so the value-extraction is exercised for real.  The full stack is
proven by the e2e BacktestEngine suite once the Strategy is rewired.
"""

from __future__ import annotations

from types import SimpleNamespace

from nautilus_trader.model.currencies import EUR
from nautilus_trader.model.identifiers import InstrumentId, Venue
from nautilus_trader.model.objects import Money

from aegis_trader.portfolio import NautilusBookState

_VENUE = Venue("XLON")
_FIGI_A = "BBG000B9XRY4"
_IID_A = InstrumentId.from_str(f"{_FIGI_A}.XLON")


class _FakePortfolio:
    """Quacks like PortfolioFacade for the reads the adapter performs."""

    def __init__(self, *, equity: float, cash: float,
                 exposures: dict[InstrumentId, Money] | None = None) -> None:
        self._equity = equity
        self._cash = cash
        self._exposures = exposures or {}

    def equity(self, venue=None, account_id=None):
        return {EUR: Money(self._equity, EUR)}

    def account(self, venue=None):
        balance = SimpleNamespace(total=Money(self._cash, EUR))
        return SimpleNamespace(balances=lambda: {EUR: balance})

    def net_exposure(self, instrument_id, price=None, account_id=None, target_currency=None):
        return self._exposures.get(instrument_id)


class _FakePosition:
    def __init__(self, instrument_id: InstrumentId, *, is_short: bool) -> None:
        self.instrument_id = instrument_id
        self.is_short = is_short


class _FakeCache:
    def __init__(self, *, instruments: list, positions: list) -> None:
        self._instruments = instruments
        self._positions = positions

    def instruments(self):
        return self._instruments

    def positions_open(self):
        return self._positions


def _book_state(*, portfolio: _FakePortfolio, cache: _FakeCache,
                instr_to_figi: dict[str, str] | None = None) -> NautilusBookState:
    return NautilusBookState(
        portfolio=portfolio,
        cache=cache,
        venue=_VENUE,
        base_currency=EUR,
        instr_to_figi=instr_to_figi if instr_to_figi is not None else {_IID_A.value: _FIGI_A},
    )


def test_nav_reads_base_currency_equity():
    """nav() collapses equity(venue)[base].as_double() to a plain float."""
    bs = _book_state(
        portfolio=_FakePortfolio(equity=100_000.0, cash=50_000.0),
        cache=_FakeCache(instruments=["x"], positions=[]),
    )
    assert bs.nav() == 100_000.0


def test_cash_reads_base_currency_balance():
    """cash() collapses account.balances().get(base).total.as_double()."""
    bs = _book_state(
        portfolio=_FakePortfolio(equity=100_000.0, cash=42_000.0),
        cache=_FakeCache(instruments=["x"], positions=[]),
    )
    assert bs.cash() == 42_000.0


def test_cache_health_reflects_instruments_present():
    bs_healthy = _book_state(
        portfolio=_FakePortfolio(equity=1.0, cash=1.0),
        cache=_FakeCache(instruments=["x"], positions=[]),
    )
    bs_empty = _book_state(
        portfolio=_FakePortfolio(equity=1.0, cash=1.0),
        cache=_FakeCache(instruments=[], positions=[]),
    )
    assert bs_healthy.is_cache_healthy() is True
    assert bs_empty.is_cache_healthy() is False


def test_realized_weight_long_is_exposure_over_nav():
    """A long position's realized weight = Nautilus-marked exposure / NAV."""
    bs = _book_state(
        portfolio=_FakePortfolio(
            equity=100_000.0, cash=0.0,
            exposures={_IID_A: Money(22_000.0, EUR)},
        ),
        cache=_FakeCache(
            instruments=["x"],
            positions=[_FakePosition(_IID_A, is_short=False)],
        ),
    )
    assert bs.realized_weights() == {_FIGI_A: 0.22}


def test_realized_weight_short_is_negative():
    """A short position flips the sign (net_exposure is an absolute magnitude)."""
    bs = _book_state(
        portfolio=_FakePortfolio(
            equity=100_000.0, cash=0.0,
            exposures={_IID_A: Money(10_000.0, EUR)},
        ),
        cache=_FakeCache(
            instruments=["x"],
            positions=[_FakePosition(_IID_A, is_short=True)],
        ),
    )
    assert bs.realized_weights() == {_FIGI_A: -0.10}


def test_realized_weight_skips_uncovered_holdings():
    """A position whose instrument is not in the bimap is out of scope."""
    other = InstrumentId.from_str("BBG000OTHER01.XLON")
    bs = _book_state(
        portfolio=_FakePortfolio(
            equity=100_000.0, cash=0.0,
            exposures={other: Money(5_000.0, EUR)},
        ),
        cache=_FakeCache(
            instruments=["x"],
            positions=[_FakePosition(other, is_short=False)],
        ),
        instr_to_figi={_IID_A.value: _FIGI_A},  # `other` not covered
    )
    assert bs.realized_weights() == {}


def test_realized_weight_skips_unpriced_position():
    """No mark (net_exposure None) → the position contributes nothing."""
    bs = _book_state(
        portfolio=_FakePortfolio(equity=100_000.0, cash=0.0, exposures={}),
        cache=_FakeCache(
            instruments=["x"],
            positions=[_FakePosition(_IID_A, is_short=False)],
        ),
    )
    assert bs.realized_weights() == {}


def test_realized_weights_empty_when_nav_nonpositive():
    """A zero/negative NAV makes weights undefined → empty (no divide)."""
    bs = _book_state(
        portfolio=_FakePortfolio(
            equity=0.0, cash=0.0,
            exposures={_IID_A: Money(5_000.0, EUR)},
        ),
        cache=_FakeCache(
            instruments=["x"],
            positions=[_FakePosition(_IID_A, is_short=False)],
        ),
    )
    assert bs.realized_weights() == {}
