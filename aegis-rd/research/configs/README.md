# Local Run Configs

Local `aerd run` configs are ignored by git by default. Directory layout carries no semantics: subdirectories are free organization, the config is always selected by the explicit path passed to `aerd run <config>`, and no mode is inferred from folders or CLI flags.

Use `aerd run <config>` for strategy or research sweeps over direct component refs.

## Authoring Contract

The full Run Config forward contract (field tree with requiredness and defaults, literal catalogs, lock syntax, split params, component ID selection, embedded validated example) lives in a CLI guide rendered from the validating pydantic models and code constants:

- **`aerd show config-schema`**: the exact Run Config authoring shape `aerd run` accepts. Structural requiredness and literal constraints come from the validating model; curated prose supplies domain semantics.

Run `aerd show config-schema` for the single source of authoring-contract truth. Add `--json` for programmatic consumption.

## Related Catalogs

- **`aerd show splitters <method>`**: inspect available splitter methods and signature-derived params before authoring YAML.
- **`aerd show components`**: list available component IDs for `strategy.id` and `indicators[].id`.

Ignored files are not secret management. Do not put API keys, provider tokens, or credentials directly in local YAMLs or notebooks. Use environment-backed secret references, and do not force-add local configs unless they are intentionally reviewed as tracked artifacts.
