"""Self-consistency oracle: batch-vs-single equality for every fixture Component.

ADR-0017: ``run`` over the full candidate batch must equal stitching ``run``
invoked per single-candidate batch.  Bitwise NaN-aware equality — no tolerance.
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest
from nautilus_trader.model.identifiers import InstrumentId

from research.aegis_research.component_registry import (
    FrozenComponentRegistry,
    discover_component_registry,
)
from research.aegis_research.data import MarketDataBundle
from research.aegis_research.optimization.component_source import ComponentStrategyInputs

# ── Instrument IDs that satisfy tests.momentum_rotator's sleeve constants ──
_MOMENTUM_ROTATOR_INSTRUMENT_IDS = [
    InstrumentId.from_str(value)
    for value in (
        "SPY.XNAS",
        "IWM.XNAS",
        "EEM.XNAS",
        "TLT.XNAS",
        "GLD.XNAS",
        "DBC.XNAS",
        "VNQ.XNAS",
        "UUP.XNAS",
        "XLE.XNAS",
        "XLU.XNAS",
    )
]

_N_BARS = 100
_N_CANDIDATES = 3


# ── Registry built from fixture components ────────────────────────────────


def _fixture_component_root() -> Path:
    this_file = Path(__file__).resolve()
    # tests/unit/research/aegis_research/ -> go up to repo/worktree root
    # parents[0]=aegis_research, [1]=research, [2]=unit, [3]=tests, [4]=repo-root
    repo = this_file.parents[4]
    return repo / "tests" / "fixtures" / "components"


def _fixture_registry() -> FrozenComponentRegistry:
    root = _fixture_component_root()
    return discover_component_registry(root=root, repo_root=root.parent.parent)


_FIXTURE_REGISTRY = _fixture_registry()


def _fixture_component_ids() -> list[Any]:
    """Parametrise entries so each Component is one test case."""
    params: list[Any] = []
    for family in ("indicators", "strategies"):
        for comp_id in _FIXTURE_REGISTRY.ids(family):
            defn = _FIXTURE_REGISTRY.definitions[family][comp_id]
            params.append(pytest.param(defn, id=f"{family}/{comp_id}"))
    return params


# ── Synthetic data ────────────────────────────────────────────────────────


def _make_data(
    n_dates: int = _N_BARS,
    instrument_ids: list[InstrumentId] | None = None,
    seed: int = 42,
) -> MarketDataBundle:
    instrument_ids = instrument_ids or _MOMENTUM_ROTATOR_INSTRUMENT_IDS
    dates = pd.date_range("2023-01-01", periods=n_dates, freq="D")
    rng = np.random.default_rng(seed)
    returns = rng.normal(0.0003, 0.012, size=(n_dates, len(instrument_ids)))
    prices = 100.0 * np.exp(np.cumsum(returns, axis=0))
    close = pd.DataFrame(
        prices,
        index=dates,
        columns=pd.Index(instrument_ids, name="instrument_id"),
    )
    return MarketDataBundle(arrays={"Close": close})


# ── Parameter generators per component ────────────────────────────────────


def _param_lists_for(definition: Any) -> dict[str, list[Any]]:
    """Return a dict of param_name -> list[value] with _N_CANDIDATES entries."""
    comp_id = definition.id

    if comp_id == "tests.momentum_score":
        return {
            "h1": [10, 15, 21],
            "h2": [20, 30, 42],
            "h3": [40, 60, 84],
            "h4": [60, 80, 100],
            "w1": [12.0, 8.0, 16.0],
            "w2": [4.0, 2.0, 6.0],
            "w3": [2.0, 1.0, 3.0],
            "w4": [1.0, 0.5, 2.0],
        }
    if comp_id == "tests.realized_vol":
        return {"window": [10, 20, 30]}
    if comp_id == "tests.momentum_rotator":
        return {
            "top_n": [2, 3, 4],
            "top_k_defensive": [1, 2, 1],
            "tau": [0.0, 0.0, 0.0],
        }
    raise ValueError(f"Unknown fixture component: {comp_id}")


# ── Oracle core ───────────────────────────────────────────────────────────


def _assert_indicator_batch_equals_stitched(
    definition: Any,
    data: MarketDataBundle,
    n_candidates: int,
    param_lists: dict[str, list[Any]],
) -> None:
    """Assert an indicator's batched ``run`` equals its stitched single-candidate runs."""
    run = definition.load_callable()
    close = data.array("Close")
    T, S = close.shape

    batch = run(data, n_candidates=n_candidates, **param_lists)
    assert isinstance(batch, dict), (
        f"Indicator {definition.id}: expected mapping, got {type(batch).__name__}"
    )

    # Stitch single-candidate results
    stitched: dict[str, np.ndarray] = {
        name: np.full((T, n_candidates * S), np.nan) for name in batch
    }
    for i in range(n_candidates):
        single_params = {k: [v[i]] for k, v in param_lists.items()}
        single = run(data, n_candidates=1, **single_params)
        assert isinstance(single, dict), (
            f"Indicator {definition.id} single-candidate: expected mapping, "
            f"got {type(single).__name__}"
        )
        for name, arr in single.items():
            stitched[name][:, i * S : (i + 1) * S] = arr

    for name in batch:
        assert np.array_equal(batch[name], stitched[name], equal_nan=True), (
            f"Indicator {definition.id!r} output {name!r}: batch != stitched single-candidate"
        )


