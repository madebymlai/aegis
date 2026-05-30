from __future__ import annotations

from research.aegis_research.canonical_json import canonical_json_bytes
from research.aegis_research.optimization.canonical import mint_canonical_token


def test_mint_canonical_token_uses_stable_json_digest() -> None:
    payload = {
        "schema_version": "component_lock.v1",
        "run_id": "run-a",
        "rank": 1,
        "component_family": "strategies",
        "component_id": "demo.ma_cross",
        "component_slot": "strategy:demo.ma_cross",
        "candidate_key": "cand_7e175c0267fe6bcd22c8551907f72766",
    }

    assert canonical_json_bytes(payload) == (
        b'{"candidate_key":"cand_7e175c0267fe6bcd22c8551907f72766",'
        b'"component_family":"strategies","component_id":"demo.ma_cross",'
        b'"component_slot":"strategy:demo.ma_cross","rank":1,"run_id":"run-a",'
        b'"schema_version":"component_lock.v1"}'
    )
    assert mint_canonical_token("lock", payload) == "lock_0c4dfb0a67e5cd25d7ccb857816875ae"
