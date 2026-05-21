# Local Strategy Playbooks

This directory is for repo-controlled local strategy playbooks selected by stable ID.

Local playbook files are ignored by git by default. New strategy playbooks must declare `result_schema: "aegis.optimization_source.v1"` and return one parameterized pipeline plus a `params` mapping built from `vbt.Param`; Aegis wraps it in `vbt.cv_split`. See `docs/examples/playbooks/optimization_playbook_example.py`. `vbt.Param` jointly searches indicator and strategy parameters when the indicator is computed inside the pipeline.

The older `result_schema: "playbook_sweep_result.v1"` contract (strategy candidate axis plus bounded materializer) is **deprecated and scheduled for removal under issue #32**. It is retained only for already-authored playbooks and external read/reporting tools; do not author new playbooks against it. See `docs/examples/playbooks/strategy_playbook_example.py`.

Both contracts route through `aerd run`. Configs that declare `optimization` require an optimization-source strategy; configs without `optimization` currently still accept the deprecated sweep contract. Ignored files are not secret management; do not store credentials here, and force-add local research playbooks only after an intentional review.
