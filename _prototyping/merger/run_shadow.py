"""Run one prospective, research-only cash-merger shadow observation."""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import yaml

from _prototyping.merger.shadow import (
    AegisCatalogMarkSource,
    CashMergerShadow,
    EdgarEventSource,
    FredDtb3RateSource,
)


class ShadowConfigError(ValueError):
    """The prototype YAML cannot define an executable shadow observation."""


def main() -> None:
    args = _arguments()
    as_of = _timestamp(args.as_of)
    config = _load_config(args.config)
    root = args.state_dir.expanduser().resolve()
    shadow = CashMergerShadow(root)
    cash_rate = FredDtb3RateSource(root / "sources" / "fred-dtb3").latest(as_of=as_of.date())
    end = as_of.date() - timedelta(days=1)
    evidence = shadow.run(
        source=EdgarEventSource(config["instrument_ids"]),
        marks=AegisCatalogMarkSource(
            cash_rate.annual_rate,
            catalog_path=config["catalog_path"],
            market_instrument_id=config["market_instrument_id"],
        ),
        start=shadow.next_refresh_start(end=end),
        end=end,
        as_of=as_of,
        capital=config["shadow_capital"],
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
                    "formed_this_run": evidence.decision_formed,
                    "positions": len(evidence.decision.positions),
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
    default_cache = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument(
        "--state-dir",
        type=Path,
        default=default_cache / "aegis" / "cash-merger-shadow",
    )
    parser.add_argument(
        "--as-of",
        help="Timezone-aware ISO timestamp; defaults to the current UTC time.",
    )
    return parser.parse_args()


def _timestamp(value: str | None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ShadowConfigError("--as-of must include a timezone")
    return parsed.astimezone(UTC)


def _load_config(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text())
    if not isinstance(payload, dict):
        raise ShadowConfigError("shadow config must be a YAML mapping")
    unknown = set(payload) - {
        "shadow_capital",
        "instrument_ids",
        "market_instrument_id",
        "catalog_path",
    }
    if unknown:
        raise ShadowConfigError(f"unknown shadow config fields: {sorted(unknown)}")
    capital = float(payload.get("shadow_capital", 0.0))
    if capital <= 0.0:
        raise ShadowConfigError("shadow_capital must be positive")
    raw_ids = payload.get("instrument_ids")
    if not isinstance(raw_ids, list) or not raw_ids or not all(
        isinstance(instrument_id, str) for instrument_id in raw_ids
    ):
        raise ShadowConfigError("instrument_ids must be a non-empty list of InstrumentId strings")
    catalog = payload.get("catalog_path")
    return {
        "shadow_capital": capital,
        "instrument_ids": tuple(dict.fromkeys(raw_ids)),
        "market_instrument_id": str(payload.get("market_instrument_id", "SPY.ARCA")),
        "catalog_path": Path(catalog).expanduser() if catalog is not None else None,
    }


if __name__ == "__main__":
    main()
