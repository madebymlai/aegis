"""Build the recent Massive cash-merger census and stop at the coverage gate."""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

from cash_merger.census import (
    CashMergerCensusSource,
    CashMergerEvent,
)
from cash_merger.ditat import DitatPendingCashReferenceSource
from cash_merger.eligibility import DomesticIssuerReferenceSource
from cash_merger.massive import MassiveClient
from cash_merger.target_events import MassiveTargetEventSource

_ROOT = Path(__file__).resolve().parent


@dataclass(frozen=True)
class _ObservedEvents:
    observations: tuple[CashMergerEvent, ...]

    def events(self, start: date, end: date) -> Iterable[CashMergerEvent]:
        return self.observations


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a Massive-sourced fixed-cash merger tape in the prototype cache."
    )
    parser.add_argument("--start", type=date.fromisoformat, required=True)
    parser.add_argument("--end", type=date.fromisoformat, required=True)
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=_ROOT / "cache",
    )
    return parser.parse_args()


def _active_breadth(deals, start: date, end: date) -> dict[str, float | int]:
    days = max((end - start).days + 1, 1)
    counts: list[int] = []
    for offset in range(days):
        current = date.fromordinal(start.toordinal() + offset)
        counts.append(
            sum(
                date.fromisoformat(deal.announced_at[:10]) <= current
                and (
                    deal.resolved_at is None or current < date.fromisoformat(deal.resolved_at[:10])
                )
                for deal in deals
            )
        )
    ordered = sorted(counts)
    return {
        "mean_active": sum(counts) / len(counts),
        "median_active": ordered[len(ordered) // 2],
        "maximum_active": max(counts),
        "days_with_ten_or_more": sum(count >= 10 for count in counts),
        "fraction_days_with_ten_or_more": sum(count >= 10 for count in counts) / len(counts),
    }


def main() -> None:
    args = _arguments()
    api_key = os.environ.get("MASSIVE_API_KEY")
    if not api_key:
        raise SystemExit("MASSIVE_API_KEY is required in the process environment")
    client = MassiveClient(api_key, cache_dir=args.cache_dir / "massive-http")
    provider = MassiveTargetEventSource(client)
    observations = provider.events(args.start, args.end)
    source = CashMergerCensusSource(
        cache_dir=args.cache_dir / "census",
        events=_ObservedEvents(observations),
        references=DomesticIssuerReferenceSource(
            DitatPendingCashReferenceSource(),
            client,
        ),
    )
    snapshot = source.sync(args.start, args.end)
    breadth = _active_breadth(snapshot.deals, args.start, args.end)
    report = {
        "source": (
            "Massive target-role disclosures with batched target-CIK 8-K validation"
        ),
        "covered_start": snapshot.covered_start,
        "covered_end": snapshot.covered_end,
        "causal_observations": len(observations),
        "fixed_cash_deals": len(snapshot.deals),
        "completed": sum(deal.outcome == "completed" for deal in snapshot.deals),
        "terminated": sum(deal.outcome == "terminated" for deal in snapshot.deals),
        "pending": sum(deal.outcome == "pending" for deal in snapshot.deals),
        "breadth": breadth,
        "coverage_gate": {
            **asdict(snapshot.audit),
            "passes": snapshot.audit.passes(0.90),
            "reason": (
                "Current pending-target recall against independently listed cash deals, "
                "restricted to domestic SEC 10-K filers supported by the 8-K source; "
                "the reference is audit-only and never enters selection or sizing."
            ),
        },
        "advance_to_priceability": snapshot.audit.passes(0.90),
        "cache_identity": snapshot.source_sha256,
    }
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
