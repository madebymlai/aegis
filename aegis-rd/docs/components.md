# Components

Components are reviewed Python percent-cell files under `research/components/{indicators,strategies}/`. Run configs select them by manifest `id`:

```yaml
strategy:
  id: demo.cross

indicators:
  - id: demo.ma
```

Each entry carries `id` plus optional values-only `params` that fix declared parameters.

YAML never imports Python, names modules, embeds formulas, or points at arbitrary files. Discovery reads only the literal `COMPONENT_MANIFEST`, the required module-level `run` entry point, and the optional module-level `param_space` entry point without executing the component file. Callable code loads only after validation selects a known ID under the fixed component root.

## Authoring Contracts

The full component authoring contract (file structure, manifest fields, entry-point signatures, return shapes, selection conventions, ownership boundaries, legacy errors) lives in two CLI guides rendered from the validating models and code constants:

- **`aerd show indicator-schema`** — Indicator Component authoring contract.
- **`aerd show strategy-schema`** — Strategy Component authoring contract.

Run `aerd show indicator-schema` or `aerd show strategy-schema` for the single source of authoring-contract truth. Add `--json` for programmatic consumption.

## Component Catalogs

- **`aerd show components`** — List all discovered component IDs, their inputs, outputs, and whether they expose a searchable `param_space`.

## Directory-Level Concerns

Local component files are ignored by git by default except placeholder READMEs. Ignored files are not secret management; do not store credentials in local research code.

Packaged component examples live under `research/aegis_research/component_registry/authoring/indicator_example.py` and `research/aegis_research/component_registry/authoring/strategy_example.py`. These are the single authorable references — round-tripped through the real registry parser.
