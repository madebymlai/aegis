from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from vectorbtpro import vbt

from research.aegis_research.config import PortfolioConfig
from research.aegis_research.portfolio_policy import (
    apply_executable_mask_and_terminal_liquidation,
)

SYMBOL_LEVEL = "symbol"
PORTFOLIO_DIAGNOSTICS_SCHEMA_VERSION = "portfolio_diagnostics.v3"
VBT_PORTFOLIO_FACTORY = "Portfolio.from_optimizer"
VBT_PF_METHOD = "from_orders"
VBT_RESOLVED_SIZE_TYPE = "targetpercent"
VBT_SHARED_GROUP_BY = "all_symbols_single_group"
VBT_CANDIDATE_GROUP_BY = f"except_level:{SYMBOL_LEVEL}"
VBT_CALL_SEQUENCE_CAVEAT = (
    "VectorBT automatic call sequencing sorts approximate order value using predetermined "
    "prices; it is not a custom path-dependent execution engine."
)
# These conflict-resolution knobs belong to ``from_signals``; ``from_orders`` (the
# factory this route uses) never sees them, regardless of direction.
VBT_NOT_APPLICABLE_SETTINGS: dict[str, str] = {
    "upon_short_conflict": "not_applicable_from_orders",
    "upon_dir_conflict": "not_applicable_from_orders",
    "upon_opposite_entry": "not_applicable_from_orders",
}
VBT_LEVERAGE_MODE = "eager"
# Requested ≈ realized fill-fidelity tolerance, per fill row and asset. ``pfo.allocations``
# (requested target) and ``pf.get_allocations`` (the executed book revalued at that bar's
# close) differ by a small, benign amount even on correct fills — a target decided from one
# price snapshot is revalued at another, so a held leg drifts a few percent (maintainer-
# confirmed: "most rows have correct allocation; discrepancies are rare"). The known
# ``cash_sharing`` + multi-asset leverage mis-fill ("only one asset in a group can use
# leverage at a time") is a different beast: a leg fails to fill and lands ~a full target
# magnitude away (≈1.0), silently under-trading or drifting the book net-long. This tolerance
# sits in the wide gap between the two so it catches the mis-fill without flagging revaluation.
REQUESTED_REALIZED_TOLERANCE = 0.5
# Bars between a rebalance decision and the row its fill settles into the realized book.
# Same-close fills land on the decision row (lag 0); next-open fills land on the next row
# (``from_ago=1`` → lag 1). A fill that would land past the last bar (a next-open terminal
# liquidation) cannot execute and is skipped by the fidelity check.
EXECUTION_FILL_LAG: dict[str, int] = {"same_close": 0, "next_open": 1}
# Next-open execution: a target decided from bar t's close fills at bar t+1's open.
# VBT's ``price="nextopen"`` sets ``from_ago=1`` (shift one bar) and fills at the open,
# which is the canonical VBT way to avoid same-bar look-ahead without manual shifting.
VBT_NEXT_OPEN_PRICE = "nextopen"

ORDER_REJECTION_STATUSES: tuple[str, ...] = (
    "NoCash",
    "PartialFill",
    "SizeNaN",
    "SizeZero",
)


@dataclass(frozen=True)
class PortfolioSimulationResult:
    portfolio: vbt.Portfolio
    diagnostics: dict[str, Any]


def _execution_settings(open_: pd.DataFrame | None) -> tuple[dict[str, Any], str]:
    """Resolve VBT fill-timing kwargs.

    With ``open_`` provided, fill at the next bar's open (``price="nextopen"`` ->
    ``from_ago=1``) so a target decided from bar t's close cannot fill on bar t —
    eliminating same-bar look-ahead. Without it, fall back to close fills.
    """
    if open_ is None:
        return {}, "same_close"
    return {"price": VBT_NEXT_OPEN_PRICE, "open": open_}, "next_open"


