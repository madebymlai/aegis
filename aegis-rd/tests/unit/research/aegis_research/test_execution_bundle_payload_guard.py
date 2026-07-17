"""Execution payloads ship VERBATIM and must import without research-only deps.

``param_space`` is the research-only sweep surface; the convention is a LAZY
``from vectorbtpro import vbt`` inside it, so the payload module imports clean in
deployables that exclude vectorbtpro (aegis-trader). A module-level import would
fail there at import time - "Sleeve compute FAILED ... Sleeve holds this period"
on every bar, silently. The export guard turns that regression into a loud error
at export instead.
"""

from __future__ import annotations

import pytest

from research.aegis_research.execution_bundle import _assert_payload_imports_clean

_CLEAN = '''# %% imports
import numpy as np


# %% parameter space
def param_space():
    from vectorbtpro import vbt  # research-only; lazy so execution payloads import clean

    return {"lookback": vbt.Param([21, 63])}


# %% main compute
def run(inputs, *, n_candidates, **param_lists):
    return np.zeros(1)
'''


def test_clean_payload_passes_through_verbatim() -> None:
    assert _assert_payload_imports_clean("indicator_0.py", _CLEAN) is _CLEAN


@pytest.mark.parametrize(
    "bad_import",
    [
        "from vectorbtpro import vbt",
        "import vectorbtpro as vbt",
        "import vectorbtpro",
    ],
)
def test_module_level_vectorbtpro_import_fails_loud(bad_import: str) -> None:
    source = f"{bad_import}\n{_CLEAN}"
    with pytest.raises(ValueError, match="research-only dependency at module level"):
        _assert_payload_imports_clean("strategy.py", source)
