# Playbooks

Notebook playbooks are repo-controlled exploratory notebooks under `research/playbooks/{labels,indicators,strategies}/`. `aerd run` selects them by stable ID from notebook metadata, not by path:

```yaml
strategy:
  source: playbook
  id: ma_strategy_explore

indicators:
  - source: playbook
    ids: [ma_explore]
  - source: component
    ids: all

ranking:
  metric: total_return_pct
  direction: desc
```

Each indicator playbook ID represents one indicator idea/family. The selected playbook or component owns its defaults, sweep grids, and variant definitions. Run configs select source blocks only: `ids: all` expands to every discovered indicator for that source, and `ids: [...]` selects explicit stable IDs. If a baseline exists, the playbook declares exactly one component indicator ID and emits baseline metric evidence; leaderboard rows show indicator source, primary metric, optional baseline metric, raw delta, and direction-adjusted delta. Baseline-delta ranking is used only when explicitly selected.

Run artifacts are immutable evidence under the configured run root. Playbook-backed rows remain source-labeled as playbook evidence; manual promotion into `research/components/` is still a reviewed source-code step, not an automatic command that mutates component files.

Configs cannot provide arbitrary notebook paths, scripts, imports, inline Python, formulas, generated run state, last-run refs, or leaderboard-row refs as reproducible run inputs.

Public playbook examples live under `docs/examples/playbooks/`.
