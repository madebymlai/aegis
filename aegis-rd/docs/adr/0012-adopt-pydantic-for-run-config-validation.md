# Adopt pydantic v2 for Run Config validation

Status: accepted

We replace the hand-rolled validation toolkit (the ~310-loc `validation/base.py`
type/required/range primitives) with **pydantic v2** (`pydantic.dataclasses`, per-field
strict) as the Run Config schema-and-validation layer. The driver is single-source-of-truth:
requiredness now lives with the field — a field with no default *is* required — so the
`gross_cap` "default `1.0` in the schema, `is required` in the validator" drift becomes
unrepresentable. The schema dataclasses *become* pydantic dataclasses, so a model both
validates and constructs: this collapses the three homes a field has today
(`schema.py` type/default · `validation/*.py` rule · `builders.py` construction) into one,
and **`builders.py` dissolves** into the models. The serialized type stays a dataclass, so
`to_builtin` and the `resolved_config.v1` byte oracle (ADR-0003/0004) are preserved.

## Considered options

- **Stay code-first; derive requiredness from `__dataclass_fields__` (option B):** the cheap
  fix — one helper, no dependency — and it kills the same drift. Rejected as the end state
  because it leaves the 310-loc primitive toolkit in place and gives cross-field rules no
  declarative home; chosen pydantic also deletes the toolkit and houses domain rules in
  validators.
- **cattrs:** structures into stdlib dataclasses (byte oracle safe by construction) and
  accumulates errors. Rejected after a prototype: its error→issue mapping bakes the path into
  the message string (needs string-parsing to recover our flat `(path, message)` contract),
  and its default float coercion is *laxer* than today — it silently accepts `bool` as a
  number, a strictness regression, unless custom structure hooks are registered.
- **msgspec:** fastest and modern, but fail-fast (raises on the first error), which breaks the
  established all-errors-at-once `ConfigValidationError` contract; and its `Struct` is not a
  stdlib dataclass, so `to_builtin` would need teaching.
- **marshmallow / jsonschema / schema-first codegen:** a separate schema artifact re-creates
  the two-authorities split we are removing, and schema-first cannot express the recursive
  security sweeps or the byte-stable serialization without bolt-ons.

## Consequences

- New runtime dependency: pydantic v2 (`pydantic-core`, Rust). Added to `pyproject`.
- **Models validate *and* construct; `builders.py` dissolves.** The schema dataclasses become
  `@pydantic.dataclasses.dataclass`, so `TypeAdapter(T).validate_python(raw)` produces the real
  frozen instance. The nested coercion `builders.py` did — `data.quality`, `optimization.split`,
  the polymorphic `lock:` scalar-or-mapping handle — moves onto the models (`mode="before"`
  validators / nested dataclasses). **Construction now validates**: the ~149 direct
  construction sites keep their `PortfolioConfig(...)` call shape but run validators in
  `__init__`. No unchecked escape hatch is provided — no site builds a deliberately-invalid
  instance (the validation-failure tests drive a raw dict through the model/coordinator, not
  the constructor), so there is nothing to protect.
