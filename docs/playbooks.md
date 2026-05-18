# Playbooks

Notebook playbooks are repo-controlled exploratory notebooks under `research/playbooks/{labels,indicators,strategies}/`. `aerd run` selects them by stable ID from notebook metadata, not by path:

```yaml
lane: run
strategy:
  source: playbook
  id: ma_strategy_explore
  params:
    threshold: 0.01

indicator_refs:
  - source: playbook
    id: ma_explore
    params:
      window: 10
  - source: component
    id: all

ranking:
  metric: total_return_pct
  direction: desc
```

Each indicator playbook ID represents one indicator idea/family. Parameter sweeps inside that family are allowed. Run configs may select playbook indicator refs, explicit component indicator refs, and an `id: all` component selector in the same run. If a baseline exists, the playbook declares exactly one component indicator ID and emits baseline metric evidence; leaderboard rows show indicator source, primary metric, optional baseline metric, raw delta, and direction-adjusted delta. Baseline-delta ranking is used only when explicitly selected.

Run artifacts are immutable evidence under the configured run root. Playbook-backed rows remain source-labeled as playbook evidence; manual promotion into `research/components/` is still a reviewed source-code step, not an automatic command that mutates component files.

Configs cannot provide arbitrary notebook paths, scripts, imports, inline Python, formulas, generated run state, last-run refs, or leaderboard-row refs as reproducible `run`/`train` inputs.

Public playbook examples live under `docs/examples/playbooks/`.
