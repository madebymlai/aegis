"""Cost-aware alpha benchmark over the repaired fixed-cash merger census.

This remains a throwaway prototype.  It deliberately imports the real Aegis
portfolio simulator and convergent metrics, while keeping merger-specific data
assembly and decisions outside the repository's production packages.
"""

from __future__ import annotations

import json
import math
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from aegis_data.distributions import Distribution
from nautilus_trader.model.identifiers import InstrumentId

from cash_merger.census import CashMergerDeal, CashMergerEvent, load_snapshot
from cash_merger.massive import MassiveClient
from cash_merger.target_events import MassiveTargetEventSource
from cash_merger.timing import DealTimingTape, GuidanceState, build_timing_tape
from research.aegis_research.component_registry.contracts import SYMBOL_LEVEL
from research.aegis_research.configuration import PortfolioConfig
from research.aegis_research.metrics.custom.convergent import (
    _convergent_downside_lskew,
    _convergent_income_utility,
    _convergent_tail_budget,
)
from research.aegis_research.optimization.window_evaluation import ResolvedBook
from research.aegis_research.optimization.window_evaluation._simulation import (
    simulate_portfolio_batch,
)


@dataclass(frozen=True)
class CandidateSpec:
    construction: str
    q_minimum: float
    maximum_lifecycle_slots: int
    initial_weight: float | None


_CANDIDATES = {
    "q70_monthly_capped": CandidateSpec(
        construction="monthly_capped",
        q_minimum=0.70,
        maximum_lifecycle_slots=40,
        initial_weight=None,
    ),
    "q70_monthly_guided_enp": CandidateSpec(
        construction="monthly_guided_enp",
        q_minimum=0.70,
        maximum_lifecycle_slots=40,
        initial_weight=None,
    ),
}
_MIN_CONCURRENT = 10
_NAME_CAP = 0.10
_BREAK_LOSS_CAP = 0.02
_MIN_MEDIAN_DOLLAR_VOLUME = 1_000_000.0
_EXPECTED_CLOSE_DAYS = 175
_MIN_BETA_RETURNS = 20
_SLIPPAGE = 0.0005
_FIXED_FEE = 0.35


@dataclass(frozen=True)
class DealMarketState:
    initial_fallback: float
    beta: float
    announcement_market_close: float


@dataclass(frozen=True)
class EligibleDeal:
    deal: CashMergerDeal
    column: int
    price: float
    break_loss: float
    q_market: float
    success_return: float
    event_age_bucket: str
    guidance_state: GuidanceState
    expected_remaining_days: int
    outside_days: int | None


@dataclass(frozen=True)
class EventHazardTable:
    completion_by_age: dict[str, float]
    completion_by_age_and_guidance: dict[str, float]
    adverse: float
    observations_by_age: dict[str, int]
    completions_by_age: dict[str, int]
    observations_by_age_and_guidance: dict[str, int]
    completions_by_age_and_guidance: dict[str, int]
    adverse_events: int
    training_end: str
    completed_durations: tuple[int, ...]

    def completion_rate(self, age_bucket: str, guidance_state: GuidanceState) -> float:
        key = f"{age_bucket}:{guidance_state}"
        if self.observations_by_age_and_guidance.get(key, 0) >= 10:
            return self.completion_by_age_and_guidance[key]
        return self.completion_by_age[age_bucket]

    def expected_remaining_days(self, age_days: int) -> int:
        residuals = [duration - age_days for duration in self.completed_durations if duration > age_days]
        if len(residuals) >= 5:
            return max(int(round(float(np.median(residuals)))), 1)
        return max(_EXPECTED_CLOSE_DAYS - age_days, 30)


@dataclass(frozen=True)
class CashCurve:
    annual_rate: pd.Series
    daily_return: pd.Series


@dataclass(frozen=True)
class PriceTape:
    close: pd.DataFrame
    open: pd.DataFrame
    volume: pd.DataFrame
    distributions: tuple[Distribution, ...]
    deals: tuple[CashMergerDeal, ...]
    deal_state: dict[str, DealMarketState]
    offer_history: dict[str, tuple[CashMergerEvent, ...]]
    timing: DealTimingTape
    market_close: pd.Series
    exclusions: dict[str, int]


