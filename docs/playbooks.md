# Playbooks

Playbooks are repo-controlled Jupytext-compatible Python percent-cell files under `research/playbooks/{labels,indicators,strategies}/`. `aerd run` selects them by stable ID from `PLAYBOOK_MANIFEST`, not by path:

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

Each playbook ID represents one research idea/family. Playbooks own sweep grids and variant definitions; components are fixed-param promoted implementations. Run configs select source blocks only: `ids: all` expands to every discovered playbook for that source, and `ids: [...]` selects explicit stable IDs. Playbooks receive runner-provided inputs through the same logical data contract as components, and run configs still declare `data.arrays` for those inputs. Playbooks do not receive run-config params; put VectorBT-native parameter grids in the playbook itself. Every emitted `variant_records` row must include a `params` mapping containing the swept parameter values needed to reproduce or promote that candidate, for example `{"window": 20, "wtype": "simple", "threshold": 0.01}`. Use `params: {}` when the candidate varies by named logic rather than tunable params. Strategy playbook rows must return `entries` and `exits` signals; Aegis computes portfolio metrics centrally. Playbook-provided metrics are not leaderboard authority.

Indicator playbook rows become rankable only when a strategy source consumes their named outputs and emits executable signals. Each indicator candidate returns source-scoped outputs such as `{"outputs": {"ma": ma_frame}}`; strategies read them from keys like `inputs.indicators["playbook:ma_explore"]["outputs"]["ma"]`. Aegis fails the run if a selected indicator playbook axis is not consumed by the strategy, because an unused indicator should not appear next to ranked strategy metrics.

Leaderboards rank complete composed strategy candidates, not raw indicators. A row is the combination of strategy source/candidate/params, consumed indicator source/candidate/params, portfolio config, and Aegis central VBT metrics:

```json
{
  "composed_candidate_id": "strategy:playbook:ma_cross:fast+indicators:[playbook:ma_explore:ma-20]",
  "strategy_source": "playbook",
  "strategy_id": "ma_cross",
  "strategy_candidate_id": "fast",
  "strategy_params": {"threshold": 0.01},
  "indicator_candidates": [
    {
      "source": "playbook",
      "id": "ma_explore",
      "candidate_id": "ma-20",
      "params": {"window": 20},
      "outputs": ["ma"]
    }
  ],
  "metric_authority": "aegis",
  "primary_metric": "total_return_pct"
}
```

Use purposeful percent cells in playbook files: a broad overview cell that states the research idea and source data, imports/definitions as needed, a literal metadata cell, and a `# %% main ...` cell containing the callable. The callable docstring should explain the indicator, label, or strategy approach being explored.

In `PLAYBOOK_MANIFEST`, `family` is the registry bucket and must match the directory: `indicators`, `strategies`, or `labels`. Indicator playbooks also declare `indicator_family`, which describes the idea being explored, such as `moving_average`; it is not the registry bucket.

Run artifacts are immutable evidence under the configured run root. Playbook-backed rows remain source-labeled as playbook evidence; manual promotion into `research/components/` is still a reviewed source-code step, not an automatic command that mutates component files. To promote a composed winner, copy the winning indicator source/candidate/params into a fixed indicator component, copy the winning strategy source/candidate/params into a fixed strategy component, and rerun with those component refs to verify the promoted implementation.

Configs cannot provide arbitrary source paths, imports, inline Python, formulas, generated run state, last-run refs, or leaderboard-row refs as reproducible run inputs.

Public playbook examples live under `docs/examples/playbooks/`.
