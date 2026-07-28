"""Checks for the locked-config returns loader (``scripts/floor_evaluation.py``).

Outside the default ``testpaths`` by the boundary ``scripts/tests/README.md`` describes.
Run explicitly:

    uv run pytest scripts/tests/test_floor_evaluation.py -q

SCOPE. The loader is orchestration: it composes ``load_run_config``, the data port,
``run_pipeline_setup`` and ``build_development_paths``, and computes no statistics. So these
check the parts the module actually owns - its guards, its index normalization and its
provenance - and stub the pipeline behind it. Re-testing ``build_development_paths`` here
would duplicate ``tests/`` and couple these checks to machinery this module deliberately
reuses rather than reimplements.

The guards matter more than they look. A locked config that still carries a sweep axis, or a
replay that yields two streams, would otherwise produce *a* number silently - and a
delta-Theta-hat computed from the wrong column is indistinguishable from a right one.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pandas as pd
import pytest
import yaml

from research.aegis_research.configuration import CONFIG_SCHEMA_VERSION
from research.aegis_research.optimization.param_namespace import FIXED_CANDIDATE_PARAM
from research.aegis_research.run._stages.setup import SetupResult
from scripts import floor_evaluation
from scripts.floor_evaluation import FloorEvaluationError, load_locked_strategy_returns
from tests.support.research.aegis_research.component_fixtures import (
    write_indicator_component,
    write_strategy_component,
)
from tests.support.research.aegis_research.factories import make_run_data

LOCK_RUN_ID = "20260101T000000000000Z_run_fixture"
CANDIDATE_KEY = "cand_0123456789abcdef"


def _write_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, lock: str | None = LOCK_RUN_ID
) -> Path:
    """Write a minimal but real run config to disk, since the loader takes a path.

    Components are discovered relative to the working directory, so the fixture tree only
    resolves with the cwd moved to ``tmp_path``.
    """
    root = tmp_path / "research" / "components"
    write_indicator_component(root / "indicators" / "returns.py")
    write_strategy_component(root / "strategies" / "strategy.py")
    raw: dict[str, Any] = {
        "schema_version": CONFIG_SCHEMA_VERSION,
        "name": "run_fixture",
        "output_dir": "runs",
        "data": {
            "arrays": ["OHLCV"],
            "instruments": ["SYN.XNAS"],
            "start": "2024-01-01",
            "end": "2024-01-03",
            "timeframe": "1D",
        },
        "portfolio": {"direction": "longonly"},
        "strategy": {"id": "demo.strategy"},
        "indicators": [{"id": "demo.returns"}],
        "ranking": {"metric": "total_return"},
        "optimization": {"search": "grid", "observation_block_bars": 20},
    }
    if lock is not None:
        raw["lock"] = lock
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    return path


class _Source:
    def __init__(self, params: dict[str, Any]) -> None:
        self.params = params


def _stub_pipeline(
    monkeypatch: pytest.MonkeyPatch,
    *,
    value: pd.DataFrame,
    params: dict[str, Any] | None = None,
) -> None:
    """Stand in for everything downstream of config resolution."""
    close = pd.DataFrame({"SYN.XNAS": [1.0, 2.0]})
    monkeypatch.setattr(
        floor_evaluation,
        "load_run_data",
        lambda *a, **k: make_run_data(close=close, open_=close),
    )
    monkeypatch.setattr(
        floor_evaluation,
        "run_pipeline_setup",
        lambda **k: SetupResult(
            store_path=Path("runs/.candidate_store/candidates.sqlite3"),
            optimization_source=_Source(params or {FIXED_CANDIDATE_PARAM: [0]}),
            run_data=k["run_data"],
        ),
    )
    monkeypatch.setattr(floor_evaluation.ResolvedBook, "resolve", classmethod(lambda *a: object()))
    monkeypatch.setattr(
        floor_evaluation,
        "build_development_paths",
        lambda **k: SimpleNamespace(replay=SimpleNamespace(portfolio=object())),
    )
    monkeypatch.setattr(floor_evaluation, "_resolved_candidate_key", lambda *a: CANDIDATE_KEY)

    class _Curve:
        @staticmethod
        def from_portfolio(_pf: Any) -> Any:
            class _R:
                @staticmethod
                def returns() -> pd.DataFrame:
                    return value

            return _R()

    monkeypatch.setattr(floor_evaluation, "EquityCurve", _Curve)


def _one_stream() -> pd.DataFrame:
    index = pd.DatetimeIndex(["2024-01-02 14:30", "2024-01-03 14:30"], tz="UTC")
    return pd.DataFrame({"candidate": [0.01, -0.02]}, index=index)


def test_unlocked_config_is_rejected_before_any_data_is_loaded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unlocked config must fail fast - loading market data first would be wasted work."""

    def _fail(*_a: Any, **_k: Any) -> Any:
        raise AssertionError("market data must not load for an unlocked config")

    monkeypatch.setattr(floor_evaluation, "load_run_data", _fail)
    path = _write_config(tmp_path, monkeypatch, lock=None)

    with pytest.raises(FloorEvaluationError, match="no top-level lock"):
        load_locked_strategy_returns(path)


