# Local Indicator Playbooks

This directory is for repo-controlled local indicator playbooks selected by stable ID.

Local playbook files are ignored by git by default. Run-lane indicator playbooks use `result_schema: "playbook_sweep_result.v1"` and emit candidate-indexed output surfaces for strategy playbook sweeps. Use `docs/examples/playbooks/indicator_playbook_example.py` as the public authoring reference. Ignored files are not secret management; do not store credentials here, and force-add local research playbooks only after an intentional review.
