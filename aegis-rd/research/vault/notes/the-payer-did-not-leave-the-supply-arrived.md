---
title: The Payer Did Not Leave, the Supply Arrived
date: 2026-07-25
topic: variance-risk-premium
status: research-finding
aliases:
  - The VRP reconciliation
  - Why the variance premium compressed
related:
  - "[[income-must-accrue-not-be-captured]]"
  - "[[carry-as-the-short-gamma-income-pole]]"
  - "[[the-skew-is-the-product]]"
tags:
  - note
  - variance-risk-premium
  - demeter
  - correction
---

# The Payer Did Not Leave, the Supply Arrived

> [!abstract] Correction
> Two live documents state that the S&P 500 variance risk premium collapsed because dealers
> stopped being reliably short gamma - the payer left. That reading does not survive contact
> with the current literature. The break date moved between the authors' own drafts, every
> structural explanation offered for it predicts the **wrong sign**, and the one mechanism
> that predicts the right sign is not dealer withdrawal at all: a wave of new volatility
> *sellers* arrived. The premium compressed because supply grew, which is a materially
> different fact with a materially different consequence for anyone thinking of selling
> variance.

## Three objects, routinely conflated

Most of the apparent contradiction in this literature dissolves once three distinct
measurements are kept apart:

1. the raw implied-minus-realized variance gap;
2. the risk-adjusted alpha, which is what Dew-Becker and Giglio actually test;
3. the deep-tail or crash-conditional exposure.

Terstegge ("Intermediary Option Pricing", working paper, CBOE data 2011-2023) reads as a
rebuttal of Dew-Becker and Giglio and is not one. His own *local* dealer gamma is flat too.
His contribution is that scenario gamma evaluated at a large downward move stays strongly
negative, concentrated in deep out-of-the-money puts, across the same window the alpha test
calls zero.

The reconciliation is arithmetic: **a near-zero average alpha is entirely consistent with a
large loss concentrated in rare tail states.** Zero alpha does not mean no premium. It means
the seller is being paid about fairly for bearing crash risk. That is a legitimate exposure
and it is not an edge, which is exactly the distinction [[what-is-a-strategy]] draws between
compensation for risk and someone else's systematic behaviour.

## Why the received story is shaky

**The break date moved.** The November 2023 NBER version dated it near 2010; the current
draft says August 2012. Same authors, same project, two-year shift. The paper remains a
working paper, not peer reviewed.

**And every structural explanation points the wrong way.** Tighter dealer capital under
Volcker and Basel III should make dealers demand *more* compensation, not less. Volmageddon
(February 2018) reduced short-volatility ETP supply, which should *raise* premia. Zero-day
option growth postdates the break by most of a decade and cannot have caused it - and BIS
explicitly tested and rejected the popular claim that 0DTE broke the VIX. The only
explanation evidenced from inside the paper itself is that dealer net gamma shifted, which
restates the observation rather than explaining it.

## The mechanism with the right sign

Option-selling *vehicles* grew large enough for their hedging flow to suppress volatility.
Four sources, different datasets, same conclusion: BIS Quarterly Review (March 2024,
official); Calvet, Célérier, Liao and Vallée on roughly USD 1.3 trillion of structured
products; Park and Kurucak independently on N-PORT mutual fund data; and the Chicago Fed
variance-premium paper. Covered-call ETFs and retail structured notes are now a standing
supply of short volatility that did not exist at this scale before.

New sellers arrived. Supply grew. The premium compressed. The sign works, and no other
candidate explanation does.

