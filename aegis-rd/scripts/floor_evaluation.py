"""Reproduce a locked Run Config as a net daily return stream.

This is the loader half of the floor evaluation. It exists so the two poles of the
Floor - the trend sleeve and the convergent income sleeve - can be turned into two
aligned daily return series and handed to
``research.aegis_research.metrics.custom.convergent.evaluate_allocator_contribution``,
which owns the paired statistics (delta-Theta-hat, downside correlation, and the
paired circular-block intervals around them).

WHY THE SPLIT IS HERE
---------------------
The predecessor of this module (deleted by ``b1a50e34`` along with the split and
window workflows it depended on) carried both halves: it loaded returns *and* owned
its own ``_mppm``, Sharpe and bootstrap, duplicating - and contradicting - the
library's. Commit ``77565936`` moved the statistics into the metric module. What is
left here computes no statistics at all: it is orchestration over the run pipeline,
and the dependency runs script -> library, never the reverse.

CORRECTNESS BY REUSE
--------------------
The replay is not re-derived. This module calls ``build_development_paths``, the same
function the optimization runner uses, so a locked config evaluated here and the same
config evaluated by a Run produce the *same* portfolio through the *same* code path.
A second, parallel replay implementation would be free to drift from the pipeline;
this one cannot. The cost is that ranking metrics are computed and discarded, which is
cheap for the single Candidate a locked config resolves to.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
from aegis_data.catalog import catalog_data_port

from research.aegis_research.configuration import load_run_config
from research.aegis_research.metrics.custom.support.equity_curve import EquityCurve
from research.aegis_research.optimization.candidate_paths import build_development_paths
from research.aegis_research.optimization.param_namespace import FIXED_CANDIDATE_PARAM
from research.aegis_research.portfolio_simulation import ResolvedBook
from research.aegis_research.run._stages.setup import run_pipeline_setup
from research.aegis_research.run.data import load_run_data
from research.aegis_research.run.data_contract import build_run_data_array_contract


class FloorEvaluationError(ValueError):
    """A config cannot be reproduced as a single net return stream."""


@dataclass(frozen=True)
class LockedStrategyReturns:
    """One locked config's production-simulated net return stream, with provenance.

    The provenance travels with the series because the returns feed a *reported*
    number. A delta-Theta-hat without the candidate key that produced it cannot be
    re-derived later, and the pair of configs is the whole claim.
    """

    config_path: str
    config_hash: str
    config_name: str
    base_currency: str
    lock_run_id: str
    lock_candidate_id: str
    resolved_candidate_key: str
    returns: pd.Series

    def evidence(self) -> dict[str, Any]:
        """The provenance record for this stream, JSON-ready."""
        return {
            "config_path": self.config_path,
            "config_hash": self.config_hash,
            "config_name": self.config_name,
            "base_currency": self.base_currency,
            "lock_run_id": self.lock_run_id,
            "lock_candidate_id": self.lock_candidate_id,
            "resolved_candidate_key": self.resolved_candidate_key,
            "observations": len(self.returns),
            "start": self.returns.index.min().date().isoformat(),
            "end": self.returns.index.max().date().isoformat(),
        }


def load_locked_strategy_returns(config_path: str | Path) -> LockedStrategyReturns:
    """Reproduce one locked config and return its full net daily return stream."""
    path = Path(config_path).expanduser().resolve()
    resolved = load_run_config(path)
    config = resolved.config

    if config.lock is None:
        raise FloorEvaluationError(
            f"config {path} has no top-level lock; select and lock a Candidate before "
            "paired evaluation"
        )
    registry = resolved.component_registry
    if registry is None:
        raise FloorEvaluationError(f"config {path} has no resolved Component registry")

    array_contract = build_run_data_array_contract(config, registry)
    array_contract.assert_configured()
    run_data = load_run_data(
        config.data,
        required_arrays=array_contract.required_arrays,
        port=catalog_data_port(config.data.path, resolver=config.data.marking_resolver()),
        custom_data_providers=None,
    )

    setup = run_pipeline_setup(config=config, component_registry=registry, run_data=run_data)
    source = setup.optimization_source
    # A locked config must collapse to the single fixed Candidate axis. If any sweep axis
    # survives, the config is locked in name only and the "one stream" contract below would
    # silently pick an arbitrary column.
    if tuple(source.params) != (FIXED_CANDIDATE_PARAM,):
        raise FloorEvaluationError(
            f"locked config {path} still exposes Candidate axes: {sorted(source.params)}"
        )

    paths = build_development_paths(
        run_data=run_data,
        source=source,
        optimization=config.optimization,
        book=ResolvedBook.resolve(config.portfolio, run_data),
        report=config.report,
        metric_registry=resolved.metric_registry,
        min_trades=config.ranking.min_trades,
        ranking_metric=config.ranking.metric,
    )

    return_frame = EquityCurve.from_portfolio(paths.replay.portfolio).returns()
    if return_frame.shape[1] != 1:
        raise FloorEvaluationError(
            f"locked config {path} produced {return_frame.shape[1]} return streams; expected one"
        )
    returns = return_frame.iloc[:, 0].dropna().rename(config.name)
    # Both poles must land on identical daily timestamps or the pairing aligns silently
    # wrong and every paired statistic downstream is meaningless.
    returns.index = pd.DatetimeIndex(returns.index).tz_localize(None).normalize()
    if returns.empty:
        raise FloorEvaluationError(f"locked config {path} produced no returns")

    return LockedStrategyReturns(
        config_path=str(path),
        config_hash=resolved.raw_config_hash,
        config_name=config.name,
        base_currency=config.data.base_currency,
        lock_run_id=config.lock.run_id,
        lock_candidate_id=config.lock.candidate_id,
        resolved_candidate_key=_resolved_candidate_key(config, setup.store_path),
        returns=returns,
    )


def _resolved_candidate_key(config: Any, store_path: Path) -> str:
    """Re-read the Candidate key the Lock resolved to, for the provenance record."""
    from research.aegis_research.candidates.lock import resolve_lock_run
    from research.aegis_research.candidates.store import CandidateStore

    with CandidateStore(store_path) as store:
        return str(resolve_lock_run(config.lock, store=store).candidate_key)


__all__ = [
    "FloorEvaluationError",
    "LockedStrategyReturns",
    "load_locked_strategy_returns",
]
