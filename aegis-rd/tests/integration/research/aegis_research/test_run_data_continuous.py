from __future__ import annotations

import pandas as pd
import pytest
from aegis_data.bar_type import mic_canonical_instrument_id
from aegis_data.catalog import CatalogBackedDataPort, GapFillProviderError
from aegis_data.continuous_future import DEFAULT_ADJUSTMENT_MODE
from aegis_data.marking import DeclaredMarkingResolver, MarkMode
from aegis_data.testing import FakeCatalog, bars, future
from nautilus_trader.model.enums import ContinuousFutureAdjustmentType
from nautilus_trader.model.identifiers import InstrumentId, Symbol
from nautilus_trader.model.instruments import CurrencyPair, Equity, FuturesContract, Instrument
from nautilus_trader.model.objects import Currency, Price, Quantity

from research.aegis_research.run import data as run_data_module
from research.aegis_research.run.data import (
    ContinuousRootCollisionError,
    RunData,
    RunDataUnavailable,
    RunDataWindowBoundsError,
    load_run_data,
)
from research.aegis_research.run.data_contract import (
    build_data_array_contract,
    candidate_data_identity,
)
from tests.support.research.aegis_research.factories import make_data_config


def _id(value: str) -> InstrumentId:
    return InstrumentId.from_str(value)


def _definition(instrument_id: InstrumentId) -> Instrument:
    symbol = instrument_id.symbol.value
    if "/" in symbol:
        base, quote = symbol.split("/")
        return CurrencyPair(
            instrument_id=instrument_id,
            raw_symbol=Symbol(symbol),
            base_currency=Currency.from_str(base),
            quote_currency=Currency.from_str(quote),
            price_precision=5,
            size_precision=0,
            price_increment=Price(1e-5, 5),
            size_increment=Quantity.from_int(1),
            ts_event=0,
            ts_init=0,
        )
    return Equity(
        instrument_id=instrument_id,
        raw_symbol=Symbol(symbol),
        currency=Currency.from_str("USD"),
        price_precision=2,
        price_increment=Price.from_str("0.01"),
        lot_size=Quantity.from_int(1),
        ts_event=0,
        ts_init=0,
    )


def _fake_port(
    frames: dict[InstrumentId, pd.DataFrame],
    *,
    legs: list[FuturesContract] | None = None,
    exchange: tuple[InstrumentId, ...] = (),
) -> CatalogBackedDataPort:
    resolver = DeclaredMarkingResolver(declared=dict.fromkeys(exchange, MarkMode.MID))
    catalog = FakeCatalog(
        [
            *(_definition(mic_canonical_instrument_id(iid)) for iid in frames),
            *(legs or []),
        ],
        {
            str(resolver.resolve(iid, "1D").mark_bars[0]): bars(iid, frame)
            for iid, frame in frames.items()
        },
    )
    return CatalogBackedDataPort(catalog, resolver=resolver)


def _frame(
    index: pd.DatetimeIndex,
    *,
    close: list[float],
    volume: list[float],
) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Open": close,
            "High": close,
            "Low": close,
            "Close": close,
            "Volume": volume,
        },
        index=index,
    )


def _load_native_and_continuous(
    monkeypatch: pytest.MonkeyPatch,
) -> RunData:
    aapl = _id("AAPL.NASDAQ")
    es = _id("ES.XCME")
    index = pd.DatetimeIndex(["2024-01-01", "2024-01-02"])
    port = _fake_port(
        {aapl: _frame(index, close=[10.0, 11.0], volume=[100.0, 110.0])},
        legs=[future("ESH4.XCME", "2024-03-15")],
    )
    continuous = _frame(index, close=[5000.0, 5010.0], volume=[1.0, 2.0])

    class FakeContinuousModel:
        quote_currency = "USD"

        def __init__(self, _port_arg, root, *, adjustment_mode, **_kwargs):
            self.continuous_id = es
            self.frame = continuous

        def materialize(self, *, end: str) -> None:
            pass

    monkeypatch.setattr(run_data_module, "ContinuousContractModel", FakeContinuousModel)
    config = make_data_config(
        arrays=["Close", "Volume"],
        base_currency="USD",
        instruments=["AAPL.NASDAQ"],
        futures=["ES"],
    )

    return load_run_data(
        config,
        required_arrays=("Close", "Volume"),
        port=port,
        custom_data_providers=None,
    )


