#!/usr/bin/env python3
"""Evaluate materialized Demeter cash-merger configs beside locked Atalanta."""

from __future__ import annotations

import argparse
import json

from research.configs.demeter.cash_merger_evaluation import (
    evaluate_cash_merger_frontier,
)


def _labeled_path(value: str) -> tuple[str, str]:
    label, separator, path = value.partition("=")
    if not separator or not label or not path:
        raise argparse.ArgumentTypeError("Demeter configs use LABEL=/path/to/config.yaml")
    return label, path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trend", required=True)
    parser.add_argument("--demeter", action="append", type=_labeled_path, required=True)
    args = parser.parse_args()
    report = evaluate_cash_merger_frontier(args.trend, dict(args.demeter))
    print(json.dumps(report, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
