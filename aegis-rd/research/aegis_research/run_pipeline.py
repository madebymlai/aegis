from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import Any

import pandas as pd
from aegis_data.calendars import TradingCalendar
from aegis_data.source import continuous_panel, databento_source
from aegis_data.store import FxPair, read_fx_history
from aegis_data.yfinance import YFinanceLocator, pull_yfinance_fx_history

from research.aegis_research.component_registry import (
    FrozenComponentRegistry,
)
from research.aegis_research.configuration import (
    FORWARD_OPTIMIZATION_REQUIRED_MESSAGE,
    ConfigValidationError,
    ConfigValidationIssue,
    DataConfig,
    ResolvedRunConfig,
    RunConfig,
    SymbolSpec,
    required_store_window_edge,
    store_gap_fill_provider,
)
from research.aegis_research.data import (
    MarketDataBundle,
    MarketDataResult,
    load_market_data_result,
    market_data_bundle,
)
from research.aegis_research.market_data.currency import (
    assemble_fx_rates,
    convert_bundle_to_base,
    required_fx_currencies,
)
from research.aegis_research.metrics.registry import FrozenMetricRegistry
from research.aegis_research.optimization.evidence_ledger import (
    EvidenceFailureStage,
    RunEvidence,
)
from research.aegis_research.optimization.pipeline.completion import (
    run_pipeline_completion,
)
from research.aegis_research.optimization.pipeline.execution import run_pipeline_execution
from research.aegis_research.optimization.pipeline.publishing import run_pipeline_publishing
from research.aegis_research.optimization.pipeline.setup import run_pipeline_setup
from research.aegis_research.optimization.run_data_contract import (
    DataArrayContract,
    build_run_data_array_contract,
)
from research.aegis_research.provenance.capture import capture_config_evidence
from research.aegis_research.provenance.data_artifacts import write_data_metadata_artifact
from research.aegis_research.provenance.recorder import RerunMode, RunRecorder
from research.aegis_research.provenance.run_store import RunStore


