"""Component param-namespace wire-format codec.

Owns the param-namespace wire format end-to-end and nothing else.  The format is
frozen and singular — there is no second live encoding and no instance state, so
the three public functions are free functions, not a class.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from research.aegis_research.component_registry import (
    COMPONENT_FAMILIES,
    ComponentFamily,
)
from research.aegis_research.optimization.portfolio_params import is_portfolio_param_key

FIXED_CANDIDATE_PARAM = "__aegis_fixed_candidate__"
PARAM_KEY_PREFIX = "component"
PARAM_KEY_SEPARATOR = "__"


@dataclass(frozen=True, slots=True)
class ComponentRef:
    """Identifier for one Component slot within a Candidate's param grid.

    A frozen value type — NOT a NamedTuple — because a NamedTuple silently
    compares equal to a raw 3-tuple, defeating the type-safety point.
    """

    family: ComponentFamily
    component_id: str
    slot: str


class ParamNamespaceError(ValueError):
    pass


def encode(ref: ComponentRef, param_name: str) -> str:
    """Produce the namespaced key for a Component's parameter.

    The per-part hex escaping ensures a part's contents can never collide with
    the ``__`` separator.
    """
    namespace_parts = (ref.family, ref.component_id, ref.slot, param_name)
    if not all(namespace_parts):
        raise ParamNamespaceError("component param namespace parts must not be empty")
    return PARAM_KEY_SEPARATOR.join(
        (PARAM_KEY_PREFIX, *(_encode_namespace_part(p) for p in namespace_parts))
    )


def decode(key: str) -> tuple[ComponentRef, str]:
    """Parse a namespaced key back into a ``(ComponentRef, param_name)`` pair.

    Rejects unknown Component families — the namespace only ever admits known
    families (a format-level admissibility check depending on ``component_registry``).
    """
    parts = key.split(PARAM_KEY_SEPARATOR)
    if len(parts) != 5 or parts[0] != PARAM_KEY_PREFIX:
        raise ParamNamespaceError(f"not a component param key: {key!r}")
    _, encoded_family, encoded_component_id, encoded_slot, encoded_param_name = parts
    family = _decode_namespace_part(encoded_family)
    component_id = _decode_namespace_part(encoded_component_id)
    slot = _decode_namespace_part(encoded_slot)
    param_name = _decode_namespace_part(encoded_param_name)
    if family not in COMPONENT_FAMILIES:
        raise ParamNamespaceError(f"unsupported component param family: {family!r}")
    return ComponentRef(family, component_id, slot), param_name


def slice_by_component(
    param_row: Mapping[str, Any],
) -> dict[ComponentRef, dict[str, Any]]:
    """Group a Candidate's flat param row by Component, skipping non-component axes."""
    slices: dict[ComponentRef, dict[str, Any]] = {}
    for key, value in param_row.items():
        if key == FIXED_CANDIDATE_PARAM or is_portfolio_param_key(key):
            continue
        ref, param_name = decode(key)
        slices.setdefault(ref, {})[param_name] = value
    return slices


def _encode_namespace_part(value: str) -> str:
    return value.encode("utf-8").hex()


def _decode_namespace_part(value: str) -> str:
    try:
        return bytes.fromhex(value).decode("utf-8")
    except ValueError as error:
        raise ParamNamespaceError(f"invalid component param namespace part: {value!r}") from error
