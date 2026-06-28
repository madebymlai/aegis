from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np
import pandas as pd
from aegis_runtime import gate
from nautilus_trader.model.identifiers import InstrumentId
from numba import njit
from vectorbtpro import vbt
from vectorbtpro.base.flex_indexing import flex_select_1d_pc_nb, flex_select_nb
from vectorbtpro.portfolio.enums import Direction, OrderStatusInfo, SizeType

from research.aegis_research.component_registry.contracts import SYMBOL_LEVEL
from research.aegis_research.configuration import InstrumentBandConfig, PortfolioConfig
from research.aegis_research.exposure_validation import (
    validate_exposure,
)

_SINGLE_CANDIDATE_ID = "single"
# Short borrow carry mechanism (ADR-0008): a per-bar, short-masked ``cash_dividends`` array
# of ``(net_rate / periods_per_year) * close``. ``* live position`` gives drifted notional,
# only-while-open, and the cost-on-short / credit-on-long sign for free — hence the long-leg
# mask (a positive per-share value would otherwise *credit* a long position).
# Margin interest (``int_rate x borrowed_cash``) needs ``vbt.pf_nb.get_debt_nb(c)``;
# the from-signals substrate exposes the callback context needed for that future work.
VBT_PF_METHOD = "from_signals"
VBT_RESOLVED_SIZE_TYPE = "targetpercent"
VBT_LEVERAGE_MODE = "eager"
# Surplus buying power for the VBT engine, expressed as a multiple of gross_cap.
# Exposure Validation is the sole gross_cap enforcer (ADR-0007 amended 2026-06-09);
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
# VBT ``price`` strings: both ``nextopen``/``nextclose`` set ``from_ago=1`` (shift one
# bar -> no same-bar look-ahead); they differ only in which price of bar t+1 they fill at.
VBT_NEXT_OPEN_PRICE = "nextopen"
VBT_NEXT_CLOSE_PRICE = "nextclose"
# Fill-timing -> VBT ``price``. ``same_close`` maps to None: no ``price`` override, so the
# engine fills at the current bar's close (from_ago=0, look-ahead — mechanics tests only).
_VBT_PRICE_BY_FILL_TIMING: dict[str, str | None] = {
    "next_open": VBT_NEXT_OPEN_PRICE,
    "next_close": VBT_NEXT_CLOSE_PRICE,
    "same_close": None,
}
_gate_nb = njit(gate)
_SIZE_TYPE_TARGET_PERCENT = int(SizeType.TargetPercent)
_DIRECTION_BOTH = int(Direction.Both)


@njit
def _order_val_price_nb(c, price, val_price, order_i, col):
    order_price = flex_select_nb(price, order_i, col)
    order_val_price = flex_select_nb(val_price, c.i, col)
    if np.isinf(order_val_price) and order_val_price > 0:
        if np.isinf(order_price) and order_price > 0:
            return flex_select_nb(c.close, c.i, col)
        if np.isinf(order_price) and order_price < 0:
            return flex_select_nb(c.open, c.i, col)
        return order_price
    if np.isnan(order_val_price) or (np.isinf(order_val_price) and order_val_price < 0):
        return c.last_val_price[col]
    return order_val_price


@njit
def _position_value_nb(c, price, val_price, order_i, col):
    """Drifted notional of one column's position at the order valuation price."""
    col_price = _order_val_price_nb(c, price, val_price, order_i, col)
    multiplier = flex_select_1d_pc_nb(c.multiplier, col)
    return c.last_position[col] * col_price * multiplier


@njit
def _group_value_nb(c, price, val_price, order_i):
    """Group value at the order valuation price (cash + drifted positions).

    Recomputed from current-bar prices rather than read off ``c.last_value``,
    which lags a bar at the pre-order-segment stage (the engine sizes the pending
    order off that same stale value). Cash sharing is always on for the batched
    sim, so the group's cash is ``last_cash[group]``.
    """
    group_value = c.last_cash[c.group]
    for col in range(c.from_col, c.to_col):
        group_value += _position_value_nb(c, price, val_price, order_i, col)
    return group_value


@njit
def _realized_weight_nb(c, price, val_price, order_i, col, group_value):
    """The column's live-drifted weight: its position value as a fraction of group value."""
    if c.last_position[col] == 0.0:
        return 0.0
    return _position_value_nb(c, price, val_price, order_i, col) / group_value


