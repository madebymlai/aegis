from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd
from vectorbtpro import vbt

from research.aegis_research.candidate_sweeps import SYMBOL_LEVEL
from research.aegis_research.config import PortfolioConfig, SignalConfig

PORTFOLIO_DIAGNOSTICS_SCHEMA_VERSION = "portfolio_diagnostics.v2"
VBT_PORTFOLIO_FACTORY = "Portfolio.from_signals"
VBT_RESOLVED_SIZE_TYPE = "valuepercent"
VBT_LONG_SIGNAL_SETTINGS = {
    "accumulate": False,
    "upon_long_conflict": "ignore",
}
VBT_SHARED_CASH_SETTINGS = {
    "cash_sharing": True,
    "group_by": True,
    "call_seq": "auto",
}
VBT_CALL_SEQUENCE_CAVEAT = (
    "VectorBT automatic call sequencing sorts approximate order value using predetermined "
    "prices; it is not a custom path-dependent execution engine."
)
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
    size = _entry_size_frame(simulation_entries, config.entry_budget)
    _assert_same_index("generated size", close, size)
    _assert_same_columns("generated size", close, size)
    pf = vbt.Portfolio.from_signals(
        close=close,
        entries=simulation_entries,
        exits=simulation_exits,
        init_cash=config.init_cash,
        fees=config.fees,
        slippage=config.slippage,
        size=size,
        size_type=VBT_RESOLVED_SIZE_TYPE,
        direction=config.direction,
        **VBT_LONG_SIGNAL_SETTINGS,
        **VBT_SHARED_CASH_SETTINGS,
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
            size,
            config,
            execution_diagnostics,
        ),
    )


def simulate_portfolio_batch(
    close: pd.DataFrame,
    entries: pd.DataFrame,
    exits: pd.DataFrame,
    config: PortfolioConfig,
    signal_config: SignalConfig,
    *,
    open_prices: pd.DataFrame | None = None,
    market_index: pd.Index | None = None,
) -> PortfolioSimulationResult:
    _validate_candidate_signal_frames(entries, exits)
    expanded_close = expand_market_frame_to_candidate_columns(
        close,
        entries.columns,
        feature_name="Close",
    )
    expanded_open = None
    if open_prices is not None:
        expanded_open = expand_market_frame_to_candidate_columns(
            open_prices,
            entries.columns,
            feature_name="Open",
        )
    _validate_signal_frames(expanded_close, entries, exits)
    simulation_entries, simulation_exits, non_executable_diagnostics = _simulation_signals(
        expanded_close.index,
        entries,
        exits,
        signal_config,
        market_index=market_index,
    )
    timing_kwargs, execution_diagnostics = _execution_timing_kwargs(
        signal_config,
        expanded_open,
        expanded_close,
        simulation_entries,
        simulation_exits,
        non_executable_diagnostics,
    )
    size = _candidate_entry_size_frame(simulation_entries, config.entry_budget)
    _assert_same_index("generated size", expanded_close, size)
    _assert_same_columns("generated size", expanded_close, size)
    group_by = vbt.ExceptLevel(SYMBOL_LEVEL)
    pf = vbt.Portfolio.from_signals(
        close=expanded_close,
        entries=simulation_entries,
        exits=simulation_exits,
        init_cash=config.init_cash,
        fees=config.fees,
        slippage=config.slippage,
        size=size,
        size_type=VBT_RESOLVED_SIZE_TYPE,
        direction=config.direction,
        **VBT_LONG_SIGNAL_SETTINGS,
        cash_sharing=True,
        group_by=group_by,
        call_seq=VBT_SHARED_CASH_SETTINGS["call_seq"],
        **timing_kwargs,
    )
    diagnostics = _portfolio_diagnostics(
        pf,
        expanded_close,
        entries,
        exits,
        simulation_entries,
        simulation_exits,
        size,
        config,
        execution_diagnostics,
    )
    candidate_ids = _candidate_group_ids(entries.columns)
    diagnostics["grouping"] = {
        "cash_sharing": True,
        "group_by": f"except_level:{SYMBOL_LEVEL}",
        "group_count": len(candidate_ids),
        "group_scope": "candidate_symbols_single_cash_pool",
        "candidate_ids": candidate_ids,
    }
    diagnostics["shape"] |= {
        "candidate_count": len(candidate_ids),
        "column_count": len(expanded_close.columns),
    }
    return PortfolioSimulationResult(portfolio=pf, diagnostics=diagnostics)


