---
title: "Convergent Income Engine - Reviewer 3 report"
paper: "The Convergent Income Engine: Funding the Book Through Ordinary Markets"
date: 2026-07-25
tags:
  - review
  - income-engine
  - portfolio-construction
---

# Reviewer 3 report

Seat: portfolio construction, multi-strategy allocation, practitioner implementation. Independent
referee, no knowledge of the other four reports.

## Independence note

I formed the assessment below by reading `_plan.md`, `_synthesis.md`, `_sources.md`, `_buildability.md`,
and the relevant sections of ① (§2.2, §4.1, §4.2, §4.4, §5.4, §5.5) and `research/README.md` before
opening `_argument.md`. Each item below is tagged **MINE** (not raised in `_argument.md`), **CONFIRMS**
(matches a finding already in `_argument.md`, sometimes extended further than the stress test took it),
or **DISAGREE**. I did this so the team lead can tell what a second, independently-run pass adds versus
what it merely re-derives.

## Recommendation

**Minor Revision.**

The four-clause contract is sound as portfolio architecture, and the D6/D7/D8 repair sequence shows the
authors respond to real pressure rather than paper over it. Nothing below requires reopening D1 through
D5. But three fixes need to land in the plan before drafting starts, because each is a place where a
decision the authors have already made correctly has not yet been carried into the text that will
actually govern the paper: the Target-tier dependency (D6.4) needs to move from a decision-log entry into
the contract's own prose, the measured $\Delta\hat\Theta$ result in D8 needs to either carry the
segment-conditioning the synthesis says is a precondition for reading it or say plainly that it does not,
and D7's forward cap needs a different risk metric than gross notional. There is also one unresolved
tension between D5 and D6.2 that the plan should name and settle rather than let stand.

## Summary of the claim, in my own words

The paper argues that "convergent income sleeve" is not a mechanism (carry, credit spread, option
premium) but a portfolio role inherited from ①'s Floor: sell convexity, earn calm-market income, and let
the resulting crash inventory be the thing that funds the responder's wait. It operationalises that role
as a four-clause contract (earn ordinary-market return; sell convexity, so an inventory exists; place
that inventory's loss away from the responder's own failure state at a stated horizon; be ranked on
contribution to the paired book, not standalone smoothness), builds an admission test on that contract, a
two-class taxonomy of what compels the payer (rule versus circumstance, cut by substitutability), and a
falsification protocol with five pre-registered verdicts. It concludes the seat's real occupants are
mostly circumstance-compelled and therefore decaying, so the honest sizing posture is a labelled beta
allocation with a forward exposure cap rather than a persistent edge, and it hands the full
roster-ordering test back to ① as a named cross-paper obligation while discharging a restricted,
Floor-level version itself.

## Major concerns

### 1. D5 and D6.2 are not yet reconciled, and the fix is a reachability test the plan already has the vocabulary for

**MINE.** D5's surviving claim, after the D6 repair, is that "the seat's occupants are drawn
predominantly from the substitutable class, so fair pricing is the equilibrium the seat should be
designed for" (`_plan.md` D5, "What survives unchanged"). D6.2 then restores a rule-compelled,
non-substitutable cell that *does* pay this seat: an index-exclusion rule forces a tracker to sell a
downgraded bond, and the dealer who warehouses it is compensated for holding deteriorating credit through
an extended window, which the plan correctly reads as clause-2 inventory rather than a quick funding
turn. D6.2 calls this cell "the taxonomy's most useful, not its embarrassment" and says "a book should
look for occupants" there.

