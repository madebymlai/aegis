---
title: Income Must Accrue, Not Be Captured
date: 2026-07-24
topic: strategy-design
status: research-decision
aliases:
  - The accrual-versus-capture screen
  - Why the EUR 5,000 convergent seat stays empty
related:
  - "[[what-is-a-strategy]]"
  - "[[accessible-ordinary-market-income-after-an-open-search]]"
  - "[[public-filings-special-situations-as-atalantas-pair]]"
  - "[[what-makes-a-convergent-sleeve-an-income-engine]]"
  - "[[short-horizon-reversal-in-small-cross-sections]]"
tags:
  - note
  - demeter
  - strategy-design
  - negative-result
---

# Income Must Accrue, Not Be Captured

> [!abstract] Decision
> A day of open search across twelve parallel hunts closed every remaining convergent candidate for
> the EUR 5,000 book and produced one reusable screen: **the sleeve's drift must accrue from holding,
> never be captured by trading.** Where the return is a statistical tendency, it must be traded into
> existence, and our execution costs sit above the tendency. This single criterion explains the whole
> graveyard, which had accumulated four separate diagnoses for one disease.
>
> The search independently re-derived [[accessible-ordinary-market-income-after-an-open-search]]
> (2026-07-17) and did not overturn it. It adds three durable structural findings, verified size
> thresholds, and three corrections to claims held elsewhere in the vault.

## The screen

The seat's job, from [[what-makes-a-convergent-sleeve-an-income-engine]], is positive drift in
ordinary markets with the loss placed where the trend pole does not also fail. Trend fails in chop,
so the seat should earn in chop.

Something that earns in chop and loses in sustained trends is structurally short the trend, which
is the liquidity provider's position. But **the liquidity provider's income is the bid-ask spread**,
not the reversion. The reversion only lets them exit flat.

That diagnoses the 2026-06-13 kill exactly. Those runs had the placement right - chop tercile +0.6
to +2.1%/mo, trend tercile -1.3 to -2.6%/mo, eff-slope t of -2.3 to -4.3 - and negative drift,
because we were a price taker. We took the liquidity provider's risk and paid their income to
someone else. That is a **sign inversion**, not a cost problem, so no drift-band width or turnover
control can repair it.

Generalised: if realising an effect requires transacting, we pay the spread plus a EUR 1.25 floor
on both sides. At EUR 2,450 that floor alone is roughly 5bp per side on a full-sleeve order and far
worse on anything smaller.

Two independent results sharpen the reversion case specifically. Hudson, McGroarty and Urquhart
(*Finance Research Letters*, 2017) find mean-reversion rules profitable at 5-minute bars and
**negative at 30-minute and slower** - so the edge is a microstructure phenomenon living at a
frequency where capture costs dominate absolutely, which is the accrual argument restated in the
frequency domain. And Martin and Schöneborn (*Risk*, 2011) derive the optimal no-trade buffer as
scaling with the cube root of transaction cost, while noting it reduces cost bleed and **does not
manufacture edge that was not there pre-cost**. Our drift bands are the right instrument for a
positive gross signal and cannot repair a negative one.

> [!caution] The chop-versus-trend complementarity is not clean at the fast end
> "Trend loses in chop, so the seat should earn in chop" holds for quiet chop and for grinding
> sustained trends. It breaks for **fast volatility spikes**: a short-convexity sleeve's real killer
> is spike speed and magnitude rather than direction, and that is also trend-following's worst
> environment - February 2018, SVB, and the August 2024 carry unwind are the cited episodes. The two
> poles can therefore fail together in the fastest events rather than trading off. Any candidate
> admitted on loss-placement grounds owes a check on this specific state, not just on the trend
> tercile.

| Killed candidate | Drift source | Outcome |
|---|---|---|
| Short-horizon reversal | statistical, captured by trading | negative drift, twice |
| ETF residual cluster reversal | statistical, captured by trading | +1.02% gross over five years, break-even 1.2bp |
| Calendar and index-rebalance effects | statistical, captured by trading | dead or below the cost floor |
| Merger arb, fallen angels | event, captured by trading | reachable wrapper sits on the forced side |

Carry, credit spread and received option premium accrue whether or not we trade. Those survive a
high cost floor structurally rather than by tuning.

