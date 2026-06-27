from __future__ import annotations

from collections.abc import Mapping

from vectorbtpro import vbt

from research.aegis_research.configuration import OptimizationConfig

PORTFOLIO_PARAM_PREFIX = "portfolio"
PORTFOLIO_PARAM_SEPARATOR = "__"
PORTFOLIO_BAND_UP_PARAM = f"{PORTFOLIO_PARAM_PREFIX}{PORTFOLIO_PARAM_SEPARATOR}band_up"
PORTFOLIO_BAND_DOWN_PARAM = f"{PORTFOLIO_PARAM_PREFIX}{PORTFOLIO_PARAM_SEPARATOR}band_down"
PORTFOLIO_BAND_PARAMS = (PORTFOLIO_BAND_UP_PARAM, PORTFOLIO_BAND_DOWN_PARAM)


def portfolio_param_grid(optimization: OptimizationConfig) -> dict[str, vbt.Param]:
    """Candidate axes owned by the portfolio execution layer."""
    grid = optimization.portfolio
    if not grid.band_up and not grid.band_down:
        return {}
    return {
        PORTFOLIO_BAND_UP_PARAM: vbt.Param(list(grid.band_up)),
        PORTFOLIO_BAND_DOWN_PARAM: vbt.Param(list(grid.band_down)),
    }


def optimization_params(
    source_params: Mapping[str, vbt.Param],
    optimization: OptimizationConfig,
) -> dict[str, vbt.Param]:
    """Merge signal-source axes with portfolio-owned axes."""
    params = dict(source_params)
    portfolio_params = portfolio_param_grid(optimization)
    duplicate = sorted(set(params) & set(portfolio_params))
    if duplicate:
        raise ValueError(f"optimization param names collide with portfolio params: {duplicate}")
    params.update(portfolio_params)
    return params


def is_portfolio_param_key(value: str) -> bool:
    return value in PORTFOLIO_BAND_PARAMS
