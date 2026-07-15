#!/usr/bin/env python3
"""Refresh validated SEC/ECB snapshots, then build Demeter cash-merger configs."""

from __future__ import annotations

import argparse
import warnings
from datetime import date
from pathlib import Path
from typing import Protocol

import requests

from research.aegis_research.external_data.ecb_fx import EcbFxError, EcbUsdEurSource
from research.aegis_research.external_data.sec_cash_mergers import (
    CashMergerSourceError,
    SecCashMergerEventSource,
)
from research.configs.demeter.cash_merger_family import (
    CashMergerConfigRequest,
    materialize_cash_merger_configs,
)


def _mapping(value: str) -> tuple[str, str]:
    symbol, separator, instrument_id = value.partition("=")
    if not separator or not symbol or not instrument_id:
        raise argparse.ArgumentTypeError("instrument mappings use SYMBOL=INSTRUMENT.VENUE")
    return symbol.upper(), instrument_id


class _SnapshotSource[SnapshotT](Protocol):
    def refresh(self, start: date, end: date) -> None: ...

    def load_cached(self, start: date, end: date) -> SnapshotT: ...


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

    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)
    event_source = SecCashMergerEventSource(args.event_cache)
    event_snapshot = _refresh_or_cached(event_source, start, end)
    fx_source = EcbUsdEurSource(args.fx_cache)
    fx_snapshot = _refresh_or_cached(fx_source, start, end)
    paths = materialize_cash_merger_configs(
        event_snapshot,
        CashMergerConfigRequest(
            event_snapshot_path=event_source.cached_path(event_snapshot),
            fx_snapshot_path=fx_source.cached_path(fx_snapshot),
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


def _refresh_or_cached[SnapshotT](
    source: _SnapshotSource[SnapshotT], start: date, end: date
) -> SnapshotT:
    try:
        source.refresh(start, end)
    except (requests.RequestException, CashMergerSourceError, EcbFxError) as error:
        warnings.warn(f"external-data refresh failed; using validated cache: {error}", stacklevel=2)
    return source.load_cached(start, end)


if __name__ == "__main__":
    raise SystemExit(main())
