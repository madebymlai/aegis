from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd
from vectorbtpro import vbt

from research.aegis_research.config import PortfolioConfig, SignalConfig

PORTFOLIO_DIAGNOSTICS_SCHEMA_VERSION = "portfolio_diagnostics.v1"
VBT_LONG_SIGNAL_SETTINGS = {
    "accumulate": False,
    "upon_long_conflict": "ignore",
}
VBT_SHORT_SIDE_SETTINGS_NOT_APPLICABLE = {
    "upon_short_conflict": "not_applicable_long_only_v1",
    "upon_dir_conflict": "not_applicable_long_only_v1",
    "upon_opposite_entry": "not_applicable_long_only_v1",
}


@dataclass(frozen=True)
class PortfolioSimulationResult:
    portfolio: vbt.Portfolio
    diagnostics: dict[str, Any]


def simulate_portfolio(
    close: pd.DataFrame,
    entries: pd.DataFrame,
    exits: pd.DataFrame,
    config: PortfolioConfig,
    signal_config: SignalConfig,
    *,
    open_prices: pd.DataFrame | None = None,
    market_index: pd.Index | None = None,
) -> PortfolioSimulationResult:
    _validate_signal_frames(close, entries, exits)
    simulation_entries, simulation_exits, non_executable_diagnostics = _simulation_signals(
        close.index,
        entries,
        exits,
        signal_config,
        market_index=market_index,
    )
    timing_kwargs, execution_diagnostics = _execution_timing_kwargs(
        signal_config,
        open_prices,
        close,
        simulation_entries,
        simulation_exits,
        non_executable_diagnostics,
    )
    pf = vbt.Portfolio.from_signals(
        close=close,
        entries=simulation_entries,
        exits=simulation_exits,
        init_cash=config.init_cash,
        fees=config.fees,
        slippage=config.slippage,
        size=config.size,
        size_type=config.size_type,
        direction=config.direction,
        **VBT_LONG_SIGNAL_SETTINGS,
        **timing_kwargs,
    )
    return PortfolioSimulationResult(
        portfolio=pf,
        diagnostics=_portfolio_diagnostics(
            pf,
            close,
            entries,
            exits,
            simulation_entries,
            simulation_exits,
            config,
            execution_diagnostics,
        ),
    )


def _validate_signal_frames(
    close: pd.DataFrame,
    entries: pd.DataFrame,
    exits: pd.DataFrame,
) -> None:
    if close.empty or len(close.columns) == 0:
        raise ValueError("portfolio close input must contain at least one row and symbol column")
    _assert_same_index("entries", close, entries)
    _assert_same_index("exits", close, exits)
    _assert_same_columns("entries", close, entries)
    _assert_same_columns("exits", close, exits)
    _assert_numeric_non_null("Close", close)