**The screen does not license holdings.** [[what-is-a-strategy]] is the binding constraint: a
constant exposure qualifies only when the payer is named, the sizing is specified, and the premium's
existence is falsifiable. Accrual is necessary, not sufficient.

## Three structural findings

**Retail liquidity provision is closed by infrastructure, at any size.** IBKR blocks two-sided
quoting at the order-system level. This is independent of capital, so it never reopens with NAV. The
"earn in chop" half of the seat's job therefore cannot be met by supplying immediacy, which
permanently closes reversal and every market-making variant. Reported by practitioner sources and
not independently verified against IBKR documentation, so confirm before relying on it in writing.

**A rules-based wrapper puts you on the mandated side by construction.** Observed four times:

- Fallen angels - the ICE index rebalances monthly on a published cutoff, so the ETF is the forced
  buyer. Absorbing the flow needs the bonds.
- Corporate bond month-end rebalancing - Dick-Nielsen and Rossi (sample 2002-2013) state that index
  trackers are the forced sellers and dealers the compensated providers, with dealer returns "not
  replicable by other investors in the economy." A retail holder of a corporate bond index ETF is
  one of the tracking-error-minimising funds that literature describes.
- ETF creation and redemption - retail cannot be an authorised participant.
- Dual-listed US/UK ETF pairs - the effect held through 2019; the US leg is a non-KID US-domiciled
  fund, blocked for EU retail.

Buying a rules-based wrapper makes you the rule-follower. Being the absorber requires discretion,
discretion requires direct instruments, and direct instruments carry the notional walls below. This
is why the public-filings family survived where everything else died: investment trust shares and
SPAC common are equity-like, with no denomination floor.

**Two kinds of wall, and only one has a number.** A *size wall* (contract notional, commission
floor) dissolves mechanically as NAV grows. A *structural wall* (proportional spread erosion,
eligibility rules, infrastructure prohibitions, collision with an existing sleeve) does not dissolve
at any size. Sorting candidates by wall type is more decision-useful than any individual threshold,
because a structural wall should be recorded as closed so nobody revisits it at a larger NAV.

## Verified thresholds

Sleeve budget is 0.28 x 1.75 x NAV. The reopening figures assume a position at 25% of sleeve budget,
since `SLEEVE_GROSS_LIMIT` is enforced fail-closed with no headroom at 100% and a one-position sleeve
is not a sleeve.

| Candidate | Wall | Reopens at |
|---|---|---|
| Futures as an asset class | size | NAV ~40,000-50,000, a step change rather than gradual |
| Eurex EURO STOXX 50 dividend futures (EUR 100/index point, verified) | size | NAV ~140,000 (bare fit ~35,000) |
| Diversified futures option-selling book | size | NAV ~27,000 (practitioner folk figure, unverified) |
| One EUR 100,000-denominated corporate bond | size | NAV ~816,000 |
| FX carry, spot and futures both | structural | never - proportional spread and financing erosion |
| Retail liquidity provision | structural | never - order-system prohibition |
| Put-write and short VSTOXX | structural | never - collides with the tail sleeve at any size |

Direct EUR corporate bonds are gated by the EU Prospectus Regulation, which exempts bonds of
EUR 100,000+ denomination from retail prospectus rules. Boerse Stuttgart data (January 2024) shows
86% of listed corporate bonds are untradable by retail on that basis. Options show no comparable NAV
gate at IBIE, and listed options and futures are not PRIIPs-blocked; dispersion trading therefore
fails on leg count rather than access, and reopens with size into a premium that is itself
contested.

## Corrections to claims held elsewhere

**SPAC cash redemptions has closed on breadth.** One of the three sub-books in
[[public-filings-special-situations-as-atalantas-pair]]. Total SPAC trust assets fell roughly 90%
from about USD 187.5bn in 2022-23 to about USD 20bn by June 2025, and around 25% of live deals now
trade at a premium to trust. This is a harder kill than that note's stated reason (published returns
coming from IPO units and warrants rather than secondary common-only trades) and should be recorded
against it.

**CATB should be removed as the preferred successor.**
[[fx-carry-is-not-yet-a-small-account-demeter-replacement]] still names it so. It is now dead on
both counts: Tomunen (2026, *RFS*) shows cat-bond premia are rent on an intermediary capital
constraint that decayed on post-crisis inflows, and the vehicle carries a 128bp TER, traded at
roughly a 12% discount to NAV in June 2026, holds about USD 12-14m, is USD-based despite the EUR
line, and faces a pending ESMA proposal to cap or exclude cat bonds from UCITS.