- **Byte oracle preserved, with one deliberate exception.** `pydantic.dataclasses` is
  byte-identical to the stdlib dataclass for normal float inputs (verified by prototype and
  pinned by `tests/.../test_resolved_config_oracle.py`). The single forced byte change: an
  integer YAML literal in a `float` field (`gross_cap: 1`) currently serializes as `1` but
  coerces to `1.0` under pydantic (confirmed: strict `float` accepts `int` and coerces, while
  still rejecting `bool`/`str` — matching today's `_is_number`). We **normalize** rather than
  reject int literals — it is the natural strict behaviour and fixes a latent quirk (today an
  `int` is stored in a `float` field). It lands as an isolated, reviewed "normalize numeric
  fields to float" change with the golden hash updated in the same commit — never silently.
- **Strict is per-field, not model-level.** `Annotated[T, Field(strict=True)]`; model-level
  `strict=True` makes pydantic refuse to build a dataclass from a dict.
- **Repeated constraints are named once as a domain-type vocabulary** in a dedicated
  `configuration/field_types.py` (`PositiveCash` = `gt=0`, `UnitInterval` = `ge=0, le=1`,
  `NonNegativeRate` = `ge=0`, …). This is No-Primitive-Obsession applied to the schema and an
  Information-Hiding win — `gross_cap: PositiveCash` reads as the domain rule, and a change to
  the strictness rule is one edit, not ~40 copy-pasted `Annotated[...]`.
- **Requiredness is decided explicitly per section, because there is more than one drift.**
  The defaulted-yet-required offenders are **`gross_cap` *and* `data.arrays`** (both default in
  `schema.py` yet `"is required"` in their validator); both drop their default and become
  field-required. The change is byte-invisible — the validator already forced them explicit in
  every real config. `schema_version` is a *benign* third case: it keeps its model default
  (ergonomic in-code construction) and the coordinator keeps enforcing present-in-raw +
  `== CONFIG_SCHEMA_VERSION`, because "must appear in the YAML" is an input-presence rule, not a
  property of the constructed type (same bucket as `output_dir`).
- **The `ConfigValidationIssue(path, message)` contract is kept; structural wording becomes
  pydantic's.** A small `ValidationError.errors() → ConfigValidationIssue` adapter maps
  `loc` → our dotted path and takes pydantic's `msg` **verbatim** — there is **no translation
  table**. The ~89 generic structural messages adopt pydantic's phrasing and the asserting
  tests are updated to match; this is a deliberate, one-time UX change, not a silent rider. The
  ~21 bespoke messages (removed-field tombstones, "resolved internally" guidance) stay
  hand-written and are emitted by the **coordinator's raw-dict prepass**, *not* by a pydantic
  validator. (Verified against 2.12.5: a `@model_validator` raising `ValueError` yields
  `loc=()` — no field path — and prepends `"Value error, "` to the message, destroying both the
  exact string and the `portfolio.entry_budget`-style path.) So a shared `removed_fields(map)`
  coordinator helper scans the raw section, appends `ConfigValidationIssue(path, message)` with
  the exact string, and **strips the matched keys before pydantic runs** — otherwise
  `extra="forbid"` double-emits an unknown-key error for the same key. The per-section map may
  live as a class-var on the model for co-location (OCP); the coordinator consumes it.
  Unknown-key consequence: with `extra="forbid"` on a pydantic *dataclass*, an unexpected key is
  rejected with its path but the verbatim wording **"Unexpected keyword argument"** (type
  `unexpected_keyword_argument`) — *not* the `BaseModel` phrasing "Extra inputs are not
  permitted", and not the old "unknown field" string; the path is the guarantee callers and
  tests rely on.
- **Registry/filesystem checks stay in the coordinator; models are context-free.** Checks that
  need runtime state pydantic lacks at validation time — `ranking.metric ∈ metric_registry`,
  component-ref `id` registered + the strategy/indicator output contract (`component_registry`),
  and `output_dir` filesystem safety (cwd/symlink/project-root) — are **not** threaded through
  `model_validate(context=...)`; they remain in the coordinator. The registry validators
  **slim to membership-only** (`_validate_ranking` → just `_validate_metric_selection`;
  component refs → just "id registered" + output contract); their structural checks move onto
  the models, so they do not double-emit errors pydantic now owns.
- **Coordinator shape and all-errors-at-once.** The coordinator runs: a **raw-dict prepass**
  for tombstones (top-level removed-training fields and per-section removed fields — emit +
  strip), the pydantic validation (catching `ValidationError`), and the slimmed
  registry/filesystem checks on the raw dict — **merging all into one issue list** so a
  structural error and a registry error co-report. (The contract is soft: tests assert issue
  *membership*, not an exact set.) Intra-section invariants (e.g. `search == "random"` ⇒
  `random_subset` + `seed` required) live on `@model_validator(mode="after")` — note these emit
  at section-root path (`loc=()`) with a `"Value error, …"` message, so their tests assert the
  section path, not a field path. The code has no registry-free *cross-section* invariant, so no
  cross-section layer is built.
- The executable/denied-key security gates were already removed (commit `92e3ca1`, local +
  trusted-input threat model) and stay removed; this ADR does not reintroduce them.
- **Test-construction factories land first.** Dropping the `gross_cap`/`data.arrays` defaults
  breaks every direct construction site that omits them (~149, across ~20 test files). A
  `make_portfolio_config(**overrides)`-style factory in test support is landed *before* the
  first port, so each port edits one helper rather than N call sites and the diffs stay
  reviewable.
- **Migration is section-by-section, collapsing to a whole-tree model at the end.** Behind the
  oracle test: lock `resolved_config.v1` (done), land test factories, normalize int→float, then
  port `portfolio` → `data` → `optimization` → `components` → `ranking`/`lock`. *During*
  migration each ported section gets a pydantic dataclass + `TypeAdapter`; the coordinator merges
  issues across ported and un-ported sections. *At the end*, with every section a pydantic
  dataclass, collapse to a single whole-tree `RunConfig` model — one `validate_python`
  accumulates all structural errors natively.
- **End state (the deletion-test win).** The `configuration/` validation surface (~13 files
  today) collapses to four core modules: `field_types.py` (domain-type vocabulary, the only new
  module), `schema.py` (the pydantic models + their `@model_validator`s + per-section tombstone
  maps), `validation.py` (the thin coordinator: prepass → validate → adapter →
  registry/filesystem/presence → merge), and `resolution.py` (unchanged). Deleted:
  `builders.py`, `validation/base.py`, and the six per-section validator modules (`components`,
  `data`, `lock`, `metrics`, `optimization`, `portfolio`) — the `validation/` package collapses
  to its coordinator. If the tree does not shrink to roughly this, something leaked.
  `env_references.py` and `configuration/__init__.py` are untouched.

## Amendment — 2026-07-22: the model is the structural authoring contract

The accepted forward contract now makes `schema_version` and `optimization` required,
keyword-only model fields. `schema_version` is the current-version Literal and
`optimization` is non-null, so every constructed `RunConfig` represents an executable
Run. Run-name syntax and scalar Lock-handle shape are likewise owned by Pydantic authoring
types and validators.

This supersedes the earlier decision to give those fields model defaults and enforce
their presence with a raw prepass. The prepass constants, special missing-optimization
message, post-construction name/Lock checks, and downstream null-optimization guards are
removed. Structural wording is Pydantic's verbatim wording through the existing
`ConfigValidationIssue` adapter.

The shared Pydantic field vocabulary also moves from the configuration package to a
neutral Aegis RD authoring leaf consumed by both Run Config schema and Component
manifests. This removes their import cycle without creating a compatibility surface.
Registry orchestration and structural-versus-registry co-reporting are addressed
separately by the ADR-0014 amendment.

## Amendment — 2026-07-22: typed construction is the registry cutoff

Run Config resolution now performs one registry-free whole-tree Pydantic construction
before any Component discovery, Metric Registry construction, or registry cross-check.
If construction fails, resolution returns all Pydantic structural issues and stops. Raw
authoring mappings are retained only as boundary input and authored evidence; they are no
longer interpreted by a second validation dialect.

When construction succeeds, the coordinator's typed band-override universe issue may be
combined with typed Component and Metric registry issues. Registry discovery and integrity
failures remain separate setup errors because there is no trustworthy registry against
which authoring selections can be checked.

## Amendment — 2026-07-23: Component manifests collapse onto the same rule

The manifest layer now follows the decision this ADR made for Run Config: the model
validates *and* constructs. `IndicatorManifest`, `StrategyManifest`, and their
`ComponentManifest` base become `@pydantic_dataclass(frozen=True, extra="forbid")` in
`component_registry/contracts.py`, carrying the field constraints and
`@model_validator`s directly. The private `_BaseManifestPayload` /
`_IndicatorManifestPayload` / `_StrategyManifestPayload` mirror models and both
`_build_*_manifest` builders are **deleted** — `manifests.py` was still running the
`builders.py` pattern this ADR dissolved everywhere else, so a manifest field had three
homes (payload model, domain dataclass, builder) instead of one.

- **Strict stays per-field, as this ADR already requires.** Re-confirmed against pydantic
  2.13.4: `strict=True` on a dataclass config — or passed to `validate_python` — rejects
  dict input outright with `dataclass_exact_type` ("Input should be an instance of
  IndicatorManifest"). The payload models could carry model-level
  `ConfigDict(strict=True)` because they were `BaseModel`s; the domain dataclasses cannot.
- **Authored lists, domain tuples.** Authors write `"input_names": ["Close"]`; the frozen
  type holds a tuple. `AuthoredArrayNames`/`AuthoredParamNames` pair a `BeforeValidator`
  that converts *only* the authored `list` form with `Field(strict=True)` on the tuple, so
  every other sequence shape is rejected. This is load-bearing rather than cosmetic: plain
  lax tuple validation accepts a `set`, which `ast.literal_eval` can produce, and its
  iteration order would leak through `public_snapshot()` into the registry fingerprint.
- **Unknown-key wording follows the dataclass, as it did for Run Config.** Manifests now
  report `"Unexpected keyword argument"` instead of the `BaseModel` phrasing `"Extra inputs
  are not permitted"`; four assertions in `test_component_registry.py` are updated. Both
  authoring surfaces now word unknown keys identically. Error accumulation is unaffected —
  field errors and the unexpected-keyword error still surface together in one
  `ComponentRegistryError`.
- **Construction now validates, and that immediately paid.** A test stub was building an
  Indicator with `output_names=()` — a state the parser has always rejected but the
  unvalidated dataclass allowed. Making the illegal state unrepresentable surfaced it.
- **Byte-invisible.** `public_snapshot()` still emits lists via `to_builtin`, so no golden
  hash moves.

The two families keep their split for a real reason, not a mirroring one: `param_names`
and `defaults` are common and live on the base with the shared
`defaults ⊆ param_names` validator; the family-specific required fields are `kw_only`
so they can sit among the base's defaulted fields — the `DataConfig.arrays` pattern.
