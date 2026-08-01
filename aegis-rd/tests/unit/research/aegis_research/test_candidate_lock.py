"""Unit tests for the top-level Lock run-resolution deep module.

A ``Lock`` (``run_id`` + ``candidate_id`` = the ``candidates`` primary key) reproduces
one prior Candidate end-to-end: the deep module loads that Candidate by its primary key
and fans its parameters across every Component using the component-param slicing.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from nautilus_trader.model.enums import ContinuousFutureAdjustmentType
from vectorbtpro import vbt

from research.aegis_research.candidates.lock import (
    LockRunResolutionError,
    resolve_lock_run,
)
from research.aegis_research.candidates.models import CandidateSet
from research.aegis_research.candidates.records import candidate_rows_from_result
from research.aegis_research.candidates.store import CandidateStore
from research.aegis_research.optimization.component_source import (
    _source_identity as build_source_identity,
)
from research.aegis_research.optimization.param_namespace import (
    ComponentRef,
    encode,
)
from research.aegis_research.optimization.ranking import (
    EvaluatedCandidate,
    OptimizationResult,
)
from research.aegis_research.run.identity import RunId
from tests.support.research.aegis_research.factories import (
    make_component_runtime,
    make_lock,
    make_selection_identity,
)

_DATA_IDENTITY = {
    "schema_version": "candidate_data_identity.v3",
    "requested_instrument_ids": ["SYN.XNAS"],
    "instrument_ids": ["SYN.XNAS"],
    "timeframe": "1D",
}

_STRATEGY_REF = ComponentRef("strategies", "demo.ma_cross", "strategy:demo.ma_cross")
_INDICATOR_REF = ComponentRef("indicators", "demo.mom", "demo.mom")
_FAST_KEY = encode(_STRATEGY_REF, "fast_window")
_SLOW_KEY = encode(_STRATEGY_REF, "slow_window")
_WINDOW_KEY = encode(_INDICATOR_REF, "window")


def test_resolves_per_component_params_for_locked_candidate(tmp_path: Path) -> None:
    with _store_with_candidate(tmp_path) as store:
        candidate_key = store.candidate_key_for_role("run-a", "best")

        resolved = resolve_lock_run(
            make_lock(run_id="run-a", candidate_id=candidate_key),
            store=store,
        )

    assert resolved.run_id == "run-a"
    assert resolved.candidate_key == candidate_key
    # Params fan across both the strategy and the indicator slots.
    strategy_ref = ComponentRef("strategies", "demo.ma_cross", "strategy:demo.ma_cross")
    indicator_ref = ComponentRef("indicators", "demo.mom", "demo.mom")
    assert resolved.component_params[strategy_ref] == {"fast_window": 2, "slow_window": 10}
    assert resolved.component_params[indicator_ref] == {"window": 20}


def test_resolves_role_handle_through_rankings(tmp_path: Path) -> None:
    # aegis-rd-6ie: a role keyword in candidate_id resolves to the ranked candidate_key
    # via candidate_rankings, and provenance still records the *resolved* hash.
    with _store_with_candidate(tmp_path) as store:
        expected_key = store.candidate_key_for_role("run-a", "best")

        resolved = resolve_lock_run(
            make_lock(run_id="run-a", candidate_id="best"),
            store=store,
        )

    assert resolved.candidate_key == expected_key
    assert resolved.provenance["candidate_id"] == expected_key


def test_role_selects_the_matching_ranked_candidate(tmp_path: Path) -> None:
    # With three *distinct* ranked candidates, the median role must resolve to the
    # median candidate's key and params — never the best's.
    with _store_with_distinct_roles(tmp_path) as store:
        ranked = {
            role: store.candidate_key_for_role("run-a", role)
            for role in ("best", "median", "worst")
        }

        resolved = resolve_lock_run(
            make_lock(run_id="run-a", candidate_id="median"),
            store=store,
        )

    assert resolved.candidate_key == ranked["median"]
    assert resolved.candidate_key != ranked["best"]
    strategy_ref = ComponentRef("strategies", "demo.ma_cross", "strategy:demo.ma_cross")
    indicator_ref = ComponentRef("indicators", "demo.mom", "demo.mom")
    assert resolved.component_params[strategy_ref] == {"fast_window": 3, "slow_window": 12}
    assert resolved.component_params[indicator_ref] == {"window": 22}


def test_exposes_recorded_adjustment_mode_as_a_typed_fact(tmp_path: Path) -> None:
    # Export reads only this lock-resolved fact — never raw provenance mappings and
    # never the current code default.
    with _store_with_candidate(
        tmp_path, data_identity={**_DATA_IDENTITY, "adjustment_mode": "backward_spread"}
    ) as store:
        candidate_key = store.candidate_key_for_role("run-a", "best")

        resolved = resolve_lock_run(
            make_lock(run_id="run-a", candidate_id=candidate_key),
            store=store,
        )

    assert resolved.adjustment_mode is ContinuousFutureAdjustmentType.BACKWARD_SPREAD


def test_missing_adjustment_mode_identity_resolves_to_none(tmp_path: Path) -> None:
    # A prior Run recorded no mode; the typed fact is None and the
    # futures-vs-mode decision belongs to export.
    with _store_with_candidate(tmp_path) as store:
        candidate_key = store.candidate_key_for_role("run-a", "best")

        resolved = resolve_lock_run(
            make_lock(run_id="run-a", candidate_id=candidate_key),
            store=store,
        )

    assert resolved.adjustment_mode is None


def test_rejects_an_unknown_recorded_adjustment_mode(tmp_path: Path) -> None:
    with _store_with_candidate(
        tmp_path, data_identity={**_DATA_IDENTITY, "adjustment_mode": "forward_ratio"}
    ) as store:
        candidate_key = store.candidate_key_for_role("run-a", "best")

        with pytest.raises(LockRunResolutionError, match="adjustment mode"):
            resolve_lock_run(
                make_lock(run_id="run-a", candidate_id=candidate_key),
                store=store,
            )


def test_rejects_unknown_run_id(tmp_path: Path) -> None:
    with _store_with_candidate(tmp_path) as store:
        candidate_key = store.candidate_key_for_role("run-a", "best")
        with pytest.raises(LockRunResolutionError, match="unknown candidate"):
            resolve_lock_run(
                make_lock(run_id="run-missing", candidate_id=candidate_key),
                store=store,
            )


def test_rejects_unknown_candidate_id(tmp_path: Path) -> None:
    with _store_with_candidate(tmp_path) as store:  # noqa: SIM117
        with pytest.raises(LockRunResolutionError, match="unknown candidate"):
            resolve_lock_run(
                make_lock(run_id="run-a", candidate_id="cand_missing"),
                store=store,
            )


def test_rejects_candidate_missing_referenced_component(tmp_path: Path) -> None:
    without_indicator = _source_identity(drop_indicator_runtime=True)
    with _store_with_candidate(tmp_path, source_identity=without_indicator) as store:
        candidate_key = store.candidate_key_for_role("run-a", "best")
        with pytest.raises(LockRunResolutionError, match="does not include component"):
            resolve_lock_run(
                make_lock(run_id="run-a", candidate_id=candidate_key),
                store=store,
            )


def test_resolves_a_superseded_contract_whose_read_fields_did_not_move(
    tmp_path: Path,
) -> None:
    # Resolution gates on the shape it reads, not on the recorded contract version:
    # a Candidate written under an older component-source contract still reproduces
    # exactly when the fields Lock resolution consumes are unchanged. Gating on the
    # version instead would refuse it for a change it does not depend on.
    superseded = {**_source_identity(), "schema_version": "component_optimization_source.v1"}
    with _store_with_candidate(tmp_path, source_identity=superseded) as store:
        candidate_key = store.candidate_key_for_role("run-a", "best")

        resolved = resolve_lock_run(
            make_lock(run_id="run-a", candidate_id=candidate_key),
            store=store,
        )

    assert resolved.component_params[_STRATEGY_REF] == {"fast_window": 2, "slow_window": 10}
    assert resolved.component_params[_INDICATOR_REF] == {"window": 20}


@pytest.mark.parametrize("field", ["fixed_params", "param_keys"])
def test_rejects_a_runtime_that_omits_a_param_mapping(tmp_path: Path, field: str) -> None:
    # Silently defaulting to {} would drop the Component's fixed params and
    # reproduce a different strategy than the Candidate names.
    source = _source_identity()
    del source["strategy"][field]  # type: ignore[union-attr]
    with _store_with_candidate(tmp_path, source_identity=source) as store:
        candidate_key = store.candidate_key_for_role("run-a", "best")
        with pytest.raises(LockRunResolutionError, match=field):
            resolve_lock_run(
                make_lock(run_id="run-a", candidate_id=candidate_key),
                store=store,
            )


def _store_with_candidate(
    tmp_path: Path,
    *,
    data_identity: dict[str, object] | None = None,
    source_identity: dict[str, object] | None = None,
) -> CandidateStore:
    store = CandidateStore(tmp_path / "candidates.sqlite3")
    identity = _DATA_IDENTITY if data_identity is None else data_identity
    candidates = _candidate_rows(identity)
    source = _source_identity() if source_identity is None else source_identity
    store.commit_candidates(
        CandidateSet.create(
            run_id=RunId("run-a"),
            candidates=candidates,
            provenance={
                "schema_version": "candidate_store_provenance.v3",
                "run_id": "run-a",
                "source": source,
                "data": identity,
                "selection_identity": make_selection_identity(),
            },
        )
    )
    return store


def _store_with_distinct_roles(tmp_path: Path) -> CandidateStore:
    store = CandidateStore(tmp_path / "candidates.sqlite3")
    fast_key = encode(
        ComponentRef("strategies", "demo.ma_cross", "strategy:demo.ma_cross"), "fast_window"
    )
    slow_key = encode(
        ComponentRef("strategies", "demo.ma_cross", "strategy:demo.ma_cross"), "slow_window"
    )
    window_key = encode(ComponentRef("indicators", "demo.mom", "demo.mom"), "window")
    result = OptimizationResult(
        best=_candidate({fast_key: 2, slow_key: 10, window_key: 20}, 0.30),
        median=_candidate({fast_key: 3, slow_key: 12, window_key: 22}, 0.20),
        worst=_candidate({fast_key: 5, slow_key: 15, window_key: 25}, 0.10),
    )
    rows = candidate_rows_from_result(
        result,
        source_identity={"source": "component", "id": "ma_opt", "source_hash": "abc"},
        data_identity=_DATA_IDENTITY,
        selection_identity=make_selection_identity(),
        book_settings={"target_exposure_cap": 1.0},
        store_namespace={"kind": "local_sqlite", "name": "default"},
    )
    store.commit_candidates(
        CandidateSet.create(
            run_id=RunId("run-a"),
            candidates=rows,
            provenance={
                "schema_version": "candidate_store_provenance.v3",
                "run_id": "run-a",
                "source": _source_identity(),
                "selection_identity": make_selection_identity(),
            },
        )
    )
    return store


def _candidate(params: dict[str, object], score: float) -> EvaluatedCandidate:
    return EvaluatedCandidate(
        params=params,
        score=score,
        observation_block_metrics={"block-000": {"total_return": score}},
        metrics={"total_return": score},
    )


def _candidate_rows(data_identity: dict[str, object]) -> list[dict[str, object]]:
    fast_key = encode(
        ComponentRef("strategies", "demo.ma_cross", "strategy:demo.ma_cross"), "fast_window"
    )
    slow_key = encode(
        ComponentRef("strategies", "demo.ma_cross", "strategy:demo.ma_cross"), "slow_window"
    )
    window_key = encode(ComponentRef("indicators", "demo.mom", "demo.mom"), "window")
    winner = _candidate({fast_key: 2, slow_key: 10, window_key: 20}, 0.30)
    result = OptimizationResult(best=winner, median=winner, worst=winner)
    return candidate_rows_from_result(
        result,
        source_identity={"source": "component", "id": "ma_opt", "source_hash": "abc"},
        data_identity=data_identity,
        selection_identity=make_selection_identity(),
        book_settings={"target_exposure_cap": 1.0},
        store_namespace={"kind": "local_sqlite", "name": "default"},
    )


def _source_identity(*, drop_indicator_runtime: bool = False) -> dict[str, object]:
    """Build source provenance through the real ``component_source`` producer.

    Hand-writing the runtime shape here would be a third copy of it — producer,
    consumer, and fixture — so ``component_source`` could rename a field and leave
    this suite green while every stored Candidate diverged from what ``lock.py``
    reads. Generating it means that drift fails here first.
    """
    strategy = make_component_runtime(
        _STRATEGY_REF,
        param_keys={"fast_window": _FAST_KEY, "slow_window": _SLOW_KEY},
    )
    indicators = (
        ()
        if drop_indicator_runtime
        else (make_component_runtime(_INDICATOR_REF, param_keys={"window": _WINDOW_KEY}),)
    )
    params = {key: vbt.Param([1]) for key in (_FAST_KEY, _SLOW_KEY, _WINDOW_KEY)}
    return build_source_identity(strategy, indicators, params)
