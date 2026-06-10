# Local Indicator Components

This directory is for reviewed local indicator component files selected by stable ID. Discovery is recursive — subdirectories are free organization; run configs select components by manifest `id`, never by path. Verify discovery with `aerd show components`.

Use `docs/examples/components/indicator_component_example.py` as the public authoring reference. An indicator component is a Python percent-cell file (every `# %%` cell labeled with a purpose, including one `# %% main` cell) declaring a literal `COMPONENT_MANIFEST` and a literal `COMPONENT_CALLABLE`. The manifest requires `family: "indicators"`, `id`, `version`, `input_names`, `output_names`, and `wide_callable`; `param_names`, `defaults`, and `param_space_callable` are optional. The wide callable `(data, *, n_candidates, **param_lists)` reads declared features via `data.feature(...)` and returns one candidate-major `(rows, n_candidates * n_symbols)` array.

Local component files are ignored by git by default. Ignored files are not secret management; do not store credentials here, and force-add local research code only after an intentional review.