> [!caution] One in-house result cuts against this, weakly
> A throwaway cross-market prototype (2026-07-25, `_prototyping/global_variance_premium/`)
> split the raw gap at August 2012 across every market with free pre-2012 volatility-index
> history. Australia flattened hardest and cleanest in the panel and is the only market whose
> change is statistically distinguishable from the US - in the direction of **more**
> compression. Australia's option-income vehicle market is far smaller than America's, so a
> supply-driven story predicts the opposite ordering.
>
> Weight it lightly. The panel is four markets; the measure is the raw gap rather than alpha;
> two markets have short, crisis-dominated pre-periods; and the US answer is itself unstable
> across US benchmarks (S&P 500 p=0.088, Nasdaq p=0.0025, Dow p=0.82 on one identical
> specification), which means the comparison lacks a stable reference point. Vehicle assets
> under management were out of scope and were not measured.
>
> It does not refute the supply mechanism. It does mean the mechanism is not yet confirmed by
> anything on this desk, and the "no other candidate explanation does" claim above should be
> read as "none was found", not as "none exists".

The European instance is documented specifically: retail structured-product issuance
compresses implied volatility on Euro Stoxx 50 around 60-70% moneyness, with the 60% strike
estimated about two volatility points below its unaffected level.

## What this changes

**For anyone considering selling variance**, the consequence is worse than the received
story, not better. "The premium mysteriously died" invites the hope that it might return.
"A wave of new sellers arrived and compressed it" says the crowded side is the selling side,
and that joining means being the marginal entrant into a documented supply glut.

**For the roster**, it sharpens rather than removes the convergent seat's rationale. Fairly
priced risk-bearing still pays in ordinary markets and still places its loss away from where
a trend sleeve fails. It is an allocation, not an alpha, and it should be labelled and sized
as one.

**For [[budgeting-convexity]] and [[research/convergent-engine/_brief|the convergent brief]]**,
both of which carry the payer-left claim: the citation is a working paper whose break date
moved, whose mechanism is unexplained by the available structural candidates, and whose most
plausible cause is the opposite of the one stated. Do not let it harden into a settled
premise.

## The open measurement gap

Nobody has run a Dew-Becker-Giglio-style structural-break alpha test on either a
deep-out-of-the-money-only slice or any non-US index. Both are publishable-grade gaps.

The second matters most for us, and it has now been chased far enough to state precisely.

Qiao, Xu, Zhang and Zhou (*Journal of Banking & Finance*, 2024, January 2006 to December
2023, nine emerging and eleven developed markets) is the one published paper with a current
sample and wide coverage. It cannot settle the question, for two reasons worth recording so
nobody re-opens it hopefully.

**Different object.** They measure the raw implied-minus-*expected*-realized gap, where the
expected-realized leg is itself a statistical forecast in the Bekaert-Hoerova style. That is
not a delta-hedged alpha. Their positive readings and Dew-Becker and Giglio's zero alpha were
never in contradiction.

**And no break test.** They ran none, in eighteen years of twenty-market panel data; the only
temporal split is in-sample against out-of-sample for forecast validation. Their US
full-sample average (8.67) sits dead centre of the developed range, but that average straddles
both sides of the 2012 break, so it is **fully consistent with "high before 2012, flat
since."** A full-sample mean cannot separate the two hypotheses.

So the sharper open question is: rerun their exact twenty-market panel with a 2012 split and
see whether the US uniquely flattens. If it does, Dew-Becker and Giglio means "something
specific happened to the S&P 500" rather than "the variance premium died" - different claims
with different consequences.

Two further cautions on the non-US evidence. China's volatility index only begins in February
2015, so the market-cap-weighted emerging aggregate is missing its heaviest constituent
through the entire 2008 crisis, and several other indices are spliced mid-sample - disclosed
in a table footnote rather than discussed as a limitation. And a separate published paper on
SSE 50 ETF options (2016-2021) reports a *negative* China variance premium, directly
conflicting with Qiao et al.'s positive figure. That discrepancy is unresolved.

Current European evidence is thinner still: the nearest study runs November 2006 to October
2017 and should be read as background, not as evidence about today.

## Limitations

The four sources behind the supply mechanism include two working papers and one official
BIS review; the structured-product magnitude figures are estimates from those papers rather
than measured premia. The reconciliation in the first section is an argument about what the
sources measure, not a new measurement. And the Qiao et al. result is named here as an open
question precisely because nobody on this desk has read it.
