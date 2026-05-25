from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from research.aegis_research.component_registry import discover_component_registry
from research.aegis_research.config import (
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
    output = source.pipeline(close, **{indicator_key: 2, strategy_key: 0.95})

    assert isinstance(output, pd.DataFrame)
    assert output.shape == close.shape
    assert output.index.equals(close.index)
    assert list(output.columns) == list(close.columns)


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
    registry = _registry(tmp_path)
    config = _config(
        indicators=[RunIndicatorSourceConfig(id="demo.trend", lock_id="lock_trend_best")],
    )
    resolved = {
        component_ref_key("indicators", "demo.trend", "demo.trend"): {"window": 3},
    }

    source = build_component_optimization_source(
        config,
        component_registry=registry,
        data=_data_bundle(),
        resolved_component_params=resolved,
    )

    indicator_key = component_param_key("indicators", "demo.trend", "demo.trend", "window")

    assert indicator_key not in source.params
    assert source.evidence["indicators"][0]["param_mode"] == "locked"
    assert source.evidence["indicators"][0]["fixed_params"] == {"window": 3}


def test_component_source_rejects_unresolved_lock_refs(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    config = _config(
        indicators=[RunIndicatorSourceConfig(id="demo.trend", lock_id="lock_trend_best")],
    )

    with pytest.raises(ComponentSourceError, match="requires resolved"):
        build_component_optimization_source(
            config, component_registry=registry, data=_data_bundle()
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
        ranking=RankingConfig(metric="total_return", direction="desc"),
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
        "from vectorbtpro import vbt\n"
        "COMPONENT_MANIFEST = {"
        f"'family': 'indicators', 'id': {component_id!r}, 'version': '1.0.0', "
        "'input_names': ['Close'], 'param_names': ['window'], "
        "'output_names': ['trend'], 'defaults': {'window': 2}, "
        "'param_space_callable': 'param_space'}\n"
        "COMPONENT_CALLABLE = 'run'\n"
        "# %% parameter space\n"
        "def param_space():\n"
        "    return {'window': vbt.Param([2, 3])}\n"
        "# %% main compute\n"
        "def run(data, window):\n"
        "    '''Return a rolling trend frame.'''\n"
        "    close = data.feature('Close')\n"
        "    return close.rolling(int(window), min_periods=1).mean()\n"
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
        "'defaults': {'threshold': 1.0}, 'param_space_callable': 'param_space'}\n"
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
        "'param_space_callable': 'param_space'}\n"
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
    )


def _data_bundle() -> MarketDataBundle:
    index = pd.date_range("2026-01-01", periods=6, freq="1D")
    close = pd.DataFrame({"SYN": [10.0, 11.0, 10.5, 12.0, 11.5, 13.0]}, index=index)
    return MarketDataBundle(features={"Close": close}, loaded_features=("Close",))
