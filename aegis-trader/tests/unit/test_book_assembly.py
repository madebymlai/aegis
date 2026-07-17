from __future__ import annotations

from dataclasses import FrozenInstanceError
from typing import Any, cast

import pytest
from nautilus_trader.model.enums import ContinuousFutureAdjustmentType
from nautilus_trader.model.identifiers import InstrumentId

from aegis_runtime import DriftBand

from aegis_trader.bundles.book import (
    AssembledBook,
    ContinuousDeclarationConflictError,
    ContinuousRootDeclaration,
    InstrumentBandError,
    MissingAvailabilityArrayError,
    UndeliverableArrayError,
    UnprovisionedArrayError,
    assemble_book,
)
from aegis_trader.bundles.bands import BundleBands
from aegis_trader.bundles.stub import StubBundleRegistry
from aegis_trader.domain.analytics_horizon import AnalyticsHorizon
from aegis_trader.domain.book_config import BookConfig, SleeveConfig
from aegis_trader.domain.streams import MarketStream, StreamRequirement
from aegis_trader.domain.types import SleeveName
from aegis_trader.trader.strategy import (
    BookConfigMismatchError,
    RebalanceStrategy,
    RebalanceStrategyConfig,
)
from tests.support.factories import make_bundle

_AAPL = InstrumentId.from_str("AAPL.NASDAQ")
_ES = InstrumentId.from_str("ES.XCME")
_EURUSD = InstrumentId.from_str("EUR/USD.IDEALPRO")
_MSFT = InstrumentId.from_str("MSFT.NASDAQ")
_RATIO = ContinuousFutureAdjustmentType.BACKWARD_RATIO
_SPREAD = ContinuousFutureAdjustmentType.BACKWARD_SPREAD


def _book(*sleeves: tuple[str, str]) -> BookConfig:
    return BookConfig(
        sleeves=tuple(
            SleeveConfig(
                name=SleeveName(name),
                wheel_filename=wheel,
                risk_share=1.0,
            )
            for name, wheel in sleeves
        )
    )


def test_assemble_book_derives_every_book_fact_from_loaded_sleeves() -> None:
    trend_band = DriftBand(up=0.10, down=0.20)
    carry_band = DriftBand(up=0.30, down=0.40)
    root_band = DriftBand(up=0.50, down=0.60)
    config = _book(("trend", "trend.whl"), ("carry", "carry.whl"))
    trend_bundle = make_bundle(
        native_instrument_ids=(_MSFT,),
        exchange_instrument_ids=(_EURUSD,),
        continuous_futures={"ES": _ES},
        adjustment_mode=_RATIO,
        instrument_bands={_MSFT: trend_band, _ES: root_band},
        lookback_bars=41,
        direction="longonly",
    )
    carry_bundle = make_bundle(
        native_instrument_ids=(_AAPL,),
        instrument_bands={_AAPL: carry_band},
        lookback_bars=20,
        direction="shortonly",
    )
    registry = StubBundleRegistry(
        {"trend.whl": trend_bundle, "carry.whl": carry_bundle}
    )

    assembled = assemble_book(config, registry)

    assert assembled == AssembledBook(
        config=config,
        sleeves={
            SleeveName("carry"): carry_bundle,
            SleeveName("trend"): trend_bundle,
        },
        loadable_instrument_ids=(_AAPL, _EURUSD, _MSFT),
        requires_margin=True,
        continuous_history_bars={"ES": 42},
        bands=BundleBands(
            bands={_AAPL: carry_band, _ES: root_band, _MSFT: trend_band},
            owner_by_instrument={
                _AAPL: SleeveName("carry"),
                _ES: SleeveName("trend"),
                _MSFT: SleeveName("trend"),
            },
        ),
        continuous_declarations={
            "ES": ContinuousRootDeclaration(
                continuous_id=_ES,
                adjustment_mode=_RATIO,
                timeframe="1D",
            )
        },
        sleeve_streams={
            SleeveName("carry"): (MarketStream(_AAPL, "1D"),),
            SleeveName("trend"): (
                MarketStream(_EURUSD, "1D"),
                MarketStream(_MSFT, "1D"),
            ),
        },
        required_streams=(
            StreamRequirement(
                stream=MarketStream(_AAPL, "1D"),
                history_bars=21,
                consumers=(SleeveName("carry"),),
            ),
            StreamRequirement(
                stream=MarketStream(_EURUSD, "1D"),
                history_bars=42,
                consumers=(SleeveName("trend"),),
            ),
            StreamRequirement(
                stream=MarketStream(_MSFT, "1D"),
                history_bars=42,
                consumers=(SleeveName("trend"),),
            ),
        ),
        # Golden: an all-daily roster derives the weekday convention.
        analytics_horizon=AnalyticsHorizon("1D", 252),
    )


