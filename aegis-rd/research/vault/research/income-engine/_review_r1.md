---
title: "Convergent Income Engine - Reviewer 1 report (empirical and intermediary-based asset pricing)"
date: 2026-07-25
tags:
  - review
  - income-engine
  - peer-review
---

# Reviewer 1 report

Reviewing the plan for "The Convergent Income Engine: Funding the Book Through Ordinary Markets" as an
independent referee with expertise in empirical asset pricing and intermediary-based asset pricing. This
report was drafted from `_plan.md`, `_synthesis.md`, `_sources.md`, `_buildability.md`, `research/README`,
and budgeting-convexity §2.2/§4 (①), forming an independent view before reading the authors' own internal
stress test, `_argument.md`. The novelty statement at the end identifies what is new relative to that pass.

## Recommendation: Major Revision

The economic architecture is serious and the plan already shows real self-correcting discipline: D4, D6,
D7, and D8 read as a genuine audit trail of repairs made under pressure, not as decoration. Nothing here
sinks the project. But several load-bearing pieces of the argument currently rest on economic distinctions
that are asserted at a coarser grain than the underlying literature supports, and each of these needs to be
sharpened, or explicitly scoped as unresolved, before the draft can carry the weight the plan wants to put
on it. The payer story blends three distinct intermediation mechanisms under one "capacity binds" label
without showing they behave alike. The venue-indexed crash-share claim (D1) may be confounding a
payoff-convexity effect with a venue effect. The forward-cap repair in D7, while conceptually the right
move, rests on an instrument whose adequacy for bounding tail losses is admittedly unargued. And Kargar's
plurality finding, genuine as it is, is being asked to generalize from one crisis episode to a
cross-market architecture. None of this requires abandoning D1 through D8. It requires the drafting stage
to either close these gaps or state them as open, in the same honest register the plan already uses for
Bassi et al. and Jurek-Xu.

## Summary of the paper's claim, in my own words

The paper argues that the "convergent" sleeve of a multi-strategy book, the leg that sells convexity for
calm-market carry, is best understood not as any particular trading mechanism (FX carry, credit spread,
option premium, catastrophe risk transfer) but as a portfolio **role**: something that earns a positive
expected return in ordinary markets, sells convexity so that it genuinely carries crash inventory, places
that inventory's loss where the book's convex responder pole is not simultaneously failing, and is judged
by its marginal contribution to the paired book rather than by its own standalone smoothness. It adopts,
from the companion architecture paper (①), the claim that this role is paid because an intermediary's
capacity to bear unhedgeable risk binds somewhere, and it needs only be paid a fair price for that risk,
not an excess one, for the role to be worth holding. Its central analytical move (D5) sorts the ways a
counterparty can be compelled to transact against this seat into two classes: rule-compelled (a rule bars
a specific kind of holder, so arriving capital is the wrong kind and the premium survives) and
circumstance-compelled (a need any capital can meet, so the premium compresses toward the marginal
arbitrageur's cost of capital). It argues the seat's actual occupants are drawn mostly from the second
class, which converts a compressed, unglamorous premium from disappointment into the designed equilibrium
rather than an unlucky draw. Because whether a premium is fair cannot be verified on realized returns (the
peso problem), the paper responds by admitting candidates on ex-ante economic rationale, refusing to claim
its metric (ΔΘ̂) verifies adequacy, and proposing instead to bound the risk with a forward cap, so that
being wrong about adequacy costs return rather than solvency.

## Major concerns

### 1. The payer story blends three distinct intermediation mechanisms under one label

① §2.2's sentence, that the short pole "is paid for bearing unhedgeable risk where the intermediary's
capacity binds, and the size of that payment tracks the constraint," is doing service in this paper's
corpus for at least three mechanisms that are not interchangeable. First, demand-pressure or inventory-risk
pricing, where a market maker with imperfect hedging ability must be paid to absorb an order imbalance
(Garleanu, Pedersen and Poteshman). This is a partial-equilibrium result about specific option-market
segments. Second, capital-constrained stochastic-discount-factor pricing, where an intermediary's aggregate
leverage or capital ratio is claimed to price risk across asset classes (He-Kelly-Manela, Adrian-Etula-Muir,
Kargar). This is a general-equilibrium asset-pricing claim whose empirical status the register itself
concedes is genuinely contested. Third, rule-based eligibility exclusion, where a specific class of holder
is barred outright regardless of that holder's capital position (window dressing, index-exclusion rules,
UCITS eligibility). This third mechanism does not obviously depend on capacity at all: a bank barred from a
specific balance-sheet posture on a reporting date may have ample capital and still be unable to hold the
position, because the constraint is eligibility rather than scarcity.

