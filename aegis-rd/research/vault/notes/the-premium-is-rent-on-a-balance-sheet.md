---
title: The Premium Is Rent on a Balance Sheet
date: 2026-07-25
topic: market-behaviour
status: research-note
aliases:
  - What the behaviour sweep left unfollowed
  - Why the convergent search converged
related:
  - "[[income-must-accrue-not-be-captured]]"
  - "[[the-payer-did-not-leave-the-supply-arrived]]"
  - "[[window-dressing-at-the-regulatory-snapshot]]"
  - "[[what-is-a-strategy]]"
tags:
  - note
  - market-behaviour
  - register
  - negative-result
---

# The Premium Is Rent on a Balance Sheet

> [!abstract] The finding, and the register beneath it
> A day of behaviour research, run three ways - screened by our own constraints, then by
> mechanism family, then fully open - converged on the same answer. Real, well-evidenced,
> durable behaviours exist. Nearly every one of them **sells balance-sheet capacity that
> somebody else is prohibited from holding.** That is not incidental to those premia; it is
> what they are compensation *for*. An unlevered account with no balance sheet to rent is
> trying to sell the one thing it does not have.
>
> This note records the conclusion and then registers everything found and not followed, so
> the next search starts from here rather than repeating it.

## The conclusion

Look at what the mechanisms actually pay for:

| Behaviour | What is being rented |
|---|---|
| Quarter-end window dressing | A repo book held across a reporting date |
| Treasury cash-futures basis | Financing capacity for the position |
| Bank significant risk transfer | Capital against a junior tranche |
| Corporate bond issuance premium | Inventory warehousing |
| Spot-versus-futures crypto wedge | Margin in two segmented venues at once |
| Covered interest parity deviation | A dealer balance sheet across currencies |

In each case the compensation exists **because a rule stops the natural holder from holding**.
The premium is rent on capacity, and the reason it survives competition is that the party best
placed to arbitrage it is the party the rule constrains. That is a genuinely durable limit to
arbitrage - it does not dissolve as capital arrives, because arriving capital is the wrong
kind.

It is also the reason this search could not have ended differently. The durability and the
inaccessibility have the same cause.

One category escapes the pattern, and only one: behaviours where **being small is the
qualifying condition** rather than a handicap. Odd-lot tender priority is the documented
instance, recorded in [[income-must-accrue-not-be-captured]]. A full day of primary-document
searching produced exactly one, worth a few hundred euros a year. That it exists at all is
the more interesting fact; that only one turned up is the sobering one.

> [!warning] Correction, same day: the measurement below does not decide the question
> External verification of the metric (Exa, against primary sources) found that the sign of
> ΔΘ̂ is set by a **scale convention that the code's own docstring misdescribes**, not by the
> data.
>
> `composite_allocator_utility` states it compares "both at the same book vol". It does not:
> the two *legs* are scaled to 10% each, but the blended book's volatility then floats down
> to **7.66%** while the reference (trend alone) stays at **10%**. Θ is a certainty-equivalent
> *growth rate* and is not scale-invariant, so a lower-volatility portfolio scores lower on it
> mechanically. Re-levering both books to a common volatility - the standard convention, per
> Graham-Harvey's GH2, and the one the live allocator actually implements by scaling sleeves
> to `book_vol_target` - **flips the sign**:
>
> | | fixed-weight (as implemented) | vol-matched |
> |---|---|---|
> | daily (n=1889) | **-0.014055** | **+0.008034** |
> | monthly (n=90) | **-0.020225** | **+0.017266** |
>
> The blend's Sharpe is **higher** than trend alone (1.213 against 1.132): the pole does
> improve the book's risk-adjusted quality, and the negative reading comes from it also
> de-risking the book.
>
> **Under every convention the intervals still span zero**, and that is now known to be
> expected rather than informative: O'Connor (2024) finds power of 0.32 for a 0.05 Sharpe
> difference at thirty years and correlation 0.80, and Kazak and Pohlmeier find false-negative
> rates near 80% for certainty-equivalent-difference tests over five to ten years. The test is
> **underpowered by construction**.
>
> Two further defects, both verified against primary sources. The claim that ΔΘ̂ "is the Tasche
> marginal contribution" is a **category error**: Tasche's Proposition 2.2 is proved for a risk
> measure homogeneous of degree 1, and Θ(λr) is approximately λμ - (ρ/2)λ²σ², which is not
> λΘ(r). Only the arithmetic form is borrowed, none of the guarantees. And Tasche's `X - X_i`
> would be `0.6·trend_leg`, where the code uses `1.0·trend_leg` - a second scale deviation.
>
> So the claim below that the negative sign "was not a blending artifact" is **withdrawn**: the
> archived -0.0115 and the -0.0141 here share the same portfolio-level scale mismatch, so they
> corroborate each other's convention rather than the finding. The honest statement is that
> **this measurement cannot currently decide whether the pole earns its seat.** It remains true
> that no positive result has been demonstrated.

