from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from aegis_data.catalog import (
    CatalogBackedDataPort,
    CatalogCoverageGapError,
    GapFillProviderError,
)
from aegis_data.custom_data import (
    CustomDataCoverageError,
    FixtureRecord,
    ServedCustomData,
)
from aegis_data.distributions import Distribution, write_distribution_data
from aegis_data.testing import FakeCatalog
from nautilus_trader.model.data import BarType
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.persistence.catalog import ParquetDataCatalog

from research.aegis_research.canonical_json import to_builtin
from research.aegis_research.instrument_resolution import TradeableInstrument
from research.aegis_research.run import data as run_data_module
from research.aegis_research.run.data import (
    RunDataEmptyArrayError,
    RunDataIndexMismatchError,
    RunDataMissingArrayError,
    RunDataMissingValueError,
    RunDataNonNumericArrayError,
    RunDataUnavailable,
    load_run_data,
)
from tests.support.research.aegis_research.factories import make_data_config
from tests.support.research.aegis_research.market_data_fixtures import (
    OHLCV_ARRAY_NAMES,
    UnservableCatalog,
    equity_definition,
    instrument_id,
    seed_catalog_frames,
    seed_catalog_fx,
    seed_catalog_ohlcv,
    unservable_port,
)


def test_load_run_data_returns_an_eager_native_bundle_from_one_catalog_window(
    tmp_path: Path,
) -> None:
    catalog_path = tmp_path / "catalog"
    start, end = seed_catalog_ohlcv(
        catalog_path,
        ["MSFT.XNAS", "AAPL.XNAS"],
        periods=3,
        currency="USD",
    )
    seed_catalog_fx(catalog_path, periods=3)
    config = make_data_config(
        arrays=["OHLCV"],
        base_currency="USD",
        instruments=["MSFT.XNAS", "AAPL.XNAS"],
        exchange=["EUR/USD.IDEALPRO"],
        start=start,
        end=end,
        path=str(catalog_path),
    )
    port = CatalogBackedDataPort(
        ParquetDataCatalog(catalog_path),
        resolver=config.marking_resolver(),
    )

    run_data = load_run_data(
        config,
        required_arrays=("Open", "Close"),
        port=port,
        custom_data_providers=None,
    )

    expected_ids = (
        InstrumentId.from_str("MSFT.XNAS"),
        InstrumentId.from_str("AAPL.XNAS"),
    )
    assert run_data.instrument_resolution.tradeables == (
        TradeableInstrument(expected_ids[0]),
        TradeableInstrument(expected_ids[1]),
    )
    assert tuple(run_data.bundle.arrays) == OHLCV_ARRAY_NAMES
    assert tuple(run_data.bundle.array("Open").columns) == expected_ids
    assert tuple(run_data.bundle.array("Close").columns) == expected_ids
    assert len(run_data.bundle.array("Close").index) == 3
    assert run_data.replay_index.equals(run_data.bundle.array("Close").index)
    assert run_data.instrument_count == 2
    evidence = to_builtin(run_data.evidence)
    assert evidence["schema_version"] == "run_data.v1"
    assert evidence["requested_instrument_ids"] == [
        "MSFT.XNAS",
        "AAPL.XNAS",
        "EUR/USD.IDEALPRO",
    ]
    assert evidence["loaded_arrays"] == list(OHLCV_ARRAY_NAMES)
    assert (
        not {
            "healthy",
            "quality",
            "quality_state",
            "unavailable_arrays",
            "skipped_instruments",
        }
        & evidence.keys()
    )