Those two claims sit in tension and the plan does not say so. If a durable, rule-compelled occupant is a
live possibility for this seat, "predominantly substitutable" needs a reason it still holds, not just a
label of "unchanged." The plan already has that reason available and half-states it: the one cited
exemplar of the durable-and-pays-this-seat cell is sourced from Dick-Nielsen and Rossi's own finding that
the dealer's compensation is "not replicable by other investors in the economy." If that is right, the
cell is real as an economic fact about the market and simultaneously empty as a source of occupants an
allocator's book can hold, which is exactly what would let D5's "predominantly substitutable" survive
D6.2's counterexample intact. But the plan states this as two separate, unconnected facts (D5's
survival paragraph and D6.2's reachability disclaimer) rather than as the single argument that
reconciles them. As written, a careful reader can construct the objection ("if durable occupants exist,
your beta-labelling conclusion needs qualifying") and the plan's own materials answer it, but nothing in
the plan currently makes that answer explicit.

**Remedy.** State directly, in the same place D6.2's cell is introduced or in D5's survival paragraph,
that the durable-and-pays-this-seat cell is compatible with "predominantly substitutable" specifically
because its one evidenced instance is not investor-reachable on the source's own account, and that this
is *why* it does not yet revise the beta-labelling conclusion, only the taxonomy. If a reachable instance
of that cell is ever found, that finding would matter to D3 and D5 and the plan should say so rather than
leave the connection implicit. This does not require naming an implementation. It is asking for a
sentence connecting two decisions the plan has already made.

### 2. The Target-tier dependency is a settled decision (D6.4) that has not propagated into the text drafting will actually use

**CONFIRMS and extends `_argument.md` §2 item 2.** `_argument.md`'s stress test found that §6's "mandated
separation" fails its own reversal test (remove the Target, the collision D2 describes does not occur)
and recommended the section say so in its own text, not only in a synthesis document. D6.4 in the current
plan accepts exactly that finding: "the role is falsifiable within this roster, not in general." That is
the right call and I have nothing to add to the underlying logic.

What I want to flag, going one step past the stress test, is that the fix has not yet reached the text
that will actually be handed to drafting. The thesis paragraph in `_plan.md` (the one paragraph most
likely to survive into the paper's own §1 near-verbatim, given how the rest of the plan is written)
states the bound unconditionally: "the seat's inventory is bounded above the Target tier's wing, because
the book has already bought the deep crash and selling it back is incoherent." D5's own restatement of
D2 is equally unconditional: "a behaviour that pays only by selling the deep crash is inadmissible,
because the book already bought it." Neither sentence carries the roster-scoping D6.4 requires. A
drafting pass working from this plan as written would reasonably produce a §6 that states the mandate as
a general property of the role, which is the exact failure mode `_argument.md` flagged and D6.4 was
written to prevent.

**Remedy.** Add the scoping clause where the bound is first stated, not only in the D6.4 decision note:
something to the effect that the bound holds within this roster, because it is the Target's ownership of
the fast-deep segment that creates the collision, and that a book without a Target-equivalent tier is not
bound by it. One sentence, placed at the point of first assertion rather than in a later caveat, closes
this.

### 3. D8's measured result appears to have already dropped the segment-conditioning the synthesis requires to read it

**CONFIRMS and extends `_argument.md` §3, §8.** The stress test flagged, prospectively, that the
$\Delta\hat\Theta$ baseline excludes the Target, so a fast-spike joint loss is priced against a book with
no fast defence and overstates the penalty, and warned this was "easy for drafting to lose given how
technical it is." `_synthesis.md` §3.5 states plainly that segment-conditioned reporting and an explicit
statement of what the baseline book contains are preconditions for the number to be readable at all, not
optional detail.

D8 reports the measurement that was run after that warning was written: $\Delta\hat\Theta = -0.014055$,
downside correlation +0.2724, intervals at 21, 63 and 126 days all spanning zero, computed on "both live
locked poles" at a single book tilt. There is no segment conditioning in what is reported (fast-spike
windows are not separated from protracted-drawdown windows) and no statement of what the two-leg baseline
contains. On the plan's own stated requirement, this is not yet a number the paper is licensed to read as
"Indeterminate" under D4's verdict table, because the precondition D4's own logic (via §6, via §3.5) sets
for interpreting it has not been shown to be met. This is not a hypothetical risk anymore; on what the
plan currently shows, the gap the stress test warned about looks to have already happened in the one
concrete measurement the plan carries.

**Remedy.** Either compute and report the segment-conditioned version before D8 is finalised, or state
explicitly in D8 that the reported figure is unconditioned and is read as a full-sample "Indeterminate"
result pending the segment-conditioned re-run, so the caveat travels with the number the way the Tasche
scope condition and the smoothing caveat already do. Given D8 already models how to carry a caveat next
to a number, this is a formatting discipline the plan already knows how to apply; it is just missing here.

### 4. A gross notional cap is not denominated in the quantity the peso problem threatens

**MINE.** D7 is right that realised returns cannot certify adequate pricing and that the correct response
is a forward cap rather than a backward-looking tail statistic, and right that the corpus does not
currently supply one. But `SLEEVE_GROSS_LIMIT`, named as the nearest available mechanism, bounds
*position size*, not *loss given the tail state the cap exists to guard against*. A cap denominated in
gross notional treats every occupant of the seat as equally convex per unit of notional, which is false
by construction: the whole reason this seat exists is that it sells convexity, and different
convexity-selling constructions lose very different multiples of their notional in the same crash. A
notional cap sized to be adequate for a mildly concave occupant is not automatically adequate for a
sharply concave one at the same notional, and the cap as named does not distinguish between them.

What the peso problem actually threatens is a loss whose magnitude the corpus admits it cannot estimate
from realised data. The correct unit for a cap meant to survive that is a stated maximum acceptable loss
under a specified stress scenario, with position size solved backward from that loss budget, re-solved
whenever the occupant's convexity profile changes, rather than a static share of NAV. This is the same
logic ①§5.4 already applies to the Target ("a cost paid continuously, recovered only in stress... sized
as a budget"); D7 should apply the mirror version to this seat's downside rather than settle for the
notional figure as an adequate stand-in. This is a construction-level requirement about which quantity
the cap is denominated in, not a request to specify an instrument, strike, or account constraint.

**Remedy.** State the forward cap as a scenario-loss budget (an accepted maximum drawdown contribution
under a named stress scenario, at the role level) rather than as a gross exposure limit, and name the
notional limit as one implementation of that budget rather than as the budget itself. If no such
scenario-loss framework exists yet in the corpus, say so as an explicit further gap alongside the ones D7
already names, rather than letting the notional figure stand in as though it discharges the requirement.

## Minor concerns

- **Clause 3's prose should distinguish correlation-sufficiency from capacity-sufficiency.** `_synthesis.md`
  §3.5(a-ter) establishes that the Floor's real condition is additive: the responder must cover its own
  bleed *and* the funding sleeve's protracted-drawdown loss, not merely avoid being correlated with it.
  The $\Delta\hat\Theta$ machinery (convex utility on the blended book) already prices this correctly, but
  the plain-English contract clause ("place that inventory's loss where the convex pole does not also
  fail") reads as a pure decorrelation claim to anyone who reads the contract without the metric. Worth
  one clarifying phrase so the two properties are not conflated by a reader who only sees the prose.
- **The two downside-correlation figures (+0.2724 and +0.253) are already flagged as unreconciled in
  D8.** I have nothing to add to the plan's own handling of this beyond agreeing it must be closed, not
  quoted from both, before drafting.
- **State the existence/buildability boundary once, explicitly, in the conclusion.** D4's "Seat earned"
  verdict is an existence claim; D7 and `_buildability.md` are careful never to claim more than that. A
  reader of the finished paper alone (without the plan or the buildability note) could still come away
  reading "role holds" as "role is investable now." One sentence in §9 stating that the existence
  verdict does not itself certify buildability at any given scale would close this off explicitly rather
  than leaving it to be inferred from the surrounding discipline.

## What the paper gets right

The best single piece of construction reasoning in the plan is D6.1's repair: recognising that the
original three-clause test excluded window dressing on a label ("pays a funding rate") rather than a
principle, and fixing it by restoring the clause ① already licenses (sell convexity) rather than
inventing a new one. That is the right way to close a gerrymandering charge, because it shows the
admission criterion doing real, demonstrated filtering work independent of the other three clauses,
answering my own first question above (Q1) cleanly: clause 2 is not circular. A behaviour can satisfy
"positive ordinary-market return, loss placed away from the responder's failure, positively ranked" while
having no crash inventory at all, and D6.1's own worked example (a repo spread with almost no loss to
place) proves it. That is a genuine, falsifiable role-definition, not a restatement of "the pole is
short-convexity by fiat."

The decision to admit on ex-ante rationale and never claim verification (D7, part 3) is exactly the
right discipline for a role built on a premium the corpus itself shows may be unverifiable from realised
returns (the peso problem), and the paper is unusually careful, for a construction-facing document, about
keeping that discipline visible at every point a number appears (D8's caveats, the Tasche scope
correction, the pending reconciliation flag).

The handling of ①'s §4.4 commission (my Q6) is honest, not evasion. The seat paper cannot run the
four-sleeve ordered-versus-unordered comparison because it does not own the Target or Expansion streams;
the plan states that limitation plainly, names the comparator ① specifies, and runs the one restricted
version it actually can (mandated Floor weight against equal-risk-contribution-implied weight, at a fixed
weight rather than solving for an optimum). That is a real, if partial, discharge of a real obligation,
correctly scoped rather than either overclaimed or quietly dropped. `_argument.md` reaches the same
verdict independently; I reach it from the construction side, on the grounds that the restricted test is
a genuinely analogous, not merely decorative, version of the ordering question (it tests how the
convergent weight is set, which is the Floor-level content of the ordering claim), provided the paper is
careful in the final text not to blur "which weight" with "which tier order," a distinction the plan
currently keeps but which is easy to lose in condensed prose.

## Novelty statement

The paper's novelty is in construction, not asset pricing, and it should be read and judged that way. It
does not claim a new premium or a new estimator. Its contribution is turning ①'s qualitative Floor
pairing into an admission test with a demonstrated filter (D6.1), a taxonomy with a direction term that
is new relative to the folded corpus (D6.2, restoring which side of a rule-compelled flow gets paid,
rather than treating rule-compelled as a single bucket), and a falsification protocol with pre-registered
verdicts that closes a specific gap (the corpus's own 27-cell re-rank was read post hoc as "no partner
found" rather than any of a stated set of outcomes). These are real, modest contributions to how a
portfolio role is specified and audited inside a pre-committed multi-tier architecture, which is a
different and rarer kind of contribution than a new anomaly, and the plan should not undersell it by
apologising for the absence of a headline empirical result.
