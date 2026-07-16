"""Pipeline-seam harness for rebalance behavior tests.

Stages weight-space scenarios through ``RebalancePipeline.rebalance``
and reads them back in production observables (orders, halt reason, gate
outcome, summary, applied sleeve weights).

Identity-sizing convention: every bar closes at 1.0 and NAV is 1,000,000, so a
weight delta ``w`` sizes to a quantity of ``round(w * 1_000_000)`` — weights
read back exactly as micro-NAV order quantities.

Band ownership note: book assembly requires each instrument's drift band to be
declared by exactly one sleeve, and a bundle's plan must band exactly its
contract's instruments — sleeves therefore never share an instrument.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

import pandas as pd
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
from aegis_runtime.currency import CurrencyConversion

from aegis_trader.data.market_data import MarketBar
from aegis_trader.domain.book_config import BookConfig, SleeveConfig
from aegis_trader.domain.sizing import InstrumentSizing
from aegis_trader.domain.sleeve_ledger import (
    MIN_SLEEVE_VOL_RETURNS,
    SleeveLedger,
)
from aegis_trader.domain.types import OrderSide, SleeveName
from aegis_trader.trader.pipeline import (
    CompletedRebalancePeriod,
    DueSleeve,
    RebalancePipeline,
    RebalanceRequest,
    RebalanceResult,
)
from tests.support.factories import assemble_test_book

NAV = 1_000_000.0
_DAY_NS = 86_400_000_000_000


def iid(symbol: str) -> InstrumentId:
    return InstrumentId.from_str(f"{symbol}.TEST")


@dataclass(frozen=True)
class SleeveSpec:
    """One sleeve of a staged book: its targets and the bands it owns.

    ``targets`` maps symbol -> latest target weight; ``rows`` optionally stages
    earlier target rows before it.  ``bands`` defaults to a zero-width band per
    owned symbol (trade straight to target).  ``stale`` starves the sleeve of
    bars so it holds.
    """

    name: str
    risk_share: float
    targets: Mapping[str, float]
    rows: Sequence[Mapping[str, float]] = ()
    bands: Mapping[str, DriftBand] | None = None
    weight_band: float = 0.0
    stale: bool = False

    @property
    def sleeve_name(self) -> SleeveName:
        return SleeveName(self.name)

    @property
    def wheel_filename(self) -> str:
        return f"{self.name}.whl"


class WeightSleeveBundle(ExecutionBundle):
    """A sleeve bundle that emits the spec's target weights verbatim."""

    def __init__(self, spec: SleeveSpec) -> None:
        symbols = tuple(spec.targets)
        instrument_ids = tuple(iid(symbol) for symbol in symbols)
        bands = {
            iid(symbol): (
                spec.bands[symbol]
                if spec.bands is not None and symbol in spec.bands
                else DriftBand.symmetric(0.0)
            )
            for symbol in symbols
        }
        self._rows = (*spec.rows, spec.targets)
        contract = DataContract(
            instrument_ids=instrument_ids,
            required_arrays=("Close",),
            base_currency="EUR",
            timeframe="1D",
            missing_index=MissingIndexPolicy.DROP,
            lookback_bars=1,
        )
        manifest = BundleManifest(
            run_id="rebalance-harness",
            role="best",
            candidate_key="candidate",
            component_source_hashes={},
            instrument_ids=instrument_ids,
        )
        plan = LockedExecutionPlan(
            strategy=ComponentSpec(
                family="strategy",
                component_id="staged-weights",
                module="tests.staged_weights",
                input_names=(),
                output_names=(),
                params={},
            ),
            indicators=(),
            instrument_bands=bands,
            gross_cap=1.0,
            net_cap=None,
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
        rows = self._rows[-len(close.index):]
        padded = (*(rows[0],) * (len(close.index) - len(rows)), *rows)
        target = pd.DataFrame(
            [
                {iid(symbol): weight for symbol, weight in row.items()}
                for row in padded
            ],
            index=close.index,
        )
        target.columns.name = "instrument_id"
        return target


class _BookState:
    def __init__(self, realized_weights: dict[InstrumentId, float]) -> None:
        self._realized_weights = realized_weights

    def nav(self) -> float:
        return NAV

    def cash(self) -> float:
        return NAV

    def is_cache_healthy(self) -> bool:
        return True

    def realized_weights(self) -> dict[InstrumentId, float]:
        return dict(self._realized_weights)


class _UnitPriceMarketData:
    """Every staged instrument: two fresh daily bars closing at 1.0, EUR-quoted."""

    def __init__(self, instrument_ids: frozenset[InstrumentId]) -> None:
        self._instrument_ids = instrument_ids
        self._bars = (
            MarketBar(0, 1.0, 1.0, 1.0, 1.0, 1_000.0),
            MarketBar(_DAY_NS, 1.0, 1.0, 1.0, 1.0, 1_000.0),
        )

    def instrument_sizing(self, instrument_id: InstrumentId) -> InstrumentSizing:
        return InstrumentSizing(currency="EUR", size_increment=1.0)

    def make_quantity(self, _instrument_id: InstrumentId, raw_shares: float) -> float:
        return raw_shares

    def execution_instrument_id(self, instrument_id: InstrumentId) -> InstrumentId:
        return instrument_id

    def currency_pair(self, instrument_id: InstrumentId) -> tuple[str, str] | None:
        return None

    def fx_rate(self, base_currency: str, quote_currency: str) -> float | None:
        return 1.0

    def lookback_window(
        self,
        instrument_id: InstrumentId,
        _timeframe: str,
        *,
        period: int,
        period_ns: int,
        limit: int,
    ) -> tuple[MarketBar, ...]:
        _ = (period, period_ns)
        if instrument_id not in self._instrument_ids:
            return ()
        return self._bars[-limit:]

    def has_bar_in_period(
        self,
        instrument_id: InstrumentId,
        _timeframe: str,
        *,
        period: int,
        period_ns: int,
    ) -> bool:
        _ = (period, period_ns)
        return instrument_id in self._instrument_ids


class StagedLedger(SleeveLedger):
    """A ledger answering staged covariance (one entry per period) and drawdown."""

    def __init__(
        self,
        *,
        covariances: Sequence[dict[SleeveName, dict[SleeveName, float]] | None] | None = None,
        drawdown: float | None = None,
    ) -> None:
        super().__init__()
        self._covariances = None if covariances is None else list(covariances)
        self._drawdown = drawdown

    def realized_covariance(
        self,
        names: Sequence[SleeveName],
        *,
        min_returns: int = MIN_SLEEVE_VOL_RETURNS,
    ) -> dict[SleeveName, dict[SleeveName, float]] | None:
        if self._covariances is None:
            return None
        return self._covariances.pop(0)

    def current_drawdown(self, current_nav: float) -> float:
        if self._drawdown is None:
            return super().current_drawdown(current_nav)
        return self._drawdown


@dataclass
class RebalanceHarness:
    """One staged book behind its pipeline; each ``run`` is one completed period.

    ``due`` names the Sleeves whose period completed this run; every Sleeve is
    due when omitted (the single-timeframe driving of the current Strategy).
    """

    pipeline: RebalancePipeline
    sleeve_names: tuple[SleeveName, ...]
    _period: int = field(default=0, init=False)

    def run(self, due: Sequence[str] | None = None) -> RebalanceResult:
        self._period += 1
        period = CompletedRebalancePeriod(
            period=self._period, period_ns=self._period * _DAY_NS
        )
        due_names = (
            self.sleeve_names
            if due is None
            else tuple(SleeveName(name) for name in due)
        )
        return self.pipeline.rebalance(
            RebalanceRequest(
                due=tuple(DueSleeve(sleeve=name, period=period) for name in due_names)
            )
        )


def build_harness(
    sleeves: Sequence[SleeveSpec],
    *,
    realized: Mapping[str, float] | None = None,
    ledger: SleeveLedger | None = None,
    bundle_overrides: Mapping[str, ExecutionBundle] | None = None,
    **book_kwargs: object,
) -> RebalanceHarness:
    """Assemble a staged book through its real assembly path.

    ``bundle_overrides`` swaps a spec's default ``WeightSleeveBundle`` by wheel
    filename — for staging compute failures and other bundle behaviors.
    """
    book = BookConfig(
        sleeves=tuple(
            SleeveConfig(
                name=spec.sleeve_name,
                wheel_filename=spec.wheel_filename,
                risk_share=spec.risk_share,
                weight_band_down=spec.weight_band,
                weight_band_up=spec.weight_band,
            )
            for spec in sleeves
        ),
        base_currency="EUR",
        **book_kwargs,  # type: ignore[arg-type]
    )
    bundles: dict[str, ExecutionBundle] = {
        spec.wheel_filename: WeightSleeveBundle(spec) for spec in sleeves
    }
    bundles.update(bundle_overrides or {})
    staged_ids = frozenset(
        iid(symbol) for spec in sleeves if not spec.stale for symbol in spec.targets
    ) | frozenset(iid(symbol) for symbol in (realized or {}))
    pipeline = RebalancePipeline(
        book_state=_BookState({iid(symbol): weight for symbol, weight in (realized or {}).items()}),
        market_data=_UnitPriceMarketData(staged_ids),
        book=assemble_test_book(book, bundles),
        ledger=ledger if ledger is not None else SleeveLedger(),
    )
    return RebalanceHarness(
        pipeline,
        sleeve_names=tuple(spec.sleeve_name for spec in sleeves),
    )


def signed_order_weights(result: RebalanceResult) -> dict[str, float]:
    """Each order read back as a signed weight of NAV, keyed by symbol."""
    return {
        order.instrument_id.symbol.value: (
            order.quantity if order.side is OrderSide.BUY else -order.quantity
        )
        / NAV
        for order in result.orders
    }
