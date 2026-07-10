"""Declared mark modes end to end (aegis-rd-tggo.2).

A researcher declares a leg's mark mode as one token where they name it
(``UEQC.XETR:QUOTE``); the pipeline loads the right series through the
production wiring — the declared resolver composed into the catalog port —
with no probe, no side table, and no stored MID bar.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from nautilus_trader.model.identifiers import InstrumentId

from research.aegis_research.data import load_market_data_result
from research.aegis_research.market_data.panels import market_data_bundle
from tests.support.research.aegis_research.factories import make_data_config
from tests.support.research.aegis_research.market_data_fixtures import (
    seed_catalog_frames,
    seed_catalog_quote,
)

_START = "2024-01-01"
_END = "2024-01-04"
_DAYS = pd.date_range(_START, periods=3, freq="D")


def _frame(closes: list[float]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Open": closes,
            "High": closes,
            "Low": closes,
            "Close": closes,
            "Volume": [1_000.0] * len(closes),
        },
        index=_DAYS,
    )


def test_a_declared_quote_leg_loads_the_mid_derived_from_its_bid_and_ask(
    tmp_path: Path,
) -> None:
    catalog_path = tmp_path / "catalog"
    seed_catalog_frames(
        catalog_path,
        {"SYN.XNAS": _frame([10.0, 11.0, 12.0])},
        start=_START,
        end=_END,
        currency="EUR",
    )
    seed_catalog_quote(
        catalog_path,
        "UEQC.XETR",
        bid_frame=_frame([100.00, 101.00, 102.00]),
        ask_frame=_frame([101.00, 102.00, 103.00]),
        start=_START,
        end=_END,
    )
    config = make_data_config(
        arrays=["Close"],
        base_currency="EUR",
        instruments=["UEQC.XETR:QUOTE", "SYN.XNAS"],
        start=_START,
        end=_END,
        path=str(catalog_path),
    )

    result = load_market_data_result(config)

    bundle = market_data_bundle(result)
    ueqc = InstrumentId.from_str("UEQC.XETR")
    syn = InstrumentId.from_str("SYN.XNAS")
    assert list(bundle.array("Close").columns) == [ueqc, syn]
    assert bundle.array("Close")[ueqc].tolist() == [100.50, 101.50, 102.50]
    assert bundle.array("Close")[syn].tolist() == [10.0, 11.0, 12.0]
