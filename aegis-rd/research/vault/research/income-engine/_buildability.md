---
title: "Convergent Engine - ILS buildability verdict"
paper: "The Convergent Income Engine: Funding the Book Through Ordinary Markets"
date: 2026-07-25
tags:
  - buildability
  - verification
  - ils
---

# ILS buildability verdict: the premium question comes before the access question

> [!abstract] Verdict
> The ILS premium is not gone. Tomunen's own year-by-year estimates stay positive across every year of
> his sample, including nine years after the 2010 break he documents, and his model requires a fully
> unconstrained specialist-fund sector to zero it out, which the paper does not show has happened. What
> the evidence supports is compression, not extinction. Orthogonality demotes from an architectural
> property (true in every state, "by construction") to a conditional one (true in the trigger always,
> true in returns in normal and most crisis states, false in a systemic funding-liquidity crisis - which
> is exactly the state the pole was recruited to survive). Access, once checked, is not the binding
> constraint: the dedicated UCITS cat-bond funds are 85-100% direct cat-bond exposure, not a diluted
> sliver, and their active management means the retail buyer joins the compensated supply side of
> Tomunen's own model rather than following a rules-based mandate. What does bind, and what the vault's
> prior treatment scoped too narrowly, is a pending ESMA proposal that targets exactly the concentrated
> fund structure that solves the dilution problem. Full verdict paragraph and section-level consequence
> in [[#4. The verdict, and what the paper does with the section|§4]].

This note resolves two open obligations from
[[research/income-engine/_brief|the porting brief]] in the order the brief demands: whether the
premium survives Tomunen, then how the orthogonality claim in
[[insurance-linked-securities-as-the-orthogonal-income-pole]] should be demoted, then - only because
something survives step one - whether the UCITS-wrapper route in
[[the-ucits-constrained-carry-sleeve]] reconciles with the cat-bond UCITS universe (~USD 19.12bn at
end-2025, and already re-verified below as larger by the time of writing) into one buildability verdict.
It does not re-derive what [[income-must-accrue-not-be-captured]] and
[[the-premium-is-rent-on-a-balance-sheet]] already settled about CATB (the ETF) or about the
balance-sheet-rent family generally, though the load-bearing CATB figures those notes carry are
independently re-verified below rather than simply repeated. This note also does not generalize its
findings to the rest of the balance-sheet-rent family: cat bonds are the one member with a public,
multi-decade return series, which is exactly why they are the one member that can be shown to be
compressing rather than gone - that selection effect, already named in
[[the-premium-is-rent-on-a-balance-sheet]], cuts against reading anything here onto SRT, reinsurance, or
the other unmeasured members of the family.

> [!note] Verification pass, 2026-07-25
> This note was first drafted using standard web search/fetch and treating the brief's "settled" CATB
> figures as given. A second pass, using Exa (this desk's standard research channel) against primary
> sources - the fund manager's own site and KIID, justETF, Morningstar, the ESMA final report itself, and
> the published RFS abstract via DOI resolution - re-verified every load-bearing figure below rather than
> carrying them forward from a summary. Three findings moved as a result: the UCITS cat-bond universe is
> materially larger today than the "~USD 19bn" figure this note originally carried (§3); the ESMA question
> is more genuinely unsettled, on both mechanism and outcome, than the first draft characterized it (§3);
> and Tomunen's headline finding is now confirmed against the *published* RFS abstract, not only the
> pre-publication draft (§1, Limitations). Nothing found in this pass overturns the verdict in §4; it
> sharpens the evidence under it.

## 1. Is the ILS premium still there?

Tomunen's central empirical result is a cross-sectional pricing test: a theoretically motivated measure
of specialist funds' marginal rate of substitution explains 71% of the variation in cat bonds' expected
returns.[^tomunen] The price of that risk, λ<sub>cat,t</sub>, is estimated year by year from 2003 to
2018. **In all sixteen years the estimate is positive**, ranging 1.02% to 7.62%, with a full-sample
Fama-MacBeth average of 2.06%; robustness checks that drop callable bonds, restrict to earthquake-only
bonds, or restrict to parametric-trigger bonds leave the estimate "not materially affected" at "around
the 2% level."[^tomunenjmp] Nine of those sixteen years are after 2010, the year Tomunen's own Figure 4
dates as the start of the decline. The point estimate does not cross zero in any of them, in the primary
text available to this note.

That rules out reading (a) - **the premium is gone** - as a fair characterization of what Tomunen shows.
It is not what the paper argues, and the year-by-year series contradicts it directly.

What the paper does show is reading (b): **compression tied to a specific, named mechanism**, not a
generic decay. The model's own structure makes the point sharp: the premium is proportional to the
intermediary constraint parameter α, and is exactly zero only in the limiting case α = 0, i.e. the
specialist funds facing no capital constraint at all.[^tomunen] Empirically, "the premium has decreased
significantly after the financial crisis and seems to have become less responsive to the occurrence of
disasters," attributed to "a gradual but large inflow of new institutional capital into the specialist
funds"; most pointedly, the premium "seems not to have reacted strongly to the record losses of 2017"
because "the funds were quickly able to raise new capital to replace losses."[^tomunenjmp] That is a
description of α falling and refilling faster after each shock, not of α hitting zero. It is also exactly
the functional form [[the-premium-is-rent-on-a-balance-sheet]] already flags as the general
limits-to-arbitrage prediction: constrained-capacity premia compress toward the marginal arbitrageur's
cost of capital, not to zero.[^svy] Tomunen's paper does not itself test that specific asymptote (there
is no formal test in the accessible text of whether the post-2010 or post-2017 subsample premium is
statistically indistinguishable from zero); the year-by-year point estimates are the best available
evidence, and they stay on the positive side throughout. The published abstract, resolved directly via
DOI and read separately from the draft, confirms the same wording survived peer review: "the aggregate
premium decreases and becomes less sensitive to the occurrence of disasters when intermediaries' access
to outside capital improves."[^tomunendoi] "Decreases and becomes less sensitive," not "disappears" -
the final published text uses the same compression language as the draft this note otherwise relies on.

Reading (c) - **intact but inaccessible** - is the access question, answered in §3. Since (a) is not
supported, something survives to make that question worth asking.

> [!caution] Correction this finding makes to language used elsewhere in the vault
> [[income-must-accrue-not-be-captured]] states CATB is "dead on both counts" and cites Tomunen for the
> economics half. That note's word choice, "decayed," is accurate and matches what is found here. But
> where it is read as "the premium is gone," this note's primary-source check does not support that
> reading - Tomunen's own estimates stay positive throughout his sample. The vehicle half of that verdict
> (128bp TER, ~12% discount to NAV, USD 12-14m, USD-based despite the EUR line) is untouched and is not
> revisited here; it is about the ETF, not the mechanism.

## 2. Demote the orthogonality claim, precisely

[[insurance-linked-securities-as-the-orthogonal-income-pole]] makes two distinct orthogonality claims
under one label, and only one of them is contradicted.

**What survives unconditionally: the trigger.** A hurricane is not caused by a recession and a recession
is not caused by an earthquake. Nothing in the challenge evidence touches this - Gürtler, Hibbeln &
Winkelvos and Carayannopoulos & Perez are both about *pricing and return correlation*, not about what
causes the covered peril. This half of the claim is not weakened by anything below.

**What fails: unconditional return/price orthogonality across all states.** Three independent channels,
each separately sourced and each already verified in this vault's
[[research/budgeting-convexity/_challenge-verification|challenge-verification audit]], converge on the
same state:

- **Pricing channel.** Cat-bond secondary-market spreads "co-move significantly positively with the
  reinsurance cycle" and their "dependency on corporate credit spreads strengthens significantly after
  the Lehman bankruptcy" - a direct, VERIFIED finding, not an inference.[^ghw]
- **Return channel.** Cat bonds are "zero-beta assets only in non-crisis periods." With Lehman's
  collapse, "CAT bond returns became significantly correlated with the market," with correlation
  coefficients "large and significant" from September 2008 through the end of 2009 and an average
  correlation of 0.29 in that window - forced-liquidation pressure, not a change in the insurance
  trigger. The same paper finds correlations reverted to insignificance by early 2011 and that cat bonds
  remained a net-valuable diversifier over the full period; both halves of that finding should travel
  together.[^cp]
- **Counterparty/structural channel.** Four 2008-vintage cat bonds using Lehman Brothers Special
  Financing as their total-return-swap counterparty (Ajax Re, Newton Re, Carillon, Willow Re) were
  downgraded when Lehman failed, because "the issuers of the bonds have terminated their swaps" and "the
  lack of a counterparty is the reason for the following actions."[^lehmantrs] These were **rating and
  collateral impairments, not confirmed principal losses** - the swap structure broke, not the insurance
  trigger, and no contemporaneous record establishes a realized loss of principal on these four deals.
  This distinction is load-bearing: it means the failure mode was "the wrapper's financing plumbing
  failed alongside everything else's," not "the peril turned out to be financial after all."

These are three different mechanisms - a pricing dependency, a forced-liquidation correlation, and a
counterparty-structure risk - and none of them touches the trigger. But they all activate in the same
state: a systemic dealer/intermediary funding crisis. That is precisely the state a concave "floor" pole
exists to survive, and precisely the state the article's own title claims decoupling from ("A book with a
TSMOM convex pole and a cat-bond concave pole is decoupled from *both* sides"). **Orthogonality was a
design goal that failed in the one state it was held for** - the brief's framing is exactly right, and it
is now backed by three separately verified channels rather than one.

**The correct weaker claim.** Cat bonds are orthogonal to the financial cycle at the trigger level in
every state, and orthogonal in returns in normal and most crisis states, with a bounded, temporary,
liquidity-driven co-movement channel that opens specifically in a Lehman-scale funding seizure and closes
again within roughly two years. This is not a new taxonomy - the article's own source already supplies
the right vocabulary and this note should use it instead of "orthogonal": cat bonds are "an effective
diversifier against all asset classes, a poor hedge, and a strong safe haven against extreme equity
declines only in the post-crisis period."[^role] **Diversifier, yes; hedge, no; the thing a floor pole
needs in the crisis itself, no.** The magnitude matters too and should not be lost in the demotion: the
correlation change was "far smaller than for any other asset" and normalized post-2009,[^cp] so this is a
real but bounded failure, not a reversion to credit-carry's structural recession beta.

## 3. Reconcile access - the UCITS wrapper against the cat-bond UCITS universe

Something survived step 1, so the access question is live. [[income-must-accrue-not-be-captured]]
established two failure modes that killed other candidates - wrapper dilution (TFIF holds
significant-risk-transfer at 7.4% of NAV) and wrapper inversion (a rules-based tracker puts the holder on
the mandated, forced side of a flow). Neither applies to the dedicated cat-bond UCITS funds, for reasons
specific to this mechanism rather than a general exemption.

**Dilution: solved, not a wall.** This is the opposite structure from TFIF. ESMA's own data-gathering
exercise for its Eligible Assets Directive review finds "UCITS catastrophe bond funds allocate 88% of NAV
to direct catastrophe bond exposure" in aggregate, and consultation respondents reported dedicated
cat-bond UCITS "consist only of cat bonds and cash," with cat bonds typically "85-97%" and "up to 100%"
of NAV in at least one jurisdiction.[^esma] Two of the largest funds confirm this directly: Schroder GAIA
Cat Bond's own July 2026 factsheet states the fund is "$3.9 billion, only in tradeable ILS
instruments";[^schroderfs] Twelve Cat Bond Fund's stated objective is "risk-adjusted returns by investing
in Cat Bonds" via "a globally diversified portfolio of Cat Bonds."[^twelvefs] A position in either buys
roughly its full notional in the intended mechanism, not TFIF's EUR 181 out of EUR 2,450.

**Inversion: solved on active management alone, which is sufficient by itself.** The inversion law
concerns *rules-based, passively mechanical* wrappers - a fallen-angel index that rebalances monthly on a
published cutoff, a corporate bond index tracker that is the forced seller at month-end. Dedicated
cat-bond UCITS funds are actively managed: Schroder Capital's own material describes "an active trading
strategy" with "effective portfolio construction... to filter transactions without sufficient risk/reward
characteristics."[^schroderfs] That closes the inversion question on its own - a discretionary manager
selecting bonds is not the rules-based mandate the inversion law requires, so the retail buyer is not put
on a forced, mandated side. A further, weaker point is available but should not be read as load-bearing:
Tomunen's own model treats the specialist funds' aggregate AUM, relative to market size, as the literal
supply-side capital whose constraint sets the premium.[^tomunenjmp] *If* a UCITS cat-bond fund of the kind
named in the ILS article - Twelve, Schroder GAIA, Fermat, Icosa, Plenum, Franklin K2, Leadenhall - counts
as a specialist fund in Tomunen's own sense, buying into it would make the retail investor a capital
contributor to the constrained-capacity side the premium compensates, rather than merely a non-forced
buyer. **This equivalence is this note's own inference, unverified against Tomunen's underlying data
sample, and the inversion verdict above does not rest on it** - it is offered as a plausible
strengthening, not as part of the argument that closes the question.

**A crowding dynamic worth naming, though it is not a wall - and it has kept running past the figure this
note first carried.** The UCITS cat-bond sector added USD 5.3bn (about 39%) in 2025 to reach USD
19.12bn at year-end, across 18 funds.[^artemis19bn] That figure is already stale by the time of writing.
Re-verified against Artemis's own tracking: the sector opened 2026 at ~USD 19.2bn, passed USD 20bn for
the first time in February, dipped to ~USD 19.8bn at the end of Q1, and reached ~USD 20.46bn by the end
of April 2026 across 20 funds - growth of 6.5% in four months on top of 2025's 39%.[^artemisq1][^artemisapr]
Six funds with over USD 1bn each account for USD 16.6bn of that, 81% of the sector.[^artemisapr] This is
mechanically the kind of institutional capital inflow Tomunen names as the specific cause of the
post-2010 premium compression documented in §1, and it has not slowed - if anything it has accelerated
into 2026 alongside a record first half of new cat-bond issuance.[^artemisq2] There is no prohibition or
eligibility rule here, so it does not belong in the wall taxonomy below, but it is a real tension the
paper should state plainly: the vehicle that solves access is the same channel that erodes what is being
accessed, and the erosion pressure is larger and more current than the "~USD 19bn end-2025" figure this
note first used. This is not decisive against buildability - the premium has stayed positive through the
inflow, per §1, and cat-bond fund UCITS returns were still running a 10.22% rolling twelve-month average
as of late June 2026[^artemisjun] - but it bounds how durable the current level should be assumed to be.

**Size wall: real, small, and dissolves quickly.** Share-class minimums vary widely within the same fund
family. The most retail-accessible line verified here is Twelve Cat Bond Fund B EUR Acc (ISIN
IE00BD2B9603): EUR 10,000 minimum investment, 1.73% TER, ~EUR 4.01bn fund size.[^twelvefs] Institutional
lines sit far higher - Twelve's Class I USD Acc (launched February 2026, following the January 2026
merger of Securis Catastrophe Bond Fund into the Twelve Capital UCITS ICAV[^twelvemerger]) and Schroder
GAIA Cat Bond's I/IF classes both carry USD/CHF 1,000,000 minimums.[^schroderfs2] The size wall is real
for the smallest accounts but trivial by the vault's own comparison set - roughly EUR 10,000 against
NAV ~27,000-140,000+ for the futures and options candidates in
[[income-must-accrue-not-be-captured]], and it dissolves entirely once cleared in that one fund line.

**The wall the vault's prior treatment scoped too narrowly: structural, pending, genuinely unsettled on
both mechanism and outcome, and still aimed at exactly the concentrated structure that solves dilution.**
[[income-must-accrue-not-be-captured]] and the ILS article's own footnote frame the ESMA question as a
watch item on the CATB *ETF*.[^catbfootnote] It is broader than that, and it is also less resolved than a
single re-read of the headline recommendation suggests - both things are true at once. ESMA's 26 June
2025 technical advice to the European Commission on the review of the UCITS Eligible Assets Directive
(ESMA34-2087785638-1548) names catastrophe bonds explicitly among "large-scale investments in such
alternative assets with their idiosyncratic risks" that ESMA conceptually believes "would be better done
under the AIFMD framework" than under UCITS.[^esma] The specific legislative mechanism proposed is a
look-through test plus a broadened 10% aggregate limit for *indirect* alternative-asset exposure gained
through "delta-one instruments, ETNs, ETCs, AIFs" and similar wrappers, with the report stating explicitly
that this "does not affect investments in traditional company shares or bonds."[^esma] Whether that
carve-out protects Twelve's or Schroder GAIA's *direct* cat-bond holdings turns on a question the report
does not resolve in the text located: whether a cat bond counts as an ordinary "transferable security"
bond under Article 8(1)(a) of the EAD at all. At least one consultation respondent argued it does not;
others in the same consultation argued the opposite, that excluding cat bonds is "neither justified by
empirical evidence nor consistent with principles of proportionality."[^esma][^esmaplenum] ESMA's own
senior policy officer for investment management, asked directly in a November 2025 interview, declined to
settle it either way: "It is not that ESMA's technical advice takes a position against retail investors
accessing cat bonds per se... The advice is not about outlining what constitutes a good or bad investment,"
while still maintaining the concentration concern - "conceptually, if you opened up UCITS to alternative
assets [like cat bonds] beyond 10%, that would risk blurring the lines between UCITS and alternative
investment funds."[^esmaplenum] What is not contested: ESMA's own data shows the 72 UCITS funds currently
holding cat bonds are concentrated and "typically aimed at professional investors," not retail, even
before any rule changes;[^esma] the European Commission has not decided whether to adopt the advice, other
national regulators are reportedly not aligned with ESMA's view, and market participants expect any
Commission process to "take time" and any resulting change to arrive "some years" out, with ESMA itself
recommending transitional provisions if the recommendation is adopted.[^esmaplenum] The Commission's
original mandate to ESMA set an October 2024 deadline; the advice was not delivered until June 2025, which
is the best available evidence for how slowly this specific process actually moves.[^esmamandate] Net: this
is not an imminent shutoff, and it may not even reach direct bond holdings if the "traditional bonds"
carve-out is read broadly - but it is a live, structural, unresolved question aimed at exactly this fund
structure, and no NAV threshold rescues a wrapper that does get reclassified out of UCITS.

| Candidate | Type | Verdict |
|---|---|---|
| Wrapper dilution | - | Not a wall: 85-100% direct cat-bond exposure in the named funds, confirmed by ESMA's own data and by two funds' own factsheets |
| Wrapper inversion | - | Not a wall, and inverted: active management; the buyer joins Tomunen's specialist-fund supply side |
| Premium-eroding capital inflow | - | Not a wall (no prohibition); a crowding dynamic sharing a cause with the access channel itself |
| Share-class minimum subscription | size | Dissolves at ~EUR 10,000 in the most accessible verified line (Twelve B EUR Acc); institutional lines sit at USD/CHF 1m |
| ESMA UCITS-eligibility reclassification (AIFMD relabeling) | structural | Pending and genuinely unsettled on both mechanism (does the look-through reach direct bond holdings) and outcome (Commission undecided, regulators split); no NAV threshold would rescue it if it lands |
| Current professional-investor skew in existing funds | structural-practical | Live today per ESMA's own data; formally retail-eligible share classes exist but are a minority of the universe's AUM |

## 4. The verdict, and what the paper does with the section

> [!abstract] Verdict, one paragraph
> The ILS premium is not gone: Tomunen's own year-by-year estimates never cross zero across sixteen
> years, nine of them after the 2010 break he documents, and his model requires a fully unconstrained
> specialist-fund sector to zero it out, which his paper does not show. The honest reading is
> compression tied to a named, decaying-but-not-exhausted capital constraint, consistent with (though
> not itself proof of) the general limits-to-arbitrage prediction that constrained-capacity premia
> compress toward the marginal arbitrageur's cost of capital rather than to zero. Orthogonality demotes
> from an architectural property to a conditional one: the trigger stays meteorological in every state,
> and returns stay uncorrelated in normal and most crisis states, but three independently sourced
> channels - credit-spread-dependent secondary pricing, forced-liquidation return correlation, and
> TRS-counterparty structural risk (rating and collateral impairment, not confirmed principal loss) - all
> activate in a systemic funding-liquidity crisis, which is exactly the state a concave floor pole is
> recruited to survive; the right vocabulary is the diversifier/hedge/safe-haven taxonomy the article's
> own sources already supply, not "orthogonal." Access, once checked against the failure modes that
> killed other candidates, is not the binding constraint: the dedicated UCITS cat-bond funds run 85-100%
> direct cat-bond exposure rather than a diluted sliver, and their active-management structure makes the
> retail buyer a capital contributor to Tomunen's own constrained-capacity side rather than a rules-
> following forced counterparty - the two failure modes that killed SRT and fallen angels do not apply
> here. What does bind is a wall the vault's prior treatment scoped too narrowly to the ETF: a June 2025
> ESMA technical advice conceptually places large concentrated cat-bond exposure under the AIFMD framework
> rather than UCITS, ESMA's own data shows the 72 existing cat-bond UCITS funds are already "typically
> aimed at professional investors" rather than retail, and ESMA's own policy officer has declined to rule
> out the concentration concern even while declining to take a position against retail access "per se."
> Whether the specific proposed mechanism (a look-through test for indirect exposure, explicitly carved
> out for "traditional... bonds") actually reaches funds holding cat bonds directly, and whether the
> European Commission adopts any of it, are both genuinely open - national regulators are reportedly
> split and the Commission has missed one deadline on this file already. That wall is structural, pending,
> and unresolved on both whether it applies and whether it lands; no NAV threshold rescues it either way if
> it does. The size wall that does exist (a roughly EUR 10,000 retail share-class minimum at the smallest
> verified vehicle) is trivial by comparison. The mechanism is real, weaker and more conditional than the
> article's title claims, riding a premium that the very inflows giving retail access are documented to
> erode - and those inflows have not slowed, the sector is materially larger now than the figure this note
> first carried - wrapped in vehicles under an active, genuinely unresolved regulatory question. **Buildable
> today. Not durably so, and not orthogonal in the state that would matter most.**

**Section-level consequence.** The ILS section survives - this is not the negative result CATB turned
out to be, and nothing here manufactures a kill to keep the brief's ordering tidy. But it needs
retitling and reframing. "Insurance-Linked Securities as the Orthogonal Income Pole" claims an
architecture-level property (decoupling "by construction," a floor "decoupled from both sides") that this
note does not support as an unconditional claim. The section should be reframed as a *conditional,
better-than-credit-carry, still-imperfect* concave companion: real trigger-level decoupling, real but
bounded crisis-state correlation risk, a premium that is compressing on a named and still-operating
mechanism rather than a mysterious decay, and a wrapper route that works today but sits under a specific,
citable, unresolved regulatory threat that the paper should name rather than bury in a footnote. It should
stop calling the mechanism "orthogonal" and start using the diversifier/hedge/safe-haven vocabulary its
own sources already supply. It should also carry the crowding observation from §3 explicitly: sizing and
timing guidance for this pole cannot treat the current UCITS-era premium level as a stable baseline,
because the vehicle's own growth is part of what is compressing it.

## Limitations

> [!warning] Aggregator-sourced access figures - flagged for Stage 2.5 integrity verification
> This paper is theoretical (the convergent seat as a portfolio role); everything below is footnote-level
> access detail, not load-bearing to the §4 verdict. None of it was checked against the underlying fund's
> own KID or prospectus, so each line should be independently closed or dropped at the integrity gate
> rather than carried forward on this note's confidence:
>
> - Twelve Cat Bond Fund B EUR Acc (IE00BD2B9603): EUR 10,000 minimum, 1.73% TER, ~EUR 4.01bn size -
>   source is Investing.com.[^twelvefs]
> - Schroder GAIA Cat Bond IF Accumulation USD / CHF Hedged: USD/CHF 1,000,000 minimum - source is
>   Investing.com.[^schroderfs2]
> - **Schroder GAIA Cat Bond's retail-sized entry point is unconfirmed, not merely aggregator-sourced.**
>   Only institutional-minimum share classes (I, IF, both 1,000,000) were located; whether a smaller,
>   genuinely retail line exists was not established either way, and §3's size-wall discussion should be
>   read as resting on Twelve's retail line, not Schroder's.
> - CATB (ETF) AUM $14.79M and TER 1.38% - TradingView; the TER figure is a known outlier against 128bp
>   independently confirmed via HANetf's own site and justETF (see [^catbver]).
> - CATB AUM $14.02m as of 14 July 2026 - Morningstar (lt.morningstar.com), not the fund's own factsheet.
> - CATB fund size EUR 10m - justETF.
>
> Not flagged here: HANetf's own fund page and KIID, Schroder Capital's own investor presentation, the
> ESMA final report, and Artemis trade-press figures (this vault's established source class for cat-bond
> market data throughout [[insurance-linked-securities-as-the-orthogonal-income-pole]] and
> [[the-ucits-constrained-carry-sleeve]]) - those are issuer/primary sources or an already-accepted vault
> source class, not retail data aggregators.

- The year-by-year figures in §1 (the 1.02%-7.62% range, the 2.06% average, the "around 2%" robustness
  figure) are drawn from the November 2019 job-market-paper draft of Tomunen's study
  (tuomastomunen.com / wpcarey.asu.edu), not the final peer-reviewed *Review of Financial Studies* 39(3)
  full text, which remains paywalled beyond its abstract. This limitation is narrower than it was in the
  first draft of this note: the RFS-published *abstract* was subsequently resolved directly via DOI
  (https://doi.org/10.1093/rfs/hhaf055) and confirms the same headline finding in the same words -
  "the aggregate premium decreases and becomes less sensitive to the occurrence of disasters when
  intermediaries' access to outside capital improves"[^tomunendoi] - so the *direction* of the finding is
  now confirmed against the published text, not only the draft. The vault's independent
  challenge-verification separately confirms this is the same underlying study.[^tomunenverif] What is
  still unconfirmed against the published version specifically is the exact year-by-year figures and
  whether the final sample extends past 2018; treat those as drawn from a pre-publication draft.
- No formal statistical test of "is the post-2010 (or post-2017) subsample premium significantly
  different from zero" was located in the accessible text. The year-by-year point-estimate series is the
  best available evidence for reading (b) over reading (a); it is suggestive rather than a direct test of
  the specific limits-to-arbitrage asymptote invoked in §1.
- The Twelve and Schroder share-class figures (minimums, TERs, fund sizes) and the Schroder retail-line
  gap are aggregator-sourced or unconfirmed; see the flagged block at the top of this section rather than
  repeating the detail here. Neither affects the dilution or inversion findings, which hold across the
  fund family regardless of which specific share class is the retail entry point.
- The ESMA final report's treatment of cat bonds is genuinely nuanced and contested within its own text -
  it names cat bonds as an example within a broader "large-scale alternative assets belong under AIFMD"
  argument, explicitly states its proposed look-through/10%-limit mechanism "does not affect investments
  in traditional company shares or bonds," and separately carries a disputed legal question (raised by one
  consultation respondent, contested by others) about whether cat bonds qualify as UCITS-eligible
  transferable securities at all. This note's characterization is drawn directly from the primary document
  (ESMA34-2087785638-1548, dated 26 June 2025, read in full via Exa fetch) plus the original October 2023
  Commission mandate letter and Artemis trade-press reporting on industry and ESMA-official reaction. What
  this note could not resolve, because the report itself does not appear to resolve it in the text
  located: whether ESMA's own "large-scale... AIFMD" conceptual view is meant to reach direct, ordinary
  bond-form holdings of cat bonds (like Twelve's and Schroder GAIA's) or only synthetic/wrapped indirect
  exposure. Treat the ESMA threat as real and unresolved, not as a specific, dated mechanism certain to
  bind the dedicated funds - the European Commission's eventual decision remains open and should be
  re-checked before this note is relied on for a final publication date.
- **CATB (the ETF) figures were independently re-verified for this pass rather than only carried from the
  brief; the aggregator-sourced ones among them are flagged in the block at the top of this section.**
  Net of the flagged items: the vault's 128bp TER is confirmed by two independent sources (HANetf's own
  factsheet page and justETF) against a conflicting 1.38% on TradingView, treated as the lower-confidence
  outlier; the ~12% discount to NAV is confirmed by a live TradingView price-vs-NAV read (USD 10.454
  against USD 11.86), despite the same page's auto-generated FAQ text inconsistently calling this a
  "premium" (the raw numbers are trusted over that auto-text); and the AUM trajectory (HANetf's own site
  at two dates plus Morningstar) shows real growth from ~USD 8.2m in April 2026 to ~USD 14.0-14.8m now,
  consistent with the vault's original "USD 12-14m" figure rather than contradicting it.[^catbver] One
  new, unconfirmed fact surfaced in this pass: a HANetf shareholder notice dated 16 April 2026 announces a
  "Change of the Investment Policy" for CATB; the notice PDF could not be fetched, and the fund's own KIID
  dated 1 May 2026 (post-dating the notice) shows an unremarkable policy (minimum 80% in cat bonds, broad
  peril/geography scope, active management), so this is recorded as an open item rather than a material
  finding.[^catbver]
