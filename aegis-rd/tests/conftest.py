import pytest
from aegis_data import custom_kinds

from tests.support.custom_data import FIXTURE_CUSTOM_DATA_KINDS


@pytest.fixture(autouse=True)
def declared_fixture_custom_data_kinds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        custom_kinds,
        "DECLARED_CUSTOM_DATA_KINDS",
        FIXTURE_CUSTOM_DATA_KINDS,
    )
