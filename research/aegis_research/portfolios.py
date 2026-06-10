from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from vectorbtpro import vbt
from vectorbtpro.portfolio.enums import OrderStatusInfo

from research.aegis_research.allocation_policy import (
    assert_signed_allocations_within_caps,
)
from research.aegis_research.component_registry.contracts import SYMBOL_LEVEL
from research.aegis_research.configuration import PortfolioConfig

_SINGLE_CANDIDATE_ID = "single"
# Short borrow carry mechanism (ADR-0008): a per-bar, short-masked ``cash_dividends`` array
# of ``(net_rate / periods_per_year) * close``. ``* live position`` gives drifted notional,
# only-while-open, and the cost-on-short / credit-on-long sign for free — hence the long-leg
# mask (a positive per-share value would otherwise *credit* a long position).
# Margin interest (``int_rate x borrowed_cash``) needs ``vbt.pf_nb.get_debt_nb(c)``, which is
# unavailable on ``from_orders``; charging it would require ``from_signals``/``from_order_func``.
# Deferred by architectural boundary, not punted (see ADR-0008).
VBT_PF_METHOD = "from_orders"
VBT_RESOLVED_SIZE_TYPE = "targetpercent"
VBT_LEVERAGE_MODE = "eager"
# Surplus buying power for the VBT engine, expressed as a multiple of gross_cap.
# The Allocation Policy gate is the sole gross_cap enforcer (ADR-0007 amended 2026-06-09);
# giving the engine k x gross_cap of headroom (k >= 2) prevents the engine from silently
# under-filling orders during compliant at-cap rebalance transitions that need >1x cap
# of temporary buying power (e.g. sell A -> buy B when call_seq="auto" sequences buys
# before sells). The multiplier is tied to gross_cap (never np.inf) to stay bounded for
# any config, avoiding a 0 x inf division-by-zero at zero free cash.
#
# k = 2 is the floor, not the value: under drawdown drift a compliant transition can
# transiently need ~3x cap (book at cap + equity halves -> drifted gross ~2x cap relative
# to current equity, co-held with the new at-cap book when sequencing fails). k = 5 keeps
# legitimate Runs clear of the tripwire; unused headroom costs nothing (margin interest is
# unmodeled, ADR-0008). If the tripwire ever fires on a legitimate Run, raise k — never
# reintroduce a tolerance (ADR-0011 amendment).
_GROSS_CAP_LEVERAGE_MULTIPLIER = 5
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
    """Build a simulated portfolio from allocations.

    Masks gap rows as non-executable, force-liquidates the terminal row to
    cash, builds the PFO, runs ``from_optimizer``, and asserts no NoCash
    rejection occurred.
    """
    masked = _apply_non_executable_mask(allocations, market_index=market_index)
    # Terminal liquidation: zero the final row so runs end in realized cash.
    if not masked.empty:
        masked.iloc[-1, :] = 0.0
    pfo = vbt.PFO.from_filled_allocations(
        masked,
        valid_only=True,
        nonzero_only=False,
        unique_only=False,
    )
    exec_kwargs = _execution_settings(open_frame)
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
        leverage=config.gross_cap * _GROSS_CAP_LEVERAGE_MULTIPLIER,
        leverage_mode=VBT_LEVERAGE_MODE,
        cash_dividends=short_masked_cash_dividends(
            price_frame, allocations, config, periods_per_year=periods_per_year
        ),
        log=True,
        **exec_kwargs,
    )
    _assert_no_nocash_rejection(pf)
    return pf


def _assert_no_nocash_rejection(pf: vbt.Portfolio) -> None:
    """Exact tripwire: any NoCash rejection is a genuine bug.

    With surplus buying power (leverage = k x gross_cap, k >= 2) the engine always has
    headroom to fill every Allocation-Policy-compliant order.  A NoCash rejection under
    these conditions is not a tolerance-graded under-fill — it is a genuine mis-fill
    that must fail closed so no Candidate is silently scored on a corrupted book.
    """
    records = pf.logs.records
    if records.empty:
        return
    if (records["res_status_info"] == OrderStatusInfo.NoCash).any():
        raise ValueError(
            "portfolio simulation produced an unexpected NoCash order rejection: "
            "the engine exhausted buying power on an Allocation-Policy-compliant book"
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
        [[_SINGLE_CANDIDATE_ID], allocations.columns],
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
    """Simulate a batch of candidate portfolios."""
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
    return _build_portfolio(
        expanded_close,
        allocations,
        config,
        open_frame=expanded_open,
        market_index=market_index,
        group_by=vbt.ExceptLevel(SYMBOL_LEVEL),
        periods_per_year=periods_per_year,
    )


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


def _apply_non_executable_mask(
    allocations: pd.DataFrame,
    *,
    market_index: pd.Index | None,
) -> pd.DataFrame:
    """Return the masked frame with gap rows NaN'd.

    Rebalance rows whose bar is not the immediate successor of the previous
    row's bar in the provided market index are NaN'd so the simulator holds
    instead of trading.
    """
    if allocations.empty or len(allocations.columns) == 0:
        return allocations.copy()
    executable = _next_open_executable_mask(allocations.index, market_index)
    masked = allocations.copy().astype(float)
    non_executable_rows = ~executable
    if non_executable_rows.any():
        masked.iloc[non_executable_rows.to_numpy(), :] = np.nan
    return masked


def count_non_executable_rows(
    window_index: pd.Index,
    market_index: pd.Index | None,
) -> int:
    """Count window rows that would be held (non-executable) under next-open rules.

    Pure index geometry — the seam cost of one window: the number of rows in
    ``window_index`` whose bar is not the immediate successor of the previous
    row's bar in ``market_index``, independent of allocation values. Raises
    ``ValueError`` if ``market_index`` does not contain every window row.
    """
    executable = _next_open_executable_mask(window_index, market_index)
    return int((~executable).sum())


def _next_open_executable_mask(
    index: pd.Index,
    market_index: pd.Index | None,
) -> pd.Series:
    """Return a boolean Series marking rows executable under next-open rules.

    A row is executable only if its bar is the immediate successor of the
    previous row's bar in the market index. The first row is always executable.
    """
    executable = pd.Series(True, index=index)
    if market_index is None or len(index) == 0:
        return executable
    market_positions = pd.Series(range(len(market_index)), index=market_index)
    try:
        positions = market_positions.loc[index].to_numpy()
    except KeyError as error:
        raise ValueError(
            "portfolio market_index must contain all allocation rows"
        ) from error
    if len(index) < 2:
        return executable
    contiguous = positions[1:] == positions[:-1] + 1
    executable.iloc[1:] = contiguous
    return executable
