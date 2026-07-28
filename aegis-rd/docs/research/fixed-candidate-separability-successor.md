# Successor to the Friedman separability warning

> **Status: superseded.** The continuous Observation-Block ranking design replaces
> the whole-Development winner and separate held-out replay assumed below. This file
> is retained only as historical research context.

**Date:** 2026-07-21  
**Question:** What should tell Aegis that the globally ranked fixed-Candidate winner is not uniquely supported by continuous Development evidence?

## Recommendation

Report a **Model Confidence Set (MCS)** over the full admissible Candidate grid and warn whenever the preselected global winner is not the only member of that set. Build it by jointly block-bootstrapping the continuous Development Candidate paths and recomputing the exact configured ranking Metric on every resampled path.

This is one metric-agnostic statistical pipeline. It does not need observational execution Windows, per-Metric significance formulas, or an adapter registry. The registered Metric calculation remains the sole definition of Candidate performance; MCS supplies the common multiple-comparison procedure around it.

MCS is the conceptual successor to the old Friedman warning. Friedman accepted any Metric because it reduced an already-existing block-by-Candidate matrix to ranks, but its nominal p-value required repeated independent blocks. After removing execution Splits, Aegis has one continuous path and one whole-Development Metric per Candidate. MCS obtains the required sampling distribution by dependence-preserving resampling instead of recreating portfolio boundaries. It returns a multiplicity-aware set designed to contain the best object at the stated confidence level and explicitly applies to general objects such as trading rules. [Hansen, Lunde, and Nason (2011), *The Model Confidence Set*](https://doi.org/10.3982/ECTA5771), [author working paper](https://pure.au.dk/ws/files/34269366/rp10_76.pdf)

The result is evidence only. It must not select, rerank, replace, invalidate, or relabel any Candidate.

## One statistic for every registered Metric

Let `M_i = metric(path_i)` be Candidate `i`'s exact complete-Development ranking Metric after normalizing the registered direction so that larger is better. For each shared bootstrap draw `b`, resample the aligned Development timestamps in blocks across every Candidate and every primitive metric input, reconstruct each resampled path, and ask the existing Metric engine for:

```text
M_i^b = metric(resampled_path_i^b)
```

For each Candidate pair, define:

```text
Delta_ij   = M_i - M_j
Delta_ij^b = M_i^b - M_j^b
SE_ij      = bootstrap_standard_error(Delta_ij^b)
```

The observed MCS range statistic is:

```text
T_R,M = max(i,j in M) abs(Delta_ij / SE_ij)
```

Calibrate it with null-centered bootstrap differences:

```text
T_R,M^b = max(i,j in M) abs(((Delta_ij^b - Delta_ij) / SE_ij))
p_M     = mean(T_R,M^b >= T_R,M)
```

If the equal-performance test rejects, apply the coherent range-statistic elimination rule to remove the empirically worst member from the temporary set and repeat. Stop at the first non-rejection. The survivors form `MCS_95`. MCS also assigns each Candidate an inclusion p-value through the sequential procedure. These internal eliminations construct evidence; they never modify the Aegis Candidate Grid or its frozen roles. [Hansen, Lunde, and Nason, Sections 2–3](https://pure.au.dk/ws/files/34269366/rp10_76.pdf)

This formula does not change for Sharpe, drawdown, or a bespoke utility. Only the existing registered Metric calculation changes the meaning of `M_i`. The MCS paper expressly allows a user-specified criterion and uses trading rules ranked by Sharpe as an example. That does not make bootstrap inference assumption-free: the chosen block bootstrap must consistently estimate the sampling distribution of the statistic. Aegis therefore records the protocol and reports unavailable evidence when the statistic cannot be validly recomputed or studentized; it never substitutes mean return or another proxy.

## Deep module and Candidate-path contract

The implementation should be one deep Candidate Separability module. Its interface accepts:

- the admissible continuous Development Candidate paths;
- the configured ranking Metric;
- canonical Run identity.

It returns Separability Evidence. The module owns synchronized resampling, resampled-path reconstruction, registered-Metric recomputation, studentization, sequential MCS elimination, warnings, and failure reasons. Callers do not manipulate bootstrap arrays or know metric-specific significance behavior.

The canonical Candidate path contains the synchronized primitive observations needed by the existing Metric engine. All columns and inputs use the same sampled timestamp sequence so serial dependence and cross-Candidate covariance remain represented. Derived state must be reconstructed from resampled primitives: for example, resampled returns produce a new Equity Curve and drawdown; already-derived equity levels are not themselves shuffled.

This is statistical resampling of completed Development evidence. It does not rerun parameter optimization, alter Candidate parameters, reset the original portfolio, or introduce observational execution Splits.

The module returns `separability_evidence=unavailable(reason)` rather than a nominal p-value when:

- the exact registered Metric cannot be recomputed from the canonical resampled path;
- the Metric or pairwise variance is non-finite or degenerate;
- usable observations are insufficient for the block protocol;
- synchronized Candidate paths cannot be formed.

No Metric declaration or adapter registration is required. Unavailability is a property of the attempted evidence calculation, not a second Metric capability system.

## Fixed bootstrap protocol

Aegis uses one shared Politis–Romano stationary bootstrap with 10,000 replications. Stationary bootstrap blocks have geometrically distributed lengths and are designed for weakly dependent stationary observations. [Politis and Romano (1994), *The Stationary Bootstrap*](https://doi.org/10.1080/01621459.1994.10476870)

The expected block length is selected deterministically with the corrected Patton–Politis–White automatic selector applied to Candidate-versus-cross-sectional-average performance-differential series. Aegis uses the largest finite estimate, clamped to the usable Development length. [Patton, Politis, and White (2009), correction to automatic block-length selection](https://doi.org/10.1080/07474930802459016)

The bootstrap seed derives from canonical Run identity. Confidence level (`alpha=0.05`), bootstrap kind, replication count, block-length rule, and seed derivation are Evidence-protocol constants, not Run Config fields.

## Warning semantics

```text
if |MCS_95| > 1:
    warn: "Development evidence does not isolate a unique superior Candidate
           (95% Model Confidence Set: N of K Candidates). The globally ranked
           winner is retained, but its role is not statistically unique."
elif evidence is unavailable:
    warn with the precise unavailable reason
else:
    no separability warning
```

Evidence records the initial equal-performance p-value, MCS members, per-Candidate MCS p-values, elimination order, ranking Metric, confidence level, statistic, bootstrap kind, block length, replication count, seed, and usable observations.

A multi-member MCS does not prove that its members are equal. It means Development evidence did not exclude them from the superior set at 95% confidence. A singleton means separation only within this searched Development grid; it is not out-of-sample validation. An MCS p-value is not the probability that a Candidate is best.

## Why not SPA, Reality Check, or nominal Friedman?

| Method | Question | Fit |
|---|---|---|
| Model Confidence Set | Which Candidates cannot be excluded from the superior set? | **Yes.** It returns the required multiplicity-aware set without a separately chosen benchmark. |
| White Reality Check | Does any searched alternative beat a fixed benchmark? | No. It answers a benchmark-superiority question. |
| Hansen SPA | Does any alternative beat a fixed benchmark? | No. It improves Reality Check power but still does not return the superior set. |
| Nominal Friedman | Are ranks equal across independent blocks? | No. The continuous design has no independent execution blocks, and adjacent synthetic blocks would make the nominal p-value miscalibrated. |

[White (2000), *A Reality Check for Data Snooping*](https://doi.org/10.1111/1468-0262.00152) and [Hansen (2005), *A Test for Superior Predictive Ability*](https://doi.org/10.1198/073500105000000063) remain relevant when an independently fixed benchmark exists, but they are not the successor to the Candidate-indistinguishability warning.

## Terminal holdout

The terminal Held-out period does **not** participate in path construction, resampling, block-length choice, metric recomputation, MCS membership, or warning thresholds. MCS is a Development-only post-selection uncertainty diagnostic. Held-out remains a separate replay of frozen representatives.

One terminal regime can flatter or punish a Candidate by luck, but no p-value can turn that one realized regime into evidence about regimes that were never observed. The diagnostic must therefore describe Development separability honestly and must not claim that it makes Held-out representative.
