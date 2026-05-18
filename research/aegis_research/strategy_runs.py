from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from research.aegis_research.component_registry import (
    ComponentSelection,
    FrozenComponentRegistry,
)
from research.aegis_research.config import ResolvedLaneConfig, SignalConfig, to_builtin
from research.aegis_research.data import load_market_data_result
from research.aegis_research.play_artifacts import build_play_leaderboard
from research.aegis_research.portfolios import simulate_portfolio
from research.aegis_research.provenance.manifest import atomic_write_json, hash_file
from research.aegis_research.provenance.recorder import RerunMode
from research.aegis_research.provenance.run_store import RunStore
from research.aegis_research.reports import portfolio_metrics

STRATEGY_ARTIFACT_SCHEMA_VERSION = "strategy_run.v1"
STRATEGY_OUTPUT_FORBIDDEN_KEYS = {
    "costs",
    "direction",
    "entry_budget",
    "execution_timing",
    "fees",
    "portfolio",
    "price",
    "size",
    "sizing",
    "slippage",
}


@dataclass(frozen=True)
class StrategyInputBundle:
    close: pd.DataFrame
    indicators: dict[str, Any]
    params: dict[str, Any]
    metadata: dict[str, Any]


@dataclass(frozen=True)
class StrategySignalResult:
    entries: pd.DataFrame
    exits: pd.DataFrame
    diagnostics: dict[str, Any]


def run_strategy_sweep(
    resolved_config: ResolvedLaneConfig,
    *,
    component_registry: FrozenComponentRegistry,
    rerun_mode: str = RerunMode.NEW,
    run_id: str | None = None,
    parent_run_id: str | None = None,
    supersedes_run_id: str | None = None,
) -> dict[str, Any]:
    config = resolved_config.config
    if config.lane != "run":
        raise ValueError("run_strategy_sweep requires a run lane config")

    recorder = RunStore(config.output_dir).start_run(
        run_label=config.name,
        config=resolved_config.redacted_resolved_config(),
        mode=rerun_mode,
        run_id=run_id,
        parent_run_id=parent_run_id,
        supersedes_run_id=supersedes_run_id,
    )
    recorder.manifest.evidence = {
        "lane": "run",
        "evidence_type": "strategy_sweep",
        "component_registry_fingerprint": component_registry.fingerprint,
    }
    recorder.persist()

    try:
        data_result = load_market_data_result(config.data, required_features=("Close", "Open"))
        data_result.assert_usable()
        close = data_result.feature("Close")
        open_prices = data_result.feature("Open")

        definition = component_registry.get(ComponentSelection("strategies", config.strategy.id))
        strategy_callable = definition.load_callable()
        bundle = StrategyInputBundle(
            close=close,
            indicators={},
            params=config.strategy.params,
            metadata={
                "strategy_id": config.strategy.id,
                "component_source_hash": definition.identity.source_hash,
            },
        )
        signal_result = validate_strategy_output(strategy_callable(bundle), bundle)
        signal_config = SignalConfig()
        portfolio = simulate_portfolio(
            close,
            signal_result.entries,
            signal_result.exits,
            config.portfolio,
            signal_config,
            open_prices=open_prices,
            market_index=close.index,
        )
        metrics = portfolio_metrics(portfolio.portfolio, config.report)
        variant_record = {
            "variant_id": config.strategy.id,
            "strategy_source": "component",
            "strategy_id": config.strategy.id,
            "component_source_hash": definition.identity.source_hash,
            "metrics": metrics,
            "params": config.strategy.params,
            "portfolio": to_builtin(asdict(config.portfolio)),
        }
        leaderboard = build_play_leaderboard(
            [variant_record],
            metric=config.ranking.metric,
            direction=config.ranking.direction,
            rank_by=config.ranking.rank_by,
        )
        payload = {
            "schema_version": STRATEGY_ARTIFACT_SCHEMA_VERSION,
            "lane": "run",
            "evidence_type": "strategy_sweep",
            "strategy": {
                "source": "component",
                "id": config.strategy.id,
                "version": definition.manifest.version,
                "source_hash": definition.identity.source_hash,
            },
            "leaderboard": leaderboard,
            "signal_diagnostics": signal_result.diagnostics,
            "portfolio_diagnostics": portfolio.diagnostics,
        }
        _write_strategy_artifact(recorder, payload)
        recorder.mark_run_completed()
        return {
            "run_id": recorder.manifest.run_id,
            "run_dir": str(recorder.run_dir),
            "manifest_path": str(recorder.manifest_path),
            "status": recorder.manifest.status,
            "started_at": recorder.manifest.started_at,
            "finished_at": recorder.manifest.finished_at,
            "lane": "run",
            "evidence_type": "strategy_sweep",
            "strategy_artifact_id": "strategy.run",
            "leaderboard": leaderboard,
        }
    except Exception as error:
        recorder.mark_run_failed(diagnostic={"error_type": type(error).__name__, "message": str(error)[:1000]})
        raise


def validate_strategy_output(output: Any, bundle: StrategyInputBundle) -> StrategySignalResult:
    if not isinstance(output, dict):
        raise TypeError("strategy output must be a mapping")
    forbidden = sorted(set(output) & STRATEGY_OUTPUT_FORBIDDEN_KEYS)
    if forbidden:
        raise ValueError(f"strategy output must not contain portfolio fields: {forbidden}")
    if "entries" not in output or "exits" not in output:
        raise ValueError("strategy output must include entries and exits")
    entries = _signal_frame(output["entries"], bundle.close, "entries")
    exits = _signal_frame(output["exits"], bundle.close, "exits")
    diagnostics = {
        "schema_version": "strategy_signal_diagnostics.v1",
        "entry_states": _true_count(entries),
        "exit_states": _true_count(exits),
        "symbols": [str(column) for column in entries.columns],
        "timing": "signals_are_bar_aligned_inputs_to_config_owned_portfolio_execution",
    }
    if isinstance(output.get("diagnostics"), dict):
        diagnostics["strategy"] = output["diagnostics"]
    return StrategySignalResult(entries=entries, exits=exits, diagnostics=diagnostics)


def _signal_frame(value: Any, close: pd.DataFrame, name: str) -> pd.DataFrame:
    frame = value.to_frame() if isinstance(value, pd.Series) else value
    if not isinstance(frame, pd.DataFrame):
        raise TypeError(f"strategy output {name} must be a pandas DataFrame")
    if not frame.index.equals(close.index):
        raise ValueError(f"strategy output {name} has misaligned timestamps")
    if list(map(str, frame.columns)) != list(map(str, close.columns)):
        raise ValueError(f"strategy output {name} has misaligned symbols")
    return frame.fillna(False).astype(bool)


def _write_strategy_artifact(recorder, payload: dict[str, Any]) -> None:
    artifact_path = Path("strategy_run.json")
    recorder.artifacts.plan_artifact(
        artifact_id="strategy.run",
        role="strategy_sweep_evidence",
        artifact_type="json",
        producer_stage="strategy_run",
        path=str(artifact_path),
        schema_version=STRATEGY_ARTIFACT_SCHEMA_VERSION,
    )
    recorder.artifacts.begin_artifact_write("strategy.run")
    full_path = recorder.run_dir / artifact_path
    atomic_write_json(full_path, payload)
    recorder.artifacts.complete_artifact(
        "strategy.run",
        content_hash=hash_file(full_path),
        size=full_path.stat().st_size,
        shape={"leaderboard_rows": len(payload["leaderboard"]["rows"])},
    )


def _true_count(value: pd.DataFrame | pd.Series) -> int:
    return int(value.to_numpy(dtype=bool).sum())