class MassiveMarketSource:
    """Complete lifecycle bars from immutable Massive HTTP responses."""

    def __init__(self, client: MassiveClient) -> None:
        self.client = client
        self._cached = self._index_cached_bars(client.cache_dir)

    def bars(self, ticker: str, start: date, end: date) -> pd.DataFrame:
        cached = self._cached.get(ticker, {})
        required_end = end
        has_window = (
            cached
            and min(cached) <= start + timedelta(days=7)
            and max(cached) >= required_end - timedelta(days=7)
        )
        if not has_window:
            print(
                f"STATE prices fetch ticker={ticker} start={start} end={end}",
                flush=True,
            )
            self._fetch_with_backoff(ticker, start, end)
            self._cached = self._index_cached_bars(self.client.cache_dir)
            cached = self._cached.get(ticker, {})
        rows = [row for day, row in sorted(cached.items()) if start <= day <= end]
        if not rows:
            return pd.DataFrame(columns=["Open", "Close", "Volume"])
        return pd.DataFrame(
            {
                "Open": [float(row["o"]) for row in rows],
                "Close": [float(row["c"]) for row in rows],
                "Volume": [float(row.get("v") or 0.0) for row in rows],
            },
            index=pd.DatetimeIndex([pd.Timestamp(row["date"]) for row in rows]),
        )

    def dividends(
        self, tickers: tuple[str, ...], start: date, end: date
    ) -> tuple[dict[str, Any], ...]:
        rows: list[dict[str, Any]] = []
        for offset in range(0, len(tickers), 75):
            batch = tickers[offset : offset + 75]
            params: dict[str, object] | None = {
                "ticker.any_of": ",".join(batch),
                "ex_dividend_date.gte": start.isoformat(),
                "ex_dividend_date.lte": end.isoformat(),
                "limit": 1000,
                "sort": "ex_dividend_date.asc",
            }
            url = "/stocks/v1/dividends"
            while url:
                payload = self._get_with_backoff(url, params)
                rows.extend(payload.get("results") or ())
                url = str(payload.get("next_url") or "")
                params = None
        return tuple(rows)

    def _fetch_with_backoff(self, ticker: str, start: date, end: date) -> None:
        encoded = urllib.parse.quote(ticker, safe="")
        self._get_with_backoff(
            f"/v2/aggs/ticker/{encoded}/range/1/day/{start.isoformat()}/{end.isoformat()}",
            {"adjusted": "true", "sort": "asc", "limit": 50000},
        )

    def _get_with_backoff(
        self, path: str, params: dict[str, object] | None
    ) -> dict[str, Any]:
        for attempt in range(6):
            try:
                return self.client._get(path, params)
            except urllib.error.HTTPError as error:
                if error.code != 429 or attempt == 5:
                    raise
                wait = 15.0 * (attempt + 1)
                print(f"STATE provider rate_limited retry_in={wait:.0f}s", flush=True)
                time.sleep(wait)
        raise AssertionError("unreachable")

    @staticmethod
    def _index_cached_bars(cache_dir: Path) -> dict[str, dict[date, dict[str, Any]]]:
        by_ticker: dict[str, dict[date, dict[str, Any]]] = defaultdict(dict)
        for path in cache_dir.glob("massive-*.json"):
            try:
                payload = json.loads(path.read_text())
            except (OSError, json.JSONDecodeError):
                continue
            ticker = str(payload.get("ticker") or "").upper()
            for row in payload.get("results") or ():
                if not ticker or not isinstance(row, dict) or not {"t", "o", "c"} <= row.keys():
                    continue
                day = datetime.fromtimestamp(float(row["t"]) / 1000.0, UTC).date()
                by_ticker[ticker][day] = {**row, "date": day.isoformat()}
        return dict(by_ticker)


