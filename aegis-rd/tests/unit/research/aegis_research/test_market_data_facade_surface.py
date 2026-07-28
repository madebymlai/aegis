from __future__ import annotations

import importlib.util


def test_legacy_market_data_modules_are_absent() -> None:
    assert importlib.util.find_spec("research.aegis_research.data") is None
    assert importlib.util.find_spec("research.aegis_research.market_data") is None
    assert importlib.util.find_spec("research.aegis_research.drift_bands") is None
