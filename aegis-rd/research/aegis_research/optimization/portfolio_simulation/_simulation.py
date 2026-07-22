from __future__ import annotations

import hashlib
import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from aegis_data.distributions import Distribution
from aegis_runtime import (
    SLEEVE_GROSS_LIMIT,
    DriftBand,
    ExposureLimits,
    debit_interest,
    gate,
    validate_exposure,
)
from aegis_runtime.currency import CurrencyConversion
from nautilus_trader.model.identifiers import InstrumentId
from numba import njit
from vectorbtpro import vbt
from vectorbtpro.base.flex_indexing import flex_select_1d_pc_nb, flex_select_nb
from vectorbtpro.portfolio.enums import Direction, OrderStatusInfo, SizeType

from research.aegis_research.component_registry.contracts import SYMBOL_LEVEL
from research.aegis_research.configuration import PortfolioConfig
from research.aegis_research.market_data.identity import as_instrument_id
from research.aegis_research.optimization.portfolio_simulation.resolved_book import (
    ResolvedBook,
)

# Short borrow carry mechanism (ADR-0008): a per-bar, short-masked ``cash_dividends`` array
# of ``(net_rate / periods_per_year) * close``. ``* live position`` gives drifted notional,
# only-while-open, and the cost-on-short / credit-on-long sign for free — hence the long-leg
# mask (a positive per-share value would otherwise *credit* a long position).
# Margin interest is separate: it charges broker-visible negative group cash through
# ``cash_earnings``. VBT ``pf.debt`` is eager-mode bookkeeping, not a broker loan, so
# it must never be the charge base. Futures ids are spot-simmed by VBT; their signed
# marked position value is added back to raw group cash before charging, because a broker
# sees daily variation margin rather than a full-notional cash loan. Locked initial
# margin is still not modeled as consumed cash, so levered mixed futures/spot books
# undercharge rate x margin requirement; that is the only documented futures residual.
VBT_PF_METHOD = "from_signals"
VBT_RESOLVED_SIZE_TYPE = "targetpercent"
VBT_LEVERAGE_MODE = "eager"
VBT_STATICIZED_CACHE_ENV = "AERD_VBT_STATICIZED_CACHE_DIR"
# Surplus buying power for the VBT engine, as a multiple of the unit-gross sleeve
# contract (SLEEVE_GROSS_LIMIT; aegis-rd-ui1m). Exposure Validation is the sole
# gross enforcer (ADR-0007 amended 2026-06-09); giving the engine k x unit gross
# of headroom (k >= 2) prevents it from silently under-filling orders during
# compliant at-cap rebalance transitions that need >1x of temporary buying power
# (e.g. sell A -> buy B when call_seq="auto" sequences buys before sells; the vbt
# maintainer confirms no processing order can guarantee a sell frees cash, and
# leverage headroom is one of the two sanctioned fixes). The product stays finite
# (never np.inf) to remain bounded, avoiding a 0 x inf division-by-zero at zero
# free cash.
#
# k = 2 is the floor, not the value: under drawdown drift a compliant transition can
# transiently need ~3x (book at cap + equity halves -> drifted gross ~2x relative
# to current equity, co-held with the new at-cap book when sequencing fails). k = 5 keeps
# legitimate Runs clear of the tripwire. Margin interest is priced on negative group cash,
# which decrements by full order notional under eager leverage; ``pf.debt`` is bookkeeping
# and must not be interpreted as the loan. If the tripwire ever fires on a legitimate Run,
# raise k — never reintroduce a tolerance (ADR-0011 amendment).
_SLEEVE_GROSS_LEVERAGE_MULTIPLIER = 5
# VBT ``price`` strings: both ``nextopen``/``nextclose`` set ``from_ago=1`` (shift one
# bar -> no same-bar look-ahead); they differ only in which price of bar t+1 they fill at.
VBT_NEXT_OPEN_PRICE = "nextopen"
VBT_NEXT_CLOSE_PRICE = "nextclose"
PORTFOLIO_REPLAY_CONTRACT_SCHEMA_VERSION = "portfolio_replay_contract.v1"
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