def test_load_run_data_drops_calendar_rows_missing_from_any_tradeable(
    tmp_path: Path,
) -> None:
    catalog_path = tmp_path / "catalog"
    seed_catalog_frames(
        catalog_path,
        {
            "MSFT.XNAS": _ohlcv(["2024-01-01", "2024-01-02", "2024-01-03"]),
            "AAPL.XNAS": _ohlcv(["2024-01-01", "2024-01-03"]),
        },
        start="2024-01-01",
        end="2024-01-03",
        currency="USD",
    )
    config = make_data_config(
        arrays=["Open", "Close"],
        base_currency="USD",
        instruments=["MSFT.XNAS", "AAPL.XNAS"],
        start="2024-01-01",
        end="2024-01-03",
        missing_index="drop",
    )
    port = CatalogBackedDataPort(ParquetDataCatalog(catalog_path))

    run_data = load_run_data(
        config,
        required_arrays=("Open", "Close"),
        port=port,
        custom_data_providers=None,
    )

    assert run_data.bundle.array("Close").index.tolist() == [
        pd.Timestamp("2024-01-01"),
        pd.Timestamp("2024-01-03"),
    ]


def test_load_run_data_rejects_mismatching_tradeable_calendars_under_raise(
    tmp_path: Path,
) -> None:
    catalog_path = tmp_path / "catalog"
    seed_catalog_frames(
        catalog_path,
        {
            "MSFT.XNAS": _ohlcv(["2024-01-01", "2024-01-02", "2024-01-03"]),
            "AAPL.XNAS": _ohlcv(["2024-01-01", "2024-01-03"]),
        },
        start="2024-01-01",
        end="2024-01-03",
        currency="USD",
    )
    config = make_data_config(
        arrays=["Open", "Close"],
        base_currency="USD",
        instruments=["MSFT.XNAS", "AAPL.XNAS"],
        start="2024-01-01",
        end="2024-01-03",
        missing_index="raise",
    )
    port = CatalogBackedDataPort(ParquetDataCatalog(catalog_path))

    with pytest.raises(RunDataIndexMismatchError, match="mismatching indexes"):
        load_run_data(
            config,
            required_arrays=("Open", "Close"),
            port=port,
            custom_data_providers=None,
        )


def test_load_run_data_carries_compact_failure_evidence_for_catalog_gaps() -> None:
    config = make_data_config(
        arrays=["Open", "Close"],
        base_currency="USD",
        instruments=["MSFT.XNAS"],
        start="2024-01-01",
        end="2024-01-03",
    )

    with pytest.raises(RunDataUnavailable) as excinfo:
        load_run_data(
            config,
            required_arrays=("Open", "Close"),
            port=unservable_port(),
            custom_data_providers=None,
        )

    assert isinstance(excinfo.value.__cause__, CatalogCoverageGapError)
    evidence = to_builtin(excinfo.value.evidence)
    assert evidence["schema_version"] == "run_data_failure.v1"
    assert evidence["requested_instrument_ids"] == ["MSFT.XNAS"]
    assert evidence["error_type"] == "CatalogCoverageGapError"
    assert "quality" not in evidence


def test_load_run_data_chains_gap_fill_provider_failures() -> None:
    msft = instrument_id("MSFT.XNAS")
    config = make_data_config(
        arrays=["Open", "Close"],
        base_currency="USD",
        instruments=[msft.value],
        start="2024-01-01",
        end="2024-01-03",
    )
    port = CatalogBackedDataPort(
        UnservableCatalog(instruments=[equity_definition(msft, "USD")], bars={}),
        provider=_BrokenProvider(),
    )

    with pytest.raises(RunDataUnavailable) as excinfo:
        load_run_data(
            config,
            required_arrays=("Open", "Close"),
            port=port,
            custom_data_providers=None,
        )

    assert isinstance(excinfo.value.__cause__, GapFillProviderError)
    assert isinstance(excinfo.value.__cause__.__cause__, RuntimeError)
    assert excinfo.value.evidence.error_type == "GapFillProviderError"


