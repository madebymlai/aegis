from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import (
    AfterValidator,
    BeforeValidator,
    ConfigDict,
    Field,
    model_validator,
)
from pydantic.dataclasses import dataclass as pydantic_dataclass

from research.aegis_research.authoring_fields import (
    ComponentIdStr,
    NonEmptyStr,
    has_data_array_token_shape,
)
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


# ── Authored manifest vocabulary ───────────────────────────────────────────
#
# A manifest is authored as a dict literal and validated straight into the
# frozen types below (ADR-0012: the model validates *and* constructs). Authors
# write lists; the domain type holds tuples, so an authored list is converted
# up front and every other sequence shape — notably an unordered set, whose
# iteration order would leak into the registry fingerprint — is left for strict
# tuple validation to reject.


def _validate_array_token(token: str) -> str:
    """Pydantic item-validator: Array names must be VBT feature names."""
    if not has_data_array_token_shape(token):
        raise ValueError(
            "must be a VBT feature name without surrounding whitespace or control characters"
        )
    return token


def _tuple_from_authored_list(value: Any) -> Any:
    """Accept the authored list form; hand anything else to strict validation."""
    return tuple(value) if type(value) is list else value


ArrayName = Annotated[NonEmptyStr, AfterValidator(_validate_array_token)]
AuthoredArrayNames = Annotated[
    tuple[ArrayName, ...],
    BeforeValidator(_tuple_from_authored_list),
    Field(strict=True),
]
AuthoredParamNames = Annotated[
    tuple[NonEmptyStr, ...],
    BeforeValidator(_tuple_from_authored_list),
    Field(strict=True),
]

MANIFEST_CONFIG = ConfigDict(extra="forbid")


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


@pydantic_dataclass(frozen=True, config=MANIFEST_CONFIG)
class ComponentManifest:
    family: ComponentFamily
    id: ComponentIdStr
    version: NonEmptyStr
    param_names: AuthoredParamNames = ()
    defaults: Mapping[str, Any] = field(default_factory=dict)

    @model_validator(mode="after")
    def _reject_dot_ids(self) -> ComponentManifest:
        if self.id in {".", ".."}:
            raise ValueError("component id must not be '.' or '..'")
        return self

    @model_validator(mode="after")
    def _check_defaults_in_params(self) -> ComponentManifest:
        unknown = sorted(set(self.defaults) - set(self.param_names))
        if unknown:
            raise ValueError(f"defaults keys must be declared in param_names; unknown: {unknown}")
        return self


@pydantic_dataclass(frozen=True, config=MANIFEST_CONFIG)
class IndicatorManifest(ComponentManifest):
    family: Literal["indicators"]
    # Keyword-only so a required field can sit among the base's defaulted ones.
    input_names: AuthoredArrayNames = field(kw_only=True)
    output_names: AuthoredArrayNames = field(kw_only=True)
    bar_aligned: Literal[True] = True

    @property
    def consumes_outputs(self) -> tuple[str, ...]:
        """Indicators consume no strategy outputs — uniform query surface."""
        return ()

    @model_validator(mode="after")
    def _check_output_names(self) -> IndicatorManifest:
        if not self.output_names:
            raise ValueError("output_names must not be empty")
        duplicates = sorted(
            {name for name in self.output_names if self.output_names.count(name) > 1}
        )
        if duplicates:
            raise ValueError(f"output_names must be unique; duplicates: {duplicates}")
        return self

    def public_fields(self) -> dict[str, Any]:
        """Family-specific facts contributed to ``ComponentDefinition.public_snapshot()``."""
        return {
            "outputs": list(self.output_names),
            "bar_aligned": self.bar_aligned,
        }


@pydantic_dataclass(frozen=True, config=MANIFEST_CONFIG)
class StrategyManifest(ComponentManifest):
    """Strategy component manifest.

    `output_name` is the declared allocation-native channel emitted by the
    component. It must be one of the four registered shapes — `active`,
    `scores`, `ranks`, or `target_weights` — consumed by the portfolio policy
    layer (see `STRATEGY_ALLOCATION_OUTPUTS`). Legacy `entries`/`exits`
    signal pairs are rejected.
    """

    family: Literal["strategies"]
    # Keyword-only so a required field can sit among the base's defaulted ones.
    input_names: AuthoredArrayNames = field(kw_only=True)
    output_name: NonEmptyStr = field(kw_only=True)
    consumes_outputs: AuthoredParamNames = ()
    owns_portfolio: Literal[False] = False

    @property
    def output_names(self) -> tuple[str, ...]:
        """Strategies produce no indicator outputs — uniform query surface."""
        return ()

    @model_validator(mode="after")
    def _check_output_name_allowed(self) -> StrategyManifest:
        if self.output_name not in STRATEGY_ALLOCATION_OUTPUTS:
            raise ValueError(
                f"unsupported allocation output {self.output_name!r}; "
                f"registered shapes are {sorted(STRATEGY_ALLOCATION_OUTPUTS)}"
            )
        return self

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
