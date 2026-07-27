---
title: "Convergent Engine - implementation state, NOT paper content"
date: 2026-07-26
tags:
  - implementation-state
  - not-paper-content
---

# Implementation state

> [!danger] This file is not paper content and the drafting stage must not draw on it
> The paper is **theoretical**: it argues the convergent seat is a portfolio role, and it reasons over
> market behaviours. Everything below is the state of **this desk's codebase and one desk's measured
> result**. None of it belongs in the argument.
>
> It is retained because it was established at real cost during Stage 4 and because it is the honest
> record of what the pipeline found, not because the paper needs it.

## Why it was removed rather than fenced

D7 holds that compensation adequacy is **unverifiable on realised returns**, so the paper admits on
ex-ante rationale and never claims verification. A paper resting on that epistemics **cannot coherently
report a realised-return measurement as evidence**, however carefully fenced. Confining the figure to one
paragraph shrank the incoherence rather than removing it.

The same reasoning removes the codebase findings. Whether `convergent.py` exposes a rescaling statistic,
whether an episode-level drawdown classifier exists, and which of two figures our code reproduces are
facts about **our repository**. A theoretical article states what would have to be measured and what each
outcome would mean; it does not inventory our functions.

## What the paper says instead

§8 specifies the ranking test as **theory**: the metric, the verdict structure, and what each outcome
would mean. It reports no figure, names no call path, and makes no claim about what is or is not currently
computable here. The execution record lives in this file, in `bd`, and in the run diaries.

---

## Removed from the plan, verbatim

### D8. The measured ΔΘ̂ result enters as one fenced paragraph in §8, and nowhere else

**The premise this pipeline started from is stale.** The ΔΘ̂ loader landed
(`aegis-rd/scripts/floor_evaluation.py`, `load_locked_strategy_returns`, `aegis-rd-n77e`) and the test has
been run. Any statement that it cannot be run is out of date. What survives from the intake constraint is
narrower and still binding: **never imply more than was found.**

The result, on both live locked poles, 1,889 common trading days from 2019-01-02 to 2026-06-30, at the
book's own tilt (`convergent_weight` 0.4, `rho` 3.0, `book_vol` 0.10):

- **ΔΘ̂ = -0.014055**, downside correlation **+0.2724**
- intervals at 21, 63 and 126 days **all span zero**, around [-0.050, +0.029]
- `earns_its_seat` = **False**
- corroborates the -0.0115 archived from a superseded implementation, so the sign is not a blending
  artifact

**Why it gets one paragraph and not a section.** The test applied is: *does the change survive deleting the
number?* It does not. This is one candidate (`carry_floor`) on one universe over one window at one book
tilt, and under D4 a single candidate's result cannot speak to the role. So it is **not a finding about
this paper's subject.** It is evidence about the *method's reach*: the test is computable, and on a live
candidate over seven and a half years it returns **indeterminate**. That is the honest reading recorded
against the issue, and it vindicates D7 using this desk's own data rather than Burnside et al.'s. It must
not reshape D3, D5, or D4's substance. The theory does not move on one candidate.

**RM-4 resolved: the number is unconditioned, and the baseline is confirmed.** `composite_allocator_utility`
computes the baseline term as `_blended_book(trend_daily, trend_daily, convergent_weight=0.0)`, so it is the
trend leg alone scaled to book vol. **Neither the Target nor the Expansion tier appears in either term** -
confirmed by grepping both locked configs, zero matches. The prospective warning that drafting would lose
this has been pre-empted: state the baseline contents explicitly wherever the figure appears.

**Segment-conditioning is not computable today**, so the figure must be reported as a full-sample
unconditioned result pending a re-run rather than as satisfying `_synthesis.md` §3.5's precondition.
`downside_correlation` conditions only on a daily-magnitude quantile, not on episode or duration;
`EquityCurve.drawdown_curve()` returns a continuous level with no episode boundaries; no episode-level
fast-versus-protracted classifier exists in `aegis_research`; and vectorbtpro's drawdown primitives are not
wired in even unused. That is a gap in this codebase rather than a claim about what vectorbtpro can do.

**Two caveats travel with the number and may not be separated from it.**

1. **The Tasche scope condition.** ΔΘ̂ borrows the with-minus-without arithmetic and **not** Tasche's
   theorems: his Proposition 2.2 requires a risk measure homogeneous of degree 1 and Θ is not homogeneous,
   so none of the Euler/RORAC guarantees transfer. The source article was corrected for this
   (`aegis-rd-v1k7`, commit `110507ad`); the paper must not reinherit the stronger claim.
2. **The smoothing question is measured and closed for this sleeve, and it strengthens the reading.**
   Getmansky, Lo and Makarov show smoothed marks bias contemporaneous correlations **toward zero**, which
   would hide co-crashing from the very statistic hired to catch it. That profile has now been estimated
   (commit `03ece3b7`, `convergent_smoothing_index`, one-month horizon): **both live poles read xi =
   1.0000, at the no-smoothing ceiling.** First-order autocorrelation is *negative* (-0.104 convergent,
   -0.024 trend), which is bid-ask bounce in an exchange-traded mark and the opposite sign from staleness;
   Sharpe inflation is 1.0000; and the lagged downside correlations alternate in sign rather than decaying
   positively, so no co-movement is displaced into lags. **The guard is real rather than an artifact**, so
   the measurement is more trustworthy than a caveat would imply, not less.

   The asymmetry claim survives only where it was never tested, and it is **venue-specific** in the same
   way D1's crash share is. `_synthesis.md` Gap 5 records that no de-smoothed ILS series exists at any
   frequency, and cat-bond funds are OTC-marked rather than exchange-traded. The role article's own
   pre-registered expectation was that an exchange-traded NAV should smooth *less* than the OTC-marked
   funds in the literature, and that expectation held. So: **closed for this sleeve, still open for ILS**,
   where de-smoothing could only raise crisis co-movement above the reported 0.29 and therefore only
   weaken the placement case.

