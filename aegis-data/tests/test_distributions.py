from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pandas as pd
import pytest
from nautilus_trader.adapters.interactive_brokers.common import IBContract
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.persistence.catalog import ParquetDataCatalog

from aegis_data.distributions import (
    Distribution,
    query_distribution_data,
    request_distribution_data,
    recover_distributions_from_adjusted_last,
    write_distribution_data,
)
from aegis_data.ibkr import IbkrHistoricalProvider, IbkrRequestError

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
    catalog = ParquetDataCatalog(tmp_path / "catalog")
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


class _FakeAdjustedLastClient:
    def __init__(self, closes: list[tuple[pd.Timestamp, float]] | None = None) -> None:
        self.closes = closes or [(pd.Timestamp("2024-01-02", tz="UTC"), 470.12)]

    def request_daily_closes(self, **kwargs: Any) -> list[tuple[pd.Timestamp, float]]:
        return self.closes


class _QualifiedIdentityAdjustedLastClient:
    def request_daily_closes(
        self, *, contract: IBContract, **_kwargs: Any
    ) -> list[tuple[pd.Timestamp, float]]:
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
        close = 470.12 if contract == expected else -1.0
        return [(pd.Timestamp("2024-01-02", tz="UTC"), close)]


class _FakeQualificationSession:
    def __init__(self, instruments: list[Any]) -> None:
        self.instruments = instruments

    async def connect(self) -> None:
        pass

    async def aclose(self) -> None:
        pass

    async def request_instruments(self, **kwargs: Any) -> list[Any]:
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
    instruments: list[Any], adjusted_last_client_factory: Any
) -> IbkrHistoricalProvider:
    session = _FakeQualificationSession(instruments)
    return IbkrHistoricalProvider(
        client_factory=lambda: session,
        adjusted_last_client_factory=adjusted_last_client_factory,
    )


def _unexpected_adjusted_last_client() -> Any:
    raise AssertionError("raw client created before qualification succeeded")


def test_request_adjusted_last_preserves_the_qualified_ibkr_identity() -> None:
    provider = _provider_with_qualification(
        [_qualified_spy()],
        _QualifiedIdentityAdjustedLastClient,
    )

    series = provider.request_adjusted_last(
        _SPY,
        start=pd.Timestamp("2024-01-01", tz="UTC"),
        end=pd.Timestamp("2024-02-01", tz="UTC"),
        currency="USD",
    )

    assert series.to_dict() == {pd.Timestamp("2024-01-02", tz="UTC"): 470.12}


def test_request_adjusted_last_returns_sorted_daily_closes() -> None:
    raw = _FakeAdjustedLastClient(
        [
            (pd.Timestamp("2024-01-03", tz="UTC"), 472.25),
            (pd.Timestamp("2024-01-02", tz="UTC"), 470.12),
        ]
    )
    provider = _provider_with_qualification([_qualified_spy()], lambda: raw)

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


def test_request_adjusted_last_rejects_missing_qualification_before_raw_request() -> (
    None
):
    provider = _provider_with_qualification(
        [],
        _unexpected_adjusted_last_client,
    )

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
    provider = _provider_with_qualification(
        [first, second],
        _unexpected_adjusted_last_client,
    )

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
    provider = _provider_with_qualification(
        [qualified],
        _unexpected_adjusted_last_client,
    )

    with pytest.raises(IbkrRequestError, match="QQQ.XNAS.*SPY.ARCA"):
        provider.request_adjusted_last(
            _SPY,
            start=pd.Timestamp("2024-01-01", tz="UTC"),
            end=pd.Timestamp("2024-02-01", tz="UTC"),
            currency="USD",
        )


def test_request_adjusted_last_rejects_missing_contract_metadata() -> None:
    qualified = SimpleNamespace(id=_SPY, info={})
    provider = _provider_with_qualification(
        [qualified],
        _unexpected_adjusted_last_client,
    )

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
    provider = _provider_with_qualification(
        [qualified],
        _unexpected_adjusted_last_client,
    )

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
    provider = _provider_with_qualification(
        [qualified],
        _unexpected_adjusted_last_client,
    )

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
    provider = _provider_with_qualification(
        [qualified],
        _unexpected_adjusted_last_client,
    )

    with pytest.raises(IbkrRequestError, match="SPY.ARCA.*EUR.*USD"):
        provider.request_adjusted_last(
            _SPY,
            start=pd.Timestamp("2024-01-01", tz="UTC"),
            end=pd.Timestamp("2024-02-01", tz="UTC"),
            currency="USD",
        )


def test_adjusted_last_raw_clients_use_fresh_client_ids() -> None:
    provider = IbkrHistoricalProvider(client_id=7)

    first = provider._adjusted_last_client()
    second = provider._adjusted_last_client()

    assert second.client_id == first.client_id + 1


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


def test_request_adjusted_last_wraps_raw_fault() -> None:
    class _Boom(_FakeAdjustedLastClient):
        def request_daily_closes(
            self, **kwargs: Any
        ) -> list[tuple[pd.Timestamp, float]]:
            raise RuntimeError("ib down")

    provider = _provider_with_qualification([_qualified_spy()], _Boom)

    with pytest.raises(IbkrRequestError, match="ADJUSTED_LAST"):
        provider.request_adjusted_last(
            _SPY,
            start=pd.Timestamp("2024-01-01", tz="UTC"),
            end=pd.Timestamp("2024-02-01", tz="UTC"),
            currency="USD",
        )
