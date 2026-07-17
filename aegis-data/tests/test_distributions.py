from __future__ import annotations

from typing import Any

import pandas as pd
import pytest
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
        self.calls: list[dict[str, Any]] = []

    def request_daily_closes(self, **kwargs: Any) -> list[tuple[pd.Timestamp, float]]:
        self.calls.append(kwargs)
        return self.closes


def test_request_adjusted_last_uses_raw_ibapi_seam() -> None:
    fake = _FakeAdjustedLastClient()
    provider = IbkrHistoricalProvider(adjusted_last_client_factory=lambda: fake)

    series = provider.request_adjusted_last(
        _SPY,
        start=pd.Timestamp("2024-01-01", tz="UTC"),
        end=pd.Timestamp("2024-02-01", tz="UTC"),
        currency="USD",
    )

    assert series.to_dict() == {pd.Timestamp("2024-01-02", tz="UTC"): 470.12}
    assert fake.calls == [
        {
            "instrument_id": _SPY,
            "what_to_show": "ADJUSTED_LAST",
            "start": pd.Timestamp("2024-01-01", tz="UTC"),
            "end": pd.Timestamp("2024-02-01", tz="UTC"),
            "primary_exchange": "ARCA",
            "currency": "USD",
            "timeout": 120,
        }
    ]


def test_request_adjusted_last_translates_mic_venue_to_ib_primary_exchange() -> None:
    # LVO.XAMS: the corpus venue is the MIC (XAMS), but IB only accepts its own
    # exchange code (AEB) as primaryExchange — a MIC reaches IB as error 200
    # "exchange invalid" (observed live: the aerd LVO dividend fatality).
    fake = _FakeAdjustedLastClient()
    provider = IbkrHistoricalProvider(adjusted_last_client_factory=lambda: fake)

    provider.request_adjusted_last(
        InstrumentId.from_str("LVO.XAMS"),
        start=pd.Timestamp("2024-01-01", tz="UTC"),
        end=pd.Timestamp("2024-02-01", tz="UTC"),
        currency="EUR",
    )

    assert fake.calls[0]["primary_exchange"] == "AEB"


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
        def request_daily_closes(self, **kwargs: Any) -> list[tuple[pd.Timestamp, float]]:
            raise RuntimeError("ib down")

    provider = IbkrHistoricalProvider(adjusted_last_client_factory=_Boom)

    with pytest.raises(IbkrRequestError, match="ADJUSTED_LAST"):
        provider.request_adjusted_last(
            _SPY,
            start=pd.Timestamp("2024-01-01", tz="UTC"),
            end=pd.Timestamp("2024-02-01", tz="UTC"),
            currency="USD",
        )
