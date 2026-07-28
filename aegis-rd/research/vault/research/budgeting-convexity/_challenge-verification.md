---
title: "Budgeting Convexity - external challenge verification"
paper: "Budgeting Convexity"
status: "Challenge verification complete - see closing assessment"
tags:
  - integrity
  - challenge-verification
---

# External challenge verification report

Independent source verification of an external research sweep claiming the foundation of Sections 2.2
and 2.4 (the durability of the short-convexity pole's payer) is wrong. This is verification only, not
advocacy for or against the challenge and not a revision of the paper. Every claim below was checked by
live web lookup (Exa search and fetch) against primary sources; nothing is asserted from memory. Audit
trail dated 2026-07-24.

Verdict vocabulary used throughout: **VERIFIED**, **PARTIALLY_VERIFIED** (with the failing part stated),
**NOT_FOUND**, **MISATTRIBUTED**, **MISCHARACTERIZED**.

---

## Verdict table

| # | Claim | Verdict | Lookup that established it |
|---|---|---|---|
| 1 | Dew-Becker synthetic-options paper exists, ~100-year zero alpha | VERIFIED | Federal Reserve Bank of Chicago WP 2025-17 (fetched full text); NBER WP 31833 (fetched full text) |
| 2 | Construction spans jump risk / identification question | PARTIALLY_VERIFIED - see dedicated section below | Same two documents, direct quotes on the traded-synthetic wedge |
| 3a | SPX VRP compressed to ~zero around 2010 | VERIFIED (with a dating nuance: 2010 vs. 2012 across sibling papers) | Dew-Becker & Giglio Chicago Fed WP 2025-17; Dew-Becker & Giglio, "The decline of the S&P 500 variance risk premium" (dew-becker.org, conditionally accepted, *Critical Finance Review*, 2026); corroborated by Bates (2022), which dates the break to ~2017 |
| 3b | Dealer net S&P gamma flipped from negative to zero/positive post-crisis | VERIFIED, with an important qualifying nuance | Same two Dew-Becker & Giglio papers (CBOE open-close data); independently corroborated (with a caveat) by an unpublished FMA/AFA conference paper on dealer "shadow gamma" |
| 4 | Tomunen: cat-bond premium scales with intermediary capital constraint, decayed post-crisis, blunted after 2017 losses | VERIFIED | Tomunen (2026), *Review of Financial Studies*; working-paper/dissertation drafts of the same study for the 2017 detail |
| 5 | Cross-asset VRP "AEA study," ~20 futures, 2006-2020, SPX near-zero, illiquidity/jump attribution | PARTIALLY_VERIFIED - empirical findings accurate, "AEA study" framing overreaches | Heston & Todorov (2023), SSRN working paper presented at ASSA/AEA 2024, not AEA-published |
| 6 | Gârleanu, Pedersen, & Poteshman: index end-users net buyers, single-stock end-users net suppliers | VERIFIED | Gârleanu, Pedersen, & Poteshman (2009), *Review of Financial Studies* |
| 7a | Gürtler, Hibbeln, & Winkelvos: cat-bond credit-spread dependence strengthens in crisis | VERIFIED (co-author's first name corrected: Christine, not Niklas) | Gürtler, Hibbeln, & Winkelvos (2016), *Journal of Risk and Insurance* |
| 7b | Carayannopoulos & Perez: cat-bond correlation with markets rises in crisis | VERIFIED | Carayannopoulos & Perez (2015), *The Geneva Papers on Risk and Insurance* |
| 7c | 2008 Lehman TRS counterparty failures (Ajax Re, Newton Re, Carillon, Willow Re) | VERIFIED | S&P and A.M. Best 2008 rating-action reports (via Artemis.bm, Insurance Journal/Claims Journal) |
| 8 | CBS 2025 thesis, 236 instruments, 185M quotes, VRP negative, survives costs; status = student thesis | VERIFIED | CBS Research Portal record for Hebsgaard & Dueholm (2025) |

---

## 1. The Dew-Becker linchpin (Priority 1, claim 1)

**Verdict: VERIFIED**, with one necessary precision the sweep's summary omits: the paper the sweep
describes is not a single fixed document but a research program that has been retitled and re-hosted as
it moved toward publication.

- Dew-Becker, I., & Giglio, S. (2023). *Risk preferences implied by synthetic options* (NBER Working
  Paper No. 31833). National Bureau of Economic Research. https://doi.org/10.3386/w31833 (posted Nov.
  2023, last revised Dec. 2024).
- Dew-Becker, I., & Giglio, S. (2025). *The decline of the variance risk premium: Evidence from traded
  and synthetic options* (Working Paper No. 2025-17). Federal Reserve Bank of Chicago.
  https://doi.org/10.21033/wp-2025-17 (dated Sept. 4, 2025).

These are the same underlying study carried forward: same two authors, same theoretical framework
(synthetic options as dynamically replicated portfolios), same 1926-2022 sample, materially identical
abstract and section structure. The Chicago Fed version is the more recent host and matches the
sweep's claimed affiliation exactly: "Dew-Becker: Federal Reserve Bank of Chicago. Giglio: Yale
University and NBER." I could not confirm journal acceptance for this specific paper as of the lookup
date; it remains, at minimum, a Federal Reserve working paper. (Its sibling paper on the S&P 500 break
specifically, discussed under claim 3 below, is further along: "Conditionally accepted, *Critical
Finance Review*, 2026," per the author's own site.)

**Direct quote establishing the "100 years, no negative alpha" claim**, from the Chicago Fed WP 2025-17
abstract: "Synthetic options never, over the last 100 years, had negative alpha, indicating that
equity investors never required high compensation for market downturns."

**Construction, in the authors' own words:** "The synthetic options are constructed back to 1926 using
data on the CRSP market return... Empirically, replication works quite well: synthetic options have
returns that are over 90 percent correlated with traded option returns and, most importantly, hedge all
realized crashes over the last century effectively. That does not mean that options could have been
synthesized in real time historically, though - trading costs and other frictions would have made that
infeasible."

**The paired finding on traded options:** "Whereas traded options have strongly negative CAPM alphas,
synthetic options have historical alphas that are indistinguishable from zero... there is a break in
the returns somewhere around 2010. In the period since 2010, in fact, the alphas of the traded options
have converged to zero, consistent with the synthetic options."

**Distinguishing it from the 2017 JFE paper the sweep was warned not to confuse it with:** Dew-Becker,
I., Giglio, S., Le, A., & Rodriguez, M. (2017). The price of variance risk. *Journal of Financial
Economics, 123*(2), 225-250. https://doi.org/10.1016/j.jfineco.2016.04.003. That paper studies variance
*swap term structure* 1996-2014 and finds "only unexpected, transitory realized variance was
significantly priced," with claims to forward variance carrying no premium - a genuinely different
question (term-structure pricing, not the century-long synthetic-vs-traded alpha comparison) and a
genuinely different sample. The sweep's claim maps cleanly onto the 2023/2025 paper and does not appear
to have garbled the two; the "100 years / synthetic options / no negative alpha" formulation only
appears in the Dew-Becker & Giglio synthetic-options work, never in the 2017 JFE paper.

---

## 2. The identification question: can the construction span jump risk? (Priority 1, claim 2)

This is the section the requester specifically asked to have tested rather than confirmed. My honest
reading, after reading the authors' own text on this exact point:

**The objection is well-founded and the authors' own language supports it rather than defeating it.**

The synthetic options are built by daily delta-hedging (dynamic replication in the underlying), which
is exactly the construction that is well understood to fail to span discontinuous jumps: a discretely
rebalanced hedge cannot track a payoff through a jump the position had no chance to rebalance against.
The authors do not dispute this. In their own robustness discussion, addressing exactly the alternative
explanation that synthetic and traded options "hedge different states," they write:

> "Synthetic option returns depend on the path the market takes, so the gap between true and synthetic
> returns is a function of realized volatility and other higher-order factors like jumps. If that gap
> is related to marginal utility, then it will be priced and drive a wedge between the traded and
> synthetic returns." (footnote: "No-arbitrage option prices typically rely on this type of mechanism,
> e.g. Pan (2002).")

This is the authors conceding, in their own words, that jump risk lives in the wedge between synthetic
and traded returns, not in the synthetic leg itself. Since the synthetic option is constructed
precisely so as not to be exposed to jumps (that is what "delta-hedged" means), its own zero alpha is a
statement about compensation for the risk that continuous/discrete rebalancing *can* span (essentially
diffusive, realized-volatility risk), and says nothing directly about whether investors require
compensation for the jump risk that rebalancing *cannot* span. The paper's own accounting elsewhere
confirms this: "Since a synthetic put is essentially a delta hedge, the difference between the returns
on the traded and synthetic put returns is the return on a delta-hedged put, which is a measure of the
variance risk premium." In other words: wherever a jump/crash premium exists, it should show up in the
wedge (i.e., in the traded option's own alpha relative to the synthetic leg), not in the synthetic
leg's alpha.

What the authors actually test is narrower than "does synthetic replication capture jump risk." They
test whether the *shrinking* of that wedge over time (the convergence of traded-option alpha toward
zero) can be explained by jump risk itself having declined, and they reject that narrower alternative:
"those factors do not appear to have shrunk over time. The volatility of the gap between traded and
synthetic option returns has been stable, jump variation shows no trend, and skewness in market returns
has become significantly more negative." This is evidence against "declining jump risk" as the
explanation for the *convergence*; it is not evidence that the synthetic leg's own zero alpha is
unbiased with respect to jump-risk compensation, because the synthetic leg was never designed to be
exposed to that compensation in the first place.

Read this way, the paper's own results are arguably compatible with, rather than contrary to, a
jump-risk premium having existed for most of the 20th century and only compressing recently: the wedge
(delta-hedged/traded-option alpha, "literally a measure of the variance risk premium") was "highly
negative, especially in the period up to 2010," and only "flattened around 2010." That is exactly where
a jump-preference premium would have to live under the authors' own accounting, and exactly where they
document it was large for most of the century and shrank only recently.

**Bottom line on the identification question:** the sweep's summary ("synthetic options show no
negative alpha over 100 years, therefore no jump-preference premium") overreaches what the paper
supports. The paper is careful and precise about what its zero-alpha result does and does not cover;
it explicitly flags that jump risk lives in the untested wedge, not in the tested synthetic leg. A
faithful version of the challenge is entitled to say: "the *diffusive/realized-volatility* component of
index risk was not, on the authors' own century-long measure, priced above CAPM, which weakens claims
resting purely on volatility risk aversion." It is not entitled to say the paper shows no premium for
jump/crash risk specifically, since the authors' own construction and their own footnote say that
component is not tested by the synthetic leg at all.

---

## 3. The break claim (Priority 1, claim 3)

### 3a. SPX VRP compression toward zero

**Verdict: VERIFIED**, sourced independently across two Dew-Becker & Giglio outputs plus one
genuinely separate author (Bates), with a dating nuance worth flagging.

- Dew-Becker, I., & Giglio, S. (2025). *The decline of the variance risk premium: Evidence from traded
  and synthetic options* (Working Paper No. 2025-17). Federal Reserve Bank of Chicago.
  https://doi.org/10.21033/wp-2025-17. Sample: monthly S&P 500 traded option returns 1987-2022 (CBOE),
  synthetic options 1926-2022 (CRSP). Quote: "there is a break in the returns somewhere around 2010. In
  the period since 2010, in fact, the alphas of the traded options have converged to zero."
- Dew-Becker, I., & Giglio, S. (2026). *The decline of the S&P 500 variance risk premium*. Conditionally
  accepted, *Critical Finance Review*. Sample: S&P 500 option strategies (straddles, delta-hedged
  straddles, 95% puts, delta-hedged puts, variance-swap series) 1987-2025 (CBOE). The author's own
  site abstract: "Historically, S&P 500 options earned large negative premia. That has not been true
  since around 2010. Their market-adjusted returns are now approximately zero." The paper's own body
  text, however, dates the statistically estimated break to "around 2012," specifically August 2012 -
  "the last date where a 12-month moving average of intermediary S&P 500 gamma was negative." So within
  the same research program the plain-language summary says "around 2010" (matching the sweep exactly)
  while the precise statistical estimate is 2012. This is a real but minor internal inconsistency in
  dating, not a fabrication; "approximately zero around 2010" is a fair characterization of either
  version.
- Independent corroboration with a different break date: Bates, D. S. (2022). Empirical option pricing
  models. *Annual Review of Financial Economics, 14*, 369-389.
  https://doi.org/10.1146/annurev-financial-111720-091255. Dew-Becker & Giglio's own comparison: "Bates
  (2022) also finds a decline in premia, but dates it somewhat later than us - 2017 instead of 2012."
  This is a genuinely separate author reaching the same qualitative conclusion (the premium declined)
  from separate methodology (weekly rather than daily delta-hedging, data through 2020), but with a
  materially later break-date estimate. A faithful characterization of the literature should report the
  range (2010-2017 depending on source and method), not pick the earliest estimate as if it were
  uncontested.

### 3b. Dealer net gamma flip

**Verdict: VERIFIED**, with an important qualifying nuance from an independent source.

Both Dew-Becker & Giglio papers report the same underlying finding from CBOE open-close options data:
"We show that the net S&P 500 gamma exposure of dealers and market makers for Cboe options shifted
from being consistently negative to being zero or positive following the financial crisis." The more
recent, S&P-500-specific paper dates this precisely: "The options premium goes away around 2012, which
is the same time that the net positions of dealers shift from negative to neutral," based on CBOE
open-close data 1996-2025.

An independent (non-Dew-Becker) source corroborates the *level* finding but complicates its
interpretation. An unpublished conference paper by an author surnamed Terstegge (presented at FMA
Derivatives 2025 / circulated via AFA program materials; full given name and publication status not
independently confirmed, so this source is corroborating rather than load-bearing) analyzes CBOE
dealer position data 2011-2023 and finds: "Aggregate dealer inventory gamma is near zero or slightly
positive." This confirms the "flip" as measured by conventional (local) gamma. But the same paper shows
that under a hypothetical large move ("shadow gamma"), dealer exposure remains strongly negative:
"re-calculating dealer inventory gamma for the scenario where the S&P 500 has fallen by, for example,
10%, reveals a large negative aggregate dealer inventory gamma... Standard risk measures miss this
exposure." The reason: dealers hold a persistent short position concentrated in deep out-of-the-money
puts, whose local gamma near current spot is negligible but which carries large negative gamma once the
underlying has moved. This is a materially important nuance for anyone using the "gamma flipped to
zero/positive" finding to argue the short-convexity payer has disappeared: measured under small,
day-to-day moves, dealers look flat; measured under the crash scenario that actually matters for a
convexity/insurance argument, the short exposure documented by decades of prior literature is still
there. A faithful version of the break claim should state the flip as measured (local/contemporaneous
gamma) and flag that a separate, independent source finds the crash-scenario exposure has not
correspondingly disappeared.

---

## 4. Tomunen: cat-bond intermediary capital constraint (Priority 2, claim 4)

**Verdict: VERIFIED.**

- Tomunen, T. (2026). Failure to share natural disaster risk. *The Review of Financial Studies, 39*(3),
  661-701. https://doi.org/10.1093/rfs/hhaf055. (Author affiliation on the SSRN/dissertation drafts of
  the same study: Boston College, matching the sweep's guess.)

Model result, quoted: "We can see that the premium is proportional to the intermediary constraint
α. If α = 0, the managers are not constrained... the cat bond market specific risk carries no premium.
If, on the other hand, the intermediaries are constrained and α > 0, the cat bond market specific risk
has a positive price." Empirical fit: "71% of the variation in the expected returns of the test assets
is explained by a theoretically-motivated measure of these intermediaries' marginal rate of
substitution."

Post-crisis decay, quoted: "I also find that the premium has decreased significantly after the
financial crisis and seems to have become less responsive to the occurrence of disasters," attributed
to "a gradual but large inflow of new institutional capital into the specialist funds."

2017 detail, quoted: "Most notably, the premium seems not to have reacted strongly to the record losses
of 2017... After 2017 losses, the funds were quickly able to raise new capital to replace losses, which
contributed to the attenuated price reaction." This precise 2017 detail lives in the working-paper and
dissertation drafts of the same study rather than in the terser published RFS abstract, but it is the
same paper, not a different or invented source.

---

## 5. The cross-asset VRP "AEA study" (Priority 2, claim 5)

**Verdict: PARTIALLY_VERIFIED.** Empirical findings are accurately characterized; the "AEA study"
framing mischaracterizes the venue.

- Heston, S. L., & Todorov, K. (2023). *Exploring the variance risk premium across assets* [Unpublished
  working paper]. SSRN. https://doi.org/10.2139/ssrn.4373509.

This is an SSRN working paper that was presented at the ASSA/AEA Annual Meeting in January 2024. It is
**not** published in the *American Economic Review*, any *AEJ*, or *AEA Papers & Proceedings* - it does
not appear in the May 2024 *AEA P&P* volume, and an independent 2026 citation still describes it as
"Unpublished working paper." Calling it an "AEA study" inflates a conference presentation into an AEA
publication.

Findings, quoted and confirmed accurate: "In the period 2006-2020, most assets had significant variance
risk premiums, but the realized S&P 500 variance risk premium was not significantly different from
zero," across "twenty different futures, including equities, bonds, currencies, and commodities."

Attribution, quoted, and here the sweep's framing overstates the authors' own hedging: "We find little
evidence that the variance risk premium across assets is associated with systematic variance risk...
However, we find **mild evidence** that the variance risk premium is associated with hedging
constraints as proxied by illiquidity measures... and measures of jump risk (kurtosis)." "Mild evidence"
is weaker than "attributing the premium to illiquidity and jump risk," which is how the sweep's claim
frames it.

---

## 6. Gârleanu, Pedersen, & Poteshman - demand-based option pricing (Priority 2, claim 6)

**Verdict: VERIFIED**, exactly as stated.

- Gârleanu, N., Pedersen, L. H., & Poteshman, A. M. (2009). Demand-based option pricing. *The Review of
  Financial Studies, 22*(10), 4259-4299. https://doi.org/10.1093/rfs/hhp005.

Quoted: "We are the first to document that end-users have a net long position in S&P 500 index options
with large net positions in out-of-the-money (OTM) puts... Since options are in zero net supply, this
implies that dealers are short index options." And, on the sign flip for single names: "For instance,
end-users are net short single-stock options - not long, as in the case of index options... in the
equity option market, unlike the index-option market, end users are net suppliers of options."

---

## 7. ILS orthogonality failures (Priority 2, claim 7)

**7a. Gürtler, Hibbeln, & Winkelvos - VERIFIED**, with a co-author first-name correction.

- Gürtler, M., Hibbeln, M., & Winkelvos, C. (2016). The impact of the financial crisis and natural
  catastrophes on CAT bonds. *Journal of Risk and Insurance, 83*(3), 579-612.
  https://doi.org/10.1111/jori.12057. The third author is **Christine Winkelvos**, not "Niklas
  Winkelvos" as the sweep had it.

Quoted: "Financial crisis hypothesis (H6): If a financial crisis occurs, the positive dependency
between corporate credit spreads and CAT bond premiums increases." Result: "the dependency strengthens
after the financial turmoil in the aftermath of the Lehman event. This finding is consistent with our
hypothesis (H6)." And: "Hence, CAT bonds cannot be regarded as zero-beta securities. This dependency
even strengthens significantly in the case of the financial crisis."

**7b. Carayannopoulos & Perez - VERIFIED.**

- Carayannopoulos, P., & Perez, M. F. (2015). Diversification through catastrophe bonds: Lessons from
  the subprime financial crisis. *The Geneva Papers on Risk and Insurance - Issues and Practice, 40*(1),
  1-28. https://doi.org/10.1057/gpp.2014.14.

Quoted: "CAT bonds are zero-beta assets only in non-crisis periods... With the collapse of Lehman
Brothers, CAT bond returns became significantly correlated with the market... The correlation
coefficients become large and significant in September 2008, and remain statistically different from
zero until the end of 2009... The average correlation coefficient during this crisis period is 0.29."
Note for faithful characterization: the same paper also finds correlations reverted to insignificance
by early 2011 and argues cat bonds remained a net-valuable diversifier overall - a claim that any
paraphrase should not drop.

**7c. Lehman TRS counterparty failures - VERIFIED**, all four names confirmed correctly as given.

Primary sources: S&P and A.M. Best rating actions, September-October 2008 (republished via Artemis.bm
and Insurance Journal/Claims Journal). S&P, Sept. 30, 2008: "Standard & Poor's have now downgraded all
four of the catastrophe bonds which used Lehman Brothers Special Financing as the total return swap
counterparty. The issuers of the bonds have terminated their swaps... the lack of a counterparty is the
reason for the following actions." The four deals are confirmed exactly as named in the claim: Ajax Re,
Newton Re, Carillon, and Willow Re. A.M. Best, Sept. 18, 2008: "the rating actions reflect the
uncertainty of Lehman Brothers Special Financing Inc., the swap counterparty in each of the
catastrophe bonds, to meet its obligation under the swap agreement." This confirms the transmission
mechanism as TRS-counterparty/collateral impairment rather than the insured catastrophe risk itself.
One precision: these were rating downgrades (to CC/CCC/c), not confirmed principal losses as of the
contemporaneous record; "suffered losses" should be phrased as rating/collateral impairment unless a
later default is separately sourced.

---

## 8. The CBS 2025 thesis (Priority 2, claim 8)

**Verdict: VERIFIED**, including its non-peer-reviewed status.

- Hebsgaard, M., & Dueholm, A. E. (2025). *The variance and correlation risk premia: Empirical evidence
  and implications across equity markets, asset classes, time periods, and volatility regimes,
  accounting for transaction costs* [Master's thesis, Copenhagen Business School]. CBS Research Portal.

CBS Research Portal explicitly labels the record "Student thesis: Master thesis," MSc in Business
Administration and Mathematical Business Economics, published 15 May 2025, 138 pages, supervised by
Anders Bjerre Trolle - confirming it is a student thesis, not peer-reviewed work, exactly as the sweep
concedes.

Numbers confirmed exactly: "we synthesize swap rates for 236 financial instruments from 185 million
quotes on out-of-the-money options between 1996 and 2023." Findings confirmed: "We find that the
variance risk premium is significantly negative across equity markets, asset classes, time periods and
volatility regimes. It can not be explained by factor models, and it remains negative after transaction
costs."

---

## Closing assessment

**What survives verification, largely intact:** claims 1, 3a, 3b, 4, 6, 7a, 7b, 7c, and 8 are all
real, correctly attributed findings from the sources claimed (with the minor name correction in 7a and
the rating-vs-loss precision in 7c). The Dew-Becker & Giglio synthetic-options program is real, says
close to verbatim what the sweep claims, and the SPX VRP compression and dealer-gamma-flip findings are
independently documented (with Bates 2022 supplying genuine, if later-dated, corroboration). Tomunen's
intermediary-capital story, including the specific 2017 recapitalization detail, is confirmed in the
authors' own words. The ILS crisis-correlation and Lehman-TRS claims are all confirmed as stated. The
CBS thesis is exactly what the sweep says it is, including conceding its non-peer-reviewed status.

**Where the challenge overreaches:**

1. Claim 2, the identification question, is the most important qualification. The authors' own text
   concedes that jump risk lives in the wedge between traded and synthetic returns, not in the tested
   synthetic leg, and that wedge (which is where a jump premium would have to show up) was strongly
   negative for most of the century the sweep cites. A faithful challenge is entitled to say the paper
   weakens claims resting on *diffusive/volatility-aversion* pricing of the short-convexity pole; it is
   not entitled to say the paper shows no jump-risk premium, since the paper's own construction does not
   test that.
2. Claim 3a's precise break date shifts between 2010 (plain-language summary) and 2012 (the paper's own
   statistical estimate) within the same research program, and a genuinely separate source (Bates 2022)
   puts it at 2017. The literature gives a range, not a single agreed date.
3. Claim 3b's "gamma flip" is real under conventional local-gamma measurement but an independent source
   shows the crash-scenario ("shadow gamma") exposure has not correspondingly disappeared - a real
   complication for reading the flip as evidence the structural short-convexity payer has left.
4. Claim 5's "AEA study" is an inflated description of an SSRN working paper merely presented at an
   AEA-hosted conference, and its "attributing the premium to illiquidity and jump risk" overstates the
   authors' own "mild evidence" language.

None of these overreaches invalidate the underlying facts; they narrow what the facts are entitled to
support. The strongest, most literally-supported form of the challenge is: the empirically measured VRP
and dealer short-gamma exposure for SPX specifically have compressed since roughly 2010-2017, for
reasons the primary authors attribute to intermediary frictions and capital constraints (not to a
change in end-investor insurance demand), while other assets and instruments (cat bonds, most VRP
futures, single-stock options) continue to show the premium and payer patterns the paper describes.
Whether that SPX-specific compression falls within or outside the durability claims Sections 2.2 and
2.4 make is an interpretive question for the author, not one this verification pass resolves.
