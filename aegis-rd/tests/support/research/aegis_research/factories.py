"""Test-construction factories for Run Config dataclasses.

Each factory supplies valid defaults for every field and accepts **overrides.
Routing construction through factories means porting one helper instead of N call
sites when section defaults change (e.g. when the unit-gross sleeve contract
dropped gross_cap/net_cap from the schema, aegis-rd-ui1m).

These are test-support only — no production code changes.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pandas as pd
from aegis_data.distributions import Distribution
from aegis_runtime import DriftBand, InstrumentId, MarketDataBundle
from aegis_runtime.currency import CurrencyConversion
from vectorbtpro import vbt

from research.aegis_research.component_registry.contracts import (
    SYMBOL_LEVEL,
    ComponentDefinition,
    ComponentFamily,
    ComponentSourceIdentity,
    IndicatorManifest,
    StrategyManifest,
)
from research.aegis_research.component_registry.registry import (
    FrozenComponentRegistry,
    freeze_component_registry,
)
from research.aegis_research.configuration import (
    CONFIG_SCHEMA_VERSION,
    DataConfig,
    DataQualityConfig,
    Lock,
    OptimizationConfig,
    PortfolioConfig,
    RankingConfig,
    ReportConfig,
    RunConfig,
    RunIndicatorSourceConfig,
    RunSourceRefConfig,
    SignalConfig,
)
from research.aegis_research.market_data.run_arrays import RunArrays
from research.aegis_research.optimization.continuous_evidence import (
    CONTINUOUS_SELECTION_IDENTITY_SCHEMA_VERSION,
    METRIC_EXTRACTOR_PROTOCOL_SCHEMA_VERSION,
)
from research.aegis_research.optimization.continuous_replay import (
    continuous_replay_protocol,
)
from research.aegis_research.optimization.observation_blocks import (
    ObservationBlocks,
    observation_block_protocol,
)
from research.aegis_research.optimization.pipeline.setup import SetupResult
from research.aegis_research.optimization.run_data_contract import (
    DataArrayContract,
    RunDataFacts,
)
from research.aegis_research.optimization.window_evaluation import ResolvedBook
from research.aegis_research.optimization.window_evaluation._simulation import (
    _build_portfolio,
    expand_market_frame_to_candidate_columns,
    simulate_portfolio_batch,
)
from tests.support.research.aegis_research.test_doubles import FakeDataResult


def make_data_quality_config(**overrides: Any) -> DataQualityConfig:
    """Return a DataQualityConfig with valid defaults, overridden by any kwargs."""
    defaults: dict[str, Any] = {
        "allowed_degradations": [],
    }
    defaults.update(overrides)
    return DataQualityConfig(**defaults)


def make_data_config(**overrides: Any) -> DataConfig:
    """Return a DataConfig with valid defaults, overridden by any kwargs.

    ``arrays`` is field-required on the pydantic DataConfig; the factory
    supplies it as a kwarg just like every other field.
    """
    defaults: dict[str, Any] = {
        "arrays": ["OHLCV"],
        "base_currency": "EUR",
        "instruments": ["SYN.XNAS"],
        "exchange": [],
        "futures": [],
        "start": "2024-01-01",
        "end": "2024-01-03",
        "timeframe": "1D",
        "path": None,
        "missing_index": "raise",
        "quality": make_data_quality_config(),
    }
    defaults.update(overrides)
    return DataConfig(**defaults)


def make_signal_config(**overrides: Any) -> SignalConfig:
    """Return a SignalConfig with valid defaults, overridden by any kwargs."""
    defaults: dict[str, Any] = {
        "policy": "long_only_hysteresis",
        "long_entry_threshold": 0.55,
        "long_exit_threshold": 0.50,
        "execution_timing": "next_open",
    }
    defaults.update(overrides)
    return SignalConfig(**defaults)


def make_portfolio_config(**overrides: Any) -> PortfolioConfig:
    """Return a PortfolioConfig with valid defaults, overridden by any kwargs."""
    defaults: dict[str, Any] = {
        "init_cash": 10_000.0,
        "fees": 0.001,
        "slippage": 0.0005,
        "direction": "longonly",
        "short_borrow_rate": 0.005,
        "short_rebate_rate": 0.0,
        "margin_interest_rate": 0.0367,
        # Mechanics tests assert exact same-bar order dates/prices; pin same_close so they
        # stay shift-free. Production PortfolioConfig defaults to next_close; tests that
        # exercise realistic fills set fill_timing explicitly.
        "fill_timing": "same_close",
    }
    defaults.update(overrides)
    return PortfolioConfig(**defaults)


def make_report_config(**overrides: Any) -> ReportConfig:
    """Return a ReportConfig with valid defaults, overridden by any kwargs."""
    defaults: dict[str, Any] = {
        "min_oos_sharpe": 0.5,
        "max_oos_drawdown": 0.35,
        "min_oos_trades": 5,
        "freq": "1D",
        "year_freq": "252D",
    }
    defaults.update(overrides)
    return ReportConfig(**defaults)


def make_run_source_ref_config(**overrides: Any) -> RunSourceRefConfig:
    """Return a RunSourceRefConfig with valid defaults, overridden by any kwargs."""
    defaults: dict[str, Any] = {
        "id": "demo.strategy",
        "params": {},
    }
    defaults.update(overrides)
    return RunSourceRefConfig(**defaults)


def make_run_indicator_source_config(**overrides: Any) -> RunIndicatorSourceConfig:
    """Return a RunIndicatorSourceConfig with valid defaults, overridden by any kwargs."""
    defaults: dict[str, Any] = {
        "id": "demo.indicator",
        "params": {},
    }
    defaults.update(overrides)
    return RunIndicatorSourceConfig(**defaults)


def make_ranking_config(**overrides: Any) -> RankingConfig:
    """Return a RankingConfig with valid defaults, overridden by any kwargs."""
    defaults: dict[str, Any] = {
        "metric": "total_return",
        "min_trades": 0,
    }
    defaults.update(overrides)
    return RankingConfig(**defaults)


def make_optimization_config(**overrides: Any) -> OptimizationConfig:
    """Return an OptimizationConfig with valid defaults, overridden by any kwargs."""
    defaults: dict[str, Any] = {
        "search": "grid",
        "observation_block_bars": 20,
        "random_subset": None,
        "seed": None,
        "execute": {},
    }
    defaults.update(overrides)
    return OptimizationConfig(**defaults)


def make_selection_identity(**overrides: Any) -> dict[str, Any]:
    """Return a structurally current continuous-selection identity for tests."""
    blocks = ObservationBlocks.from_bounds(
        pd.RangeIndex(20), ((0, 10), (10, 20))
    )
    defaults: dict[str, Any] = {
        "schema_version": CONTINUOUS_SELECTION_IDENTITY_SCHEMA_VERSION,
        "trial_lineage": {
            "search": "grid",
            "random_subset": None,
            "seed": None,
            "candidate_grid": [{"position": 0, "params": {}}],
        },
        "warmup": {"resolved_warmup_bars": 0, "scored_start": 0},
        "scored_interval": {"start": 0, "end": 20, "end_exclusive": True},
        "replay_protocol": continuous_replay_protocol(
            fill_timing="next_close",
            direction="longonly",
            scored_start=0,
            sim_end=20,
        ),
        "observation_block_protocol": observation_block_protocol(blocks),
        "metric_protocol": {
            "schema_version": METRIC_EXTRACTOR_PROTOCOL_SCHEMA_VERSION,
            "registry_fingerprint": "0" * 64,
            "candidate_vector_contract": "non_scalar_canonical_candidate_series.v1",
            "extractors": {
                "total_return": {
                    "kind": "native_full_portfolio",
                    "source_type": "vbt_stats",
                    "boundary_semantics": "native_continuous",
                    "scale": "percent",
                    "absolute": False,
                }
            },
        },
        "metric_inputs": {
            "freq": "1D",
            "year_freq": "252D",
            "periods_per_year": 252,
        },
        "ranking": {
            "metric": "total_return",
            "direction": "maximize",
            "min_trades": 0,
            "score": "mean_within_observation_block_rank",
            "tie_method": "average",
            "equal_score_tie_break": "materialized_candidate_position",
        },
    }
    defaults.update(overrides)
    return defaults


def make_lock(**overrides: Any) -> Lock:
    """Return a Lock with valid defaults, overridden by any kwargs."""
    defaults: dict[str, Any] = {
        "run_id": "run-a",
        "candidate_id": "best",
    }
    defaults.update(overrides)
    return Lock(**defaults)


def make_run_config(**overrides: Any) -> RunConfig:
    """Return a RunConfig with valid defaults, overridden by any kwargs.

    Nested section factories supply defaults for every section; callers pass
    ready-made instances for the sections they need to differ
    (e.g. ``portfolio=make_portfolio_config(fees=0)``).
    """
    defaults: dict[str, Any] = {
        "name": "test-run",
        "strategy": make_run_source_ref_config(),
        "indicators": [make_run_indicator_source_config()],
        "ranking": make_ranking_config(),
        "schema_version": CONFIG_SCHEMA_VERSION,
        "data": make_data_config(),
        "portfolio": make_portfolio_config(),
        "report": make_report_config(),
        "optimization": None,
        "lock": None,
        "output_dir": "runs",
    }
    defaults.update(overrides)
    return RunConfig(**defaults)


def make_component_registry(
    definitions: Mapping[
        ComponentFamily,
        Mapping[str, ComponentDefinition],
    ],
) -> FrozenComponentRegistry:
    """Build a FrozenComponentRegistry in memory — no tmp dirs, no file writing.

    Accepts fully-constructed ``ComponentDefinition`` objects keyed by family
    and id; families may be omitted.  Delegates to
    ``freeze_component_registry`` so the factory stops re-deriving the freeze
    loop and fingerprint recipe.
    """
    return freeze_component_registry(definitions)


def make_indicator_component_definition(
    *,
    id: str = "demo.indicator",
    version: str = "1.0.0",
    input_names: tuple[str, ...] = ("Close",),
    param_names: tuple[str, ...] = (),
    output_names: tuple[str, ...] = ("value",),
    defaults: Mapping[str, Any] | None = None,
    has_param_space: bool = False,
    has_lookback: bool = False,
) -> ComponentDefinition:
    return ComponentDefinition(
        _manifest=IndicatorManifest(
            family="indicators",
            id=id,
            version=version,
            input_names=input_names,
            param_names=param_names,
            output_names=output_names,
            defaults=dict(defaults or {}),
        ),
        _file_path=Path(f"/fixtures/{id}.py"),
        identity=_component_source_identity(id),
        _has_param_space=has_param_space,
        has_lookback=has_lookback,
    )


def make_strategy_component_definition(
    *,
    id: str = "demo.strategy",
    version: str = "1.0.0",
    input_names: tuple[str, ...] = ("Close",),
    param_names: tuple[str, ...] = (),
    output_name: str = "active",
    consumes_outputs: tuple[str, ...] = (),
    defaults: Mapping[str, Any] | None = None,
    has_param_space: bool = False,
    has_lookback: bool = False,
) -> ComponentDefinition:
    return ComponentDefinition(
        _manifest=StrategyManifest(
            family="strategies",
            id=id,
            version=version,
            input_names=input_names,
            param_names=param_names,
            output_name=output_name,
            consumes_outputs=consumes_outputs,
            defaults=dict(defaults or {}),
        ),
        _file_path=Path(f"/fixtures/{id}.py"),
        identity=_component_source_identity(id),
        _has_param_space=has_param_space,
        has_lookback=has_lookback,
    )


def _component_source_identity(component_id: str) -> ComponentSourceIdentity:
    return ComponentSourceIdentity(
        repo_relative_path=f"tests/fixtures/{component_id}.py",
        source_hash="0" * 64,
    )


def make_run_arrays(**overrides: Any) -> RunArrays:
    """Return a RunArrays with valid defaults, overridden by any kwargs.

    Defaults are a coherent single-series shape: the P&L frames are the signal
    Close/Open objects themselves, mirroring what ``prepare_run_arrays``
    produces when no P&L series is declared.
    """
    close = overrides.pop("close", pd.DataFrame({0: [1.0, 2.0]}))
    open_ = overrides.pop("open_", pd.DataFrame({0: [1.0, 2.0]}))
    defaults: dict[str, Any] = {
        "signal": MarketDataBundle({"Close": close, "Open": open_}),
        "pnl_close": close,
        "pnl_open": open_,
        "currency_conversion": None,
        "distributions": (),
    }
    defaults.update(overrides)
    return RunArrays(**defaults)


def make_run_data_facts(**overrides: Any) -> RunDataFacts:
    """Return a RunDataFacts with valid defaults, overridden by any kwargs.

    Defaults are the simplest healthy fixture: a fake data result, a contract
    whose configured arrays satisfy the pipeline-required Close/Open pair, and
    no metric-registry fingerprint.
    """
    defaults: dict[str, Any] = {
        "data_result": FakeDataResult(),
        "array_contract": DataArrayContract(
            configured_arrays=("Close", "Open"),
            pipeline_required_arrays=("Close", "Open"),
        ),
        "metric_registry_fingerprint": None,
    }
    defaults.update(overrides)
    return RunDataFacts(**defaults)


def make_setup_result(**overrides: Any) -> SetupResult:
    """Return a SetupResult with valid defaults, overridden by any kwargs.

    All fields carry plausible no-op values so tests that only exercise a
    single field (or a subset) can construct the wrapper directly without
    reaching into the setup stage internals.
    """
    defaults: dict[str, Any] = {
        "store_path": Path("candidates.sqlite3"),
        "optimization_source": _fake_optimization_source(),
        "arrays": make_run_arrays(),
    }
    defaults.update(overrides)
    return SetupResult(**defaults)


class _FakeOptimizationSource:
    def __init__(self) -> None:
        self.params: dict[str, Any] = {}
        self.evidence: dict[str, Any] = {"strategy": {}}


def _fake_optimization_source() -> Any:
    return _FakeOptimizationSource()


def make_candidate_portfolio(
    close: pd.DataFrame,
    allocations: pd.DataFrame,
    config: PortfolioConfig | None = None,
    *,
    periods_per_year: int = 252,
    **sim_kwargs: Any,
) -> vbt.Portfolio:
    """Simulate a Candidate batch for metrics tests.

    Wraps the Window Evaluation internal simulation seam so tests that only
    need a Portfolio to extract metrics from never name the sim module
    (mirrors ``make_run_arrays``). ``config`` defaults to the factory
    PortfolioConfig.
    """
    book = ResolvedBook(config if config is not None else make_portfolio_config())
    return simulate_portfolio_batch(
        close, allocations, book, periods_per_year=periods_per_year, **sim_kwargs
    )


SINGLE_CANDIDATE_ID = "single"


def _wrap_single_candidate(allocations: pd.DataFrame) -> pd.DataFrame:
    """Lift a flat symbol frame into the one-candidate MultiIndex the batch path expects."""
    columns = pd.MultiIndex.from_product(
        [[SINGLE_CANDIDATE_ID], allocations.columns],
        names=["candidate_id", SYMBOL_LEVEL],
    )
    return pd.DataFrame(allocations.to_numpy(), index=allocations.index, columns=columns)


def make_single_book_portfolio(
    close: pd.DataFrame,
    allocations: pd.DataFrame,
    config: PortfolioConfig,
    *,
    open_: pd.DataFrame | None = None,
    periods_per_year: int = 252,
    fees_by_symbol: pd.Series | None = None,
    instrument_bands: Mapping[InstrumentId, DriftBand] | None = None,
    futures_roots: tuple[str, ...] = (),
    distributions: Sequence[Distribution] | None = None,
    currency_conversion: CurrencyConversion | None = None,
) -> vbt.Portfolio:
    """Simulate one plain-symbol book through the batched path.

    Test support for carry/mechanics assertions: wraps ``allocations`` into a
    one-candidate MultiIndex (``SINGLE_CANDIDATE_ID``) and the loose book facts
    into a :class:`ResolvedBook`, then delegates to the internal simulation
    seam. Not a production interface — the batch entry is the only production
    path.
    """
    alloc_mi = _wrap_single_candidate(allocations)
    return simulate_portfolio_batch(
        close,
        alloc_mi,
        ResolvedBook(
            config=config,
            fees_by_symbol=fees_by_symbol,
            instrument_bands=instrument_bands,
            futures_roots=futures_roots,
        ),
        open_=open_,
        periods_per_year=periods_per_year,
        distributions=distributions,
        currency_conversion=currency_conversion,
    )


def make_engine_mechanics_portfolio(
    close: pd.DataFrame,
    allocations: pd.DataFrame,
    config: PortfolioConfig,
    *,
    periods_per_year: int = 252,
    futures_roots: tuple[str, ...] = (),
) -> vbt.Portfolio:
    """Simulate one book on the engine seam directly below the exposure gate.

    Engine-mechanics pins only. The gate forbids gross above the unit sleeve
    contract as an END state (aegis-rd-ui1m), but the engine's surplus buying
    power still finances such states TRANSIENTLY (buys sequenced before sells,
    drawdown-drifted books mid-rebalance), so the margin-interest and
    futures-mask cash semantics must stay pinned on books the public batch
    entry rejects. Every behavioral test drives ``simulate_portfolio_batch``;
    only exact-cash-math pins may use this seam.
    """
    alloc_mi = _wrap_single_candidate(allocations)
    expanded_close = expand_market_frame_to_candidate_columns(
        close, alloc_mi.columns, feature_name="Close"
    )
    return _build_portfolio(
        expanded_close,
        alloc_mi,
        ResolvedBook(config=config, futures_roots=futures_roots),
        open_frame=None,
        group_by=vbt.ExceptLevel(SYMBOL_LEVEL),
        scored_start=0,
        periods_per_year=periods_per_year,
    )
