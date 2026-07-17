"""Run the repaired cash-merger alpha benchmark in one command."""

from __future__ import annotations

import argparse
import json
import os
from datetime import date
from pathlib import Path

from cash_merger.alpha import alpha_report
from cash_merger.massive import MassiveClient

_ROOT = Path(__file__).resolve().parent


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--snapshot",
        type=Path,
        default=_ROOT / "offline-v9" / "cash-merger-census-c54377d961e20acb.json",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=_ROOT / "cache-v5" / "massive-http",
    )
    parser.add_argument("--capital", type=float, default=5_000.0)
    parser.add_argument(
        "--evaluation-start",
        type=date.fromisoformat,
        required=True,
        help="First common evaluation date; hazard training ends the previous day.",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=_ROOT / "alpha-report.json",
    )
    return parser.parse_args()


def main() -> None:
    args = _arguments()
    api_key = os.environ.get("MASSIVE_API_KEY")
    if not api_key:
        raise SystemExit("MASSIVE_API_KEY is required")
    client = MassiveClient(
        api_key,
        cache_dir=args.cache_dir,
        minimum_interval_seconds=12.2,
    )
    report = alpha_report(
        args.snapshot,
        client,
        capital=args.capital,
        evaluation_start=args.evaluation_start,
    )
    payload = json.dumps(report, indent=2, sort_keys=True, allow_nan=True) + "\n"
    args.report.write_text(payload)
    print(payload, end="")


if __name__ == "__main__":
    main()