> [!success] Measured 2026-07-25: the seat's occupant does not demonstrably earn its seat
> The ΔΘ̂ loader landed (`aegis-rd/scripts/floor_evaluation.py`,
> `load_locked_strategy_returns`), so this is no longer an open obligation. **Any statement
> that the test cannot be run is out of date.**
>
> Both poles, live locked configs, 1,889 common trading days from 2019-01-02 to 2026-06-30,
> at the book's own 60/40 tilt (`convergent_weight` 0.4, `rho` 3.0, `book_vol` 0.10):
>
> - **ΔΘ̂ = -0.014055**
> - **downside correlation = +0.2724**
> - intervals at 21d, 63d and 126d all **span zero**, around [-0.050, +0.029]
> - `earns_its_seat` = **False**
>
> Read it carefully. The honest claim is **not** that the sleeve destroys value; it is that
> after seven and a half years its contribution is **indistinguishable from zero**. It fails
> the bar on both clauses - negative point estimate, and no interval clearing zero - but the
> dominant fact is that the data cannot support a verdict in either direction.
>
> This **corroborates** the -0.0115 recorded in `carry_floor.yaml`'s header on 2026-07-04,
> which came from the superseded implementation that blended raw returns at a fixed weight
> with `leg_volatility_normalization: False`. Re-running through the corrected metric, which
> pins each leg to book vol so the certainty equivalent ranks shape and placement rather than
> scale, moves the estimate from -0.0115 to -0.0141. **The negative sign was not a blending
> artifact.** The positive downside correlation is the co-crash with the trend pole that the
> same header called "fast-crash-limited", now measured independently.
>
> Two caveats. The metric's `DEFAULT_BOOK_VOL` is 0.10 while `book.toml` sets
> `book_vol_target = 0.09`; the metric should take the book's value rather than its own
> default. And reaching this required regenerating both candidate stores - they were schema
> v6 and v7 against a required v8, and only 4 of roughly 278 stores in the tree are current.
> Each config was re-run unlocked and re-locked only after the run reported
> `candidate_count: 1`, which is what proves the grid collapses to the pinned cell and the
> candidate was re-minted rather than re-crowned.

## Register: behaviours found and not followed

Recorded so a future search can start here. None was pursued, and inclusion is not
endorsement - the status column is what matters.

**Well evidenced, mechanism sound**

- **Quarter and year-end dealer balance-sheet window dressing.** Written up separately in
  [[window-dressing-at-the-regulatory-snapshot]]. Bassi, Behn, Grill and Waibel, *Journal of
  Financial Intermediation*, 2024.
- **Spot-versus-futures crypto carry wedge.** A 24/7 asset wrapped in a market-hours vehicle
  with margin segmented from the futures venue; a May 2026 arXiv working paper reports a
  persistent 2.58% annualised wedge, corroborated by CME's own published gap and open-interest
  data. Authors not recorded here - attribute before citing. **This is the closed-window
  friction with a real instance**: the limit to arbitrage is that the wrapper genuinely cannot
  trade when the asset does, which arriving capital cannot relax.
- **Target-date fund contrarian rebalancing.** *Journal of Finance*, 2023; mechanism close to
  definitional, since the mandate *is* the trading rule, and the flow is growing rather than
  being arbitraged. Note the sign: the mandated party is a forced contrarian, so whoever takes
  the other side is buying what rose. **This flow plausibly pays trend-following**, which makes
  it an argument for the sleeve we already run rather than a candidate for a second one.