def _vbt_staticized_callback_path() -> Path:
    return Path(__file__).with_name("_callbacks.py").resolve()


def _vbt_staticized_source_paths() -> tuple[Path, ...]:
    return (
        _vbt_staticized_callback_path(),
        Path(__file__).resolve(),
        Path(gate.__code__.co_filename).resolve(),
        Path(debit_interest.__code__.co_filename).resolve(),
    )


def _vbt_staticized_cache_key() -> str:
    fingerprint = hashlib.sha256()
    for path in _vbt_staticized_source_paths():
        fingerprint.update(str(path).encode("utf-8"))
        fingerprint.update(b"\0")
        fingerprint.update(path.read_bytes())
        fingerprint.update(b"\0")
    return fingerprint.hexdigest()[:12]


def portfolio_replay_implementation_fingerprint() -> str:
    """Hash replay implementation sources without environment-specific paths."""
    fingerprint = hashlib.sha256()
    for path in _vbt_staticized_source_paths():
        fingerprint.update(path.name.encode("utf-8"))
        fingerprint.update(b"\0")
        fingerprint.update(path.read_bytes())
        fingerprint.update(b"\0")
    return fingerprint.hexdigest()


def _vbt_staticized_cache_dir() -> Path:
    override = os.environ.get(VBT_STATICIZED_CACHE_ENV)
    if override:
        cache_dir = Path(override).expanduser()
    else:
        xdg_cache_home = os.environ.get("XDG_CACHE_HOME")
        cache_root = (
            Path(xdg_cache_home).expanduser()
            if xdg_cache_home is not None
            else Path.home() / ".cache"
        )
        cache_dir = (
            cache_root
            / "aegis-rd"
            / "vbt-staticization"
            / f"driftband-{_vbt_staticized_cache_key()}"
        )
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


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
def _band_pre_order_segment_nb(
    c,
    target_alloc,
    price,
    val_price,
    from_ago,
    up_arr,
    down_arr,
    dest_arr,
    cash_earnings,
    margin_day_offsets,
    last_margin_accrual_i,
    futures_mask,
    margin_interest_rate,
):
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
    ``realized`` (hold) or the breach destination — the ``destination_fraction``
    interpolation between band edge and target (1.0 = the target itself): a hold
    suppresses the pending order; a trade rewrites it to the resolved weight with the same
    ``current/sizing`` correction the adjust used, because the engine's pending order
    was sized off ``last_value`` which lags a bar at this stage.
    """
    # ``from_ago`` is column-uniform here (one fill-timing price string for the whole
    # book - see ``_VBT_PRICE_BY_FILL_TIMING``), so a single ``order_i`` read off
    # ``c.from_col`` indexes every column's row correctly. A per-column ``from_ago``
    # would need ``order_i`` recomputed inside the loop.
    order_i = c.i - abs(int(flex_select_nb(from_ago, c.i, c.from_col)))
    _accrue_margin_interest_nb(
        c,
        price,
        val_price,
        order_i,
        cash_earnings,
        margin_day_offsets,
        last_margin_accrual_i,
        futures_mask,
        margin_interest_rate,
    )
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
        dest = float(flex_select_nb(dest_arr, order_i, col))
        resolved_w = _gate_nb(realized_w, target_w, up, down, dest)
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


@njit
def _accrue_margin_interest_nb(
    c,
    price,
    val_price,
    order_i,
    cash_earnings,
    margin_day_offsets,
    last_margin_accrual_i,
    futures_mask,
    margin_interest_rate,
):
    if margin_interest_rate <= 0.0:
        return
    last_i = int(last_margin_accrual_i[c.group])
    elapsed_days = margin_day_offsets[c.i] - margin_day_offsets[last_i]
    if elapsed_days <= 0.0:
        return
    adjusted_cash = c.last_cash[c.group]
    if order_i >= 0:
        for col in range(c.from_col, c.to_col):
            if futures_mask[col]:
                adjusted_cash += _position_value_nb(c, price, val_price, order_i, col)
    charge = debit_interest(adjusted_cash, margin_interest_rate, elapsed_days)
    if charge > 0.0:
        cash_earnings[c.i, c.from_col] -= charge
    last_margin_accrual_i[c.group] = c.i


def _execution_settings(fill_timing: str, open_: pd.DataFrame | None) -> dict[str, Any]:
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
            raise ValueError("next_open fill_timing requires Open prices, but none were provided")
        return {"price": price, "open": open_, "from_ago": None}
    return {"price": price, "from_ago": None}


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
        pd.Series(config.fees, index=symbols.unique()) if fees_by_symbol is None else fees_by_symbol
    )
    return fees.reindex(symbols).to_numpy().reshape(1, -1)


def _futures_mask(columns: pd.Index, futures_roots: Sequence[str]) -> np.ndarray:
    roots = frozenset(str(root) for root in futures_roots)
    if not roots:
        return np.zeros(len(columns), dtype=np.bool_)
    symbols = columns.get_level_values(SYMBOL_LEVEL)
    return np.array([_instrument_root(symbol) in roots for symbol in symbols], dtype=np.bool_)


def _instrument_root(value: object) -> str:
    if isinstance(value, InstrumentId):
        return value.symbol.value
    text = str(value)
    if "." not in text:
        return text
    return InstrumentId.from_str(text).symbol.value


def _build_portfolio(
    price_frame: pd.DataFrame,
    allocations: pd.DataFrame,
    book: ResolvedBook,
    *,
    open_frame: pd.DataFrame | None,
    group_by: Any,
    scored_start: int,
    periods_per_year: int,
    distributions: Sequence[Distribution] | None = None,
    currency_conversion: CurrencyConversion | None = None,
) -> vbt.Portfolio:
    """Build a simulated portfolio from allocations.

    Builds the PFO over the unchanged continuous path, runs ``from_optimizer``,
    and asserts no NoCash rejection occurred.
    """
    config = book.config
    pfo = vbt.PFO.from_filled_allocations(
        allocations,
        valid_only=True,
        nonzero_only=False,
        unique_only=False,
    )
    exec_kwargs = _execution_settings(config.fill_timing, open_frame)
    band_up, band_down, band_destination = _band_arrays(allocations, config, book.instrument_bands)
    # The gate reads targets from our own copy of the allocations: ``order_mode``
    # overwrites its internal ``size`` array with resolved order amounts before the
    # pre-order-segment callback runs.
    target_alloc = np.ascontiguousarray(allocations.to_numpy(), dtype=np.float64)
    margin_day_offsets = _margin_day_offsets(price_frame.index)
    last_margin_accrual_i = np.zeros(_candidate_group_count(allocations.columns), dtype=np.int64)
    futures_mask = _futures_mask(allocations.columns, book.futures_roots)
    cash_dividends = short_masked_cash_dividends(
        price_frame, allocations, config, periods_per_year=periods_per_year
    ) + distribution_cash_dividends(
        price_frame,
        distributions or (),
        currency_conversion=currency_conversion,
    )
    pf = vbt.Portfolio.from_optimizer(
        price_frame,
        pfo,
        pf_method=VBT_PF_METHOD,
        size_type=VBT_RESOLVED_SIZE_TYPE,
        min_size=np.nan,
        pre_order_segment_func_nb=_vbt_staticized_callback_path(),
        pre_order_segment_args=(
            target_alloc,
            vbt.Rep("price"),
            vbt.Rep("val_price"),
            vbt.Rep("from_ago"),
            band_up,
            band_down,
            band_destination,
            vbt.Rep("cash_earnings"),
            margin_day_offsets,
            last_margin_accrual_i,
            futures_mask,
            config.margin_interest_rate,
        ),
        staticized={"path": _vbt_staticized_cache_dir()},
        direction=config.direction,
        cash_sharing=True,
        call_seq="auto",
        group_by=group_by,
        sim_start=scored_start,
        sim_end=len(price_frame.index),
        fees=_resolve_fees(price_frame, config, book.fees_by_symbol),
        fixed_fees=config.fixed_fee,
        size_granularity=_size_granularity(allocations.columns, book),
        slippage=config.slippage,
        init_cash=config.init_cash,
        leverage=SLEEVE_GROSS_LIMIT * _SLEEVE_GROSS_LEVERAGE_MULTIPLIER,
        leverage_mode=VBT_LEVERAGE_MODE,
        cash_earnings=vbt.RepEval("np.full(wrapper.shape_2d, 0.0)"),
        arg_config={"cash_earnings": {"full_shape": True}},
        cash_dividends=cash_dividends,
        log=True,
        save_returns=False,
        # Margin financing accrues through the final simulated row even when no
        # allocation changes there. VBT otherwise skips the pre-order callback
        # on empty segments, which used to be masked by the removed terminal
        # liquidation order.
        skip_empty=False,
        **exec_kwargs,
    )
    _assert_no_nocash_rejection(pf)
    return pf


def _size_granularity(columns: pd.Index, book: ResolvedBook) -> np.ndarray:
    """Broadcast catalog size increments over each Candidate's symbol columns."""

    if book.size_increment_by_instrument is None:
        return np.full((1, len(columns)), np.nan, dtype=float)
    symbols = columns.get_level_values(SYMBOL_LEVEL)
    missing = sorted(
        {
            as_instrument_id(symbol).value
            for symbol in symbols
            if as_instrument_id(symbol) not in book.size_increment_by_instrument
        }
    )
    if missing:
        raise ValueError(
            f"portfolio simulation has no catalog size increment for tradeable columns: {missing}"
        )
    increments = np.array(
        [book.size_increment_by_instrument[as_instrument_id(symbol)] for symbol in symbols],
        dtype=float,
    )
    if (~np.isfinite(increments) | (increments <= 0.0)).any():
        raise ValueError("portfolio simulation size increments must be finite and positive")
    return increments.reshape(1, -1)


