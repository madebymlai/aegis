# Local Strategy Components

This directory is for reviewed local strategy component files selected by stable ID. Discovery is recursive — subdirectories are free organization; run configs select components by manifest `id`, never by path. Verify discovery with `aerd show components`.

Use `docs/examples/components/strategy_component_example.py` as the public authoring reference. A strategy component is a Python percent-cell file (every `# %%` cell labeled with a purpose, including one `# %% main` cell) declaring a literal `COMPONENT_MANIFEST` and a module-level `run` function. The manifest requires `family: "strategies"`, `id`, `version`, `input_names`, and an `output_name` in `{active, scores, ranks, target_weights}`; `consumes_outputs`, `param_names`, and `defaults` are optional, and `owns_portfolio` must stay `false`. Define module-level `param_space()` when the component has searchable params. The `run(inputs, *, n_candidates, **param_lists)` entry point reads `inputs.data`, candidate-major indicator arrays under `inputs.indicators[output_name]`, and `inputs.n_symbols`, and returns one candidate-major `(rows, n_candidates * n_symbols)` array.

Local component files are ignored by git by default. Ignored files are not secret management; do not store credentials here, and force-add local research code only after an intentional review.