**CLO AAA carries no segmentation residual.** Elkamhi, Li and Nozawa (*Management Science* 71(3),
2025) find AAA CLO spreads are a fair reflection of correlated loan default risk. Cordell, Roberts
and Schwert (*Journal of Finance* 78(3), 2023) find the risk-adjusted return not significantly
different from zero, and attribute the buyer base to banks and insurers finding CLO AAA
capital-*efficient*. That is clientele attraction, the opposite of the barred-capital mechanism the
exclusion thesis requires.

**EUR/USD CIP has largely compressed.** The BIS 2016 evidence for a persistent tens-of-bp basis does
not survive contact with 2024-2025 data: an ING note dates the EUR/USD 5-year basis at 1-3bp in
November 2024 against a four-year trailing average near -20bp. Possibly cyclical, and other pairs
remain wider, but the durable-limit framing should not rest on this pair.

## The hard-dated vehicle exists, and does not fill the seat

The last open screening question is closed. **Aberforth Geared Value & Income Trust** (AGVI,
GB00BPJMQ253, LSE) satisfies all four conditions: the Articles require a wind-up GM on or before
30 June 2031 with weighted voting that passes the resolution if any shareholder votes in favour, so
the default is wind-up rather than continuation; two predecessor trusts in the franchise wound up on
schedule in 2017 and 2024; it holds 68 listed UK small caps marked to market; it has a PRIIPs KID;
and it traded at -14.03% to NAV on 13 July 2026.

It fails on two grounds, neither of them the anchor.

- **The discount is the sector, not a mispricing.** The AIC's UK Smaller Companies sector average was
  12.46-13.8% against a 29-year average of 14.4%. AGVI sits at the sector average alongside roughly
  nineteen peers that have no forcing mechanism. The edge is the *date*, not the size of the gap.
- **The anchor is attached to the wrong exposure.** Convergence contributes ~1.2-3.1%/year over 4.9
  years; the position is 41-42%-geared UK small-cap equity with a 1.4% ongoing charge and a 4-6%
  bid-ask spread. That beta loses disproportionately in the state the tail sleeve is bought to cover,
  which is a correlated collision.

Two clean by-products. The discount-plus-date combination lives in the **geared equity leg** of
split-cap structures and never the ZDP leg, because ZDPs price to their known fixed payout - AGZI
trades at a 1.96-4.8% premium. And UCITS fixed-maturity bond funds satisfy the first three
conditions but are open-ended, so no secondary price exists to diverge from NAV and the fourth
condition cannot apply.

A discount without a dated anchor is not a trade at all. Naspers/Prosus is the illustration: a 30-40%
discount against which a USD 36-39bn open-ended buyback since June 2022 has closed only 10-13
points, with management stating they expect it to persist.

## Wrapper dilution

Distinct from the inversion law above, and it closed three candidates today. At retail you cannot buy
a mechanism; you buy a fund containing some of it, at whatever ratio the manager chose. TFIF holds
SRT at 7.4% of NAV, so EUR 2,450 buys roughly EUR 181 of the intended exposure and EUR 2,270 of the
CLO and ABS this note kills above. AGVI's contractual convergence is a 1.2-3.1% annual component
inside a geared equity position. The fallen-angel ETF is the inversion case rather than the dilution
one, but the lesson composes: **"does an accessible vehicle exist" and "can we access the mechanism"
are different questions.** Compute the mechanism's share of the vehicle before treating access as
solved.

If no such vehicle exists, the seat stays empty and the 0.28 risk share becomes an asset-allocation
question rather than a strategy question, per
[[accessible-ordinary-market-income-after-an-open-search]].

Bank significant-risk-transfer is the day's best mechanism and is **unknown rather than dead** - the
distinction that matters. A bank must hold capital against a loan book regardless of its own risk
view and pays a third party to take the junior slice, so the wedge is a capital rule rather than a
capital shortage, and the income accrues from holding. Access is real and cheap: TwentyFour Income
Fund (LSE, GG00B90J5Z95) discloses named SRT deals, keeps a current EU-format KID, and charges 0.75%
with sub-1% ongoing charges and no performance fee.