def test_load_run_data_keeps_authoring_errors_direct() -> None:
    config = make_data_config(
        arrays=["Close"],
        base_currency="USD",
        instruments=["MSFT.XNAS"],
        start="2024-01-01",
        end="2024-01-03",
    )

    with pytest.raises(RunDataMissingArrayError, match="missing required Arrays") as excinfo:
        load_run_data(
            config,
            required_arrays=("Open", "Close"),
            port=CatalogBackedDataPort(FakeCatalog(instruments=[], bars={})),
            custom_data_providers=None,
        )

    assert excinfo.value.__cause__ is None


def test_load_run_data_applies_one_catalog_currency_conversion_to_the_bundle(
    tmp_path: Path,
) -> None:
    catalog_path = tmp_path / "catalog"
    seed_catalog_frames(
        catalog_path,
        {"AAPL.XNAS": _flat_ohlcv(100.0)},
        start="2024-01-01",
        end="2024-01-02",
        currency="USD",
    )
    seed_catalog_frames(
        catalog_path,
        {"EUNL.XETR": _flat_ohlcv(200.0)},
        start="2024-01-01",
        end="2024-01-02",
        currency="EUR",
    )
    seed_catalog_fx(catalog_path, periods=2, base_rate=2.0, drift=0.0)
    config = make_data_config(
        arrays=["OHLCV"],
        base_currency="EUR",
        instruments=["AAPL.XNAS", "EUNL.XETR"],
        exchange=["EUR/USD.IDEALPRO"],
        start="2024-01-01",
        end="2024-01-02",
    )
    port = CatalogBackedDataPort(
        ParquetDataCatalog(catalog_path),
        resolver=config.marking_resolver(),
    )

    run_data = load_run_data(
        config,
        required_arrays=("Open", "Close"),
        port=port,
        custom_data_providers=None,
    )

    aapl = InstrumentId.from_str("AAPL.XNAS")
    eunl = InstrumentId.from_str("EUNL.XETR")
    assert run_data.bundle.array("Open")[aapl].tolist() == [50.0, 50.0]
    assert run_data.bundle.array("Close")[aapl].tolist() == [50.0, 50.0]
    assert run_data.bundle.array("High")[aapl].tolist() == [50.0, 50.0]
    assert run_data.bundle.array("Low")[aapl].tolist() == [50.0, 50.0]
    assert run_data.bundle.array("Volume")[aapl].tolist() == [100.0, 100.0]
    assert run_data.bundle.array("Close")[eunl].tolist() == [200.0, 200.0]
    assert tuple(run_data.bundle.array("Close").columns) == (aapl, eunl)
    assert run_data.currency_conversion.currency_by_instrument_id == {
        aapl: "USD",
        eunl: "EUR",
    }
    assert not hasattr(run_data, "pnl_close")
    assert not hasattr(run_data, "pnl_open")


def test_load_run_data_carries_verified_distributions_and_native_size_increments(
    tmp_path: Path,
) -> None:
    catalog_path = tmp_path / "catalog"
    seed_catalog_ohlcv(
        catalog_path,
        ["AAPL.XNAS"],
        periods=3,
        currency="USD",
    )
    aapl = InstrumentId.from_str("AAPL.XNAS")
    distribution = Distribution.from_ex_date(
        aapl,
        "2024-01-02",
        amount=0.42,
        currency="USD",
    )
    write_distribution_data(ParquetDataCatalog(catalog_path), [distribution])
    config = make_data_config(
        arrays=["OHLCV"],
        base_currency="USD",
        instruments=[aapl.value],
        start="2024-01-01",
        end="2024-01-03",
    )
    port = CatalogBackedDataPort(ParquetDataCatalog(catalog_path))

    run_data = load_run_data(
        config,
        required_arrays=("Open", "Close"),
        port=port,
        custom_data_providers=None,
    )

    assert len(run_data.distributions) == 1
    assert run_data.distributions[0].instrument_id == aapl
    assert run_data.distributions[0].ex_date == distribution.ex_date
    assert run_data.distributions[0].amount == pytest.approx(0.42)
    assert run_data.size_increment_by_instrument == {aapl: 1.0}


