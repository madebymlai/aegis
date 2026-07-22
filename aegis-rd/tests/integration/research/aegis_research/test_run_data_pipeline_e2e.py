from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from aegis_data.catalog import CatalogBackedDataPort
from aegis_data.custom_data import FixtureRecord, ServedCustomData
from aegis_data.testing import FakeCatalog, future
from nautilus_trader.model.identifiers import InstrumentId

from research.aegis_research import run_data as run_data_module
from research.aegis_research import run_pipeline as run_pipeline_module
from research.aegis_research.component_registry import discover_component_registry
from research.aegis_research.configuration import CONFIG_SCHEMA_VERSION, resolve_run_config
from research.aegis_research.optimization.portfolio_simulation._simulation import (
    VBT_STATICIZED_CACHE_ENV,
)
from research.aegis_research.run_pipeline import run_strategy_sweep
from tests.support.research.aegis_research.market_data_fixtures import seed_catalog_ohlcv

_START = "2024-01-01"
_END = "2024-01-13"
_PERIODS = 12


def test_custom_array_reaches_components_replay_and_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    catalog_path = tmp_path / "catalog"
    seed_catalog_ohlcv(catalog_path, ["AAPL.XNAS"], periods=_PERIODS, currency="USD")
    registry = _array_strategy_registry(tmp_path, input_name="FixtureValue")
    resolved = resolve_run_config(
        _run_config(
            tmp_path,
            data={
                "arrays": ["OHLCV", "FixtureValue"],
                "base_currency": "USD",
                "instruments": ["AAPL.XNAS"],
                "start": _START,
                "end": _END,
                "timeframe": "1D",
                "path": str(catalog_path),
            },
        ),
        component_registry=registry,
    )
    monkeypatch.setenv(VBT_STATICIZED_CACHE_ENV, str(tmp_path.parent / "vbt-cache"))

    result = run_strategy_sweep(
        resolved,
        component_registry=registry,
        run_id="custom-array-e2e",
        custom_data_providers={FixtureRecord: (_FixtureProvider(),)},
    )

    manifest = _manifest(tmp_path, "custom-array-e2e")
    assert result["candidates"][0]["complete_period_metrics"]["total_trades"] > 0
    assert "FixtureValue" in manifest["evidence"]["data"]["loaded_arrays"]
    assert manifest["run"]["status"] == "completed"


def test_continuous_future_reaches_components_replay_and_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    es = InstrumentId.from_str("ES.XCME")
    index = pd.date_range(_START, periods=_PERIODS, freq="D")
    continuous_frame = pd.DataFrame(
        {
            "Open": np.linspace(100.0, 111.0, _PERIODS),
            "High": np.linspace(100.0, 111.0, _PERIODS),
            "Low": np.linspace(100.0, 111.0, _PERIODS),
            "Close": np.linspace(100.0, 111.0, _PERIODS),
            "Volume": np.full(_PERIODS, 1_000.0),
        },
        index=index,
    )
    port = CatalogBackedDataPort(
        FakeCatalog(instruments=[future("ESH4.XCME", "2024-03-15")], bars={})
    )

    class FakeContinuousModel:
        continuous_id = es
        quote_currency = "USD"
        frame = continuous_frame

        def __init__(self, _port, root, **_kwargs):
            assert str(root) == "ES"

        def materialize(self, *, end: str) -> None:
            assert end == _END

    monkeypatch.setattr(run_data_module, "ContinuousContractModel", FakeContinuousModel)
    monkeypatch.setattr(
        run_pipeline_module,
        "catalog_data_port",
        lambda _path, resolver=None: port,
    )
    monkeypatch.setenv(VBT_STATICIZED_CACHE_ENV, str(tmp_path.parent / "vbt-cache"))
    registry = _array_strategy_registry(tmp_path, input_name="Close")
    resolved = resolve_run_config(
        _run_config(
            tmp_path,
            data={
                "arrays": ["OHLCV"],
                "base_currency": "USD",
                "instruments": [],
                "futures": ["ES"],
                "start": _START,
                "end": _END,
                "timeframe": "1D",
            },
        ),
        component_registry=registry,
    )

    result = run_strategy_sweep(
        resolved,
        component_registry=registry,
        run_id="continuous-future-e2e",
    )

    manifest = _manifest(tmp_path, "continuous-future-e2e")
    data_evidence = manifest["evidence"]["data"]
    assert result["candidates"][0]["complete_period_metrics"]["total_trades"] > 0
    assert data_evidence["tradeables"] == [{"instrument_id": "ES.XCME", "continuous_root": "ES"}]
    assert data_evidence["adjustment_mode"] == "backward_ratio"


def _run_config(tmp_path: Path, *, data: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": CONFIG_SCHEMA_VERSION,
        "name": "run_data_pipeline_e2e",
        "output_dir": str(tmp_path / "runs"),
        "data": data,
        "portfolio": {
            "direction": "longonly",
            "fees": 0.0,
            "slippage": 0.0,
            "fill_timing": "next_open",
        },
        "strategy": {"id": "tests.array_strategy"},
        "indicators": [],
        "ranking": {"metric": "total_return"},
        "optimization": {"search": "grid", "observation_block_bars": 6},
    }


def _array_strategy_registry(tmp_path: Path, *, input_name: str):
    components = tmp_path / "research" / "components"
    strategy = components / "strategies" / "array_strategy.py"
    strategy.parent.mkdir(parents=True, exist_ok=True)
    strategy.write_text(
        "# %% component overview\n"
        "# Strategy proving one configured Array reaches Candidate replay.\n"
        "\n# %% define component metadata\n"
        "import numpy as np\n"
        "COMPONENT_MANIFEST = {"
        "'family': 'strategies', 'id': 'tests.array_strategy', 'version': '1.0.0', "
        f"'input_names': ['{input_name}'], "
        "'output_name': 'target_weights', 'owns_portfolio': False}\n"
        "\n# %% main compute\n"
        "def run(inputs, *, n_candidates, **param_lists):\n"
        '    """Read the declared Array and return full target weights."""\n'
        f"    array = inputs.data.array('{input_name}')\n"
        "    rows, symbols = array.shape\n"
        "    return np.ones((rows, n_candidates * symbols), dtype=float)\n"
        "\n# %% lookback\n"
        "def lookback(**params):\n"
        '    """The fixture strategy has no warmup."""\n'
        "    return 0\n"
    )
    return discover_component_registry(root=components, repo_root=tmp_path)


def _manifest(tmp_path: Path, run_id: str) -> dict[str, object]:
    return json.loads((tmp_path / "runs" / run_id / "manifest.json").read_text())


class _FixtureProvider:
    def request_records(
        self,
        instrument_id: InstrumentId,
        *,
        start: pd.Timestamp,
        end: pd.Timestamp,
    ) -> ServedCustomData[FixtureRecord]:
        return ServedCustomData(
            records=(
                FixtureRecord(
                    end.value,
                    end.value,
                    instrument_id=instrument_id,
                    value=7.0,
                    provider="fixture",
                ),
            ),
            served_from=start,
        )
