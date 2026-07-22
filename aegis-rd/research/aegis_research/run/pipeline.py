from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from aegis_data.catalog import catalog_data_port

from research.aegis_research.canonical_json import to_builtin
from research.aegis_research.component_registry import (
    FrozenComponentRegistry,
)
from research.aegis_research.configuration import (
    ResolvedRunConfig,
    RunConfig,
)
from research.aegis_research.metrics.registry import FrozenMetricRegistry
from research.aegis_research.portfolio_simulation import ResolvedBook
from research.aegis_research.run._stages.completion import (
    run_pipeline_completion,
)
from research.aegis_research.run._stages.execution import run_pipeline_execution
from research.aegis_research.run._stages.publishing import run_pipeline_publishing
from research.aegis_research.run._stages.setup import run_pipeline_setup
from research.aegis_research.run.data import RunData, RunDataUnavailable, load_run_data
from research.aegis_research.run.data_contract import (
    DataArrayContract,
    build_run_data_array_contract,
    run_data_evidence_payload,
)
from research.aegis_research.run.evidence import RunEvidence
from research.aegis_research.run.record.capture import capture_config_evidence
from research.aegis_research.run.record.manifest import RunStage
from research.aegis_research.run.record.recorder import RunRecorder
from research.aegis_research.run.record.run_store import RunStore

if TYPE_CHECKING:
    from aegis_data.custom_data import CustomDataProviderMap


def run_strategy_sweep(
    resolved_config: ResolvedRunConfig,
    *,
    component_registry: FrozenComponentRegistry,
    run_id: str | None = None,
    on_run_refs: Callable[[dict[str, Any]], None] | None = None,
    custom_data_providers: CustomDataProviderMap | None = None,
) -> dict[str, Any]:
    """Run a strategy sweep end-to-end, recording provenance for the Run.

    ``on_run_refs`` receives the Run's refs snapshot (run id, manifest path,
    status, started-at, finished-at) when the Run is created,
    and again with terminal refs after a failure or interruption is recorded,
    immediately before the exception re-raises. It does not fire on successful
    completion — the returned result carries the final refs. The callback must
    not raise: a raising callback's error propagates with the Run's real
    failure as its ``__context__``. (ADR-0016)
    """
    config = resolved_config.config
    array_contract = build_run_data_array_contract(config, component_registry)

    recorder = RunStore(config.output_dir).start_run(
        config=resolved_config.resolved_config_document(),
        run_id=run_id,
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
        run_evidence.enter_stage(RunStage.DATA)
        array_contract.assert_configured()
        try:
            run_data = load_run_data(
                config.data,
                required_arrays=array_contract.required_arrays,
                port=catalog_data_port(
                    config.data.path,
                    resolver=config.data.marking_resolver(),
                ),
                custom_data_providers=custom_data_providers,
            )
        except RunDataUnavailable as error:
            recorder.manifest.evidence["data"] = to_builtin(error.evidence)
            recorder.persist()
            raise
        recorder.manifest.evidence["data"] = run_data_evidence_payload(
            run_data,
            array_contract,
        )
        recorder.persist()
        run_evidence.enter_stage(RunStage.SETUP)
        metric_registry = resolved_config.metric_registry
        book = ResolvedBook.resolve(config.portfolio, run_data)
        return _run_optimization_strategy_sweep(
            config,
            component_registry=component_registry,
            recorder=recorder,
            run_data=run_data,
            array_contract=array_contract,
            book=book,
            metric_registry=metric_registry,
            run_evidence=run_evidence,
        )
    except KeyboardInterrupt as error:
        recorder.mark_run_interrupted(
            stage=run_evidence.active_stage,
            error=error,
        )
        if on_run_refs is not None:
            on_run_refs(recorder.run_refs())
        raise
    except Exception as error:
        recorder.mark_run_failed(
            stage=run_evidence.active_stage,
            error=error,
        )
        if on_run_refs is not None:
            on_run_refs(recorder.run_refs())
        raise


def _run_optimization_strategy_sweep(
    config: RunConfig,
    *,
    component_registry: FrozenComponentRegistry,
    recorder: RunRecorder,
    run_data: RunData,
    array_contract: DataArrayContract,
    book: ResolvedBook,
    metric_registry: FrozenMetricRegistry,
    run_evidence: RunEvidence,
) -> dict[str, Any]:
    # Stage 1: Setup — resolve locks, build optimization source and evidence baseline
    run_evidence.enter_stage(RunStage.SETUP)
    try:
        setup = run_pipeline_setup(
            config=config,
            component_registry=component_registry,
            run_data=run_data,
            array_contract=array_contract,
            metric_registry_fingerprint=metric_registry.fingerprint,
            run_evidence=run_evidence,
        )
    except Exception:
        run_evidence.persist_partial()
        raise

    # Stage 2: Execution — preflight gate, two-phase optimization sweep
    execution = run_pipeline_execution(
        config=config,
        setup=setup,
        book=book,
        metric_registry=metric_registry,
        run_evidence=run_evidence,
    )

    # Stage 3: Publishing — three representative candidates, candidate store
    publishing = run_pipeline_publishing(
        config=config,
        recorder=recorder,
        run_data=run_data,
        array_contract=array_contract,
        metric_registry_fingerprint=metric_registry.fingerprint,
        optimization_source=setup.optimization_source,
        execution=execution,
        run_evidence=run_evidence,
        store_path=setup.store_path,
    )

    # Stage 4: Completion — lifecycle completion, activation, result
    return run_pipeline_completion(
        setup=setup,
        publishing=publishing,
        config=config,
        recorder=recorder,
        run_evidence=run_evidence,
    )
