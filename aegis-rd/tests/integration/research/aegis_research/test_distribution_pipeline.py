from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from aegis_data.bar_type import raw_bar_type
from aegis_data.catalog import CatalogBackedDataPort
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.objects import Price, Quantity
from nautilus_trader.persistence.catalog import ParquetDataCatalog

from research.aegis_research.component_registry import discover_component_registry
from research.aegis_research.configuration import (
    CONFIG_SCHEMA_VERSION,
    resolve_run_config,
)
from research.aegis_research.market_data.adapters import catalog as catalog_adapter
from research.aegis_research.optimization.window_evaluation._simulation import (
    VBT_STATICIZED_CACHE_ENV,
)
from research.aegis_research.run_pipeline import run_strategy_sweep
from tests.support.research.aegis_research.market_data_fixtures import (
    equity_definition,
    instrument_id,
)

_START = "2024-01-01"
_END = "2024-01-13"
_PERIODS = 12
_PRICE = 1.0
_DISTRIBUTION_AMOUNT = 0.01
_DISTRIBUTION_OFFSET = 1
_DISTRIBUTING_RD_TOTAL_RETURN = 1.0


def _flat_adjusted_last() -> pd.Series:
    return pd.Series(
        [_PRICE] * _PERIODS,
        index=pd.date_range(_START, periods=_PERIODS, freq="D", tz="UTC"),
    )


def _adjusted_last_with_cash_distribution() -> pd.Series:
    adjusted = _PRICE / (1.0 - (_DISTRIBUTION_AMOUNT / _PRICE))
    return pd.Series(
        [_PRICE] * _DISTRIBUTION_OFFSET
        + [adjusted] * (_PERIODS - _DISTRIBUTION_OFFSET),
        index=pd.date_range(_START, periods=_PERIODS, freq="D", tz="UTC"),
    )


@pytest.mark.parametrize(
    ("case_name", "adjusted_last_factory", "expected_total_return"),
    [
        ("verified-zero", _flat_adjusted_last, 0.0),
        (
            "distributing",
            _adjusted_last_with_cash_distribution,
            _DISTRIBUTING_RD_TOTAL_RETURN,
        ),
    ],
    ids=["verified-zero", "distributing"],
)
def test_rd_pipeline_total_return_reflects_verified_distribution_coverage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    case_name: str,
    adjusted_last_factory: Callable[[], pd.Series],
    expected_total_return: float,
) -> None:
    instrument = instrument_id("DIV.XNAS")
    monkeypatch.setenv(
        VBT_STATICIZED_CACHE_ENV,
        str(tmp_path.parent / "vbt-staticization"),
    )
    workspace = tmp_path / case_name
    adjusted_last = adjusted_last_factory()

    total_return = _pipeline_total_return(
        workspace,
        instrument,
        adjusted_last=adjusted_last,
        monkeypatch=monkeypatch,
    )

    assert total_return == pytest.approx(expected_total_return, abs=1e-9)


def _pipeline_total_return(
    workspace: Path,
    instrument: InstrumentId,
    *,
    adjusted_last: pd.Series,
    monkeypatch: pytest.MonkeyPatch,
) -> float:
    catalog_path = workspace / "catalog"
    _seed_flat_catalog(catalog_path, instrument)
    catalog = ParquetDataCatalog(catalog_path)
    port = CatalogBackedDataPort(
        catalog,
        distribution_provider=_AdjustedLastProvider(adjusted_last),
    )
    monkeypatch.setattr(
        catalog_adapter,
        "catalog_data_port",
        lambda _path, resolver=None: port,
    )
    components = workspace / "research" / "components"
    _write_always_long_strategy(components / "strategies" / "always_long.py")
    registry = discover_component_registry(root=components, repo_root=workspace)
    resolved = resolve_run_config(
        _run_config(catalog_path, workspace, instrument),
        component_registry=registry,
    )
    result = run_strategy_sweep(
        resolved,
        component_registry=registry,
        run_id=workspace.name,
    )
    return float(result["candidates"][0]["metrics"]["total_return"])


def _run_config(
    catalog_path: Path,
    workspace: Path,
    instrument: InstrumentId,
) -> dict[str, object]:
    return {
        "schema_version": CONFIG_SCHEMA_VERSION,
        "name": "distribution_pipeline_regression",
        "output_dir": str(workspace / "runs"),
        "data": {
            "arrays": ["OHLCV"],
            "base_currency": "USD",
            "instruments": [instrument.value],
            "start": _START,
            "end": _END,
            "timeframe": "1D",
            "path": str(catalog_path),
        },
        "portfolio": {
            "fees": 0.0,
            "slippage": 0.0,
            "gross_cap": 1.0,
            "direction": "longonly",
            "short_borrow_rate": 0.0,
            "short_rebate_rate": 0.0,
            "fill_timing": "same_close",
        },
        "strategy": {"id": "demo.always_long"},
        "indicators": [],
        "ranking": {"metric": "total_return"},
        "report": {"min_oos_trades": 0},
        "optimization": {
            "search": "grid",
            "split": {
                "method": "from_n_expanding",
                "params": {"n": 3, "min_length": 6, "split": 0.5},
                "max_splits": 3,
            },
        },
    }


def _write_always_long_strategy(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# %% component overview\n"
        "# Strategy fixture used by the distribution pipeline regression.\n"
        "\n"
        "# %% define component metadata\n"
        "import numpy as np\n"
        "import pandas as pd\n"
        "COMPONENT_MANIFEST = {"
        "'family': 'strategies', 'id': 'demo.always_long', 'version': '1.0.0', "
        "'input_names': ['Close'], "
        "'output_name': 'target_weights', 'owns_portfolio': False}\n"
        "\n# %% main compute\n"
        "def run(bundle):\n"
        "    \"\"\"Return a fully invested long-only allocation frame.\"\"\"\n"
        "    close = bundle.data.array('Close')\n"
        "    return pd.DataFrame(1.0, index=close.index, columns=close.columns)\n"
        "\n# %% wide compute\n"
        "def run(inputs, *, n_candidates, **param_lists):\n"
        "    \"\"\"Return a wide fully invested long-only allocation matrix.\"\"\"\n"
        "    close = inputs.data.array('Close')\n"
        "    rows, symbols = close.shape\n"
        "    return np.ones((rows, n_candidates * symbols), dtype=float)\n"
    )


def _seed_flat_catalog(catalog_path: Path, instrument: InstrumentId) -> None:
    catalog_path.mkdir(parents=True, exist_ok=True)
    catalog = ParquetDataCatalog(catalog_path)
    catalog.write_data([equity_definition(instrument, "USD")])
    index = pd.date_range(_START, periods=_PERIODS, freq="D")
    bar_type = raw_bar_type(instrument, "1D")
    catalog.write_data(
        [_bar(bar_type, timestamp=timestamp) for timestamp in index],
        start=pd.Timestamp(_START, tz="UTC").value,
        end=pd.Timestamp(_END, tz="UTC").value,
    )


def _bar(bar_type: BarType, *, timestamp: pd.Timestamp) -> Bar:
    ts_event = pd.Timestamp(timestamp, tz="UTC").value
    price = Price.from_str(f"{_PRICE:.2f}")
    return Bar(
        bar_type,
        price,
        price,
        price,
        price,
        Quantity.from_int(1_000),
        ts_event,
        ts_event,
    )


class _AdjustedLastProvider:
    def __init__(self, adjusted_last: pd.Series) -> None:
        self.adjusted_last = adjusted_last

    def request_adjusted_last(self, **_: Any) -> pd.Series:
        return self.adjusted_last.copy()
