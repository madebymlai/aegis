# Local Strategy Components

This directory is for reviewed local strategy component files selected by stable ID. Discovery is recursive — subdirectories are free organization; run configs select components by manifest `id`, never by path. Verify discovery with `aerd show components`.

Use `aerd show strategy-schema` for the full Strategy Component authoring contract. The packaged authorable reference lives at `research/aegis_research/component_registry/strategy_example.py`.

Local component files are ignored by git by default. Ignored files are not secret management; do not store credentials here, and force-add local research code only after an intentional review.
