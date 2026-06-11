from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from research.aegis_research.component_registry import discover_component_registry
from research.aegis_research.configuration import (
    RunConfig,
    RunIndicatorSourceConfig,
    RunSourceRefConfig,
)
from research.aegis_research.data import MarketDataBundle
from research.aegis_research.optimization.component_source import (
    ComponentSourceError,
    build_component_optimization_source,
)
from research.aegis_research.optimization.param_namespace import (
    FIXED_CANDIDATE_PARAM,
    ComponentRef,
    encode,
)
from research.aegis_research.optimization.precompute import candidate_keys
from tests.support.research.aegis_research.factories import (
    make_portfolio_config,
    make_ranking_config,
    make_run_config,
    make_run_indicator_source_config,
    make_run_source_ref_config,
)

_INDICATOR_REF = ComponentRef("indicators", "demo.trend", "demo.trend")
_STRATEGY_REF = ComponentRef("strategies", "demo.strategy", "strategy")
_INDICATOR_WINDOW_KEY = encode(_INDICATOR_REF, "window")
_STRATEGY_THRESHOLD_KEY = encode(_STRATEGY_REF, "threshold")


def _run_pipeline(source, close, n_candidates, **param_lists):
    """Compose the source's two real stages on one slice.

    Precompute on ``close`` then simulate that window — the fused per-slice view
    the runner does not use for sweeps, exercised here through the production
    ``precompute`` -> ``simulate`` interface rather than a method on the source.
    """
    store = source.precompute(close, n_candidates, **param_lists)
    indicator_window = store.window(slice(None), candidate_keys(param_lists))
    return source.simulate(close, indicator_window, n_candidates, **param_lists)