def _execution_timing_kwargs(
    signal_config: SignalConfig,
    open_prices: pd.DataFrame | None,
    close: pd.DataFrame,
    entries: pd.DataFrame,
    exits: pd.DataFrame,
    non_executable_diagnostics: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    if signal_config.execution_timing == "same_close":
        return {"price": "close"}, {
            "timing": "same_close",
            "vbt_price": "close",
            "open_required": False,
            **non_executable_diagnostics,
        }
    if open_prices is None:
        raise ValueError("next_open execution requires open prices")
    _assert_same_index("Open", close, open_prices)
    _assert_same_columns("Open", close, open_prices)
    required_open_mask = (entries | exits).shift(1, fill_value=False)
    _assert_numeric_non_null("Open execution", open_prices, required_open_mask)
    return {"price": "nextopen", "open": open_prices}, {
        "timing": "next_open",
        "vbt_price": "nextopen",
        "open_required": True,
        **non_executable_diagnostics,
    }


def _portfolio_diagnostics(
    pf: vbt.Portfolio,
    close: pd.DataFrame,
    entries: pd.DataFrame,
    exits: pd.DataFrame,
    simulation_entries: pd.DataFrame,
    simulation_exits: pd.DataFrame,
    config: PortfolioConfig,
    execution_diagnostics: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": PORTFOLIO_DIAGNOSTICS_SCHEMA_VERSION,
        "execution": execution_diagnostics,
        "vbt_settings": {
            "direction": config.direction,
            **VBT_LONG_SIGNAL_SETTINGS,
            "one_order_per_bar": True,
        },
        "contract": {
            "direction_scope": "long_only_v1",
            "not_applicable_vbt_settings": dict(VBT_SHORT_SIDE_SETTINGS_NOT_APPLICABLE),
        },
        "shape": {
            "rows": len(close.index),
            "symbols": [str(column) for column in close.columns],
            "symbol_count": len(close.columns),
        },
        "raw_signals": {
            "raw_entry_states": _true_count(entries),
            "raw_exit_states": _true_count(exits),
            "simultaneous_entry_exit_states": _true_count(entries & exits),
        },
        "simulation_signals": {
            "entry_states": _true_count(simulation_entries),
            "exit_states": _true_count(simulation_exits),
        },
        "records": portfolio_record_counts(pf),
    }


def _simulation_signals(
    index: pd.Index,
    entries: pd.DataFrame,
    exits: pd.DataFrame,
    signal_config: SignalConfig,
    *,
    market_index: pd.Index | None,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    zero_counts = dict.fromkeys(map(str, entries.columns), 0)
    if signal_config.execution_timing == "same_close":
        return (
            entries,
            exits,
            {
                "terminal_non_executable_signals": 0,
                "terminal_non_executable_by_symbol": zero_counts,
                "gap_non_executable_signals": 0,
                "gap_non_executable_by_symbol": zero_counts,
                "non_executable_signals": 0,
                "non_executable_by_symbol": zero_counts,
            },
        )

    executable_mask = _next_open_executable_mask(index, entries.columns, market_index)
    raw_signal_mask = entries | exits
    terminal_mask = _terminal_row_mask(index, entries.columns)
    non_executable_mask = raw_signal_mask & ~executable_mask
    terminal_non_executable = non_executable_mask & terminal_mask
    gap_non_executable = non_executable_mask & ~terminal_mask
    return (
        entries & executable_mask,
        exits & executable_mask,
        {
            "terminal_non_executable_signals": _true_count(terminal_non_executable),
            "terminal_non_executable_by_symbol": _count_by_symbol(terminal_non_executable),
            "gap_non_executable_signals": _true_count(gap_non_executable),
            "gap_non_executable_by_symbol": _count_by_symbol(gap_non_executable),
            "non_executable_signals": _true_count(non_executable_mask),
            "non_executable_by_symbol": _count_by_symbol(non_executable_mask),
        },
    )


def _next_open_executable_mask(
    index: pd.Index,
    columns: pd.Index,
    market_index: pd.Index | None,
) -> pd.DataFrame:
    executable = pd.Series(False, index=index)
    if len(index) < 2:
        return _broadcast_mask(executable, columns)
    if market_index is None:
        executable.iloc[:-1] = True
        return _broadcast_mask(executable, columns)
    market_positions = pd.Series(range(len(market_index)), index=market_index)
    try:
        positions = market_positions.loc[index].to_numpy()
    except KeyError as error:
        raise ValueError("portfolio market_index must contain all simulation rows") from error
    executable.iloc[:-1] = positions[1:] == positions[:-1] + 1
    return _broadcast_mask(executable, columns)


def _terminal_row_mask(index: pd.Index, columns: pd.Index) -> pd.DataFrame:
    terminal = pd.Series(False, index=index)
    if len(index):
        terminal.iloc[-1] = True
    return _broadcast_mask(terminal, columns)


def _broadcast_mask(mask: pd.Series, columns: pd.Index) -> pd.DataFrame:
    return pd.DataFrame(dict.fromkeys(columns, mask), index=mask.index)


def portfolio_record_counts(pf: vbt.Portfolio) -> dict[str, Any]:
    order_counts = _count_map(pf.orders.count())
    trade_counts = _count_map(pf.trades.count())
    return {
        "order_count": _sum_counts(order_counts),
        "trade_count": _sum_counts(trade_counts),
        "orders_per_symbol": order_counts,
        "trades_per_symbol": trade_counts,
    }


def _assert_same_index(name: str, expected: pd.DataFrame, actual: pd.DataFrame) -> None:
    if not actual.index.equals(expected.index):
        raise ValueError(f"portfolio {name} input index must match Close index exactly")


def _assert_same_columns(name: str, expected: pd.DataFrame, actual: pd.DataFrame) -> None:
    if not actual.columns.equals(expected.columns):
        raise ValueError(f"portfolio {name} input columns must match Close columns exactly")


def _assert_numeric_non_null(
    name: str,
    frame: pd.DataFrame,
    mask: pd.DataFrame | None = None,
) -> None:
    non_numeric = [
        column for column in frame.columns if not pd.api.types.is_numeric_dtype(frame[column])
    ]
    if non_numeric:
        raise ValueError(f"portfolio {name} input has non-numeric columns {non_numeric}")
    if mask is None:
        if frame.isna().any().any():
            raise ValueError(f"portfolio {name} input contains null prices")
        return
    if (frame.isna() & mask).any().any():
        raise ValueError(f"portfolio {name} input contains null prices")


def _true_count(value: pd.DataFrame | pd.Series) -> int:
    return int(value.to_numpy(dtype=bool).sum())


def _count_by_symbol(value: pd.DataFrame) -> dict[str, int]:
    return {str(column): _true_count(value.loc[:, column]) for column in value.columns}


def _count_map(value: Any) -> dict[str, int]:
    if isinstance(value, pd.DataFrame):
        return {
            "__".join(map(str, key)) if isinstance(key, tuple) else str(key): int(item)
            for key, item in value.stack().items()
        }
    if isinstance(value, pd.Series):
        return {str(key): int(item) for key, item in value.items()}
    return {"portfolio": int(value)}


def _sum_counts(values: dict[str, int]) -> int:
    return sum(values.values())