def _margin_day_offsets(index: pd.Index) -> np.ndarray:
    """Cumulative elapsed calendar days from the first row for margin accrual."""
    if isinstance(index, pd.DatetimeIndex):
        normalized = index.normalize()
        if normalized.tz is not None:
            normalized = normalized.tz_localize(None)
        days = normalized.to_numpy(dtype="datetime64[D]").astype(np.int64)
        return (days - days[0]).astype(np.float64)
    return np.arange(len(index), dtype=np.float64)


def _candidate_group_count(columns: pd.Index) -> int:
    if isinstance(columns, pd.MultiIndex):
        group_labels = columns.droplevel(SYMBOL_LEVEL)
        return len(group_labels.unique())
    return len(columns)


def _band_arrays(
    allocations: pd.DataFrame,
    config: PortfolioConfig,
    instrument_bands: Mapping[InstrumentId, DriftBand] | None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Per-column ``(up, down, destination_fraction)`` bands over a sleeve-default base.

    *instrument_bands* is the run's resolved instrument → :class:`DriftBand` map (the
    same one the bundle carries), so the sim gates each column with exactly the band the
    export resolved. A column absent from the map gates at the sleeve-wide default.
    """
    shape = (1, len(allocations.columns))
    up = np.full(shape, config.band_up, dtype=float)
    down = np.full(shape, config.band_down, dtype=float)
    destination = np.full(shape, config.band_destination_fraction, dtype=float)
    if not instrument_bands:
        return up, down, destination
    symbols = allocations.columns.get_level_values(SYMBOL_LEVEL)
    for col, symbol in enumerate(symbols):
        band = instrument_bands.get(as_instrument_id(symbol))
        if band is None:
            continue
        up[0, col] = band.up
        down[0, col] = band.down
        destination[0, col] = band.destination_fraction
    return up, down, destination


def _assert_no_nocash_rejection(pf: vbt.Portfolio) -> None:
    """Exact tripwire: any NoCash rejection is a genuine bug.

    With surplus buying power (leverage = k x SLEEVE_GROSS_LIMIT, k >= 2) the engine always has
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