- **Corporate bond primary-market issuance premium.** Segmented investors; publication status
  and sample unconfirmed.
- **Treasury auction cycle price pressure.** *Review of Financial Studies*, 2013. No obvious
  decay story located, but the sample is old.

**Real but dated, crisis-only, or otherwise qualified**

- **"Dash for cash" monthly payment-cycle pressure.** *RFS* 2020, but the core sample ends
  2013 and post-2018 persistence is unconfirmed.
- **Attention-induced retail trading and reversal.** *Journal of Finance* 2022, sample
  2018-2020. A persistent friction rather than a compelled-flow story.
- **Debt-ceiling bill-supply distortion spilling into corporate credit.** 2024, working paper
  for the corporate-credit leg specifically.
- **LDI-style fire sales.** Rigorous, but explicitly a crisis-state phenomenon.
- **Foreign-ownership-limit price premia.** Mechanism as clean as any here - a legally closed
  arbitrage - but only pre-2018 citations located.
- **Capital-gains lock-in with interest-rate-dependent magnitude.** Only the rate-dependence
  refinement is additive; the base effect is textbook.
- **T+1 settlement reaching the UK and EU on 11 October 2027.** Legislated, dated years ahead,
  compressing FX-funding and securities-lending recall windows. A mandated change with a
  certain date, which is the scarce shape - but no specific behaviour has been attached to it
  yet.
- **Overnight and extended-hours price discovery migration.** NYSE's own Q2 2025 research plus
  a 2026 SSRN working paper.

**Failed our own bar**

- **0DTE dealer-gamma effects on realised volatility.** The literature currently disagrees on
  the *sign*. A mechanism that does not fix a sign is not a behaviour by this vault's standard.
- **Broad-index leveraged ETF rebalancing.** Economically insignificant once capital flows are
  controlled for.

## Two branches that deflated on inspection

**The intermediary single-factor story is contested.** He, Kelly and Manela (*JFE* 2017) found
dealer capital shocks pricing seven asset classes at similar risk prices, and this vault
adopted that as the spine of the convergent seat's economics. Gospodinov and Robotti (*JFE*
2021) re-run the original sample with misspecification-robust inference and the capital
factor's significance disappears in nearly every asset class, with a placebo test flagging an
unrelated industry factor as priced in **39 of 40 cases**. Separately, Adrian, Etula and Muir
(*JF* 2014) and He-Kelly-Manela use reciprocal measures and obtain **opposite-signed** risk
prices; Kargar (*JFE* 2021) resolves this by showing broker-dealers cut leverage 47% in 2008-09
while bank holding companies raised it 72%, i.e. **at least two distinct constrained
intermediary types**, not one factor. Nobody has re-estimated the seven-asset test past
2012-13.

Two further live facts: the eSLR relaxation took effect **1 April 2026**, and limits-to-arbitrage
theory predicts constraint premia compress to the marginal arbitrageur's **cost of capital, not
to zero**.

**Regulated risk transfer is weaker on evidence than on mechanism.** An ECB working paper using
the EU "SME supporting factor" risk-weight discontinuity finds banks select loans for transfer
on **regulatory risk weight rather than economic risk**, with less-capitalised banks using it
most - selection running against the buyer. The Solvency II risk margin is a regulatory formula
rather than a market price, and its cost-of-capital rate is being cut from 6% to 4.75% **by
legislative fiat effective January 2027**, which is the cleanest available demonstration that
these premia are policy dials. Meyricke and Sherris (peer-reviewed) find Solvency II actually
*disincentivises* transferring high-age longevity risk. And the one anti-decay result -
Börger, Freimann and Ruß (*Journal of Risk and Insurance*, 2023), that longevity premia should
*rise* as reinsurer capacity saturates - is a calibrated theoretical model whose precondition
has not occurred: 2024-25 capacity is still expanding, and Cairns et al. (*British Actuarial
Journal*, 2018) document nearly two decades of failure to scale on basis risk and liquidity.

