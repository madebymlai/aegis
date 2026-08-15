# NautilusConfig Execution Bundle migration

Date: 2026-08-16
Baseline: NautilusTrader 1.231.0, msgspec 0.21.1
Scope: the Execution Bundle's research-to-runtime JSON boundary

## Verdict

Migrate the Execution Bundle to a new `execution_bundle.v6` contract built from
`NautilusConfig` types. Under Forward-First, this is a real simplification: the
producer and consumer can change together, current wheels can be regenerated,
and no v5 reader or compatibility shim is required.

The worthwhile migration is **not** an envelope-only substitution. Wrapping the
current stdlib dataclasses in one `NautilusConfig` still serializes the derived
`_exposure_limits` field and silently accepts unknown fields inside nested
dataclasses. The clean design converts every value type that crosses this wire
to a `NautilusConfig` struct:

- `DataContract`
- `BundleManifest`
- `ComponentSpec`
- `LockedExecutionPlan`
- `DriftBand`
- `ExecutionBundle`, as the root configuration and behavioral object

Their public names and domain behavior stay intact. `ExecutionBundle` is both
the frozen root `NautilusConfig` and the deep domain interface that loads locked
Components and computes weights. This removes a private payload envelope and a
post-decode wrapper copy without pushing Aegis computation into a free function.

This design removes the Pydantic dependency from `aegis-runtime`, deletes the
custom Nautilus-type serializers, deletes the reflected raw-presence ledger,
deletes the null-removal patch, and delegates nested decoding, mapping-key
conversion, unknown-field rejection, JSON paths, and default omission to the
same configuration machinery Nautilus 1.231 uses.

## Primary-source validation

Context7 resolved the official `/nautechsystems/nautilus_trader` corpus and was
used to locate the configuration API. Its available corpus tracks `develop`, so
all material behavior was checked again against both the official v1.231.0 tag
and the installed 1.231.0 wheel.