def test_component_source_composes_indicator_and_strategy_param_spaces(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    config = _config()
    data = _data_bundle()

    source = build_component_optimization_source(config, component_registry=registry, data=data)

    assert set(source.params) == {_INDICATOR_WINDOW_KEY, _STRATEGY_THRESHOLD_KEY}
    assert source.output_name == "active"
    assert source.evidence["produced_outputs"] == ["trend"]
    assert source.evidence["consumed_outputs"] == ["trend"]

    close = data.array("Close")
    n_candidates = 1
    output = _run_pipeline(source, close, n_candidates, **_single_candidate_params())

    assert isinstance(output, pd.DataFrame)
    assert output.shape == (len(close), n_candidates * len(close.columns))
    assert output.index.equals(close.index)
    assert isinstance(output.columns, pd.MultiIndex)
    assert output.columns.names[-1] == "symbol"


def test_component_source_fixed_params_override_param_space_axes(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    config = _config(
        strategy=make_run_source_ref_config(id="demo.strategy", params={"threshold": 0.95}),
        indicators=[make_run_indicator_source_config(id="demo.trend", params={"window": 3})],
    )

    source = build_component_optimization_source(
        config,
        component_registry=registry,
        data=_data_bundle(),
    )

    assert list(source.params) == [FIXED_CANDIDATE_PARAM]
    assert source.evidence["fixed_candidate_param"] == FIXED_CANDIDATE_PARAM
    assert source.evidence["strategy"]["param_mode"] == "fixed"
    assert source.evidence["indicators"][0]["param_mode"] == "fixed"


def test_component_source_uses_resolved_locked_params_as_constants(tmp_path: Path) -> None:
    # ADR-0006: a top-level Lock drives force_locked, fixing every Component's params from
    # the reproduced Candidate. There is no per-Component lock reference any more.
    registry = _registry(tmp_path)
    config = _config(
        indicators=[make_run_indicator_source_config(id="demo.trend")],
    )
    resolved = {
        _STRATEGY_REF: {"threshold": 0.95},
        _INDICATOR_REF: {"window": 3},
    }

    source = build_component_optimization_source(
        config,
        component_registry=registry,
        data=_data_bundle(),
        resolved_component_params=resolved,
        force_locked=True,
    )

    assert _INDICATOR_WINDOW_KEY not in source.params
    assert source.evidence["indicators"][0]["param_mode"] == "locked"
    assert source.evidence["indicators"][0]["fixed_params"] == {"window": 3}
    assert source.evidence["strategy"]["param_mode"] == "locked"


def test_component_source_rejects_unresolved_lock_refs(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    config = _config(
        indicators=[make_run_indicator_source_config(id="demo.trend")],
    )

    with pytest.raises(ComponentSourceError, match="requires resolved"):
        build_component_optimization_source(
            config, component_registry=registry, data=_data_bundle(), force_locked=True
        )


def test_component_source_rejects_hidden_param_space_axes(tmp_path: Path) -> None:
    root = tmp_path / "research" / "components"
    _write_hidden_strategy(root / "strategies" / "hidden_strategy.py")
    registry = discover_component_registry(root=root, repo_root=tmp_path)
    config = _config(
        strategy=make_run_source_ref_config(id="demo.hidden_strategy"),
        indicators=[],
    )

    with pytest.raises(ComponentSourceError, match="hide=True"):
        build_component_optimization_source(
            config, component_registry=registry, data=_data_bundle()
        )


def test_component_source_rejects_duplicate_produced_outputs(tmp_path: Path) -> None:
    root = _write_components(tmp_path)
    _write_indicator(root / "indicators" / "trend_copy.py", component_id="demo.trend_copy")
    registry = discover_component_registry(root=root, repo_root=tmp_path)
    config = _config(
        indicators=[
            make_run_indicator_source_config(id="demo.trend"),
            make_run_indicator_source_config(id="demo.trend_copy"),
        ],
    )

    with pytest.raises(ComponentSourceError, match="produced by both"):
        build_component_optimization_source(
            config, component_registry=registry, data=_data_bundle()
        )


def test_indicator_batched_callable_must_return_mapping(tmp_path: Path) -> None:
    root = tmp_path / "research" / "components"
    _write_indicator_template(
        root / "indicators" / "trend.py",
        return_expression="result",
    )
    _write_strategy_template(root / "strategies" / "strategy.py")
    registry = discover_component_registry(root=root, repo_root=tmp_path)
    source = build_component_optimization_source(
        _config(), component_registry=registry, data=_data_bundle()
    )
    with pytest.raises(ComponentSourceError, match=r"indicator 'demo.trend'.*mapping"):
        source.precompute(
            _data_bundle().array("Close"),
            1,
            **_single_candidate_params(),
        )


@pytest.mark.parametrize(
    ("return_expression", "match"),
    [
        ("{}", r"indicator 'demo.trend'.*missing=\['trend'\].*unknown=\[\]"),
        (
            "{'trend': result, 'other': result}",
            r"indicator 'demo.trend'.*missing=\[\].*unknown=\['other'\]",
        ),
    ],
)
def test_indicator_mapping_keys_must_match_manifest_outputs(
    tmp_path: Path, return_expression: str, match: str
) -> None:
    root = tmp_path / "research" / "components"
    _write_indicator_template(
        root / "indicators" / "trend.py",
        return_expression=return_expression,
    )
    _write_strategy_template(root / "strategies" / "strategy.py")
    registry = discover_component_registry(root=root, repo_root=tmp_path)
    source = build_component_optimization_source(
        _config(), component_registry=registry, data=_data_bundle()
    )

    with pytest.raises(ComponentSourceError, match=match):
        source.precompute(
            _data_bundle().array("Close"),
            1,
            **_single_candidate_params(),
        )


def test_two_output_indicator_outputs_remain_distinct_for_strategy(tmp_path: Path) -> None:
    root = tmp_path / "research" / "components"
    _write_two_output_indicator(root / "indicators" / "trend.py")
    _write_two_output_strategy(root / "strategies" / "strategy.py")
    registry = discover_component_registry(root=root, repo_root=tmp_path)
    source = build_component_optimization_source(
        _config(),
        component_registry=registry,
        data=_data_bundle(),
    )
    close = _data_bundle().array("Close")

    store = source.precompute(close, 1, **_single_candidate_params())

    assert set(store.outputs) == {"trend", "inverse_trend"}
    assert not np.array_equal(
        store.outputs["trend"], store.outputs["inverse_trend"], equal_nan=True
    )

    result = _run_pipeline(source, close, 1, **_single_candidate_params())

    np.testing.assert_array_equal(result.to_numpy(), np.ones_like(result.to_numpy()))


@pytest.mark.parametrize(
    ("return_expression", "match"),
    [
        (
            "{'trend': result[:-1]}",
            r"component indicators/demo.trend.*expected shape \(6, 1\).*actual shape \(5, 1\)",
        ),
        (
            "{'trend': np.concatenate([result, result], axis=1)}",
            r"component indicators/demo.trend.*expected shape \(6, 1\).*actual shape \(6, 2\)",
        ),
    ],
)
def test_indicator_output_shape_gate_rejects_wrong_rows_and_columns(
    tmp_path: Path, return_expression: str, match: str
) -> None:
    root = tmp_path / "research" / "components"
    _write_indicator_template(root / "indicators" / "trend.py", return_expression=return_expression)
    _write_strategy_template(root / "strategies" / "strategy.py")
    registry = discover_component_registry(root=root, repo_root=tmp_path)
    source = build_component_optimization_source(
        _config(), component_registry=registry, data=_data_bundle()
    )

    with pytest.raises(ComponentSourceError, match=match):
        source.precompute(
            _data_bundle().array("Close"),
            1,
            **_single_candidate_params(),
        )


@pytest.mark.parametrize(
    ("return_expression", "match"),
    [
        (
            "alloc[:-1]",
            r"component strategies/demo.strategy.*expected shape \(6, 1\).*actual shape \(5, 1\)",
        ),
        (
            "np.concatenate([alloc, alloc], axis=1)",
            r"component strategies/demo.strategy.*expected shape \(6, 1\).*actual shape \(6, 2\)",
        ),
    ],
)
def test_strategy_allocation_shape_gate_rejects_wrong_rows_and_columns(
    tmp_path: Path, return_expression: str, match: str
) -> None:
    root = tmp_path / "research" / "components"
    _write_indicator_template(root / "indicators" / "trend.py")
    _write_strategy_template(root / "strategies" / "strategy.py", return_expression=return_expression)
    registry = discover_component_registry(root=root, repo_root=tmp_path)
    source = build_component_optimization_source(
        _config(), component_registry=registry, data=_data_bundle()
    )
    close = _data_bundle().array("Close")

    with pytest.raises(ComponentSourceError, match=match):
        _run_pipeline(source, close, 1, **_single_candidate_params())


def test_component_optimization_source_schema_version_is_v2(tmp_path: Path) -> None:
    source = build_component_optimization_source(
        _config(),
        component_registry=_registry(tmp_path),
        data=_data_bundle(),
    )

    assert source.evidence["schema_version"] == "component_optimization_source.v2"
    assert source.diagnostics["schema_version"] == "component_optimization_source.v2"
    assert source.metadata["schema_version"] == "component_optimization_source.v2"


def _single_candidate_params() -> dict[str, list[object]]:
    return {
        _INDICATOR_WINDOW_KEY: [2],
        _STRATEGY_THRESHOLD_KEY: [0.95],
    }


def _config(
    *,
    strategy: RunSourceRefConfig | None = None,
    indicators: list[RunIndicatorSourceConfig] | None = None,
) -> RunConfig:
    return make_run_config(
        name="component_source",
        strategy=strategy or make_run_source_ref_config(id="demo.strategy"),
        indicators=indicators
        if indicators is not None
        else [make_run_indicator_source_config(id="demo.trend")],
        ranking=make_ranking_config(metric="total_return"),
        portfolio=make_portfolio_config(direction="longonly"),
    )


def _registry(tmp_path: Path):
    root = _write_components(tmp_path)
    return discover_component_registry(root=root, repo_root=tmp_path)


def _write_components(tmp_path: Path) -> Path:
    root = tmp_path / "research" / "components"
    _write_indicator(root / "indicators" / "trend.py", component_id="demo.trend")
    _write_strategy(root / "strategies" / "strategy.py")
    return root


def _write_indicator(path: Path, *, component_id: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# %% component overview\n"
        "# Parameterized indicator fixture.\n"
        "# %% define component metadata\n"
        "import numpy as np\n"
        "from vectorbtpro import vbt\n"
        "COMPONENT_MANIFEST = {"
        f"'family': 'indicators', 'id': {component_id!r}, 'version': '1.0.0', "
        "'input_names': ['Close'], 'param_names': ['window'], "
        "'output_names': ['trend'], 'defaults': {'window': 2}, "
        "}\n"
        "# %% parameter space\n"
        "def param_space():\n"
        "    return {'window': vbt.Param([2, 3])}\n"
        "# %% main compute\n"
        "def run(data, window):\n"
        "    '''Return a rolling trend frame.'''\n"
        "    close = data.array('Close')\n"
        "    return close.rolling(int(window), min_periods=1).mean()\n"
        "# %% batched compute\n"
        "def run(data, *, n_candidates, **param_lists):\n"
        "    '''Return indicator output.'''\n"
        "    close = data.array('Close')\n"
        "    T, S = close.shape\n"
        "    windows = param_lists['window']\n"
        "    result = np.zeros((T, n_candidates * S))\n"
        "    for i, w in enumerate(windows):\n"
        "        cols = slice(i * S, (i + 1) * S)\n"
        "        result[:, cols] = close.rolling(int(w), min_periods=1).mean().values\n"
        "    return {'trend': result}\n"
    )


def _write_strategy(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# %% component overview\n"
        "# Parameterized strategy fixture.\n"
        "# %% define component metadata\n"
        "import numpy as np\n"
        "import pandas as pd\n"
        "from vectorbtpro import vbt\n"
        "COMPONENT_MANIFEST = {"
        "'family': 'strategies', 'id': 'demo.strategy', 'version': '1.0.0', "
        "'input_names': ['Close'], 'param_names': ['threshold'], "
        "'output_name': 'active', 'consumes_outputs': ['trend'], "
        "'defaults': {'threshold': 1.0}, "
        "}\n"
        "# %% parameter space\n"
        "def param_space():\n"
        "    return {'threshold': vbt.Param([0.95, 1.0])}\n"
        "# %% main compute\n"
        "def run(inputs, threshold):\n"
        "    '''Return active allocation derived from thresholded trend signals.'''\n"
        "    close = inputs.data.array('Close')\n"
        "    trend = inputs.indicators['trend']\n"
        "    selected = trend.ge(close * float(threshold)).fillna(False)\n"
        "    active = pd.DataFrame(np.nan, index=close.index, columns=close.columns, dtype=object)\n"
        "    active.loc[:] = selected.astype(object)\n"
        "    return active\n"
        "# %% batched compute\n"
        "def run(inputs, *, n_candidates, **param_lists):\n"
        "    '''Return strategy output.'''\n"
        "    close = inputs.data.array('Close')\n"
        "    T, S = close.shape\n"
        "    thresholds = param_lists['threshold']\n"
        "    trend_arr = inputs.indicators['trend']\n"
        "    close_arr = close.values\n"
        "    alloc = np.full((T, n_candidates * S), np.nan)\n"
        "    for i, thr in enumerate(thresholds):\n"
        "        cols = slice(i * S, (i + 1) * S)\n"
        "        trend_slice = trend_arr[:, cols]\n"
        "        selected = trend_slice >= (close_arr * float(thr))\n"
        "        n_sel = selected.sum(axis=1, keepdims=True).clip(min=1)\n"
        "        alloc[:, cols] = np.where(selected, 1.0 / n_sel, 0.0)\n"
        "    return alloc\n"
    )


def _write_hidden_strategy(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# %% component overview\n"
        "# Hidden parameter strategy fixture.\n"
        "# %% define component metadata\n"
        "import numpy as np\n"
        "import pandas as pd\n"
        "from vectorbtpro import vbt\n"
        "COMPONENT_MANIFEST = {"
        "'family': 'strategies', 'id': 'demo.hidden_strategy', 'version': '1.0.0', "
        "'input_names': ['Close'], 'param_names': ['threshold'], "
        "'output_name': 'active', 'defaults': {'threshold': 1.0}, "
        "}\n"
        "# %% parameter space\n"
        "def param_space():\n"
        "    return {'threshold': vbt.Param([0.95, 1.0], hide=True)}\n"
        "# %% main compute\n"
        "def run(inputs, threshold):\n"
        "    '''Return active allocation for the hidden-param fixture.'''\n"
        "    close = inputs.data.array('Close')\n"
        "    selected = close.gt(close.shift(1)).fillna(False)\n"
        "    active = pd.DataFrame(np.nan, index=close.index, columns=close.columns, dtype=object)\n"
        "    active.loc[:] = selected.astype(object)\n"
        "    return active\n"
        "# %% batched compute\n"
        "def run(inputs, *, n_candidates, **param_lists):\n"
        "    '''Return strategy output for the hidden-param fixture.'''\n"
        "    close = inputs.data.array('Close')\n"
        "    T, S = close.shape\n"
        "    close_arr = close.values\n"
        "    alloc = np.full((T, n_candidates * S), np.nan)\n"
        "    for i in range(n_candidates):\n"
        "        cols = slice(i * S, (i + 1) * S)\n"
        "        prev = np.roll(close_arr, 1, axis=0)\n"
        "        prev[0] = np.nan\n"
        "        selected = close_arr > prev\n"
        "        n_sel = selected.sum(axis=1, keepdims=True).clip(min=1)\n"
        "        alloc[:, cols] = np.where(selected, 1.0 / n_sel, 0.0)\n"
        "    return alloc\n"
    )


def test_component_source_pipeline_returns_multiindex_frame(tmp_path: Path) -> None:
    root = tmp_path / "research" / "components"
    _write_indicator_template(root / "indicators" / "trend.py")
    _write_strategy_template(root / "strategies" / "strategy.py")
    registry = discover_component_registry(root=root, repo_root=tmp_path)
    config = _config()
    data = _data_bundle()

    source = build_component_optimization_source(config, component_registry=registry, data=data)
    close = data.array("Close")
    n_candidates = 2
    n_symbols = len(close.columns)

    result = _run_pipeline(
        source,
        close,
        n_candidates,
        **{_INDICATOR_WINDOW_KEY: [2, 3], _STRATEGY_THRESHOLD_KEY: [0.95, 1.0]},
    )

    assert isinstance(result, pd.DataFrame)
    assert result.shape == (len(close), n_candidates * n_symbols)
    assert isinstance(result.columns, pd.MultiIndex)
    assert result.columns.names[-1] == "symbol"
    assert result.index.equals(close.index)


def test_component_precompute_deduplicates_indicator_params_with_window_parity(
    tmp_path: Path,
) -> None:
    root = tmp_path / "research" / "components"
    _write_indicator_template(root / "indicators" / "trend.py")
    _write_strategy_template(root / "strategies" / "strategy.py")
    registry = discover_component_registry(root=root, repo_root=tmp_path)
    data = _data_bundle()
    source = build_component_optimization_source(_config(), component_registry=registry, data=data)
    close = data.array("Close")

    param_lists = {
        _INDICATOR_WINDOW_KEY: [2, 2, 3, 3],
        _STRATEGY_THRESHOLD_KEY: [0.95, 1.0, 0.95, 1.0],
    }

    store = source.precompute(close, 4, **param_lists)

    # Four full candidates collapse to two unique indicator parameter tuples.
    n_symbols = len(close.columns)
    assert store.outputs["trend"].shape == (len(close), 2 * n_symbols)

    # The store still expands the deduped indicator blocks back to candidate-major
    # order when a simulation window asks for all four full candidate keys.
    indicator_window = store.window(slice(None), candidate_keys(param_lists))
    roll2 = close.rolling(2, min_periods=1).mean().to_numpy()
    roll3 = close.rolling(3, min_periods=1).mean().to_numpy()
    expected = np.concatenate([roll2, roll2, roll3, roll3], axis=1)
    np.testing.assert_array_equal(indicator_window["trend"], expected)

    result = source.simulate(close, indicator_window, 4, **param_lists)

    assert result.shape == (len(close), 4 * n_symbols)
    assert isinstance(result.columns, pd.MultiIndex)


def _write_two_output_indicator(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# %% component overview\n"
        "# Two-output indicator fixture.\n"
        "# %% define component metadata\n"
        "import numpy as np\n"
        "from vectorbtpro import vbt\n"
        "COMPONENT_MANIFEST = {"
        "'family': 'indicators', 'id': 'demo.trend', 'version': '1.0.0', "
        "'input_names': ['Close'], 'param_names': ['window'], "
        "'output_names': ['trend', 'inverse_trend'], 'defaults': {'window': 2}, "
        "}\n"
        "# %% parameter space\n"
        "def param_space():\n"
        "    return {'window': vbt.Param([2, 3])}\n"
        "# %% main compute\n"
        "def run(data, window):\n"
        "    '''Return trend and inverse trend frames.'''\n"
        "    close = data.array('Close')\n"
        "    trend = close.rolling(int(window), min_periods=1).mean()\n"
        "    return {'trend': trend, 'inverse_trend': -trend}\n"
        "# %% batched compute\n"
        "def run(data, *, n_candidates, **param_lists):\n"
        "    '''Return two distinct indicator outputs.'''\n"
        "    close = data.array('Close')\n"
        "    T, S = close.shape\n"
        "    result = np.zeros((T, n_candidates * S))\n"
        "    for i, w in enumerate(param_lists['window']):\n"
        "        cols = slice(i * S, (i + 1) * S)\n"
        "        result[:, cols] = close.rolling(int(w), min_periods=1).mean().values\n"
        "    return {'trend': result, 'inverse_trend': -result}\n"
    )


def _write_two_output_strategy(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# %% component overview\n"
        "# Strategy consuming two indicator outputs.\n"
        "# %% define component metadata\n"
        "import numpy as np\n"
        "import pandas as pd\n"
        "from vectorbtpro import vbt\n"
        "COMPONENT_MANIFEST = {"
        "'family': 'strategies', 'id': 'demo.strategy', 'version': '1.0.0', "
        "'input_names': ['Close'], 'param_names': ['threshold'], "
        "'output_name': 'active', 'consumes_outputs': ['trend', 'inverse_trend'], "
        "'defaults': {'threshold': 1.0}, "
        "}\n"
        "# %% parameter space\n"
        "def param_space():\n"
        "    return {'threshold': vbt.Param([0.95, 1.0])}\n"
        "# %% main compute\n"
        "def run(inputs, threshold):\n"
        "    '''Return active allocation when trend exceeds inverse trend.'''\n"
        "    close = inputs.data.array('Close')\n"
        "    return pd.DataFrame(1.0, index=close.index, columns=close.columns)\n"
        "# %% batched compute\n"
        "def run(inputs, *, n_candidates, **param_lists):\n"
        "    '''Use both outputs so aliasing changes the result.'''\n"
        "    trend = inputs.indicators['trend']\n"
        "    inverse = inputs.indicators['inverse_trend']\n"
        "    return np.where(trend > inverse, 1.0, 0.0)\n"
    )


def _data_bundle() -> MarketDataBundle:
    index = pd.date_range("2026-01-01", periods=6, freq="1D")
    close = pd.DataFrame({"SYN": [10.0, 11.0, 10.5, 12.0, 11.5, 13.0]}, index=index)
    return MarketDataBundle(arrays={"Close": close})


def _write_indicator_template(
    path: Path,
    *,
    return_expression: str = "{'trend': result}",
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# %% component overview\n"
        "# Parameterized indicator fixture with callable.\n"
        "# %% define component metadata\n"
        "import numpy as np\n"
        "from vectorbtpro import vbt\n"
        "COMPONENT_MANIFEST = {"
        "'family': 'indicators', 'id': 'demo.trend', 'version': '1.0.0', "
        "'input_names': ['Close'], 'param_names': ['window'], "
        "'output_names': ['trend'], 'defaults': {'window': 2}, "
        "}\n"
        "# %% parameter space\n"
        "def param_space():\n"
        "    return {'window': vbt.Param([2, 3])}\n"
        "# %% main compute\n"
        "def run(data, window):\n"
        "    '''Return a rolling trend frame.'''\n"
        "    close = data.array('Close')\n"
        "    return close.rolling(int(window), min_periods=1).mean()\n"
        "# %% batched compute\n"
        "def run(data, *, n_candidates, **param_lists):\n"
        "    '''Return indicator output.'''\n"
        "    close = data.array('Close')\n"
        "    T, S = close.shape\n"
        "    windows = param_lists['window']\n"
        "    result = np.zeros((T, n_candidates * S))\n"
        "    for i, w in enumerate(windows):\n"
        "        cols = slice(i * S, (i + 1) * S)\n"
        "        result[:, cols] = close.rolling(int(w), min_periods=1).mean().values\n"
        f"    return {return_expression}\n"
    )


def _write_strategy_template(
    path: Path,
    *,
    return_expression: str = "alloc",
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# %% component overview\n"
        "# Parameterized strategy fixture with callable.\n"
        "# %% define component metadata\n"
        "import numpy as np\n"
        "import pandas as pd\n"
        "from vectorbtpro import vbt\n"
        "COMPONENT_MANIFEST = {"
        "'family': 'strategies', 'id': 'demo.strategy', 'version': '1.0.0', "
        "'input_names': ['Close'], 'param_names': ['threshold'], "
        "'output_name': 'active', 'consumes_outputs': ['trend'], "
        "'defaults': {'threshold': 1.0}, "
        "}\n"
        "# %% parameter space\n"
        "def param_space():\n"
        "    return {'threshold': vbt.Param([0.95, 1.0])}\n"
        "# %% main compute\n"
        "def run(inputs, threshold):\n"
        "    '''Return active allocation derived from thresholded trend signals.'''\n"
        "    close = inputs.data.array('Close')\n"
        "    trend = inputs.indicators['trend']\n"
        "    selected = trend.ge(close * float(threshold)).fillna(False)\n"
        "    active = pd.DataFrame(np.nan, index=close.index, columns=close.columns, dtype=object)\n"
        "    active.loc[:] = selected.astype(object)\n"
        "    return active\n"
        "# %% batched compute\n"
        "def run(inputs, *, n_candidates, **param_lists):\n"
        "    '''Return strategy output.'''\n"
        "    import numpy as np, pandas as pd\n"
        "    close = inputs.data.array('Close')\n"
        "    T, S = close.shape\n"
        "    thresholds = param_lists['threshold']\n"
        "    trend_arr = inputs.indicators['trend']\n"
        "    close_arr = close.values\n"
        "    alloc = np.full((T, n_candidates * S), np.nan)\n"
        "    for i, thr in enumerate(thresholds):\n"
        "        cols = slice(i * S, (i + 1) * S)\n"
        "        trend_slice = trend_arr[:, cols]\n"
        "        selected = trend_slice >= (close_arr * float(thr))\n"
        "        n_sel = selected.sum(axis=1, keepdims=True).clip(min=1)\n"
        "        alloc[:, cols] = np.where(selected, 1.0 / n_sel, 0.0)\n"
        f"    return {return_expression}\n"
    )
