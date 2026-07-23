from __future__ import annotations

import pytest

from research.aegis_research.run.identity import RunId


def test_run_id_owns_validation_and_text_projection() -> None:
    run_id = RunId("run_2026-07.23")

    assert str(run_id) == "run_2026-07.23"


@pytest.mark.parametrize("value", ["", ".", "..", "contains/slash", "contains space"])
def test_run_id_rejects_values_outside_the_identity_contract(value: str) -> None:
    with pytest.raises(ValueError, match="run_id must contain"):
        RunId(value)