Three things stop it filling the seat, none of them the premium.

- **The wrapper delivers 7.4% of the reason for buying it.** SRT is 7.4% of TFIF's NAV; the rest is
  European CLO and ABS, which carries no segmentation residual per the correction above. At EUR 2,450
  that is roughly EUR 181 of the intended exposure.
- **It is a holding.** Against [[what-is-a-strategy]] it has a named payer and nothing else - no
  state, no exit, no declared failure condition.
- **The loss state has never occurred.** BIS/BCBS (February 2026): "the efficacy of risk mitigants
  has not yet been tested by large-scale credit losses and SRT markets are opaque to regulators and
  participants." EBA 2020 and an ESRB report through Q2 2024 both show near-zero realized defaults.
  March 2020 and 2022 were mark-to-market events. The concave shape this seat requires is a
  well-motivated hypothesis about a market that has not lived through its own bad state.

Carry that third point explicitly into any sizing decision rather than treating the loss state as
established.

## The screen, corrected by the one thing that passed

Reading primary documents instead of papers produced the only candidate all day that satisfies all
five parts of [[what-is-a-strategy]]: **US issuer odd-lot tender priority** (Rule 13e-4, holders of
fewer than 100 shares who tender all of them are accepted in full while everyone else is prorated).
State is the announced offer, action is buying under 100 shares and tendering, exit is settlement,
the payer is the issuer paying a premium to cut registrar cost, and failure is an amended offer, a
missed election, or a premium below costs.

Two verified facts that no paper would have supplied. The SEC's 1996 rule release considered the
"buy 99 shares to qualify" abuse, found it happens "rarely, if ever," and made the record-date
defence **optional**; roughly ten live 2023-2026 filings mostly omit it. And the EUR-domestic
analogue is dead on a different wall - AIB, Bank of Ireland and Permanent TSB odd-lot offers pay a
5% premium to VWAP but are restricted to registered holders and explicitly exclude Euroclear
Participants and CDI holders, which is every nominee position including IBKR.

This corrects the screen at the top of this note. The line is not *accrues from holding* versus
*captured by trading* - odd-lot tender is neither. It is **statistical versus contractual**. What
our cost floor destroys is capturing a statistical tendency by transacting; what survives is a
payment fixed by a document, whether received by holding a coupon or claimed by making an election.

Size it honestly. Being small is the qualification, so capacity fits by construction - 99 shares of
anything under about EUR 24 sits inside the sleeve - but there are 2-6 actionable events a year,
two dedicated tracking sites and a purpose-built EDGAR scanner already compete for them, per-event
profit runs EUR 100-1,200, and capacity binds on aggregate beneficial ownership so sub-accounts do
not multiply it. That is a real strategy, correctly sized to us, and too sparse to hold a 0.28 risk
share as continuous income - exactly the verdict sub-book C of
[[public-filings-special-situations-as-atalantas-pair]] reached without the primary-document
evidence.

## Kills re-tagged: measured absent, or never measured

Roughly 65 distinct closures from the day were audited against one test - *would the literature have
shown this if it were true?* Four verdicts rather than two: DEAD (measured absent), UNKNOWN (never
measured), CLOSED-FOR-US (real but behind access, size, eligibility or collision), and SUPERSEDED
(the channel itself ceased to exist).

Two flavours of UNKNOWN turn out to matter differently. **AT1's exclusion decomposition is an effort
gap** - nobody has run the Blitz-Fabozzi-style regression and someone could. **SRT's loss state is
unresolvable until a recession happens**, so no effort closes it. Only the first is a research task.

`graveyard.md` is a different layer from these asset-class kills - mostly parameter-level backtests -
but three entries bear on today's work and two would have been misread:

- **Line 70 kills the shadow-gamma payoff as a trade** (wrong sign at daily cadence, null at weekly,
  edge below the cost wall) without contradicting the Terstegge finding, which is about whether
  dealers still hold the deep-tail short. **Real as a risk-model input, dead as a trade** - two
  verdicts this vault has been merging.
- **Line 49 does not test the AT1 exclusion premium.** It is a sizing-tax result for an AT1 leg on a
  specific book, not a risk decomposition. Do not read it as closing that question.
