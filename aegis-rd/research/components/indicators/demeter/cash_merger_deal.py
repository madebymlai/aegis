# %% component overview
# Causal fixed-cash merger economics reconstructed from point-in-time SEC filings.

from pathlib import Path

import numpy as np
import pandas as pd
from nautilus_trader.model.identifiers import InstrumentId

from research.aegis_research.external_data.ecb_fx import EcbUsdEurSource
from research.aegis_research.external_data.sec_cash_mergers import (
    SecCashMergerEventSource,
)

COMPONENT_MANIFEST = {
    "family": "indicators",
    "id": "demeter.cash_merger_deal",
    "version": "1.0.0",
    "input_names": ["Close"],
    "param_names": [
        "event_cache_dir",
        "fx_cache_dir",
        "filing_lag_days",
        "break_lookback",
        "completion_probability",
        "default_close_days",
        "roundtrip_cost_bps",
        "min_expected_value_bps",
        "benchmark_symbol",
        "residual_lookback",
        "news_exclusion_days",
    ],
    "output_names": [
        "deal_executable_price",
        "deal_cash_offer",
        "deal_break_value",
        "deal_completion_probability",
        "deal_expected_close_days",
        "deal_total_cost",
        "deal_expected_value",
        "deal_break_loss",
        "deal_eligible",
        "deal_annualized_spread",
        "deal_residual",
        "deal_news",
        "deal_status",
    ],
    "defaults": {
        "event_cache_dir": "research/data/cache/sec/cash-mergers",
        "fx_cache_dir": "research/data/cache/ecb/eur-per-usd",
        "filing_lag_days": 1,
        "break_lookback": 20,
        "completion_probability": 0.90,
        "default_close_days": 120,
        "roundtrip_cost_bps": 20.0,
        "min_expected_value_bps": 0.0,
        "benchmark_symbol": "",
        "residual_lookback": 5,
        "news_exclusion_days": 2,
    },
}


def lookback(**params):
    return max(int(params.get("break_lookback", 20)), int(params.get("residual_lookback", 5)))


def _cache_dir(value):
    path = Path(value)
    return path if path.is_absolute() else Path(__file__).resolve().parents[4] / path


def _symbol_root(value):
    if isinstance(value, InstrumentId):
        return value.symbol.value
    text = str(value)
    return text.split(".", 1)[0]