def expand_market_frame_to_candidate_columns(
    frame: pd.DataFrame,
    target_columns: pd.MultiIndex,
    *,
    feature_name: str,
) -> pd.DataFrame:
    _validate_candidate_columns(target_columns, field_name="target columns")
    if not frame.index.is_unique:
        raise ValueError(f"{feature_name} input index must be unique")
    symbol_columns = {str(column): column for column in frame.columns}
    if len(symbol_columns) != len(frame.columns):
        raise ValueError(f"{feature_name} input symbols must be unique when stringified")
    symbol_values = target_columns.get_level_values(SYMBOL_LEVEL)
    missing_symbols = sorted({str(symbol) for symbol in symbol_values} - set(symbol_columns))
    if missing_symbols:
        raise ValueError(f"{feature_name} input is missing symbols for candidate columns: {missing_symbols}")
    expanded = pd.DataFrame(
        {
            column: frame[symbol_columns[str(column[target_columns.names.index(SYMBOL_LEVEL)])]].to_numpy()
            for column in target_columns
        },
        index=frame.index,
    )
    expanded.columns = target_columns
    return expanded


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


def _validate_candidate_signal_frames(entries: pd.DataFrame, exits: pd.DataFrame) -> None:
    _validate_candidate_columns(entries.columns, field_name="entries")
    _validate_candidate_columns(exits.columns, field_name="exits")
    if not entries.index.equals(exits.index):
        raise ValueError("sweep exits index must match entries index")
    if not entries.columns.equals(exits.columns):
        raise ValueError("sweep exits columns must match entries columns")


def _validate_candidate_columns(columns: pd.Index, *, field_name: str) -> None:
    if not isinstance(columns, pd.MultiIndex):
        raise TypeError(f"sweep {field_name} must use MultiIndex columns")
    if columns.names.count(SYMBOL_LEVEL) != 1:
        raise ValueError(f"sweep {field_name} must include exactly one {SYMBOL_LEVEL!r} level")
    if len(columns.names) < 2:
        raise ValueError(f"sweep {field_name} must include candidate and symbol levels")
    if columns.has_duplicates:
        raise ValueError(f"sweep {field_name} must not contain duplicate columns")
    for candidate_id in _candidate_group_ids(columns):
        mask = _candidate_group_mask(columns, candidate_id)
        if not mask.any():
            raise ValueError(f"sweep {field_name} candidate {candidate_id!r} has no symbols")


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
    size: pd.DataFrame,
    config: PortfolioConfig,
    execution_diagnostics: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": PORTFOLIO_DIAGNOSTICS_SCHEMA_VERSION,
        "execution": execution_diagnostics,
        "vbt_settings": {
            "factory": VBT_PORTFOLIO_FACTORY,
            "direction": config.direction,
            "size_type": VBT_RESOLVED_SIZE_TYPE,
            "cash_sharing": VBT_SHARED_CASH_SETTINGS["cash_sharing"],
            "group_by": VBT_SHARED_CASH_SETTINGS["group_by"],
            "call_seq": VBT_SHARED_CASH_SETTINGS["call_seq"],
            "call_sequence_semantics": "sell_before_buy_within_shared_cash_group",
            "call_sequence_caveat": VBT_CALL_SEQUENCE_CAVEAT,
            "fees": config.fees,
            "slippage": config.slippage,
            **VBT_LONG_SIGNAL_SETTINGS,
            "one_order_per_bar": True,
        },
        "contract": {
            "direction_scope": "long_only_v1",
            "allocation_mode": "event_style_signals",
            "entry_budget": config.entry_budget,
            "entry_budget_interpretation": (
                "total portfolio-value share split across executable same-bar entries"
            ),
            "rebalances_existing_positions": False,
            "not_applicable_vbt_settings": dict(VBT_SHORT_SIDE_SETTINGS_NOT_APPLICABLE),
        },
        "grouping": {
            "cash_sharing": VBT_SHARED_CASH_SETTINGS["cash_sharing"],
            "group_by": VBT_SHARED_CASH_SETTINGS["group_by"],
            "group_count": 1,
            "group_scope": "all_symbols_single_cash_pool",
        },
        "sizing": _sizing_summary(size, simulation_entries, config.entry_budget),
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


