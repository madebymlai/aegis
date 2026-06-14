# Local Strategy Components

This directory is for reviewed local strategy component files selected by stable ID. Discovery is recursive — subdirectories are free organization; run configs select components by manifest `id`, never by path. Verify discovery with `aerd show components`.

Use `aerd show strategy-schema` for the full Strategy Component authoring contract. The packaged authorable reference lives at `research/aegis_research/component_registry/strategy_example.py`.

Live component files are tracked by git by default after review. Historical variants under an `archive/` subdirectory are ignored by git; ignored files are provenance clutter control, not secret management.
