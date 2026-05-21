# Local Indicator Playbooks

This directory is for repo-controlled local indicator playbooks selected by stable ID.

Local playbook files are ignored by git by default. Indicator playbooks use `result_schema: "playbook_sweep_result.v1"` and emit candidate-indexed output surfaces for legacy strategy playbook sweeps. Use `docs/examples/playbooks/indicator_playbook_example.py` as the public authoring reference.

Issue #31 optimization sources (`aegis.optimization_source.v1`) compute their indicators inside the parameterized pipeline using `vbt.Param`; they do not consume external indicator playbooks. Indicator playbooks therefore apply only to the legacy candidate-sweep path. Ignored files are not secret management; do not store credentials here, and force-add local research playbooks only after an intentional review.
