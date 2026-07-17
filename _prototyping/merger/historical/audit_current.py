"""Audit the cached Massive pending tape against an independent current list."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import date
from pathlib import Path

from cash_merger.census import audit_coverage, load_snapshot
from cash_merger.ditat import DitatPendingCashReferenceSource


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("snapshot", type=Path)
    args = parser.parse_args()
    snapshot = load_snapshot(args.snapshot)
    references = DitatPendingCashReferenceSource().deals(date.today(), date.today())
    audit = audit_coverage(snapshot.deals, references)
    report = {
        **asdict(audit),
        "passes_90_percent_gate": audit.passes(0.90),
        "massive_pending_symbols": sorted(
            deal.announcement_symbol for deal in snapshot.deals if deal.outcome == "pending"
        ),
        "reference_cash_symbols": sorted(
            deal.target_symbol for deal in references if deal.target_symbol is not None
        ),
        "contract": (
            "Ditat is an independent current-snapshot audit only; it is not a strategy input "
            "and does not establish historical recall."
        ),
    }
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
