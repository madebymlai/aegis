# Local Indicator Components

This directory is for reviewed local indicator component files selected by stable ID. Discovery is recursive — subdirectories are free organization; run configs select components by manifest `id`, never by path. Verify discovery with `aerd show components`.

Use `docs/examples/components/indicator_component_example.py` as the public authoring reference. An indicator component is a Python percent-cell file (every `# %%` cell labeled with a purpose, including one `# %% main` cell) declaring a literal `COMPONENT_MANIFEST` and a module-level `run` function. The manifest requires `family: "indicators"`, `id`, `version`, `input_names`, and `output_names`; `param_names` and `defaults` are optional. Define module-level `param_space()` when the component has searchable params. The `run(data, *, n_candidates, **param_lists)` entry point reads declared features via `data.feature(...)` and returns a mapping of output name to candidate-major `(rows, n_candidates * n_symbols)` array.

Local component files are ignored by git by default. Ignored files are not secret management; do not store credentials here, and force-add local research code only after an intentional review.