def test_assemble_book_exposes_stream_requirements_per_sleeve() -> None:
    config = _book(("trend", "trend.whl"), ("carry", "carry.whl"))
    registry = StubBundleRegistry(
        {
            "trend.whl": make_bundle(
                native_instrument_ids=(_MSFT,),
                exchange_instrument_ids=(_EURUSD,),
                lookback_bars=41,
            ),
            "carry.whl": make_bundle(
                native_instrument_ids=(_AAPL,),
                lookback_bars=20,
            ),
        }
    )

    assembled = assemble_book(config, registry)

    assert assembled.sleeve_streams == {
        SleeveName("carry"): (MarketStream(_AAPL, "1D"),),
        SleeveName("trend"): (
            MarketStream(_EURUSD, "1D"),
            MarketStream(_MSFT, "1D"),
        ),
    }


def test_assemble_book_deduplicates_shared_streams_with_the_deepest_history() -> None:
    config = _book(("trend", "trend.whl"), ("carry", "carry.whl"))
    registry = StubBundleRegistry(
        {
            "trend.whl": make_bundle(
                native_instrument_ids=(_MSFT,),
                exchange_instrument_ids=(_EURUSD,),
                lookback_bars=41,
            ),
            "carry.whl": make_bundle(
                native_instrument_ids=(_AAPL,),
                exchange_instrument_ids=(_EURUSD,),
                lookback_bars=20,
            ),
        }
    )

    assembled = assemble_book(config, registry)

    assert assembled.required_streams == (
        StreamRequirement(
            stream=MarketStream(_AAPL, "1D"),
            history_bars=21,
            consumers=(SleeveName("carry"),),
        ),
        StreamRequirement(
            stream=MarketStream(_EURUSD, "1D"),
            history_bars=42,
            consumers=(SleeveName("carry"), SleeveName("trend")),
        ),
        StreamRequirement(
            stream=MarketStream(_MSFT, "1D"),
            history_bars=42,
            consumers=(SleeveName("trend"),),
        ),
    )


def test_assemble_book_orders_sleeves_ids_and_bands_deterministically() -> None:
    config = _book(("trend", "trend.whl"), ("carry", "carry.whl"))
    registry = StubBundleRegistry(
        {
            "trend.whl": make_bundle(
                native_instrument_ids=(_MSFT,),
                exchange_instrument_ids=(_EURUSD,),
                continuous_futures={"ES": _ES},
            ),
            "carry.whl": make_bundle(native_instrument_ids=(_AAPL,)),
        }
    )

    assembled = assemble_book(config, registry)

    assert (
        tuple(assembled.sleeves),
        assembled.loadable_instrument_ids,
        tuple(assembled.bands.bands),
    ) == (
        (SleeveName("carry"), SleeveName("trend")),
        (_AAPL, _EURUSD, _MSFT),
        (_AAPL, _ES, _MSFT),
    )


def test_assemble_book_accepts_hourly_and_daily_cash_sleeves() -> None:
    config = _book(("trend", "trend.whl"), ("carry", "carry.whl"))
    registry = StubBundleRegistry(
        {
            "trend.whl": make_bundle(
                timeframe="1H",
                native_instrument_ids=(_MSFT,),
                lookback_bars=30,
            ),
            "carry.whl": make_bundle(timeframe="1D", lookback_bars=20),
        }
    )

    assembled = assemble_book(config, registry)

    assert assembled.required_streams == (
        StreamRequirement(
            stream=MarketStream(_AAPL, "1D"),
            history_bars=21,
            consumers=(SleeveName("carry"),),
        ),
        StreamRequirement(
            stream=MarketStream(_MSFT, "1H"),
            history_bars=31,
            consumers=(SleeveName("trend"),),
        ),
    )
    assert not hasattr(assembled, "timeframe")