def build_price_tape(
    snapshot_path: Path,
    market: MassiveMarketSource,
    offer_events: tuple[CashMergerEvent, ...],
    timing: DealTimingTape,
    *,
    capital: float,
) -> PriceTape:
    snapshot = load_snapshot(snapshot_path)
    exclusions: dict[str, int] = defaultdict(int)
    events_by_accession = {event.accession: event for event in offer_events}
    offer_history: dict[str, tuple[CashMergerEvent, ...]] = {}
    deals: list[CashMergerDeal] = []
    for deal in snapshot.deals:
        if deal.initial_offer_price <= 0.0:
            exclusions["invalid_offer"] += 1
            continue
        observations = tuple(
            sorted(
                (
                    events_by_accession[accession]
                    for accession in deal.accessions
                    if accession in events_by_accession
                    and events_by_accession[accession].status == "pending"
                    and events_by_accession[accession].offer_price is not None
                ),
                key=lambda event: (event.available_at, event.accession),
            )
        )
        if not observations or not math.isclose(
            float(observations[0].offer_price),
            deal.initial_offer_price,
            rel_tol=0.0,
            abs_tol=1e-9,
        ):
            exclusions["causal_offer_history_unavailable"] += 1
            continue
        offer_history[deal.deal_id] = observations
        deals.append(deal)

    by_symbol: dict[str, list[CashMergerDeal]] = defaultdict(list)
    for deal in deals:
        by_symbol[deal.announcement_symbol].append(deal)

    raw: dict[str, pd.DataFrame] = {}
    priceable_symbols: list[str] = []
    covered_end = date.fromisoformat(snapshot.covered_end)
    earliest_announcement = min(
        date.fromisoformat(deal.announced_at[:10]) for deal in deals
    )
    market_frame = market.bars(
        "SPY", earliest_announcement - timedelta(days=50), covered_end
    )
    if market_frame.empty:
        raise RuntimeError("SPY market tape unavailable for dynamic fallback")
    for position, (symbol, lifecycles) in enumerate(sorted(by_symbol.items()), start=1):
        first = min(date.fromisoformat(item.announced_at[:10]) for item in lifecycles)
        last = max(
            (
                date.fromisoformat(item.resolved_at[:10]) + timedelta(days=7)
                if item.resolved_at is not None
                else covered_end
            )
            for item in lifecycles
        )
        frame = market.bars(symbol, first - timedelta(days=50), min(last, covered_end))
        if frame.empty or len(frame.loc[frame.index < pd.Timestamp(first)]) < 10:
            exclusions["insufficient_price_history"] += len(lifecycles)
            continue
        raw[symbol] = frame
        priceable_symbols.append(symbol)
        if position % 10 == 0:
            print(
                f"STATE prices progress={position}/{len(by_symbol)} retained={len(raw)}",
                flush=True,
            )

    deal_state: dict[str, DealMarketState] = {}
    for deal in deals:
        if deal.announcement_symbol not in priceable_symbols:
            continue
        announced = pd.Timestamp(deal.announced_at[:10])
        stock = raw[deal.announcement_symbol]["Close"].loc[lambda values: values.index < announced]
        market_pre = market_frame["Close"].loc[lambda values: values.index < announced]
        aligned = pd.concat(
            [stock.rename("stock"), market_pre.rename("market")], axis=1, join="inner"
        ).dropna()
        log_returns = np.log(aligned).diff().dropna()
        market_variance = float(log_returns["market"].var(ddof=1))
        market_at_announcement = market_frame["Close"].loc[
            market_frame.index <= announced
        ]
        if (
            len(stock.tail(20)) < 20
            or len(log_returns) < _MIN_BETA_RETURNS
            or not math.isfinite(market_variance)
            or market_variance <= 0.0
            or market_at_announcement.empty
        ):
            exclusions["insufficient_beta_history"] += 1
            continue
        beta = float(log_returns["stock"].cov(log_returns["market"]) / market_variance)
        if not math.isfinite(beta):
            exclusions["invalid_beta"] += 1
            continue
        deal_state[deal.deal_id] = DealMarketState(
            initial_fallback=float(stock.tail(20).mean()),
            beta=beta,
            announcement_market_close=float(market_at_announcement.iloc[-1]),
        )

    retained = tuple(deal for deal in deals if deal.deal_id in deal_state)
    if not retained:
        raise RuntimeError("no priceable merger lifecycles")
    retained_symbols = sorted({deal.announcement_symbol for deal in retained})
    index = pd.DatetimeIndex(
        sorted(
            {
                day
                for symbol, frame in raw.items()
                if symbol in retained_symbols
                for day in frame.index
                if pd.Timestamp(snapshot.covered_start) <= day <= pd.Timestamp(snapshot.covered_end)
            }
        )
    )
    ids = {
        symbol: InstrumentId.from_str(f"{symbol}.MASSIVE")
        for symbol in retained_symbols
    }
    close = pd.DataFrame(index=index, columns=ids.values(), dtype=float)
    open_ = close.copy()
    volume = close.copy()
    for symbol, frame in raw.items():
        if symbol not in ids:
            continue
        instrument_id = ids[symbol]
        close[instrument_id] = frame["Close"].reindex(index).ffill().bfill()
        open_[instrument_id] = frame["Open"].reindex(index).ffill().bfill()
        volume[instrument_id] = frame["Volume"].reindex(index).fillna(0.0)

    dividend_rows = market.dividends(
        tuple(sorted(retained_symbols)),
        date.fromisoformat(snapshot.covered_start),
        covered_end,
    )
    distributions: list[Distribution] = []
    for row in dividend_rows:
        symbol = str(row.get("ticker") or "").upper()
        ex_date = row.get("ex_dividend_date")
        amount = row.get("split_adjusted_cash_amount", row.get("cash_amount"))
        if symbol not in ids or not ex_date or amount is None or float(amount) <= 0.0:
            continue
        distributions.append(
            Distribution.from_ex_date(
                ids[symbol], str(ex_date), amount=float(amount), currency="USD"
            )
        )
    print(
        f"STATE tape deals={len(retained)} symbols={len(retained_symbols)} "
        f"dividends={len(distributions)} exclusions={dict(exclusions)}",
        flush=True,
    )
    return PriceTape(
        close=close,
        open=open_,
        volume=volume,
        distributions=tuple(distributions),
        deals=retained,
        deal_state={deal.deal_id: deal_state[deal.deal_id] for deal in retained},
        offer_history={deal.deal_id: offer_history[deal.deal_id] for deal in retained},
        timing=timing,
        market_close=market_frame["Close"].reindex(index).ffill().bfill(),
        exclusions=dict(exclusions),
    )


def build_allocations(
    tape: PriceTape,
    annual_rates: pd.Series,
    *,
    capital: float,
    hazards: EventHazardTable,
    active_from: pd.Timestamp,
) -> tuple[pd.DataFrame, list[dict[str, Any]], list[dict[str, Any]]]:
    ids = tuple(tape.close.columns)
    id_by_symbol = {instrument_id.symbol.value: instrument_id for instrument_id in ids}
    dollar_volume = (tape.close * tape.volume).rolling(20, min_periods=10).median()
    candidate_arrays: list[np.ndarray] = []
    eligibility_audit: list[dict[str, Any]] = []
    hazard_score_audit: list[dict[str, Any]] = []
    for candidate, spec in _CANDIDATES.items():
        if spec.construction in {
            "monthly_capped",
            "monthly_guided_enp",
        }:
            target = _monthly_allocations(
                tape,
                spec,
                annual_rates,
                dollar_volume,
                id_by_symbol,
                capital,
                hazards=hazards if spec.construction == "monthly_guided_enp" else None,
                active_from=active_from,
                eligibility_audit=(
                    eligibility_audit if spec.construction == "monthly_capped" else None
                ),
                hazard_score_audit=(
                    hazard_score_audit
                    if spec.construction == "monthly_guided_enp"
                    else None
                ),
            )
        else:
            raise ValueError(f"unknown prototype construction {spec.construction}")
        candidate_arrays.append(target)
        active = (target > 0.0).sum(axis=1)
        print(
            f"STATE signal candidate={candidate} invested_days={int((active > 0).sum())} "
            f"median_names={float(np.median(active[active > 0])) if np.any(active > 0) else 0.0:.1f} "
            f"max_names={int(active.max())}",
            flush=True,
        )

    columns = pd.MultiIndex.from_tuples(
        [(candidate, instrument_id) for candidate in _CANDIDATES for instrument_id in ids],
        names=["candidate", SYMBOL_LEVEL],
    )
    allocations = pd.DataFrame(
        np.concatenate(candidate_arrays, axis=1),
        index=tape.close.index,
        columns=columns,
    )
    if (allocations.T.groupby(level=0).sum().T > 1.0 + 1e-12).any().any():
        raise RuntimeError("alpha benchmark breached its gross-cap contract")
    return allocations, eligibility_audit, hazard_score_audit


