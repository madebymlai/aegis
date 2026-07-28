---
title: "RM-28 - the capacity-provision test against the rest of the register"
date: 2026-07-25
topic: income-engine
status: research-note
related:
  - "[[the-premium-is-rent-on-a-balance-sheet]]"
  - "[[window-dressing-at-the-regulatory-snapshot]]"
  - "[[income-must-accrue-not-be-captured]]"
  - "[[research/income-engine/_plan|_plan]]"
  - "[[research/income-engine/_review|_review]]"
tags:
  - note
  - income-engine
  - register
  - RM-28
---

# RM-28 - the capacity-provision test against the rest of the register

## Verdict

The two-test admission criterion (D6.1's convexity clause, plus the capacity-provision test the
convergence ruling in [[research/income-engine/_review|_review]] adds) was run against eight
register entries beyond the two already reconciled (window dressing, index-exclusion
warehousing). **None of the eight counters the generalisation. None of them newly confirms it
either.** Five fail one of the criterion's own prior gates before the capacity-provision question
is even reached - three because they turn out to be circumstance-compelled rather than durable
and non-substitutable, two because they fail the convexity clause outright. One tests a different
question entirely (D6.2's direction term). One remains genuinely indeterminate on the evidence
available. One - bank significant risk transfer - is a contested near-miss that the paper must
name rather than resolve by definitional convenience.

**The scope condition the paper should carry, in one sentence:** the capacity-provision
generalisation holds over the subset of compelled behaviours that clear a prior durability gate
(rule-compelled, not relaxable by added capital) and a convexity gate (genuinely carrying a crash
inventory, not a vacuous spread); most of the register's remaining entries do not fail the test,
they never reach it, because they are circumstance-compelled or convexity-free before the
capacity question arises - so the generalisation's tested population is the two cases already
reconciled, not the wider page count of the register.

This verdict excludes the spot-versus-futures crypto venue wedge from its evidence base. See the
next section.

## Scope limitation: the crypto venue wedge was withdrawn from testing

The editor's brief for RM-28 named the spot-versus-futures crypto venue wedge as the sharpest
available test of the generalisation, on the reasoning that the compensated party there might be
holding directional price risk through a window others cannot access rather than supplying
capacity to anyone. On instruction from the team lead, **that case was withdrawn from this sweep
before any verification work was done on it here** - no attribution check, no primary-source
read, no classification against the two-test criterion.

**Disclosure sentence the paper can carry:** *This test of the capacity-provision generalisation
excludes the spot-versus-futures crypto venue wedge, the single case the paper's own editor
identified as the sharpest available counter-example candidate; excluding the case most likely to
defeat a structural claim is a methodologically loaded choice, and the generalisation below is
stated as holding across the cases actually tested, not across the full register.*

One observation worth recording without leaning on it: the register's own "what is being rented"
table already glosses this case as renting "margin in two segmented venues at once," which reads
as capacity-provision on its face and would, if it held up against the primary source, have
confirmed the generalisation rather than countered it. That is a reason the exclusion may cost the
paper little. It is not a substitute for having tested it, and it should not be cited as if the
case were resolved.

## Method: three gates, not one test

The brief's two-test criterion turns out to presuppose a prior classification the corpus already
has and had not yet applied systematically outside window dressing and index-exclusion
warehousing. Applying it case by case surfaces the same funnel each time, so it is stated once
here rather than re-derived eight times.

1. **Entry gate.** Is there an identifiable compelled action and a named compensated party - a
   behaviour, not a bare price effect or a strategy label? ([[research/README|research/README]]'s
   standard.)
2. **Durability gate (D5, sharpened by RM-14).** Is the compulsion rule-compelled - a rule that
   bars a class of holder outright, not relaxable by that class raising more capital - or
   circumstance-compelled - a constraint that scales with capital and relaxes as more of it
   arrives? Only the first is the durable, non-substitutable population the "regardless of
   occupant" claim is about. Circumstance-compelled cases are expected to compress and are not
   counter-examples when they don't.
3. **Convexity gate (D6.1).** Does the compensation carry a crash inventory, or does it satisfy
   loss-placement vacuously - a spread with almost nothing to place?
4. **Capacity-provision gate (D9).** Only for cases that clear 1 through 3: is the compensated
   function risk-bearing, which a portfolio seat performs by definition, or capacity-provision -
   financing, warehousing, market-presence or balance-sheet services a risk-bearing allocation
   cannot supply?

A case can fail at gate 2 or 3 without saying anything about gate 4. That distinction is the
finding this sweep mostly returns.

## The case table

Each row is named for the compelled action, per the altitude discipline in
[[research/income-engine/_plan|_plan]] D6.2 ("An index rule compels a tracker to sell an
excluded bond" passes; "fallen angels" does not). The anomaly label the literature files it under
is given only as a cross-reference.

| # | Compelled action (anomaly label) | Compelled party | Compensated party | What compensation is FOR | Rule- or circumstance-compelled | Convexity | Verdict |
|---|---|---|---|---|---|---|---|
| 1 | A leveraged holder must finance a position its own balance sheet cannot fund (Treasury cash-futures basis) | Bank dealers, whose SLR/eSLR-constrained balance sheets cannot elastically expand repo lending against growing Treasury supply | Relative-value hedge funds that "serve as warehouses for Treasuries... funding them in the repo market" | Warehousing plus repo financing - capacity-provision on its face | **Circumstance** - a leverage ratio relaxable by more capital; eSLR relaxed 1 Apr 2026; hedge-fund AUM in this trade grew from niche to ~$400-500bn since 2016, the substitution signature | Yes - March 2020 unwind, documented margin-call/deleveraging risk | **Out of population** (fails gate 2); would have confirmed the generalisation had it cleared |
| 2 | A bank must hold capital against a loan book regardless of its own risk view, so it pays a third party to hold the junior slice (significant risk transfer) | The originating bank, bound by CRR risk-weighted capital formulas (Art. 244/245) | The SRT investor / protection seller, who "will compensate the Bank if losses occur" | Bearing tail credit loss on a defined tranche; ESRB states synthetic securitisation explicitly "does not provide originator banks with funding" - the loans, servicing and customer relationship stay with the bank | **Contested.** Weight of evidence (Solvency II cost-of-capital cut by "legislative fiat," longevity capacity "still expanding," Osberghaus & Schepens 2025 showing selection by regulatory rather than economic risk weight) favours circumstance-compelled | Yes, unambiguously - mezzanine/first-loss tranches are textbook loss-absorbing | **Near-miss, genuinely contested** - see below |
| 3 | An issuer must place a large block into a segmented buyer base on a fixed date, so it concedes price (corporate bond primary-market issuance premium) | The issuing firm, facing underwriter market power and price-inelastic same-day demand | Primary-market investors, disproportionately short-term "flippers" who resell within days (~20% of allocation) | Allocation access via underwriter relationships / bookbuilding participation, not held price risk | Neither cleanly - relationship-gated access, not a codified bar or a capital-scaling charge; a taxonomy gap, not a clean classification | **Fails** - a same-week flip is a spread with almost nothing to place | **Fails entry criterion** (convexity) before the capacity question is reached |
| 4 | A dealer cannot expand its balance sheet across currencies (covered interest parity deviation) | End-investors who "cannot directly borrow" in the funding currency and must hedge; dealer banks intermediating face convex balance-sheet costs | The dealer/intermediary bank, paid the basis for "renting" balance-sheet space across currencies | Balance-sheet/financing capacity across two currencies - capacity-provision on its face | **Circumstance** - balance-sheet costs scale with position size; the vault's own prior finding already shows EUR/USD CIP "largely compressed" (1-3bp late 2024 vs -20bp trailing average) | Yes - imperfectly hedged books, documented dislocations in 2008 and 2020 | **Out of population** (fails gate 2) for the best-evidenced pair; would have confirmed the generalisation had it cleared. Less-liquid pairs not tested |
| 5 | Primary dealers must absorb mandated supply on a published calendar (Treasury auction cycle price pressure) | Primary dealers, obligated by dealer status to bid every auction regardless of risk appetite | Diffusely, "arbitrageurs and end-investors," explicitly undersized relative to the auction | Bearing short-term price risk around a predictable calendar event; the source's own language is "limited risk-bearing capacity," not financing capacity | **Mixed** - dealer obligation is a durable status rule, but the compensated function is open to any risk-bearing capital, not restricted by rule to a narrow class | **Unclear** - a small, mean-reverting pattern (9-18bp) with no demonstrated crash state in the primary source | **Indeterminate** |
| 6 | A glidepath rule compels a fund to sell what rose (target-date fund contrarian rebalancing) | The target-date fund, bound by its own disclosed mandate | Whoever buys strength - the responder, per D6.2's own table | Not applicable to this test - pays the trend/momentum seat this book already runs, not the seat under RM-28's test | Rule-compelled, durable (the mandate is the trading rule) | Not reached | **Out of scope** - tests D6.2's direction term, already resolved, not D9's capacity test |
| 7 | Institutions must meet month-end payment obligations irrespective of price (dash for cash) | Institutions with month-end cash obligations, bound by the 3-day settlement convention | Diffusely, "speculators and market makers"; the source's own emphasis is on costs borne by the compelled institutions (~$30.6bn/year) rather than a named compensated party | To the extent identifiable, ordinary short-horizon liquidity provision, not a named capacity service | Calendar/settlement-driven, durable in timing, but open to any capital | **Likely fails** - a repeated, modest, mean-reverting pattern, no crash-inventory framing | **Likely fails entry criterion** (convexity), same shape as #3 |
| 8 | Foreign investors are legally barred from holding beyond a statutory limit (foreign-ownership-limit price premia) | Foreign investors, barred by statute from holding beyond a fixed ceiling | In most non-China regimes, domestic investors, who hold the unrestricted class at a discount to what foreign investors pay | A pure segmented-access price level - no financing, warehousing, market-making or distribution function identified | **Rule-compelled**, cleanly - the paradigm eligibility bar - but moot given the next column | **Fails outright** - a static cross-sectional price gap, no loss-placement dimension | **Fails entry criterion** (convexity). Also evidentially stale - only pre-2018 sources located, confirming the register's own caveat |

## Bank significant risk transfer, treated at length as the decisive contested case

This is the case the sweep did not expect to be decisive. Unlike the other seven, its classifier
tension is genuine rather than an artefact of thin evidence, and the paper cannot resolve it by
picking whichever reading is convenient.

**Why it looks risk-bearing, cleanly.** Per the ECB and ESRB's own primary account (Osberghaus &
Schepens 2025; the 2023 ESRB occasional paper on the European SRT market), a synthetic risk
transfer does not move the underlying loans anywhere. The bank keeps originating, servicing and
holding the customer relationship. What moves is a funded credit-linked note or CDS referencing a
tranche of expected losses, and the investor "will compensate the Bank if losses occur." The
ESRB's own text states plainly that synthetic securitisation "does not provide originator banks
with funding." There is no financing being extended, no inventory being warehoused, no market
being made and no distribution network being run - the investor posts collateral against a defined
loss distribution and is paid a spread for bearing it. That is a funded credit derivative, and a
risk-bearing portfolio seat can hold one directly. [[income-must-accrue-not-be-captured]] already
records a live instance: TwentyFour Income Fund is a retail-accessible, portfolio-shaped vehicle
that discloses named SRT deals and holds them as ordinary risk-bearing positions. This is not a
hypothetical occupant; it exists today.

**Why the weight of evidence still classifies it as circumstance-compelled.** Applying RM-14's own
operational test - does the rule bar a class of holder outright, or does it scale with capital and
relax as more arrives - the answer for bank capital requirements is the latter. A bank is never
legally barred from holding these loans; it must hold proportionally more regulatory capital
against them, and that requirement is a policy dial in exactly the sense
[[the-premium-is-rent-on-a-balance-sheet]] already documented for this family before RM-28 began:
the Solvency II cost-of-capital rate is being cut from 6% to 4.75% "by legislative fiat" effective
January 2027; longevity reinsurance capacity is "still expanding" rather than saturated; Meyricke
and Sherris find Solvency II actually *disincentivises* transferring high-age longevity risk. The
new evidence gathered for this sweep sharpens the same picture from the bank side: Osberghaus and
Schepens (ECB working paper 3210) exploit a discontinuity in risk weights (the EU "SME supporting
factor") and find banks select loans for synthetic transfer by regulatory risk weight relative to
economic risk, which is a capital-optimisation signature, not an eligibility-bar signature. The
market itself has grown roughly fivefold in six years (EUR 60bn to EUR 300bn, 2018-2024 per the
same working paper) precisely as capital rules tightened and eased on different dials, consistent
with capacity scarcity rather than a fixed bar.

**What this means for the paper, stated without resolving it for the authors.** If bank capital
charges are circumstance-compelled - the reading the evidence currently favours - SRT falls out of
the durable, non-substitutable population the "regardless of occupant" claim is about, the same
way the Treasury financing case and the CIP case do, and the fact that its compensated function is
risk-bearing is uninteresting: a substitutable premium being risk-bearing is exactly what the
paper predicts, since D5's own architecture holds that circumstance-compelled premia are the class
a risk-bearing seat *can* occupy. But if a future referee or a closer reading of the CRR's Article
244/245 commensurate-transfer test finds a harder eligibility-bar core inside the capital-charge
mechanism than RM-14's blunt operational test currently credits, this is the register's most
serious counter-example candidate, because unlike every other durable case in the register, its
compensated function is not even arguably capacity-provision. The paper should name this tension
explicitly rather than let RM-2's prose imply the classification is settled. Recommended language:
*"Bank capital requirements are treated here as circumstance-compelled per the operational test in
[section], consistent with the observed compression of capital-relief pricing under policy easing;
this classification, not the mechanism's evidence quality, is what keeps significant risk transfer
out of the tested population, and a reader who classifies bank capital charges as an eligibility
bar rather than a capacity-scarcity rule should read significant risk transfer as an open
counter-example rather than a closed case."*

## Counter-examples and indeterminates, and what each costs the paper

**No clean counter-example was found among the eight.** That is different from the generalisation
being confirmed eight further times; see the verdict above.

**Bank significant risk transfer (case 2)** is the one item the paper cannot treat as closed. Cost
if left unaddressed: a referee who disagrees with the circumstance-compelled classification gets a
free counter-example, because the compensated function is undeniably risk-bearing on the primary
sources' own account. Cost of addressing it properly: one paragraph, drafted above, that states the
classification and its evidentiary basis rather than assuming it.

**Treasury auction cycle pressure (case 5)** is indeterminate rather than resolved. Its compelled
party is durably rule-bound (dealer status), but its compensated party is diffuse and its
convexity is unproven in the primary literature. Cost if cited as either a confirmation or a
counter-example: overclaiming in either direction. The honest move is to leave it out of both the
confirming and the countering lists and say why.

**The corporate-bond issuance premium and dash-for-cash cases (3 and 7)** share a shape: a
compelled party, a plausible but diffuse compensated party, and a compensation stream that looks
captured by short-horizon trading rather than held through a crash window. Both plausibly fail
D6.1's convexity clause for the same reason window dressing originally needed the clause restored -
a spread with almost nothing to place is not the same as an inventory placed well. Cost to the
paper: none directly, since neither reaches the capacity-provision question either way, but they
are useful negative evidence that the convexity gate is doing real work rather than being trivially
satisfied by anything labelled "compelled."

**Target-date fund rebalancing (case 6)** costs the paper nothing new; it corroborates D6.2's
already-settled direction term (this flow pays the responder, not this seat) rather than testing
the capacity-provision question at all. Worth flagging only so a reader does not mistake its
absence from the confirming column for a gap.

**Foreign-ownership-limit premia (case 8)** fails the convexity gate outright and is evidentially
stale, exactly as the register already flagged before this sweep began. Nothing new here beyond
confirming the register's own caveat with fresh search.

## Additional register entries screened, not deeply tested

The team lead's brief asked for the named eight plus anything else the register lists. The
remaining entries were screened against the register's own text rather than given fresh primary
research, because the register itself already states why each fails the entry gate or is not yet
testable, and re-deriving that with new sources would not change the answer:

- **Attention-induced retail trading and reversal.** The register's own words: "a persistent
  friction rather than a compelled-flow story." Fails the entry gate by the register's own
  account - there is no compelled party.
- **Debt-ceiling bill-supply distortion.** Dated to a specific 2024 episode and confined to the
  corporate-credit leg; not tested here for the same reason it was not pursued originally
  (crisis-adjacent, narrow venue).
- **LDI-style fire sales.** The register calls this "explicitly a crisis-state phenomenon," which
  fails the four-clause contract's own first clause (earn a positive expected return in *ordinary*
  markets) before any capacity question arises.
- **Capital-gains lock-in.** No clean two-sided compelled/compensated structure is described
  anywhere in the corpus; this is a single-investor tax distortion, not a behaviour with a named
  payer.
- **T+1 settlement reaching the UK and EU, 11 October 2027.** The register's own words: "no
  specific behaviour has been attached to it yet." Not testable until one is.
- **Overnight and extended-hours price discovery migration.** No compelled action or named payer
  identified anywhere in the corpus.

None of these six was worth an Exa call under the effort this sweep was given; each is closed on
the register's own text.

## Limitations

**The crypto venue wedge is untested here, on instruction, and the paper must not read this note
as having resolved it.** See the scope-limitation section above. Whatever this note's verdict says
about the other eight, it says nothing about that case, and the disclosure sentence provided should
travel with any use of this note's verdict line.

**Bank significant risk transfer's classification is a judgment call under genuine uncertainty, not
a settled fact.** The evidence for circumstance-compelled is the weight of the corpus's prior
findings plus one new working paper (Osberghaus & Schepens); it is not a proof, and RM-14's
operational test itself is a blunt instrument the paper has not yet stress-tested against a case
this close to the line. Treat the recommended language above as a starting draft, not a closed
determination.

**Treasury auction cycle pressure could not be resolved from the primary literature available in
the time this sweep had**, specifically on whether the compensated activity carries a genuine crash
inventory. A dedicated search for a crisis-episode study of this specific mechanism (rather than
the calm-period average effect Lou-Yan-Zhang document) might close this; none was found.

**The corporate-bond issuance premium and dash-for-cash verdicts rest on inference from investor
holding periods (days) rather than a primary source that directly states the compensation is
captured rather than accrued.** This inference follows the vault's own accrual-versus-capture
screen in [[income-must-accrue-not-be-captured]], applied here to a different question (the
convexity clause) than the one it was built for (retail cost-floor viability), and that transfer
should be checked rather than assumed sound.

**Coverage is eight named cases plus six screened-and-closed entries, not the full space of
compelled market behaviours.** A structural claim resting on "regardless of occupant" is
falsifiable by a single clean counter-example the corpus has not yet searched for. This sweep
narrows where one might be hiding; it does not prove none exists.