- The claim that dedicated cat-bond UCITS funds are effectively equivalent to Tomunen's "specialist
  funds" is this note's own synthesis, not something either source states directly. It is a reasonable
  inference from Tomunen's definition (AUM of funds specializing in cat-bond risk-bearing) matching the
  observable structure of Twelve, Schroder GAIA, and peers, but it has not been checked against Tomunen's
  own data sample (insurancelinked.com AUM series) to confirm these specific UCITS vehicles were counted
  in his measure.
- This note answers the buildability question at the level of a EU-retail, long-only, UCITS-wrapped
  investor generally, consistent with the framing in [[the-ucits-constrained-carry-sleeve]]. It does not
  size a specific NAV threshold for the EUR 2,450-5,000 Demeter book described in
  [[income-must-accrue-not-be-captured]]; broker-level tradability (e.g. IBKR contract resolution and
  PRIIPs KID availability for the specific share classes named here) was not verified and is a
  precondition for any operational sizing decision, separate from this buildability verdict.

## Sources

[^tomunen]: Tomunen, T. (2026). "Failure to Share Natural Disaster Risk." *The Review of Financial
Studies*, 39(3), 661-701. https://doi.org/10.1093/rfs/hhaf055. Model result and empirical fit as
independently verified in
[[research/budgeting-convexity/_challenge-verification|the vault's prior challenge-verification audit]].

[^tomunenjmp]: Tomunen, T. (2019). "Failure to Share Natural Disaster Risk" [Job market paper].
https://wpcarey.asu.edu/sites/g/files/litvpz246/files/2021-11/tuomas_tomunen_seminar_paper.pdf - same
underlying study as [^tomunen] per the vault's prior verification. Direct quotes and figures used in §1:
"71% of the variation... financial intermediaries' marginal rate of substitution" (abstract); Table 3,
p.26-27, λ<sub>cat,t</sub> positive in all 16 years 2003-2018, range 1.02%-7.62%, time-series average
2.06%; §6.3, p.39, robustness across callable/earthquake-only/parametric-trigger subsamples, "stays at
around the 2% level"; §5.2, p.29, "the premium has decreased significantly after the financial crisis...
gradual but large inflow of new institutional capital into the specialist funds... the premium seems not
to have reacted strongly to the record losses of 2017... the funds were quickly able to raise new capital
to replace losses."

[^tomunenverif]: [[research/budgeting-convexity/_challenge-verification|Budgeting Convexity - external
challenge verification]] (2026-07-24), item 4, verdict VERIFIED against the RFS-published text.

[^ghw]: Gürtler, M., Hibbeln, M. & Winkelvos, C. (2016). "The Impact of the Financial Crisis and Natural
Catastrophes on CAT Bonds." *Journal of Risk and Insurance*, 83(3), 579-612.
https://doi.org/10.1111/jori.12057. VERIFIED in
[[research/budgeting-convexity/_challenge-verification|the prior audit]], item 7a.

[^cp]: Carayannopoulos, P. & Perez, M. F. (2015). "Diversification through Catastrophe Bonds: Lessons
from the Subprime Financial Crisis." *The Geneva Papers on Risk and Insurance*, 40(1), 1-28.
https://doi.org/10.1057/gpp.2014.14. VERIFIED in
[[research/budgeting-convexity/_challenge-verification|the prior audit]], item 7b.

[^lehmantrs]: S&P (30 September 2008) and A.M. Best (18 September 2008) rating-action reports on Ajax Re,
Newton Re, Carillon and Willow Re, republished via Artemis.bm and Insurance Journal/Claims Journal.
VERIFIED in [[research/budgeting-convexity/_challenge-verification|the prior audit]], item 7c, including
the rating-impairment-not-principal-loss precision.

[^role]: "The role of catastrophe bonds in an international multi-asset portfolio: Diversifier, hedge, or
safe haven?" *Finance Research Letters*.
https://www.sciencedirect.com/science/article/abs/pii/S1544612319302971 - already cited in
[[insurance-linked-securities-as-the-orthogonal-income-pole]] as [^role]; reused here as the source of the
correct replacement vocabulary.

[^svy]: Shleifer, A. & Vishny, R. W. (1997). "The Limits of Arbitrage." *The Journal of Finance*, 52(1),
35-55. General theory citation for the compress-to-cost-of-capital-not-zero prediction, as already used in
[[the-premium-is-rent-on-a-balance-sheet]].

[^esma]: ESMA (26 June 2025). "Final Report - Technical Advice to the European Commission on the review of
the UCITS Eligible Assets Directive." ESMA34-2087785638-1548.
https://www.esma.europa.eu/sites/default/files/2025-06/ESMA34-2087785638-1548_Final_report_on_the_Technical_Advice_on_the_review_of_the_UCITS_EAD.pdf
- para 77, "the look-through approach does not affect investments in traditional company shares or
bonds... [it] aims to limit the use of instruments (e.g. certain delta-one instruments, ETNs, ETCs, AIFs
etc.) that provide for exposures to alternative assets"; para 83, "large-scale investments in such
alternative assets with their idiosyncratic risks would be better done under the AIFMD framework"; paras
84-93 (10% limit for indirect exposures, transitional-provisions recommendation); Annex IV (cat-bond data
annex: "UCITS exposure: Cat bonds amount to ~0.1% of total UCITS NAV"; "UCITS catastrophe bond funds
allocate 88% of NAV to direct catastrophe bond exposure"; "Only 72 UCITS in EU invest in catastrophe
bonds, reflecting niche, concentrated market"; "Concentrated in a small number of specialised thematic
funds (72 UCITS), typically aimed at professional investors"; stakeholder consultation table, one
respondent arguing cat bonds "should not be allowed, as they are not related to a permissible asset under
Article 8(1)(a) EAD," others arguing exclusion is unjustified; "dedicated cat bonds UCITS consist only of
cat bonds and cash... cat bonds account for 85 - 97%... In one jurisdiction, cat bond UCITS can hold up to
100% of cat bonds"). Verified by direct fetch and local text extraction (2026-07-25) and independently
re-confirmed via Exa fetch of the same primary document (2026-07-25).

[^esmaplenum]: Artemis.bm, "Plenum urges European Commission not to adopt ESMA's UCITS cat bond
recommendation" (2026). https://www.artemis.bm/news/plenum-european-commission-esma-ucits-catastrophe-bond-recommendation/
- industry contestation, "CAT bonds have been successfully integrated into the UCITS ecosystem for more
than a decade," excluding them "neither justified by empirical evidence nor consistent with principles of
proportionality." Corroborated by Artemis.bm, "ESMA policy officer says 10%+ of cat bonds in UCITS funds
risks blurring lines with AIF" (28 November 2025).
https://www.artemis.bm/news/esma-policy-officer-says-10-of-cat-bonds-in-ucits-funds-risks-blurring-lines-with-aif/
- Kian Navid, ESMA senior policy officer for investment management, quoted via Euronews: "It is not that
ESMA's technical advice takes a position against retail investors accessing cat bonds per se... The
advice is not about outlining what constitutes a good or bad investment, but it provides data and risk
analyses for the European Commission's consideration," and separately, "conceptually, if you opened up
UCITS to alternative assets [like cat bonds] beyond 10%, that would risk blurring the lines between UCITS
and alternative investment funds (AIFs)." Same article: "other national regulators in Europe are not all
aligned with ESMA's view," and any change is expected to "take some years." Both verified by direct fetch
and independently re-confirmed via Exa fetch, 2026-07-25.

[^schroderfs]: Schroders Capital, "Schroder GAIA Cat Bond" investor presentation, dated 30 June / 1-5 July
2026. https://api.schroders.com/document-store/id/28f7c6bd-3341-43a7-856d-ff3731f96065 - "$3.9 billion,
only in tradeable ILS instruments"; "An active trading strategy"; "Effective portfolio construction at
the heart of the philosophy to filter transactions without sufficient risk/reward characteristics"; fund
launch 2 May 2011, "one of the first UCITS cat bond-only funds in the market"; annual performance by
year, 2013-2026 YTD (+10.87% 2025, +3.66% 2026 through June). Manager marketing material, high COI;
verified by direct fetch and local text extraction, 2026-07-25.

[^schroderfs2]: Same source as [^schroderfs] and Investing.com listings for Schroder GAIA Cat Bond IF
Accumulation USD (0P0001ZS3J) and IF Accumulation CHF Hedged (0P0001ZS3E), both showing a 1,000,000
minimum investment. Aggregator data, moderate confidence.

[^twelvefs]: Investing.com, Twelve Cat Bond Fund B EUR Acc (IE00BD2B9603).
https://www.investing.com/funds/ie00bd2b9603 - EUR 10,000 minimum investment, 1.73% TER, ~EUR 4.01bn
total assets, launched 5 June 2020. Aggregator data, moderate confidence - not cross-checked against
Twelve Capital's own KID. Fund objective language ("risk-adjusted returns by investing in Cat Bonds," "a
globally diversified portfolio of Cat Bonds") corroborated by fund description via web search, 2026-07-25.

[^twelvemerger]: Securis Catastrophe Bond Fund transferred into Twelve Capital UCITS ICAV via merger,
effective 26 January 2026, per Swiss Fund Data listing for Twelve Capital UCITS ICAV - Twelve Cat Bond
Fund SI2 GBP Acc. https://www.swissfunddata.ch/sfdpub/en/funds/docs/185047 - fund-roster update to the
names in [[insurance-linked-securities-as-the-orthogonal-income-pole]]'s investability section.

[^artemis19bn]: Artemis.bm, "UCITS catastrophe bond funds added $5.3bn+ in 2025, reaching $19.12bn AUM"
(9 January 2026). https://www.artemis.bm/news/ucits-catastrophe-bond-funds-added-5-3bn-in-2025-reaching-19-12bn-aum/
- $19.12bn combined AUM across "the now 18 UCITS cat bond funds that have reported data" as of end-2025,
+$5.3bn (~39%) over the year, 31% of the outstanding cat-bond market. Already verified in
[[insurance-linked-securities-as-the-orthogonal-income-pole]]'s own [^artemis] footnote (verified by fetch
2026-07-04) and independently re-confirmed via Exa fetch, 2026-07-25. This end-2025 figure is stale by the
time of writing; see [^artemisq1] and [^artemisapr] for the 2026 trajectory used in §3.

[^catbfootnote]: [[insurance-linked-securities-as-the-orthogonal-income-pole]]'s own [^catb] footnote and
[[income-must-accrue-not-be-captured]]'s CATB correction both scope the ESMA question to the KRC Cat Bond
UCITS ETF specifically. §3 above widens that scope to the fund universe on the strength of the ESMA
primary document.

[^tomunendoi]: Tomunen, T. "Failure to Share Natural Disaster Risk." *The Review of Financial Studies*,
published abstract resolved via DOI. https://doi.org/10.1093/rfs/hhaf055 - "I test whether asset prices
reflect risk exposures of financial intermediaries... I analyze catastrophe bonds whose cash flows are
linked to natural disasters and find that 71% of the security-level variation in expected returns can be
explained by a theoretically motivated measure of intermediaries' marginal utility... the aggregate
premium decreases and becomes less sensitive to the occurrence of disasters when intermediaries' access
to outside capital improves." Read directly via Exa web-fetch against the DOI resolver, 2026-07-25;
matches the RePEc/IDEAS listing for *Review of Financial Studies* 2026, Volume 39, Issue 3, pp. 661-701.
Full text beyond the abstract remains paywalled.

[^artemisq1]: Artemis.bm, "UCITS catastrophe bond funds surpassed milestone $20bn in AUM in Q1 2026"
(8 April 2026). https://www.artemis.bm/news/ucits-catastrophe-bond-funds-surpassed-milestone-20bn-in-aum-in-q1-2026/
- sector opened 2026 at ~$19.2bn, passed $20bn for the first time in February (~$20.09bn), closed Q1 2026
at ~$19.8bn across 20 funds, +3% for the quarter. Verified by Exa fetch, 2026-07-25.

[^artemisapr]: Artemis.bm, "UCITS cat bond fund assets rise 6.5% YTD in 2026, near $20.5bn after April"
(8 May 2026). https://www.artemis.bm/news/ucits-cat-bond-fund-assets-rise-6-5-ytd-in-2026-near-20-5bn-after-april/
- combined AUM ~$20.46bn as of 30 April 2026 across "twenty pure UCITS catastrophe bond funds"; six funds
with over $1bn each contribute $16.6bn, 81% of the sector. Verified by Exa fetch, 2026-07-25.

[^artemisq2]: Artemis.bm, "Q2 2026 Catastrophe Bond & ILS Market Report" (July 2026).
https://www.artemis.bm/wp-content/uploads/2026/07/catastrophe-bond-ils-market-report-q2-2026.pdf - record
H1 2026 issuance of ~$17.98bn (beating the prior H1 record of $17.6bn in 2025); outstanding cat bond
market reached $65.6bn at end-Q2 2026, up from $61.3bn at end-2025. Cited as broader-market context for
continued 2026 inflows rather than a UCITS-fund-specific AUM figure. Verified by Exa fetch, 2026-07-25.

[^artemisjun]: Artemis.bm, "Cat bond fund UCITS average 0.62% return in June. 12-month rolling-return
10.22%" (6 July 2026). https://www.artemis.bm/news/cat-bond-fund-ucits-average-0-62-return-in-june-12-month-rolling-return-10-22/
- Plenum CAT Bond UCITS Fund Indices: June 2026 average return 0.62%, H1 2026 YTD 2.91%, rolling
twelve-month average 10.22% as of 26 June 2026 (versus 11.69% a year earlier). Verified by Exa fetch,
2026-07-25.

[^esmamandate]: European Commission, "Formal request to ESMA for technical advice on the review of
Commission Directive 2007/16/EC on UCITS eligible assets" (June 2023).
https://www.esma.europa.eu/sites/default/files/2023-06/Formal_request_to_ESMA_-_Mandate_UCITS_EAD_review.pdf
- mandate issued June 2023, requesting ESMA "deliver its technical advice by 31 October 2024"; the advice
was not in fact published until 26 June 2025, eight months late. Verified by Exa fetch, 2026-07-25.

[^catbver]: Re-verification sources for the CATB (KRC Cat Bond UCITS ETF, IE000UWJUW87) figures carried
from [[income-must-accrue-not-be-captured]]: HANetf's own fund page, https://hanetf.com/fund/catb-cat-bond-etf/
(TER 128bp, Net Assets $14,000,598, undated/current) and its French-locale mirror
https://hanetf.com/fr/fund/catb-cat-bond-etf/ (same TER, Net Assets $8,179,104 "as of 22.04.2026");
HANetf KIID dated 1 May 2026, https://hanetf.com/wp-content/assets/upload/kiid-CATB-IE000UWJUW87-en-GB.pdf
(minimum 80% of net assets in Cat Bonds); justETF, https://www.justetf.com/en/etf-profile.html?isin=IE000UWJUW87
(TER 1.28% p.a., fund size EUR 10m); Morningstar via lt.morningstar.com fund snapshot (Net Assets $14.02m
as of 14/07/2026, Ongoing Cost 1.28%); TradingView, https://www.tradingview.com/symbols/LSE-CATB/ (live
snapshot: price $10.454 vs NAV $11.86, "-12.2%" discount statistic, AUM $14.79M, expense ratio shown as
1.38% - the outlier TER figure on this page). All verified by Exa fetch, 2026-07-25.