def distribution_cash_dividends(
    close: pd.DataFrame,
    distributions: Sequence[Distribution],
    *,
    currency_conversion: CurrencyConversion | None = None,
) -> pd.DataFrame:
    """Build the unmasked per-share distribution cash array for vbt.

    VBT multiplies ``cash_dividends`` by the signed live position, so a positive
    per-share distribution credits longs and charges shorts without masking.
    """
    cash_dividends = pd.DataFrame(0.0, index=close.index, columns=close.columns)
    if not distributions:
        return cash_dividends
    columns_by_instrument = _columns_by_instrument(close.columns)
    for distribution in distributions:
        target_columns = columns_by_instrument.get(distribution.instrument_id.value, [])
        if not target_columns:
            continue
        ex_date = _matching_index_label(distribution, close.index)
        if ex_date not in cash_dividends.index:
            continue
        amount = _distribution_amount(
            distribution,
            close.index,
            ex_date,
            currency_conversion=currency_conversion,
        )
        cash_dividends.loc[ex_date, target_columns] += amount
    return cash_dividends


def _columns_by_instrument(columns: pd.Index) -> dict[str, list[Any]]:
    values = (
        columns.get_level_values(SYMBOL_LEVEL) if isinstance(columns, pd.MultiIndex) else columns
    )
    out: dict[str, list[Any]] = {}
    for column, value in zip(columns, values, strict=True):
        key = value.value if isinstance(value, InstrumentId) else str(value)
        out.setdefault(key, []).append(column)
    return out