def _build_portfolio(
    price_frame: pd.DataFrame,
    allocations: pd.DataFrame,
    config: PortfolioConfig,
    *,
    open_frame: pd.DataFrame | None,
    market_index: pd.Index | None,
    group_by: Any,
) -> tuple[vbt.Portfolio, Any, dict[str, Any], str]:
    """Mask allocations, build the PFO, and run ``from_optimizer``.

    Shared core for the single-group and per-candidate simulations: identical
    masking, allocation-filling, and execution settings; only ``group_by`` (and
    whether the frames are candidate-expanded) differs between the two callers.
    """
    masked, non_exec_diag = apply_executable_mask_and_terminal_liquidation(
        allocations,
        market_index=market_index,
    )
    pfo = vbt.PFO.from_filled_allocations(
        masked,
        valid_only=True,
        nonzero_only=False,
        unique_only=False,
    )
    exec_kwargs, execution_timing = _execution_settings(open_frame)
    pf = vbt.Portfolio.from_optimizer(
        price_frame,
        pfo,
        pf_method=VBT_PF_METHOD,
        size_type=VBT_RESOLVED_SIZE_TYPE,
        direction=config.direction,
        cash_sharing=True,
        call_seq="auto",
        group_by=group_by,
        fees=config.fees,
        slippage=config.slippage,
        init_cash=config.init_cash,
        leverage=config.gross_cap,
        leverage_mode=VBT_LEVERAGE_MODE,
        **exec_kwargs,
    )
    return pf, pfo, non_exec_diag, execution_timing


def simulate_portfolio(
    close: pd.DataFrame,
    allocations: pd.DataFrame,
    config: PortfolioConfig,
    *,
    open_: pd.DataFrame | None = None,
    market_index: pd.Index | None = None,
) -> PortfolioSimulationResult:
    _validate_allocations_frame(close, allocations)
    pf, pfo, non_exec_diag, execution_timing = _build_portfolio(
        close,
        allocations,
        config,
        open_frame=open_,
        market_index=market_index,
        group_by=True,
    )
    diagnostics = _portfolio_diagnostics(
        pf=pf,
        pfo=pfo,
        close=close,
        config=config,
        non_executable=non_exec_diag,
        group_by_label=VBT_SHARED_GROUP_BY,
        candidate_ids=None,
        execution_timing=execution_timing,
    )
    return PortfolioSimulationResult(portfolio=pf, diagnostics=diagnostics)