> [!bug] Corrected after the Stage 2.5 re-run, and it was the orchestrator's error
> D8 originally asserted that the smoothing profile was "unestimated" and that +0.2724 "may understate the
> true co-crash." Both were false at the time of writing: `03ece3b7` landed at 03:27:08 and this file was
> saved at 03:30:32, three minutes later. The source commit states plainly that "the caveat this session
> attached to it is withdrawn." The gate blocked on this, correctly, and it sat inside the one part of the
> file that reports numbers.
>
> **Standing lesson, not a one-off.** This is the second finding of the same shape, after the ΔΘ̂ loader
> premise. The vault is being committed to by another session while this plan is written, so a plan
> artifact goes stale against a moving repo. Anything in this file asserting that a measurement does not
> exist must be re-checked against `git log` and `bd` immediately before drafting, not trusted from when it
> was written.

> [!success] RM-9 resolved: quote +0.2724 only. **+0.253 has no call path in the repository.**
> My earlier hypothesis here, that the two figures were the same guard at different horizons, **was
> wrong.** `downside_correlation` at `convergent.py:421` takes only `(convergent_daily, trend_daily, *,
> quantile)`. **There is no horizon or lag parameter and there never has been**, across the function's whole
> git history, so there is no horizon for the figures to differ on.
>
> **+0.2724 is fully traceable**: `downside_correlation` called from `evaluate_allocator_contribution`
> (line 665) with defaults, fed by `load_locked_strategy_returns` on `atalanta/trend_floor.yaml` plus
> `demeter/carry_floor.yaml`, 1,889 common days, commit `bf8ac1ee`, matching `bd show aegis-rd-n77e`.
>
> **+0.253 is not reproducible from committed code.** Commit `03ece3b7`'s only code addition is
> `_convergent_smoothing_index`, a single-stream variance-ratio diagnostic that returns xi = 1.0000 and is
> not a correlation at all. That commit's message also reports "lagged downside correlations (-0.125,
> +0.159, -0.096)", and no function in the repository computes a lagged version of this guard. Since
> `downside_correlation` is deterministic, the same call on the same data must return 0.2724.
>
> **The paper quotes +0.2724 and never +0.253.** The smoothing measurement itself (xi = 1.0000, negative
> autocorrelation, no lag displacement) stands and is separately verified; it is the correlation figure in
> that commit's *message* that has no source.

> [!danger] Outside this paper's scope, and the more serious half of the finding
> The unreproducible +0.253 is **live**, not archival. `runs/demeter/2026-07-25.md:73` uses "the
> incumbent's +0.253" as a threshold inside a KEEP / ITERATE / KILL gate condition, in a diary written
> after the loader result existed. A research decision is being gated on a number that no committed code
> produces. That is a Lu-taxonomy Mode 3 instance (hallucinated experimental result) which has propagated
> from a commit message into a decision rule. **It is another session's artifact and not this paper's to
> fix**, but it must not be inherited: any figure this paper takes from that diary needs its own call path
> confirmed first.

**Consequence for §8's shape.** It is no longer a pure pre-registration, because a test already run cannot
be pre-registered. §8 reports the measured instance, then pre-registers what would move it **off
indeterminate** - which is the only pre-registration still available and the more useful one.


---

## Codebase findings from Stage 4, recorded and not carried into the paper

- **RM-9.** `+0.253` has no reproducible call path. `downside_correlation`
  (`metrics/custom/convergent.py:421`) takes only `(convergent_daily, trend_daily, *, quantile)`, has no
  horizon or lag parameter across its full history, and is the only function computing this guard. The
  reproducible value is `+0.2724`. `+0.253` originates in commit `03ece3b7`'s message, whose only code
  addition returns xi = 1.0000 and is not a correlation. Filed and closed as `aegis-rd-kfgj`; the live
  gate threshold in `runs/demeter/2026-07-25.md` was corrected.
- **RM-4.** Segment-conditioned contribution is not computable here: no episode-level
  fast-versus-protracted classifier exists, `drawdown_curve()` gives a continuous level with no episode
  boundaries, and vectorbtpro's drawdown primitives are not wired in. The baseline term is
  `_blended_book(trend_daily, trend_daily, convergent_weight=0.0)`, the trend leg alone, with neither
  Target nor Expansion in either term. Filed and closed as `aegis-rd-coj7`.
- **RM-7.** No statistic exists that rescales the responder leg to a fixed risk budget, so
  *role redundant* and *seat earned* cannot be discriminated on this codebase. Every weight parameter
  scales the convergent leg only.
- **The smoothing measurement stands**: xi = 1.0000 both poles, first-order autocorrelation -0.104 and
  -0.024, bid-ask bounce rather than staleness. Only the correlation figures in `03ece3b7`'s message lack
  a source.
