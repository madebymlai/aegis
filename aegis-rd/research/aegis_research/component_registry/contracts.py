from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from research.aegis_research.canonical_json import to_builtin

ComponentFamily = Literal["indicators", "strategies"]
COMPONENT_FAMILIES: tuple[ComponentFamily, ...] = ("indicators", "strategies")
COMPONENT_ENTRYPOINT = "run"
COMPONENT_PARAM_SPACE_ENTRYPOINT = "param_space"
COMPONENT_LOOKBACK_ENTRYPOINT = "lookback"

# The four allocation-native channels a Strategy may emit; every strategy must
# declare exactly one as its ``output_name`` (see `StrategyManifest`).
STRATEGY_ALLOCATION_OUTPUTS: frozenset[str] = frozenset(
    {"active", "scores", "ranks", "target_weights"}
)

# The MultiIndex level naming the symbol axis of a candidate-batched allocation frame.
# Candidate-frame vocabulary, like STRATEGY_ALLOCATION_OUTPUTS: it lives here so the
# simulation boundary and Exposure Validation import it from one stdlib-only
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


@dataclass(frozen=True)
class IndicatorManifest(ComponentManifest):
    input_names: tuple[str, ...]
    param_names: tuple[str, ...]
    output_names: tuple[str, ...]
    defaults: Mapping[str, Any]
    bar_aligned: bool = True

    @property
    def consumes_outputs(self) -> tuple[str, ...]:
        """Indicators consume no strategy outputs — uniform query surface."""
        return ()

    def public_fields(self) -> dict[str, Any]:
        """Family-specific facts contributed to ``ComponentDefinition.public_snapshot()``."""
        return {
            "outputs": list(self.output_names),
            "bar_aligned": self.bar_aligned,
        }


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
    owns_portfolio: bool = False

    @property
    def output_names(self) -> tuple[str, ...]:
        """Strategies produce no indicator outputs — uniform query surface."""
        return ()

    def public_fields(self) -> dict[str, Any]:
        """Family-specific facts contributed to ``ComponentDefinition.public_snapshot()``."""
        return {
            "output_name": self.output_name,
            "consumes_outputs": list(self.consumes_outputs),
            "owns_portfolio": self.owns_portfolio,
        }


@dataclass(frozen=True)
class ComponentDefinition:
    _manifest: IndicatorManifest | StrategyManifest
    _file_path: Path
    identity: ComponentSourceIdentity
    _has_param_space: bool = False
    has_lookback: bool = False

    @property
    def family(self) -> ComponentFamily:
        return self._manifest.family

    @property
    def id(self) -> str:
        return self._manifest.id

    @property
    def version(self) -> str:
        return self._manifest.version

    @property
    def input_names(self) -> tuple[str, ...]:
        return self._manifest.input_names

    # ── Query surface ──────────────────────────────────────────────────────

    def declared_param_names(self) -> tuple[str, ...]:
        return self._manifest.param_names

    def default_params(self) -> dict[str, Any]:
        return dict(self._manifest.defaults)

    def allocation_output_name(self) -> str:
        if not isinstance(self._manifest, StrategyManifest):
            raise ComponentRegistryError(
                f"component {self.family}/{self.id} does not declare a strategy allocation output"
            )
        return self._manifest.output_name

    def undeclared_params(self, provided: frozenset[str]) -> frozenset[str]:
        """Return params in *provided* that are not declared in the manifest."""
        return provided - frozenset(self._manifest.param_names)

    def unsatisfied_params(self, provided: frozenset[str]) -> frozenset[str]:
        """Return declared params neither provided, nor defaulted, nor waived.

        A module-level ``param_space`` waives all declared params regardless of
        what is provided or defaulted.
        """
        if self._has_param_space:
            return frozenset()
        return frozenset(self._manifest.param_names) - provided - frozenset(self._manifest.defaults)

    def produced_output_names(self) -> tuple[str, ...]:
        """Output names this component produces (uniform across families).

        Indicator manifests return their ``output_names``; strategy manifests
        return empty — callers never type-dispatch.
        """
        return self._manifest.output_names

    def consumed_output_names(self) -> tuple[str, ...]:
        """Output names this component consumes (uniform across families).

        Strategy manifests return their ``consumes_outputs``; indicator
        manifests return empty — callers never type-dispatch.
        """
        return self._manifest.consumes_outputs

    # ── Callable loading ───────────────────────────────────────────────────

    def load_callable(self) -> Any:
        from research.aegis_research.component_registry.registry import _load_component_callable

        return _load_component_callable(self)

    def source_text(self) -> str:
        return self._file_path.read_text(encoding="utf-8")

    def load_param_space(self) -> Any | None:
        if not self._has_param_space:
            return None
        from research.aegis_research.component_registry.registry import _load_component_attribute

        return _load_component_attribute(self, COMPONENT_PARAM_SPACE_ENTRYPOINT)

    def warmup_bars(self, params: Mapping[str, Any]) -> int:
        if not self.has_lookback:
            raise ComponentRegistryError(
                f"component {self.family}/{self.id} has no lookback entrypoint"
            )
        from research.aegis_research.component_registry.registry import _load_component_attribute

        lookback = _load_component_attribute(self, COMPONENT_LOOKBACK_ENTRYPOINT)
        result = lookback(**params)
        if not isinstance(result, int) or result < 0:
            raise ComponentRegistryError(
                f"component {self.family}/{self.id} lookback() must return a non-negative int, "
                f"got {result!r}"
            )
        return result

    def public_snapshot(self) -> dict[str, Any]:
        """The one projection of a component's public facts.

        Emitted into the registry snapshot and hashed for the registry fingerprint.
        """
        manifest = self._manifest
        payload: dict[str, Any] = {
            "family": self.family,
            "id": self.id,
            "version": manifest.version,
            "callable": COMPONENT_ENTRYPOINT,
            "source_hash": self.identity.source_hash,
            "source": self.identity.public(),
            "inputs": list(manifest.input_names),
            "params": {
                "names": list(manifest.param_names),
                "defaults": dict(manifest.defaults),
                "param_space": {
                    "available": self._has_param_space,
                    "entrypoint": COMPONENT_PARAM_SPACE_ENTRYPOINT
                    if self._has_param_space
                    else None,
                },
            },
            "lookback": {
                "available": self.has_lookback,
                "entrypoint": COMPONENT_LOOKBACK_ENTRYPOINT if self.has_lookback else None,
            },
        }
        payload.update(manifest.public_fields())
        return to_builtin(payload)
