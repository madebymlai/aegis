"""IBKR qualification, catalog fill, and causal panel construction for UCITS ETFs."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from .model import (
    MIN_CLUSTER_SIZE,
    MINIMUM_HISTORY_SESSIONS,
    PrototypeState,
    state_from_history,
)
from .universe import BENCHMARK, UCITS_UNIVERSE, UcitsCandidate

if TYPE_CHECKING:
    from aegis_data.catalog import CatalogBackedDataPort
    from aegis_data.ibkr import IbkrHistoricalProvider

MINIMUM_DOLLAR_VOLUME = 250_000.0
HISTORY_CALENDAR_DAYS = 550
MINIMUM_FAMILY_SIZE = MIN_CLUSTER_SIZE


class CandidateExclusion(Exception):
    """A named reason one UCITS candidate cannot enter the audit panel."""


class CandidateIneligible(CandidateExclusion):
    """The freshly qualified IB contract fails an eligibility invariant."""


class CandidateDataUnavailable(CandidateExclusion):
    """Required causal history could not be loaded for one candidate."""


class UniverseHistoryInvalid(ValueError):
    """The screened histories cannot form a valid UCITS peer panel."""


@dataclass(frozen=True)
class AssetHistory:
    ticker: str
    family: str
    instrument_id: str
    frame: pd.DataFrame
    distributions: Mapping[pd.Timestamp, float]


@dataclass(frozen=True)
class IncludedAsset:
    ticker: str
    family: str
    instrument_id: str
    observations: int
    median_dollar_volume: float


@dataclass(frozen=True)
class ExcludedAsset:
    ticker: str
    reason: str


@dataclass(frozen=True)
class UniverseLoad:
    state: PrototypeState
    execution_returns: pd.DataFrame
    dollar_volumes: pd.DataFrame
    included: tuple[IncludedAsset, ...]
    excluded: tuple[ExcludedAsset, ...]
    benchmark: str
    start: str
    end: str


def load_ucits_universe(
    *,
    as_of: str | None = None,
    catalog_path: Path | None = None,
    gateway_port: int = 4002,
    client_id: int = 43,
    history_calendar_days: int = HISTORY_CALENDAR_DAYS,
    minimum_median_dollar_volume: float = MINIMUM_DOLLAR_VOLUME,
    progress: Callable[[str], None] | None = None,
) -> UniverseLoad:
    """Qualify and load each candidate independently through one IBKR session."""

    from aegis_data.catalog import CatalogBackedDataPort, open_catalog
    from aegis_data.custom_data import CustomDataWarmer
    from aegis_data.ibkr import (
        IbkrHistoricalProvider,
        historic_catalog_client_factory,
        historic_data_client_factory,
        seed_instrument_definitions,
    )
    from aegis_data.research_bars import CatalogBarWarmer

    report = progress or (lambda _message: None)
    end = as_of or latest_completed_london_session().date().isoformat()
    start = (
        (pd.Timestamp(end) - pd.Timedelta(days=history_calendar_days))
        .date()
        .isoformat()
    )
    provider = IbkrHistoricalProvider(
        port=gateway_port,
        client_id=client_id,
        market_data_type="DELAYED_FROZEN",
        call_deadline=90,
    )
    catalog = open_catalog(catalog_path)
    port = CatalogBackedDataPort(
        catalog,
        provider=CatalogBarWarmer(catalog, historic_data_client_factory(provider)),
        custom_data_warmer=CustomDataWarmer(
            catalog,
            historic_catalog_client_factory(provider),
        ),
        definition_seeder=lambda instrument_id: seed_instrument_definitions(
            catalog, provider, (instrument_id,)
        ),
    )
    histories: dict[str, AssetHistory] = {}
    exclusions: list[ExcludedAsset] = []
    for candidate in UCITS_UNIVERSE:
        report(f"loading {candidate.instrument_id} {start}..{end}")
        try:
            histories[candidate.ticker] = _load_candidate_history(
                provider=provider,
                port=port,
                candidate=candidate,
                start=start,
                end=end,
            )
        except CandidateExclusion as error:
            reason = str(error)
            exclusions.append(ExcludedAsset(candidate.ticker, reason))
            report(f"excluded {candidate.ticker}: {reason}")
    loaded = history_to_state(
        histories,
        benchmark=BENCHMARK,
        minimum_median_dollar_volume=minimum_median_dollar_volume,
    )
    return UniverseLoad(
        state=loaded.state,
        execution_returns=loaded.execution_returns,
        dollar_volumes=loaded.dollar_volumes,
        included=loaded.included,
        excluded=tuple(
            sorted((*exclusions, *loaded.excluded), key=lambda item: item.ticker)
        ),
        benchmark=BENCHMARK,
        start=start,
        end=end,
    )


def _load_candidate_history(
    *,
    provider: IbkrHistoricalProvider,
    port: CatalogBackedDataPort,
    candidate: UcitsCandidate,
    start: str,
    end: str,
) -> AssetHistory:
    from aegis_data.catalog import CatalogWindowRequest
    from nautilus_trader.model.identifiers import InstrumentId

    instrument_id = InstrumentId.from_str(candidate.instrument_id)
    try:
        window = port.load_window(
            CatalogWindowRequest((instrument_id,), start, end, "1D")
        )
        live_instrument = _exact_instrument(
            provider.request_instruments((instrument_id,)), candidate
        )
        eligibility_failure = _eligibility_failure(live_instrument)
        if eligibility_failure is not None:
            raise CandidateIneligible(eligibility_failure)
        frame = window.ohlcv[instrument_id]
        distributions = {
            event.ex_date: event.amount
            for event in window.distributions
            if event.instrument_id == instrument_id
        }
    except CandidateExclusion:
        raise
    except Exception as error:
        detail = str(error).strip()
        raise CandidateDataUnavailable(f"{type(error).__name__}: {detail}") from error
    return AssetHistory(
        ticker=candidate.ticker,
        family=candidate.family,
        instrument_id=candidate.instrument_id,
        frame=frame,
        distributions=distributions,
    )


def history_to_state(
    histories: Mapping[str, AssetHistory],
    *,
    benchmark: str,
    minimum_median_dollar_volume: float = MINIMUM_DOLLAR_VOLUME,
) -> UniverseLoad:
    """Convert verified raw bars and distributions into one aligned total-return state."""

    if benchmark not in histories:
        raise UniverseHistoryInvalid(f"benchmark {benchmark} has no usable history")
    accepted, included, excluded = _screen_histories(
        histories,
        benchmark=benchmark,
        minimum_median_dollar_volume=minimum_median_dollar_volume,
    )
    if benchmark not in accepted:
        raise UniverseHistoryInvalid(f"benchmark {benchmark} failed the history gate")
    accepted, included, family_exclusions = _prune_incomplete_families(
        accepted, included, benchmark=benchmark
    )
    excluded.extend(family_exclusions)
    tradeable = {
        ticker: history for ticker, history in accepted.items() if ticker != benchmark
    }
    if len(tradeable) < MINIMUM_FAMILY_SIZE:
        raise UniverseHistoryInvalid(
            f"fewer than {MINIMUM_FAMILY_SIZE} UCITS peer candidates survived"
        )
    returns, volumes, gaps = _aligned_arrays(accepted)
    market = returns.pop(benchmark).rename(benchmark)
    volumes = volumes.drop(columns=benchmark)
    gaps = gaps.drop(columns=benchmark)
    state = state_from_history(returns, market, volumes, gaps)
    execution_returns = _next_session_execution_returns(
        accepted, state.returns.index
    ).drop(columns=benchmark)
    dollar_volumes = _dollar_volume_panel(accepted, state.returns.index).drop(
        columns=benchmark
    )
    return UniverseLoad(
        state=state,
        execution_returns=execution_returns,
        dollar_volumes=dollar_volumes,
        included=tuple(sorted(included, key=lambda item: item.ticker)),
        excluded=tuple(sorted(excluded, key=lambda item: item.ticker)),
        benchmark=benchmark,
        start=state.returns.index[0].date().isoformat(),
        end=state.returns.index[-1].date().isoformat(),
    )


def _screen_histories(
    histories: Mapping[str, AssetHistory],
    *,
    benchmark: str,
    minimum_median_dollar_volume: float,
) -> tuple[dict[str, AssetHistory], list[IncludedAsset], list[ExcludedAsset]]:
    required_observations = MINIMUM_HISTORY_SESSIONS
    accepted: dict[str, AssetHistory] = {}
    included: list[IncludedAsset] = []
    excluded: list[ExcludedAsset] = []
    for ticker, history in histories.items():
        frame = _normalized_frame(history.frame)
        if len(frame) < required_observations:
            excluded.append(
                ExcludedAsset(ticker, f"fewer than {required_observations} daily bars")
            )
            continue
        dollar_volume = float((frame["Close"] * frame["Volume"]).tail(60).median())
        if ticker != benchmark and dollar_volume < minimum_median_dollar_volume:
            excluded.append(
                ExcludedAsset(
                    ticker,
                    f"median dollar volume below ${minimum_median_dollar_volume:,.0f}",
                )
            )
            continue
        accepted[ticker] = AssetHistory(
            ticker=history.ticker,
            family=history.family,
            instrument_id=history.instrument_id,
            frame=frame,
            distributions=history.distributions,
        )
        included.append(
            IncludedAsset(
                ticker=ticker,
                family=history.family,
                instrument_id=history.instrument_id,
                observations=len(frame),
                median_dollar_volume=dollar_volume,
            )
        )
    return accepted, included, excluded


def _prune_incomplete_families(
    accepted: Mapping[str, AssetHistory],
    included: list[IncludedAsset],
    *,
    benchmark: str,
) -> tuple[dict[str, AssetHistory], list[IncludedAsset], list[ExcludedAsset]]:
    family_counts: dict[str, int] = {}
    for ticker, history in accepted.items():
        if ticker != benchmark:
            family_counts[history.family] = family_counts.get(history.family, 0) + 1
    incomplete = {
        family for family, count in family_counts.items() if count < MINIMUM_FAMILY_SIZE
    }
    retained = {
        ticker: history
        for ticker, history in accepted.items()
        if history.family not in incomplete
    }
    retained_metadata = [item for item in included if item.family not in incomplete]
    exclusions = [
        ExcludedAsset(
            ticker,
            f"fewer than {MINIMUM_FAMILY_SIZE} liquid funds remain in family",
        )
        for ticker, history in accepted.items()
        if history.family in incomplete
    ]
    return retained, retained_metadata, exclusions


def latest_completed_london_session(now: datetime | None = None) -> pd.Timestamp:
    """Conservatively return the latest completed London business date."""

    current = now or datetime.now(tz=ZoneInfo("Europe/London"))
    local = pd.Timestamp(current)
    if local.tzinfo is None:
        local = local.tz_localize("Europe/London")
    else:
        local = local.tz_convert("Europe/London")
    date = local.normalize()
    if local.weekday() >= 5 or (local.hour, local.minute) < (16, 45):
        date = date - pd.offsets.BDay()
    return date


def _exact_instrument(
    instruments: Iterable[object], candidate: UcitsCandidate
) -> object:
    matches = [
        item
        for item in instruments
        if getattr(getattr(item, "id", None), "value", None) == candidate.instrument_id
    ]
    if len(matches) != 1:
        raise CandidateDataUnavailable(
            f"qualification returned {len(matches)} exact matches"
        )
    return matches[0]


def _eligibility_failure(instrument: object) -> str | None:
    info = instrument.info  # type: ignore[attr-defined]
    contract = info.get("contract", {})
    if info.get("stockType") != "ETF":
        return f"IB stock type is {info.get('stockType')!r}, not ETF"
    if contract.get("currency") != "USD":
        return f"listing currency is {contract.get('currency')!r}, not USD"
    if contract.get("primaryExchange") != "LSEETF":
        return f"primary exchange is {contract.get('primaryExchange')!r}, not LSEETF"
    reasons = info.get("ineligibilityReasons") or info.get("ineligibilityReasonList")
    if reasons:
        return "IB account marks the contract ineligible"
    return None


def _normalized_frame(frame: pd.DataFrame) -> pd.DataFrame:
    normalized = frame.loc[:, ["Open", "High", "Low", "Close", "Volume"]].copy()
    normalized.index = pd.to_datetime(normalized.index, utc=True).normalize()
    return normalized[~normalized.index.duplicated(keep="last")].sort_index()


def _aligned_arrays(
    histories: Mapping[str, AssetHistory],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    returns: dict[str, pd.Series] = {}
    volumes: dict[str, pd.Series] = {}
    gaps: dict[str, pd.Series] = {}
    for ticker, history in histories.items():
        frame = history.frame
        cash = _distribution_series(history)
        previous_close = frame["Close"].shift(1)
        returns[ticker] = np.log((frame["Close"] + cash) / previous_close)
        gaps[ticker] = np.log((frame["Open"] + cash) / previous_close)
        volumes[ticker] = frame["Volume"]
    return_panel = pd.DataFrame(returns).replace([np.inf, -np.inf], np.nan).dropna()
    volume_panel = pd.DataFrame(volumes).reindex(return_panel.index).dropna()
    gap_panel = pd.DataFrame(gaps).reindex(return_panel.index).dropna()
    common = return_panel.index.intersection(volume_panel.index).intersection(
        gap_panel.index
    )
    return return_panel.loc[common], volume_panel.loc[common], gap_panel.loc[common]


def _next_session_execution_returns(
    histories: Mapping[str, AssetHistory], state_index: pd.Index
) -> pd.DataFrame:
    returns: dict[str, pd.Series] = {}
    for ticker, history in histories.items():
        frame = history.frame
        cash = _distribution_series(history)
        open_to_next_open = np.log(
            (frame["Open"].shift(-1) + cash.shift(-1)) / frame["Open"]
        )
        returns[ticker] = open_to_next_open.shift(-1)
    return pd.DataFrame(returns).reindex(state_index)


def _dollar_volume_panel(
    histories: Mapping[str, AssetHistory], state_index: pd.Index
) -> pd.DataFrame:
    return pd.DataFrame(
        {
            ticker: history.frame["Close"] * history.frame["Volume"]
            for ticker, history in histories.items()
        }
    ).reindex(state_index)


def _distribution_series(history: AssetHistory) -> pd.Series:
    cash = pd.Series(0.0, index=history.frame.index)
    for ex_date, amount in history.distributions.items():
        date = pd.Timestamp(ex_date)
        if date.tzinfo is None:
            date = date.tz_localize("UTC")
        else:
            date = date.tz_convert("UTC")
        date = date.normalize()
        if date in cash.index:
            cash.loc[date] += float(amount)
    return cash