- **Line 68 already killed the HMM 60/40 rebalancing calendar signal in-house** - reproduces
  2000-2023, dies 2024 onward, fails pairing with trend. That resolves the corresponding
  working-paper candidate on our own out-of-sample data.

**One reopen is both live and actionable: European put-write.** Vol selling was closed on
Dew-Becker & Giglio, which measures the S&P 500; no EU replication of that alpha test exists, and
Gârleanu, Pedersen & Poteshman already established that the premium's sign varies by venue. OESX and
ODAX trade at IBIE today, so there is no access question, and premium received is contractual rather
than statistical, so it passes the screen at the top of this note.

The test must be strike-specific and the deep end should be expected to fail: European retail
structured-product issuance compresses implied volatility at 60-70% moneyness, with the 60%-strike
Euro Stoxx 50 put estimated about 2 vol points below its unaffected level. The live question is
whether a premium survives at strikes away from that barrier zone, post-2012, in a defined-risk
structure whose wing sits above -20% so it does not collide with the tail sleeve. That is a
measurement on option data, not another literature search.

Bank SRT, insurer reinsurance and pension/longevity transfer are excluded from the reopen ranking
entirely: no research reopens a license requirement.

## The search was biased, and the bias points one way

Every hunt converged on the same shape: what is alive needs institutional access, what retail can
reach is dead or is directional beta. That conclusion is substantially an artefact of where we
looked.

Academic finance is funded, staffed and data-supplied by institutions. Its datasets are
institutional, and the effects that get measured are the effects a fund could deploy capital
against. An effect whose total capacity is below institutional minimum is invisible to that
corpus: no fund can use it, so nobody measures it, and nobody positioned to publish can trade it.
Searching that corpus and concluding "only institutional mechanisms survive" is circular. This
compounds the survivorship and publication bias `research/README` already names, rather than
replacing it.

Twelve parallel hunts of one corpus is **one sample twelve times, not twelve samples**. Their
agreement looked like robustness and was shared selection.

The category the corpus cannot see is **rules where being small is the qualifying condition**. The
vault already holds the canonical instance and states the bias in one line: sub-book C of
[[public-filings-special-situations-as-atalantas-pair]] notes that "no clean modern study isolates
odd-lot priority." Odd lots are accepted in full while large holders are prorated, so the edge is
literally being small, and that is exactly why it is unstudied.

A second axis compounds it. Our screen demands published evidence that a premium exists, but whole
classes are **negotiated and private and therefore cannot produce a return series at all**. BIS,
ECB and IMF sources confirm bank significant-risk-transfer and Solvency II reinsurance are real and
growing while stating outright that no public investor-return series exists. Absence of a measured
premium is not evidence of no premium when the market is private by construction, yet our method
records it as a kill. This bias points at exactly the mechanism class that scored best on economics.

The corrective is to read **primary documents rather than papers** - offer documents, Schedule TO
filings, prospectuses, scheme circulars, exchange notices. The provision is binding whether or not
a researcher found it interesting. This is the one search channel where our size is not a
disadvantage.

> [!warning] A decay route specific to retail
> Alongside competitors building workarounds (Regulation Q) and the rule-maker rewriting the rule to
> defeat predation (MSCI's staggered implementation and 2023 move to quarterly comprehensive reviews;
> the 1987 witching-hour settlement change), there is a third route that only affects us: **the
> retail channel is withdrawn**. LendingClub ended its Retail Notes program on 31 December 2020, per
> its own 8-K. The academic evidence for that premium describes a channel that no longer exists
> rather than one that compressed. Any retail-accessible mechanism carries this risk, and it does not
> show up as decay in a return series - the series simply stops.

## Limitations

The accrual screen is derived from this book's cost structure, not from the literature, so it is a
constraint on *us* rather than a claim about markets. It would not bind a book with institutional
execution.

The closures recorded above inherit the bias described in the preceding section. They are reliable
as statements about *what the literature documents* and weaker as statements about what exists. A
mechanism absent from these findings may be absent from the corpus rather than from markets.

The IBKR two-sided-quoting prohibition is the load-bearing claim in the first structural finding and
rests on practitioner report alone. Verify it directly before citing it as settled.

Several closures rest on single working papers or on practitioner data. The CLO kill is the
best-evidenced (two published papers, different identification strategies); the SPAC and CIP
corrections rest on industry data rather than peer-reviewed measurement.
