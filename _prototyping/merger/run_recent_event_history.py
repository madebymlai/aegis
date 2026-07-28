"""Audit recent cash-merger history through the active event and selector path."""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from cash_merger.massive import MassiveClient

from _prototyping.merger.historical.recent import (
    MassiveEventTapeSource,
    MassiveHistoricalBars,
    MassiveMarkSource,
    adapt_events,
)
from _prototyping.merger.legacy_aegis_rd.external_data.sec_cash_mergers import (
    SecCashMergerEventSource,
)
from _prototyping.merger.shadow.shadow import CashMergerShadow

_DEFAULT_CACHE = (
    Path(__file__).resolve().parent / "historical" / "cache-v5" / "massive-http"
)
_MINIMUM_EVENT_WARMUP_DAYS = 730
_DEFAULT_OUTPUT = (
    Path(__file__).resolve().parent
    / "historical"
    / "recent-event-driven-selection-report.json"
)


class HistoricalReplayInputError(ValueError):
    """The requested discovery or evaluation window is invalid."""


def run_recent_event_history(
    *,
    cache_dir: Path,
    event_start: date,
    start: date,
    end: date,
    capital: float,
    annual_cash_rate: float,
    fetch_events: bool = False,
    market_api_key: str | None = None,
) -> dict[str, Any]:
    """Replay SEC-derived causal events daily through ``CashMergerShadow``.

    SEC EDGAR master indexes establish the historical event population.
    ``ShadowLedger`` reduces those observations to the active set at each date,
    Massive supplies only recent OHLCV, and the unmodified active selector makes
    the monthly decision.
    """

    if event_start > start - timedelta(days=_MINIMUM_EVENT_WARMUP_DAYS):
        raise HistoricalReplayInputError(
            "event discovery must include at least 730 days of warmup"
        )
    if event_start > start:
        raise HistoricalReplayInputError("event discovery start exceeds evaluation start")
    if start > end:
        raise HistoricalReplayInputError("evaluation start exceeds evaluation end")

    event_source = SecCashMergerEventSource(cache_dir / "edgar-events")
    if fetch_events:
        event_source.sync(event_start, end)
    tape = event_source.load(event_start, end)
    observations, reviews = adapt_events(
        tape.events,
        source_label="SEC EDGAR event tape",
    )
    bars = MassiveHistoricalBars(
        MassiveClient(market_api_key or "offline-cache-only", cache_dir=cache_dir),
        allow_fetch=market_api_key is not None,
    )
    market = bars.bars("SPY", start, end)
    trading_days = tuple(timestamp.date() for timestamp in market.index)
    source = MassiveEventTapeSource(observations, reviews)
    marks = MassiveMarkSource(bars, annual_cash_rate=annual_cash_rate)

    event_status = Counter(event.status for event in tape.events)
    observation_status = Counter(item.status.value for item in observations)
    exclusion_reasons: Counter[str] = Counter()
    unavailable_reasons: Counter[str] = Counter()
    monthly_assessments: dict[str, int] = {}
    monthly_positions: dict[str, int] = {}
    terminal_exit_events: set[str] = set()
    selection_days = 0
    invested_days = 0
    prior_refresh_end = event_start - timedelta(days=1)

    with TemporaryDirectory(prefix="aegis-merger-event-replay-") as temporary:
        shadow = CashMergerShadow(Path(temporary))
        for trading_day in trading_days:
            result = shadow.run(
                source=source,
                marks=marks,
                start=prior_refresh_end + timedelta(days=1),
                end=trading_day,
                as_of=datetime.combine(trading_day, datetime.max.time(), UTC),
                capital=capital,
            )
            prior_refresh_end = trading_day
            unavailable_reasons.update(
                item.reason for item in result.market_unavailable_items
            )
            if result.selection_formed:
                selection_days += 1
                month = trading_day.strftime("%Y-%m")
                monthly_assessments[month] = len(result.selection.assessments)
                monthly_positions[month] = len(result.selection.decision.positions)
                exclusion_reasons.update(
                    exclusion.reason.value for exclusion in result.selection.exclusions
                )
            if result.selection.decision.positions:
                invested_days += 1
            terminal_exit_events.update(result.terminal_exit_event_ids)

    maximum_assessments = max(monthly_assessments.values(), default=0)
    maximum_positions = max(monthly_positions.values(), default=0)
    alpha_claim = invested_days > 0
    classification = (
        "candidate_return_stream_generated"
        if alpha_claim
        else "no_return_stream_under_active_selector"
    )
    return {
        "schema_version": 1,
        "classification": classification,
        "alpha_claim_supported": False,
        "alpha_claim_reason": (
            "A position path exists but return validation is outside this audit."
            if alpha_claim
            else "The active selector never formed the required diversified position set."
        ),
        "architecture": {
            "membership": "filing event -> event-time identity -> active lifecycle set",
            "instrument_identity": (
                "provisional event-time ticker plus CIK; not canonical Nautilus identity"
            ),
            "canonical_instrument_identity_resolved": False,
            "selection": "CashMergerSelector via CashMergerShadow",
            "cache_role": "immutable source evidence and OHLCV only",
            "event_source_mode": "sec_edgar_master_index",
            "live_event_query_completed": fetch_events,
            "market_source_mode": (
                "massive_recent_ohlcv_with_immutable_cache"
                if market_api_key is not None
                else "massive_offline_cache"
            ),
            "configured_or_current_symbol_cohort_used": False,
            "source_completeness": "validated SEC snapshot coverage",
        },
        "window": {
            "warmup_policy": "two_year_continuous_event_history",
            "warmup_calendar_days": (start - event_start).days,
            "event_discovery_start": event_start.isoformat(),
            "source_evidence_start": tape.covered_start,
            "source_evidence_end": tape.covered_end,
            "warmup_coverage_satisfied": (
                date.fromisoformat(tape.covered_start) <= event_start
                and date.fromisoformat(tape.covered_end) >= end
            ),
            "start": start.isoformat(),
            "end": end.isoformat(),
            "trading_days": len(trading_days),
            "first_market_day": trading_days[0].isoformat() if trading_days else None,
            "last_market_day": trading_days[-1].isoformat() if trading_days else None,
        },
        "event_tape": {
            "source_events": len(tape.events),
            "source_event_status": dict(sorted(event_status.items())),
            "observations": len(observations),
            "observation_status": dict(sorted(observation_status.items())),
            "lifecycles": len({item.event_id for item in observations}),
            "event_time_tickers": len({item.ticker for item in observations}),
            "unlinked_terminal_reviews": len(reviews),
            "unresolved_announcement_identities": None,
            "unresolved_identity_accession_sample": [],
            "identity_resolution_audit_available": False,
        },
        "selection_audit": {
            "capital": capital,
            "annual_cash_rate": annual_cash_rate,
            "selection_days": selection_days,
            "invested_days": invested_days,
            "maximum_monthly_assessments": maximum_assessments,
            "maximum_monthly_positions": maximum_positions,
            "monthly_assessments": monthly_assessments,
            "monthly_positions": monthly_positions,
            "terminal_exit_lifecycles": len(terminal_exit_events),
            "selection_exclusions": dict(sorted(exclusion_reasons.items())),
            "market_unavailable_observations": dict(sorted(unavailable_reasons.items())),
        },
    }


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-dir", type=Path, default=_DEFAULT_CACHE)
    parser.add_argument("--output", type=Path, default=_DEFAULT_OUTPUT)
    parser.add_argument(
        "--event-start",
        type=date.fromisoformat,
        default=date(2022, 7, 16),
    )
    parser.add_argument("--start", type=date.fromisoformat, default=date(2024, 7, 16))
    parser.add_argument("--end", type=date.fromisoformat, default=date(2026, 7, 16))
    parser.add_argument("--capital", type=float, default=100_000.0)
    parser.add_argument("--annual-cash-rate", type=float, default=0.04)
    parser.add_argument(
        "--fetch-events",
        action="store_true",
        help="Backfill the complete requested event range from SEC EDGAR.",
    )
    parser.add_argument(
        "--fetch-market",
        action="store_true",
        help="Fetch missing recent OHLCV using MASSIVE_API_KEY.",
    )
    return parser.parse_args()


def main() -> None:
    arguments = _arguments()
    market_api_key = os.environ.get("MASSIVE_API_KEY") if arguments.fetch_market else None
    if arguments.fetch_market and market_api_key is None:
        raise SystemExit("--fetch-market requires MASSIVE_API_KEY in the process environment")
    report = run_recent_event_history(
        cache_dir=arguments.cache_dir,
        event_start=arguments.event_start,
        start=arguments.start,
        end=arguments.end,
        capital=arguments.capital,
        annual_cash_rate=arguments.annual_cash_rate,
        fetch_events=arguments.fetch_events,
        market_api_key=market_api_key,
    )
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