def test_load_run_data_persists_and_warm_reads_custom_arrays_without_provider_identity(
    tmp_path: Path,
) -> None:
    catalog_path = tmp_path / "catalog"
    seed_catalog_ohlcv(
        catalog_path,
        ["AAPL.XNAS"],
        periods=3,
        currency="USD",
    )
    config = make_data_config(
        arrays=["Open", "Close", "FixtureValue", "FixtureAvailable"],
        base_currency="USD",
        instruments=["AAPL.XNAS"],
        start="2024-01-01",
        end="2024-01-03",
        path=str(catalog_path),
    )
    provider = _FixtureProvider(secret="credential-must-not-persist")
    port = CatalogBackedDataPort(ParquetDataCatalog(catalog_path))

    cold = load_run_data(
        config,
        required_arrays=("Open", "Close", "FixtureValue", "FixtureAvailable"),
        port=port,
        custom_data_providers={FixtureRecord: (provider,)},
    )
    warm = load_run_data(
        config,
        required_arrays=("Open", "Close", "FixtureValue", "FixtureAvailable"),
        port=port,
        custom_data_providers={FixtureRecord: (provider,)},
    )

    aapl = InstrumentId.from_str("AAPL.XNAS")
    assert cold.bundle.array("FixtureValue")[aapl].tolist() == [0.0, 0.0, 7.0]
    assert cold.bundle.array("FixtureAvailable")[aapl].tolist() == [0.0, 0.0, 1.0]
    assert warm.bundle.array("FixtureValue").equals(cold.bundle.array("FixtureValue"))
    assert warm.evidence == cold.evidence
    assert len(provider.requests) == 1
    assert "credential-must-not-persist" not in str(to_builtin(cold.evidence))


def test_load_run_data_reports_missing_custom_coverage_as_unavailable(
    tmp_path: Path,
) -> None:
    config, port = _custom_config_and_port(tmp_path)

    with pytest.raises(RunDataUnavailable) as excinfo:
        load_run_data(
            config,
            required_arrays=("Open", "Close", "FixtureValue"),
            port=port,
            custom_data_providers=None,
        )

    assert isinstance(excinfo.value.__cause__, CustomDataCoverageError)
    assert excinfo.value.evidence.error_type == "CustomDataCoverageError"


def test_load_run_data_chains_custom_provider_failures(tmp_path: Path) -> None:
    config, port = _custom_config_and_port(tmp_path)

    with pytest.raises(RunDataUnavailable) as excinfo:
        load_run_data(
            config,
            required_arrays=("Open", "Close", "FixtureValue"),
            port=port,
            custom_data_providers={FixtureRecord: (_FailingFixtureProvider(),)},
        )

    assert isinstance(excinfo.value.__cause__, GapFillProviderError)
    assert isinstance(excinfo.value.__cause__.__cause__, RuntimeError)
    assert "custom provider offline" in str(excinfo.value.__cause__.__cause__)


def test_load_run_data_keeps_incompatible_custom_values_direct(tmp_path: Path) -> None:
    config, port = _custom_config_and_port(tmp_path)

    with pytest.raises(RunDataMissingValueError, match="contains missing values") as excinfo:
        load_run_data(
            config,
            required_arrays=("Open", "Close", "FixtureValue"),
            port=port,
            custom_data_providers={FixtureRecord: (_NonFiniteFixtureProvider(),)},
        )

    assert not isinstance(excinfo.value, RunDataUnavailable)