def _entry_size_frame(entries: pd.DataFrame, entry_budget: float) -> pd.DataFrame:
    active_entries = entries.sum(axis=1)
    per_entry = pd.Series(0.0, index=entries.index)
    active_rows = active_entries > 0
    per_entry.loc[active_rows] = entry_budget / active_entries.loc[active_rows]
    return entries.astype(float).mul(per_entry, axis=0)


def _candidate_entry_size_frame(entries: pd.DataFrame, entry_budget: float) -> pd.DataFrame:
    size = pd.DataFrame(0.0, index=entries.index, columns=entries.columns)
    for candidate_id in _candidate_group_ids(entries.columns):
        mask = _candidate_group_mask(entries.columns, candidate_id)
        candidate_entries = entries.loc[:, mask]
        active_entries = candidate_entries.sum(axis=1)
        per_entry = pd.Series(0.0, index=entries.index)
        active_rows = active_entries > 0
        per_entry.loc[active_rows] = entry_budget / active_entries.loc[active_rows]
        size.loc[:, mask] = candidate_entries.astype(float).mul(per_entry, axis=0)
    return size


def _candidate_group_ids(columns: pd.MultiIndex) -> list[Any]:
    candidate_levels = [name for name in columns.names if name != SYMBOL_LEVEL]
    if len(candidate_levels) == 1:
        return list(dict.fromkeys(columns.get_level_values(candidate_levels[0])))
    return list(dict.fromkeys(columns.droplevel(SYMBOL_LEVEL)))


def _candidate_group_mask(columns: pd.MultiIndex, candidate_id: Any) -> pd.Series:
    candidate_levels = [name for name in columns.names if name != SYMBOL_LEVEL]
    if len(candidate_levels) == 1:
        return pd.Series(columns.get_level_values(candidate_levels[0]) == candidate_id, index=columns)
    return pd.Series(columns.droplevel(SYMBOL_LEVEL) == candidate_id, index=columns)


def _sizing_summary(
    size: pd.DataFrame,
    entries: pd.DataFrame,
    entry_budget: float,
) -> dict[str, Any]:
    active_entries = entries.sum(axis=1)
    nonzero_count = int(active_entries.sum())
    nonzero_sizes = entry_budget / active_entries[active_entries > 0]
    return {
        "entry_budget": entry_budget,
        "size_type": VBT_RESOLVED_SIZE_TYPE,
        "budget_basis": "portfolio_value",
        "budget_split": "equally_across_executable_same_bar_entries",
        "active_entry_rows": int((active_entries > 0).sum()),
        "max_entries_per_row": int(active_entries.max()) if len(active_entries) else 0,
        "nonzero_size_cells": nonzero_count,
        "min_nonzero_valuepercent": (float(nonzero_sizes.min()) if len(nonzero_sizes) else None),
        "max_nonzero_valuepercent": (float(nonzero_sizes.max()) if len(nonzero_sizes) else None),
    }


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
    group_order_counts = _count_map(pf.orders.count())
    group_trade_counts = _count_map(pf.trades.count())
    symbol_order_counts = _count_map(pf.orders.count(group_by=False))
    symbol_trade_counts = _count_map(pf.trades.count(group_by=False))
    return {
        "order_count": _sum_counts(group_order_counts),
        "trade_count": _sum_counts(group_trade_counts),
        "orders_per_group": group_order_counts,
        "trades_per_group": group_trade_counts,
        "orders_per_symbol": symbol_order_counts,
        "trades_per_symbol": symbol_trade_counts,
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
