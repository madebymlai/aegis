---
title: "Income Engine - Stage 4.5 final integrity"
date: 2026-07-27
tags:
  - integrity
  - income-engine
---

# Stage 4.5 final integrity - income engine

Verification of the complete eight-section draft. Stage 2.5's three passes checked the *plan*; this pass checks
the *prose*. **Status: PASSED**, with two disclosed limits and two items owed.

## Summary

**Status: PASSED**, with two disclosed limits and two items owed. Updated after bibliographic verification
returned.

| Class | Count |
|---|---|
| Checks passed | 12 |
| Reference entries, all fields verified | 23 |
| Defects found and fixed in this pass | 9 |
| Blocking, now resolved | 1 |
| Disclosed limits carried into the paper | 2 |
| Owed before submission, non-blocking | 2 |
| Body word count | 6,994 |
| Abstract | 314 |

## B1 RESOLVED, and the register was stale rather than the plan fabricated

**Dick-Nielsen, J., & Rossi, M. (2019). The cost of immediacy for corporate bonds. *Review of Financial Studies,
32*(1), 1-41. https://doi.org/10.1093/rfs/hhy080.** Every field independently confirmed against the DOI
resolver, RePEc, an institutional repository record, and the typeset article PDF.

This pass raised the possibility that `_plan.md` D6.2 had invented "2019, RFS 32(1)" because `_sources.md`
recorded the citation as incomplete with an instruction not to fill the gap. **That suspicion was wrong. The plan
was correct and the register was stale.** Recording it plainly because the reverse error, trusting a decision
block over a verification register, is the one this project has actually made before.

All three dependent sub-claims confirmed in the published text:

- The quoted phrase appears verbatim: "these returns are not replicable by other investors in the economy, who
  would face a possibly large bid-ask spread to implement the strategy of buying at the exclusion date and
  selling afterward." One caution now known: a 2014 working-paper draft read "not **easily** replicable"; the
  published text drops "easily", and this paper quotes the published form.
- The paper separates exclusion reasons and runs downgrade against low-maturity comparisons throughout.
- **The claim D6.2's derivation of the convexity clause depends on holds**: "For downgraded exclusions, only
  around two-thirds of the bonds have been sold after 100 days", and costs are higher for downgrades "because
  the downgraded bonds are both more risky and kept longer on inventory." Had this failed it would have reached
  Section 3's argument, not merely its footnotes.

## References list

**Twenty-three entries, all fields verified against primary or publisher sources.** In-text to list reconciliation
runs clean in both directions: nothing cited is absent from the list, nothing listed is uncited.

Two fields were deliberately omitted rather than filled:

- The BIS box's page range. The only page numbers located came from the ECB's citation of the box rather than
  from BIS's own pagination, so the entry carries no page range and says why.
- Bassi et al.'s sample-period sentence remains unread in the paywalled final text. The bibliographic entry is
  fully verified via RePEc; the paper cites the mechanism only, and the contraction magnitudes are not quoted.

## Passed

1. **Prohibited terms: all absent.** Nine checks, zero hits: "the seat", "the funder", the section symbol, em
   dashes, Bassi et al.'s embargoed contraction figures, "investor-reachable", "fallen angel", "unevidenced to
   contradicted".
2. **①'s hedges travel with its reused source.** All three attached to Dew-Becker and Giglio (2025) are present in
   Section 4: daily delta-hedged synthetics "cannot span a jump by construction", the Bates (2022) dispute over
   the break date, and "what survives is the direction, not a date".
3. **No measurement leakage.** Zero hits for `delta_theta`, the paired-book metric's symbol, `earns_its_seat`,
   "we measure", "our results", "backtest", "Sharpe". The paper reports no measurement.
4. **No wikilinks in the body.** Conventions match ①: prose cross-references, APA author-date inline.
5. **Clause numbering consistent** across abstract, Section 1, Section 5 and Section 8, with the first clause
   stated as ex-ante in all four (RM-6).
