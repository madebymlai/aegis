"""Evidence for per-Component ``params:`` a top-level ``lock:`` overrides.

A locked Run reproduces one prior Candidate: every Component takes its parameters from
that Candidate (ADR-0006 lock-wins). When the same config also declares per-Component
``params:``, those values are *overridden* — the lock wins. Rather than dropping them
silently, this module renders the overridden ``params:`` as a fail-loud Evidence record
so the Run's Manifest faithfully reports that the author's values were ignored.

It is a pure query over the typed ``RunConfig`` spine: no store access, no resolution. The
component slot mirrors the optimization source — ``"strategy"`` for the strategy ref and
the indicator id for each indicator ref.
"""

from __future__ import annotations

from typing import Any

from research.aegis_research.component_registry import ComponentFamily
from research.aegis_research.config import (
    RunConfig,
    RunIndicatorSourceConfig,
    RunSourceRefConfig,
    to_builtin,
)

LOCK_PARAM_OVERRIDE_SCHEMA_VERSION = "lock_param_override.v1"


def overridden_component_params(config: RunConfig) -> list[dict[str, Any]]:
    """Return one Evidence record per Component whose ``params:`` the lock overrides.

    Each record names the Component (family, id, slot), the overridden parameter names,
    and the ignored values. Components without ``params:`` contribute nothing.
    """
    records: list[dict[str, Any]] = []
    strategy_record = _override_record("strategies", "strategy", config.strategy)
    if strategy_record is not None:
        records.append(strategy_record)
    for indicator in config.indicators:
        indicator_record = _override_record("indicators", indicator.id, indicator)
        if indicator_record is not None:
            records.append(indicator_record)
    return records


def _override_record(
    family: ComponentFamily,
    slot: str,
    ref: RunSourceRefConfig | RunIndicatorSourceConfig,
) -> dict[str, Any] | None:
    if not ref.params:
        return None
    ignored_values = to_builtin(dict(ref.params))
    return {
        "family": family,
        "component_id": ref.id,
        "slot": slot,
        "param_names": sorted(ignored_values),
        "ignored_values": ignored_values,
    }
