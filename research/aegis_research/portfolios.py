from __future__ import annotations

from typing import Any

import pandas as pd
from vectorbtpro import vbt
from vectorbtpro.portfolio.enums import OrderStatusInfo

from research.aegis_research.config import PortfolioConfig
from research.aegis_research.portfolio_policy import (
    apply_executable_mask_and_terminal_liquidation,
    assert_signed_allocations_within_caps,
)

SYMBOL_LEVEL = "symbol"
# Short borrow carry mechanism (ADR-0008): a per-bar, short-masked ``cash_dividends`` array
# of ``(net_rate / periods_per_year) * close``. ``* live position`` gives drifted notional,
# only-while-open, and the cost-on-short / credit-on-long sign for free — hence the long-leg
# mask (a positive per-share value would otherwise *credit* a long position).
# Margin interest (``int_rate × borrowed_cash``) needs ``vbt.pf_nb.get_debt_nb(c)``, which is
# unavailable on ``from_orders``; charging it would require ``from_signals``/``from_order_func``.
# Deferred by architectural boundary, not punted (see ADR-0008).
VBT_PF_METHOD = "from_orders"
VBT_RESOLVED_SIZE_TYPE = "targetpercent"
VBT_LEVERAGE_MODE = "eager"
# Next-open execution: a target decided from bar t's close fills at bar t+1's open.
# VBT's ``price="nextopen"`` sets ``from_ago=1`` (shift one bar) and fills at the open,
# which is the canonical VBT way to avoid same-bar look-ahead without manual shifting.
VBT_NEXT_OPEN_PRICE = "nextopen"


def _execution_settings(open_: pd.DataFrame | None) -> dict[str, Any]:
    """Resolve VBT fill-timing kwargs.

    With ``open_`` provided, fill at the next bar's open (``price="nextopen"`` ->
    ``from_ago=1``) so a target decided from bar t's close cannot fill on bar t —
    eliminating same-bar look-ahead. Without it, fall back to close fills.
    """
    if open_ is None:
        return {}
    return {"price": VBT_NEXT_OPEN_PRICE, "open": open_}


def _build_portfolio(
    price_frame: pd.DataFrame,
    allocations: pd.DataFrame,
    config: PortfolioConfig,
    *,
    open_frame: pd.DataFrame | None,
    market_index: pd.Index | None,
    group_by: Any,
    periods_per_year: int,
) -> vbt.Portfolio:
    """Mask allocations, build the PFO, and run ``from_optimizer``.

    Shared core for the single-group and per-candidate simulations: identical
    masking, allocation-filling, short-financing carry, and execution settings; only
    ``group_by`` (and whether the frames are candidate-expanded) differs between the
    two callers.
    """
    masked, _ = apply_executable_mask_and_terminal_liquidation(
        allocations,
        market_index=market_index,
    )
    pfo = vbt.PFO.from_filled_allocations(
        masked,
        valid_only=True,
        nonzero_only=False,
        unique_only=False,
    )
    exec_kwargs = _execution_settings(open_frame)
    return vbt.Portfolio.from_optimizer(
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
        cash_dividends=short_masked_cash_dividends(
            price_frame, allocations, config, periods_per_year=periods_per_year
        ),
        log=True,
        **exec_kwargs,
    )


# Maximum allowed allocation-pct gap between a NoCash-rejected order's requested size and
# the held position.  A gap below this is a harmless maintenance no-op (the book already
# holds the target); a gap above it is a genuine mis-fill (the order silently failed).
_NOCASH_ALLOC_MISMATCH_TOLERANCE = 0.01
# Orders with a requested size at or below this absolute value are treated as zero-sized
# (VBT may emit them as bookkeeping artifacts) and skipped by the NoCash guard.
_NEGLIGIBLE_ORDER_SIZE = 1e-9


def _assert_no_nocash_rejection(pf: vbt.Portfolio) -> None:
    """Fail-closed: detect unexpected NoCash order rejections in the batched simulation.

    Reads the native typed ``res_status_info`` column from ``pf.logs.records`` (an
    O(records) pass that avoids building a human-readable frame or materializing
    allocations).  Rejects only when a NoCash rejection represents a genuine allocation
    mis-fill — the requested target percent differs measurably from the current holding
    and the order silently failed, corrupting the book.

    A harmless no-op (VBT re-executes an unchanged target when free-cash is zero) has
    the position already matching the target, so the allocation gap stays below
    ``_NOCASH_ALLOC_MISMATCH_TOLERANCE`` and is silently accepted.
    """
    records = pf.logs.records
    if records.empty:
        return
    no_cash = records[records["res_status_info"] == OrderStatusInfo.NoCash]
    if no_cash.empty:
        return
    has_size = abs(no_cash["req_size"]) > _NEGLIGIBLE_ORDER_SIZE
    if not has_size.any():
        return
    no_cash_with_size = no_cash[has_size]
    has_value = no_cash_with_size["st0_value"] > 0
    if not has_value.any():
        return
    no_cash_with_value = no_cash_with_size[has_value]
    current_allocation = (
        no_cash_with_value["st0_position"]
        * no_cash_with_value["st0_val_price"]
        / no_cash_with_value["st0_value"]
    )
    mismatch = abs(current_allocation - no_cash_with_value["req_size"])
    if (mismatch > _NOCASH_ALLOC_MISMATCH_TOLERANCE).any():
        worst = float(mismatch.max())
        raise ValueError(
            f"portfolio simulation produced an unexpected NoCash order rejection "
            f"(allocation mismatch {worst:.4f} exceeds tolerance "
            f"{_NOCASH_ALLOC_MISMATCH_TOLERANCE}): "
            "the cash_sharing + multi-asset leverage mis-fill under-traded a leg "
            "or drifted the book net-long"
        )


