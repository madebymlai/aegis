"""Quality verdicts at their right altitude (aegis-rd-1gef.4).

Loader-reachable scenarios — real data defects a catalog can hold — drive the
full load → observe → judge → describe sequence through
``load_market_data_result(port=...)`` over a seeded corpus, the same wiring
production uses.  Shapes the real catalog loader cannot emit (synthetic
natives, custom index evidence, absent instruments) exercise the leaf
interfaces directly through hand-built ``MarketDataLoad`` values
(``result_from_load``), the leaf seam RD ADR-0005 created.
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

import numpy as np
import pandas as pd
from aegis_data.catalog import CatalogBackedDataPort
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.persistence.catalog import ParquetDataCatalog

from research.aegis_research.data import (
    DataArrayDiagnostics,
    DataDiagnostics,
    load_market_data_result,
    required_experiment_ohlcv_arrays,
)
from research.aegis_research.market_data import quality as data_quality
from research.aegis_research.market_data.adapters._support import index_evidence
from research.aegis_research.market_data.contracts import MarketDataLoad
from tests.support.research.aegis_research.factories import (
    make_data_config,
    make_data_quality_config,
    make_signal_config,
)
from tests.support.research.aegis_research.market_data_fixtures import (
    result_from_load,
    seed_catalog_frames,
)


def test_quality_verdict_is_derived_from_typed_diagnostics_without_panels() -> None:
    quality = data_quality.evaluate(
        make_data_config(instruments=["SYN.XNAS"], arrays=["Close"]),
        (
            DataDiagnostics(
                instrument_id=_id("SYN.XNAS"),
                configured=True,
                arrays={
                    "Close": DataArrayDiagnostics(
                        available=True,
                        rows=3,
                        missing=1,
                        numeric=False,
                    )
                },
            ),
        ),
        required_arrays=("Close",),
        index_evidence={
            "raw_index_has_duplicates": True,
            "raw_index_monotonic_increasing": False,
        },
    )

    assert quality.state == "rejected"
    assert quality.reasons == (
        "raw data index contains duplicate timestamps",
        "raw data index is not monotonic increasing",
        "required array 'Close' contains missing values",
        "required array 'Close' has non-numeric instrument IDs ['SYN.XNAS']",
    )


# --------------------------------------------------------------------------- #
# port altitude: real data defects behind the production port
# --------------------------------------------------------------------------- #

_DAYS = ["2024-01-01", "2024-01-02", "2024-01-03"]


def _ohlcv(days: list[str], close: list[float]) -> pd.DataFrame:
    index = pd.DatetimeIndex([pd.Timestamp(day) for day in days])
    return pd.DataFrame(
        {
            "Open": close,
            "High": [value + 1 for value in close],
            "Low": [value - 1 for value in close],
            "Close": close,
            "Volume": [100.0] * len(close),
        },
        index=index,
    )


def _catalog_result(
    tmp_path: Path,
    frames: dict[str, pd.DataFrame],
    *,
    required_arrays: tuple[str, ...] | None = None,
    **config_overrides: object,
):
    catalog_path = tmp_path / "catalog"
    seed_catalog_frames(catalog_path, frames, start=_DAYS[0], end=_DAYS[-1])
    config = make_data_config(
        base_currency="USD",
        instruments=list(frames),
        start=_DAYS[0],
        end=_DAYS[-1],
        **config_overrides,
    )
    port = CatalogBackedDataPort(ParquetDataCatalog(catalog_path))
    return load_market_data_result(config, required_arrays=required_arrays, port=port)


def test_missing_required_rows_are_rejected_by_default(tmp_path: Path) -> None:
    # SYN2 has no bar on the middle day: a real calendar hole in the corpus
    # surfaces as a missing value after panel alignment and fails the gate.
    result = _catalog_result(
        tmp_path,
        {
            "SYN.XNAS": _ohlcv(_DAYS, [1.0, 2.0, 3.0]),
            "SYN2.XNAS": _ohlcv([_DAYS[0], _DAYS[2]], [5.0, 7.0]),
        },
        arrays=["Close"],
    )

    assert result.quality.state == "rejected"
    assert "required array 'Close' contains missing values" in result.quality.reasons


def test_allowed_missing_rows_are_degraded_allowed(tmp_path: Path) -> None:
    result = _catalog_result(
        tmp_path,
        {
            "SYN.XNAS": _ohlcv(_DAYS, [1.0, 2.0, 3.0]),
            "SYN2.XNAS": _ohlcv([_DAYS[0], _DAYS[2]], [5.0, 7.0]),
        },
        arrays=["Close"],
        quality=make_data_quality_config(allowed_degradations=["missing_rows"]),
    )

    assert result.quality.state == "degraded_allowed"
    assert "required array 'Close' contains missing values" in result.quality.warnings


def test_close_only_array_does_not_require_unconfigured_ohlcv_arrays(
    tmp_path: Path,
) -> None:
    result = _catalog_result(
        tmp_path,
        {"SYN.XNAS": _ohlcv(_DAYS, [1.0, 2.0, 3.0])},
        arrays=["Close"],
    )

    assert result.quality.state == "healthy"
    assert result.quality.warnings == ()


def test_next_open_feature_requirement_rejects_close_only_data(tmp_path: Path) -> None:
    result = _catalog_result(
        tmp_path,
        {"SYN.XNAS": _ohlcv(_DAYS, [1.0, 2.0, 3.0])},
        arrays=["Close"],
        required_arrays=required_experiment_ohlcv_arrays(signal_config=make_signal_config()),
    )

    assert result.quality.state == "rejected"
    assert "required array 'Open' is unavailable" in result.quality.reasons


def test_same_close_feature_requirement_allows_close_only_data(tmp_path: Path) -> None:
    result = _catalog_result(
        tmp_path,
        {"SYN.XNAS": _ohlcv(_DAYS, [1.0, 2.0, 3.0])},
        arrays=["Close"],
        required_arrays=required_experiment_ohlcv_arrays(
            signal_config=make_signal_config(execution_timing="same_close")
        ),
    )

    assert result.quality.state == "healthy"


def test_explicit_high_low_requirement_rejects_close_only_data(tmp_path: Path) -> None:
    result = _catalog_result(
        tmp_path,
        {"SYN.XNAS": _ohlcv(_DAYS, [1.0, 2.0, 3.0])},
        arrays=["Close"],
        required_arrays=("Close", "High", "Low"),
    )

    assert result.quality.state == "rejected"
    assert "required array 'High' is unavailable" in result.quality.reasons
    assert "required array 'Low' is unavailable" in result.quality.reasons


# --------------------------------------------------------------------------- #
# leaf altitude: shapes the catalog loader cannot emit
# --------------------------------------------------------------------------- #


def test_duplicate_index_evidence_is_rejected() -> None:
    frame = pd.DataFrame(
        {"Close": [1.0, 2.0, 3.0]},
        index=pd.to_datetime(["2020-01-01", "2020-01-01", "2020-01-02"], utc=True),
    )
    config = make_data_config(instruments=["SYN.XNAS"], arrays=["Close"])

    result = result_from_load(config, _load(_native_data(frame), frame))

    assert result.quality.state == "rejected"
    assert "raw data index contains duplicate timestamps" in result.quality.reasons
    assert result.metadata.provenance.index_evidence["raw_index_has_duplicates"] is True


def test_non_monotonic_index_evidence_is_rejected() -> None:
    # The catalog loader sorts bars into a monotonic index, so this shape can
    # only be staged at the leaf seam with hand-built evidence.
    frame = pd.DataFrame(
        {"Close": [1.0, 2.0, 3.0]},
        index=pd.to_datetime(["2020-01-02", "2020-01-01", "2020-01-03"], utc=True),
    )
    config = make_data_config(instruments=["SYN.XNAS"], arrays=["Close"])

    result = result_from_load(config, _load(_native_data(frame), frame))

    assert result.quality.state == "rejected"
    assert "raw data index is not monotonic increasing" in result.quality.reasons


def test_next_open_signal_timing_requires_open_feature() -> None:
    assert required_experiment_ohlcv_arrays() == ("Close", "Open")
    assert required_experiment_ohlcv_arrays(signal_config=make_signal_config()) == ("Close", "Open")


def test_same_close_signal_timing_does_not_require_open_feature() -> None:
    assert required_experiment_ohlcv_arrays(
        signal_config=make_signal_config(execution_timing="same_close")
    ) == ("Close",)


def test_next_close_signal_timing_does_not_require_open_feature() -> None:
    assert required_experiment_ohlcv_arrays(
        signal_config=make_signal_config(execution_timing="next_close")
    ) == ("Close",)


def test_skipped_symbol_requires_skip_policy_opt_in() -> None:
    native_data = _native_data(_close_frame(5), instrument_id="AAA.XNAS")

    result = result_from_load(
        make_data_config(instruments=["AAA.XNAS", "BBB.XNAS"], arrays=["Close"]),
        MarketDataLoad(native_data=native_data),
    )

    assert result.quality.state == "rejected"
    assert (
        "configured instrument IDs missing from loaded data: ['BBB.XNAS']" in result.quality.reasons
    )


def test_skipped_symbol_with_explicit_policy_is_degraded_allowed() -> None:
    native_data = _native_data(_close_frame(5), instrument_id="AAA.XNAS")

    result = result_from_load(
        make_data_config(
            instruments=["AAA.XNAS", "BBB.XNAS"],
            arrays=["Close"],
            quality=make_data_quality_config(allowed_degradations=["skipped_instrument_ids"]),
        ),
        MarketDataLoad(native_data=native_data),
    )

    assert result.quality.state == "degraded_allowed"
    assert (
        "configured instrument IDs missing from loaded data: ['BBB.XNAS']"
        in result.quality.warnings
    )


def test_custom_index_evidence_is_carried_into_provenance() -> None:
    native_data = _native_data(_close_frame(5), instrument_id="AAA.XNAS")

    result = result_from_load(
        make_data_config(instruments=["AAA.XNAS"]),
        MarketDataLoad(
            native_data=native_data,
            evidence={"source": "post_vectorbt_alignment"},
        ),
    )

    assert result.metadata.provenance.index_evidence["source"] == "post_vectorbt_alignment"


def _id(value: str) -> InstrumentId:
    return InstrumentId.from_str(value)


def test_provider_update_support_uses_symbol_update_capability() -> None:
    result = result_from_load(
        make_data_config(instruments=["SYN.XNAS"]),
        MarketDataLoad(native_data=_UpdateCapableProviderData()),
    )

    assert result.metadata.provenance.update_supported is True


def test_provider_update_support_uses_feature_update_capability() -> None:
    result = result_from_load(
        make_data_config(instruments=["SYN.XNAS"]),
        MarketDataLoad(native_data=_FeatureUpdateProviderData()),
    )

    assert result.metadata.provenance.update_supported is True


class _ProviderMetadataData:
    index = pd.date_range("2020-01-01", periods=3, freq="1D", tz="UTC")
    features: ClassVar[list[str]] = ["Close"]
    symbols: ClassVar[list[InstrumentId]] = [_id("SYN.XNAS")]
    fetch_kwargs: ClassVar[dict[str, object]] = {
        "period": "1mo",
        "limit": 100,
        "headers": {"period": "sessionid=abc"},
        "cache_path": "/home/alice/cache.db",
    }
    returned_kwargs: ClassVar[dict[str, object]] = {"freq": "1D", "auth": {"tz": "UTC"}}

    def get(self, feature=None, **_kwargs) -> pd.DataFrame:
        if feature not in {None, "Close"}:
            raise ValueError(feature)
        return pd.DataFrame({_id("SYN.XNAS"): [1.0, 2.0, 3.0]}, index=self.index)


class _UpdateCapableProviderData(_ProviderMetadataData):
    symbol_oriented = True

    def update_symbol(self, symbol: str, **_kwargs) -> pd.DataFrame:
        return pd.DataFrame({symbol: [4.0]}, index=self.index[:1])


class _FeatureUpdateProviderData(_ProviderMetadataData):
    feature_oriented = True

    def update_feature(self, feature: str, **_kwargs) -> pd.DataFrame:
        return pd.DataFrame({_id("SYN.XNAS"): [4.0]}, index=self.index[:1])


def _load(native_data: object, frame: pd.DataFrame) -> MarketDataLoad:
    return MarketDataLoad(
        native_data=native_data,
        evidence=index_evidence(frame.index, source="test_fixture"),
    )


def _close_frame(periods: int) -> pd.DataFrame:
    return pd.DataFrame(
        {"Close": np.arange(1, periods + 1, dtype=float)},
        index=pd.date_range("2020-01-01", periods=periods, tz="UTC"),
    )


def _native_data(frame: pd.DataFrame, *, instrument_id: str = "SYN.XNAS") -> pd.DataFrame:
    native = frame.copy()
    native.columns = pd.MultiIndex.from_product(
        [[_id(instrument_id)], native.columns],
        names=["symbol", "feature"],
    )
    return native