def _monthly_allocations(
    tape: PriceTape,
    spec: CandidateSpec,
    annual_rates: pd.Series,
    dollar_volume: pd.DataFrame,
    id_by_symbol: dict[str, InstrumentId],
    capital: float,
    *,
    hazards: EventHazardTable | None,
    active_from: pd.Timestamp,
    eligibility_audit: list[dict[str, Any]] | None,
    hazard_score_audit: list[dict[str, Any]] | None,
) -> np.ndarray:
    target = np.zeros(tape.close.shape, dtype=float)
    held: dict[str, tuple[int, float, CashMergerDeal]] = {}
    previous_month: tuple[int, int] | None = None
    for row, today in enumerate(tape.close.index):
        if today < active_from:
            continue
        held = _drop_resolved(held, today)
        month = (today.year, today.month)
        if month != previous_month:
            eligible, audit = _eligibility_snapshot(
                tape,
                row,
                today,
                float(annual_rates.iloc[row]),
                dollar_volume,
                id_by_symbol,
                spec.q_minimum,
                capital,
                hazards=hazards,
                use_timing=hazards is not None,
            )
            if eligibility_audit is not None:
                eligibility_audit.append({"date": today.date().isoformat(), **audit})
            if hazards is None:
                ranked = sorted(
                    eligible,
                    key=lambda item: (-item.q_market, item.deal.deal_id),
                )
            else:
                scored = [
                    (_event_net_payoff(item, hazards, capital), item)
                    for item in eligible
                ]
                score_values = [score for score, _item in scored]
                if hazard_score_audit is not None:
                    guidance_counts = defaultdict(int)
                    for item in eligible:
                        guidance_counts[item.guidance_state] += 1
                    hazard_score_audit.append(
                        {
                            "date": today.date().isoformat(),
                            "q70_deals": len(scored),
                            "positive_enp": sum(score > 0.0 for score in score_values),
                            "minimum_enp": min(score_values) if score_values else None,
                            "median_enp": (
                                float(np.median(score_values)) if score_values else None
                            ),
                            "maximum_enp": max(score_values) if score_values else None,
                            "guidance_states": dict(guidance_counts),
                            "median_expected_remaining_days": (
                                float(np.median([item.expected_remaining_days for item in eligible]))
                                if eligible
                                else None
                            ),
                            "outside_dates_available": sum(
                                item.outside_days is not None for item in eligible
                            ),
                        }
                    )
                ranked = [
                    item
                    for score, item in sorted(
                        scored,
                        key=lambda value: (-value[0], value[1].deal.deal_id),
                    )
                    if score > 0.0
                ]
            chosen = ranked[: spec.maximum_lifecycle_slots]
            held = {}
            if chosen and len(chosen) >= _MIN_CONCURRENT:
                equal_weight = 1.0 / len(chosen)
                for item in chosen:
                    weight = min(
                        _NAME_CAP,
                        equal_weight,
                        _BREAK_LOSS_CAP / item.break_loss,
                    )
                    if capital * weight >= item.price + _FIXED_FEE:
                        held[item.deal.deal_id] = (item.column, weight, item.deal)
                if len(held) < _MIN_CONCURRENT:
                    held = {}
            previous_month = month
        for column, weight, _deal in held.values():
            target[row, column] = weight
    return target


def _fixed_entry_allocations(
    tape: PriceTape,
    spec: CandidateSpec,
    annual_rates: pd.Series,
    dollar_volume: pd.DataFrame,
    id_by_symbol: dict[str, InstrumentId],
    capital: float,
) -> np.ndarray:
    if spec.initial_weight is None:
        raise ValueError("fixed-entry construction requires an initial weight")
    target = np.zeros(tape.close.shape, dtype=float)
    held: dict[str, tuple[int, float, CashMergerDeal]] = {}
    for row, today in enumerate(tape.close.index):
        held = _drop_resolved(held, today)
        eligible = [
            item
            for item in _eligible_deals(
                tape,
                row,
                today,
                float(annual_rates.iloc[row]),
                dollar_volume,
                id_by_symbol,
                spec.q_minimum,
                capital,
            )
            if item.deal.deal_id not in held
        ]
        if len(held) + len(eligible) >= _MIN_CONCURRENT:
            gross = sum(weight for _, weight, _ in held.values())
            for item in sorted(
                eligible, key=lambda value: (value.deal.announced_at, value.deal.deal_id)
            ):
                if len(held) >= spec.maximum_lifecycle_slots:
                    break
                weight = min(
                    _NAME_CAP,
                    spec.initial_weight,
                    _BREAK_LOSS_CAP / item.break_loss,
                )
                if (
                    gross + weight <= 1.0 + 1e-12
                    and capital * weight >= item.price + _FIXED_FEE
                ):
                    held[item.deal.deal_id] = (item.column, weight, item.deal)
                    gross += weight
        for column, weight, _deal in held.values():
            target[row, column] = weight
    return target


def _drop_resolved(
    held: dict[str, tuple[int, float, CashMergerDeal]],
    today: pd.Timestamp,
) -> dict[str, tuple[int, float, CashMergerDeal]]:
    return {
        deal_id: position
        for deal_id, position in held.items()
        if position[2].resolved_at is None
        or today < pd.Timestamp(position[2].resolved_at[:10])
    }