def _aligned_deals(close, events, eur_per_usd, params):
    index = close.index
    dates = pd.DatetimeIndex(index)
    normalized = (dates.tz_localize(None) if dates.tz is not None else dates).normalize()
    symbols = [_symbol_root(column) for column in close.columns]
    symbol_index = {symbol: position for position, symbol in enumerate(symbols)}
    periods, n_symbols = close.shape
    names = COMPONENT_MANIFEST["output_names"]
    outputs = {name: np.full((periods, n_symbols), np.nan) for name in names}
    outputs["deal_eligible"].fill(0.0)
    outputs["deal_news"].fill(0.0)
    outputs["deal_status"].fill(0.0)

    lag = pd.Timedelta(days=int(params["filing_lag_days"]))
    by_symbol = {}
    for event in events:
        if event.target_symbol not in symbol_index:
            continue
        effective = pd.Timestamp(event.available_at).tz_localize(None).normalize() + lag
        by_symbol.setdefault(event.target_symbol, []).append((effective, event))

    q = float(params["completion_probability"])
    if not 0.0 < q < 1.0:
        raise ValueError("demeter.cash_merger_deal: completion_probability must be in (0, 1)")
    break_lookback = int(params["break_lookback"])
    residual_lookback = int(params["residual_lookback"])
    default_close_days = int(params["default_close_days"])
    cost_rate = float(params["roundtrip_cost_bps"]) / 10_000.0
    min_ev_rate = float(params["min_expected_value_bps"]) / 10_000.0
    news_days = int(params["news_exclusion_days"])

    benchmark = str(params["benchmark_symbol"])
    benchmark_position = symbol_index.get(benchmark) if benchmark else None
    prices = close.to_numpy(dtype=float)
    fx_index = eur_per_usd.index
    if fx_index.tz is not None:
        fx_index = fx_index.tz_localize(None)
    fx = pd.Series(eur_per_usd.to_numpy(dtype=float), index=fx_index.normalize())
    fx = fx.reindex(normalized, method="ffill")

    for symbol, updates in by_symbol.items():
        column = symbol_index[symbol]
        first_effective = updates[0][0]
        first_row = int(normalized.searchsorted(first_effective, side="left"))
        history = prices[max(0, first_row - break_lookback) : first_row, column]
        history = history[np.isfinite(history) & (history > 0.0)]
        break_value = float(np.median(history)) if len(history) >= min(5, break_lookback) else np.nan
        state = None
        announcement = None
        update_index = 0
        news_until = None
        for row, today in enumerate(normalized):
            while update_index < len(updates) and updates[update_index][0] <= today:
                effective, event = updates[update_index]
                if state is None:
                    state = {
                        "status": event.status,
                        "offer": event.offer_price,
                        "expected_close": event.expected_close,
                    }
                    announcement = effective
                else:
                    state["status"] = event.status
                    if event.offer_price is not None:
                        state["offer"] = event.offer_price
                    if event.expected_close is not None:
                        state["expected_close"] = event.expected_close
                news_until = effective + pd.Timedelta(days=news_days)
                update_index += 1
            if state is None:
                continue
            price = prices[row, column]
            native_offer = state["offer"]
            outputs["deal_executable_price"][row, column] = price
            outputs["deal_break_value"][row, column] = break_value
            outputs["deal_completion_probability"][row, column] = q
            outputs["deal_news"][row, column] = float(news_until is not None and today <= news_until)
            outputs["deal_status"][row, column] = {
                "pending": 1.0,
                "completed": 2.0,
                "terminated": -1.0,
            }[state["status"]]
            if native_offer is None or not np.isfinite(price) or price <= 0.0:
                continue
            offer = native_offer * fx.iloc[row]
            if not np.isfinite(offer):
                continue
            outputs["deal_cash_offer"][row, column] = offer
            expected_close = (
                pd.Timestamp(state["expected_close"])
                if state["expected_close"] is not None
                else announcement + pd.Timedelta(days=default_close_days)
            )
            days = max((expected_close - today).days, 1)
            outputs["deal_expected_close_days"][row, column] = days
            cost = price * cost_rate
            success = offer - price
            failure = price - break_value
            expected_value = q * success - (1.0 - q) * failure - cost
            outputs["deal_total_cost"][row, column] = cost
            outputs["deal_expected_value"][row, column] = expected_value
            outputs["deal_break_loss"][row, column] = failure / price
            outputs["deal_annualized_spread"][row, column] = (
                (offer / price - 1.0) * 365.0 / days
            )
            if row >= residual_lookback and benchmark_position is not None:
                target_start = prices[row - residual_lookback, column]
                benchmark_start = prices[row - residual_lookback, benchmark_position]
                benchmark_end = prices[row, benchmark_position]
                if min(target_start, benchmark_start, benchmark_end) > 0.0:
                    outputs["deal_residual"][row, column] = (
                        price / target_start - benchmark_end / benchmark_start
                    )
            outputs["deal_eligible"][row, column] = float(
                state["status"] == "pending"
                and np.isfinite(break_value)
                and failure > 0.0
                and success > 0.0
                and expected_close >= today
                and expected_value > price * min_ev_rate
            )
    return outputs


# %% main compute
def run(data, *, n_candidates, **param_lists):
    """Load cache-first deal context and align only causally available filings."""

    close = data.array("Close")
    close_dates = pd.DatetimeIndex(close.index)
    if close_dates.empty:
        raise ValueError("demeter.cash_merger_deal: Close cannot be empty")
    market_dates = close_dates.tz_localize(None) if close_dates.tz is not None else close_dates
    market_start = market_dates.min().date()
    market_end = market_dates.max().date()
    n_symbols = len(close.columns)
    combined = {
        name: np.full((len(close), n_candidates * n_symbols), np.nan)
        for name in COMPONENT_MANIFEST["output_names"]
    }
    event_contexts = {}
    fx_contexts = {}
    for candidate in range(n_candidates):
        params = {name: param_lists[name][candidate] for name in COMPONENT_MANIFEST["param_names"]}
        event_key = str(_cache_dir(params["event_cache_dir"]))
        if event_key not in event_contexts:
            event_source = SecCashMergerEventSource(Path(event_key))
            event_source.sync(market_start, market_end)
            event_contexts[event_key] = event_source.load(market_start, market_end)
        fx_key = str(_cache_dir(params["fx_cache_dir"]))
        if fx_key not in fx_contexts:
            fx_source = EcbUsdEurSource(Path(fx_key))
            fx_source.sync(market_start, market_end)
            fx_contexts[fx_key] = fx_source.load(market_start, market_end)
        aligned = _aligned_deals(
            close,
            event_contexts[event_key].events,
            fx_contexts[fx_key].eur_per_usd,
            params,
        )
        start = candidate * n_symbols
        for name, values in aligned.items():
            combined[name][:, start : start + n_symbols] = values
    return combined
