"""Book Startup unit tests: gate funnel in, boot result or halt out."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone

import pandas as pd
from nautilus_trader.model.enums import ContinuousFutureAdjustmentType
from nautilus_trader.model.identifiers import InstrumentId

from aegis_runtime import (
    BundleManifest,
    ComponentSpec,
    DataContract,
    DriftBand,
    ExecutionBundle,
    LockedExecutionPlan,
    MarketDataBundle,
    MissingIndexPolicy,
)
from aegis_runtime.domain.currency import CurrencyConversion

from aegis_trader.bundles.book import ContinuousRootDeclaration
from aegis_trader.data.market_data import MarketBar
from aegis_trader.domain.book_config import BookConfig, SleeveConfig
from aegis_trader.domain.roll import Halt, RequestBars, RollIntentBatch, SubscribeBars
from aegis_trader.domain.sizing import InstrumentSizing
from aegis_trader.domain.analytics_horizon import derive_horizon
from aegis_trader.domain.sleeve_ledger import SleeveLedger
from aegis_trader.domain.startup import StartupGate
from aegis_trader.domain.types import SleeveName
from aegis_trader.trader.book_startup import (
    BootResult,
    SubscribeQuoteTicks,
    bootstrap,
)
from aegis_trader.trader.pipeline import RebalancePipeline
from aegis_trader.trader.sleeve_arrays import SleeveArrays
from tests.support.bundle_double import BundleDouble
from tests.support.factories import assemble_test_book

_NOW = datetime(2026, 6, 22, 12, 0, tzinfo=timezone.utc)
_SLEEVE = SleeveName("trend")
_INSTRUMENT_ID = InstrumentId.from_str("PIPE.XNYS")
_SECOND_INSTRUMENT_ID = InstrumentId.from_str("CARRY.XNYS")
_FRONT_LEG = InstrumentId.from_str("ESH4.XCME")
_FX_EURUSD = InstrumentId.from_str("EUR/USD.IDEALPRO")
_FX_USDJPY = InstrumentId.from_str("USD/JPY.IDEALPRO")


class _FixedWeightBundle(BundleDouble):
    def __init__(
        self,
        instrument_id: InstrumentId = _INSTRUMENT_ID,
        *,
        timeframe: str = "1D",
        lookback_bars: int = 20,
        band: DriftBand | None = None,
    ) -> None:
        self._instrument_id = instrument_id
        contract = DataContract(
            instrument_ids=(instrument_id,),
            required_arrays=("Close",),
            base_currency="EUR",
            timeframe=timeframe,
            missing_index=MissingIndexPolicy.DROP,
            lookback_bars=lookback_bars,
        )
        manifest = BundleManifest(
            run_id="book-startup-test",
            role="best",
            candidate_key="candidate",
            component_source_hashes={},
            instrument_ids=(instrument_id,),
        )
        plan = LockedExecutionPlan(
            strategy=ComponentSpec(
                family="strategy",
                component_id="fixed",
                module="tests.fixed",
                input_names=(),
                output_names=(),
                params={},
            ),
            indicators=(),
            instrument_bands={instrument_id: band or DriftBand.symmetric(0.0)},
            direction="both",
        )
        super().__init__(contract=contract, manifest=manifest, plan=plan)

    def compute_weights(
        self,
        native_prices: MarketDataBundle,
        *,
        currency_conversion: CurrencyConversion | None = None,
    ) -> pd.DataFrame:
        close = native_prices.array("Close")
        target = pd.DataFrame({self._instrument_id: [0.5, 0.5]}, index=close.index)
        target.columns.name = "instrument_id"
        return target


class _BookState:
    def __init__(
        self,
        realized_weights: dict[InstrumentId, float] | None = None,
        *,
        nav: float = 100_000.0,
        cash: float = 100_000.0,
    ) -> None:
        self._realized_weights = realized_weights or {}
        self._nav = nav
        self._cash = cash

    def nav(self) -> float:
        return self._nav

    def cash(self) -> float:
        return self._cash

    def is_cache_healthy(self) -> bool:
        return True

    def realized_weights(self) -> dict[InstrumentId, float]:
        return dict(self._realized_weights)


class _MarketData:
    def currency_pair(self, _instrument_id: InstrumentId) -> None:
        return None

    def instrument_sizing(self, _instrument_id: InstrumentId) -> InstrumentSizing:
        return InstrumentSizing(currency="EUR", size_increment=1.0)

    def make_quantity(self, _instrument_id: InstrumentId, raw_shares: float) -> float:
        return raw_shares

    def execution_instrument_id(self, instrument_id: InstrumentId) -> InstrumentId:
        return instrument_id

    def fx_rate(self, base_currency: str, quote_currency: str) -> float | None:
        if base_currency == quote_currency:
            return 1.0
        return None

    def lookback_window(
        self,
        _instrument_id: InstrumentId,
        _timeframe: str,
        *,
        period: int,
        period_ns: int,
        limit: int,
    ) -> tuple[MarketBar, ...]:
        _ = (period, period_ns, limit)
        return ()

    def has_bar_in_period(
        self,
        _instrument_id: InstrumentId,
        _timeframe: str,
        *,
        period: int,
        period_ns: int,
    ) -> bool:
        _ = (period, period_ns)
        return True


class _RollDesk:
    def __init__(self, intents: RollIntentBatch = ()) -> None:
        self.intents = intents
        self.calls: list[dict[str, object]] = []

    def start(
        self,
        *,
        end: datetime,
        warmup: bool,
        declarations: Mapping[str, ContinuousRootDeclaration],
        history_starts: Mapping[str, datetime],
    ) -> RollIntentBatch:
        self.calls.append(
            {
                "end": end,
                "warmup": warmup,
                "declarations": dict(declarations),
                "history_starts": dict(history_starts),
            }
        )
        return self.intents


def _book(*, per_name_cap: float | None = None) -> BookConfig:
    return BookConfig(
        sleeves=(
            SleeveConfig(name=_SLEEVE, wheel_filename="trend.whl", risk_share=1.0),
        ),
        base_currency="EUR",
        per_name_cap=per_name_cap,
    )


def _bootstrap(
    *,
    book: BookConfig | None = None,
    bundles: dict[SleeveName, ExecutionBundle] | None = None,
    book_state: _BookState | None = None,
    roll_desk: _RollDesk | None = None,
    fx_reference_pairs: tuple[InstrumentId, ...] = (),
    warmup_cache_on_start: bool = True,
) -> BootResult | Halt:
    config = book or _book()
    loaded = bundles or {_SLEEVE: _FixedWeightBundle()}
    assembled = assemble_test_book(
        config,
        {sleeve.wheel_filename: loaded[sleeve.name] for sleeve in config.sleeves},
    )
    pipeline = RebalancePipeline(
        book_state=book_state or _BookState(),
        market_data=_MarketData(),
        book=assembled,
        ledger=SleeveLedger(horizon=derive_horizon(("1D",))),
        arrays=SleeveArrays.bar_only(),
    )
    return bootstrap(
        now=_NOW,
        book=assembled,
        pipeline=pipeline,
        roll_desk=roll_desk or _RollDesk(),
        fx_reference_pairs=fx_reference_pairs,
        warmup_cache_on_start=warmup_cache_on_start,
    )


class _FuturesBundle(_FixedWeightBundle):
    """A futures sleeve declaring one continuous root with its recorded mode."""

    def __init__(
        self,
        continuous_id: InstrumentId,
        *,
        root: str = "ES",
        adjustment_mode: ContinuousFutureAdjustmentType = (
            ContinuousFutureAdjustmentType.BACKWARD_RATIO
        ),
    ) -> None:
        contract = DataContract(
            instrument_ids=(continuous_id,),
            required_arrays=("Close",),
            base_currency="EUR",
            timeframe="1D",
            missing_index=MissingIndexPolicy.DROP,
            lookback_bars=20,
            futures=(root,),
            adjustment_mode=adjustment_mode,
        )
        manifest = BundleManifest(
            run_id="book-startup-test",
            role="best",
            candidate_key="candidate",
            component_source_hashes={},
            instrument_ids=(continuous_id,),
        )
        plan = LockedExecutionPlan(
            strategy=ComponentSpec(
                family="strategy",
                component_id="fixed",
                module="tests.fixed",
                input_names=(),
                output_names=(),
                params={},
            ),
            indicators=(),
            instrument_bands={continuous_id: DriftBand.symmetric(0.0)},
            direction="both",
        )
        BundleDouble.__init__(self, contract=contract, manifest=manifest, plan=plan)


def test_bootstrap_passes_coherent_declarations_to_roll_desk() -> None:
    roll_desk = _RollDesk()
    es = InstrumentId.from_str("ES.XCME")

    result = _bootstrap(
        bundles={_SLEEVE: _FuturesBundle(es)},
        roll_desk=roll_desk,
    )

    assert isinstance(result, BootResult)
    assert roll_desk.calls[0]["declarations"] == {
        "ES": ContinuousRootDeclaration(
            continuous_id=es,
            adjustment_mode=ContinuousFutureAdjustmentType.BACKWARD_RATIO,
            timeframe="1D",
        )
    }
    assert roll_desk.calls[0]["history_starts"] == {
        "ES": datetime(2026, 4, 20, 12, 0, tzinfo=timezone.utc)
    }


def test_bootstrap_resolves_an_empty_declaration_mapping_for_etf_books() -> None:
    roll_desk = _RollDesk()

    result = _bootstrap(roll_desk=roll_desk)

    assert isinstance(result, BootResult)
    assert roll_desk.calls[0]["declarations"] == {}


def test_bootstrap_halts_on_account_integrity_before_starting_roll_desk() -> None:
    roll_desk = _RollDesk()

    result = _bootstrap(
        book_state=_BookState(nav=100_000.0, cash=90_000.0),
        roll_desk=roll_desk,
    )

    assert result == Halt(
        StartupGate.ACCOUNT_INTEGRITY,
        "NAV/cash mismatch: NAV=100000.00, cash=90000.00, "
        "gap=10000.00 exceeds tolerance 0.00 (fraction=0.0)",
    )
    assert roll_desk.calls == []


def test_bootstrap_returns_roll_halt_without_subscription_intents() -> None:
    roll_desk = _RollDesk(
        (Halt(StartupGate.CONTINUOUS_IDENTITY, "continuous venue drift"),)
    )

    result = _bootstrap(roll_desk=roll_desk, fx_reference_pairs=(_FX_EURUSD,))

    assert result == Halt(
        StartupGate.CONTINUOUS_IDENTITY,
        "continuous venue drift",
    )
    assert roll_desk.calls[0]["history_starts"] == {}


def test_bootstrap_warms_each_stream_from_its_own_sleeve_lookback() -> None:
    deep = SleeveName("deep")
    shallow = SleeveName("shallow")
    book = BookConfig(
        sleeves=(
            SleeveConfig(name=deep, wheel_filename="deep.whl", risk_share=1.0),
            SleeveConfig(name=shallow, wheel_filename="shallow.whl", risk_share=1.0),
        ),
        base_currency="EUR",
    )

    result = _bootstrap(
        book=book,
        bundles={
            deep: _FixedWeightBundle(_INSTRUMENT_ID, lookback_bars=40),
            shallow: _FixedWeightBundle(_SECOND_INSTRUMENT_ID, lookback_bars=20),
        },
        warmup_cache_on_start=True,
    )

    assert isinstance(result, BootResult)
    requests = [intent for intent in result.intents if isinstance(intent, RequestBars)]
    assert requests == [
        RequestBars(
            _SECOND_INSTRUMENT_ID,
            "1D",
            datetime(2026, 4, 20, 12, 0, tzinfo=timezone.utc),
            _NOW,
        ),
        RequestBars(
            _INSTRUMENT_ID,
            "1D",
            datetime(2026, 2, 19, 12, 0, tzinfo=timezone.utc),
            _NOW,
        ),
    ]


def test_bootstrap_warms_an_intraday_stream_with_the_session_aware_multiplier() -> None:
    result = _bootstrap(
        bundles={_SLEEVE: _FixedWeightBundle(timeframe="1H", lookback_bars=20)},
        warmup_cache_on_start=True,
    )

    assert isinstance(result, BootResult)
    requests = [intent for intent in result.intents if isinstance(intent, RequestBars)]
    assert requests == [
        RequestBars(
            _INSTRUMENT_ID,
            "1H",
            datetime(2026, 6, 17, 6, 0, tzinfo=timezone.utc),
            _NOW,
        ),
    ]


def test_bootstrap_pass_returns_pipeline_startup_result_and_intent_batch() -> None:
    roll_desk = _RollDesk((SubscribeBars(_FRONT_LEG, "1D"),))

    result = _bootstrap(
        roll_desk=roll_desk,
        fx_reference_pairs=(_FX_USDJPY, _FX_EURUSD),
        warmup_cache_on_start=True,
    )

    assert isinstance(result, BootResult)
    assert result.startup_result.trading_enabled is True
    assert result.startup_result.nav == 100_000.0
    assert result.startup_result.cash == 100_000.0
    assert result.intents == (
        SubscribeBars(_FRONT_LEG, "1D"),
        SubscribeBars(_INSTRUMENT_ID, "1D"),
        RequestBars(
            _INSTRUMENT_ID,
            "1D",
            datetime(2026, 4, 20, 12, 0, tzinfo=timezone.utc),
            _NOW,
        ),
        SubscribeQuoteTicks(_FX_EURUSD),
        SubscribeQuoteTicks(_FX_USDJPY),
    )