① is entitled to state the payer story at whatever altitude serves the architecture paper. Adopting it
wholesale, as this plan does, and then building a two-class admission taxonomy (D5) and a venue-by-venue
identification programme on top of it, asks the phrase to do work ① never asked it to do: show that "the
size of the payment tracks the constraint" holds, in the same sense, across all three mechanisms. As
currently written, the plan asserts the unifying language and lets D5's taxonomy paper over the difference
between them.

**Remedy.** Add one paragraph early in paper §2 naming the three mechanisms explicitly and stating which
one each folded venue instantiates. Flag anywhere the paper needs "size tracks the constraint" to hold in
the rule-exclusion case, since that specific functional claim is native to the two capacity-scarcity
mechanisms, not obviously to eligibility bars.

### 2. D1's venue-indexed crash share may be a payoff-convexity effect mislabeled as a venue effect

D1 already flags an "unhandled part": Jurek's crash-neutral G10 carry evidence and Bollerslev-Todorov's
jump-decomposition of the index-options variance premium point in opposite directions, and the plan
speculates this "may hold strongly for received option premium and weakly for FX carry." I agree the
tension is real, but I think the plan has the wrong candidate explanation. Jurek measures the crash share
of a directional, linear FX carry trade's expected excess return, how much survives once tail protection is
purchased. Bollerslev and Todorov measure the jump share of the variance risk premium itself, a payoff that
is convex in the underlying by construction and therefore mechanically loads on jump risk, because jumps
contribute disproportionately to realized quadratic variation. A short-variance or short-option position is
close to definitionally jump-sensitive in a way a linear spot-currency carry position is not, independent
of which venue either is traded in.

This means the split D1 documents may be a payoff-convexity effect, linear FX carry against convex
option and variance exposure, rather than a venue effect, and "venue-indexed crash share" risks mislabeling
it. This matters downstream: D1's whole point is to license a claim that generalizes to calibrate
expectations for the credit-spread and received-option-premium occupants too, and both of those sit closer
to Bollerslev-Todorov's convex end than to Jurek's linear end. If the real driver is payoff shape rather
than venue, the "crash is a minority of the premium" reading that underwrites D3's "very little income is
given up by keeping the inventory" argument (synthesis §4.2) may not transfer to those occupants at all.

**Remedy.** Reframe the claim as payoff-shape indexed rather than venue-indexed, or test and rule out the
convexity confound directly, ideally using the corpus's own commodity-carry-constructions finding that
concave versus convex shape is a property of construction rather than asset class, which already supplies a
within-venue comparison of the kind needed here.

### 3. Gospodinov-Robotti's critique may reach further into the corpus than the paper currently lets it

The plan is disciplined about not resting on He-Kelly-Manela's single-factor cross-sectional test given
Gospodinov-Robotti's misspecification-robust re-test (a 39-of-40 placebo false-positive rate), and it
correctly demotes Zeng's attractive 92 percent cross-sectional fit to corroborating status for exactly this
reason. But Tomunen's headline result, that a theoretically motivated constraint measure explains 71
percent of the cross-sectional variation in cat bonds' expected returns, is also a cross-sectional
asset-pricing fit statistic evaluated on a modest set of test assets, and the plan treats it as immune to
the same critique because it arises from a structural model rather than a linear factor regression. That
distinction is not obviously load-bearing against what Gospodinov-Robotti actually attack, which is the
fragility of cross-sectional pricing inference under plausible misspecification and correlated test assets,
not something specific to linear factor models as opposed to structural ones. A structural model with a
fitted constraint parameter can display the same kind of spuriously high fit on a modest cross-section that
a linear factor can. I am not asserting Tomunen's result is spurious. I am asserting the paper has not shown
it is not, and this result is currently the single most load-bearing empirical anchor for the "compresses
toward the marginal arbitrageur's cost of capital rather than to zero" claim that both D5 and D6.5 depend
on.