6. **The asymmetry is never written as mutual in the indicative** (D16c's prohibition).
7. **The falsifier is stated and distinguished from a failed candidate**, closing D13's equivocation.
8. **Both structural failure routes present**, neither reachable by accumulation (RM-8).
9. **Word counts computed, not estimated** (D17). Body total 6,542.
10. **In-text to reference-list reconciliation clean in both directions.**
11. **Cross-references to ① disambiguated**; see F1.
12. **Every quoted figure traced to a publisher or primary source**; two were excluded on that basis.

## Defects found and fixed before verification returned

**F1. Cross-references to ① were ambiguous, and one was actively misleading.** Our sections are integers, ①'s are
sub-numbered, but the convention was undeclared, and Section 2 contained the bare reference "(Section 2)" meaning
**①'s** Section 2 while sitting inside **our** Section 2. Five references now name the architecture paper
explicitly.

**F2. A flag was attached to a figure never quoted.** Section 4 said Tomunen's year-by-year magnitudes "carry that
flag" when no magnitude appeared. Corrected.

**F3. A critique was gestured at rather than named** (RM-12). Gospodinov and Robotti (2021) now named, with the
load-bearing claim distinguished from the fit statistic the critique reaches.

**F4. An attribution was missing.** The jump-driven compensation finding now attributed to Bollerslev and Todorov
(2011).

## Owed before submission, non-blocking

**O1 CLOSED, and closing it changed Section 7 rather than just footnoting it.** The claim is now sourced three
ways: the equilibrium logic to Grossman and Miller (1988), the supply-side confirmation to Comerton-Forde et al.
(2010), and, most importantly, the **concentration** claim to Nagel (2012), which directly tests state-contingent
income rather than average level and finds expected returns and conditional Sharpe ratios rising sharply with
implied volatility.

Two consequences that were not anticipated:

- **One step remains the paper's own and is now marked as such.** No source partitions liquidity-provision income
  into *calm* versus *choppy* as two distinct low-income regimes, which is how Section 1's contract frames the
  responder's bleed. The evidence conditions on a single stress proxy. Section 7 states that the finer partition
  is this paper's extrapolation.
- **A genuine counterexample was found and it produced a second rejection ground.** In the fastest
  funding-constrained episodes the income inverts: a simulated market-making strategy profitable before and after
  the August 2007 deleveraging lost significantly through the acute week, because the supplier was compelled to
  unwind rather than free to charge more (Khandani & Lo, 2011), which is what a funding-constrained model predicts
  (Brunnermeier & Pedersen, 2009). So the concentration claim holds **on average across stress states, not in
  every one.** That does not rescue the candidate: the inversion puts its worst losses in the fast segment the
  tier above already owns, so Section 6's collision applies too, and the behaviour now fails on **both** the
  timing of its income and the placement of its loss.

**A related addition to Section 5.** The same funding-constraint model supplies a mechanism for this engine's own
protracted-state loss being unbounded, which Section 5 previously argued only from an absence of evidence. A
short-convexity position held under margin constraints may have to be reduced as stress deepens, so realised
returns are negatively skewed rather than compensation elevated. Section 5 names it as an argument, not a
measurement.

**Two commercial affiliations arrived with these citations and are disclosed at the entries themselves**: one
author is a principal at a large systematic asset manager, another chairs a quantitative asset manager. Both are
cited for a theoretical prediction and a documented episode respectively, not for point estimates. The disclosure
section now names this.

**O2. The abstract is 315 words** against ①'s 248. Common caps are 250 to 300. The target venue is not set in the
Paper Configuration Record, so the required trim is not determinable yet.

**O3 CLOSED.** The disclosure is written and states that the central contribution claim was proposed by an AI
editorial process at the authors' explicit request and is not author-formed. It sits in the body rather than an
acknowledgement, because it concerns the thesis.

**O4 CLOSED.** Reconciliation run; see above.

**O5. Companion-paper citations are owed.** The architecture paper and the responder study are referred to in
prose but have no reference entries, because their authorship is not established in this session. **Do not invent
it.** Add the entries when it is set.

## Four further defects found and fixed after verification returned

**F5. Chen, Joslin and Ni was cited as "forthcoming". It has been in *RFS* since January 2019**, coincidentally
the same volume and issue as Dick-Nielsen and Rossi. Corrected.

**F6. The BIS box was cited institutionally as "(BIS, 2024)". It is bylined** to Todorov and Vilkov. Corrected to
an authored citation, which also gives the finding its proper attribution.

**F7. "(ECB, 2024)" was an unexpanded abbreviation.** Corrected to European Central Bank, whose box carries no
individual byline.

**F8. Jurek's headline figures were stale, and the published claim is stronger.** Section 4 previously said
crash-neutral carry "remains significantly profitable", resting on a 3.18 to 5.31 percent range recorded in
`_plan.md` D1. Those figures come from a **2008 conference draft**; a 2009 redraft reports 3.85 and 6.55 percent,
and the final 2014 *JFE* paper uses a different sample and reports different quantities again. Section 4 now
carries the published abstract's own claim, that **crash risk premia account for at most one third of the excess
return**, which is both verified and a sharper statement of the point. D1 carries a flag so a later pass does not
retrieve the stale figure.

## F9. A formatting defect I introduced, found by the reconciliation check

Span-level rewrapping during editing split hyphenated compounds across lines. **Markdown joins wrapped lines with
a space, so `Comerton-Forde` would have rendered as `Comerton- Forde`**, and two further compounds were affected.
It surfaced only because the citation-to-reference reconciliation reported "Comerton- Forde et al." as an
unmatched surname, which looked like a bibliography error and was a typography error.

Repaired at the raw-text level, then the whole body rewrapped with hyphen breaking disabled. Zero lines now end in
a letter followed by a hyphen. **Worth keeping as a check**: a reconciliation script that compares in-text
surnames against list entries also catches line-break damage to names, which no spell or link check would.

## Final state

| | |
|---|---|
| Body | 6,994 words across eight sections |
| Abstract | 314 words |
| Disclosure | present, names the contribution's provenance and three commercial affiliations |
| References | 23 entries, every field verified, reconciliation clean both directions |
| Budget | 6,600; actual is about 7 percent over, reason recorded in D20 and here |

**Why the paper exceeds its budget.** Two sections grew because verification required it: Section 7 had to source a
claim it had asserted, and the counterexample that arrived with the source produced a second rejection ground;
Section 5 gained a mechanism for the loss channel it had previously argued only from absence of evidence. Neither
was padding and the map was not re-priced again.

## Still open, and neither is mine to close

1. **The abstract's required length depends on a target venue**, which the Paper Configuration Record does not
   name. Common caps are 250 to 300 against the current 314.
2. **Companion-paper reference entries for the architecture paper and the responder study** are owed once their
   authorship is established. It was not invented.
