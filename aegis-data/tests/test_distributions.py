from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pandas as pd
import pytest
from nautilus_trader.adapters.interactive_brokers.common import IBContract
from nautilus_trader.model.identifiers import InstrumentId

from aegis_data.distributions import (
    Distribution,
    query_distribution_data,
    request_distribution_data,
    recover_distributions_from_adjusted_last,
    write_distribution_data,
)
from aegis_data.ibkr import IbkrHistoricalProvider, IbkrRequestError
from aegis_data.ibkr.historical import _HistoricSession
from aegis_data.storage import Catalog

_SPY = InstrumentId.from_str("SPY.ARCA")


def test_recovery_ignores_sub_half_cent_rounding_noise() -> None:
    dates = pd.date_range("2024-01-01", periods=4, freq="D")
    trades = pd.Series([100.00, 100.00, 100.00, 100.00], index=dates)
    # Jan-02 implies 0.004/share, below the half-cent cash floor; Jan-03
    # implies 0.50/share and is a real ex-date.
    factors = pd.Series(
        [1.0, 1.0 / (1.0 - 0.00004), 1.0 / (1.0 - 0.00004) / (1.0 - 0.005), 1.0],
        index=dates,
    )
    adjusted = trades * factors

    events = recover_distributions_from_adjusted_last(
        instrument_id=_SPY,
        trades=trades,
        adjusted_last=adjusted,
        currency="USD",
    )

    assert [(event.ex_date, event.amount, event.currency) for event in events] == [
        (pd.Timestamp("2024-01-03", tz="UTC"), pytest.approx(0.50), "USD")
    ]


def test_recovery_aligns_naive_trades_with_utc_adjusted_last() -> None:
    trade_dates = pd.date_range("2024-01-01", periods=3, freq="D")
    adjusted_dates = pd.date_range("2024-01-01", periods=3, freq="D", tz="UTC")
    trades = pd.Series([100.0, 100.0, 100.0], index=trade_dates)
    adjusted = pd.Series([100.0, 100.0 / (1.0 - 0.01), 100.0], index=adjusted_dates)

    events = recover_distributions_from_adjusted_last(
        instrument_id=_SPY,
        trades=trades,
        adjusted_last=adjusted,
        currency="USD",
    )

    assert [(event.ex_date, event.amount) for event in events] == [
        (pd.Timestamp("2024-01-02", tz="UTC"), pytest.approx(1.0))
    ]


def test_recovery_collapses_duplicate_daily_trade_rows() -> None:
    trade_dates = pd.DatetimeIndex(
        [
            pd.Timestamp("2024-01-01"),
            pd.Timestamp("2024-01-02"),
            pd.Timestamp("2024-01-02"),
        ]
    )
    adjusted_dates = pd.date_range("2024-01-01", periods=2, freq="D", tz="UTC")
    trades = pd.Series([100.0, 100.0, 100.0], index=trade_dates)
    adjusted = pd.Series([100.0, 100.0 / (1.0 - 0.01)], index=adjusted_dates)

    events = recover_distributions_from_adjusted_last(
        instrument_id=_SPY,
        trades=trades,
        adjusted_last=adjusted,
        currency="USD",
    )

    assert [(event.ex_date, event.amount) for event in events] == [
        (pd.Timestamp("2024-01-02", tz="UTC"), pytest.approx(1.0))
    ]


def test_distribution_catalog_write_is_append_only_new(tmp_path) -> None:
    catalog = Catalog.open(tmp_path / "catalog")
    first = Distribution.from_ex_date(_SPY, "2024-01-02", amount=0.25, currency="USD")
    second = Distribution.from_ex_date(_SPY, "2024-03-02", amount=0.30, currency="USD")
    third = Distribution.from_ex_date(_SPY, "2024-06-02", amount=0.35, currency="USD")

    assert write_distribution_data(catalog, [first, second]) == 2
    assert write_distribution_data(catalog, [first, second, third]) == 1

    stored = query_distribution_data(catalog, [_SPY])
    assert [(item.ex_date, item.amount) for item in stored] == [
        (pd.Timestamp("2024-01-02", tz="UTC"), pytest.approx(0.25)),
        (pd.Timestamp("2024-03-02", tz="UTC"), pytest.approx(0.30)),
        (pd.Timestamp("2024-06-02", tz="UTC"), pytest.approx(0.35)),
    ]


class _FakeNautilusRequest:
    def __init__(self, **kwargs: Any) -> None:
        self.__dict__.update(kwargs)


class _FakeNautilusRequests:
    def add(self, **kwargs: Any) -> _FakeNautilusRequest:
        return _FakeNautilusRequest(**kwargs)


class _FakeNautilusEClient:
    def __init__(self) -> None:
        self.contract: IBContract | None = None

    def reqHistoricalData(self, *, contract: IBContract, **_kwargs: Any) -> None:  # noqa: N802
        self.contract = contract

    def cancelHistoricalData(self, **_kwargs: Any) -> None:  # noqa: N802
        pass


class _FakeNautilusBar:
    def __init__(self, timestamp: pd.Timestamp, close: float) -> None:
        self.ts_event = timestamp.value
        self.close = SimpleNamespace(as_double=lambda: close)


