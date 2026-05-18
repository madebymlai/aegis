# Playbooks

Notebook playbooks are repo-controlled exploratory notebooks under `research/playbooks/{labels,indicators,strategies}/`. `aerd play` selects them by stable ID from notebook metadata, not by path:

```yaml
lane: play
play:
  stages: [indicators]
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

Each indicator playbook ID represents one indicator idea/family. Parameter sweeps inside that family are allowed. If a baseline exists, the playbook declares exactly one component indicator ID and emits baseline metric evidence; leaderboard rows show indicator source, primary metric, optional baseline metric, raw delta, and direction-adjusted delta. Baseline-delta ranking is used only when explicitly selected.

Play artifacts are exploratory evidence under `runs/play/`: successful runs replace `last-run` after staging validation, optional backup preserves the previous completed last-run, and failed attempts never replace the prior successful last-run. Play artifacts can inform manual promotion, but there is no automatic command that mutates component files.

Configs cannot provide arbitrary notebook paths, scripts, imports, inline Python, formulas, generated play state, last-run refs, or leaderboard-row refs as reproducible `run`/`train` inputs.
