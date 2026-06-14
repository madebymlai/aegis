---
title: Understand from_rolling offset Semantics (Additive to Default Step)
date: 2026-05-29
category: best-practices
module: vectorbtpro.generic.splitting
problem_type: best_practice
component: optimization
severity: medium
applies_when:
  - configuring from_rolling splits for walk-forward optimization
  - setting the offset param in an optimization config
  - seeing fewer splits than expected from a rolling splitter
  - tuning non-overlapping in-sample / out-of-sample windows
tags:
  - vectorbtpro
  - from-rolling
  - splitter
  - cross-validation
  - walk-forward
  - offset
  - optimization
---

# Understand from_rolling offset Semantics (Additive to Default Step)

## Context

When configuring `from_rolling` splits for walk-forward optimization, the
`offset` parameter is easy to misread as the total distance between the start
of consecutive splits. It is not.

`offset` is **additive** to VBT's default step, not the total distance between
split starts. When `split` creates multiple sets, VBT's default step equals the
in-sample (IS) length — the first set. Setting `offset=N` adds `N` extra bars
**beyond** that default step.

```
effective_step = IS_length + offset
```

Misreading this leads to setting a large `offset` (e.g. equal to the IS length)
in the belief it produces standard non-overlapping walk-forward, when in fact it
doubles the step and skips entire regimes between splits.

## Guidance

For standard non-overlapping walk-forward — where the out-of-sample (OOS) window
of split N feeds directly into the in-sample window of split N+1 — use
`offset: 0`.

```yaml
optimization:
  cv:
    method: from_rolling
    params:
      length: 252
      offset: 0      # standard non-overlapping walk-forward
      split: 0.8
    max_splits: 100
```

Worked example showing how `offset` changes the effective step and split count:

```yaml
# length=504, split=0.5 → IS=252 bars, OOS=252 bars

# offset: 0   → step=252, 5 splits on 7yr daily data (correct)
# offset: 126 → step=378, 4 splits (gap between OOS and next IS)
# offset: 252 → step=504, 3 splits (skips entire regimes)
```

## Why This Matters

A non-zero `offset` silently reduces the number of splits and leaves gaps in
coverage. With `offset` set to the IS length, every other regime is skipped
entirely, so the optimization never validates against those periods — producing
fewer, less representative splits while looking like a correctly configured
walk-forward.

## When to Apply

- Apply when authoring or reviewing an optimization config that uses
  `from_rolling`.
- Apply when the number of splits produced is lower than expected for the data
  length and IS/OOS sizing.
- Apply when you intend OOS of one split to become IS of the next
  (contiguous, non-overlapping walk-forward) — use `offset: 0`.

## Examples

Review question: "Do I want OOS of split N to feed straight into IS of split
N+1?" If yes, `offset: 0`. Any non-zero `offset` deliberately introduces a gap
(or overlap, via the anchor controls) between consecutive split starts.

## Related

- [VBT docs: Cross-Validation > Splitter > Rolling](https://vectorbt.pro/pvt_16ebf9ef/tutorials/cross-validation/splitter/#rolling)
  — full offset anchor controls (`offset_anchor_set`, `offset_anchor`,
  `offset_space`).
- `research/configs/README.md` — optimization config contract and splitter
  pipeline notes.
