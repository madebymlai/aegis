from __future__ import annotations

from vectorbtpro import vbt

from research.aegis_research.optimization.portfolio_params import (
    PORTFOLIO_BAND_DOWN_PARAM,
    PORTFOLIO_BAND_UP_PARAM,
    optimization_params,
    portfolio_param_grid,
)
from tests.support.research.aegis_research.factories import (
    make_optimization_config,
)


def test_portfolio_param_grid_is_empty_without_band_sweep() -> None:
    assert portfolio_param_grid(make_optimization_config()) == {}


def test_optimization_params_appends_portfolio_band_axes() -> None:
    optimization = make_optimization_config(
        portfolio={"band_up": [0.05], "band_down": [0.15, 0.20]}
    )

    params = optimization_params({"alpha": vbt.Param([0.5, 1.0])}, optimization)

    assert list(params) == ["alpha", PORTFOLIO_BAND_UP_PARAM, PORTFOLIO_BAND_DOWN_PARAM]
    assert params[PORTFOLIO_BAND_UP_PARAM].value == [0.05]
    assert params[PORTFOLIO_BAND_DOWN_PARAM].value == [0.15, 0.20]
