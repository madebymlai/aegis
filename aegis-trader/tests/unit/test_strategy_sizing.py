from __future__ import annotations

from aegis_runtime import (
    BundleManifest,
    ComponentSpec,
    DataContract,
    DriftBand,
    ExecutionBundle,
    LockedExecutionPlan,
    MissingIndexPolicy,
)
from nautilus_trader.model.identifiers import InstrumentId

from aegis_trader.data import MarketBar
from aegis_trader.domain.book_config import BookConfig, SleeveConfig
from aegis_trader.domain.sizing import InstrumentSizing
from aegis_trader.domain.sleeve_ledger import SleeveLedger
from aegis_trader.domain.types import SleeveName
from aegis_trader.trader.pipeline import (
    CompletedRebalancePeriod,
    DueSleeve,
    RebalancePipeline,
    RebalanceRequest,
)
from tests.support.factories import assemble_test_book

_INSTRUMENT_ID = InstrumentId.from_str("GBUS.XLON")


class _MarketData:
    def currency_pair(self, _instrument_id: InstrumentId) -> None:
        return None

    def instrument_sizing(self, instrument_id: InstrumentId) -> InstrumentSizing | None:
        assert instrument_id == _INSTRUMENT_ID
        return InstrumentSizing(currency="GBp", size_increment=1.0)

    def make_quantity(self, instrument_id: InstrumentId, raw_shares: float) -> object:
        raise AssertionError("quantity construction is not part of this test")

    def execution_instrument_id(self, instrument_id: InstrumentId) -> InstrumentId:
        return instrument_id

    def fx_rate(self, base_currency: str, quote_currency: str) -> float | None:
        assert (base_currency, quote_currency) == ("EUR", "GBp")
        return 0.85

    def lookback_window(
        self,
        instrument_id: InstrumentId,
        timeframe: str,
        *,
        period: int,
        period_ns: int,
        limit: int,
    ) -> tuple[MarketBar, ...]:
        assert (instrument_id, timeframe) == (_INSTRUMENT_ID, "1D")
        assert (period, period_ns, limit) == (1, 86_400_000_000_000, 1)
        return (
            MarketBar(
                ts_event=86_400_000_000_000,
                open=850.0,
                high=850.0,
                low=850.0,
                close=850.0,
                volume=1.0,
            ),
        )

    def has_bar_in_period(
        self,
        instrument_id: InstrumentId,
        timeframe: str,
        *,
        period: int,
        period_ns: int,
    ) -> bool:
        raise AssertionError("freshness is not part of this test")


class _BookState:
    def nav(self) -> float:
        return 100_000.0

    def cash(self) -> float:
        return 100_000.0

    def is_cache_healthy(self) -> bool:
        return True

    def realized_weights(self) -> dict[InstrumentId, float]:
        return {}


class _PenceBundle(ExecutionBundle):
    def __init__(self) -> None:
        contract = DataContract(
            instrument_ids=(_INSTRUMENT_ID,),
            required_arrays=("Close",),
            base_currency="EUR",
            timeframe="1D",
            missing_index=MissingIndexPolicy.DROP,
            lookback_bars=1,
        )
        manifest = BundleManifest(
            run_id="pence-001",
            role="synth",
            candidate_key="k",
            component_source_hashes={},
            instrument_ids=(_INSTRUMENT_ID,),
        )
        plan = LockedExecutionPlan(
            strategy=ComponentSpec(
                family="strategy",
                component_id="s",
                module="m",
                input_names=(),
                output_names=(),
                params={},
            ),
            indicators=(),
            instrument_bands={_INSTRUMENT_ID: DriftBand.symmetric(0.0)},
            gross_cap=1.0,
            net_cap=None,
            direction="both",
        )
        super().__init__(contract=contract, manifest=manifest, plan=plan)


def test_pipeline_collects_sizing_params_by_native_instrument_id() -> None:
    book = BookConfig(
        sleeves=(
            SleeveConfig(
                name=SleeveName("uk"),
                wheel_filename="uk.whl",
                risk_share=1.0,
            ),
        ),
        base_currency="EUR",
    )
    bundle = _PenceBundle()
    pipeline = RebalancePipeline(
        book_state=_BookState(),
        market_data=_MarketData(),
        book=assemble_test_book(book, {"uk.whl": bundle}),
        ledger=SleeveLedger(),
    )

    pipeline.rebalance(
        RebalanceRequest(
            due=(
                DueSleeve(
                    sleeve=SleeveName("uk"),
                    period=CompletedRebalancePeriod(
                        period=1, period_ns=86_400_000_000_000
                    ),
                ),
            )
        )
    )
    instrument_metas, fx_rates, prices = pipeline._collect_sizing_params()

    assert instrument_metas == {
        _INSTRUMENT_ID: InstrumentSizing(currency="GBp", size_increment=1.0)
    }
    assert fx_rates == {"GBp": 0.85}
    assert prices == {_INSTRUMENT_ID: 850.0}
