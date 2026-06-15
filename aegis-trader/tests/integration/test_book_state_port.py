"""Integration tests for NautilusBookState (Wave B / B11; Wave D venue-agnostic).

The adapter is a *deep* module: it collapses the Demeter train-wrecks the
Strategy used to inline (``portfolio.equity(venue)[base].as_double()``,
``account.balances().get(base).total.as_double()``) into a narrow
``BookStatePort`` (nav / cash / health / realized_weights), delegating the
marking + base-currency conversion of realized exposure to Nautilus's own
``PortfolioFacade.net_exposure``.

Wave D — the book is *venue-agnostic*: NAV and cash aggregate across every
account the reconciled cache holds (``cache.accounts()``), summing the
base-currency total per account.  This is correct both for a single live IBKR
account spanning many exchanges and for a multi-venue backtest with one account
per venue; there is no book-wide ``default_venue``.

Tested against fakes that quack like Nautilus's PortfolioFacade / CacheFacade
(the abstractions the kernel itself depends on), using real Money / Currency /
AccountId / InstrumentId so the value-extraction is exercised for real.  The
full stack is proven by the e2e BacktestEngine suite once the Strategy is
rewired.
"""

from __future__ import annotations

from nautilus_trader.model.currencies import EUR
from nautilus_trader.model.identifiers import AccountId, InstrumentId
from nautilus_trader.model.objects import Money

from aegis_trader.portfolio import NautilusBookState

_FIGI_A = "BBG000B9XRY4"
_IID_A = InstrumentId.from_str(f"{_FIGI_A}.XLON")
_ACCT_XLON = AccountId("XLON-001")
_ACCT_XETR = AccountId("XETR-001")


class _FakeAccount:
    """Quacks like a Nautilus Account for the base-currency cash total."""

    def __init__(self, account_id: AccountId, *, cash: Money) -> None:
        self.id = account_id
        self._cash = cash

    def balances_total(self) -> dict:
        return {self._cash.currency: self._cash}


class _FakePortfolio:
    """Quacks like PortfolioFacade: equity is resolved per account_id."""

    def __init__(
        self,
        *,
        equities: dict[AccountId, Money] | None = None,
        exposures: dict[InstrumentId, Money] | None = None,
    ) -> None:
        self._equities = equities or {}
        self._exposures = exposures or {}

    def equity(self, venue=None, account_id=None):
        money = self._equities.get(account_id)
        return {money.currency: money} if money is not None else {}

    def net_exposure(self, instrument_id, price=None, account_id=None, target_currency=None):
        return self._exposures.get(instrument_id)


class _FakePosition:
    def __init__(self, instrument_id: InstrumentId, *, is_short: bool) -> None:
        self.instrument_id = instrument_id
        self.is_short = is_short


class _FakeCache:
    def __init__(self, *, instruments: list, positions: list, accounts: list) -> None:
        self._instruments = instruments
        self._positions = positions
        self._accounts = accounts

    def instruments(self):
        return self._instruments

    def positions_open(self):
        return self._positions

    def accounts(self):
        return self._accounts


def _book_state(*, portfolio: _FakePortfolio, cache: _FakeCache,
                instr_to_figi: dict[str, str] | None = None) -> NautilusBookState:
    return NautilusBookState(
        portfolio=portfolio,
        cache=cache,
        base_currency=EUR,
        instr_to_figi=instr_to_figi if instr_to_figi is not None else {_IID_A.value: _FIGI_A},
    )


def _single_account_book(*, equity: float, cash: float,
                         exposures: dict[InstrumentId, Money] | None = None,
                         positions: list | None = None) -> NautilusBookState:
    """One account holding the given base-currency equity/cash."""
    return _book_state(
        portfolio=_FakePortfolio(
            equities={_ACCT_XLON: Money(equity, EUR)}, exposures=exposures,
        ),
        cache=_FakeCache(
            instruments=["x"],
            positions=positions or [],
            accounts=[_FakeAccount(_ACCT_XLON, cash=Money(cash, EUR))],
        ),
    )


def test_nav_aggregates_base_currency_equity_across_accounts():
    """nav() sums per-account base-currency equity (multi-venue book)."""
    bs = _book_state(
        portfolio=_FakePortfolio(equities={
            _ACCT_XLON: Money(60_000.0, EUR),
            _ACCT_XETR: Money(40_000.0, EUR),
        }),
        cache=_FakeCache(
            instruments=["x"],
            positions=[],
            accounts=[
                _FakeAccount(_ACCT_XLON, cash=Money(0.0, EUR)),
                _FakeAccount(_ACCT_XETR, cash=Money(0.0, EUR)),
            ],
        ),
    )
    assert bs.nav() == 100_000.0