A selection effect worth keeping: of this whole family, exactly one member has a public
multi-decade return series - cat bonds - and that is also the one documented to have decayed.
The only instance we can measure is the only instance we found decaying, and nothing tells us
whether that generalises.

## Open measurement gaps

None of these is closable by further literature search. Each needs original measurement.

- A Dew-Becker-Giglio-style structural-break alpha test on a **deep-out-of-the-money-only
  slice**. Nobody has run it.
- The same test on **any non-US index**. Qiao, Xu, Zhang and Zhou (*JBF* 2024) hold eighteen
  years of twenty-market panel data and ran no break test; their US full-sample average
  straddles the 2012 break and so cannot distinguish the hypotheses.
- **Re-estimation of the He-Kelly-Manela seven-asset cross-section past 2012-13.**
- The **Bassi et al. sample period**, unconfirmed and needed before that paper is cited in
  anything formal.

## Method warnings earned the hard way

**Data-access bias, not economic-importance bias.** The strongest documented behaviours exist
because a research team had a specific data-sharing agreement - confidential ECB repo data,
ANcerno institutional trades, Bank of England gilt records. Mechanisms just as real that never
found a matching dataset are underrepresented for a data reason, not a reality reason.

**Geography.** Every sweep defaulted to English-language, US and European sources. Japanese,
Korean, Chinese, Indian and Gulf mandate structures are almost certainly under-searched.

**Synthetic papers are now in the corpus.** One search surfaced a paper with the shape of a
fabricated or auto-generated article, plausible on a highlights pass. Separately, a sub-agent
on this desk attributed invented numbers to a real paper, caught only because a second agent
verified against the primary source. Anything post-2023 needs a venue check, and any
load-bearing number needs to be read in the source rather than in a summary.

**Parallel searches of one corpus are one sample.** Twelve agreeing hunts looked like
robustness and were shared selection. The only search that changed the answer used a different
source class entirely - primary filings rather than papers.

## Making the accepted occupant better

The seat is filled by a beta allocation, not a strategy. "Smarter" therefore means cheaper and
better diversified, never better timed - a timing signal turns it back into a strategy and
re-opens every question this note closes. In order:

1. **Remove the currency and financing tax.** The sleeve holds USD legs converted to EUR while
   positive EUR cash does not offset a USD debit, so it pays USD margin interest and conversion
   on every rebalance. Natively-EUR alternatives are **confirmed against the IBKR gateway**
   (2026-07-25, `reqContractDetails`, all listings):
   - `EUCL` - iShares EUR AAA CLO, Xetra (IBIS2), EUR
   - `PCL0` - Palmer Square EUR CLO Senior Debt UCITS, Xetra (IBIS2), EUR
   - `IMBE` - iShares US MBS **EUR-hedged accumulating**, Amsterdam (AEB), EUR
   Contract details prove the instrument is listed, not that this account may trade it;
   permissions, market data and PRIIPs KID availability are separate gates and were not
   tested.

> [!failure] AT1 does not serve this purpose, and one earlier claim was fabricated
> An agent search reported "ATEA - AT1 CoCo, 0.39% TER" and it was repeated on this desk
> before any broker check. **`ATEA` is ATEA ASA, a Norwegian IT services company**, listed on
> Oslo in NOK. The ticker was wrong, not merely imprecise.
>
> Every AT1 contingent-convertible ETF the gateway does list is **USD-denominated**: `AT1` and
> `AT1D` (Invesco USD AT1 Capital Bond UCITS) and `CCBO`/`COCB` (WisdomTree AT1 CoCo UCITS
> USD). Their EUR lines on Borsa Italiana are EUR *trading* listings of USD funds, so the
> dollar exposure survives - which defeats the reason AT1 was raised. `AT1E` returns no
> security definition. Note also that `COCO` is WT COCOA, a cocoa commodity ETF.
>
> This is the failure mode warned about under "Method warnings" in this same note,
> reproduced by the author of the warning. Ticker-level claims from agent search are not
> evidence; the gateway is. Probe kept at `_prototyping/at1_access/probe.py`.
2. **Recalibrate the drift band's `destination_fraction` toward the fixed-fee optimum**, which
   is what a EUR 1.25 per-order floor implies.
