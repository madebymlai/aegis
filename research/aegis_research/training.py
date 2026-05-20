from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from research.aegis_research.config import ResolvedLaneConfig, TrainLaneConfig
from research.aegis_research.experiments import run_experiment
from research.aegis_research.model_registry import FrozenModelRegistry, ModelRegistry
from research.aegis_research.provenance.recorder import RerunMode


def run_training(
    config: ResolvedLaneConfig | TrainLaneConfig | dict[str, Any],
    *,
    model_registry: ModelRegistry | FrozenModelRegistry | None = None,
    label_result_builder: Callable[..., Any] | None = None,
    indicator_result_builder: Callable[..., Any] | None = None,
    rerun_mode: str = RerunMode.NEW,
    run_id: str | None = None,
    parent_run_id: str | None = None,
    supersedes_run_id: str | None = None,
    on_run_started: Callable[[Mapping[str, Any]], None] | None = None,
) -> dict[str, object]:
    result = run_experiment(
        config,
        model_registry=model_registry,
        label_result_builder=label_result_builder,
        indicator_result_builder=indicator_result_builder,
        rerun_mode=rerun_mode,
        run_id=run_id,
        parent_run_id=parent_run_id,
        supersedes_run_id=supersedes_run_id,
        on_run_started=on_run_started,
    )
    result["lane"] = "train"
    result["evidence_type"] = "ml_training"
    return result
