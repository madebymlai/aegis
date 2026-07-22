# Extract registry cross-checks from the validation coordinator; narrow the resolve surface

Status: accepted

After the ADR-0012 collapse, ~300 of `configuration/validation.py`'s 536 loc were one concern —
checking that what a Run Config *selects* (strategy id, indicator ids and params, output contract,
ranking metric) is honored by the registries — written in two hand-paired dialects: typed checks on
the constructed `RunConfig` and best-effort raw-dict checks that co-report registry errors when
pydantic fails. We extract the concern into **`configuration/cross_checks.py`** behind a single
union entry — `cross_check_registries(config_or_raw, *, component_registry, metric_registry)
-> list[ConfigValidationIssue]` — that owns both dialects internally. The coordinator's call
becomes one unconditional line, making the "cross-checks always run, even when pydantic fails"
invariant visible in the code rather than kept by discipline. The module is package-internal: it
does not join the public config surface.

In the same change, **`resolve_run_config` narrows to raw-dict input only.** Its polymorphic
`ResolvedRunConfig`/`RunConfig` branches — including the metric-registry swap re-check
(`_assert_resolved_config_registries`) that imported a private validation function across modules —
serve zero production callers (the only production entry is `cli_commands/run.py` →
`load_run_config`); they were pinned by a single contract test. Branches, re-check, private import,
and pinning test are deleted.

Also deleted, extending the `92e3ca1` / ADR-0009 threat model (local, single-machine, trusted
config and code): the csv-path security check (`_validate_csv_path_security`,
`_is_absolute_or_user_path`) and the entire `output_dir` filesystem-safety check (symlink walk,
project-root containment, relative-only rule). These defend boundaries nothing crosses locally —
verified: lock resolution opens the candidate store via the current config's `output_dir`, so no
functionality depends on the rules. The system's real integrity boundary is the export gate
(issue #40, Nuitka bundle export); pre-export checks belong to that work when it lands. The lock
shape check stays in the coordinator and is re-documented as a typo-catcher (empty `run_id`,
unknown role keyword) — it was never security.

## Considered options

- **Registries validate selections against themselves (Tell-Don't-Ask):** `component_registry`
  and `metrics` each gain a "validate this selection → issues" surface, keeping manifest knowledge
  at home. Rejected: the cluster mixes registry-rules with *config*-rules (duplicate selection,
  `id: all`, issue paths in Run Config tree layout) that registries must not know; the concern
  would span three homes with the coordinator still merging, and the dual raw/typed dialect would
  fragment across packages.
- **Keep the swap path with a narrow public metric-membership export:** preserves today's resolve
  contract byte-for-byte. Rejected: the path is dead in production; keeping it would make
  `cross_checks.py` carry a second public name solely for a test-only affordance.
- **Keep path checks as portability rails (project-relative configs stay reproducible across
  machines):** rejected by the owner — portability is not a valued property here, csv is mostly
  unused, and export-time parity checks will be designed inside the export feature.

## Consequences

- `validation.py` becomes a genuine thin coordinator (~200 loc): prepass → whole-tree pydantic →
  error adapter → config-local checks (name, data-source whitelist, lock shape) → one
  `cross_check_registries` call. A new "does the config select something real?" rule lands in
  exactly one file.
- The `ConfigValidationIssue(path, message)` all-errors-at-once contract is unchanged. The raw
  dialect remains a deliberate membership-level subset (no params/output-contract checks), now
  documented in one place.
- Rule tests port from `resolve_run_config`-driven setups (tmp dirs + on-disk component files +
  discovery per case) to direct tests of the module's entry, using a new in-memory
  `FrozenComponentRegistry` factory in `tests/support/`. A thin layer of coordinator-level tests
  keeps pinning structural+registry co-reporting. Swap-path and path-security tests are deleted.
- The vestigial foot-of-file "circular dependency" imports in `validation.py` die — the cycle they
  guarded no longer existed at decision time (verified empirically; `configuration/__init__.py` was
  empty). **Amended post-implementation:** the sibling one-import-home slice of the same epic
  promoted `configuration/__init__.py` to the public surface, which created a *real* cycle
  (`__init__` → `resolution` → `component_registry` → `manifests` → `configuration.field_types` →
  `__init__`, introduced when manifest payload models reused the config field types). It is broken
  by deliberately deferring `component_registry` imports to `TYPE_CHECKING` or function scope inside
  `resolution`/`validation`/`cross_checks` — load-bearing this time, not vestigial. The cleaner
  long-term cut, if the deferred imports grate, is hoisting `field_types` out of the
  `configuration` package.
- "Registry cross-checks" is architecture vocabulary, not domain language: no CONTEXT.md term.
  CONTEXT.md's existing sentence — "Configs are inert — they select trusted IDs and parameters
  only" — is the domain concept this module enforces.

## Amendment — 2026-07-22: typed-only registry cross-checking

The raw best-effort dialect and the union entry described above are removed. Registry
cross-checking now accepts only a complete `RunConfig` plus frozen registries. Resolution
first constructs the typed Run Config without registry state; structural failure stops
before discovery, Metric Registry construction, or cross-checking.

After typed construction, resolution discovers or accepts the Component Registry, derives
requested ranking and report Metric IDs from `RunConfig`, constructs the effective Metric
Registry, and accumulates all typed registry issues. The typed band-override universe issue
is retained and co-reported with those registry issues. Discovery and registry-integrity
failures remain fail-fast setup errors rather than authoring diagnostics.

The programmatic boundary accepts Mapping-shaped input and immediately copies it to the
plain authored mapping used for evidence and hashing. YAML scalars, sequences, and other
non-mapping roots retain the friendly `$: run config must be a mapping` diagnostic.