3. **Test whether a second exposure diversifies or merely doubles the pole.** Real question,
   not obviously yes: `carry-is-not-one-premium` warns that stacked carry mechanisms concentrate
   one pole rather than adding an independent one. This is what ΔΘ̂ is for.
4. **Richness gating is off the table until the §5.5 argument is written.** The role article
   recommends sourcing the credit signal from spread richness rather than level; the convergent
   brief warns that a gate deciding whether a premium is available sits close to the
   return-forecasting line and owes an explicit argument. That argument does not exist yet.
5. **The sleeve already volatility-targets, and the effect is window-dependent.** Measured,
   not asserted - see the callout below. The earlier advice here read "do not
   volatility-target it", which was wrong on both counts: the book already does, and the
   consequence is not the one the role article names.

> [!info] Measured: the existing vol target is a crash-only mute, and that is not obviously bad
> The book volatility-targets at **two** levels: the allocator
> (`aegis-trader/aegis_trader/domain/allocator.py:158`, `risk_share * book_vol_target /
> vol`) and inside the sleeve, where `demeter.carry_mix` computes
> `exposure = min(vol_target / sigma_book * richness**carry_gain, 1.0)` with `vol_target`
> pinned at 0.10 by mandate. `sigma_book` is a **comonotone** sum with no diversification
> credit, so it overstates true book vol and the term binds more readily than real portfolio
> risk warrants.
>
> Replicating the live configuration (SDHY + LQDH, `defensive=1.0`, satellites zero, `lean`
> pinned to 1.0 because the live candidate's `carry_gain` is unknown) on dividend-adjusted
> total return, 2013-10 to 2026-07:
>
> - The term is **inert on 96.4% of days**. Every binding day falls in a stress year - 2020,
>   2022 and 2025 at a 21-day window; **all** of them in 2020 at 63 days. It is a crash-only
>   mechanism by construction, exactly as the shape of the `min(..., 1.0)` cap implies.
> - At **21 days** the mute *improves* Sharpe (+0.839 against +0.736) and max drawdown
>   (-13.6% against -20.1%) while leaving skew **essentially untouched** (-1.750 against
>   -1.736). So the role article's specific worry - that the Sharpe gain is bought by shedding
>   the negative skew the sleeve is paid for - is **not** what happens here. The gain comes
>   from cutting variance, and the crash exposure survives.
> - At **63 days** the same mute delivers no Sharpe gain at all (+0.699 against +0.701) and
>   degrades skew badly (-3.109 against -1.733). The window choice, not the mute, decides
>   whether this is worth having.
> - Through the full COVID episode the muted sleeve **lost more** (-6.8% against -4.6%): it
>   saved roughly 6 points in the crash leg and gave back 11 in the rebound (+7.5% against
>   +18.9%). It buys a smoother path and pays for it in outcome, in the one episode where it
>   activates.
>
> **Weight this carefully. It is effectively N=1**: 85 of 123 binding days are 2020, so every
> conclusion about whether the mute helps rests on a single crisis. Two legs only, no FX or
> AT1 satellite, USD returns with no EUR conversion, and **no costs modelled** - and the mute
> trades precisely when spreads are widest, against a EUR 1.25 per-order floor.
>
> One methodological note worth keeping. The first run of this test used unadjusted prices on
> distributing credit ETFs, which omits the coupon - the entire return - and reported the
> **opposite** conclusion (mute hurts Sharpe, -0.135 against -0.073). That result would have
> been reported confidently had the loader's `auto_adjust=False` not been checked. On an
> income sleeve, price return is not a rough proxy for total return; it inverts the answer.
> Probe kept at `_prototyping/voltarget_bind/probe.py`.

## Limitations

This register is a summary of agent research, not of primary reading. Every citation here
should be verified against the source before it is used in a paper - several are flagged as
unconfirmed above and at least one attribution is missing entirely.

The central claim - that these premia are rent on balance-sheet capacity - is a synthesis
across the day's findings, not a result anyone published. It is offered as the pattern that
explains why three differently-designed searches converged, and it should be attacked rather
than assumed.
