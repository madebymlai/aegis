"""Materialize the Demeter cash-merger config family from its event inventory."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import yaml

from research.aegis_research.external_data.sec_cash_mergers import CashMergerSnapshot


class CashMergerConfigError(ValueError):
    pass


@dataclass(frozen=True)
class CashMergerConfigRequest:
    event_cache_dir: Path
    fx_cache_dir: Path
    instrument_ids: Mapping[str, str]
    benchmark_instrument_id: str
    start: str
    end: str
    init_cash: float = 5_000.0


def materialize_cash_merger_configs(
    snapshot: CashMergerSnapshot,
    request: CashMergerConfigRequest,
    output_dir: Path,
) -> tuple[Path, ...]:
    """Write the preregistered complete/sparse/residual config family."""

    symbols = tuple(
        sorted(
            {
                event.target_symbol
                for event in snapshot.events
                if event.status == "pending" and event.offer_price is not None
            }
        )
    )
    missing = tuple(symbol for symbol in symbols if symbol not in request.instrument_ids)
    if missing:
        raise CashMergerConfigError(
            f"no native InstrumentId mapping for event symbols: {list(missing)}"
        )
    if not symbols:
        raise CashMergerConfigError("event snapshot contains no definitive fixed-cash targets")

    instruments = [request.instrument_ids[symbol] for symbol in symbols]
    instruments.append(request.benchmark_instrument_id)
    variants = (
        ("complete", 0, False),
        ("6", 6, False),
        ("8", 8, False),
        ("10", 10, False),
        ("12", 12, False),
        ("residual_12", 12, True),
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for label, max_positions, residual_enabled in variants:
        document = _config_document(
            label=label,
            max_positions=max_positions,
            residual_enabled=residual_enabled,
            instruments=instruments,
            request=request,
        )
        path = output_dir / f"cash_merger_{label}.yaml"
        path.write_text(yaml.safe_dump(document, sort_keys=False))
        paths.append(path)
    return tuple(paths)


def _config_document(
    *,
    label: str,
    max_positions: int,
    residual_enabled: bool,
    instruments: list[str],
    request: CashMergerConfigRequest,
) -> dict[str, object]:
    benchmark_symbol = request.benchmark_instrument_id.split(".", 1)[0]
    return {
        "name": f"demeter_cash_merger_{label}",
        "schema_version": 10,
        "output_dir": f"runs/demeter_eu/cash_merger_{label}",
        "data": {
            "base_currency": "EUR",
            "instruments": instruments,
            "exchange": ["EUR/USD.IDEALPRO"],
            "arrays": ["OHLCV"],
            "start": request.start,
            "end": request.end,
            "timeframe": "1D",
            "missing_index": "nan",
            "quality": {"allowed_degradations": ["missing_rows"]},
        },
        "indicators": [
            {
                "id": "demeter.cash_merger_deal",
                "params": {
                    "cache_dir": str(request.event_cache_dir),
                    "fx_cache_dir": str(request.fx_cache_dir),
                    "event_start": request.start,
                    "refresh_live": True,
                    "refresh_fx_live": True,
                    "filing_lag_days": 1,
                    "break_lookback": 20,
                    "completion_probability": 0.9,
                    "default_close_days": 120,
                    "roundtrip_cost_bps": 20.0,
                    "min_expected_value_bps": 0.0,
                    "benchmark_symbol": benchmark_symbol,
                    "residual_lookback": 5,
                    "news_exclusion_days": 2,
                },
            }
        ],
        "strategy": {
            "id": "demeter.cash_merger_break_risk",
            "params": {
                "max_positions": max_positions,
                "max_weight_multiple": 1.5,
                "residual_entry_enabled": residual_enabled,
                "residual_entry_threshold": -0.02,
            },
        },
        "portfolio": {
            "base_currency": "EUR",
            "gross_cap": 1.0,
            "net_cap": 1.0,
            "direction": "longonly",
            "init_cash": request.init_cash,
            "fees": 0.0,
            "slippage": 0.0005,
            "fx_conversion_cost": 0.0003,
            "fixed_fee": 0.35,
            "band_up": 0.02,
            "band_down": 0.02,
        },
        "ranking": {"metric": "convergent_income_utility"},
        "report": {
            "metrics": [
                "convergent_tail_budget",
                "convergent_downside_lskew",
                "total_fees_paid",
            ]
        },
        "optimization": {
            "search": "grid",
            "seed": 42,
            "split": {
                "method": "from_n_expanding",
                "params": {"n": 4, "min_length": 756, "split": -252},
                "max_splits": 10,
            },
        },
    }