@njit
def _band_pre_order_segment_nb(c, target_alloc, price, val_price, from_ago, up_arr, down_arr):
    """Apply the shared DriftBand no-trade gate to each pending order in the segment.

    Runs once per order-bearing segment, after ``order_mode`` has resolved the
    pending orders but before they execute. ``skip_empty`` omits segments with no
    pending order, so the gate fires only on rebalance bars - not on every bar like
    a per-element ``adjust_func_nb`` would (the dominant cost was the per-cell
    callback invocation, not its body).

    The gate decides on the *target weight* read from ``target_alloc`` (the original
    allocations - by this stage ``order_mode`` has overwritten its own ``size`` array
    with resolved order amounts) against the live-drifted ``realized`` weight, valued
    at the order price exactly as the retired adjust path did. ``gate`` returns either
    ``realized`` (hold) or the original ``target`` (trade): a hold suppresses the
    pending order; a trade rewrites it to the target weight with the same
    ``current/sizing`` correction the adjust used, because the engine's pending order
    was sized off ``last_value`` which lags a bar at this stage.
    """
    # ``from_ago`` is column-uniform here (one fill-timing price string for the whole
    # book - see ``_VBT_PRICE_BY_FILL_TIMING``), so a single ``order_i`` read off
    # ``c.from_col`` indexes every column's row correctly. A per-column ``from_ago``
    # would need ``order_i`` recomputed inside the loop.
    order_i = c.i - abs(int(flex_select_nb(from_ago, c.i, c.from_col)))
    if order_i < 0:
        return ()
    group_value = _group_value_nb(c, price, val_price, order_i)
    # A zero-NAV group has no weights to gate; no-op the segment rather than divide
    # by it (Define-Errors-Out-of-Existence). Unreachable on real runs - the shared
    # cash term keeps group value positive - so it never perturbs scored results.
    if group_value == 0.0:
        return ()
    sizing_group_value = c.last_value[c.group]
    for col in range(c.from_col, c.to_col):
        if np.isnan(c.order_info[col]["size"]):
            continue
        target_w = float(flex_select_nb(target_alloc, order_i, col))
        if np.isnan(target_w):
            continue
        realized_w = _realized_weight_nb(c, price, val_price, order_i, col, group_value)
        up = float(flex_select_nb(up_arr, order_i, col))
        down = float(flex_select_nb(down_arr, order_i, col))
        resolved_w = _gate_nb(realized_w, target_w, up, down)
        if resolved_w == realized_w:
            c.order_info[col]["size"] = np.nan
        elif sizing_group_value != 0.0:
            # Re-express the order as a signed target-percent so the executor
            # re-resolves it against ``last_value`` (sizing_group_value) - which lags
            # a bar - cancelling the engine's stale sizing back to ``resolved_w`` of
            # the current value. ``order_mode`` resolves orders to plain amounts; the
            # gate deliberately normalizes every traded order to one signed
            # target-percent under direction Both (the buy/sell and long/short sign
            # live in the value, not a LongOnly/ShortOnly flag), so set both fields
            # together regardless of ``config.direction``. Sign-safe because exposure
            # validation already constrains each target's sign to ``config.direction``
            # (longonly => target >= 0, shortonly => target <= 0), so Both never admits
            # a position the configured direction forbids.
            c.order_info[col]["size"] = resolved_w * group_value / sizing_group_value
            c.order_info[col]["size_type"] = _SIZE_TYPE_TARGET_PERCENT
            c.order_info[col]["direction"] = _DIRECTION_BOTH
    return ()


def _execution_settings(
    fill_timing: str, open_: pd.DataFrame | None
) -> dict[str, Any]:
    """Resolve VBT fill-timing kwargs from the explicit ``fill_timing`` decision.

    ``next_close`` fills at bar t+1's close, ``next_open`` at bar t+1's open (the only
    mode that reads ``open_``), ``same_close`` at bar t's own close. The open array is
    supplied only when the timing actually needs it.
    """
    price = _VBT_PRICE_BY_FILL_TIMING[fill_timing]
    if price is None:
        return {}
    if price == VBT_NEXT_OPEN_PRICE:
        if open_ is None:
            raise ValueError(
                "next_open fill_timing requires Open prices, but none were provided"
            )
        return {"price": price, "open": open_}
    return {"price": price}


def _resolve_fees(
    price_frame: pd.DataFrame,
    config: PortfolioConfig,
    fees_by_symbol: pd.Series | None,
) -> Any:
    """The per-column ``fees`` array for the engine - one path.

    Every leg pays ``config.fees`` unless a per-symbol override is supplied (the
    FX-conversion surcharge on non-base legs), in which case that replaces it.
    A book with no surcharge simply gets a uniform array - a no-op, not a second
    code path. The result is a ROW vector ``(1, n_cols)`` so the engine broadcasts
    one fee down each column's rows (a bare 1d array reads as a ``(n_cols, 1)``
    column instead).
    """
    symbols = price_frame.columns.get_level_values(SYMBOL_LEVEL)
    fees = (
        pd.Series(config.fees, index=symbols.unique())
        if fees_by_symbol is None
        else fees_by_symbol
    )
    return fees.reindex(symbols).to_numpy().reshape(1, -1)


