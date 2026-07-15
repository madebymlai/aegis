#!/usr/bin/env python3
"""Build the six Demeter cash-merger wiring configs from a validated event cache."""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from research.aegis_research.external_data.sec_cash_mergers import SecCashMergerEventSource
from research.configs.demeter.cash_merger_family import (
    CashMergerConfigRequest,
    materialize_cash_merger_configs,
)


def _mapping(value: str) -> tuple[str, str]:
    symbol, separator, instrument_id = value.partition("=")
    if not separator or not symbol or not instrument_id:
        raise argparse.ArgumentTypeError("instrument mappings use SYMBOL=INSTRUMENT.VENUE")
    return symbol.upper(), instrument_id


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event-cache", type=Path, required=True)
    parser.add_argument("--fx-cache", type=Path, required=True)
    parser.add_argument("--instrument", action="append", type=_mapping, required=True)
    parser.add_argument("--benchmark", default="SPY.ARCA")
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    snapshot = SecCashMergerEventSource(args.event_cache).load(
        date.fromisoformat(args.start),
        date.fromisoformat(args.end),
        refresh=True,
    )
    paths = materialize_cash_merger_configs(
        snapshot,
        CashMergerConfigRequest(
            event_cache_dir=args.event_cache,
            fx_cache_dir=args.fx_cache,
            instrument_ids=dict(args.instrument),
            benchmark_instrument_id=args.benchmark,
            start=args.start,
            end=args.end,
        ),
        args.output_dir,
    )
    for path in paths:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