def simulate_portfolio_batch(
    close: pd.DataFrame,
    allocations: pd.DataFrame,
    config: PortfolioConfig,
    *,
    open_: pd.DataFrame | None = None,
    market_index: pd.Index | None = None,
    compute_diagnostics: bool = True,
) -> PortfolioSimulationResult:
    _validate_candidate_columns(allocations.columns, field_name="allocations")
    expanded_close = expand_market_frame_to_candidate_columns(
        close,
        allocations.columns,
        feature_name="Close",
    )
    _validate_allocations_frame(expanded_close, allocations)
    expanded_open = (
        None
        if open_ is None
        else expand_market_frame_to_candidate_columns(
            open_, allocations.columns, feature_name="Open"
        )
    )
    pf, pfo, non_exec_diag, execution_timing = _build_portfolio(
        expanded_close,
        allocations,
        config,
        open_frame=expanded_open,
        market_index=market_index,
        group_by=vbt.ExceptLevel(SYMBOL_LEVEL),
    )
    if not compute_diagnostics:
        return PortfolioSimulationResult(portfolio=pf, diagnostics={})
    candidate_ids = _candidate_group_ids(allocations.columns)
    diagnostics = _portfolio_diagnostics(
        pf=pf,
        pfo=pfo,
        close=expanded_close,
        config=config,
        non_executable=non_exec_diag,
        group_by_label=VBT_CANDIDATE_GROUP_BY,
        candidate_ids=candidate_ids,
        execution_timing=execution_timing,
    )
    diagnostics["shape"] |= {
        "candidate_count": len(candidate_ids),
        "column_count": len(expanded_close.columns),
    }
    diagnostics["grouping"] = {
        "cash_sharing": True,
        "group_by": VBT_CANDIDATE_GROUP_BY,
        "group_count": len(candidate_ids),
        "group_scope": "candidate_symbols_single_cash_pool",
        "candidate_ids": candidate_ids,
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


def _validate_candidate_columns(columns: pd.Index, *, field_name: str) -> None:
    if not isinstance(columns, pd.MultiIndex):
        raise TypeError(f"sweep {field_name} must use MultiIndex columns")
    if columns.names.count(SYMBOL_LEVEL) != 1:
        raise ValueError(f"sweep {field_name} must include exactly one {SYMBOL_LEVEL!r} level")
    if len(columns.names) < 2:
        raise ValueError(f"sweep {field_name} must include candidate and symbol levels")
    if columns.has_duplicates:
        raise ValueError(f"sweep {field_name} must not contain duplicate columns")


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


def _portfolio_diagnostics(
    *,
    pf: vbt.Portfolio,
    pfo: Any,
    close: pd.DataFrame,
    config: PortfolioConfig,
    non_executable: dict[str, Any],
    group_by_label: str,
    candidate_ids: list[Any] | None,
    execution_timing: str = "same_close",
) -> dict[str, Any]:
    price_setting = (
        VBT_NEXT_OPEN_PRICE if execution_timing == "next_open" else "default_close_no_kwarg_passed"
    )
    return {
        "schema_version": PORTFOLIO_DIAGNOSTICS_SCHEMA_VERSION,
        "vbt_settings": {
            "factory": VBT_PORTFOLIO_FACTORY,
            "pf_method": VBT_PF_METHOD,
            "size_type": VBT_RESOLVED_SIZE_TYPE,
            "direction": config.direction,
            "cash_sharing": True,
            "group_by": group_by_label,
            "call_seq": "auto",
            "call_sequence_semantics": "sell_before_buy_within_shared_cash_group",
            "call_sequence_caveat": VBT_CALL_SEQUENCE_CAVEAT,
            "fees": config.fees,
            "slippage": config.slippage,
            "leverage": config.gross_cap,
            "leverage_mode": VBT_LEVERAGE_MODE,
            "one_order_per_bar": True,
            "price": price_setting,
        },
        "contract": {
            "gross_cap": config.gross_cap,
            "net_cap": config.net_cap,
            "execution_timing": execution_timing,
            "terminal_liquidation": execution_timing == "same_close",
            "financing_carry": "not_modeled_v1",
            "not_applicable_vbt_settings": dict(VBT_NOT_APPLICABLE_SETTINGS),
        },
        "grouping": {
            "cash_sharing": True,
            "group_by": group_by_label,
            "group_count": 1 if candidate_ids is None else len(candidate_ids),
            "group_scope": (
                "all_symbols_single_cash_pool"
                if candidate_ids is None
                else "candidate_symbols_single_cash_pool"
            ),
        },
        "shape": {
            "rows": len(close.index),
            "symbols": [str(column) for column in close.columns],
            "symbol_count": len(close.columns),
        },
        "allocations": _allocations_diagnostics(pfo, pf, execution_timing=execution_timing),
        "order_rejections": _order_rejection_counts(pf),
        "non_executable": non_executable,
        "records": portfolio_record_counts(pf),
    }


def _allocations_diagnostics(
    pfo: Any, pf: vbt.Portfolio, *, execution_timing: str = "same_close"
) -> dict[str, Any]:
    alloc_records = pfo.alloc_records
    alloc_idx_arr = alloc_records.get_field_arr("alloc_idx")
    col_arr = alloc_records.get_field_arr("col")
    index = pfo.wrapper.index
    candidate_index = pfo.wrapper.grouper.get_index()
    rebalance_rows = [
        (
            _scalar(index[int(row_idx)]),
            _candidate_label(candidate_index, int(col)),
        )
        for row_idx, col in zip(alloc_idx_arr, col_arr, strict=True)
    ]
    realized = pf.get_allocations(group_by=False)
    assert_requested_realized_fidelity(
        pfo.allocations,
        realized,
        fill_lag=EXECUTION_FILL_LAG[execution_timing],
        tolerance=REQUESTED_REALIZED_TOLERANCE,
    )
    requested = _serialize_sparse_frame(pfo.allocations)
    realized_at_fill = _realized_weights_at_fill(
        realized=realized,
        index=index,
        alloc_idx_arr=alloc_idx_arr,
    )
    return {
        "rebalance_rows": rebalance_rows,
        "requested": requested,
        "realized_at_fill": realized_at_fill,
    }


def assert_requested_realized_fidelity(
    requested: pd.DataFrame,
    realized: pd.DataFrame,
    *,
    fill_lag: int = 0,
    tolerance: float = REQUESTED_REALIZED_TOLERANCE,
) -> None:
    """Fail-closed: the realized book must reproduce the requested book at each fill.

    ``requested`` is the sparse rebalance frame (``pfo.allocations`` — rebalance rows
    only); ``realized`` is the dense post-fill book (``pf.get_allocations(group_by=False)``).
    Each requested row is compared against the realized row its fill settles into:
    ``decision_row + fill_lag`` (lag 0 for same-close, 1 for next-open). A fill that would
    land past the last bar — a next-open terminal liquidation — cannot execute and is
    skipped. Realized weights drift between fills as prices move, which is expected and not
    a fill error, so only the settled fill rows are checked. A divergence beyond
    ``tolerance`` on a fill row is the known ``cash_sharing`` + multi-asset leverage mis-fill
    ("only one asset in a group can use leverage at a time"), which silently corrupts metrics
    by under-trading a leg or drifting the book net-long, and is raised.
    """
    if requested.empty:
        return
    realized_aligned = realized.reindex(columns=requested.columns)
    realized_values = realized_aligned.to_numpy(dtype=float)
    n_rows = len(realized_values)
    decision_rows = realized_aligned.index.get_indexer(requested.index)
    worst = 0.0
    for decision_row, (_, requested_row) in zip(decision_rows, requested.iterrows(), strict=True):
        fill_row = decision_row + fill_lag
        requested_values = requested_row.to_numpy(dtype=float)
        if decision_row < 0 or fill_row >= n_rows or np.isnan(requested_values).all():
            continue
        divergence = np.abs(realized_values[fill_row] - requested_values)
        worst = max(worst, float(np.nanmax(divergence)))
    if worst > tolerance:
        raise ValueError(
            f"realized allocations diverge from requested by {worst} "
            f"(> tolerance {tolerance}); the cash_sharing + multi-asset leverage "
            "mis-fill under-traded a leg or drifted the book net-long"
        )


def _realized_weights_at_fill(
    *,
    realized: pd.DataFrame,
    index: pd.Index,
    alloc_idx_arr: np.ndarray,
) -> list[dict[str, Any]]:
    if len(alloc_idx_arr) == 0:
        return []
    unique_row_idxs = sorted({int(row_idx) for row_idx in alloc_idx_arr})
    records: list[dict[str, Any]] = []
    for row_idx in unique_row_idxs:
        ts = index[row_idx]
        row = realized.loc[ts]
        records.append(
            {
                "date": _scalar(ts),
                "weights": {
                    _column_label(col): float(value)
                    for col, value in row.items()
                },
            }
        )
    return records


def _serialize_sparse_frame(frame: pd.DataFrame) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for ts, row in frame.iterrows():
        rows.append(
            {
                "date": _scalar(ts),
                "weights": {
                    _column_label(col): _scalar(value)
                    for col, value in row.items()
                    if not (isinstance(value, float) and np.isnan(value))
                },
            }
        )
    return {
        "columns": [_column_label(col) for col in frame.columns],
        "rows": rows,
    }


def _column_label(column: Any) -> str:
    if isinstance(column, tuple):
        return "__".join(map(str, column))
    return str(column)


def _candidate_label(candidate_index: pd.Index, col: int) -> Any:
    if col < 0 or col >= len(candidate_index):
        return None
    value = candidate_index[col]
    if isinstance(value, tuple):
        return "__".join(map(str, value))
    return _scalar(value)


def _order_rejection_counts(pf: vbt.Portfolio) -> dict[str, int]:
    records = pf.logs.records_readable
    counts: Counter[str] = Counter()
    if "[RES] Status Info" in records.columns:
        for value in records["[RES] Status Info"].tolist():
            if value is None:
                continue
            text = str(value)
            if text in ORDER_REJECTION_STATUSES:
                counts[text] += 1
    return {status: int(counts.get(status, 0)) for status in ORDER_REJECTION_STATUSES}


def _validate_allocations_frame(close: pd.DataFrame, allocations: pd.DataFrame) -> None:
    if close.empty or len(close.columns) == 0:
        raise ValueError("portfolio close input must contain at least one row and symbol column")
    _assert_same_index("allocations", close, allocations)
    _assert_same_columns("allocations", close, allocations)
    _assert_numeric_non_null_close(close)


def _candidate_group_ids(columns: pd.MultiIndex) -> list[Any]:
    candidate_levels = [name for name in columns.names if name != SYMBOL_LEVEL]
    if len(candidate_levels) == 1:
        return list(dict.fromkeys(columns.get_level_values(candidate_levels[0])))
    return list(dict.fromkeys(columns.droplevel(SYMBOL_LEVEL)))



def _assert_same_index(name: str, expected: pd.DataFrame, actual: pd.DataFrame) -> None:
    if not actual.index.equals(expected.index):
        raise ValueError(f"portfolio {name} input index must match Close index exactly")


def _assert_same_columns(name: str, expected: pd.DataFrame, actual: pd.DataFrame) -> None:
    if not actual.columns.equals(expected.columns):
        raise ValueError(f"portfolio {name} input columns must match Close columns exactly")


def _assert_numeric_non_null_close(close: pd.DataFrame) -> None:
    non_numeric = [
        column for column in close.columns if not pd.api.types.is_numeric_dtype(close[column])
    ]
    if non_numeric:
        raise ValueError(f"portfolio Close input has non-numeric columns {non_numeric}")
    if close.isna().any().any():
        raise ValueError("portfolio Close input contains null prices")


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


def _scalar(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "item"):
        try:
            return value.item()
        except (TypeError, ValueError):
            return value
    return value