`NautilusConfig` is a frozen, unknown-field-forbidden `msgspec.Struct` and owns
the public `parse`, `json`, and `json_primitives` operations
([official v1.231.0 source](https://github.com/nautechsystems/nautilus_trader/blob/v1.231.0/nautilus_trader/common/config.py#L241-L339)).
Its native hooks encode every Nautilus `Identifier` by value and decode an
`InstrumentId` with `InstrumentId.from_str`; they also support the other native
configuration scalar types
([official v1.231.0 hooks](https://github.com/nautechsystems/nautilus_trader/blob/v1.231.0/nautilus_trader/common/config.py#L148-L230)).
The schema hook declares identifiers as strings
([official v1.231.0 schema hook](https://github.com/nautechsystems/nautilus_trader/blob/v1.231.0/nautilus_trader/common/config.py#L92-L114)).

The installed environment reported:

```text
nautilus_trader 1.231.0
msgspec          0.21.1
NautilusConfig.__mro__ = (NautilusConfig, msgspec.Struct, ...)
```

Executable throwaway probes against that environment established all behavior
needed by v6:

| Probe | 1.231 result |
| --- | --- |
| `tuple[InstrumentId, ...]` | JSON string array; parses back to native IDs |
| `Mapping[InstrumentId, str]` | native IDs encode as JSON object keys and parse back as native keys |
| `Mapping[InstrumentId, DriftBand]` | nested values round-trip |
| `ContinuousFutureAdjustmentType` | `"backward_ratio"` round-trips to the native enum |
| standard string enum | value round-trips to the enum |
| unknown nested Struct field | rejected with its JSON path |
| missing required field | rejected with its JSON path |
| bad `InstrumentId` | rejected at `$.contract.instrument_ids[0]` |
| exception raised by `__post_init__` | wrapped as `msgspec.ValidationError` with the domain exception in `__cause__` |
| `omit_defaults=True` | omits `None`, empty, and scalar defaults; explicit `null` still decodes when the type permits it |
| `.json_schema()` | emits nested object schemas, native IDs as strings, required fields, defaults, and `additionalProperties: false` |

The probe also confirmed the envelope-only failure described by the prior
audit. A `NautilusConfig` containing the current dataclasses emitted:

```json
{
  "contract": {"adjustment_mode": null},
  "plan": {
    "_exposure_limits": {
      "gross_cap": 1.0,
      "net_cap": 1.0,
      "direction": "longonly"
    }
  }
}
```

Adding an unknown field under the nested dataclass `contract` was also silently
accepted. In contrast, when the nested types themselves inherit
`NautilusConfig`, the same field is rejected at `$.contract`. This is why the
recommended migration is an atomic type migration, not another adapter layer.

## Proposed v6 model

The production classes keep their present names. The structural shape is:

```python
class DriftBand(NautilusConfig, omit_defaults=True):
    up: float
    down: float
    destination_fraction: float = 1.0


class DataContract(NautilusConfig, omit_defaults=True):
    instrument_ids: tuple[InstrumentId, ...]
    required_arrays: tuple[str, ...]
    base_currency: str
    timeframe: str
    missing_index: MissingIndexPolicy
    lookback_bars: int = 0
    futures: tuple[str, ...] = ()
    exchange: tuple[InstrumentId, ...] = ()
    adjustment_mode: ContinuousFutureAdjustmentType | None = None
    mark_modes: Mapping[InstrumentId, str] = msgspec.field(default_factory=dict)


class BundleManifest(NautilusConfig):
    run_id: str
    role: str
    candidate_key: str
    component_source_hashes: Mapping[str, str]
    instrument_ids: tuple[InstrumentId, ...]


class ComponentSpec(NautilusConfig):
    family: str
    component_id: str
    module: str
    input_names: tuple[str, ...]
    output_names: tuple[str, ...]
    params: Mapping[str, Any]


class LockedExecutionPlan(NautilusConfig):
    strategy: ComponentSpec
    indicators: tuple[ComponentSpec, ...]
    instrument_bands: Mapping[InstrumentId, DriftBand]
    direction: str

    @property
    def exposure_limits(self) -> ExposureLimits:
        return ExposureLimits(SLEEVE_GROSS_LIMIT, None, self.direction)


class ExecutionBundle(NautilusConfig):
    schema_version: Literal["execution_bundle.v6"]
    contract: DataContract
    manifest: BundleManifest
    plan: LockedExecutionPlan

    def compute_weights(...) -> NDArray[np.float64]:
        ...  # Existing pure Aegis Component and portfolio semantics.
```

There is no private `_BundlePayload`. Research constructs this one root object,
the wheel serializes it, the installed loader parses it, and runtime calls its
existing pure `compute_weights` interface directly.

`LockedExecutionPlan.__post_init__` should still construct `exposure_limits`
once for eager direction validation. It should not store the derived value. The
property recomputes one three-field value when the plan is used, preventing a
derived implementation detail from ever becoming a Struct field.

`DataContract` should require an actual `MissingIndexPolicy`. Every production
constructor already supplies that named type, and native parsing constructs it
from the wire value. Under No Primitive Obsession and Forward-First there is no
reason to retain the direct-constructor string coercion in
`_coerce_missing_index_policy`.

`DriftBand` can preserve its current float normalization with
`msgspec.structs.force_setattr` inside `__post_init__`, the supported mutation
mechanism for frozen Struct initialization. Its current positional construction
also remains viable: installed 1.231 behavior permits positional fields on a
subclass unless that subclass itself declares `kw_only=True`.

The prototype emitted this ETF-only v6 payload:

```json
{
  "schema_version": "execution_bundle.v6",
  "contract": {
    "instrument_ids": ["AAPL.NASDAQ"],
    "required_arrays": ["Close"],
    "base_currency": "USD",
    "timeframe": "1D",
    "missing_index": "drop",
    "mark_modes": {"AAPL.NASDAQ": "LAST"}
  },
  "manifest": {
    "run_id": "run-1",
    "role": "best",
    "candidate_key": "0123456789abcdef",
    "component_source_hashes": {"strategies/x": "abc"},
    "instrument_ids": ["AAPL.NASDAQ"]
  },
  "plan": {
    "strategy": {
      "family": "strategies",
      "component_id": "x",
      "module": "bundle.strategy",
      "input_names": ["Close"],
      "output_names": ["target_weights"],
      "params": {"window": 3}
    },
    "indicators": [],
    "instrument_bands": {
      "AAPL.NASDAQ": {"up": 0.1, "down": 0.2}
    },
    "direction": "longonly"
  }
}
```

In v6, an omitted default has one meaning: the default declared by the v6
Struct. There is no separate “absent historical fact” state. This makes the
following equivalent to their explicit defaults:

- missing `lookback_bars` -> `0`
- missing `futures` or `exchange` -> empty tuple
- missing `adjustment_mode` -> `None`
- missing `mark_modes` -> empty mapping
- missing `destination_fraction` -> `1.0`

The domain invariant still rejects futures with no adjustment mode. No v5
payload receives these defaults because the top-level schema version rejects it
before it is trusted.

## Proposed loader boundary

Use native JSON bytes end to end:

```python
def build_execution_bundle(...) -> ExecutionBundle:
    return ExecutionBundle(
        schema_version=BUNDLE_PAYLOAD_SCHEMA_VERSION,
        contract=contract,
        manifest=manifest,
        plan=plan,
    )


def load_bundle_payload(raw: bytes | str) -> ExecutionBundle:
    _require_v6_schema(raw)
    try:
        return ExecutionBundle.parse(raw)
    except msgspec.ValidationError as error:
        if isinstance(error.__cause__, DataContractError):
            raise error.__cause__
        raise BundlePayloadFieldError(str(error)) from error
```

The wheel writer calls `bundle.json()` and writes those bytes directly; the
installed loader reads bytes and returns `ExecutionBundle.parse(...)`
directly. `_require_v6_schema` remains a small Aegis rule because schema
negotiation and the distinct `BundlePayloadSchemaError` are properties of the
research/live artifact, not Nautilus configuration. It may decode only the
outer JSON object to inspect `schema_version`; it must not contain a v5 branch.

`msgspec.ValidationError` already supplies a dotted/indexed JSON path. Aegis no
longer needs to walk and reformat an error collection. A domain error raised by
`__post_init__` is available as `error.__cause__`, so the existing distinction
between malformed wire data and `DataContractError` survives with a direct
cause check.

## Code that can be deleted

From `aegis_runtime.execution.bundle`:

- `Annotated`, all Pydantic imports, and `BUNDLE_TYPE_CONFIG`
- `WireInstrumentId`
- `_wire_adjustment_mode` and `WireAdjustmentMode`
- `WireMissingIndex`
- all four `@with_config(...)` decorators
- `_coerce_missing_index_policy` and direct-constructor primitive coercion
- `LockedExecutionPlan._exposure_limits` and its Pydantic `Field(exclude=True)`

From `aegis_runtime.execution.bundle_loader`:

- the private serialized payload/envelope type
- post-decode construction and copying into a second `ExecutionBundle`
- any dump adapter whose only behavior is forwarding to `bundle.json()`
- the Pydantic dataclass decorator and `TypeAdapter`
- `_PAYLOAD_ADAPTER`
- `_PAYLOAD_SECTION_FIELDS`
- `_OPTIONAL_WIRE_KEYS`
- `_require_wire_keys`
- dump-time `adjustment_mode` null removal
- `_format_payload_errors`
- the Pydantic-specific `_reraise_domain_error` loop
- `dataclasses` and all Pydantic imports

From packaging:

- `pydantic>=2.12` in `aegis-runtime/pyproject.toml`; these two files are the
  only production Pydantic imports in that package
- add an explicit msgspec dependency because runtime code will import
  `msgspec.ValidationError`, `field`, or `force_setattr` directly even though
  Nautilus already installs msgspec transitively

Tests should be consolidated, not merely translated line by line:

- delete the individual pre-v6 compatibility tests for absent
  `destination_fraction` and absent `mark_modes`; one v6 defaults round-trip
  test replaces both
- delete v5 raw-presence rejection tests for absent `exchange` and `futures`;
  absence is their declared v6 default
- keep the missing `missing_index` test because it remains required and native
  parsing rejects it
- replace the v3/v4 compatibility parameterization with one assertion that v5
  is rejected as an unsupported schema
- keep domain-invariant tests: futures/mode consistency, supported adjustment
  modes, mark vocabulary/ownership, instrument IDs, band validation, and the
  cross-section instrument-band match
- keep one malformed-wire test proving native JSON paths and one unknown-field
  test proving `additionalProperties: false` behavior at every Struct layer

## Rules that remain Aegis-owned

Nautilus should own representation mechanics, not the meaning of an Aegis
Execution Bundle. These rules remain in the domain types:

- unique and native `InstrumentId` values
- bare continuous-root validation and one synthetic ID per root
- backward-only adjustment modes and futures/mode consistency
- tradeable versus data-only FX leg separation
- closed recorded-mark vocabulary and ownership
- finite/non-negative Drift Bands and destination fraction
- valid sleeve direction and its fixed unit-gross exposure policy
- the exact match between contract instruments and plan bands
- schema-version negotiation and Aegis exception taxonomy
- component module/hash/parameter meaning and weight computation

The migration keeps exactly one native Nautilus `RebalanceStrategy` for the
Commingled Book lifecycle. It does not introduce per-Sleeve Strategies, Actors,
`StrategyFactory`, or `ImportableStrategyConfig`. In 1.231,
`StrategyFactory` resolves a Nautilus Strategy and its configuration and then
instantiates that lifecycle object. Aegis Sleeves instead run synchronously as
locked, vectorized `module.run` Components before allocation and order netting;
turning them into lifecycle objects would add OMS ownership or an internal
message protocol rather than remove domain machinery.

## Net complexity decision

**Adopt v6.** The full Struct migration has positive depth and information
hiding:

- one declaration per serialized type drives construction, JSON encoding,
  decoding, unknown-field rejection, default omission, and optional schema
  generation
- native `InstrumentId` and enum handling replaces Aegis annotation hooks
- the root `ExecutionBundle` serializes and parses directly; the loader retains
  only schema negotiation and one error-boundary translation
- the existing deep `compute_weights` method keeps Aegis vectorized decision
  semantics behind one interface, while the sole `RebalanceStrategy` owns the
  native trading lifecycle
- the runtime package loses its Pydantic dependency and two serialization
  systems no longer meet at the same wire seam
- no v5 compatibility surface survives

An envelope-only change is a **WONTFIX** because it leaks derived state and
weakens nested unknown-field rejection. A complete atomic v6 migration is the
simpler design.

## Evidence limits

The codebase review used full graph generation `2026-08-15T22:21:50Z` plus
exact source reads. Coverage checks found no recorded issue on the bundle,
loader, Drift Band, exposure, producer, wheel writer, tests, or package
manifest. Bounded scopes reported only excluded `__pycache__` directories. A
clean graph signal is best-effort, not proof of completeness. Source search
found no `dataclasses.replace`, `dataclasses.asdict`, or dataclass-field
reflection against the five proposed Struct types; the complete test suite is
still the authority for behavioral compatibility.

The probes were throwaway files outside the repository and made no production
changes.
