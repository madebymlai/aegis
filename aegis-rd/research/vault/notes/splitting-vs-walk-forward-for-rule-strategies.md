---
title: Splitting vs Walk-Forward for Rule Strategies
date: 2026-07-20
tags:
  - research-methods
  - vectorbt
  - validation
status: reasoned-only
---

# Splitting vs Walk-Forward for Rule Strategies

> [!note] Status
> Reasoned-only. This audits the current Aegis contract and implementation against official VectorBT Pro documentation. No strategy run has yet tested a replacement design.

## Conclusion

**Splitting is correct generic terminology for non-ML strategies.** VectorBT's `Splitter` explicitly supports rule-based algorithms that produce scores, not only predictive ML models.[^vbt-splitter] A split is data geometry. **Walk-forward analysis (WFA)** is a stricter chronological procedure built on that geometry: choose parameters from information available at one origin, then apply that choice only to the following unseen period.

The causal direction is **past into future**, never future into past. For split $i$:

$$
\theta_i = \operatorname{select}(S_i), \qquad \operatorname{score}_i = \operatorname{evaluate}(\theta_i, H_i), \qquad \max(S_i) < \min(H_i)
$$

VectorBT demonstrates exactly this with a rule-based SMA crossover: it finds the best parameters separately on each training range and passes the parameters for split $i$ to that split's test range.[^vbt-applying] Its purged walk-forward implementation likewise uses unshuffled folds immediately preceding the contiguous test folds.[^vbt-purged]

## The current Aegis run is not walk-forward

Aegis currently:

1. sweeps every candidate over **all** Selection windows;
2. globally ranks candidates across those windows;
3. takes the same best, median, and worst parameter sets;
4. evaluates those fixed sets over **all** Held-out windows.[^aegis-runner][^aegis-ranking]

In notation, the current operation is:

$$
\theta^* = \operatorname{select}(S_0, S_1, \ldots, S_n), \qquad
\operatorname{score}_i = \operatorname{evaluate}(\theta^*, H_i)
$$

That is a global historical robustness ranking, not WFA. With rolling or expanding windows, a later Selection window commonly contains, or occurs after, an earlier Held-out window. Therefore $H_0$ can influence $\theta^*$ through $S_1$ and the globally selected parameters are then applied backwards to $H_0$. Causal split geometry is insufficient when the selection algorithm aggregates across future origins.

This is especially visible with VectorBT's default two-set `from_rolling` geometry. The next range is anchored after the prior first set, so the prior OOS range becomes the next IS range.[^vbt-rolling] That reuse is correct in true WFA because the data has become known at the next origin. It becomes leakage only when a parameter set chosen using later origins is back-applied to earlier held-out ranges.

The behavior is intentional in [ADR-0002](../../../docs/adr/0002-replace-per-split-selection-with-global-ranking.md), but it changes the estimand. It also conflicts with the earlier run-lane requirement that each split select only from its own past Selection window and report the following test window.[^aegis-requirements] Consequently, the glossary's claim that the current Held-out sets provide "unbiased validation" is too strong for ordinary rolling or expanding configurations.[^aegis-context]

## What the schema currently guarantees

`RunSplitConfig` exposes a VBT method string plus arbitrary method parameters and resource caps.[^aegis-schema] Validation dynamically admits callable `vbt.Splitter.from_*` constructors, subject to denied parameters.[^aegis-catalog] The installed VBT surface includes chronological rolling/expanding methods, random ranges, generic ranges/splits, sklearn adapters, purged k-fold, and purged walk-forward constructors.

At runtime Aegis imposes exactly two role labels, `selection` and `held_out`. It checks that each set is non-empty and that the two sets do not overlap **within the same split**.[^aegis-splits] It does not establish:

- Selection-before-Held-out temporal order;
- chronology across splits;
- absence of cross-split overlap or reuse;
- that a Held-out observation was unknown to the selection procedure that produced its candidate;
- that the selected method represents the intended analysis mode.

Thus `split.method: from_rolling` describes geometry, not evaluation semantics. Arbitrary `from_*` methods cannot safely be treated as interchangeable sources of unbiased OOS evidence.

## Recommended distinction

Keep **Split** or **Splitter** as the low-level, VBT-native geometry vocabulary. Add an explicit analysis contract above it:

