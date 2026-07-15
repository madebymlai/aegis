#!/usr/bin/env python3
"""Evaluate two locked strategy configs as the trend/carry floor book."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

from scripts.floor_evaluation import (  # noqa: E402
    FloorEvaluationSettings,
    evaluate_locked_floor_configs,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trend", type=Path, required=True, help="locked trend Run Config path")
    parser.add_argument("--carry", type=Path, required=True, help="locked carry Run Config path")
    parser.add_argument(
        "--carry-weight",
        type=float,
        default=0.40,
        help="pre-declared carry weight in the monthly return mix (default: 0.40)",
    )
    parser.add_argument(
        "--risk-aversion",
        type=float,
        default=3.0,
        help="CRRA coefficient used by MPPM certainty equivalent (default: 3)",
    )
    parser.add_argument(
        "--bootstrap-samples",
        type=int,
        default=2_000,
        help="paired circular-block bootstrap samples per block length (default: 2000)",
    )
    parser.add_argument(
        "--block-length",
        type=int,
        action="append",
        dest="block_lengths",
        help="monthly circular-block length; repeat for sensitivity (default: 1, 3, 6)",
    )
    parser.add_argument("--seed", type=int, default=42, help="bootstrap seed (default: 42)")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    trend_path = args.trend.expanduser().resolve()
    carry_path = args.carry.expanduser().resolve()
    os.chdir(REPOSITORY_ROOT)
    settings = FloorEvaluationSettings(
        carry_weight=args.carry_weight,
        risk_aversion=args.risk_aversion,
        bootstrap_samples=args.bootstrap_samples,
        block_lengths=tuple(args.block_lengths or (1, 3, 6)),
        seed=args.seed,
    )
    try:
        report = evaluate_locked_floor_configs(trend_path, carry_path, settings=settings)
    except Exception as error:
        print(
            json.dumps({"error_type": type(error).__name__, "error": str(error)}),
            file=sys.stderr,
        )
        return 1
    print(json.dumps(report, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