def test_materializes_continuous_future_roots_as_tradeable_columns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = _load_native_and_continuous(monkeypatch)
    aapl = _id("AAPL.NASDAQ")
    es = _id("ES.XCME")

    assert list(result.bundle.array("Close").columns) == [aapl, es]
    assert result.bundle.array("Close")[es].tolist() == [5000.0, 5010.0]
    assert result.bundle.array("Volume")[es].tolist() == [1.0, 2.0]


def test_continuous_future_records_run_economics_and_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = _load_native_and_continuous(monkeypatch)
    es = _id("ES.XCME")

    assert result.adjustment_mode is DEFAULT_ADJUSTMENT_MODE
    assert result.evidence.continuous_root_currencies == {es: "USD"}
    assert result.size_increment_by_instrument[es] == 1.0
    assert len(result.evidence.distribution_coverage) == 2
    assert result.evidence.distribution_coverage[0]["instrument_id"] == "AAPL.NASDAQ"
    assert result.evidence.distribution_coverage[0]["applicable"] is True
    assert result.evidence.distribution_coverage[1]["instrument_id"] == "ES.XCME"
    assert result.evidence.distribution_coverage[1]["applicable"] is False


def test_converts_non_base_continuous_root_through_exchange_fx(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    es = _id("ES.XCME")
    eurusd = _id("EUR/USD.IDEALPRO")
    index = pd.DatetimeIndex(["2024-01-01", "2024-01-02"])
    port = _fake_port(
        {eurusd: _frame(index, close=[1.25, 1.20], volume=[0.0, 0.0])},
        legs=[future("ESH4.XCME", "2024-03-15")],
        exchange=(eurusd,),
    )

    class FakeContinuousModel:
        quote_currency = "USD"

        def __init__(self, _port_arg, _root, **_kwargs):
            self.continuous_id = es
            self.frame = _frame(index, close=[5000.0, 5010.0], volume=[1.0, 2.0])

        def materialize(self, *, end: str) -> None:
            pass

    monkeypatch.setattr(run_data_module, "ContinuousContractModel", FakeContinuousModel)
    config = make_data_config(
        arrays=["Close", "Volume"],
        base_currency="EUR",
        instruments=[],
        futures=["ES"],
        exchange=["EUR/USD.IDEALPRO"],
    )

    result = load_run_data(
        config,
        required_arrays=("Close", "Volume"),
        port=port,
        custom_data_providers=None,
    )

    assert result.bundle.array("Close")[es].tolist() == pytest.approx(
        [5000.0 / 1.25, 5010.0 / 1.20]
    )
    assert result.currency_conversion.currency_by_instrument_id == {es: "USD"}
    assert result.evidence.continuous_root_currencies == {es: "USD"}


@pytest.mark.parametrize(
    ("mode", "expected_evidence", "expected_close"),
    [
        (
            ContinuousFutureAdjustmentType.BACKWARD_RATIO,
            "backward_ratio",
            [5000.0, 5010.0],
        ),
        (
            ContinuousFutureAdjustmentType.BACKWARD_SPREAD,
            "backward_spread",
            [6000.0, 6010.0],
        ),
    ],
)
def test_adjustment_mode_is_recorded_in_evidence_identity(
    monkeypatch: pytest.MonkeyPatch,
    mode: ContinuousFutureAdjustmentType,
    expected_evidence: str,
    expected_close: list[float],
) -> None:
    es = _id("ES.XCME")
    index = pd.DatetimeIndex(["2024-01-01", "2024-01-02"])
    port = _fake_port({}, legs=[future("ESH4.XCME", "2024-03-15")])

    class FakeContinuousModel:
        quote_currency = "USD"

        def __init__(self, _port_arg, _root, *, adjustment_mode, **_kwargs):
            self.continuous_id = es
            close = (
                [5000.0, 5010.0]
                if adjustment_mode is ContinuousFutureAdjustmentType.BACKWARD_RATIO
                else [6000.0, 6010.0]
            )
            self.frame = _frame(index, close=close, volume=[1.0, 2.0])

        def materialize(self, *, end: str) -> None:
            pass

    monkeypatch.setattr(run_data_module, "ContinuousContractModel", FakeContinuousModel)
    monkeypatch.setattr(run_data_module, "DEFAULT_ADJUSTMENT_MODE", mode)
    config = make_data_config(arrays=["Close"], base_currency="USD", instruments=[], futures=["ES"])
    result = load_run_data(
        config,
        required_arrays=("Close",),
        port=port,
        custom_data_providers=None,
    )

    assert result.bundle.array("Close")[es].tolist() == expected_close
    assert result.evidence.adjustment_mode == expected_evidence


def test_adjustment_modes_produce_distinct_candidate_data_identities(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ratio = _load_adjustment_mode(
        monkeypatch,
        ContinuousFutureAdjustmentType.BACKWARD_RATIO,
        close=[5000.0, 5010.0],
    )
    spread = _load_adjustment_mode(
        monkeypatch,
        ContinuousFutureAdjustmentType.BACKWARD_SPREAD,
        close=[6000.0, 6010.0],
    )
    contract = build_data_array_contract(configured_arrays=("Close",))

    assert candidate_data_identity(ratio, contract) != candidate_data_identity(spread, contract)


def _load_adjustment_mode(
    monkeypatch: pytest.MonkeyPatch,
    mode: ContinuousFutureAdjustmentType,
    *,
    close: list[float],
) -> RunData:
    es = _id("ES.XCME")
    index = pd.DatetimeIndex(["2024-01-01", "2024-01-02"])
    port = _fake_port({}, legs=[future("ESH4.XCME", "2024-03-15")])

    class FakeContinuousModel:
        quote_currency = "USD"

        def __init__(self, _port_arg, _root, **_kwargs):
            self.continuous_id = es
            self.frame = _frame(index, close=close, volume=[1.0, 2.0])

        def materialize(self, *, end: str) -> None:
            pass

    monkeypatch.setattr(run_data_module, "ContinuousContractModel", FakeContinuousModel)
    monkeypatch.setattr(run_data_module, "DEFAULT_ADJUSTMENT_MODE", mode)
    config = make_data_config(arrays=["Close"], base_currency="USD", instruments=[], futures=["ES"])
    return load_run_data(
        config,
        required_arrays=("Close",),
        port=port,
        custom_data_providers=None,
    )


def test_continuous_failure_evidence_identifies_the_requested_root_and_arrays(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    port = _fake_port({}, legs=[future("ESH4.XCME", "2024-03-15")])

    class FailingContinuousModel:
        def __init__(self, _port_arg, _root, **_kwargs):
            pass

        def materialize(self, *, end: str) -> None:
            raise GapFillProviderError("continuous source unavailable")

    monkeypatch.setattr(run_data_module, "ContinuousContractModel", FailingContinuousModel)
    config = make_data_config(arrays=["Close"], base_currency="USD", instruments=[], futures=["ES"])

    with pytest.raises(RunDataUnavailable) as excinfo:
        load_run_data(
            config,
            required_arrays=("Close",),
            port=port,
            custom_data_providers=None,
        )

    assert excinfo.value.evidence.requested_instrument_ids == ()
    assert excinfo.value.evidence.requested_arrays == ("Close",)
    assert excinfo.value.evidence.continuous_roots == ("ES",)
    assert isinstance(excinfo.value.__cause__, GapFillProviderError)


def test_rejects_continuous_root_collision_as_authoring_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    es = _id("ES.XCME")
    index = pd.DatetimeIndex(["2024-01-01", "2024-01-02"])
    port = _fake_port(
        {es: _frame(index, close=[10.0, 11.0], volume=[1.0, 1.0])},
        legs=[future("ESH4.XCME", "2024-03-15")],
    )

    class FakeContinuousModel:
        quote_currency = "USD"

        def __init__(self, _port_arg, _root, **_kwargs):
            self.continuous_id = es
            self.frame = _frame(index, close=[99.0, 99.0], volume=[9.0, 9.0])

        def materialize(self, *, end: str) -> None:
            pass

    monkeypatch.setattr(run_data_module, "ContinuousContractModel", FakeContinuousModel)
    config = make_data_config(
        arrays=["Close"],
        base_currency="USD",
        instruments=["ES.XCME"],
        futures=["ES"],
    )

    with pytest.raises(ContinuousRootCollisionError, match="collide with raw instrument ids"):
        load_run_data(
            config,
            required_arrays=("Close",),
            port=port,
            custom_data_providers=None,
        )


def test_rejects_missing_window_edge_as_authoring_error() -> None:
    port = _fake_port({})
    config = make_data_config(
        arrays=["Close"],
        base_currency="USD",
        instruments=[],
        futures=["ES"],
        start=None,
    )

    with pytest.raises(RunDataWindowBoundsError, match=r"data\.start is required"):
        load_run_data(
            config,
            required_arrays=("Close",),
            port=port,
            custom_data_providers=None,
        )
