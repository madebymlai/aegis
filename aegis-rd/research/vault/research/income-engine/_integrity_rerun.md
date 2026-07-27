---
title: "Convergent Engine - Stage 2.5 integrity verification (re-run after remediation)"
date: 2026-07-25
tags:
  - integrity
  - verification
  - income-engine
  - rerun
---

# Stage 2.5 integrity verification - convergent engine - re-run

> [!danger] VERDICT: BLOCK
> Both original block reasons are genuinely fixed. A new one has appeared in the material the first
> gate never saw, and it is the same species of defect that made the first gate cautious about D5's
> repair chain: a specific, checkable, technical claim in the text is now factually stale relative to
> code and commits that landed in this same session, before the file was last saved.
>
> **New block reason: D8's smoothing-asymmetry caveat is stale and, as written, false.** `_plan.md` D8
> states the sleeve's Getmansky-Lo-Makarov smoothing profile is "unestimated" and that the measured
> downside correlation (+0.2724) "may understate the true co-crash." Commit `03ece3b7`
> ("report the sleeve's smoothing profile, and close the caveat it carried"), landed 2026-07-25
> 03:27:08+02:00, measured exactly this and found the opposite: both live poles read the smoothing
> index at $\xi = 1.0000$ (the no-smoothing ceiling), first-order autocorrelation is *negative*
> (bid-ask bounce, not staleness), Sharpe inflation is 1.0000, and the source article's own commit
> message states plainly "the caveat this session attached to it is withdrawn." `_plan.md`'s own file
> modification time (03:30:32) is **three minutes after** this commit landed, so the caveat was written,
> or at least last saved, after the measurement that refutes it already existed in the repository. D8
> itself states its two caveats "travel with the number and may not be separated from it" - this is not
> a peripheral aside, it is one of exactly two facts the plan treats as mandatory, inseparable context
> for the paper's only reported empirical figure, in the section the team lead correctly flagged as
> "the highest Mode 6 risk in the file." A false claim about what has and has not been measured, sitting
> at that description, is a block under the same reasoning the first gate applied to D6.1 and D6.2: narrow,
> mechanically fixable, and blocking because of where it sits rather than what it would take to fix.
>
> Everything else checked in the docket - D6.1's Bassi flag, D6.2's direction correction and its
> harder new claim, D4's verdict-row logic, D2's altitude rewrite, D7's peso-problem repair, D8's
> Tasche caveat and its fencing - comes back either clean or fixable-not-blocking. See the six docket
> items below for the full record, and [What must be fixed before drafting](#what-must-be-fixed-before-drafting-ordered-by-severity)
> for the complete fix list, which includes several non-blocking items surfaced along the way that
> should not be lost even though they do not independently gate this pass.

## Docket item 1 - D6.1's Bassi flag: PASS

The callout at the point of use states the argument "does not depend on the sample period - it
depends on the mechanism, which is a rule with a date and is visible directly in repo volumes" and
that the 12.5%/25% figures "must not be quoted in the paper until the final text is read." Re-read
D6.1's full body text (`_plan.md`) against this claim rather than taking the callout's word for it.

D6.1's actual argument uses exactly three properties of window dressing, none of them the contested
figures: (1) "earned in ordinary markets" - a qualitative timing claim; (2) "calendar-driven so
uncorrelated with anything trend-shaped" - a qualitative, rule-derived claim; (3) "observed in
confidential ECB transaction data rather than inferred from the cross-sectional test
Gospodinov-Robotti's placebo defeats 39 times in 40" - a claim about the *class* of evidence
(transaction data versus a cross-sectional factor test), not about its magnitude. The fourth-clause
repair itself - "a repo spread across a reporting date passes [the three clauses] by having almost no
loss to place" - is also about shape (near-zero inventory), not size. No quoted figure appears
anywhere in D6.1's body; the 12.5%/25% numbers appear only inside the warning callout, precisely
where they are flagged as forbidden to quote. Checked D6.3 as well, since it is the section that
argues for window dressing's *durability* (a natural extension of the sample-period question): its
argument is jurisdictional ("half the relevant world has already removed the incentive... the United
States and United Kingdom already use period-averaging"), which also does not touch the Bassi sample
period.

`_sources.md` §2.1's own assessment supports treating the mechanism at high confidence independent of
the unread PDF sentence: three independent corroborations (the 2023 ECB working-paper predecessor, a
SUERF brief, a 2026 BIS working paper) agree on the same sample period and figures, and the published
abstract is confirmed to exist via IDEAS/RePEc with matching headline figures. The NEEDS-VENUE-CHECK
status is a narrow, formal gap (nobody has read one sentence in a paywalled PDF), not a doubt about
the paper's existence or the mechanism's reality.

**Verdict: the scoping claim is true.** D6.1's argument survives deletion of the sample period and
the two contraction figures intact. The flag is not cosmetic.

## Docket item 2 - D6.2's direction correction: PASS, with a strengthening owed before drafting

**Direction.** Re-checked against Dick-Nielsen and Rossi (2019, *RFS* 32(1):1-41, confirmed to exist
and peer-reviewed in the prior gate's Phase A) and `income-must-accrue-not-be-captured.md`. The new
table states: "An index rule compels selling what a downgrade excluded" is paid to "whoever
warehouses weakness," which is "this seat," with "the tracker is the forced seller, the dealer the
buyer who warehouses." `income-must-accrue-not-be-captured.md` states the same shape verbatim:
"index trackers are the forced sellers and dealers the compensated providers." Direction now matches
both the primary source and the vault's own prior note. The old inversion is gone.

**Quote attachment.** "Not replicable by other investors in the economy" is now attached to "the
dealer... earning a return the paper states is" that phrase - correctly, since the phrase in the
primary source describes the dealer's compensated return from buying at the exclusion date and
reselling, not the tracker's forced sale.

**The new, harder claim: does the warehousing position genuinely carry negative-skew inventory, or
is it closer to a funding spread with credit beta attached?** This is the sharper test the team lead
asked for, and it deserved a primary-source check beyond what the register already carries, since the
prior gate verified only the quote and the direction, not this specific economic question. Fetched
Dick-Nielsen and Rossi's own text (via the RFS abstract, the BFI-hosted working paper, and the SEC
background PDF) for the mechanics of the warehousing position itself, distinct from the "not
replicable" quote.

The primary source supports the claim, though the plan does not show the derivation. Three facts
matter: (1) the paper explicitly separates two exclusion triggers and finds the *downgrade* exclusion,
not the low-maturity exclusion, is where the real inventory risk lives - low-maturity inventory clears
in about two weeks, while for downgraded ("fallen angel") bonds "only around two-thirds... has been
sold after 100 days," i.e. roughly a third of the position is still held three-plus months out; (2) the
paper states directly that "the costs are higher for the downgrade event compared to the low-maturity
event... because the downgraded bonds are both more risky and kept longer on inventory" - the dealer is
paid *more*, not less, specifically because the position is genuinely riskier and genuinely held longer,
which is compensation for bearing risk during a hold, not a same-day liquidity flip; (3) the paper's
own framing is that dealers "earn a positive return on average as compensation for the inventory
holding costs" of a position that is, by construction, long a credit that has just deteriorated enough
to be excluded - and credit deterioration events cluster in systemic stress, when the paper's own
finding (regulatory constraints raised the post-2008 cost of immediacy) says dealer capacity to absorb
this flow is simultaneously most constrained. That combination - more excluded bonds arriving exactly
when balance-sheet capacity is scarcest, held for months, in a name whose fundamentals are worsening
- is the shape D6.2 needs (negative-skew, crash-correlated inventory), not merely a funding-rate service.

So: the claim holds up under a fresh primary-source check, but D6.2's own sentence ("that warehousing
position is long a credit whose deterioration triggered the exclusion, so it carries the negative-skew
inventory clause 2 demands") asserts the conclusion without the holding-period and risk-versus-reward
evidence that actually supports it. This is the same shape of gap the stress test originally found in
D5 - a real claim, under-derived in the text - not a wrong claim. **Fix, not block**: add the
holding-period fact (roughly a third of downgrade-exclusion inventory unsold after 100 days, versus
cleared inventory in two weeks for the low-maturity trigger) and the "more risky, kept longer, paid
more" causal chain from the primary source, so the negative-skew claim is derived rather than asserted.

## Docket item 3 - D4's new verdict rows: PASS on coherence of the additions, one real gap found

**The indeterminate row** is a genuine repair, not a concession to a number. Before it existed, the
three-row table had no way to classify "point estimate off zero, interval spans it," which is exactly
what the live ΔΘ̂ measurement returned (see docket 6) - a verdict scheme that cannot classify its own
governing instance's most common outcome was broken on its own terms, independent of what any
particular measurement showed.

**Are the four rows mutually exclusive and jointly exhaustive?** Mostly, with one real gap. Candidate
fails (`ΔΘ̂ < 0` and interval excludes zero) and Indeterminate (point estimate off zero, interval spans
it) are cleanly disjoint by construction - one requires the interval to exclude zero, the other requires
it not to. But **Role redundant is not stated the same way**: "best candidate's ΔΘ̂ > 0 but below simply
holding more responder" carries no interval condition at all, unlike Candidate fails, which the docket
correctly notes was tightened to require significance. As written, a positive-but-statistically-
insignificant point estimate that also happens to sit below the responder benchmark satisfies
Indeterminate's literal wording (point estimate off zero, interval spans it) and could also be read as
satisfying Role redundant's literal wording (ΔΘ̂ > 0, below the benchmark), since Role redundant never
says the interval must exclude zero. That is an overlap the repair did not close - it tightened one row
and not its structural sibling. **Fix, not block**: state explicitly whether Role redundant requires an
interval excluding zero (paralleling Candidate fails) or is a point-estimate-only comparator; as
written the table is not cleanly partitioned.

**Is Role dead falsifiable in principle?** The prior gate did not address this; the stress test in
`_argument.md` called it "unfalsifiable-in-practice wearing falsifiable clothing." My own read: Role
dead, properly understood, is not on the same logical level as the other three rows. The first three
classify a single candidate's single measurement; Role dead is a universal claim ("for every
candidate, permanently") that no finite measurement can establish inductively - repeated Candidate-
fails verdicts across many candidates never add up to Role dead, because absence of a discovered
counterexample is not proof none exists. D4's own language - "the income clause forces the collision
and the contribution clause fails by construction" - is consistent with the more defensible reading:
Role dead would have to be established by a *structural* argument (the four clauses are jointly
unsatisfiable as a matter of definition, in the way D2's admission criterion is itself a structural
argument), not by an empirical tally. Read that way, it is falsifiable in the ordinary Popperian sense
(one admissible candidate refutes it) even though it is not verifiable by exhaustive search. The plan
does not spell this distinction out, and the practical worry the stress test raised - that nobody will
ever be able to tell "still haven't found one" apart from "structurally impossible" without a separate
deductive argument - is real and unresolved by the new wording. This is not a new problem introduced by
the repair, and the prior gate already recommended stating it as an explicit limitation in paper §1
rather than fixing it structurally; I'd repeat that recommendation rather than treat it as new.

## Docket item 4 - D2's rewrite to behaviour level: PASS

**(a) Nothing load-bearing lost.** The callout states the option-selling capital gates, tail-sleeve
collision, and numeric wing detail "live in `income-must-accrue-not-be-captured` and are not carried
into the body." Checked: that note does carry this detail - its "Verified thresholds" table lists
"Put-write and short VSTOXX | structural | never - collides with the tail sleeve at any size," which
is the tail-sleeve-collision fact, and the note's wall taxonomy (size versus structural) and NAV
reopening figures are exactly the implementation detail the callout points to. The pointer resolves to
real content, not a dangling reference.

**(b) Still derived from ① §4.2 and §5.4, not asserted independently.** Read both sections directly
(`budgeting-convexity.md:354-378` for §4.2, `:507-532` for §5.4) rather than trusting the citation.
§4.2 states the Target "is the immediate defense that covers the fast segment" and "is sized... by the
speed gap it closes." §5.4 states the tail sleeve "must be sized as a budget and actively monetized
rather than held by default." D2's derivation - the seat's inventory is bounded because the Target
already owns coverage of a segment of crash risk, so the seat selling into that same segment puts the
book on both sides of one exposure - follows from these two sections rather than from anything invented
for this paper. One imprecision worth naming, not a new error: §4.2's actual criterion for the Target's
scope is *speed* (the fast segment the responder is too slow to reach), while D2 and the wider corpus
sometimes describe the boundary in terms of *depth* ("the deep crash," "the Target's wing"). These are
related (options deliver fast payoff and are naturally described by strike) but not identical axes, and
`_argument.md`'s own per-section stress test on §6 already flagged this blurring ("the strike/wing
language... risks reading as instrument-specific rather than behavioural"). D2's own callout already
defers the numeric wing to the occupant's own analysis and keeps the body at the criterion level, which
is the correct mitigation; I would not raise this beyond what the corpus has already flagged.

**(c) Does not correct ①.** "The derivation runs entirely through ①'s own text... so it does not
correct ①" is accurate on the reading of §4.1/§4.2/§5.4 above - the paper adopts ①'s tier assignments
and derives a consequence from them, it does not challenge or amend what ① assigns to the Target.

## Docket item 5 - D7, peso-problem repair: fixable, not clean

**Is the `research/README` reading accurate?** Partially, and it stretches further than README states
directly. README's actual claim is methodological: a backtest *estimates* an effect already expected
from ex-ante theory, it never *discovers* one - this is a guard against data-snooping and the factor
zoo. D7 extends this into a stronger, more specific claim: that realized-return tests structurally
cannot distinguish fair pricing from inadequate pricing for this seat's premium. That extension is
reasonable and the peso-problem literature (Burnside, Eichenbaum, Kleshchelski and Rebelo) is a
legitimate reason realized returns are especially weak evidence here - but README does not itself say
this; D7 is *applying* README's general stance to a specific measurement problem, not quoting a
conclusion README already reaches. `_plan.md` should say "applying README's stance" rather than
implying README already settles the question, which is currently closer to how it reads.

**Is the Burnside et al. characterisation accurate?** Yes. `_sources.md` and `_synthesis.md` §4.2
both already carry it correctly (ATM-hedged carry payoff statistically indistinguishable from zero,
consistent with a peso problem where the feared high-marginal-utility state has not fired in-sample),
and D7's restatement matches this without drift.

**Does "underpayment costs return, not solvency" actually follow from a tail budget? This is the
load-bearing inference and it does not hold as currently derived.** D7 cites ① §5.4 (which is about
the *Target* tier's convexity-premium budget - the cost of *buying* protection) and then pivots to
`convergent_tail_budget` (a metric that *reports* the convergent seat's own realized worst-decile loss,
"never an annualised projection"). Neither of these is a forward-looking cap on the convergent seat's
own maximum possible loss. §5.4 bounds a different sleeve's spending on insurance; `convergent_tail_budget`
is a backward-looking measurement of what has actually happened, not a limit on what can happen - and
it is structurally blind to exactly the risk D7 is trying to argue against, because a peso-problem tail
event is by definition one that has not fired in the observed sample, so it cannot appear in "the worst
decile of windows actually observed." What would genuinely convert underpayment into a return-only,
survivable failure is a **position-sizing cap** - the sleeve's own risk-share allocation as a bounded
fraction of the book's capital (the `0.28 x 1.75 x NAV` sleeve budget mentioned in
`income-must-accrue-not-be-captured.md` is the right *kind* of mechanism, though that note is about a
different, smaller book) - so that even a total loss of the sleeve's allocated capital cannot threaten
the book's solvency. D7 gestures at this ("a cap on the loss the book will accept") but then cites the
wrong instrument (a reporting metric) as if it performed the capping. **Fix before drafting, not
block**: either name the actual sizing/allocation mechanism that bounds the convergent seat's maximum
loss as a fraction of the book, or state plainly that no such cap currently exists in the paper's own
scope and the "return not solvency" claim is a design requirement rather than an established fact.

**Does D7 contradict D3, or repair it?** Repair, correctly labelled as such within D7's own text
("that indifference covers the wrong pair") - D7 does not dispute that fair pricing is *sufficient*
for the role (D3's core claim), it adds a defence against the case D3's original framing did not reach
(inadequate, not merely non-excess, pricing). The content is coherent. The **presentation** is not:
D3's own text in `_plan.md` is unchanged and, read on its own, still states the indifference framing as
if it were complete, with no forward pointer to D7. This is exactly the kind of coherence gap the
regression checks below ask about, and it is the same item the prior gate listed as "[MEDIUM] Close
the gap between `_plan.md` D3 and `_argument.md`'s sharper peso-problem point" - the remediation added a
new decision (D7) rather than closing the loop by cross-referencing D3 to it. **Fix before drafting**:
add a sentence to D3 pointing to D7, the way D5 carries an explicit "SUPERSEDED by D6.2 and D6.3"
callout.

## Docket item 6 - D8, the measured result: the block

**Fencing.** Holds as written. D8 is one paragraph in §8's discussion, explicitly framed as "evidence
about the method's reach" rather than a role-level finding, and explicitly states it "must not reshape
D3, D5, or D4's substance." Grepped `_plan.md`, `_argument.md`, `_synthesis.md`, `_sources.md`,
`_buildability.md` for the result's figures outside of D8 and `_pipeline-state.md`'s superseded-intake
callout: no other section leans on the number.

**The Tasche caveat.** Verified against `bd show aegis-rd-v1k7` (closed, fixed at commit `110507ad`).
D8's text - "ΔΘ̂ borrows the with-minus-without arithmetic and not Tasche's theorems: his Proposition 2.2
requires a risk measure homogeneous of degree 1 and Θ is not homogeneous, so none of the Euler/RORAC
guarantees transfer" - matches the closed issue's own description of the fix exactly, including the
homogeneity-of-degree-1 language. Accurate and current.

**The smoothing asymmetry - stale, and this is the block.** D8's second caveat states the sleeve's
Getmansky-Lo-Makarov smoothing profile "is unestimated," that smoothed marks bias contemporaneous
correlations toward zero, and that "the measured +0.2724 may understate the true co-crash." Checked
this against the direction claim in Getmansky, Lo and Makarov (2004) - correct, smoothing does bias
correlations toward zero, this part of the caveat's *logic* is sound - and then against `git log` on
the metric and the role article, per the docket's instruction to check the `aegis-rd-600y` close reason
and current code state.

The smoothing profile is no longer unestimated. Commit `03ece3b7` ("report the sleeve's smoothing
profile, and close the caveat it carried"), landed 2026-07-25 03:27:08+02:00, implements
`convergent_smoothing_index`, runs it on both live poles, and finds $\xi = 1.0000$ for both (the
no-smoothing ceiling), first-order autocorrelation *negative* (-0.104 convergent, -0.024 trend - the
opposite sign from staleness, consistent with bid-ask bounce in an exchange-traded mark rather than
extrapolated pricing), Sharpe inflation exactly 1.0000, and lagged downside correlations that
alternate in sign rather than decaying positively, meaning no co-movement is being displaced into lags.
The commit message states directly: "the caveat this session attached to it is withdrawn." The source
article (`research-legacy/what-makes-a-convergent-sleeve-an-income-engine.md`) was edited in the same
commit to replace its own "has not been estimated" limitation with this measured result. `carry_floor.yaml`
was wired to report `convergent_smoothing_index` on every run going forward.

`_plan.md`'s own filesystem modification time is 2026-07-25 03:30:32+02:00 - three minutes after this
commit. The caveat as currently written was therefore last saved after the specific measurement that
refutes it already existed in the repository, in the exact area (the sleeve's own smoothing profile)
the article's hypothesis list had marked as the open item. This is not a citation-attribution slip; it
is a factual claim about the current state of measurement ("unestimated... may understate") that is
now false, attached as one of exactly two facts D8 itself says "may not be separated from" the number
when it is used. Given the team lead's own framing of D8 as "the sharpest Mode 6 (methodology
fabrication) surface in the artifact because it reports numbers," a stale-to-false claim about what has
and has not been measured, sitting inside the mandatory caveat block of that exact paragraph, meets the
bar the first gate applied to block on D6.1 and D6.2: narrow, one sentence, mechanically fixable, and
blocking because of where it sits.

One further wrinkle worth flagging for the fix rather than for the verdict: the smoothing-profile
commit reports the downside-correlation guard as **+0.253**, while D8 (and the `aegis-rd-n77e` loader
result it is drawn from) reports **+0.2724**. These may be the same guard measured on different windows
(the loader's figure is on the 1,889-day intersection with `trend_floor`; the smoothing-index commit's
figure may be computed on `carry_floor`'s own report-configured window) rather than a contradiction, but
the plan should reconcile which figure the paper uses and why they differ before drafting, rather than
leaving two different values for what reads as the same quantity.

**The ILS parallel.** D8's general framing - "state it once as a general asymmetry: de-smoothing can
only make loss placement look worse, never better" - and its claim that `_synthesis.md` Gap 5
"independently" reaches the same asymmetry for ILS both check out as *directionally* accurate: Gap 5
does say, independently, "de-smoothing should raise the crisis co-movement above the reported 0.29, so
this measurement can only weaken the placement case, never strengthen it," and no de-smoothed ILS
series exists in the corpus (Gap 5 states this plainly). But now that the convergent sleeve's own
profile has been measured and found clean, D8's "general asymmetry" framing needs to split into two
different states rather than one: for the **convergent sleeve**, the concern has been measured and
resolved (no bias present); for **ILS**, the concern remains live and unmeasured. Stating both under
one "general asymmetry" sentence, once the sleeve's own case is closed, will read as applying an
unresolved caveat to a resolved measurement.

**`aegis-rd-600y`.** Confirmed genuinely closed WONTFIX (`bd show`), with the close reason's own
evidence table - 12/12 correct at every drift tested for the floating-volatility convention, 9/12 for
the vol-matched alternative at the live sleeve's own +4.2%/yr drift - matching `_argument.md` §8's
"Correction, applied after the Stage 2.5 gate" passage number-for-number, including the specific figure
(+4.22%/yr, same measurement, immaterial rounding difference). Striking the stale scale-convention
warning from `_argument.md` §8 was correct, not a convenient deletion: the warning it replaces
described a concern that this same issue investigated and rejected using a controlled measurement, not
merely reasserted.

## Regression checks

**Altitude.** Swept `_plan.md` for residual strategy/instrument vocabulary against `research/README`'s
"is the label an action taken under compulsion, or a thing someone buys?" test. Found nothing new: every
instrument-level term encountered (FX carry, credit spread, received option premium, ILS) is used
explicitly as a *candidate occupant* of a behaviour-level role rather than as the behaviour itself, which
is the distinction the paper's own thesis draws ("carry is one occupancy of a job... each candidate is
admitted or excluded by whether its own venue's constraint still binds"). The one place instrument
vocabulary appears prominently - D6.2's "fallen angels" - sits inside a callout explicitly recording a
corrected error, which the team lead's brief already exempts.

**① boundary.** Checked D2, D7 and D8 specifically, since these are the remediated/new decisions.
None reintroduces the "this paper corrects ①" framing. D2 states plainly it does not correct ①, and my
own reading of §4.2/§5.4 confirms the derivation runs through ①'s own text. D7 does not touch ① at all
- it is about how to admit and bound the seat's own claim, not about ①'s roster. D8 explicitly disclaims
reshaping D3, D4 or D5, and does not address ① directly either.

**Conventions.** Zero em-dash occurrences (U+2014), re-counted directly rather than trusted from the
prior report, across all seven income-engine documents plus `notes/the-premium-is-rent-on-a-balance-sheet.md`
(the source of D8's own measured callout). The convention holds, including in the newly added D7 and D8
material.

**Coherence after edits.** D5's superseded finding remains correctly fenced under its own warning
callout, and D1 through D8 plus the thesis and nine-section map read as mutually consistent with two
exceptions, both already covered above and both fix-not-block: (1) D3 and D7 are substantively
compatible but D3's own text carries no forward pointer to D7's correction, so a reader stopping at D3
gets an incomplete picture; (2) D4's Role-redundant row was not tightened in step with Candidate-fails,
leaving a literal-reading overlap with Indeterminate. No contradiction was found between D7/D8 and
D3/D4/D5's substance beyond these two presentational gaps - in particular, D7's "realized returns were
never the warrant" and D8's treatment of a realized-return measurement as informative are compatible
once read carefully (D7 governs what the admission decision needs; D8 is a note about the test's current
power), but the plan does not state this compatibility explicitly and a fast reader could see them as
pulling apart.

## What must be fixed before drafting, ordered by severity

1. **[BLOCKING] Correct D8's smoothing-asymmetry caveat.** Replace "unestimated... may understate the
   true co-crash" with the measured result from commit `03ece3b7`: both live poles read the smoothing
   index at the no-smoothing ceiling ($\xi = 1.0000$), autocorrelation is negative (bid-ask bounce, not
   staleness), and the downside-correlation guard is unflattered by smoothing. Split the "general
   asymmetry" framing into two states: resolved and clean for the convergent sleeve's own measurement,
   still open and unmeasured for ILS. Reconcile the +0.2724 versus +0.253 figures or state explicitly
   why they differ.
2. **[HIGH] Fix D7's load-bearing inference.** "Underpayment costs return, not solvency" needs a
   forward-looking position-sizing/capital-allocation cap, not a backward-looking reporting metric
   (`convergent_tail_budget`) that cannot see an event that has not yet occurred in-sample. Either name
   the actual sizing mechanism that bounds the seat's maximum loss as a fraction of the book, or state
   the claim as a design requirement the paper is asserting rather than a fact ① or the corpus has
   already established.
3. **[MEDIUM] Close the D3/D7 cross-reference gap.** Add a sentence to D3 pointing forward to D7, the
   way D5 carries its own "SUPERSEDED by D6.2 and D6.3" callout, so D3 is not left reading as complete
   on its own.
4. **[MEDIUM] Fix D4's Role-redundant row.** State explicitly whether it requires an interval excluding
   zero (paralleling the tightened Candidate-fails row) or is a bare point-estimate comparator; as
   written it overlaps with Indeterminate on a positive-but-insignificant result.
5. **[MEDIUM] Strengthen D6.2's negative-skew derivation.** Add the primary-source holding-period fact
   (roughly a third of downgrade-exclusion inventory unsold after 100 days versus two weeks for the
   low-maturity trigger) and the "more risky, held longer, paid more" causal chain, so the claim that
   the warehousing position carries genuine negative-skew inventory is derived rather than asserted.
6. **[LOW] Attribute D7's `research/README` reading as an application, not a restatement.** README
   establishes the general methodological stance (ex-ante theory before backtest); D7's extension to
   "realized returns cannot verify pricing adequacy for this seat" is a reasonable but distinct
   inference the paper is drawing, and should be labelled as such.

## Limitations

**Scope discipline was honoured, not merely stated.** Per the team lead's instruction, the ~185-source
register was not re-verified beyond what the six docket items required (the Dick-Nielsen and Rossi
primary-source check in docket 2 and the Getmansky-Lo-Makarov direction check in docket 6, both of
which were named or clearly implied by the docket), and the 7-mode checklist was not re-run wholesale.
I did read ① §4.1, §4.2 and §5.4 directly (beyond what the prior gate's Phase A already covered) because
docket item 4 specifically asked whether D2's criterion is derived from those sections rather than
asserted, which required reading them rather than trusting the citation.

**The D6.2 primary-source check was narrower than a full re-read of Dick-Nielsen and Rossi (2019).**
I fetched search-indexed excerpts (via Exa) covering the paper's mechanism section (dealer inventory
buildup and decay around index-exclusion events, the 100-day holding-period figures, the
"more risky, kept longer" compensation logic) rather than the full PDF. The specific figures quoted
above (two-thirds sold within 100 days for downgrade exclusions, versus full clearance within two weeks
for low-maturity exclusions) come from the paper's own text as surfaced by that search, not from a
complete read of the article, and should be treated with the same discipline as any other
search-extracted quote - accurate as far as verified, not independently cross-checked against a second
source.

**The +0.2724 versus +0.253 discrepancy was not resolved, only flagged.** I did not trace the exact
computation paths (loader-paired 1,889-day window versus whatever window `carry_floor.yaml`'s own
report configuration uses) to confirm they are the same guard on different samples rather than a
genuine inconsistency. This is listed as a fix item rather than adjudicated here.

**Docket item 3's falsifiability analysis is my own philosophical read, not a primary-source check.**
There is no external authority to verify "is Role dead falsifiable" against; the analysis rests on
standard Popperian reasoning about universal claims applied to the table's own wording, which is a
different kind of verification from the citation and code checks elsewhere in this report.

**I did not re-run any code or re-derive `03ece3b7`'s measured figures independently.** The smoothing-
index result that blocks this pass was accepted from the commit message, the diff to `carry_floor.yaml`
and the role article, and the new unit test's assertion shape (`_convergent_smoothing_index` recovering
1.0 on a clean synthetic stream) - not from executing `convergent_smoothing_index` myself against the
live data. The same standard applied to `aegis-rd-600y` in the first gate (accepted a closed issue's
stated methodology without independently reproducing it) applies here.

**Word-for-word verification of the em-dash count used a byte-pattern grep for U+2014 specifically**,
not a broader sweep for en-dashes, double hyphens, or other dash-adjacent characters that could serve
the same rhetorical function while evading the specific convention check.