**Remedy.** Either state this explicitly as an open question the paper cannot close, in the same
register-honesty style already used for Bassi et al. and Jurek-Xu, or find independent, non-cross-sectional
corroboration for the compression pattern, for instance time-series evidence linking specialist-fund AUM
growth to the premium level, which the buildability note's UCITS inflow data already partially supplies.

### 4. Kargar's plurality finding is one crisis episode being asked to carry a cross-market architecture

Kargar's evidence for at least two distinct constrained intermediary types moving in opposite directions is
drawn entirely from the 2008-09 broker-dealer-versus-bank-holding-company leverage divergence. This is
genuine, carefully verified evidence and a real result against the single-factor reading. But the paper
extends it into a "plural and local" identification strategy applied across FX carry, credit spreads,
received option premium, and catastrophe risk transfer, which is a considerably larger inferential step
than the underlying evidence supports on its own. The synthesis is appropriately honest that "nobody has
re-estimated the He-Kelly-Manela seven-asset cross-section past 2012-13" (Gap 2); the same honesty should
extend to Kargar. The plurality finding is demonstrated for one crisis window and one pair of intermediary
types, and the paper generalizes it into a standing architectural principle that the corpus does not
actually test outside that window.

**Remedy.** State plainly that the generalization from Kargar's single episode to "plural, local, always"
is the paper's own extrapolation rather than an established empirical finding. This does not weaken D5's
overall case, which does not require the single-factor reading to be repaired, but it should not be
presented as more tested than it is.

### 5. D7's forward cap has an unresolved convexity mismatch, and it is the load-bearing repair for D3

D7's structure, admit on ex-ante rationale, bound by a forward cap rather than a realized-return proof,
never claim verification, is in my judgment the intellectually correct response to a genuine peso-problem
identification failure, and I want to be explicit that I think this move survives referee scrutiny in
principle. My concern is narrower and, I think, more consequential than it first appears. The plan's own
text states that the only candidate the corpus currently has for the forward cap, `SLEEVE_GROSS_LIMIT`, is
a notional or gross-exposure constraint, and states plainly that "whether that suffices has not been
argued anywhere." A notional cap bounds position size. It does not, on its own, bound loss in a peso event
unless the payoff is close to linear in notional, which is precisely the property the seat's own
construction rules out: selling convexity (① §4.1) means a large downside move produces a loss that is a
convex, not linear, function of notional. A fixed notional limit can therefore leave the tail loss
essentially uncapped in state-space terms even while capping it in position-size terms.

This is not a footnote-level gap. D3's central claim, that fair pricing is sufficient because inadequate
pricing "costs return, not solvency," depends entirely on the cap actually bounding the loss an
inadequately-priced peso event would produce. A notional cap on a convex payoff does not obviously do that.

**Remedy.** Either specify a genuinely scenario-calibrated cap, a stress loss under a stated hypothetical
crash severity translated into a position limit that accounts for each candidate's payoff convexity, before
claiming D3's sufficiency clause is discharged, or state explicitly, at the point where D3 is asserted, that
the cap currently available bounds notional rather than tail loss, and that the "solvency is protected"
claim is an unverified design intention rather than an established property of the roster.

## Minor concerns

- **The rule/circumstance boundary is ambiguous exactly where the paper needs it most.** D5's own table
  lists "capital charge" as an instance of rule-compelled behaviour, yet the paper elsewhere treats
  capital-scarcity mechanisms (HKM, Kargar, AEM) as the paradigm circumstance-compelled case, compressing
  as capital arrives. Since regulatory capital requirements are themselves rules, the paper needs an
  explicit, operational test for when a capital-related constraint counts as an eligibility bar (rule)
  versus a capacity cost any capital can relax (circumstance), because its own headline mechanism papers sit
  close to this line.

- **Jurek and Xu's 10-15 percent skewness-specific figure** is an unpublished, still-unconfirmed working
  paper. The published Jurek (2014) figure (3.18-5.31 percent crash-neutral) is the safer anchor. The
  synthesis already labels the 10-15 percent figure "magnitudes provisional," which is good practice; keep
  that hedge visible wherever the figure appears in prose, not only in the source note.

