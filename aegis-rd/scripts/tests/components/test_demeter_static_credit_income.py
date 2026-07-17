from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from nautilus_trader.model.identifiers import InstrumentId

from research.aegis_research.data import MarketDataBundle
from research.aegis_research.optimization.component_source import ComponentStrategyInputs

_ROOT = Path(__file__).resolve().parents[3]
_STRATEGY = "research/components/strategies/demeter/static_short_credit.py"


def _load_strategy():
    spec = importlib.util.spec_from_file_location(
        "demeter_static_short_credit_test", _ROOT / _STRATEGY
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _inputs(instruments: tuple[str, ...]) -> ComponentStrategyInputs:
    index = pd.date_range("2020-08-10", periods=3, freq="D")
    close = pd.DataFrame(
        {
            InstrumentId.from_str(instrument): np.linspace(100.0, 101.0, len(index))
            for instrument in instruments
        },
        index=index,
    )
    return ComponentStrategyInputs(
        data=MarketDataBundle(arrays={"Close": close}),
        indicators={},
        n_candidates=1,
        n_symbols=len(instruments),
        metadata={},
    )


def test_hedged_short_credit_pair_is_always_fully_invested_fifty_fifty() -> None:
    strategy = _load_strategy()

    result = strategy.run(
        _inputs(("CBUS5E.XBRU", "STEA.LSEETF")),
        n_candidates=1,
    )

    np.testing.assert_allclose(result, [[0.5, 0.5]] * 3)


def test_hedged_duration_comparator_is_always_fully_invested_equal_weight() -> None:
    strategy = _load_strategy()

    result = strategy.run(
        _inputs(("CBUS5E.XBRU", "LQEE.LSEETF", "STEA.LSEETF", "IHYE.LSEETF")),
        n_candidates=1,
    )

    np.testing.assert_allclose(result, [[0.25, 0.25, 0.25, 0.25]] * 3)


def test_static_short_credit_rejects_a_mixed_hedging_pair() -> None:
    strategy = _load_strategy()

    with pytest.raises(
        strategy.UnsupportedStaticCreditPairError,
        match="unsupported instrument pair",
    ):
        strategy.run(
            _inputs(("CBUS5E.XBRU", "SDHY.LSEETF")),
            n_candidates=1,
        )


@pytest.mark.parametrize(
    "instruments",
    [
        ("SDIG.LSEETF", "SDHY.LSEETF"),
        ("CBUS5E.XBRU", "STHE.LSEETF"),
    ],
)
def test_static_short_credit_preserves_the_target_for_control_and_fallback(
    instruments: tuple[str, str],
) -> None:
    strategy = _load_strategy()

    result = strategy.run(_inputs(instruments), n_candidates=1)

    np.testing.assert_allclose(result, [[0.5, 0.5]] * 3)
