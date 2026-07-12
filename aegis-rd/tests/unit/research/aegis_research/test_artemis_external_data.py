import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
import requests

from research.aegis_research.external_data.artemis import (
    ArtemisIntegrityError,
    ArtemisMarketYieldSource,
    load_snapshot,
    parse_market_yield_page,
    snapshot_payload,
)


class _Response:
    def __init__(self, text: str) -> None:
        self.text = text

    def raise_for_status(self) -> None:
        return None


def _page(*, expected_loss="1.0, 1.5") -> str:
    return f"""
    categories: ['01/01/2026', '08/01/2026'], labels: {{}}
    name: 'Collateral Yield', data: [3.0, 3.1]
    name: 'Insurance Risk Spread', data: [5.0, 5.2]
    name: 'Expected Loss', data: [{expected_loss}]
    """


def test_parses_aligned_market_yield_series() -> None:
    frame = parse_market_yield_page(_page())
    assert frame.iloc[-1].to_dict() == {
        "Collateral Yield": 3.1,
        "Insurance Risk Spread": 5.2,
        "Expected Loss": 1.5,
    }


def test_rejects_misaligned_market_yield_series() -> None:
    with pytest.raises(ValueError, match="not aligned"):
        parse_market_yield_page(_page(expected_loss="1.0"))


def test_snapshot_records_source_hash_and_retrieval_time() -> None:
    payload = snapshot_payload(_page(), retrieved_at=datetime(2026, 7, 12, tzinfo=UTC))
    assert len(payload["source_sha256"]) == 64
    assert payload["retrieved_at"] == "2026-07-12T00:00:00+00:00"
    assert len(payload["observations"]) == 2


def test_snapshot_rejects_observations_changed_after_pinning(tmp_path: Path) -> None:
    payload = snapshot_payload(_page())
    payload["observations"][0]["Expected Loss"] = 9.0
    path = tmp_path / f"cat_bond_market_yield-{payload['snapshot_sha256'][:16]}.json"
    path.write_text(json.dumps(payload))

    with pytest.raises(ArtemisIntegrityError, match="does not match"):
        load_snapshot(path)


def test_source_refresh_is_content_idempotent(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: _Response(_page()))
    source = ArtemisMarketYieldSource(tmp_path)

    source.refresh()
    first_path = next(tmp_path.glob("*.json"))
    first_contents = first_path.read_text()
    source.refresh()

    assert list(tmp_path.glob("*.json")) == [first_path]
    assert first_path.read_text() == first_contents
    assert not list(tmp_path.glob("*.tmp"))


def test_source_uses_validated_cache_when_refresh_is_offline(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: _Response(_page()))
    source = ArtemisMarketYieldSource(tmp_path)
    source.refresh()

    def offline(*args, **kwargs):
        raise requests.ConnectionError("offline")

    monkeypatch.setattr(requests, "get", offline)
    with pytest.warns(UserWarning, match="using cache"):
        snapshot = source.refresh_and_load()

    assert snapshot.frame.index[-1] == datetime(2026, 1, 8)


def test_source_cold_start_fails_clearly_when_offline(tmp_path: Path, monkeypatch) -> None:
    def offline(*args, **kwargs):
        raise requests.ConnectionError("offline")

    monkeypatch.setattr(requests, "get", offline)
    with (
        pytest.warns(UserWarning, match="using cache"),
        pytest.raises(ArtemisIntegrityError, match="online refresh is required"),
    ):
        ArtemisMarketYieldSource(tmp_path).refresh_and_load()
