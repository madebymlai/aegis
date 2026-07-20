# VectorBT splitting vs walk-forward analysis

Date: 2026-07-20

## Conclusion

Splitting is valid terminology for the mechanism, including for rule-based strategies. Walk-forward analysis is the causal evaluation protocol built from chronological splits. The relevant boundary is not ML versus non-ML: as soon as historical results choose strategy parameters or a strategy variant, that choice is a fitted decision and must not use information later than the period being evaluated.

Walk-forward means past selection data chooses parameters that are frozen and evaluated on the immediately later held-out period. It never means selecting with future data and applying the result to an earlier period.

## VectorBT semantics

VectorBT explicitly applies cross-validation to rule-based as well as ML-based models. Its `cv_split` implementation runs the parameter grid on the first set of **each split**, stores that split's grid, and uses that grid to select the parameter combination executed on the remaining set(s) of the same split. This is per-split selection, not one global selection across every training window. Sources: [Cross-validation applications](https://vectorbt.pro/pvt_16ebf9ef/tutorials/cross-validation/applications/#summary), [`cv_split` API](https://vectorbt.pro/pvt_16ebf9ef/api/generic/splitting/decorators/#vectorbtpro.generic.splitting.decorators.cv_split).

Relevant splitter families have different causal meanings:

- `from_rolling` and `from_n_rolling` can express rolling walk-forward windows when set 0 precedes set 1. [`from_rolling` API](https://vectorbt.pro/pvt_16ebf9ef/api/generic/splitting/base/#vectorbtpro.generic.splitting.base.Splitter.from_rolling)
- `from_expanding` and `from_n_expanding` can express anchored/expanding walk-forward windows. [`from_expanding` API](https://vectorbt.pro/pvt_16ebf9ef/api/generic/splitting/base/#vectorbtpro.generic.splitting.base.Splitter.from_expanding)
- `from_purged_walkforward` guarantees consecutive training folds preceding the test fold and supports purging. [`from_purged_walkforward` API](https://vectorbt.pro/pvt_16ebf9ef/api/generic/splitting/base/#vectorbtpro.generic.splitting.base.Splitter.from_purged_walkforward)
- `from_purged_kfold` uses the non-test folds as training data. Consequently, for early or middle test folds, training includes later observations. Purging/embargo controls label overlap but does not turn K-fold into a causal deployment simulation. [`from_purged_kfold` API](https://vectorbt.pro/pvt_16ebf9ef/api/generic/splitting/base/#vectorbtpro.generic.splitting.base.Splitter.from_purged_kfold)

## Current Aegis mismatch

The config model exposes `RunSplitConfig.method` as an unrestricted string plus raw VBT parameters (`research/aegis_research/configuration/schema.py`). Validation checks that the method and arguments match a `vbt.Splitter.from_*` signature, while materialization checks two non-empty, non-overlapping sets (`research/aegis_research/run_splits.py`). It does not enforce that every selection timestamp strictly precedes every held-out timestamp. Thus `from_purged_kfold` is accepted even though some splits train on the future relative to their held-out set.

More importantly, `optimization/runner.py` sweeps all selection windows, `optimization/ranking.py` globally ranks each fixed candidate across all of those windows, and only then `runner.py` applies the three global representatives to every held-out window. This is not VectorBT's per-split `cv_split` behavior and is not walk-forward. Under the default rolling geometry, held-out window `i` commonly becomes selection window `i+1`, so data reported as held out also participates in the global candidate choice later in the same run.

This contradicts the domain statement in `CONTEXT.md` that held-out sets provide unbiased validation of selected candidates.

## Recommended contract

Use a semantic validation protocol in config rather than exposing arbitrary VBT factories directly, for example `optimization.validation.protocol: walk_forward` with an explicit `window: rolling | expanding`, selection length, held-out length, step, and gap/purge horizon. Compile that contract internally to `from_rolling`, `from_expanding`, or `from_purged_walkforward`, and validate the generated membership invariant `max(selection) < min(held_out)` for every split.

Execution must then choose between two distinct products:

1. **Adaptive walk-forward:** select parameters separately on each past window, freeze them for that split's next held-out window, and stitch/aggregate only the resulting out-of-sample periods. The result is a parameter schedule, not one fixed Candidate.
2. **One promotable fixed Candidate:** use inner resampling on a historical development region, choose one Candidate globally, and evaluate it once on a final untouched outer holdout. Earlier inner folds are selection evidence, not unbiased held-out evidence for that globally selected Candidate.

For a genuinely immutable one-candidate rule with no calibration or variant selection, no train/test fitting step exists; splitting is only an evaluation/reporting choice. A chronological terminal holdout is usually clearer than calling arbitrary K-fold sets selection and held-out.