class _FakeNautilusClient:
    def __init__(
        self,
        *,
        adjusted_closes: list[tuple[pd.Timestamp, float]] | None = None,
        adjusted_error: Exception | None = None,
        expected_contract: IBContract | None = None,
    ) -> None:
        self.adjusted_closes = (
            [(pd.Timestamp("2024-01-02", tz="UTC"), 470.12)]
            if adjusted_closes is None
            else adjusted_closes
        )
        self.adjusted_error = adjusted_error
        self.expected_contract = expected_contract
        self._eclient = _FakeNautilusEClient()
        self._requests = _FakeNautilusRequests()

    def _next_req_id(self) -> int:
        return 1

    async def _await_request(self, request: Any, timeout: int) -> list[Any]:
        if self.adjusted_error is not None:
            raise self.adjusted_error
        closes = self.adjusted_closes
        if (
            self.expected_contract is not None
            and self._eclient.contract != self.expected_contract
        ):
            closes = [(pd.Timestamp("2024-01-02", tz="UTC"), -1.0)]
        return [_FakeNautilusBar(timestamp, close) for timestamp, close in closes]

    async def _stop_async(self) -> None:
        pass


class _FakeHistoricClient:
    def __init__(
        self,
        instruments: list[Any],
        *,
        adjusted_closes: list[tuple[pd.Timestamp, float]] | None = None,
        adjusted_error: Exception | None = None,
        expected_contract: IBContract | None = None,
    ) -> None:
        self.instruments = instruments
        self._client = _FakeNautilusClient(
            adjusted_closes=adjusted_closes,
            adjusted_error=adjusted_error,
            expected_contract=expected_contract,
        )

    async def connect(self) -> None:
        pass

    async def request_instruments(self, **_kwargs: Any) -> list[Any]:
        return self.instruments


def _qualified_spy() -> Any:
    return SimpleNamespace(
        id=_SPY,
        info={
            "contract": {
                "secType": "STK",
                "conId": 756733,
                "exchange": "SMART",
                "primaryExchange": "ARCA",
                "symbol": "SPY",
                "localSymbol": "SPY",
                "currency": "USD",
                "tradingClass": "SPY",
            }
        },
    )


def _provider_with_qualification(
    instruments: list[Any],
    *,
    adjusted_closes: list[tuple[pd.Timestamp, float]] | None = None,
    adjusted_error: Exception | None = None,
    expected_contract: IBContract | None = None,
) -> IbkrHistoricalProvider:
    session = _HistoricSession(
        _FakeHistoricClient(
            instruments,
            adjusted_closes=adjusted_closes,
            adjusted_error=adjusted_error,
            expected_contract=expected_contract,
        )
    )
    return IbkrHistoricalProvider(client_factory=lambda: session)


def test_request_adjusted_last_preserves_the_qualified_ibkr_identity() -> None:
    expected = IBContract(
        secType="STK",
        conId=756733,
        exchange="SMART",
        primaryExchange="ARCA",
        symbol="SPY",
        localSymbol="SPY",
        currency="USD",
        tradingClass="SPY",
    )
    provider = _provider_with_qualification(
        [_qualified_spy()],
        expected_contract=expected,
    )

    series = provider.request_adjusted_last(
        _SPY,
        start=pd.Timestamp("2024-01-01", tz="UTC"),
        end=pd.Timestamp("2024-02-01", tz="UTC"),
        currency="USD",
    )

    assert series.to_dict() == {pd.Timestamp("2024-01-02", tz="UTC"): 470.12}


def test_request_adjusted_last_uses_the_qualification_session_for_history() -> None:
    provider = _provider_with_qualification(
        [_qualified_spy()],
        adjusted_closes=[(pd.Timestamp("2024-01-02", tz="UTC"), 470.12)],
    )

    series = provider.request_adjusted_last(
        _SPY,
        start=pd.Timestamp("2024-01-01", tz="UTC"),
        end=pd.Timestamp("2024-02-01", tz="UTC"),
        currency="USD",
    )

    assert series.to_dict() == {pd.Timestamp("2024-01-02", tz="UTC"): 470.12}


def test_request_adjusted_last_returns_sorted_daily_closes() -> None:
    provider = _provider_with_qualification(
        [_qualified_spy()],
        adjusted_closes=[
            (pd.Timestamp("2024-01-03", tz="UTC"), 472.25),
            (pd.Timestamp("2024-01-02", tz="UTC"), 470.12),
        ],
    )

    series = provider.request_adjusted_last(
        _SPY,
        start=pd.Timestamp("2024-01-01", tz="UTC"),
        end=pd.Timestamp("2024-02-01", tz="UTC"),
        currency="USD",
    )

    assert list(series.items()) == [
        (pd.Timestamp("2024-01-02", tz="UTC"), 470.12),
        (pd.Timestamp("2024-01-03", tz="UTC"), 472.25),
    ]