def _find_producer(output_name: str, registry: FrozenComponentRegistry) -> Any:
    """Return the ComponentDefinition for the indicator that produces *output_name*."""
    for ind_id in registry.ids("indicators"):
        ind_def = registry.definitions["indicators"][ind_id]
        if output_name in ind_def.produced_output_names():
            return ind_def
    raise ValueError(f"No indicator produces output {output_name!r}")


def _assert_strategy_batch_equals_stitched(
    definition: Any,
    data: MarketDataBundle,
    registry: FrozenComponentRegistry,
    n_candidates: int,
    param_lists: dict[str, list[Any]],
) -> None:
    """Assert a strategy's batched ``run`` equals its stitched single-candidate runs.

    Indicator outputs consumed by the strategy are pre-computed in batch mode.
    """
    close = data.array("Close")
    S = len(close.columns)
    T = len(close)

    # Pre-compute indicator outputs (batched, one call per indicator).
    indicator_outputs: dict[str, np.ndarray] = {}
    for output_name in definition.consumed_output_names():
        producer = _find_producer(output_name, registry)
        producer_run = producer.load_callable()
        producer_params = _param_lists_for(producer)
        producer_result = producer_run(data, n_candidates=n_candidates, **producer_params)
        indicator_outputs[output_name] = producer_result[output_name]

    run = definition.load_callable()

    batch_inputs = ComponentStrategyInputs(
        data=data,
        indicators=indicator_outputs,
        n_candidates=n_candidates,
        n_symbols=S,
        metadata={},
    )
    batch = np.asarray(run(batch_inputs, n_candidates=n_candidates, **param_lists))

    stitched = np.full((T, n_candidates * S), np.nan)
    for i in range(n_candidates):
        single_indicators = {
            name: arr[:, i * S : (i + 1) * S] for name, arr in indicator_outputs.items()
        }
        single_inputs = ComponentStrategyInputs(
            data=data,
            indicators=single_indicators,
            n_candidates=1,
            n_symbols=S,
            metadata={},
        )
        single_params = {k: [v[i]] for k, v in param_lists.items()}
        single_arr = np.asarray(run(single_inputs, n_candidates=1, **single_params))
        stitched[:, i * S : (i + 1) * S] = single_arr

    assert np.array_equal(batch, stitched, equal_nan=True), (
        f"Strategy {definition.id!r}: batch != stitched single-candidate"
    )


# ── Parametrised test ─────────────────────────────────────────────────────


@pytest.mark.parametrize("definition", _fixture_component_ids())
def test_fixture_component_is_batch_self_consistent(definition: Any) -> None:
    """Every fixture Component: batch ``run`` == stitched single-candidate ``run``."""
    data = _make_data()
    param_lists = _param_lists_for(definition)
    n_candidates = _N_CANDIDATES

    if definition.family == "indicators":
        _assert_indicator_batch_equals_stitched(definition, data, n_candidates, param_lists)
    else:
        _assert_strategy_batch_equals_stitched(
            definition, data, _FIXTURE_REGISTRY, n_candidates, param_lists
        )


# ── Batch-dependent toy component (contract enforcement proof) ─────────────

_TOY_BATCH_DEPENDENT_SOURCE = textwrap.dedent('''\
    # %% component overview
    # Deliberately batch-dependent indicator -- divides by n_candidates.
    # %% imports
    import numpy as np
    # %% define component metadata
    COMPONENT_MANIFEST = {
        "family": "indicators",
        "id": "toy.batch_dependent",
        "version": "1.0.0",
        "input_names": ["Close"],
        "param_names": [],
        "output_names": ["batch_norm"],
        "defaults": {},
    }
    # %% main compute
    def run(data, *, n_candidates, **param_lists):
        """Return batch-dependent normalized close, dividing by n_candidates."""
        close = data.array("Close")
        T, S = close.shape
        values = close.values
        result = np.full((T, n_candidates * S), np.nan)
        for ci in range(n_candidates):
            cols = slice(ci * S, (ci + 1) * S)
            # BATCH-DEPENDENT: divides by n_candidates
            result[:, cols] = values / n_candidates
        return {"batch_norm": result}
    ''')


def _setup_batch_dependent(
    tmp_path: Path,
) -> tuple[Any, MarketDataBundle]:
    """Write toy batch-dependent Component to *tmp_path* and return (definition, data)."""
    comp_path = tmp_path / "components" / "indicators" / "toy_batch_dependent.py"
    comp_path.parent.mkdir(parents=True, exist_ok=True)
    comp_path.write_text(_TOY_BATCH_DEPENDENT_SOURCE)

    registry = discover_component_registry(root=tmp_path / "components", repo_root=tmp_path)
    defin = registry.definitions["indicators"]["toy.batch_dependent"]
    data = _make_data(
        n_dates=20,
        instrument_ids=[
            InstrumentId.from_str("A.XNAS"),
            InstrumentId.from_str("B.XNAS"),
        ],
        seed=1,
    )
    return defin, data


def test_batch_dependent_component_fails_oracle(tmp_path: Path) -> None:
    """A deliberately batch-dependent Component must fail the oracle.

    This proves the contract is enforceable, not vacuous.
    """
    defin, data = _setup_batch_dependent(tmp_path)
    with pytest.raises(AssertionError, match="batch != stitched"):
        _assert_indicator_batch_equals_stitched(defin, data, n_candidates=3, param_lists={})


def test_batch_dependent_component_single_candidate_passes_trivially(
    tmp_path: Path,
) -> None:
    """n_candidates=1 is the degenerate case — must always pass."""
    defin, data = _setup_batch_dependent(tmp_path)
    _assert_indicator_batch_equals_stitched(defin, data, n_candidates=1, param_lists={})