def _build_portfolio(
    price_frame: pd.DataFrame,
    allocations: pd.DataFrame,
    config: PortfolioConfig,
    *,
    open_frame: pd.DataFrame | None,
    market_index: pd.Index | None,
    group_by: Any,
    periods_per_year: int,
    fees_by_symbol: pd.Series | None = None,
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
    exec_kwargs = _execution_settings(config.fill_timing, open_frame)
    band_up, band_down = _band_arrays(masked, config)
    # The gate reads targets from our own copy of the allocations: ``order_mode``
    # overwrites its internal ``size`` array with resolved order amounts before the
    # pre-order-segment callback runs.
    target_alloc = np.ascontiguousarray(masked.to_numpy(), dtype=np.float64)
    pf = vbt.Portfolio.from_optimizer(
        price_frame,
        pfo,
        pf_method=VBT_PF_METHOD,
        size_type=VBT_RESOLVED_SIZE_TYPE,
        min_size=np.nan,
        pre_order_segment_func_nb=_band_pre_order_segment_nb,
        pre_order_segment_args=(
            target_alloc,
            vbt.Rep("price"),
            vbt.Rep("val_price"),
            vbt.Rep("from_ago"),
            band_up,
            band_down,
        ),
        direction=config.direction,
        cash_sharing=True,
        call_seq="auto",
        group_by=group_by,
        fees=_resolve_fees(price_frame, config, fees_by_symbol),
        fixed_fees=config.fixed_fee,
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


def _band_arrays(
    allocations: pd.DataFrame,
    config: PortfolioConfig,
) -> tuple[np.ndarray, np.ndarray]:
    shape = (1, len(allocations.columns))
    up = np.full(shape, config.band_up, dtype=float)
    down = np.full(shape, config.band_down, dtype=float)
    if not config.band_overrides:
        return up, down
    symbols = allocations.columns.get_level_values(SYMBOL_LEVEL)
    for col, symbol in enumerate(symbols):
        override = _band_override_for_symbol(config, symbol)
        if override is None:
            continue
        up[0, col] = override.up
        down[0, col] = override.down
    return up, down


def _band_override_for_symbol(
    config: PortfolioConfig, symbol: object
) -> InstrumentBandConfig | None:
    exact_key = symbol.value if isinstance(symbol, InstrumentId) else str(symbol)
    override = config.band_overrides.get(exact_key)
    if override is None and isinstance(symbol, InstrumentId):
        override = config.band_overrides.get(symbol.symbol.value)
    return override


def _assert_no_nocash_rejection(pf: vbt.Portfolio) -> None:
    """Exact tripwire: any NoCash rejection is a genuine bug.

    With surplus buying power (leverage = k x gross_cap, k >= 2) the engine always has
    headroom to fill every Exposure-Limits-compliant order.  A NoCash rejection under
    these conditions is not a tolerance-graded under-fill — it is a genuine mis-fill
    that must fail closed so no Candidate is silently scored on a corrupted book.
    """
    records = pf.logs.records
    if records.empty:
        return
    if (records["res_status_info"] == OrderStatusInfo.NoCash).any():
        raise ValueError(
            "portfolio simulation produced an unexpected NoCash order rejection: "
            "the engine exhausted buying power on an Exposure-Limits-compliant book"
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


def fx_adjusted_fees(
    instrument_ids: Sequence[InstrumentId],
    currency_by_instrument_id: Mapping[InstrumentId, str],
    base_currency: str,
    base_fee: float,
    fx_conversion_cost: float,
) -> pd.Series:
    """Per-instrument trade fee, adding the FX conversion cost to foreign legs.

    A foreign leg (one whose currency is not the book's base) crosses an FX
    spread on every trade - the EUR->ccy buy and the ccy->EUR sell - so it pays
    ``base_fee + fx_conversion_cost``; a base-currency leg pays ``base_fee``.
    """
    fees = {
        instrument_id: base_fee
        + (
            fx_conversion_cost
            if _requires_conversion(
                currency_by_instrument_id[instrument_id], base_currency
            )
            else 0.0
        )
        for instrument_id in instrument_ids
    }
    return pd.Series(fees)


def _requires_conversion(quote_currency: str, base_currency: str) -> bool:
    return quote_currency.upper() != base_currency.upper()


def simulate_single_book(
    close: pd.DataFrame,
    allocations: pd.DataFrame,
    config: PortfolioConfig,
    *,
    open_: pd.DataFrame | None = None,
    market_index: pd.Index | None = None,
    periods_per_year: int = 252,
    fees_by_symbol: pd.Series | None = None,
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
        fees_by_symbol=fees_by_symbol,
    )


def simulate_portfolio_batch(
    close: pd.DataFrame,
    allocations: pd.DataFrame,
    config: PortfolioConfig,
    *,
    open_: pd.DataFrame | None = None,
    market_index: pd.Index | None = None,
    periods_per_year: int,
    fees_by_symbol: pd.Series | None = None,
) -> vbt.Portfolio:
    """Simulate a batch of candidate portfolios."""
    _validate_candidate_columns(allocations.columns, field_name="allocations")
    expanded_close = expand_market_frame_to_candidate_columns(
        close,
        allocations.columns,
        feature_name="Close",
    )
    _validate_allocations_frame(expanded_close, allocations)
    validate_exposure(
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
        fees_by_symbol=fees_by_symbol,
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
