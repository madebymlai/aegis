"""Replay merger decisions from Edgartools events and Aegis catalog market data."""

from __future__ import annotations

import argparse
import calendar
import json
from dataclasses import asdict
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

from _prototyping.merger.cli import default_state_dir, iso_date
from _prototyping.merger.config import (
    CashMergerPrototypeConfig,
    load_prototype_config,
)
from _prototyping.merger.shadow import (
    AegisCatalogMarkSource,
    CashMergerShadow,
    EdgarEventSource,
    FredDtb3RateSource,
    IssuerIdentity,
    ObservedCashRate,
    ShadowLedger,
    ShadowRunEvidence,
)


class HistoricalIdentityError(ValueError):
    """Persisted merger evidence disagrees about one instrument's issuer identity."""


class HistoricalReplayConfigError(ValueError):
    """Historical replay state is configured inconsistently."""


def main() -> None:
    args = _arguments()
    config = load_prototype_config(args.config)
    root = args.state_dir.expanduser().resolve()
    decisions, unavailable_count = _replay(
        config,
        root=root,
        start=args.start,
        end=args.end,
        source_state_dir=args.source_state_dir,
    )
    payload = _report(
        decisions,
        unavailable_count=unavailable_count,
        start=args.start,
        end=args.end,
    )
    print(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False))
    if unavailable_count:
        raise SystemExit(
            f"historical replay incomplete: {unavailable_count} required market marks "
            "were unavailable"
        )


def _replay(
    config: CashMergerPrototypeConfig,
    *,
    root: Path,
    start: date,
    end: date,
    source_state_dir: Path | None,
) -> tuple[tuple[dict[str, object], ...], int]:
    instrument_ids = tuple(str(item) for item in config.instrument_ids)
    _seed_event_ledger(
        root,
        source_state_dir=source_state_dir,
        instrument_ids=instrument_ids,
        as_of=datetime.combine(end, time.max, UTC),
    )
    shadow = CashMergerShadow(root)
    source = EdgarEventSource(
        instrument_ids,
        frozen_identities=_frozen_identities(
            root,
            instrument_ids=instrument_ids,
            as_of=datetime.combine(end, time.max, UTC),
        ),
    )
    cash_rates = FredDtb3RateSource(root / "sources" / "fred-dtb3")
    decisions: list[dict[str, object]] = []
    unavailable_count = 0

    for period_start, period_end in _monthly_windows(start, end):
        as_of = datetime.combine(period_end, time.max, UTC)
        cash_rate = cash_rates.latest(as_of=period_end)
        evidence = shadow.run(
            source=source,
            marks=AegisCatalogMarkSource(
                cash_rate.annual_rate,
                catalog_path=config.catalog_path,
                market_instrument_id=str(config.market_instrument_id),
            ),
            start=period_start,
            end=period_end,
            as_of=as_of,
            capital=config.capital.value,
        )
        unavailable_count += len(evidence.market_unavailable_items)
        decisions.append(
            _decision_record(
                evidence,
                as_of=as_of,
                period_start=period_start,
                period_end=period_end,
                cash_rate=cash_rate,
            )
        )
    return tuple(decisions), unavailable_count


def _seed_event_ledger(
    root: Path,
    *,
    source_state_dir: Path | None,
    instrument_ids: tuple[str, ...],
    as_of: datetime,
) -> None:
    if source_state_dir is None:
        return
    source_root = source_state_dir.expanduser().resolve()
    if source_root == root:
        raise HistoricalReplayConfigError(
            "history replay state must differ from prospective source state"
        )
    if not source_root.is_dir():
        raise HistoricalReplayConfigError(
            f"prospective source state does not exist: {source_root}"
        )
    source = ShadowLedger(source_root / "ledger")
    configured = set(instrument_ids)
    events = tuple(
        event
        for event in source.events(as_of=as_of)
        if event.instrument_id in configured
    )
    if not events:
        raise HistoricalReplayConfigError(
            "prospective source ledger has no configured-instrument events through "
            f"{as_of.isoformat()}: {source_root}"
        )
    ShadowLedger(root / "ledger").record(events)


def _frozen_identities(
    root: Path,
    *,
    instrument_ids: tuple[str, ...],
    as_of: datetime,
) -> tuple[IssuerIdentity, ...]:
    configured = set(instrument_ids)
    identities: dict[str, IssuerIdentity] = {}
    for event in ShadowLedger(root / "ledger").events(as_of=as_of):
        if event.instrument_id not in configured:
            continue
        identity = IssuerIdentity(event.instrument_id, event.ticker, event.target_cik)
        previous = identities.get(event.instrument_id)
        if previous is not None and previous != identity:
            raise HistoricalIdentityError(
                f"ledger has conflicting issuer identities for {event.instrument_id}"
            )
        identities[event.instrument_id] = identity
    return tuple(identities[key] for key in sorted(identities))


def _decision_record(
    evidence: ShadowRunEvidence,
    *,
    as_of: datetime,
    period_start: date,
    period_end: date,
    cash_rate: ObservedCashRate,
) -> dict[str, object]:
    return {
        "as_of": as_of.isoformat(),
        "source_window": {
            "start": period_start.isoformat(),
            "end": period_end.isoformat(),
        },
        "cash_rate": {
            "observed_on": cash_rate.observed_on.isoformat(),
            "annual_rate": cash_rate.annual_rate,
        },
        "recorded_events": evidence.recorded_observations,
        "market_unavailable": [asdict(item) for item in evidence.market_unavailable_items],
        "assessments": len(evidence.selection.assessments),
        "exclusions": len(evidence.selection.exclusions),
        "positions": [
            asdict(position) for position in evidence.selection.decision.positions
        ],
        "terminal_exit_event_ids": evidence.terminal_exit_event_ids,
        "evidence_path": str(evidence.evidence_path),
    }


def _report(
    decisions: tuple[dict[str, object], ...],
    *,
    unavailable_count: int,
    start: date,
    end: date,
) -> dict[str, object]:
    return {
        "mode": "research_history_replay_no_orders",
        "source": {
            "events": "Edgartools SEC filings by acceptance timestamp",
            "market": "Aegis catalog with IBKR lazy fill",
            "fallback_market_provider": None,
        },
        "start": start.isoformat(),
        "end": end.isoformat(),
        "decision_count": len(decisions),
        "complete_market_coverage": unavailable_count == 0,
        "market_unavailable_count": unavailable_count,
        "decisions": decisions,
    }


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--start", type=iso_date, required=True)
    parser.add_argument("--end", type=iso_date, required=True)
    parser.add_argument(
        "--state-dir",
        type=Path,
        default=default_state_dir("cash-merger-history"),
        help="Dedicated replay state; do not share it with the prospective shadow run.",
    )
    parser.add_argument(
        "--source-state-dir",
        type=Path,
        help=(
            "Optional prospective shadow state whose immutable event ledger seeds "
            "historical issuer identity without current-ticker resolution."
        ),
    )
    return parser.parse_args()


def _monthly_windows(start: date, end: date) -> tuple[tuple[date, date], ...]:
    if end < start:
        raise HistoricalReplayConfigError("history replay end precedes start")
    windows: list[tuple[date, date]] = []
    cursor = start
    while cursor <= end:
        last_day = calendar.monthrange(cursor.year, cursor.month)[1]
        period_end = min(date(cursor.year, cursor.month, last_day), end)
        windows.append((cursor, period_end))
        cursor = period_end + timedelta(days=1)
    return tuple(windows)


if __name__ == "__main__":
    main()
