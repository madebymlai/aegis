# Continuous-replay, regime-robust Candidate selection

**Date:** 2026-07-21  
**Question:** How should RD select one fixed-parameter Candidate across changing regimes when every Candidate is simulated causally and continuously exactly once?

## Decision

Use **blocked rank selection over observational views of one continuous Candidate path**.

Each Candidate gets one causal replay from the common start to the common end. Predeclared chronological blocks do not create portfolios, initialize cash, close positions, repeat fees, or recompute signals. They only select intervals from the already-realized net return/state path for the configured Metric. Rank Candidates within each block and select the lowest mean rank across blocks.

This retains the current protection against a single large performance spike without adding a strategy-specific “robustness rule.” The configured Metric still defines performance; temporal rank aggregation defines how consistently that Metric compares across the different environments actually observed.

Do not call the resulting winner out of sample. All Development blocks participate in selection. A terminal holdout is needed only if someone wants a post-selection historical validation claim, and then it must sit after every decision it is intended to validate—preferably after the complete `book.toml` is frozen—not inside RD Candidate promotion.

## Common derived warmup

Warmup is derived from Component contracts and is not a researcher-configurable selection boundary.

1. Materialize the sampled Candidate grid before resolving the scored interval.
2. Resolve every configured Indicator and Strategy `lookback(**resolved_candidate_params)` for every sampled Candidate.
3. Let each Candidate's required warmup be the maximum of its Component lookbacks.
4. Let the Run's `resolved_warmup_bars` be the maximum required warmup across the sampled Candidate grid.
5. Derive one `scored_start` from `data.start` and `resolved_warmup_bars`; every Candidate and every Observation Block uses that same start.

There is no `optimization.warmup_bars` floor or other manual warmup override. A shorter-lookback Candidate must not receive additional scored rows, and a larger sampled lookback must visibly move the common scored start rather than silently change Candidate comparability. Rows before `scored_start` remain causal computational inputs and create no scored Portfolio activity. If the derived start leaves fewer than the required number of complete Observation Blocks after the deterministic remainder rule, preflight rejects the Run.

Evidence records `data.start`, `resolved_warmup_bars`, `scored_start`, and the Candidate/Component lookback values that determined the maximum. This makes a start change attributable to the sampled grid rather than to a discretionary configuration knob.

## The design

Let Candidate `c`'s single replay produce the aligned, net-of-cost portfolio path

```text
P_c = {(V_c,t, r_c,t, position_c,t, cash_c,t, ...): t = 1,...,T}
```