def _eligible_deals(
    tape: PriceTape,
    row: int,
    today: pd.Timestamp,
    annual_rate: float,
    dollar_volume: pd.DataFrame,
    id_by_symbol: dict[str, InstrumentId],
    q_minimum: float,
    capital: float,
    *,
    hazards: EventHazardTable | None = None,
    use_timing: bool = False,
) -> list[EligibleDeal]:
    return _eligibility_snapshot(
        tape,
        row,
        today,
        annual_rate,
        dollar_volume,
        id_by_symbol,
        q_minimum,
        capital,
        hazards=hazards,
        use_timing=use_timing,
    )[0]


def _eligibility_snapshot(
    tape: PriceTape,
    row: int,
    today: pd.Timestamp,
    annual_rate: float,
    dollar_volume: pd.DataFrame,
    id_by_symbol: dict[str, InstrumentId],
    q_minimum: float,
    capital: float,
    *,
    hazards: EventHazardTable | None = None,
    use_timing: bool = False,
) -> tuple[list[EligibleDeal], dict[str, int]]:
    prices = tape.close.iloc[row]
    market_price = float(tape.market_close.iloc[row])
    eligible: list[EligibleDeal] = []
    audit = {
        "active_lifecycle": 0,
        "causal_offer": 0,
        "valid_payoff": 0,
        "affordable": 0,
        "liquid": 0,
        "q70": 0,
    }
    for deal in tape.deals:
        announced = pd.Timestamp(deal.announced_at[:10])
        resolved = (
            pd.Timestamp(deal.resolved_at[:10]) if deal.resolved_at is not None else None
        )
        if today <= announced or (resolved is not None and today >= resolved):
            continue
        audit["active_lifecycle"] += 1
        offer = _causal_offer(tape.offer_history[deal.deal_id], today)
        if offer is None:
            continue
        audit["causal_offer"] += 1
        state = tape.deal_state[deal.deal_id]
        market_log_return = math.log(market_price / state.announcement_market_close)
        fallback = state.initial_fallback * math.exp(state.beta * market_log_return)
        timing_state = tape.timing.at(deal.deal_id, today)
        age_days = max((today - announced).days, 0)
        if use_timing and hazards is not None:
            discounted_offer, remaining_days = _timing_success_value(
                offer, annual_rate, timing_state, today, hazards, age_days
            )
        else:
            remaining_days = max(_EXPECTED_CLOSE_DAYS - age_days, 0)
            discounted_offer = offer / (1.0 + annual_rate * remaining_days / 365.0)
        instrument_id = id_by_symbol[deal.announcement_symbol]
        column = tape.close.columns.get_loc(instrument_id)
        price = float(prices[instrument_id])
        liquidity = float(dollar_volume.iloc[row, column])
        if not fallback < price < discounted_offer:
            continue
        break_loss = (price - fallback) / price
        if break_loss <= 0.0:
            continue
        audit["valid_payoff"] += 1
        if price > capital * _NAME_CAP:
            continue
        audit["affordable"] += 1
        if liquidity < _MIN_MEDIAN_DOLLAR_VOLUME:
            continue
        audit["liquid"] += 1
        q_market = min(
            max((price - fallback) / (discounted_offer - fallback), 0.0), 1.0
        )
        if q_market < q_minimum:
            continue
        audit["q70"] += 1
        eligible.append(
            EligibleDeal(
                deal=deal,
                column=column,
                price=price,
                break_loss=break_loss,
                q_market=q_market,
                success_return=(discounted_offer - price) / price,
                event_age_bucket=_event_age_bucket(today, announced),
                guidance_state=timing_state.guidance_state,
                expected_remaining_days=remaining_days,
                outside_days=(
                    (timing_state.outside.outside_date - today.date()).days
                    if timing_state.outside is not None
                    else None
                ),
            )
        )
    return eligible, audit


def _timing_success_value(
    offer: float,
    annual_rate: float,
    state: Any,
    today: pd.Timestamp,
    hazards: EventHazardTable,
    age_days: int,
) -> tuple[float, int]:
    guidance = state.guidance
    if guidance is not None and state.guidance_state in {"before_guidance", "in_guidance"}:
        start = max(guidance.interval.start, today.date() + timedelta(days=1))
        end = guidance.interval.end
        if end >= start:
            first = max((start - today.date()).days, 1)
            last = max((end - today.date()).days, first)
            days = np.arange(first, last + 1, dtype=float)
            value = float(np.mean(offer / (1.0 + annual_rate * days / 365.0)))
            return value, int(round(float(days.mean())))
    remaining = hazards.expected_remaining_days(age_days)
    return offer / (1.0 + annual_rate * remaining / 365.0), remaining


def _event_age_bucket(today: pd.Timestamp, announced: pd.Timestamp) -> str:
    age_weeks = max((today - announced).days, 0) / 7.0
    if age_weeks < 12.0:
        return "early"
    if age_weeks < 36.0:
        return "high"
    return "late"