def test_request_adjusted_last_rejects_missing_qualification_before_history() -> None:
    provider = _provider_with_qualification([])

    with pytest.raises(IbkrRequestError, match="SPY.ARCA.*received 0"):
        provider.request_adjusted_last(
            _SPY,
            start=pd.Timestamp("2024-01-01", tz="UTC"),
            end=pd.Timestamp("2024-02-01", tz="UTC"),
            currency="USD",
        )


def test_request_adjusted_last_rejects_ambiguous_qualification() -> None:
    first = SimpleNamespace(id=_SPY, info={"contract": {}})
    second = SimpleNamespace(id=_SPY, info={"contract": {}})
    provider = _provider_with_qualification([first, second])

    with pytest.raises(IbkrRequestError, match="SPY.ARCA.*received 2"):
        provider.request_adjusted_last(
            _SPY,
            start=pd.Timestamp("2024-01-01", tz="UTC"),
            end=pd.Timestamp("2024-02-01", tz="UTC"),
            currency="USD",
        )


def test_request_adjusted_last_rejects_a_different_qualified_identity() -> None:
    qualified = SimpleNamespace(
        id=InstrumentId.from_str("QQQ.XNAS"),
        info={"contract": {}},
    )
    provider = _provider_with_qualification([qualified])

    with pytest.raises(IbkrRequestError, match="QQQ.XNAS.*SPY.ARCA"):
        provider.request_adjusted_last(
            _SPY,
            start=pd.Timestamp("2024-01-01", tz="UTC"),
            end=pd.Timestamp("2024-02-01", tz="UTC"),
            currency="USD",
        )


def test_request_adjusted_last_rejects_missing_contract_metadata() -> None:
    qualified = SimpleNamespace(id=_SPY, info={})
    provider = _provider_with_qualification([qualified])

    with pytest.raises(IbkrRequestError, match="SPY.ARCA.*no IB contract"):
        provider.request_adjusted_last(
            _SPY,
            start=pd.Timestamp("2024-01-01", tz="UTC"),
            end=pd.Timestamp("2024-02-01", tz="UTC"),
            currency="USD",
        )


def test_request_adjusted_last_rejects_malformed_contract_metadata() -> None:
    qualified = SimpleNamespace(
        id=_SPY,
        info={"contract": {"notAnIbContractField": "invalid"}},
    )
    provider = _provider_with_qualification([qualified])

    with pytest.raises(IbkrRequestError, match="SPY.ARCA.*Unexpected keyword argument"):
        provider.request_adjusted_last(
            _SPY,
            start=pd.Timestamp("2024-01-01", tz="UTC"),
            end=pd.Timestamp("2024-02-01", tz="UTC"),
            currency="USD",
        )


def test_request_adjusted_last_rejects_an_unqualified_contract() -> None:
    qualified = SimpleNamespace(
        id=_SPY,
        info={"contract": {"secType": "STK", "conId": 0, "currency": "USD"}},
    )
    provider = _provider_with_qualification([qualified])

    with pytest.raises(IbkrRequestError, match="SPY.ARCA.*no positive IB conId"):
        provider.request_adjusted_last(
            _SPY,
            start=pd.Timestamp("2024-01-01", tz="UTC"),
            end=pd.Timestamp("2024-02-01", tz="UTC"),
            currency="USD",
        )


def test_request_adjusted_last_rejects_a_qualified_currency_mismatch() -> None:
    qualified = SimpleNamespace(
        id=_SPY,
        info={"contract": {"secType": "STK", "conId": 756733, "currency": "EUR"}},
    )
    provider = _provider_with_qualification([qualified])

    with pytest.raises(IbkrRequestError, match="SPY.ARCA.*EUR.*USD"):
        provider.request_adjusted_last(
            _SPY,
            start=pd.Timestamp("2024-01-01", tz="UTC"),
            end=pd.Timestamp("2024-02-01", tz="UTC"),
            currency="USD",
        )


def test_request_distribution_data_fetches_adjusted_last_and_decodes_events() -> None:
    dates = pd.date_range("2024-01-01", periods=3, freq="D", tz="UTC")
    trades = pd.Series([100.0, 100.0, 100.0], index=dates)
    adjusted = pd.Series([100.0, 100.0 / (1.0 - 0.01), 100.0], index=dates)

    class _Provider:
        def request_adjusted_last(self, **kwargs: Any) -> pd.Series:
            assert kwargs["instrument_id"] == _SPY
            assert kwargs["currency"] == "USD"
            return adjusted

    events = request_distribution_data(
        _Provider(),
        _SPY,
        trades=trades,
        start=dates[0],
        end=dates[-1],
        currency="USD",
    )

    assert [(event.ex_date, event.amount) for event in events] == [
        (pd.Timestamp("2024-01-02", tz="UTC"), pytest.approx(1.0))
    ]


def test_request_adjusted_last_wraps_session_fault() -> None:
    provider = _provider_with_qualification(
        [_qualified_spy()], adjusted_error=RuntimeError("ib down")
    )

    with pytest.raises(IbkrRequestError, match="ADJUSTED_LAST"):
        provider.request_adjusted_last(
            _SPY,
            start=pd.Timestamp("2024-01-01", tz="UTC"),
            end=pd.Timestamp("2024-02-01", tz="UTC"),
            currency="USD",
        )
