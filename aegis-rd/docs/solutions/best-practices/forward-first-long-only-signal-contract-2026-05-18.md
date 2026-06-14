---
title: Forward-First Long-Only Signal Contract
date: 2026-05-18
category: best-practices
module: research/aegis_research
problem_type: best_practice
component: tooling
severity: medium
applies_when:
  - Implementing or reviewing signal-generation contracts
  - Removing legacy config fields from a forward-first interface
  - Passing long-only strategy settings into VectorBT portfolio simulation
  - Handling next-open execution over purged or non-contiguous splits
related_components:
  - development_workflow
  - testing_framework
  - documentation
tags:
  - signal-generation
  - forward-first
  - long-only-contract
  - vectorbt
  - diagnostics
  - schema-validation
---

# Forward-First Long-Only Signal Contract

## Context

Aegis RD issue #11 made `positive_class_probability` the input to a v1 long-only signal contract. The contract deliberately excludes short-only, long/short, `direction="both"`, reversal, borrowing, futures, and bearish leverage behavior until a future side-specific signal contract exists.

During implementation review, two guardrails mattered as much as the positive path. Removed config fields must remain removed rather than becoming compatibility branches, and short-side VectorBT settings must not appear as active simulator settings when the v1 contract is long-only. A related correctness issue also surfaced: default `next_open` execution must not bridge non-contiguous purged train gaps by treating the next retained train row as the next executable market bar.

Session history search found no relevant prior sessions for this specific learning.

## Guidance

Keep the public signal contract forward-first and action-specific. The current v1 shape names the policy, entry threshold, exit threshold, and execution timing directly:

```python
SignalConfig(
    policy="long_only_hysteresis",
    long_entry_threshold=0.55,
    long_exit_threshold=0.50,
    execution_timing="next_open",
)
```

Do not add compatibility branches for removed fields such as `signals.long_threshold` or `signals.exit_threshold`. Keep them out of the dataclass field set so normal unknown-field validation rejects them before runtime behavior begins:

```python
signals = _section(raw, "signals", set(SignalConfig.__dataclass_fields__), issues)
```

Only pass long-relevant settings into VectorBT for the v1 contract:

```python
VBT_LONG_SIGNAL_SETTINGS = {
    "accumulate": False,
    "upon_long_conflict": "ignore",
}

vbt.Portfolio.from_signals(
    close=close,
    entries=entries,
    exits=exits,
    direction="longonly",
    **VBT_LONG_SIGNAL_SETTINGS,
)
```

Record short-side settings separately as contract diagnostics, not active VBT settings:

```python
"contract": {
    "direction_scope": "long_only_v1",
    "not_applicable_vbt_settings": VBT_SHORT_SIDE_SETTINGS_NOT_APPLICABLE,
}
```

Preserve `same_close` when the plan explicitly supports it. It is not dead code if a close-only data path or research comparison intentionally opts into it and tests exercise it. The timing requirement helper should reflect the default contract and require Open unless `same_close` is explicit:

```python
signal_config = signal_config or SignalConfig()
if signal_config.execution_timing == "next_open" and "Open" not in features:
    features.append("Open")
```

For `next_open`, use the full market index to identify whether a raw signal has a following adjacent in-split market row. Signals before purged gaps or on terminal split rows should stay in raw diagnostics but be masked out of simulation inputs and counted separately:

```python
simulation_entries, simulation_exits, diagnostics = _simulation_signals(
    close.index,
    entries,
    exits,
    signal_config,
    market_index=market_index,
)
```

## Why This Matters

Forward-first contracts stay auditable because removed fields fail loudly instead of mutating into new behavior. A custom migration branch for a removed field looks helpful, but it preserves legacy schema surface and invites future compatibility shims that the contract explicitly rejected.

Long-only portfolio simulation is easier to review when active VBT settings are exactly the settings that can affect the long-only run. If short-side conflict or opposite-entry settings are listed under active `vbt_settings`, reviewers can reasonably infer that short behavior is supported or executable.

`next_open` execution also needs split-aware adjacency, not just row order after filtering. In purged validation, train indices can contain multiple disjoint blocks. A signal at the end of one train block must not execute at the Open of the next retained train block after omitted test or purge rows.

## When to Apply

- A plan says a contract is forward-first and old fields are removed.
- A single model output such as `positive_class_probability` is not a side-specific short score.
- VectorBT `Portfolio.from_signals` receives direction-unaware `entries` and `exits` under `direction="longonly"`.
- Diagnostics need to explain unsupported simulator settings without making them look active.
- `next_open` execution runs on split subsets that may be non-contiguous relative to the full market index.

## Examples

Removed fields should fail as unknown fields:

```yaml
train:
  signals:
    long_threshold: 0.60
    exit_threshold: 0.40
```

Representative tests keep this behavior explicit:

```python
test_removed_signal_threshold_fields_fail_as_unknown_fields
test_portfolio_direction_is_long_only_for_v1_signal_contract
test_next_open_signal_before_market_index_gap_is_non_executable
test_purged_fixlb_runs_with_close_only_csv
```

`same_close` remains valid only as an explicit timing override:

```yaml
train:
  signals:
    policy: long_only_hysteresis
    long_entry_threshold: 0.55
    long_exit_threshold: 0.50
    execution_timing: same_close
```

Default `next_open` requires Open and records non-executable signals when no adjacent in-split execution row exists:

```python
assert result.diagnostics["execution"]["gap_non_executable_signals"] == 1
assert result.diagnostics["simulation_signals"]["entry_states"] == 0
```

## Related

- [Config Contract Security and Reproducibility](../architecture-patterns/config-contract-security-reproducibility-2026-05-16.md)
- [Model Plugin Target and Probability Contract](../architecture-patterns/model-plugin-target-probability-contract-2026-05-17.md)
- [Model Execution Timing Explicitly in VectorBT Backtests](./vectorbt-execution-timing-nextopen-2026-05-17.md)
- [VectorBT Same-Bar Stop Limitations](../logic-errors/vectorbt-same-bar-stop-limitations-2026-05-17.md)
- GitHub issue #11: Review signal generation and conflict semantics