def test_assemble_book_accepts_different_roots_at_different_timeframes() -> None:
    # One root = one owning Sleeve = one timeframe (aegis-rd-9qkr.5): distinct
    # roots may run at distinct cadences, each declared with its own stream.
    nq = InstrumentId.from_str("NQ.XCME")
    config = _book(("trend", "trend.whl"), ("carry", "carry.whl"))
    registry = StubBundleRegistry(
        {
            "trend.whl": make_bundle(
                timeframe="1H",
                native_instrument_ids=(),
                continuous_futures={"ES": _ES},
                lookback_bars=30,
            ),
            "carry.whl": make_bundle(
                timeframe="1D",
                native_instrument_ids=(),
                continuous_futures={"NQ": nq},
                lookback_bars=20,
            ),
        }
    )

    assembled = assemble_book(config, registry)

    assert assembled.continuous_declarations == {
        "ES": ContinuousRootDeclaration(
            continuous_id=_ES, adjustment_mode=_RATIO, timeframe="1H"
        ),
        "NQ": ContinuousRootDeclaration(
            continuous_id=nq, adjustment_mode=_RATIO, timeframe="1D"
        ),
    }
    assert assembled.continuous_history_bars == {"ES": 31, "NQ": 21}


def test_assemble_book_rejects_one_root_required_at_two_timeframes() -> None:
    # A root consumed at two cadences is an incoherent declaration: one root
    # has one owning Sleeve and one required stream (aegis-rd-9qkr.5).
    config = _book(("trend", "trend.whl"), ("carry", "carry.whl"))
    registry = StubBundleRegistry(
        {
            "trend.whl": make_bundle(
                timeframe="1H",
                native_instrument_ids=(),
                continuous_futures={"ES": _ES},
            ),
            "carry.whl": make_bundle(
                timeframe="1D",
                native_instrument_ids=(),
                continuous_futures={"ES": _ES},
            ),
        }
    )

    with pytest.raises(ContinuousDeclarationConflictError) as excinfo:
        assemble_book(config, registry)

    assert excinfo.value.root == "ES"
    assert excinfo.value.existing.timeframe == "1D"
    assert excinfo.value.conflicting.timeframe == "1H"


def test_assemble_book_rejects_bands_owned_by_two_sleeves() -> None:
    config = _book(("trend", "trend.whl"), ("carry", "carry.whl"))
    registry = StubBundleRegistry(
        {
            "trend.whl": make_bundle(
                native_instrument_ids=(_AAPL,),
                instrument_bands={_AAPL: DriftBand(up=0.10, down=0.20)},
            ),
            "carry.whl": make_bundle(
                native_instrument_ids=(_AAPL,),
                instrument_bands={_AAPL: DriftBand(up=0.30, down=0.40)},
            ),
        }
    )

    with pytest.raises(InstrumentBandError) as excinfo:
        assemble_book(config, registry)

    assert excinfo.value.instrument_id == _AAPL
    assert excinfo.value.sleeves == (SleeveName("carry"), SleeveName("trend"))


def test_assemble_book_rejects_undeliverable_required_arrays() -> None:
    config = _book(("merger", "merger.whl"))
    bundle = make_bundle(required_arrays=("Close", "OpenInterest", "fhfsdhf"))
    registry = StubBundleRegistry({"merger.whl": bundle})

    with pytest.raises(UndeliverableArrayError) as excinfo:
        assemble_book(config, registry)

    assert excinfo.value.sleeve == SleeveName("merger")
    assert excinfo.value.arrays == ("OpenInterest", "fhfsdhf")
    assert "OpenInterest" in str(excinfo.value)
    assert "merger" in str(excinfo.value)


def test_assemble_book_accepts_every_bar_derived_array() -> None:
    config = _book(("trend", "trend.whl"))
    bundle = make_bundle(required_arrays=("Open", "High", "Low", "Close", "Volume"))
    registry = StubBundleRegistry({"trend.whl": bundle})

    assembled = assemble_book(config, registry)

    assert assembled.sleeves == {SleeveName("trend"): bundle}


def test_assemble_book_accepts_provisioned_custom_arrays() -> None:
    config = _book(("event", "event.whl"))
    bundle = make_bundle(
        required_arrays=("Close", "FixtureValue", "FixtureAvailable")
    )
    registry = StubBundleRegistry({"event.whl": bundle})

    assembled = assemble_book(config, registry)

    assert assembled.sleeves == {SleeveName("event"): bundle}