def estimate_event_hazards(
    tape: PriceTape,
    *,
    training_end: pd.Timestamp,
) -> EventHazardTable:
    observations = {"early": 0, "high": 0, "late": 0}
    completions = {"early": 0, "high": 0, "late": 0}
    timing_observations: dict[str, int] = defaultdict(int)
    timing_completions: dict[str, int] = defaultdict(int)
    adverse_events = 0
    completed_durations = tuple(
        (pd.Timestamp(deal.resolved_at[:10]) - pd.Timestamp(deal.announced_at[:10])).days
        for deal in tape.deals
        if deal.outcome == "completed"
        and deal.resolved_at is not None
        and pd.Timestamp(deal.resolved_at[:10]) <= training_end
    )
    eligible_dates = tape.close.index[tape.close.index <= training_end]
    month_starts = pd.Series(eligible_dates, index=eligible_dates).groupby(
        [eligible_dates.year, eligible_dates.month]
    ).first()
    for today in month_starts:
        interval_end = today + pd.DateOffset(months=1)
        if interval_end > training_end:
            continue
        for deal in tape.deals:
            announced = pd.Timestamp(deal.announced_at[:10])
            resolved = (
                pd.Timestamp(deal.resolved_at[:10])
                if deal.resolved_at is not None
                else None
            )
            if today <= announced or (resolved is not None and resolved <= today):
                continue
            bucket = _event_age_bucket(today, announced)
            guidance_state = tape.timing.at(deal.deal_id, today).guidance_state
            timing_key = f"{bucket}:{guidance_state}"
            observations[bucket] += 1
            timing_observations[timing_key] += 1
            if resolved is None or resolved > interval_end:
                continue
            if deal.outcome == "completed":
                completions[bucket] += 1
                timing_completions[timing_key] += 1
            elif deal.outcome == "terminated":
                adverse_events += 1
    if not all(observations.values()):
        raise RuntimeError(f"hazard training has empty age bucket: {observations}")
    total_observations = sum(observations.values())
    return EventHazardTable(
        completion_by_age={
            bucket: completions[bucket] / observations[bucket]
            for bucket in observations
        },
        completion_by_age_and_guidance={
            key: timing_completions[key] / count
            for key, count in timing_observations.items()
        },
        adverse=adverse_events / total_observations,
        observations_by_age=observations,
        completions_by_age=completions,
        observations_by_age_and_guidance=dict(timing_observations),
        completions_by_age_and_guidance=dict(timing_completions),
        adverse_events=adverse_events,
        training_end=training_end.date().isoformat(),
        completed_durations=tuple(sorted(completed_durations)),
    )


def _event_net_payoff(
    deal: EligibleDeal,
    hazards: EventHazardTable,
    capital: float,
) -> float:
    maximum_weight = min(_NAME_CAP, _BREAK_LOSS_CAP / deal.break_loss)
    notional = capital * maximum_weight
    round_trip_cost_rate = 2.0 * _SLIPPAGE + 2.0 * _FIXED_FEE / notional
    return (
        hazards.completion_rate(deal.event_age_bucket, deal.guidance_state)
        * deal.success_return
        - hazards.adverse * deal.break_loss
        - round_trip_cost_rate
    )


def _causal_offer(
    observations: tuple[CashMergerEvent, ...], today: pd.Timestamp
) -> float | None:
    available = [
        float(event.offer_price)
        for event in observations
        if event.offer_price is not None and today > pd.Timestamp(event.available_at[:10])
    ]
    return available[-1] if available else None


def simulate(
    tape: PriceTape,
    allocations: pd.DataFrame,
    cash_returns: pd.Series,
    *,
    capital: float,
    report_start: pd.Timestamp,
) -> dict[str, Any]:
    config = PortfolioConfig(
        init_cash=capital,
        fees=0.0,
        slippage=_SLIPPAGE,
        fixed_fee=_FIXED_FEE,
        fill_timing="next_close",
        base_currency="USD",
        fx_conversion_cost=0.0,
        net_cap=1.0,
        gross_cap=1.0,
        direction="longonly",
        band_up=0.02,
        band_down=0.02,
        margin_interest_rate=0.0,
    )
    book = ResolvedBook(
        config=config,
        fees_by_symbol=pd.Series(0.0, index=tape.close.columns),
        size_increment_by_instrument=dict.fromkeys(tape.close.columns, 1.0),
    )
    print("STATE simulation engine=aegis whole_shares=true", flush=True)
    portfolio = simulate_portfolio_batch(
        tape.close,
        allocations,
        book,
        open_=tape.open,
        market_index=tape.close.index,
        periods_per_year=252,
        distributions=tape.distributions,
    )
    values = portfolio.get_value()
    if isinstance(values, pd.Series):
        values = values.to_frame(next(iter(_CANDIDATES)))
    returns = values.pct_change(fill_method=None).iloc[1:]
    cash = cash_returns.reindex(returns.index).ffill().bfill()
    report: dict[str, Any] = {}
    for candidate in _CANDIDATES:
        deal_stream = returns[candidate].loc[lambda values: values.index >= report_start].dropna()
        cash_stream = cash.reindex(deal_stream.index).fillna(0.0)
        reserve_weight = (
            1.0 - allocations[candidate].sum(axis=1).clip(lower=0.0, upper=1.0)
        ).shift(1).reindex(deal_stream.index).fillna(1.0)
        stream = deal_stream + reserve_weight * cash_stream
        equity = (1.0 + stream).cumprod()
        deal_equity = (1.0 + deal_stream).cumprod()
        cash_equity = (1.0 + cash_stream).cumprod()
        drawdown = equity / equity.cummax() - 1.0
        monthly = (1.0 + stream).resample("ME").prod() - 1.0
        volatility = float(stream.std(ddof=1) * math.sqrt(252.0))
        excess = stream - cash_stream
        sharpe = (
            float(excess.mean() / stream.std(ddof=1) * math.sqrt(252.0))
            if stream.std(ddof=1) > 0.0
            else 0.0
        )
        candidate_allocations = allocations[candidate].loc[
            allocations.index >= report_start
        ]
        active = (candidate_allocations > 0.0).sum(axis=1)
        held_outcomes = _held_outcomes(tape, candidate_allocations)
        report[candidate] = {
            "net_total_return": float(equity.iloc[-1] - 1.0),
            "deal_only_net_total_return": float(deal_equity.iloc[-1] - 1.0),
            "reserve_return_contribution": float(equity.iloc[-1] - deal_equity.iloc[-1]),
            "cash_total_return": float(cash_equity.iloc[-1] - 1.0),
            "excess_total_return": float(equity.iloc[-1] - cash_equity.iloc[-1]),
            "annualized_volatility": volatility,
            "cash_excess_sharpe": sharpe,
            "max_drawdown": float(drawdown.min()),
            "worst_month": float(monthly.min()) if not monthly.empty else math.nan,
            "monthly_returns": {
                stamp.date().isoformat(): float(value)
                for stamp, value in monthly.items()
            },
            "daily_skew": float(stream.skew()),
            "convergent_income_utility": _convergent_income_utility(stream.to_numpy()),
            "cash_utility": _convergent_income_utility(cash_stream.to_numpy()),
            "convergent_utility_delta_vs_cash": (
                _convergent_income_utility(stream.to_numpy())
                - _convergent_income_utility(cash_stream.to_numpy())
            ),
            "convergent_tail_budget": _convergent_tail_budget(stream.to_numpy()),
            "convergent_downside_lskew": _convergent_downside_lskew(stream.to_numpy()),
            "invested_day_fraction": float((active > 0).mean()),
            "mean_target_gross": float(candidate_allocations.sum(axis=1).mean()),
            "mean_bill_reserve_weight": float(reserve_weight.mean()),
            "median_names_when_invested": (
                float(active[active > 0].median()) if (active > 0).any() else 0.0
            ),
            "held_completed_deals": len(held_outcomes["completed"]),
            "held_terminated_deals": len(held_outcomes["terminated"]),
            "held_completed_deal_ids": held_outcomes["completed"],
            "held_terminated_deal_ids": held_outcomes["terminated"],
        }
    fees = portfolio.orders.fees.sum()
    counts = portfolio.orders.count()
    for candidate in _CANDIDATES:
        report[candidate]["total_fees_paid"] = float(fees[candidate])
        report[candidate]["total_orders"] = int(counts[candidate])
    return report