| Analysis intent | Candidate choice | Evaluation | Honest name |
|---|---|---|---|
| Fixed strategy, no parameter search | None | Metrics by time block/regime | split robustness analysis |
| Periodically retuned strategy | Select separately at each origin from past data | Apply that origin's choice to its next period | walk-forward analysis/optimization |
| One fixed parameter set for deployment | Select globally using only a development region | Evaluate once on a globally untouched outer holdout | fixed-candidate holdout validation |

For WFA, allow `from_rolling`, `from_n_rolling`, `from_expanding`, `from_n_expanding`, suitably constrained `from_ranges`, and `from_purged_walkforward`, but validate temporal invariants after construction. Rolling uses a bounded lookback; expanding uses all history available at each origin. Purged walk-forward is appropriate when prediction/evaluation intervals or trade horizons overlap; ordinary causal bar rules usually need chronological windows plus an explicit gap or embargo rather than event-label purging.[^vbt-cookbook][^vbt-purged]

The objection that per-split selection yields several non-deployable strategies conflates a fixed parameter set with a deployment policy. WFA evaluates a **periodic reselection policy**: at every live origin, rerun the same selection rule on then-available history. If Aegis intends to lock one immutable Candidate instead, it should use the fixed-candidate design with one untouched outer holdout and should not label interleaved rolling results unbiased walk-forward evidence.

## Sources

[^vbt-splitter]: VectorBT Pro, [Cross-validation: Splitter](https://vectorbt.pro/pvt_16ebf9ef/tutorials/cross-validation/splitter/#splitter). The documentation contrasts ML-focused tooling with rule-based algorithms and defines `Splitter` as arbitrary split-and-apply infrastructure.

[^vbt-applying]: VectorBT Pro, [Cross-validation applications: Applying](https://vectorbt.pro/pvt_16ebf9ef/tutorials/cross-validation/applications/#applying). The SMA example groups training results by split, chooses each split's best parameters, and passes those same split-indexed parameters to the test set.

[^vbt-purged]: VectorBT Pro, [PurgedWalkForwardCV API](https://vectorbt.pro/pvt_16ebf9ef/api/generic/splitting/purged/#vectorbtpro.generic.splitting.purged.PurgedWalkForwardCV). Training folds immediately precede contiguous test folds; overlapping prediction/evaluation intervals are purged.

[^vbt-rolling]: VectorBT Pro, [Cross-validation: rolling generation](https://vectorbt.pro/pvt_16ebf9ef/tutorials/cross-validation/splitter/#generation). With multiple sets, `from_rolling` defaults to placing the next split after the first range of the previous split; `offset_anchor_set=None` instead anchors after the entire previous split.

[^vbt-cookbook]: VectorBT Pro, [Cross-validation cookbook: Splitting](https://vectorbt.pro/pvt_16ebf9ef/cookbook/cross-validation/#splitting). Includes rolling WFA with non-overlapping test ranges and expanding windows with an explicit gap.

[^aegis-runner]: [`optimization/runner.py`](../../aegis_research/optimization/runner.py), lines 119-156 and 205-241. The runner builds one grid from every Selection window, selects representative candidates, then sweeps those candidates over every Held-out window.

[^aegis-ranking]: [`optimization/ranking.py`](../../aegis_research/optimization/ranking.py), lines 119-214. Candidate ranks are averaged across all Selection split labels before one best/median/worst set is returned.

[^aegis-requirements]: [Run-lane VBT rolling splitter requirements](../../../docs/brainstorms/2026-05-21-run-lane-vbt-rolling-splitter-requirements.md), R6 and AE2. These require per-split past Selection followed by future test evaluation.

[^aegis-context]: [`CONTEXT.md`](../../../CONTEXT.md), lines 27-56. The current domain model defines global ranking across Splits and calls subsequent Held-out evaluation unbiased.

[^aegis-schema]: [`configuration/schema.py`](../../aegis_research/configuration/schema.py), lines 246-260.

[^aegis-catalog]: [`run_splits.py`](../../aegis_research/run_splits.py), lines 132-263. The catalog discovers all callable `from_*` methods and validates parameters from signatures.

[^aegis-splits]: [`run_splits.py`](../../aegis_research/run_splits.py), lines 298-345. Aegis assigns two role labels, rejects empty sets, and checks overlap only between the two sets of the same split.
