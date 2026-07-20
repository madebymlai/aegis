"""Run one prospective, research-only cash-merger shadow observation."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import timedelta
from pathlib import Path

from _prototyping.merger.cli import default_state_dir, iso_date, utc_timestamp
from _prototyping.merger.config import load_prototype_config
from _prototyping.merger.shadow import (
    AegisCatalogMarkSource,
    CashMergerShadow,
    EdgarEventSource,
    FredDtb3RateSource,
)


def main() -> None:
    args = _arguments()
    as_of = utc_timestamp(args.as_of)
    config = load_prototype_config(args.config)
    root = args.state_dir.expanduser().resolve()
    shadow = CashMergerShadow(root)
    cash_rate = FredDtb3RateSource(root / "sources" / "fred-dtb3").latest(as_of=as_of.date())
    end = as_of.date() - timedelta(days=1)
    evidence = shadow.run(
        source=EdgarEventSource(tuple(str(item) for item in config.instrument_ids)),
        marks=AegisCatalogMarkSource(
            cash_rate.annual_rate,
            catalog_path=config.catalog_path,
            market_instrument_id=str(config.market_instrument_id),
        ),
        start=shadow.next_refresh_start(
            end=end,
            bootstrap_start=args.bootstrap_start,
        ),
        end=end,
        as_of=as_of,
        capital=config.capital.value,
    )
    print(
        json.dumps(
            {
                "mode": "research_shadow_no_orders",
                "cash_rate": {
                    "series": "DTB3",
                    "observed_on": cash_rate.observed_on.isoformat(),
                    "annual_rate": cash_rate.annual_rate,
                },
                "observations": {
                    "recorded": evidence.recorded_observations,
                    "already_present": evidence.existing_observations,
                    "reviews": evidence.reviews,
                },
                "decision": {
                    "forecast_engine": evidence.selection.engine.engine_id,
                    "decision_engine": evidence.selection.decision_engine_id,
                    "formed_this_run": evidence.selection_formed,
                    "assessments": len(evidence.selection.assessments),
                    "exclusions": len(evidence.selection.exclusions),
                    "positions": len(evidence.selection.decision.positions),
                    "terminal_exit_event_ids": evidence.terminal_exit_event_ids,
                },
                "market_unavailable": [
                    asdict(item) for item in evidence.market_unavailable_items
                ],
                "evidence_gate": asdict(evidence.qualification),
                "evidence_path": str(evidence.evidence_path),
            },
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
    )


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument(
        "--bootstrap-start",
        type=iso_date,
        required=True,
        help=(
            "First SEC filing date to replay when the state directory is empty; "
            "later runs resume from persisted evidence."
        ),
    )
    parser.add_argument(
        "--state-dir",
        type=Path,
        default=default_state_dir("cash-merger-shadow"),
    )
    parser.add_argument(
        "--as-of",
        help="Timezone-aware ISO timestamp; defaults to the current UTC time.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    main()
