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
from cash_merger.target_events import MassiveTargetEventSource

from _prototyping.merger.historical.recent import (
    MassiveEventTapeSource,
    MassiveHistoricalBars,
    MassiveMarkSource,
    MassiveOfflineEvidenceClient,
    adapt_events,
)
from _prototyping.merger.shadow.shadow import CashMergerShadow

_DEFAULT_CACHE = (
    Path(__file__).resolve().parent / "historical" / "cache-v5" / "massive-http"
)
_LATEST_EVENT_DISCOVERY_START = date(1990, 1, 1)
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
    event_api_key: str | None = None,
) -> dict[str, Any]:
    """Replay cached causal events daily through ``CashMergerShadow``.

    Cache contents never establish membership.  ``MassiveTargetEventSource``
    reconstructs lifecycles from filing observations, ``ShadowLedger`` reduces
    them to the active set at each date, and the unmodified active selector makes
    the monthly decision.
    """

    if event_start > _LATEST_EVENT_DISCOVERY_START:
        raise HistoricalReplayInputError(
            "event discovery must begin by 1990-01-01"
        )
    if event_start > start:
        raise HistoricalReplayInputError("event discovery start exceeds evaluation start")
    if start > end:
        raise HistoricalReplayInputError("evaluation start exceeds evaluation end")

    event_client = (
        MassiveClient(event_api_key, cache_dir=cache_dir)
        if event_api_key is not None
        else MassiveOfflineEvidenceClient(cache_dir)
    )
    tape = MassiveTargetEventSource(event_client).load(event_start, end)
    evidence_bounds = (
        MassiveOfflineEvidenceClient(cache_dir).event_disclosure_date_bounds
    )
    observations, reviews = adapt_events(tape.events, filing_rows=tape.filing_rows)
    bars = MassiveHistoricalBars(
        MassiveClient("offline-cache-only", cache_dir=cache_dir),
        allow_fetch=False,
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
            "event_source_mode": (
                "live_paginated_api_with_immutable_cache"
                if event_api_key is not None
                else "offline_cache_scan"
            ),
            "live_event_query_completed": event_api_key is not None,
            "configured_or_current_symbol_cohort_used": False,
            "source_completeness": "not provable from URL-addressed cache alone",
        },
        "window": {
            "event_discovery_start": event_start.isoformat(),
            "source_evidence_start": (
                evidence_bounds[0].isoformat() if evidence_bounds is not None else None
            ),
            "source_evidence_end": (
                evidence_bounds[1].isoformat() if evidence_bounds is not None else None
            ),
            "warmup_coverage_satisfied": False,
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
            "unresolved_announcement_identities": len(
                tape.unresolved_identity_accessions
            ),
            "unresolved_identity_accession_sample": (
                tape.unresolved_identity_accessions[:50]
            ),
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
        default=date(1990, 1, 1),
    )
    parser.add_argument("--start", type=date.fromisoformat, default=date(2024, 7, 16))
    parser.add_argument("--end", type=date.fromisoformat, default=date(2026, 7, 16))
    parser.add_argument("--capital", type=float, default=100_000.0)
    parser.add_argument("--annual-cash-rate", type=float, default=0.04)
    parser.add_argument(
        "--fetch-events",
        action="store_true",
        help="Fetch the complete requested filing range using MASSIVE_API_KEY.",
    )
    return parser.parse_args()


def main() -> None:
    arguments = _arguments()
    event_api_key = os.environ.get("MASSIVE_API_KEY") if arguments.fetch_events else None
    if arguments.fetch_events and event_api_key is None:
        raise SystemExit("--fetch-events requires MASSIVE_API_KEY in the process environment")
    report = run_recent_event_history(
        cache_dir=arguments.cache_dir,
        event_start=arguments.event_start,
        start=arguments.start,
        end=arguments.end,
        capital=arguments.capital,
        annual_cash_rate=arguments.annual_cash_rate,
        event_api_key=event_api_key,
    )
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