def _held_outcomes(
    tape: PriceTape, allocations: pd.DataFrame
) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {"completed": [], "terminated": []}
    for deal in tape.deals:
        if deal.outcome not in result or deal.resolved_at is None:
            continue
        instrument_id = next(
            item for item in allocations.columns if item.symbol.value == deal.announcement_symbol
        )
        announced = pd.Timestamp(deal.announced_at[:10])
        resolved = pd.Timestamp(deal.resolved_at[:10])
        held = allocations.loc[
            (allocations.index > announced) & (allocations.index < resolved), instrument_id
        ]
        if (held > 0.0).any():
            result[deal.outcome].append(deal.deal_id)
    return result


def _cash_curve(index: pd.DatetimeIndex) -> CashCurve:
    start = index.min().date() - timedelta(days=7)
    end = index.max().date()
    url = (
        "https://fred.stlouisfed.org/graph/fredgraph.csv?"
        + urllib.parse.urlencode({"id": "DTB3", "cosd": start.isoformat(), "coed": end.isoformat()})
    )
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            frame = pd.read_csv(response)
        frame.columns = ["date", "rate"]
        frame["date"] = pd.to_datetime(frame["date"])
        frame["rate"] = pd.to_numeric(frame["rate"], errors="coerce")
        annual = frame.set_index("date")["rate"].reindex(index).ffill().bfill() / 100.0
        print(f"STATE cash_benchmark source=FRED_DTB3 mean_rate={annual.mean():.4f}", flush=True)
        return CashCurve(
            annual_rate=annual.rename("annual_rate"),
            daily_return=(annual / 360.0).rename("cash"),
        )
    except Exception as error:
        raise RuntimeError("FRED DTB3 cash benchmark unavailable") from error