where each action at `t` depends only on its permitted information set and `r_c,t` is computed from continuous portfolio value, including inherited positions and all costs. The prequential principle assesses a sequential procedure from the forecasts/actions actually issued and outcomes subsequently observed; it supports this chronological, information-set-respecting object rather than shuffled or independently restarted episodes. [Dawid and Vovk (1999)](https://doi.org/10.2307/3318616)

Before looking at Candidate results, partition the scored interval into `K` contiguous, non-overlapping, equal-duration blocks `B_1,...,B_K`. Choose block duration as part of the research protocol, long enough for the configured Metric to be meaningful. Do not optimize block boundaries or duration against Candidate results. A short final remainder should be handled by a predeclared rule (for example, merge it into the previous block), not by a performance-dependent choice.

For each Candidate and block, calculate

```text
s[c,k] = Metric(observational_view(P_c, B_k))
q[c,k] = within_block_rank(direction_normalize(s[:,k]))
Q[c]   = mean_k(q[c,k])
winner = argmin_c(Q[c])
```

Use midranks for ties and a deterministic, non-performance tie-break for equal `Q`. Every block compares Candidates on the same timestamps. Equal-duration blocks and equal block weights make the estimand explicit: *relative Metric consistency over calendar time*. If the business instead wants equal weight per named regime, that is a different estimand and must be declared in advance.

Friedman's blocked rank construction supplies the relevant statistical idea: rank treatments within a block so the block's level and scale do not dominate the comparison. Here Candidates are treatments and chronological intervals are blocks. This use of ranks is a selection functional, not a nominal Friedman hypothesis test; adjacent time blocks are dependent and should not be treated as independent replicates for a textbook p-value. [Friedman (1937)](https://doi.org/10.1080/01621459.1937.10503522)

Ranks deliberately discard the size of a block win. Therefore one exceptional interval contributes one good rank, not an arbitrarily large amount to `Q`. This is the desired spike protection. It also means ranks alone can conceal the severity of losses. Always report the raw `s[c,k]`, paired score differences, full continuous equity path, and full-period Metric beside `Q`; those are evidence, not additional gates or reranking rules. Research on unstable environments likewise shows that a global average can hide changes in relative performance and motivates examining its local time path. [Giacomini and Rossi (2010)](https://doi.org/10.1002/jae.1177)

## A block is a view, not a replay

The boundary contract is the crucial part:

- orders before a block remain in the portfolio record;
- cash, positions, valuation, leverage, accrued costs, and strategy state cross the boundary unchanged;
- the first return in `B_k` uses the actual value immediately before that timestamp;
- trades spanning a boundary remain one trade; no artificial exit or entry is created;
- the Metric receives the interval of the continuous analysis path, not a freshly initialized portfolio.

For path-dependent Metrics, “slice the rows” is not sufficient if it silently resets analytical state. Drawdown, for example, must have an explicit convention: either carry the continuous historical high-water mark into the view, or define the Metric as block-local. The convention belongs to the Metric and must be identical for every Candidate and every block. It must not be an accidental side effect of reconstructing a block portfolio.

VectorBT PRO already distinguishes these two semantics. Its simulation-range documentation shows that an already-simulated `Portfolio` can be analyzed with `sim_start`/`sim_end`; with the default `rec_sim_range=False`, returns are computed over the full path and only the final metric is restricted to the requested interval. `rec_sim_range=True` recursively restricts the analysis chain and can instead behave as though earlier orders did not exist. The required design is the former: one `Portfolio`, interval analysis, and no recursive historical truncation. [VectorBT PRO simulation ranges](https://vectorbt.pro/pvt_16ebf9ef/features/analysis/#simulation-ranges)

## Regime semantics

Prefer fixed chronological blocks to ex-post regime labels for selection. They are regime-agnostic samples of changing market conditions and cannot be moved around to flatter a Candidate.

Named regimes may be useful for attribution, but a regime label can participate in selection only if its definition was frozen and its value at `t` is computed from information available by `t-1`. A label such as “the 2020 crash,” assigned with knowledge of how the episode ended, is valid descriptive evidence but not a causal selection input. Conditional predictive-ability research permits evaluation under heterogeneous, time-varying processes, but conditions decisions on information available at the decision date. [Giacomini and White (2006)](https://doi.org/10.1111/j.1468-0262.2006.00718.x)

No finite historical procedure proves robustness to an unobserved regime. The defensible claim is narrower: the selected Candidate had the best mean relative rank across the predeclared chronological environments in Development.

## Repeated pseudo-out-of-sample evidence without resets

An optional expanding-prefix trace can answer whether historical ordering persisted:

1. At boundary `k`, select the provisional winner using only block ranks `1,...,k-1`.
2. Record that already-specified Candidate's rank and raw score in block `k`.
3. Repeat without changing any Candidate parameters or replaying any portfolio.

This is a rolling-origin/pseudo-out-of-sample diagnostic of the **selection rule**, not the final Candidate's OOS result. Multiple forecast origins generally reveal more about performance variation than one terminal forecast origin. [Tashman (2000)](https://doi.org/10.1016/S0169-2070(00)00065-0) Because the diagnostic observes each Candidate's continuously running shadow portfolio, it must not be presented as the P&L of a deployable strategy that switched into previously unheld Candidate states.

The final `book.toml` Candidate can still be the winner from all Development blocks. The expanding-prefix trace reports ranking persistence; it does not rerank the final result.

## Dependence-aware uncertainty, not a robustness gate

Selection should be deterministic from `Q`. Statistical procedures should describe whether that winner is well separated, not introduce a pass/fail “robustness rule.”

For sampling uncertainty, resample the synchronized vector of Candidate net returns or primitive Metric inputs—never each Candidate independently. Identical sampled timestamps preserve paired cross-Candidate comparisons. Recompute block Metrics and ranks on every draw, then report rank-difference intervals and winner frequency.

The stationary bootstrap draws geometrically distributed consecutive blocks and provides inference for weakly dependent **stationary** observations. [Politis and Romano (1994)](https://doi.org/10.1080/01621459.1994.10476870) That assumption is incompatible with blindly bootstrapping across a path whose regime instability is the object of concern. The defensible use is:

- resample within each predeclared block only when local weak stationarity is plausible;
- preserve each observed block's place and weight, so the bootstrap is conditional on the observed regime composition;
- rebuild derived analytical quantities from the resampled primitive series;
- declare uncertainty unavailable when blocks are too short or local stationarity is implausible.

This bootstrap estimates noise around the observed-regime comparison. It does not simulate new regimes, establish invariance to structural breaks, or turn Development selection into OOS validation.

If the Metric admits a per-period loss representation, Model Confidence Set inference can additionally return the Candidates that cannot be excluded from the superior set while respecting multiple comparisons. Uninformative data correctly leave a larger set. [Hansen, Lunde, and Nason (2011)](https://doi.org/10.3982/ECTA5771) RD may still need one deterministic winner for `book.toml`; choosing the lowest `Q` member remains the declared selection rule, while a multi-member confidence set honestly reports weak separation.

## Search breadth and holdout conclusion

Blocked ranks stop one magnitude spike from dominating. They do **not** remove search overfitting. Reusing one history to try many variants can make the best observed result arise by chance, so the Candidate family and all prior trials must remain part of the evidence lineage. [White (2000)](https://doi.org/10.1111/1468-0262.00152) If there is a predeclared benchmark, Hansen's SPA test provides a multiplicity-aware benchmark-superiority test that is less sensitive than White's Reality Check to poor and irrelevant alternatives. [Hansen (2005)](https://doi.org/10.1198/073500105000000063)

A terminal RD holdout is therefore neither the source of regime robustness nor a substitute for trial-aware evidence:

- if RD uses its result to decide what enters `book.toml`, it is selection data;
- if RD is forbidden to respond to it, it is a one-episode report rather than a promotion mechanism;
- if an independent historical audit is desired, reserve it until the full book construction and all `book.toml` decisions are frozen;
- otherwise use all historical data for Development and describe paper/live forward performance as the genuine post-selection evidence.

Bailey et al. reach a related warning for investment backtests: ordinary holdout can be unreliable, and overfitting must be assessed at the level of the strategy search rather than assumed away by one split. [Bailey et al. (2016)](https://doi.org/10.21314/JCF.2016.322)

## Recommended evidence output

For every Run, retain:

- the frozen Candidate grid, configured Metric, direction, block protocol, and complete trial lineage;
- one continuous causal Candidate path and its state/cost provenance;
- the block-by-Candidate raw Metric matrix and within-block rank matrix;
- mean rank `Q`, deterministic winner, and full-period Metrics;
- local relative-performance plots and the optional expanding-prefix trace;
- synchronized bootstrap protocol and uncertainty, or a precise reason it is unavailable;
- MCS/SPA evidence when its required loss/benchmark assumptions hold;
- an explicit label that Development ranking is in-sample selection, not terminal OOS validation.

The result combines causal portfolio realism with the useful part of the existing blocked ranking: **continuous simulation determines what happened; observational blocks determine where it happened; within-block ranks determine which fixed Candidate was consistently better.**
