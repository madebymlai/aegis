from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import Any

import pandas as pd

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
        data_bundle = _to_base_currency(config, data_bundle=market_data_bundle(data_result))
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
    pair_by_currency = {ccy: f"{base_currency}{ccy}=X" for ccy in currencies}
    if not pair_by_currency:
        # No foreign legs: there is nothing to fetch (an empty symbol set cannot
        # be pulled), and the empty rates frame makes the conversion an identity.
        return pd.DataFrame(index=index)
    fx_config = replace(
        data_config,
        symbols=[
            SymbolSpec(ticker=pair, ccy=base_currency)
            for pair in pair_by_currency.values()
        ],
    )
    fx_result = load_market_data_result(fx_config, required_arrays=("Close",))
    fx_result.assert_usable()
    fx_close = market_data_bundle(fx_result).array("Close")
    return assemble_fx_rates(
        {ccy: fx_close[pair] for ccy, pair in pair_by_currency.items()},
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