def test_cash_aggregates_base_currency_balance_across_accounts():
    """cash() sums per-account base-currency balance (multi-venue book)."""
    bs = _book_state(
        portfolio=_FakePortfolio(equities={
            _ACCT_XLON: Money(1.0, EUR), _ACCT_XETR: Money(1.0, EUR),
        }),
        cache=_FakeCache(
            instruments=["x"],
            positions=[],
            accounts=[
                _FakeAccount(_ACCT_XLON, cash=Money(30_000.0, EUR)),
                _FakeAccount(_ACCT_XETR, cash=Money(12_000.0, EUR)),
            ],
        ),
    )
    assert bs.cash() == 42_000.0


def test_nav_reads_single_account_equity():
    bs = _single_account_book(equity=100_000.0, cash=50_000.0)
    assert bs.nav() == 100_000.0


def test_cash_reads_single_account_balance():
    bs = _single_account_book(equity=100_000.0, cash=42_000.0)
    assert bs.cash() == 42_000.0


def test_cache_health_reflects_instruments_present():
    bs_healthy = _book_state(
        portfolio=_FakePortfolio(equities={_ACCT_XLON: Money(1.0, EUR)}),
        cache=_FakeCache(instruments=["x"], positions=[],
                         accounts=[_FakeAccount(_ACCT_XLON, cash=Money(1.0, EUR))]),
    )
    bs_empty = _book_state(
        portfolio=_FakePortfolio(equities={_ACCT_XLON: Money(1.0, EUR)}),
        cache=_FakeCache(instruments=[], positions=[],
                         accounts=[_FakeAccount(_ACCT_XLON, cash=Money(1.0, EUR))]),
    )
    assert bs_healthy.is_cache_healthy() is True
    assert bs_empty.is_cache_healthy() is False


def test_realized_weight_long_is_exposure_over_nav():
    """A long position's realized weight = Nautilus-marked exposure / NAV."""
    bs = _single_account_book(
        equity=100_000.0, cash=0.0,
        exposures={_IID_A: Money(22_000.0, EUR)},
        positions=[_FakePosition(_IID_A, is_short=False)],
    )
    assert bs.realized_weights() == {_FIGI_A: 0.22}


def test_realized_weight_short_is_negative():
    """A short position flips the sign (net_exposure is an absolute magnitude)."""
    bs = _single_account_book(
        equity=100_000.0, cash=0.0,
        exposures={_IID_A: Money(10_000.0, EUR)},
        positions=[_FakePosition(_IID_A, is_short=True)],
    )
    assert bs.realized_weights() == {_FIGI_A: -0.10}


def test_realized_weight_skips_uncovered_holdings():
    """A position whose instrument is not in the bimap is out of scope."""
    other = InstrumentId.from_str("BBG000OTHER01.XLON")
    bs = _book_state(
        portfolio=_FakePortfolio(
            equities={_ACCT_XLON: Money(100_000.0, EUR)},
            exposures={other: Money(5_000.0, EUR)},
        ),
        cache=_FakeCache(
            instruments=["x"],
            positions=[_FakePosition(other, is_short=False)],
            accounts=[_FakeAccount(_ACCT_XLON, cash=Money(0.0, EUR))],
        ),
        instr_to_figi={_IID_A.value: _FIGI_A},  # `other` not covered
    )
    assert bs.realized_weights() == {}


def test_realized_weight_skips_unpriced_position():
    """No mark (net_exposure None) -> the position contributes nothing."""
    bs = _single_account_book(
        equity=100_000.0, cash=0.0, exposures={},
        positions=[_FakePosition(_IID_A, is_short=False)],
    )
    assert bs.realized_weights() == {}


def test_realized_weights_empty_when_nav_nonpositive():
    """A zero/negative NAV makes weights undefined -> empty (no divide)."""
    bs = _single_account_book(
        equity=0.0, cash=0.0,
        exposures={_IID_A: Money(5_000.0, EUR)},
        positions=[_FakePosition(_IID_A, is_short=False)],
    )
    assert bs.realized_weights() == {}
