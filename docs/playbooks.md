# Playbooks

Playbooks under `research/playbooks/{indicators,strategies}/` are legacy research artifacts. They are not a forward `aerd run` authoring surface. New runs use component refs directly, component-owned `param_space()` callables, and the native `optimization` block.

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

Removed forward fields:

- `strategy.source` and indicator `source` selectors are rejected. Component identity is implicit; entries name component `id` directly.
- Indicator `ids` batching is rejected. Use one indicator entry per component id so locks and candidate pins are unambiguous.
- `candidate_grid` is removed from the forward run contract. Use component `param_space()` with `vbt.Param` plus `optimization.search` and `optimization.split`.
- Top-level `split` is legacy scoring shape. Forward configs put split policy under `optimization.split`.

Historical playbook artifacts may remain readable for concrete audit/reporting needs, but new work must not extend `playbook_sweep_result.v1`, add new playbook optimization contracts, or reintroduce candidate-axis execution. Migration means moving the reviewed signal logic into `research/components/`, declaring `defaults` and optional `param_space_callable`, then rerunning through the component-native optimization path.

Public component examples live under `docs/examples/components/`.
