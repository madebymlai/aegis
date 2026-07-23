# Local Strategy Components

Reviewed local **Strategy** component files, selected by stable `id`.

Discovery is recursive: subdirectories are free organization, and run configs
select components by manifest `id`, never by path. Verify discovery with
`aerd show components`.

- **Authoring contract:** `aerd show strategy-schema`
- **Worked example:** `research/aegis_research/component_registry/authoring/strategy_example.py`

Live component files are tracked by git once reviewed. Historical variants under
an `archive/` subdirectory are git-ignored to control provenance clutter, not to
manage secrets.
