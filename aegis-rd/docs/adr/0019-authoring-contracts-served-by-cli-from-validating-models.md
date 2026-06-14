# Authoring contracts are served by the CLI, rendered from the validating models

Status: accepted

The authoring contracts for Run Configs and Components are served by three new CLI
guides — `aerd show config-schema`, `aerd show indicator-schema`, `aerd show
strategy-schema` — as curated markdown for an LLM (or human) author. Each guide is a
**hybrid template** owned by the package that owns the contract it documents
(`configuration/` for config-schema, `component_registry/` for the component guides):
derivable sections — field tables, literal catalogs such as
`STRATEGY_ALLOCATION_OUTPUTS` and `DATA_ARRAY_SHORTCUTS` — are interpolated from the
validating pydantic models and code constants at render time, so they cannot drift;
semantics prose (the batched `run` entry-point signature, NaN-selection convention,
candidate-major layout) is curated by hand; example snippets are complete, working
artifacts that tests round-trip through the real parser/validator. The prose docs this replaces
(`docs/components.md`, the schema section of `research/configs/README.md`) shrink to
pointers, and the drift-assertion tests (`test_cli_docs.py` style) migrate to assert
against rendered guide output. The driver is the same single-source-of-truth argument as
ADR-0012: contract knowledge previously lived in three homes (models, docs, README) that
demonstrably drifted — repaired by hand in commits like `6a6a0c5`.

Two contract details are part of the decision:

- **The config-schema guide states the forward contract, not the pydantic model.** The
  model alone misstates it: pydantic declares `optimization` optional and gives
  `schema_version` a default, while the validation prepass requires both (`optimization`
  present; `schema_version` present and exactly 8) and owns the tombstones and source
  whitelist. The prepass overlay gets one exported home in `configuration/` consumed by
  both the validator and the guide, so the requiredness rules cannot fork.
- **Naming rule across the `aerd show` surface:** plain-noun subcommands (`components`,
  `splitters`) show *what exists* (catalogs); `*-schema` subcommands show *how to
  author* (contracts). `show components` stays — the guides do not replace the
  discovery/verification catalog.

The v2 component contract (ADR-0017) reinforces the hybrid choice: the manifest carries
domain facts only, while the entry points are fixed-name structural rules (`def run`,
optional `def param_space`, presence-detected in the AST) — contract knowledge a pydantic
field table cannot express, only curated prose plus interpolated constants
(`COMPONENT_ENTRYPOINT`, `COMPONENT_PARAM_SPACE_ENTRYPOINT`) can.

## Considered options

- **Raw `TypeAdapter(RunConfig).json_schema()` dump:** free and drift-proof, but
  knowingly emits a schema that contradicts validation (optimization nullable,
  schema_version omittable) — authors would produce configs the printed schema accepts
  and `aerd run` rejects.
- **Static markdown printed verbatim + assertion tests:** simplest, but drift is caught
  only for the exact strings someone remembered to assert; field tables go stale the day
  a model field changes.
- **Fully generated from `json_schema()`:** zero drift, but the semantics an author
  actually needs (NaN selection, candidate-major layout, the batched entry-point
  signature) have no code source and would be lost.
- **Docs as templates** (CLI renders `docs/*.md` with interpolation markers): single
  source and browsable on disk, but the markdown grows placeholder syntax that is wrong
  when read raw, and `docs/` becomes a runtime dependency of the CLI.

## Consequences

- Example components move from `docs/examples/components/` into the owning packages
  next to their templates; the example config references the example components, and a
  test wires them together via `discover_component_registry(root=...)` so the whole
  authoring story round-trips end-to-end through the real parser and validation path.
- Guide commands keep the `CommandResult` envelope: human mode prints the markdown,
  `--json` wraps it as `{"format": "markdown", "content": ...}`. No structured
  field-table payload until something consumes it.
- `docs/components.md` and the configs README keep only directory-level concerns
  (gitignore semantics, layout-carries-no-semantics) plus a pointer to the guide
  commands.