def test_assemble_book_rejects_known_unprovisioned_arrays_distinctly() -> None:
    config = _book(("event", "event.whl"))
    bundle = make_bundle(
        required_arrays=("DormantFixtureValue", "DormantFixtureAvailable")
    )
    registry = StubBundleRegistry({"event.whl": bundle})

    with pytest.raises(UnprovisionedArrayError) as excinfo:
        assemble_book(config, registry)

    assert excinfo.value.arrays == (
        "DormantFixtureAvailable",
        "DormantFixtureValue",
    )
    assert "known" in str(excinfo.value)
    assert "provider" in str(excinfo.value)


def test_assemble_book_requires_availability_with_a_custom_value() -> None:
    config = _book(("event", "event.whl"))
    bundle = make_bundle(required_arrays=("Close", "FixtureValue"))
    registry = StubBundleRegistry({"event.whl": bundle})

    with pytest.raises(MissingAvailabilityArrayError) as excinfo:
        assemble_book(config, registry)

    assert excinfo.value.value_array == "FixtureValue"
    assert excinfo.value.availability_array == "FixtureAvailable"


def test_assemble_book_rejects_conflicting_continuous_root_declarations() -> None:
    config = _book(("trend", "trend.whl"), ("carry", "carry.whl"))
    registry = StubBundleRegistry(
        {
            "trend.whl": make_bundle(
                native_instrument_ids=(),
                continuous_futures={"ES": _ES},
                adjustment_mode=_RATIO,
            ),
            "carry.whl": make_bundle(
                native_instrument_ids=(),
                continuous_futures={"ES": _ES},
                adjustment_mode=_SPREAD,
            ),
        }
    )

    with pytest.raises(ContinuousDeclarationConflictError) as excinfo:
        assemble_book(config, registry)

    assert excinfo.value.root == "ES"
    assert excinfo.value.sleeves == (SleeveName("carry"), SleeveName("trend"))
    assert excinfo.value.existing == ContinuousRootDeclaration(
        continuous_id=_ES,
        adjustment_mode=_SPREAD,
        timeframe="1D",
    )
    assert excinfo.value.conflicting == ContinuousRootDeclaration(
        continuous_id=_ES,
        adjustment_mode=_RATIO,
        timeframe="1D",
    )


def test_identical_continuous_declarations_require_unique_band_ownership() -> None:
    config = _book(("trend", "trend.whl"), ("carry", "carry.whl"))
    registry = StubBundleRegistry(
        {
            "trend.whl": make_bundle(
                native_instrument_ids=(),
                continuous_futures={"ES": _ES},
                adjustment_mode=_RATIO,
            ),
            "carry.whl": make_bundle(
                native_instrument_ids=(),
                continuous_futures={"ES": _ES},
                adjustment_mode=_RATIO,
            ),
        }
    )

    with pytest.raises(InstrumentBandError) as excinfo:
        assemble_book(config, registry)

    assert excinfo.value.sleeves == (SleeveName("carry"), SleeveName("trend"))


def test_assemble_book_does_not_require_margin_for_long_only_sleeves() -> None:
    config = _book(("trend", "trend.whl"), ("carry", "carry.whl"))
    registry = StubBundleRegistry(
        {
            "trend.whl": make_bundle(direction="longonly"),
            "carry.whl": make_bundle(
                native_instrument_ids=(_MSFT,),
                direction="longonly",
            ),
        }
    )

    assembled = assemble_book(config, registry)

    assert assembled.requires_margin is False


def test_assembled_book_fields_are_frozen() -> None:
    config = _book(("trend", "trend.whl"))
    registry = StubBundleRegistry({"trend.whl": make_bundle()})

    assembled = assemble_book(config, registry)

    with pytest.raises(FrozenInstanceError):
        cast(Any, assembled).requires_margin = False


def test_assembled_book_sleeve_mapping_is_frozen() -> None:
    config = _book(("trend", "trend.whl"))
    registry = StubBundleRegistry({"trend.whl": make_bundle()})

    assembled = assemble_book(config, registry)

    with pytest.raises(TypeError):
        cast(Any, assembled.sleeves)[SleeveName("carry")] = make_bundle()


def test_register_book_rejects_a_different_strategy_book_config() -> None:
    assembled_config = _book(("trend", "trend.whl"))
    assembled = assemble_book(
        assembled_config,
        StubBundleRegistry({"trend.whl": make_bundle()}),
    )
    strategy = RebalanceStrategy(
        RebalanceStrategyConfig(book=_book(("trend", "other.whl")))
    )

    with pytest.raises(BookConfigMismatchError, match="configured Book Config"):
        strategy.register_book(assembled)