def run_strategy_sweep(
    resolved_config: ResolvedRunConfig,
    *,
    component_registry: FrozenComponentRegistry,
    rerun_mode: str = RerunMode.NEW,
    run_id: str | None = None,
    parent_run_id: str | None = None,
    supersedes_run_id: str | None = None,
    on_run_refs: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Run a strategy sweep end-to-end, recording provenance for the Run.

    ``on_run_refs`` receives the Run's refs snapshot (run id, run directory,
    manifest path, status, started-at, finished-at) when the Run is created,
    and again with terminal refs after a failure or interruption is recorded,
    immediately before the exception re-raises. It does not fire on successful
    completion — the returned result carries the final refs. The callback must
    not raise: a raising callback's error propagates with the Run's real
    failure as its ``__context__``. (ADR-0016)
    """
    config = resolved_config.config
    if config.optimization is None:
        raise ConfigValidationError(
            [
                ConfigValidationIssue(
                    "optimization",
                    FORWARD_OPTIMIZATION_REQUIRED_MESSAGE,
                )
            ]
        )
    array_contract = build_run_data_array_contract(config, component_registry)

    recorder = RunStore(config.output_dir).start_run(
        run_label=config.name,
        config=resolved_config.resolved_config_document(),
        mode=rerun_mode,
        run_id=run_id,
        parent_run_id=parent_run_id,
        supersedes_run_id=supersedes_run_id,
    )
    run_evidence = RunEvidence(
        recorder.manifest.evidence,
        component_registry_fingerprint=component_registry.fingerprint,
        data_arrays=array_contract.metadata(),
        optimization={},
        persist=recorder.persist,
    )
    # The Manifest's config Evidence carries the config-selection record with
    # the resolved absolute config path (ADR-0021). Runs started without a
    # selection (direct pipeline callers) record no config Evidence — existing
    # Runs and goldens are unaffected.
    if resolved_config.selection is not None:
        recorder.manifest.evidence["config"] = capture_config_evidence(resolved_config)
    recorder.persist()

    try:
        if on_run_refs is not None:
            on_run_refs(recorder.run_refs())
        array_contract.assert_configured()
        data_result = load_market_data_result(
            config.data,
            required_arrays=array_contract.required_arrays,
        )
        write_data_metadata_artifact(recorder, data_result, array_contract)
        data_result.assert_usable()
        data_bundle = _apply_futures_back_adjustment(config.data, market_data_bundle(data_result))
        data_bundle = _to_base_currency(config, data_bundle=data_bundle)
        metric_registry = resolved_config.metric_registry
        return _run_optimization_strategy_sweep(
            config,
            component_registry=component_registry,
            recorder=recorder,
            data_result=data_result,
            data=data_bundle,
            array_contract=array_contract,
            metric_registry_fingerprint=metric_registry.fingerprint,
            metric_registry=metric_registry,
            run_evidence=run_evidence,
        )
    except KeyboardInterrupt:
        recorder.mark_run_interrupted(
            diagnostic={"error_type": "KeyboardInterrupt", "message": "interrupted"}
        )
        if on_run_refs is not None:
            on_run_refs(recorder.run_refs())
        raise
    except Exception as error:
        recorder.mark_run_failed(diagnostic=_failure_diagnostic(error))
        if on_run_refs is not None:
            on_run_refs(recorder.run_refs())
        raise


def _apply_futures_back_adjustment(
    data_config: DataConfig, data_bundle: MarketDataBundle
) -> MarketDataBundle:
    """Replace each ``back_adjust`` future's panel column with the back-adjusted
    continuous series sourced from :mod:`aegis_data` (Nautilus databento port +
    OS-global parquet store); a book with no back-adjust futures passes through.
    """
    if data_config.source == "store":
        return data_bundle
    futures = [s for s in data_config.symbols if s.is_future and s.adjustment == "back_adjust"]
    if not futures:
        return data_bundle
    start = pd.Timestamp(data_config.start).date()
    end = pd.Timestamp(data_config.end).date()
    arrays = {name: panel.copy() for name, panel in data_bundle.arrays.items()}
    for spec in futures:
        fetch = databento_source(spec.dataset)
        panel = continuous_panel(spec.root, start, end, fetch=fetch)
        for name, frame in arrays.items():
            if spec.ticker in frame.columns and name in panel.columns:
                frame[spec.ticker] = panel[name].reindex(frame.index)
    return MarketDataBundle(arrays)


def _to_base_currency(
    config: RunConfig, *, data_bundle: MarketDataBundle
) -> MarketDataBundle:
    """Re-express the loaded bundle in the portfolio's base currency.

    One path: the price panels always flow through the converter. A book whose
    legs already quote in the base needs no FX series, and the conversion is then
    an identity - a no-op, not a separate branch.
    """
    base_currency = config.portfolio.base_currency
    currency_by_symbol = config.data.currency_by_symbol
    fx_rates = _load_fx_rates(
        config.data,
        base_currency=base_currency,
        currencies=required_fx_currencies(currency_by_symbol, base_currency),
        index=data_bundle.array("Close").index,
    )
    return convert_bundle_to_base(
        data_bundle, currency_by_symbol, base_currency, fx_rates
    )


def _load_fx_rates(
    data_config: DataConfig,
    *,
    base_currency: str,
    currencies: set[str],
    index: pd.Index,
) -> pd.DataFrame:
    """Fetch the ``base->ccy`` FX series (the native ``EUR<ccy>=X`` quotes) and
    align them to the price ``index``."""
    fx_ticker_by_currency = {ccy: f"{base_currency}{ccy}=X" for ccy in currencies}
    if not fx_ticker_by_currency:
        # No foreign legs: there is nothing to fetch (an empty symbol set cannot
        # be pulled), and the empty rates frame makes the conversion an identity.
        return pd.DataFrame(index=index)
    if data_config.source == "store":
        return _load_store_fx_rates(
            data_config,
            base_currency=base_currency,
            fx_ticker_by_currency=fx_ticker_by_currency,
            index=index,
        )
    fx_config = replace(
        data_config,
        symbols=[
            SymbolSpec(ticker=fx_ticker, ccy=base_currency)
            for fx_ticker in fx_ticker_by_currency.values()
        ],
    )
    fx_result = load_market_data_result(fx_config, required_arrays=("Close",))
    fx_result.assert_usable()
    fx_close = market_data_bundle(fx_result).array("Close")
    return assemble_fx_rates(
        {ccy: fx_close[fx_ticker] for ccy, fx_ticker in fx_ticker_by_currency.items()},
        index=index,
    )


def _load_store_fx_rates(
    data_config: DataConfig,
    *,
    base_currency: str,
    fx_ticker_by_currency: dict[str, str],
    index: pd.Index,
) -> pd.DataFrame:
    provider = store_gap_fill_provider(data_config.provider)
    if provider != "yfinance":
        raise ValueError(f"unsupported store FX gap-fill provider {provider!r}")
    start = required_store_window_edge(data_config.start, "start")
    end = required_store_window_edge(data_config.end, "end")
    fx_pair_by_currency = {ccy: FxPair(base_currency, ccy) for ccy in fx_ticker_by_currency}
    for ccy, fx_pair in fx_pair_by_currency.items():
        pull_yfinance_fx_history(
            fx_pair,
            timeframe=data_config.timeframe,
            start=start,
            end=end,
            calendar=TradingCalendar.WEEKDAY,
            locator=YFinanceLocator(fx_ticker_by_currency[ccy]),
        )
    histories = read_fx_history(
        tuple(fx_pair_by_currency.values()),
        timeframe=data_config.timeframe,
        start=start,
        end=end,
        calendar=TradingCalendar.WEEKDAY,
    )
    return assemble_fx_rates(
        {ccy: histories[fx_pair] for ccy, fx_pair in fx_pair_by_currency.items()},
        index=index,
    )


def _failure_diagnostic(error: Exception) -> dict[str, str]:
    return {
        "error_type": type(error).__name__,
        "message": str(error)[:1000],
    }


def _run_optimization_strategy_sweep(
    config: RunConfig,
    *,
    component_registry: FrozenComponentRegistry,
    recorder: RunRecorder,
    data_result: MarketDataResult,
    data: MarketDataBundle,
    array_contract: DataArrayContract,
    metric_registry_fingerprint: str | None,
    metric_registry: FrozenMetricRegistry,
    run_evidence: RunEvidence,
) -> dict[str, Any]:
    # Stage 1: Setup — resolve locks, build optimization source and evidence baseline
    try:
        setup = run_pipeline_setup(
            config=config,
            component_registry=component_registry,
            data=data,
            data_result=data_result,
            array_contract=array_contract,
            metric_registry_fingerprint=metric_registry_fingerprint,
            run_evidence=run_evidence,
        )
    except Exception as error:
        run_evidence.fail(EvidenceFailureStage.SETUP, error)
        raise

    # Stage 2: Execution — preflight gate, two-phase optimization sweep
    execution = run_pipeline_execution(
        config=config,
        setup=setup,
        metric_registry=metric_registry,
        run_evidence=run_evidence,
    )

    # Stage 3: Publishing — three representative candidates, candidate store
    publishing = run_pipeline_publishing(
        config=config,
        recorder=recorder,
        data_result=data_result,
        array_contract=array_contract,
        optimization_source=setup.optimization_source,
        execution=execution,
        run_evidence=run_evidence,
        store_path=setup.store_path,
        metric_registry_fingerprint=metric_registry_fingerprint,
    )

    # Stage 4: Completion — artifact, completion, activation, result
    return run_pipeline_completion(
        setup=setup,
        publishing=publishing,
        config=config,
        recorder=recorder,
        data_result=data_result,
        array_contract=array_contract,
        run_evidence=run_evidence,
        metric_registry_fingerprint=metric_registry_fingerprint,
    )