def _matching_index_label(distribution: Distribution, index: pd.Index) -> pd.Timestamp:
    ex_date = pd.Timestamp(distribution.ts_event, tz="UTC")
    if isinstance(index, pd.DatetimeIndex):
        if index.tz is None:
            return ex_date.tz_localize(None)
        return ex_date.tz_convert(index.tz)
    return ex_date


def _distribution_amount(
    distribution: Distribution,
    index: pd.Index,
    ex_date: pd.Timestamp,
    *,
    currency_conversion: CurrencyConversion | None,
) -> float:
    if currency_conversion is None:
        return distribution.amount
    rate = currency_conversion.rate_for(distribution.instrument_id, index)
    return distribution.amount * float(rate.loc[ex_date])


def simulate_portfolio_batch(
    close: pd.DataFrame,
    allocations: pd.DataFrame,
    book: ResolvedBook,
    *,
    scored_start: int = 0,
    open_: pd.DataFrame | None = None,
    periods_per_year: int,
    distributions: Sequence[Distribution] | None = None,
    currency_conversion: CurrencyConversion | None = None,
) -> vbt.Portfolio:
    """Simulate a batch of candidate portfolios under the ResolvedBook's terms."""
    _validate_candidate_columns(allocations.columns, field_name="allocations")
    expanded_close = expand_market_frame_to_candidate_columns(
        close,
        allocations.columns,
        feature_name="Close",
    )
    _validate_allocations_frame(expanded_close, allocations)
    # Candidate-wide Exposure Validation: one kernel gate, each Candidate's columns
    # reduced independently via the opaque label array (the kernel never learns what
    # a Candidate is; the offender phrasing is supplied here).
    validate_exposure(
        allocations,
        ExposureLimits(SLEEVE_GROSS_LIMIT, None, book.config.direction),
        group_by=allocations.columns.droplevel(SYMBOL_LEVEL),
        describe_group=lambda candidate: f"candidate {candidate!r}",
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
        book,
        open_frame=expanded_open,
        group_by=vbt.ExceptLevel(SYMBOL_LEVEL),
        scored_start=scored_start,
        periods_per_year=periods_per_year,
        distributions=distributions,
        currency_conversion=currency_conversion,
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
        raise ValueError(
            f"{feature_name} input is missing symbols for candidate columns: {missing_symbols}"
        )
    expanded = pd.DataFrame(
        {
            column: frame[
                symbol_columns[str(column[target_columns.names.index(SYMBOL_LEVEL)])]
            ].to_numpy()
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