def short_masked_cash_dividends(
    close: pd.DataFrame,
    allocations: pd.DataFrame,
    config: PortfolioConfig,
    *,
    periods_per_year: int,
) -> pd.DataFrame:
    """Build the per-bar short-financing carry array (ADR-0008).

    ``cash_dividends[sym, t] = (net_rate / periods_per_year) * close[sym, t]``, masked to the
    short legs (ffilled signed allocation ``< 0``); long legs are ``0``. ``net_rate`` is
    ``short_borrow_rate - short_rebate_rate``, floored at zero (a rebate above borrow does not
    pay the book to hold a short). VBT multiplies this per-share value by the live position to
    produce drifted-notional carry, charged only while the short is open, with a positive
    value costing the short — which is why the long legs must be zeroed.
    """
    net_rate = max(config.short_borrow_rate - config.short_rebate_rate, 0.0)
    cash_dividends = pd.DataFrame(0.0, index=close.index, columns=close.columns)
    if net_rate == 0.0:
        return cash_dividends
    rate_per_bar = net_rate / periods_per_year
    short_mask = allocations.ffill() < 0
    cash_dividends[short_mask] = rate_per_bar * close[short_mask]
    return cash_dividends


def simulate_single_book(
    close: pd.DataFrame,
    allocations: pd.DataFrame,
    config: PortfolioConfig,
    *,
    open_: pd.DataFrame | None = None,
    market_index: pd.Index | None = None,
    periods_per_year: int = 252,
) -> vbt.Portfolio:
    """Test-support wrapper: simulate one book through the batched path.

    Wraps plain-symbol ``allocations`` into a one-candidate MultiIndex, then
    delegates to ``simulate_portfolio_batch``.  Only for carry/mechanics tests
    that need plain symbol columns — not a production interface.
    """
    columns = pd.MultiIndex.from_product(
        [["single"], allocations.columns],
        names=["candidate_id", SYMBOL_LEVEL],
    )
    alloc_mi = pd.DataFrame(
        allocations.to_numpy(), index=allocations.index, columns=columns
    )
    return simulate_portfolio_batch(
        close,
        alloc_mi,
        config,
        open_=open_,
        market_index=market_index,
        periods_per_year=periods_per_year,
    )


def simulate_portfolio_batch(
    close: pd.DataFrame,
    allocations: pd.DataFrame,
    config: PortfolioConfig,
    *,
    open_: pd.DataFrame | None = None,
    market_index: pd.Index | None = None,
    periods_per_year: int,
) -> vbt.Portfolio:
    _validate_candidate_columns(allocations.columns, field_name="allocations")
    expanded_close = expand_market_frame_to_candidate_columns(
        close,
        allocations.columns,
        feature_name="Close",
    )
    _validate_allocations_frame(expanded_close, allocations)
    assert_signed_allocations_within_caps(
        allocations,
        gross_cap=config.gross_cap,
        net_cap=config.net_cap,
        direction=config.direction,
    )
    expanded_open = (
        None
        if open_ is None
        else expand_market_frame_to_candidate_columns(
            open_, allocations.columns, feature_name="Open"
        )
    )
    pf = _build_portfolio(
        expanded_close,
        allocations,
        config,
        open_frame=expanded_open,
        market_index=market_index,
        group_by=vbt.ExceptLevel(SYMBOL_LEVEL),
        periods_per_year=periods_per_year,
    )
    _assert_no_nocash_rejection(pf)
    return pf


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


def _validate_allocations_frame(close: pd.DataFrame, allocations: pd.DataFrame) -> None:
    if close.empty or len(close.columns) == 0:
        raise ValueError("portfolio close input must contain at least one row and symbol column")
    _assert_same_index("allocations", close, allocations)
    _assert_same_columns("allocations", close, allocations)
    _assert_numeric_non_null_close(close)


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
