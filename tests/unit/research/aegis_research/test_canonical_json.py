from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from research.aegis_research import config as public_config
from research.aegis_research.canonical_json import canonical_json_bytes, to_builtin


@dataclass(frozen=True)
class _NestedPayload:
    enabled: bool
    threshold: np.float64


@dataclass(frozen=True)
class _CanonicalPayload:
    name: str
    nested: _NestedPayload
    values: tuple[object, ...]


def test_to_builtin_is_shared_canonical_dataclass_converter() -> None:
    payload = _CanonicalPayload(
        name="demo",
        nested=_NestedPayload(enabled=True, threshold=np.float64(0.25)),
        values=("alpha", np.int64(3)),
    )

    assert public_config.to_builtin is to_builtin
    assert to_builtin(payload) == {
        "name": "demo",
        "nested": {"enabled": True, "threshold": 0.25},
        "values": ["alpha", 3],
    }
    assert canonical_json_bytes(payload) == (
        b'{"name":"demo","nested":{"enabled":true,"threshold":0.25},'
        b'"values":["alpha",3]}'
    )
