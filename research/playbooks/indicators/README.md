# Local Indicator Playbooks

This directory is for repo-controlled local indicator playbooks selected by stable ID.

Local playbook files are ignored by git by default. Indicator playbooks use `result_schema: "playbook_sweep_result.v1"` and emit candidate-indexed output surfaces consumed by deprecated strategy playbook sweeps. Use `docs/examples/playbooks/indicator_playbook_example.py` as the existing authoring reference.

Indicator playbooks are **deprecated and scheduled for removal under issue #32**, alongside the strategy sweep contract they feed. Optimization sources (`aegis.optimization_source.v1`) compute their indicators inside the parameterized pipeline using `vbt.Param` and do not consume external indicator playbooks; `vbt.Param` jointly searches indicator and strategy parameters when the indicator is computed inside the pipeline. Do not author new indicator playbooks. Ignored files are not secret management; do not store credentials here, and force-add local research playbooks only after an intentional review.
