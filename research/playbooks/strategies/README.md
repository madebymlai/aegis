# Local Strategy Playbooks

This directory is for repo-controlled local strategy playbooks selected by stable ID.

Local playbook files are ignored by git by default. Run-lane strategy playbooks use `result_schema: "playbook_sweep_result.v1"`, expose a strategy candidate axis, and materialize requested entry/exit signal batches. Use `docs/examples/playbooks/strategy_playbook_example.py` as the public authoring reference. Ignored files are not secret management; do not store credentials here, and force-add local research playbooks only after an intentional review.
