from __future__ import annotations

from aegis_runtime import (
    BundleManifest,
    ComponentSpec,
    DataContract,
    ExecutionBundle,
    ListedRef,
    LockedExecutionPlan,
    MarketDataBundle,
)
from nautilus_trader.model.identifiers import InstrumentId

from aegis_trader.domain.book_config import BookConfig, SleeveConfig
from aegis_trader.domain.sizing import InstrumentSizing
from aegis_trader.domain.types import SleeveName
from aegis_trader.trader.strategy import RebalanceStrategy, RebalanceStrategyConfig

_FIGI = "BBG000R20GS9"
_REF = ListedRef(_FIGI)
_INSTRUMENT_ID = InstrumentId.from_str("GBUS.XLON")


class _MarketData:
    def instrument_sizing(self, instrument_id: InstrumentId) -> InstrumentSizing | None:
        assert instrument_id == _INSTRUMENT_ID
        return InstrumentSizing(currency="GBP", size_increment=1.0)

    def make_quantity(self, instrument_id: InstrumentId, raw_shares: float) -> object:
        raise AssertionError("quantity construction is not part of this test")

    def fx_rate(self, base_currency: str, quote_currency: str) -> float | None:
        assert (base_currency, quote_currency) == ("EUR", "GBP")
        return 0.85


class _PenceBundle(ExecutionBundle):
    def __init__(self) -> None:
        contract = DataContract(
            refs=(_REF,),
            required_arrays=("Close",),
            base_currency="EUR",
            required_fx_currencies=(),
            timeframe="1D",
            lookback_bars=1,
        )
        manifest = BundleManifest(
            run_id="pence-001",
            role="synth",
            candidate_key="k",
            component_source_hashes={},
            refs=(_REF,),
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
            gross_cap=1.0,
            net_cap=None,
            direction="both",
            symbols=("GBUS.L",),
            currency_by_symbol={"GBUS.L": "GBp"},
        )
        super().__init__(contract=contract, manifest=manifest, plan=plan)

    def compute_weights(self, prices: MarketDataBundle, *, fx_series=None) -> object:
        raise AssertionError("weight computation is not part of this test")


def test_strategy_sizing_uses_declared_pence_currency_with_major_fx_rate():
    book = BookConfig(
        sleeves=(SleeveConfig(name=SleeveName("uk"), wheel_filename="uk.whl", risk_share=1.0),),
        base_currency="EUR",
    )
    strategy = RebalanceStrategy(config=RebalanceStrategyConfig(book=book))
    strategy.register_sleeve(book.sleeves[0].name, _PenceBundle())
    strategy._figi_bimap = {_REF: _INSTRUMENT_ID}
    strategy._market_data = _MarketData()

    instrument_metas, fx_rates, prices = strategy._collect_sizing_params()

    assert instrument_metas == {_REF: InstrumentSizing(currency="GBp", size_increment=1.0)}
    assert fx_rates == {"GBp": 0.85}
    assert prices == {}