def test_residual_candidate_axes_are_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A config locked in name only still sweeps; its 'one stream' would be arbitrary."""
    _stub_pipeline(
        monkeypatch,
        value=_one_stream(),
        params={FIXED_CANDIDATE_PARAM: [0], "vol_target": [0.1, 0.2]},
    )
    path = _write_config(tmp_path, monkeypatch)

    with pytest.raises(FloorEvaluationError, match="still exposes Candidate axes"):
        load_locked_strategy_returns(path)


def test_multiple_return_streams_are_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two streams must raise rather than be silently squeezed to the first column."""
    index = pd.DatetimeIndex(["2024-01-02", "2024-01-03"], tz="UTC")
    two = pd.DataFrame({"a": [0.01, -0.02], "b": [0.03, 0.04]}, index=index)
    _stub_pipeline(monkeypatch, value=two)
    path = _write_config(tmp_path, monkeypatch)

    with pytest.raises(FloorEvaluationError, match="produced 2 return streams"):
        load_locked_strategy_returns(path)


def test_empty_returns_are_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """An all-NaN stream drops to empty; returning it would poison the pairing silently."""
    index = pd.DatetimeIndex(["2024-01-02", "2024-01-03"], tz="UTC")
    empty = pd.DataFrame({"candidate": [float("nan"), float("nan")]}, index=index)
    _stub_pipeline(monkeypatch, value=empty)
    path = _write_config(tmp_path, monkeypatch)

    with pytest.raises(FloorEvaluationError, match="produced no returns"):
        load_locked_strategy_returns(path)


def test_locked_config_yields_one_normalised_stream_with_provenance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The happy path: one named series, a tz-naive midnight index, and full provenance.

    The index assertion is the load-bearing one. Two poles are paired by joining on this
    index, so a surviving timezone or intraday timestamp misaligns the legs and every
    downstream statistic is computed on the wrong overlap.
    """
    _stub_pipeline(monkeypatch, value=_one_stream())
    path = _write_config(tmp_path, monkeypatch)

    loaded = load_locked_strategy_returns(path)

    assert loaded.returns.name == "run_fixture"
    assert list(loaded.returns) == [0.01, -0.02]
    assert loaded.returns.index.tz is None
    assert (loaded.returns.index == loaded.returns.index.normalize()).all()

    evidence = loaded.evidence()
    assert evidence["lock_run_id"] == LOCK_RUN_ID
    assert evidence["resolved_candidate_key"] == CANDIDATE_KEY
    assert evidence["observations"] == 2
    assert evidence["start"] == "2024-01-02"
    assert evidence["end"] == "2024-01-03"
    assert evidence["config_hash"]