def test_load_run_data_rejects_an_empty_required_custom_array(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config, port = _custom_config_and_port(tmp_path)
    aapl = InstrumentId.from_str("AAPL.XNAS")
    monkeypatch.setattr(run_data_module, "ensure_arrays", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        run_data_module,
        "custom_arrays",
        lambda *_args, **_kwargs: {"FixtureValue": pd.DataFrame({aapl: pd.Series(dtype=float)})},
    )

    with pytest.raises(RunDataEmptyArrayError, match="required Array 'FixtureValue' is empty"):
        load_run_data(
            config,
            required_arrays=("Close", "FixtureValue"),
            port=port,
            custom_data_providers=None,
        )


def test_load_run_data_rejects_a_nonnumeric_required_custom_array(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config, port = _custom_config_and_port(tmp_path)
    aapl = InstrumentId.from_str("AAPL.XNAS")
    index = pd.date_range("2024-01-01", periods=3, freq="D")
    monkeypatch.setattr(run_data_module, "ensure_arrays", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        run_data_module,
        "custom_arrays",
        lambda *_args, **_kwargs: {
            "FixtureValue": pd.DataFrame({aapl: ["bad", "bad", "bad"]}, index=index)
        },
    )

    with pytest.raises(
        RunDataNonNumericArrayError,
        match="required Array 'FixtureValue' contains nonnumeric values",
    ):
        load_run_data(
            config,
            required_arrays=("Close", "FixtureValue"),
            port=port,
            custom_data_providers=None,
        )


def _ohlcv(days: list[str]) -> pd.DataFrame:
    values = [float(position + 1) for position in range(len(days))]
    return pd.DataFrame(
        {
            "Open": values,
            "High": values,
            "Low": values,
            "Close": values,
            "Volume": [100.0] * len(days),
        },
        index=pd.to_datetime(days),
    )


def _flat_ohlcv(value: float) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Open": [value, value],
            "High": [value, value],
            "Low": [value, value],
            "Close": [value, value],
            "Volume": [100.0, 100.0],
        },
        index=pd.to_datetime(["2024-01-01", "2024-01-02"]),
    )


def _custom_config_and_port(tmp_path: Path):
    catalog_path = tmp_path / "catalog"
    seed_catalog_ohlcv(
        catalog_path,
        ["AAPL.XNAS"],
        periods=3,
        currency="USD",
    )
    config = make_data_config(
        arrays=["Open", "Close", "FixtureValue"],
        base_currency="USD",
        instruments=["AAPL.XNAS"],
        start="2024-01-01",
        end="2024-01-03",
        path=str(catalog_path),
    )
    return config, CatalogBackedDataPort(ParquetDataCatalog(catalog_path))


class _BrokenProvider:
    def request_bars(self, bar_type: BarType, **_kwargs: object) -> object:
        raise RuntimeError(f"gateway dropped while fetching {bar_type}")


class _FixtureProvider:
    def __init__(self, *, secret: str) -> None:
        self.secret = secret
        self.requests: list[tuple[InstrumentId, pd.Timestamp, pd.Timestamp]] = []

    def request_records(
        self,
        instrument_id: InstrumentId,
        *,
        start: pd.Timestamp,
        end: pd.Timestamp,
    ) -> ServedCustomData[FixtureRecord]:
        self.requests.append((instrument_id, start, end))
        record = FixtureRecord(
            end.value,
            end.value,
            instrument_id=instrument_id,
            value=7.0,
            provider="fixture",
        )
        return ServedCustomData(records=(record,), served_from=start)


class _FailingFixtureProvider:
    def request_records(
        self,
        instrument_id: InstrumentId,
        *,
        start: pd.Timestamp,
        end: pd.Timestamp,
    ) -> ServedCustomData[FixtureRecord]:
        raise RuntimeError("custom provider offline")


class _NonFiniteFixtureProvider:
    def request_records(
        self,
        instrument_id: InstrumentId,
        *,
        start: pd.Timestamp,
        end: pd.Timestamp,
    ) -> ServedCustomData[FixtureRecord]:
        record = FixtureRecord(
            end.value,
            end.value,
            instrument_id=instrument_id,
            value=float("nan"),
            provider="fixture",
        )
        return ServedCustomData(records=(record,), served_from=start)
