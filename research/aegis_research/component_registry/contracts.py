from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

ComponentFamily = Literal["indicators", "strategies"]
COMPONENT_FAMILIES: tuple[ComponentFamily, ...] = ("indicators", "strategies")

# The four allocation-native channels a Strategy may emit; every strategy must
# declare exactly one as its ``output_name`` (see `StrategyManifest`).
STRATEGY_ALLOCATION_OUTPUTS: frozenset[str] = frozenset(
    {"active", "scores", "ranks", "target_weights"}
)

# The MultiIndex level naming the symbol axis of a candidate-wide allocation frame.
# Candidate-frame vocabulary, like STRATEGY_ALLOCATION_OUTPUTS: it lives here so the
# simulation boundary and the Allocation Policy gate import it from one stdlib-only
# owner instead of cycling through each other.
SYMBOL_LEVEL: str = "symbol"


class ComponentRegistryError(ValueError):
    pass


@dataclass(frozen=True)
class ComponentSelection:
    family: ComponentFamily
    id: str


@dataclass(frozen=True)
class ComponentSourceIdentity:
    repo_relative_path: str
    source_hash: str

    def public(self) -> dict[str, str]:
        return {
            "repo_relative_path": self.repo_relative_path,
            "source_hash": self.source_hash,
        }


@dataclass(frozen=True)
class ComponentManifest:
    family: ComponentFamily
    id: str
    version: str
    payload: Mapping[str, Any]

    def fingerprint_payload(self) -> Mapping[str, Any]:
        return self.payload


@dataclass(frozen=True)
class IndicatorManifest(ComponentManifest):
    input_names: tuple[str, ...]
    param_names: tuple[str, ...]
    output_names: tuple[str, ...]
    defaults: Mapping[str, Any]
    wide_callable: str
    param_space_callable: str | None = None
    bar_aligned: bool = True

    @property
    def consumes_outputs(self) -> tuple[str, ...]:
        """Indicators consume no strategy outputs — uniform query surface."""
        return ()


@dataclass(frozen=True)
class StrategyManifest(ComponentManifest):
    """Strategy component manifest.

    `output_name` is the declared allocation-native channel emitted by the
    component. It must be one of the four registered shapes — `active`,
    `scores`, `ranks`, or `target_weights` — consumed by the portfolio policy
    layer (see `STRATEGY_ALLOCATION_OUTPUTS`). Legacy `entries`/`exits`
    signal pairs are rejected.
    """

    input_names: tuple[str, ...]
    param_names: tuple[str, ...]
    output_name: str
    consumes_outputs: tuple[str, ...]
    defaults: Mapping[str, Any]
    wide_callable: str
    param_space_callable: str | None = None
    owns_portfolio: bool = False

    @property
    def output_names(self) -> tuple[str, ...]:
        """Strategies produce no indicator outputs — uniform query surface."""
        return ()


@dataclass(frozen=True)
class ComponentDefinition:
    manifest: IndicatorManifest | StrategyManifest
    callable_name: str
    file_path: Path
    identity: ComponentSourceIdentity

    @property
    def family(self) -> ComponentFamily:
        return self.manifest.family

    @property
    def id(self) -> str:
        return self.manifest.id

    @property
    def input_names(self) -> tuple[str, ...]:
        return self.manifest.input_names

    # ── Query surface ──────────────────────────────────────────────────────

    def undeclared_params(self, provided: frozenset[str]) -> frozenset[str]:
        """Return params in *provided* that are not declared in the manifest."""
        return provided - frozenset(self.manifest.param_names)

    def unsatisfied_params(self, provided: frozenset[str]) -> frozenset[str]:
        """Return declared params neither provided, nor defaulted, nor waived.

        A ``param_space_callable`` waives all declared params regardless of
        what is provided or defaulted.
        """
        if self.manifest.param_space_callable is not None:
            return frozenset()
        return (
            frozenset(self.manifest.param_names)
            - provided
            - frozenset(self.manifest.defaults)
        )

    def produced_output_names(self) -> frozenset[str]:
        """Output names this component produces (uniform across families).

        Indicator manifests return their ``output_names``; strategy manifests
        return empty — callers never type-dispatch.
        """
        return frozenset(self.manifest.output_names)

    def consumed_output_names(self) -> frozenset[str]:
        """Output names this component consumes (uniform across families).

        Strategy manifests return their ``consumes_outputs``; indicator
        manifests return empty — callers never type-dispatch.
        """
        return frozenset(self.manifest.consumes_outputs)

    # ── Callable loading ───────────────────────────────────────────────────

    def load_callable(self) -> Any:
        from research.aegis_research.component_registry.registry import load_component_callable

        return load_component_callable(self)

    def load_attribute(self, attribute_name: str) -> Any:
        from research.aegis_research.component_registry.registry import load_component_attribute

        return load_component_attribute(self, attribute_name)

    def load_attributes(self, attribute_names: Sequence[str]) -> dict[str, Any]:
        from research.aegis_research.component_registry.registry import load_component_attributes

        return load_component_attributes(self, tuple(attribute_names))