def alpha_report(
    snapshot_path: Path,
    client: MassiveClient,
    *,
    capital: float,
    evaluation_start: date,
) -> dict[str, Any]:
    snapshot = load_snapshot(snapshot_path)
    source_tape = MassiveTargetEventSource(client).load(
        date.fromisoformat(snapshot.covered_start),
        date.fromisoformat(snapshot.covered_end),
    )
    timing = build_timing_tape(snapshot.deals, source_tape.filing_rows)
    tape = build_price_tape(
        snapshot_path,
        MassiveMarketSource(client),
        source_tape.events,
        timing,
        capital=capital,
    )
    cash = _cash_curve(tape.close.index)
    evaluation_start_stamp = pd.Timestamp(evaluation_start)
    hazard_training_end = evaluation_start_stamp - pd.Timedelta(days=1)
    hazards = estimate_event_hazards(tape, training_end=hazard_training_end)
    print(
        "STATE hazard_training "
        f"end={hazards.training_end} "
        f"observations={hazards.observations_by_age} "
        f"completions={hazards.completions_by_age} "
        f"timing_observations={hazards.observations_by_age_and_guidance} "
        f"adverse={hazards.adverse_events} "
        f"rates={hazards.completion_by_age} adverse_rate={hazards.adverse:.6f}",
        flush=True,
    )
    allocations, eligibility_audit, hazard_score_audit = build_allocations(
        tape,
        cash.annual_rate,
        capital=capital,
        hazards=hazards,
        active_from=evaluation_start_stamp,
    )
    results = simulate(
        tape,
        allocations,
        cash.daily_return,
        capital=capital,
        report_start=evaluation_start_stamp,
    )
    control = results["q70_monthly_capped"]
    challenger = results["q70_monthly_guided_enp"]
    hazard_survives = (
        challenger["excess_total_return"] > control["excess_total_return"]
        and challenger["convergent_utility_delta_vs_cash"]
        > control["convergent_utility_delta_vs_cash"]
        and challenger["max_drawdown"] >= control["max_drawdown"]
        and challenger["worst_month"] >= control["worst_month"]
    )
    verdict = {
        "guided_enp": (
            "survives_forward_shadow_required"
            if hazard_survives
            else "kill_retain_q70_control"
        ),
    }
    amended_lifecycles = sum(
        len({float(event.offer_price) for event in observations if event.offer_price is not None})
        > 1
        for observations in tape.offer_history.values()
    )
    betas = np.array([state.beta for state in tape.deal_state.values()], dtype=float)
    return {
        "question": "Does point-in-time closing guidance improve ENP selection over the frozen q70 monthly cash-merger benchmark?",
        "evidence": {
            "classification": "prototype_point_in_time_guidance_small_training_reused_evaluation",
            "frozen_contract": str(Path(__file__).resolve().parents[1] / "FROZEN_ALPHA_V4.md"),
            "snapshot": str(snapshot_path),
            "capital_usd": capital,
            "fixed_cash_lifecycles": len(tape.deals),
            "causally_included_amended_lifecycles": amended_lifecycles,
            "symbols": len(tape.close.columns),
            "median_preannouncement_beta": float(np.median(betas)),
            "start": tape.close.index.min().date().isoformat(),
            "end": tape.close.index.max().date().isoformat(),
            "evaluation_start": evaluation_start.isoformat(),
            "hazard_training": {
                "training_end": hazards.training_end,
                "interval": "from each monthly observation to the next calendar-month boundary",
                "observations_by_age": hazards.observations_by_age,
                "completions_by_age": hazards.completions_by_age,
                "completion_rate_by_age": hazards.completion_by_age,
                "observations_by_age_and_guidance": hazards.observations_by_age_and_guidance,
                "completions_by_age_and_guidance": hazards.completions_by_age_and_guidance,
                "completion_rate_by_age_and_guidance": hazards.completion_by_age_and_guidance,
                "adverse_events": hazards.adverse_events,
                "adverse_rate": hazards.adverse,
                "completed_duration_observations": len(hazards.completed_durations),
            },
            "timing_coverage": _timing_coverage(tape),
            "monthly_eligibility_attrition": eligibility_audit,
            "monthly_hazard_score_distribution": hazard_score_audit,
            "exclusions": tape.exclusions,
        },
        "contract": {
            "selection_controls": {
                name: {
                    "construction": spec.construction,
                    "q_minimum": spec.q_minimum,
                    "maximum_lifecycle_slots": spec.maximum_lifecycle_slots,
                    "initial_weight": spec.initial_weight,
                }
                for name, spec in _CANDIDATES.items()
            },
            "q_market": (
                "clamp((close - beta_adjusted_mean_20_fallback) / "
                "(discounted_causal_cash_offer - beta_adjusted_mean_20_fallback), 0, 1)"
            ),
            "timing_model": (
                "causal management-guidance interval integrated into discounted success value; "
                "survival-conditioned median remaining duration when guidance is absent or stale"
            ),
            "outside_date_role": (
                "reported as a separate contractual boundary; not substituted for expected close "
                "because extension rights are not yet fully structured"
            ),
            "expected_close_when_empirical_prior_is_sparse_days": _EXPECTED_CLOSE_DAYS,
            "minimum_preannouncement_beta_returns": _MIN_BETA_RETURNS,
            "minimum_concurrent": _MIN_CONCURRENT,
            "minimum_trailing_median_dollar_volume": _MIN_MEDIAN_DOLLAR_VOLUME,
            "name_cap": _NAME_CAP,
            "per_name_fallback_break_loss_cap": _BREAK_LOSS_CAP,
            "announcement_delay": "filing-day close excluded; decision on next close; fill following close",
            "execution": (
                "Aegis production simulator, whole shares, next-close fills and 2% drift bands; "
                "resolution exits use the last adjusted market mark, never a parsed synthetic payout"
            ),
            "costs": {"fixed_usd_per_order": _FIXED_FEE, "slippage": _SLIPPAGE},
            "dividends": "Massive split-adjusted cash distributions on ex-date",
            "cash_benchmark_and_reserve": (
                "FRED DTB3; reserve overlay applied to lagged unallocated target weight"
            ),
            "known_limits": [
                "guidance comes from target 8-K item text; proxy, tender and exhibit-only updates are not yet complete",
                "outside dates are observed but do not shape the tail until extension mechanics are fully structured",
                "beta uses the existing 50-calendar-day preannouncement price window",
                "reserve accrues on target rather than realized post-rounding cash",
                "hazards use only a small first-period cohort and a pooled adverse rate",
                "evaluation history was previously viewed for the q70 benchmark",
            ],
        },
        "results": results,
        "guided_enp_survives_frozen_gate": hazard_survives,
        "verdict": verdict,
    }


def _timing_coverage(tape: PriceTape) -> dict[str, Any]:
    guided = {deal_id for deal_id, rows in tape.timing.guidance.items() if rows}
    bounded = {deal_id for deal_id, rows in tape.timing.outside_dates.items() if rows}
    retained = {deal.deal_id for deal in tape.deals}
    precision = defaultdict(int)
    for deal_id in retained:
        for observation in tape.timing.guidance.get(deal_id, ()):
            precision[observation.interval.precision] += 1
    return {
        "retained_deals": len(retained),
        "deals_with_guidance": len(retained & guided),
        "guidance_coverage": len(retained & guided) / len(retained),
        "deals_with_outside_date": len(retained & bounded),
        "outside_date_coverage": len(retained & bounded) / len(retained),
        "deals_with_both": len(retained & guided & bounded),
        "guidance_observations_by_precision": dict(precision),
    }
