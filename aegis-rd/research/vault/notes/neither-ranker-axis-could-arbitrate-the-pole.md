---
title: Neither Ranker Axis Could Arbitrate the Pole
date: 2026-07-27
topic: convergent-seat
status: measurement
related:
  - "[[what-makes-a-convergent-sleeve-an-income-engine]]"
  - "[[the-european-variance-premium-did-not-decay]]"
  - "[[the-skew-is-the-product]]"
tags:
  - note
  - demeter
  - measurement
  - methodology
---

# Neither Ranker Axis Could Arbitrate the Pole

> [!abstract] Result
> Three convergent candidates were scored against the properly locked trend pole through
> `evaluate_allocator_contribution`. All three returned `earns_its_seat = False` with
> `delta_theta` intervals straddling zero at every block length, and **the exercise cannot
> rank them**, because both of the ranker's axes are compromised in ways the codebase
> already documents. This note records the numbers and the reason they do not decide
> anything, so the next session does not re-derive them.

## What was measured

Locked `atalanta/trend_floor.yaml` (lock `20260724T233648786783Z`, candidate
`cand_71a2f9e03123ec88077f132e87a39055`, 1,955 observations) loaded through
`scripts/floor_evaluation.load_locked_strategy_returns`, paired via
`evaluate_allocator_contribution` at rho 3 and convergent weight 0.40.

| candidate | n | `delta_theta` | `downside_correlation` | earns seat |
| --- | ---: | ---: | ---: | --- |
| incumbent `carry_floor` | 1952 | -0.0156 | +0.2533 | False |
| LVO short, always on | 1903 | -0.0274 | +0.2187 | False |
| LVO short, contango-gated | 1903 | -0.0050 | +0.0167 | False |

Every interval contains zero: the incumbent spans [-0.0494, +0.0179] at block 1 and
[-0.0498, +0.0190] at block 6; the gated short spans [-0.0444, +0.0335] and [-0.0439,
+0.0327].

## Why `delta_theta`'s sign says nothing here

`_blended_book`'s own docstring is explicit: the construction is **not** a matched-risk
comparison and "its sign should not be read as one". Because the MPPM is a
certainty-equivalent growth *rate* rather than a scale-invariant score, part of
`delta_theta` is simply the blend sitting at a lower volatility than the reference, and
**on the live pair that component carries the sign: -0.013 as specified, +0.008 matched.**

The incumbent's -0.0156 measured here reproduces that documented -0.013. So the reading
"the incumbent subtracts certainty equivalent" is precisely the inference the metric
forbids, and at matched volatility the same pair reads positive. `aegis-rd-600y` proposed
fixing this and was closed WONTFIX against the governing spec.

## Why the scale-free axis cannot arbitrate either

The docstring routes the placement question to `downside_correlation`, which is scale-free.
On that axis the separation looks decisive: incumbent +0.2533 against the gated short's
+0.0167, a factor of fifteen.

But `aegis-rd-6uph` is open precisely because that guard is biased by microstructure at
daily frequency, and the bias is neither small nor uniform. Measured leg-pair correlations
on the same instruments, daily to weekly to monthly:

| pair | daily | weekly | monthly |
| --- | ---: | ---: | ---: |
| incumbent SDHY-LQDH | +0.774 | +0.869 | +0.903 |
| challenger STHE-IRCP | +0.430 | +0.763 | +0.801 |
| challenger IHYG-IRCP | +0.753 | +0.863 | +0.882 |

Daily readings understate co-movement everywhere, by different amounts per pair. A guard
read at daily frequency therefore flatters whichever candidate happens to be marked
noisiest, which is the opposite of what it is hired to detect.

## The finding

**The seat has no usable ranker for the placement question right now.** One axis is
scale-contaminated by design and documented as unreadable; the other is horizon-biased and
already filed. Any instrument comparison run through this pairing tonight was unrankable
before it started, which is the real reason a session spent on four candidate expressions
produced no ordering among them.

That makes `aegis-rd-6uph` the blocking work, not an instrument search. Until the guard is
evaluated at an aggregated horizon, a new convergent candidate cannot be shown to beat the
one in the book, and the incumbent cannot be shown to be failing either.

## What is safe to carry forward

- The pairing harness works end to end and the lock resolves correctly. The numbers above
  are reproducible; it is their interpretation that is blocked.
- `convergent_income_utility` on standalone streams is not affected by the blend-scale
  caveat, and it separated the LVO variants sharply: +0.2677 gated, **-0.0759 always-on**,
  -0.5048 for the long ETF. The always-on short destroys certainty equivalent despite a
  +13.6%/yr CAGR, which is the ranker correctly pricing an 84% drawdown that hand-picked
  statistics missed.
- The gated short's concavity is thin: quarterly skew -0.14 against the always-on -1.10.
  Per [[the-skew-is-the-product]] that is the good being sold, so the gate buys
  survivability with the product. Whether that trade is worth making is exactly the
  question the blocked ranker would have answered.
