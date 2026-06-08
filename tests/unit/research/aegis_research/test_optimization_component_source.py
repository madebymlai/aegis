from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from research.aegis_research.component_registry import discover_component_registry
from research.aegis_research.config import (
    PortfolioConfig,
    RankingConfig,
    RunConfig,
    RunIndicatorSourceConfig,
    RunSourceRefConfig,
)
from research.aegis_research.data import MarketDataBundle
from research.aegis_research.optimization.component_source import (
    FIXED_CANDIDATE_PARAM,
    ComponentSourceError,
    build_component_optimization_source,
    component_param_key,
    component_param_slices,
    component_ref_key,
    parse_component_param_key,
)
from research.aegis_research.optimization.precompute import candidate_keys


def test_component_source_composes_indicator_and_strategy_param_spaces(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    config = _config()
    data = _data_bundle()

    source = build_component_optimization_source(config, component_registry=registry, data=data)

    indicator_key = component_param_key("indicators", "demo.trend", "demo.trend", "window")
    strategy_key = component_param_key("strategies", "demo.strategy", "strategy", "threshold")
    assert set(source.params) == {indicator_key, strategy_key}
    assert source.output_name == "active"
    assert source.evidence["produced_outputs"] == ["trend"]
    assert source.evidence["consumed_outputs"] == ["trend"]

    close = data.feature("Close")
    n_candidates = 1
    output = source.pipeline(
        close, n_candidates, **{indicator_key: [2], strategy_key: [0.95]}
    )

    assert isinstance(output, pd.DataFrame)
    assert output.shape == (len(close), n_candidates * len(close.columns))
    assert output.index.equals(close.index)
    assert isinstance(output.columns, pd.MultiIndex)
    assert output.columns.names[-1] == "symbol"


def test_component_source_fixed_params_override_param_space_axes(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    config = _config(
        strategy=RunSourceRefConfig(id="demo.strategy", params={"threshold": 0.95}),
        indicators=[RunIndicatorSourceConfig(id="demo.trend", params={"window": 3})],
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
        indicators=[RunIndicatorSourceConfig(id="demo.trend")],
    )
    resolved = {
        component_ref_key("strategies", "demo.strategy", "strategy"): {"threshold": 0.95},
        component_ref_key("indicators", "demo.trend", "demo.trend"): {"window": 3},
    }

    source = build_component_optimization_source(
        config,
        component_registry=registry,
        data=_data_bundle(),
        resolved_component_params=resolved,
        force_locked=True,
    )

    indicator_key = component_param_key("indicators", "demo.trend", "demo.trend", "window")

    assert indicator_key not in source.params
    assert source.evidence["indicators"][0]["param_mode"] == "locked"
    assert source.evidence["indicators"][0]["fixed_params"] == {"window": 3}
    assert source.evidence["strategy"]["param_mode"] == "locked"


def test_component_source_rejects_unresolved_lock_refs(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    config = _config(
        indicators=[RunIndicatorSourceConfig(id="demo.trend")],
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
        strategy=RunSourceRefConfig(id="demo.hidden_strategy"),
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
            RunIndicatorSourceConfig(id="demo.trend"),
            RunIndicatorSourceConfig(id="demo.trend_copy"),
        ],
    )

    with pytest.raises(ComponentSourceError, match="produced by both"):
        build_component_optimization_source(
            config, component_registry=registry, data=_data_bundle()
        )


def test_component_param_keys_round_trip_to_component_slices() -> None:
    key = component_param_key("indicators", "demo.trend", "demo.trend", "window")

    assert parse_component_param_key(key) == {
        "family": "indicators",
        "component_id": "demo.trend",
        "slot": "demo.trend",
        "param_name": "window",
    }
    assert component_param_slices({key: 5, FIXED_CANDIDATE_PARAM: 0}) == {
        ("indicators", "demo.trend", "demo.trend"): {"window": 5}
    }


def _config(
    *,
    strategy: RunSourceRefConfig | None = None,
    indicators: list[RunIndicatorSourceConfig] | None = None,
) -> RunConfig:
    return RunConfig(
        name="component_source",
        strategy=strategy or RunSourceRefConfig(id="demo.strategy"),
        indicators=indicators
        if indicators is not None
        else [RunIndicatorSourceConfig(id="demo.trend")],
        ranking=RankingConfig(metric="total_return"),
        portfolio=PortfolioConfig(direction="longonly"),
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
        "'param_space_callable': 'param_space', 'wide_callable': 'run_wide'}\n"
        "COMPONENT_CALLABLE = 'run'\n"
        "# %% parameter space\n"
        "def param_space():\n"
        "    return {'window': vbt.Param([2, 3])}\n"
        "# %% main compute\n"
        "def run(data, window):\n"
        "    '''Return a rolling trend frame.'''\n"
        "    close = data.feature('Close')\n"
        "    return close.rolling(int(window), min_periods=1).mean()\n"
        "# %% wide compute\n"
        "def run_wide(data, *, n_candidates, **param_lists):\n"
        "    '''Return wide indicator output.'''\n"
        "    close = data.feature('Close')\n"
        "    T, S = close.shape\n"
        "    windows = param_lists['window']\n"
        "    result = np.zeros((T, n_candidates * S))\n"
        "    for i, w in enumerate(windows):\n"
        "        cols = slice(i * S, (i + 1) * S)\n"
        "        result[:, cols] = close.rolling(int(w), min_periods=1).mean().values\n"
        "    return result\n"
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
        "'defaults': {'threshold': 1.0}, 'param_space_callable': 'param_space', "
        "'wide_callable': 'run_wide'}\n"
        "COMPONENT_CALLABLE = 'run'\n"
        "# %% parameter space\n"
        "def param_space():\n"
        "    return {'threshold': vbt.Param([0.95, 1.0])}\n"
        "# %% main compute\n"
        "def run(inputs, threshold):\n"
        "    '''Return active allocation derived from thresholded trend signals.'''\n"
        "    close = inputs.data.feature('Close')\n"
        "    trend = inputs.indicators['trend']\n"
        "    selected = trend.ge(close * float(threshold)).fillna(False)\n"
        "    active = pd.DataFrame(np.nan, index=close.index, columns=close.columns, dtype=object)\n"
        "    active.loc[:] = selected.astype(object)\n"
        "    return active\n"
        "# %% wide compute\n"
        "def run_wide(inputs, *, n_candidates, **param_lists):\n"
        "    '''Return wide strategy output.'''\n"
        "    close = inputs.data.feature('Close')\n"
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
        "'param_space_callable': 'param_space', 'wide_callable': 'run_wide'}\n"
        "COMPONENT_CALLABLE = 'run'\n"
        "# %% parameter space\n"
        "def param_space():\n"
        "    return {'threshold': vbt.Param([0.95, 1.0], hide=True)}\n"
        "# %% main compute\n"
        "def run(inputs, threshold):\n"
        "    '''Return active allocation for the hidden-param fixture.'''\n"
        "    close = inputs.data.feature('Close')\n"
        "    selected = close.gt(close.shift(1)).fillna(False)\n"
        "    active = pd.DataFrame(np.nan, index=close.index, columns=close.columns, dtype=object)\n"
        "    active.loc[:] = selected.astype(object)\n"
        "    return active\n"
        "# %% wide compute\n"
        "def run_wide(inputs, *, n_candidates, **param_lists):\n"
        "    '''Return wide strategy output for the hidden-param fixture.'''\n"
        "    close = inputs.data.feature('Close')\n"
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


def test_component_source_wide_pipeline_returns_multiindex_frame(tmp_path: Path) -> None:
    root = tmp_path / "research" / "components"
    _write_wide_indicator(root / "indicators" / "trend.py")
    _write_wide_strategy(root / "strategies" / "strategy.py")
    registry = discover_component_registry(root=root, repo_root=tmp_path)
    config = _config()
    data = _data_bundle()

    source = build_component_optimization_source(config, component_registry=registry, data=data)
    close = data.feature("Close")
    n_candidates = 2
    n_symbols = len(close.columns)

    indicator_key = component_param_key("indicators", "demo.trend", "demo.trend", "window")
    strategy_key = component_param_key("strategies", "demo.strategy", "strategy", "threshold")
    result = source.pipeline(
        close,
        n_candidates,
        **{indicator_key: [2, 3], strategy_key: [0.95, 1.0]},
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
    _write_wide_indicator(root / "indicators" / "trend.py")
    _write_wide_strategy(root / "strategies" / "strategy.py")
    registry = discover_component_registry(root=root, repo_root=tmp_path)
    data = _data_bundle()
    source = build_component_optimization_source(_config(), component_registry=registry, data=data)
    close = data.feature("Close")

    indicator_key = component_param_key("indicators", "demo.trend", "demo.trend", "window")
    strategy_key = component_param_key("strategies", "demo.strategy", "strategy", "threshold")
    param_lists = {
        indicator_key: [2, 2, 3, 3],
        strategy_key: [0.95, 1.0, 0.95, 1.0],
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


def _data_bundle() -> MarketDataBundle:
    index = pd.date_range("2026-01-01", periods=6, freq="1D")
    close = pd.DataFrame({"SYN": [10.0, 11.0, 10.5, 12.0, 11.5, 13.0]}, index=index)
    return MarketDataBundle(features={"Close": close}, loaded_features=("Close",))


def _write_wide_indicator(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# %% component overview\n"
        "# Parameterized indicator fixture with wide callable.\n"
        "# %% define component metadata\n"
        "import numpy as np\n"
        "from vectorbtpro import vbt\n"
        "COMPONENT_MANIFEST = {"
        "'family': 'indicators', 'id': 'demo.trend', 'version': '1.0.0', "
        "'input_names': ['Close'], 'param_names': ['window'], "
        "'output_names': ['trend'], 'defaults': {'window': 2}, "
        "'param_space_callable': 'param_space', 'wide_callable': 'run_wide'}\n"
        "COMPONENT_CALLABLE = 'run'\n"
        "# %% parameter space\n"
        "def param_space():\n"
        "    return {'window': vbt.Param([2, 3])}\n"
        "# %% main compute\n"
        "def run(data, window):\n"
        "    '''Return a rolling trend frame.'''\n"
        "    close = data.feature('Close')\n"
        "    return close.rolling(int(window), min_periods=1).mean()\n"
        "# %% wide compute\n"
        "def run_wide(data, *, n_candidates, **param_lists):\n"
        "    '''Return wide indicator output.'''\n"
        "    close = data.feature('Close')\n"
        "    T, S = close.shape\n"
        "    windows = param_lists['window']\n"
        "    result = np.zeros((T, n_candidates * S))\n"
        "    for i, w in enumerate(windows):\n"
        "        cols = slice(i * S, (i + 1) * S)\n"
        "        result[:, cols] = close.rolling(int(w), min_periods=1).mean().values\n"
        "    return result\n"
    )


def _write_wide_strategy(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# %% component overview\n"
        "# Parameterized strategy fixture with wide callable.\n"
        "# %% define component metadata\n"
        "import numpy as np\n"
        "import pandas as pd\n"
        "from vectorbtpro import vbt\n"
        "COMPONENT_MANIFEST = {"
        "'family': 'strategies', 'id': 'demo.strategy', 'version': '1.0.0', "
        "'input_names': ['Close'], 'param_names': ['threshold'], "
        "'output_name': 'active', 'consumes_outputs': ['trend'], "
        "'defaults': {'threshold': 1.0}, 'param_space_callable': 'param_space', "
        "'wide_callable': 'run_wide'}\n"
        "COMPONENT_CALLABLE = 'run'\n"
        "# %% parameter space\n"
        "def param_space():\n"
        "    return {'threshold': vbt.Param([0.95, 1.0])}\n"
        "# %% main compute\n"
        "def run(inputs, threshold):\n"
        "    '''Return active allocation derived from thresholded trend signals.'''\n"
        "    close = inputs.data.feature('Close')\n"
        "    trend = inputs.indicators['trend']\n"
        "    selected = trend.ge(close * float(threshold)).fillna(False)\n"
        "    active = pd.DataFrame(np.nan, index=close.index, columns=close.columns, dtype=object)\n"
        "    active.loc[:] = selected.astype(object)\n"
        "    return active\n"
        "# %% wide compute\n"
        "def run_wide(inputs, *, n_candidates, **param_lists):\n"
        "    '''Return wide strategy output.'''\n"
        "    import numpy as np, pandas as pd\n"
        "    close = inputs.data.feature('Close')\n"
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
