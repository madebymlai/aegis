# Local Strategy Playbooks

This directory is for repo-controlled local strategy playbooks selected by stable ID.

Local playbook files are ignored by git by default. Strategy playbooks declare one of two `result_schema` contracts:

- `aegis.optimization_source.v1` is the forward VBT-native optimization path (issue #31). The playbook returns one parameterized pipeline plus a `params` mapping built from `vbt.Param`; Aegis wraps it in `vbt.cv_split`. See `docs/examples/playbooks/optimization_playbook_example.py`.
- `playbook_sweep_result.v1` is the legacy candidate-sweep contract. The playbook exposes a strategy candidate axis and materializes requested entry/exit signal batches. See `docs/examples/playbooks/strategy_playbook_example.py`.

Both contracts route through `aerd run`. Configs that declare `optimization` require an optimization-source strategy; configs without `optimization` use the legacy sweep contract. Ignored files are not secret management; do not store credentials here, and force-add local research playbooks only after an intentional review.