- **AQR's structural commercial interest deserves a sharper framing than per-citation COI tagging.** AQR is
  not merely a research contributor here; it is a commercial seller of the exact premia this paper argues
  are durable and worth holding. The register's per-citation tagging is careful, but the aggregate footprint
  spans the funding-unwind mechanism, the co-crash-in-recessions claim, the covered-call decomposition, and
  the cross-asset selling-insurance-is-paid claim. I recommend one summary passage, likely in the
  conclusion, that states what the argument looks like with AQR-sourced point estimates (not directional
  claims) removed.

- **The register documents an internal contradiction that the draft must not inherit.** One folded
  article's Limitations section calls Asvanunt and Richardson's raw-premium figures "COI-free" while its own
  Sources section tags the same citation as AQR-affiliated. This is caught correctly at the register level;
  the drafting stage should re-source the raw-premium comparator or drop the "COI-free" framing.

## What the paper gets right

- Adopting ① §2.2's payer story by citation rather than re-deriving it is the correct division of labour
  between the architecture paper and the seat paper, and the plan is disciplined about not letting the
  seat's construction claims leak back into a correction of ①.

- Making the central claim indifferent to whether the premium is excess (D3), and then recognizing that
  indifference alone does not reach the inadequate-pricing case (D7's amendment), is the right sequence of
  moves for a paper engaging seriously with the peso-problem literature. Most work in this space either
  ignores Burnside-Eichenbaum-Kleshchelski-Rebelo or waves at it; this plan engages with it seriously enough
  to find its own first answer insufficient and revise, which is a genuine strength.

- The handling of the contested intermediary literature is, with the exceptions noted above, disciplined
  rather than cherry-picked. Demoting Zeng despite its attractive fit, refusing to rescue the single-factor
  HKM reading, and leaning on Garleanu-Pedersen-Poteshman and Santa-Clara-Saretto (studies not exposed to
  the Gospodinov-Robotti critique) instead, is exactly the right response to a genuinely unresolved dispute
  in this literature.

- The sources register's verification discipline is unusually strong for a plan-stage document.
  Re-confirming primary text for the Kargar and Gospodinov-Robotti figures, correctly identifying and
  fencing the Terstegge working paper, and catching the Bai-Bali-Wen retraction rather than letting a
  corrected factor result slip through as live evidence, are things I do not routinely see done this
  carefully before a draft exists.

- D6.5's redirection of ILS from an "orthogonal income pole" to the primary compression exhibit is a real
  improvement. Tomunen's sixteen consecutive positive years is a cleaner illustration of "compresses, does
  not vanish" than anything else in the corpus, and the buildability note's willingness to update its own
  headline AUM figure mid-verification, rather than let it go stale, is good practice.

## Novelty statement

I formed my assessment before reading `_argument.md`. Relative to it:

**New.** Major concerns 1 (mechanism-conflation across demand-pressure, capital-constraint, and
rule-exclusion pricing under one payer-story label), 2 (the payoff-convexity-versus-venue confound in D1's
crash share), 3 (Gospodinov-Robotti's critique potentially reaching Tomunen's own cross-sectional fit), 4
(Kargar's single-episode generalization), and 5 (the notional-versus-scenario-cap convexity mismatch in
D7's forward cap) do not appear in `_argument.md`, which stress-tests D5's internal derivation logic (the
window-dressing and fallen-angel counterexamples), §6's roster dependency, and §7's sign-inversion-versus-
cost distinction. All five are inside my assigned expertise and none overlap the internal pass's findings.
The minor concern about AQR's structural commercial interest, as distinct from per-citation COI tagging, is
also new.

**Where I agree without adding.** I share `_argument.md`'s judgment that D5's two-class classification is
real content rather than relabeling, and that the finding built on top of it, that durable behaviours
mostly do not pay this seat, is the paper's most exposed claim. I found no grounds to disagree with either
point and have not repeated the window-dressing and fallen-angel argument here, though I regard it as
correct and expect the draft to address it. I also independently noticed a version of `_argument.md`'s §6
point, that D4's "the role's survival" language oversells a claim conditional on ①'s specific roster, but
since `_argument.md` develops it more fully than I would have, I have folded my instance of it into the
minor concerns rather than restating it as a major finding.

On the peso problem specifically: `_argument.md`'s critique targets the pre-D7 "indifference" framing and
is what D7 was written to answer. I evaluated D7's actual repair, which the internal pass did not have the
chance to stress-test, and found it conceptually sound but resting on an unaddressed convexity gap in its
own load-bearing instrument. That evaluation, major concern 5, is new.
