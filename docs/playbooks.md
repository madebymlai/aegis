# Playbooks

Playbooks are no longer a supported `aerd run` authoring surface. The active contract is component-only: run configs name strategy and indicator component IDs directly, components declare defaults and optional module-level `param_space()`, and all execution goes through native `optimization.search` with `optimization.split`.

Forward component config shape:

```yaml
strategy:
  id: rsi_reversion_opt

indicators: []

ranking:
  metric: total_return
  direction: desc

optimization:
  search: random
  random_subset: 16
  seed: 42
  evidence:
    return_grid: first
  split:
    method: from_rolling
    params:
      length: 252
      offset: 252
      split: 0.8
    max_splits: 10
```

Removed fields are now unknown to the forward schema: `strategy.source`, indicator `source`, indicator `ids`, top-level `split`, and `candidate_grid`. Migrate reviewed signal logic into `research/components/` and use component-owned `vbt.Param` spaces instead of candidate-axis execution.

Public component examples live under `research/aegis_research/component_registry/indicator_example.py` and `research/aegis_research/component_registry/strategy_example.py`.
