---
title: "Convergent Engine - Stage 2.5 integrity verification (third pass)"
date: 2026-07-25
tags:
  - integrity
  - verification
  - income-engine
  - rerun
---

# Stage 2.5 integrity verification - convergent engine - third pass

> [!success] VERDICT: PASS
> All six docket items check out. Four are clean corrections with nothing further owed. Two carry a
> real, non-blocking gap worth fixing before drafting: D4's rebuilt verdict table is not jointly
> exhaustive (there is no row for a candidate that actually succeeds), and D7's own section header
> ("the peso problem is answered by budgeting") overclaims relative to its now-honestly-downgraded body
> (the cap's sufficiency "has not been argued anywhere"). Neither is a false or stale claim of the kind
> that blocked the first two passes - both are coverage/framing gaps, not misstatements a reader would be
> actively misled by. The staleness regression that blocked pass 2 (D8) does not recur: no commit has
> landed in this repository since `_plan.md`'s last save (2026-07-25 03:51:38+02:00, current time
> 03:58) that bears on anything the file asserts. See the docket below for the full record and
> [What should be fixed before drafting](#what-should-be-fixed-before-drafting-ordered-by-severity) for
> the two non-blocking items.

Per the team lead's scoping, this pass does not re-verify the ~185-source register or re-run the 7-mode
checklist. It is confined to the six docket items below plus the named regression checks, against the
remediated `_plan.md` and the two prior reports (`_integrity.md`, `_integrity_rerun.md`), whose findings
are treated as settled and not redone.

## Docket item 1 - D8's smoothing caveat: PASS

**Every figure checked against commit `03ece3b7` matches exactly.** Read the commit's diff to
`convergent.py` (adds `_convergent_smoothing_index`, the Lo-MacKinlay variance-ratio estimator) and to
`research-legacy/what-makes-a-convergent-sleeve-an-income-engine.md` (replaces the "has not been
estimated" limitation and the open hypothesis-list item with the measured result), not just the commit
message. Both live poles read $\xi = 1.0000$; first-order autocorrelation is negative (-0.104
convergent, -0.024 trend), read correctly in `_plan.md` as bid-ask bounce rather than staleness; Sharpe
inflation is 1.0000; the lagged downside correlations alternate in sign (-0.125, +0.159, -0.096 in the
commit message, described in `_plan.md` as "alternate in sign rather than decaying positively," which is
accurate to the actual sequence). D8's text tracks the source commit sentence-for-sentence, including
the withdrawal language ("the caveat this session attached to it is withdrawn").

**The surviving claim - the asymmetry stays open for ILS because cat-bond funds are OTC-marked rather
than exchange-traded, and the pre-registered expectation held - is supported, with one precision note.**
`_synthesis.md` §6 Gap 5 does state "no de-smoothed ILS series exists in the corpus, at any frequency."
The pre-registered expectation is verbatim in the source article's own pre-commit text (the diff's "-"
line, i.e. what the hypothesis list said *before* this measurement): "Pre-register the expectation: an
exchange-traded UCITS ETF NAV should smooth *less* than the OTC-marked funds in the literature" - so the
expectation predates the measurement and the "OTC-marked funds in the literature" phrase is the
article's own, not invented for D8. And "that expectation held" is accurate: the commit's own docstring
states directly, "Pre-registered expectation (the article's own): an exchange-traded UCITS ETF NAV
should smooth far LESS than the OTC-marked funds GLM studied," and the measured result (xi = 1.0000,
no smoothing) confirms it.

The one thing not independently verified: `_plan.md` characterises "cat-bond funds" specifically as
"OTC-marked," and that exact term is not applied to the named ILS candidates (Twelve Cat Bond Fund,
Schroder GAIA Cat Bond) anywhere else in the corpus checked this pass. It is well supported by fact,
though: `notes/cat-bond-return-proxies-for-carry-validation.md` describes SHRIX (the closest documented
proxy for this fund family) as "an open-end mutual fund valued at NAV" against "CATB [...] an
exchange-traded ETF with bid/ask spread," and `_buildability.md` documents Twelve and Schroder GAIA as
the same kind of vehicle. "OTC-marked" is a fair synthesis of "NAV-priced open-end fund, not
exchange-traded," not a fabricated label, but it is D8's own inference rather than a term lifted from a
cited source. Not a fix item, noted for completeness since the docket asked the venue split be checked
specifically.

## Docket item 2 - D7's instrument: PASS, with one presentational gap to close

Checked against the actual code, not just the plan's characterisation.

**(a) The backward-looking-blindness reasoning is correct.** `CONVERGENT_TAIL_BUDGET_DEFINITION` in
`aegis-rd/research/aegis_research/metrics/custom/convergent.py` documents the metric's `value_semantics`
as "actual mean loss in the worst decile of overlapping 2-6 month own returns," computed by
`_left_tail_budget` over realised windows. A statistic computed from the realised sample cannot, by
construction, see a loss the sample never contained. D7's peso-problem framing (Burnside, Eichenbaum,
Kleshchelski and Rebelo, already verified in the prior two passes) is exactly this: the feared state is
one that has not fired in-sample, so a realised-worst-decile statistic is structurally blind to it. The
reasoning holds.

**(b) `SLEEVE_GROSS_LIMIT` is accurately characterised.** `aegis-runtime/aegis_runtime/bundle.py:37`
hard-codes `SLEEVE_GROSS_LIMIT = 1.0`, with a comment stating the sleeve's gross exposure "never exceeds
1.0" and that "the book allocator is the only leverager." It is enforced through
`aegis_runtime/exposure_validation.py`, whose module docstring literally opens "Fail-closed Exposure
Validation gate for signed target-weight frames," and whose `ExposureValidationError` (subclassing
`ValueError`) is raised on any breach - "the gate failed loud," per the same docstring. This is a
hard-coded, fail-closed constant enforced by a dedicated validation gate, not a number derived from
data. D7's phrase "enforced fail-closed rather than estimated" is accurate on both halves.

**(c) D7 no longer claims the bound is discharged.** Re-read the full paragraph: "Whether that suffices
has not been argued anywhere. State this as a stated design requirement with the gap named [...] and do
not present the tail budget as discharging it." This is an explicit disclaimer, not a residual claim of
sufficiency. Confirmed clean.

**(d) Does downgrading to a stated requirement leave D7's answer standing, or hollow it out? Standing,
but with a header that overclaims relative to its own body.** D7's three-part structure is (1) admit on
ex-ante rationale, (2) bound by a forward cap, (3) never claim verification. Only part (2) is affected by
this fix, and it is now explicitly a stated requirement rather than an established fact - the paper
commits to needing a sizing cap that bounds the seat's maximum loss as a fraction of the book, names
`SLEEVE_GROSS_LIMIT` as the nearest existing mechanism, and states plainly that nobody has shown it is
big enough. Parts (1) and (3) are untouched by the fix and still do real work: the admission-on-rationale
move does not depend on any cap, and "never claim verification" is if anything strengthened by the
honesty of (2). So the peso-problem defence is not hollowed out - the paper does not become indifferent
to underpayment again, it becomes honest that the response it proposes is not yet shown adequate.

What is left slightly inconsistent is presentation, not substance: the decision's own header still reads
"D7. The peso problem is answered by budgeting, not by indifference," and the "Consequence for the
contract" paragraph frames the underpayment problem as resolved by budgeting. A reader who stops at the
header and the framing sentences, without reading the fully-downgraded body of part 2, would come away
believing the solvency question is settled rather than named as an open requirement. This is the same
species of gap the second pass found between D3's own text and D7's correction (a forward-pointer
problem, not a wrong claim) - not severity enough to block, but worth tightening: either soften the
header to something like "the peso problem is addressed by a budgeting requirement, not resolved by
indifference," or add a sentence to the header paragraph itself stating that the cap's sufficiency is an
open design obligation. See fix list below.

## Docket item 3 - D4's mutual exclusivity and exhaustiveness: mutually exclusive, PASS; not jointly exhaustive, one real gap

**Mutually exclusive: yes, cleanly, after the pass-2 fix.** Indeterminate requires the interval to span
zero; Candidate fails and Role redundant both now require the interval to exclude zero (the pass-2 fix
added this condition to Role redundant, closing the literal-reading overlap the second pass found).
Candidate fails and Role redundant are distinguished by the sign of $\Delta\hat\Theta$, which is
unambiguous once the interval excludes zero. Role dead sits at a different logical level entirely (a
structural, all-candidates claim rather than a single measurement's classification, as the second pass
already established), so it cannot overlap the other three by construction. Checked this directly
against the current table text and confirm no residual overlap.

**Jointly exhaustive: no. There is a real, uncovered case.** The four rows are: Indeterminate (interval
spans zero), Candidate fails ($\Delta\hat\Theta<0$, interval excludes zero), Role redundant
($\Delta\hat\Theta>0$, interval excludes zero, *below* holding more responder), and Role dead (a
structural claim, not a per-candidate measurement outcome). A candidate whose $\Delta\hat\Theta$ is
positive, the interval excludes zero, **and it is above** simply holding more responder - i.e. a genuine,
statistically significant, economically meaningful contribution - matches none of the four rows. Role
redundant explicitly excludes it by its own "but below" clause; the other three do not apply to it either.
This is not a hypothetical edge case invented for this review: it is the single most consequential
possible outcome under D4's own logic. D4 states the role is "an existence claim," and Role dead's
definition ("for every candidate, permanently") is exactly the kind of universal claim one admissible,
above-benchmark candidate refutes - D6.2 is already used this way in the plan's own text ("the corpus
already names one"). A table built to discipline how failures and non-findings get classified, so that
"role dead" cannot become an unfalsifiable catch-all, has left the one outcome that would actually settle
the question in the role's favour without a named row.

This does not affect anything currently reported - the live measurement (D8) lands in Indeterminate,
which is correctly covered - so it is not blocking. It is a completeness gap in the taxonomy that should
be closed before drafting, the same way the second pass's Role-redundant fix closed a different gap in
the same table. See fix list below.

**Role dead's falsifiability**, addressed by the second pass and not reopened here per scope: no change
in the current text bears on that finding.

## Docket item 4 - D3's amendment callout: PASS

The callout ("Amended by D7 - the indifference claim covers the wrong pair") states D3's indifference
claim covers fair-versus-excess, that the case that hurts is inadequate pricing, and that "D7 supplies
the repair - admit on ex-ante rationale, bound by a forward cap, never claim verification." This matches
D7's own three-part structure exactly (word for word, in the same order D7 states it). D3 and D7 no
longer conflict: D3's own text is unchanged but is now explicitly flagged as superseded-in-part at the
point where a reader would otherwise take it as complete, the same mechanism D5 uses for its own
supersession by D6.1-D6.3. This closes exactly the gap the first and second passes both flagged (first
pass: "[MEDIUM] Close the gap between `_plan.md` D3 and `_argument.md`'s sharper peso-problem point";
second pass: "[MEDIUM] Close the D3/D7 cross-reference gap"). Verified fixed.

## Docket item 5 - D6.2's negative-skew derivation: PASS, independently re-verified against the primary source

The second pass verified this via search-indexed excerpts and flagged that narrower method as a
limitation of its own check. This pass re-fetched Dick-Nielsen and Rossi's text independently (SEC
background PDF and the BFI-hosted working paper) rather than relying on the prior pass's excerpts, and
checked all three claimed facts directly.

1. **"Roughly a third still held after 100 days."** Confirmed. The SEC-hosted text: "only around
   two-thirds of the bonds have been sold after 100 days" for downgrade exclusions, versus "most of the
   acquired inventory of the low-maturity bonds has been sold off" within two weeks. The BFI working
   paper states the same finding in the plan's own words almost exactly: "dealers on average do not sell
   one-third of the buildup again within 100 days." Verified, both sources agree.
2. **"The dealer is therefore exposed to further deterioration in a credit whose deterioration is
   precisely what forced the sale."** Not a direct quote (the paper does not use this exact framing) but
   a sound inference from what is directly stated: dealers hold downgraded bonds on inventory for months
   rather than weeks, and the bonds are on inventory precisely because they were downgraded - i.e.
   already deteriorating credits. Holding a deteriorating credit for an extended window is, definitionally,
   exposure to further deterioration of that same credit. Reasonable, not overstated.
3. **"The paper attributes the dealer's higher compensation specifically to that riskier and longer
   hold."** Verified verbatim. Both source PDFs state, in nearly identical language: "the costs are
   higher for the downgrade event compared to the low-maturity event as would be expected, because the
   downgraded bonds are both more risky and kept longer on inventory."

**Does the derivation establish crash-correlated inventory rather than a quickly-turned funding spread?**
Yes, on the facts checked, with one boundary worth naming. The paper directly establishes: a multi-month
hold (not a same-day flip), of a single-name credit that has just deteriorated, compensated specifically
for that risk and duration. That is inventory risk in the ordinary sense, not a funding-rate service.
What the paper does not itself measure is correlation with systemic/market-wide crashes specifically -
it studies dealer behaviour around individual downgrade events, not around index-wide stress episodes.
D6.2's leap from "holds a deteriorating single-name credit for months" to "crash-correlated inventory"
is the plan's own inference (that single-name credit deterioration clusters with, and dealer capacity for
absorbing it shrinks during, systemic credit stress), not something Dick-Nielsen and Rossi state in those
terms. It is a standard and defensible inference in credit-risk economics, and it is the same
characterisation the second pass already accepted after its own (narrower) check - this pass concurs
independently, but flags it as inference rather than direct textual support, for the same reason the
second pass did.

## Docket item 6 - the +0.253 versus +0.2724 flag: PASS, flag is accurate

`_plan.md` carries a `[!question]` callout stating both figures exist, that they are "plausibly the same
guard over different windows" (the loader's 1,889-day intersection window versus the smoothing commit's
deliberate one-month horizon), that it was "not chased down," and that "§8 must reconcile the two or
report neither." Checked: +0.2724 appears only in the loader result (`bd show aegis-rd-n77e`,
`the-premium-is-rent-on-a-balance-sheet.md`) and this callout; +0.253 appears only in commit
`03ece3b7`'s message and the role article's updated hypothesis-list entry, and this callout. No other
place in `_plan.md` uses either figure inconsistently with this framing - grepped both figures across the
file and both occurrences of each are accounted for above. The reconciliation itself was not attempted,
per instruction.

## Regression checks

**Staleness against a moving repo.** This is the check that blocked the first and second passes, so it
was run properly rather than assumed clean. `git log --all --since` the smoothing commit
(`03ece3b7`, 03:27:08) shows exactly one further commit before now: `8897d9eb`
("archive the demeter strategies no live config uses," 03:42:05), which removes three unused demeter
components and their tests; its own message confirms `carry_floor.yaml` "still resolves against its
lock," so it does not touch anything D8 or D7 depend on. `_plan.md`'s own filesystem mtime is 03:51:38,
after both commits, and the current time at the point of this check is 03:58 - no commit has landed since
`_plan.md` was last saved. Every "does not exist / not yet run / not chased down / has not been argued"
assertion in the current text was checked against this window specifically:

- D6.1's Bassi NEEDS-VENUE-CHECK flag - `_sources.md` (mtime 01:20, unchanged since well before this
  session's later commits) still carries the same status; nothing resolved it. Accurate.
- D7's "the corpus does not currently supply [a forward cap]" and "whether that suffices has not been
  argued anywhere" - no commit or `bd` issue found addressing sleeve-level capital sizing beyond
  `SLEEVE_GROSS_LIMIT` itself. Accurate.
- D8's reconciliation flag, "not chased down" - confirmed, no follow-up commit touches either figure.
  Accurate.
- D8's own standing-lesson callout ("Anything in this file asserting that a measurement does not exist
  must be re-checked against `git log` and `bd` immediately before drafting") is present in the text as
  instructed, and this pass is itself evidence the instruction is being followed rather than merely
  stated.
- One item outside `_plan.md`'s own claims, noted but not a plan defect: `bd show aegis-rd-n77e` still
  reports the issue OPEN with notes reading "REMAINING: unit test [...] and commit," which is itself
  stale (both the test file and the commit exist, at `bf8ac1ee`, confirmed by `git log` and `ls`). This
  is a tracker-hygiene gap in `bd`, not a misstatement in `_plan.md`, which already states the correct,
  current position ("the ΔΘ̂ loader landed [...] and the test has been run. Any statement that it cannot
  be run is out of date"). Flagged for whoever owns the issue tracker, not a fix item for the plan.

**Altitude.** Checked D7 and D8 specifically, since they are the material this pass had to read closely.
D7's vocabulary (`SLEEVE_GROSS_LIMIT`, `convergent_tail_budget`) is portfolio-construction/risk-control
terminology, not a behaviour label being classified - the altitude test applies to how occupants and
behaviours are named, and D7 is not naming an occupant. D8's vocabulary (`convergent_smoothing_index`,
$\xi$, Sharpe inflation, `carry_floor.yaml`) sits inside a fenced empirical paragraph reporting a
measurement, the same exemption the team lead's brief already grants to D6.2's "fallen angels" callout.
"ILS" and "cat-bond funds" appear in D8 as candidate/occupant names, the same usage pattern established
and cleared for D6.5's ILS treatment - not the behaviour label itself. No new violation found.

**① boundary.** D7 cites ① §5.4 for "the principle" of a convexity-premium budget line and does not
argue with or amend what §5.4 assigns; D8 does not address ① at all. Neither reintroduces the "this paper
corrects ①" framing the orchestrator produced twice earlier in the pipeline.

**Internal coherence.** The thesis's four clauses ("earn a positive expected return in ordinary markets;
sell convexity [...]; place that inventory's loss [...]; be ranked on its contribution") map cleanly onto
D7's "the first clause [...] is an ex-ante claim" and D4's "the income clause forces the collision and the
contribution clause fails by construction" - same four clauses, consistently referenced. D8's measured
result lands as Indeterminate, which is exactly D4's own definition of that row, and D8 explicitly states
it must not reshape D3, D4 or D5's substance, which it does not (the smoothing finding changes confidence
in the *measurement*, not the reported value or verdict). D5's superseded-finding callout is untouched and
still correctly fenced. No new contradiction found beyond the two presentational gaps already reported
under docket items 2 and 3 above.

**Conventions.** Re-counted em-dash occurrences (byte pattern for U+2014) directly, not trusted from
either prior report: zero across all nine `_`-prefixed income-engine documents (including
`_integrity.md` and `_integrity_rerun.md` themselves) and zero across the five source notes cited by D8
and D2 (`the-premium-is-rent-on-a-balance-sheet.md`, `the-payer-did-not-leave-the-supply-arrived.md`,
`window-dressing-at-the-regulatory-snapshot.md`, `income-must-accrue-not-be-captured.md`, and the role
article `what-makes-a-convergent-sleeve-an-income-engine.md`). The convention holds.

## What should be fixed before drafting, ordered by severity

Neither item below is blocking. Both are real and mechanically small.

1. **[MEDIUM] Close D4's exhaustiveness gap.** Add a named row (or an explicit note) for a candidate
   whose $\Delta\hat\Theta > 0$, whose interval excludes zero, and which is *above* simply holding more
   responder - the genuine-success case, currently mapped to no row in the table. Under the table's own
   logic this is the single outcome that would settle "Role dead" in the negative for the whole existence
   claim, and it is currently the one case the taxonomy does not name.
2. **[MEDIUM] Tighten D7's header against its own downgraded body.** "The peso problem is answered by
   budgeting, not by indifference" and the "Consequence for the contract" framing read as more settled
   than the body's own admission that the cap's sufficiency "has not been argued anywhere." Soften the
   header or add one sentence naming the open requirement at the point a reader would otherwise stop.

## Limitations

**Scope discipline was honoured.** This pass did not re-verify the ~185-source register beyond the two
primary-source checks the docket named or clearly implied (Dick-Nielsen and Rossi for docket item 5,
independently re-fetched rather than reused from the second pass's excerpts; the smoothing commit and
article diff for docket item 1), did not re-run the 7-mode checklist, and did not reopen anything either
prior pass already cleared.

**The D8 "OTC-marked" characterisation of cat-bond funds is accepted as a supported inference, not
independently traced to a single source that states it in those words.** The supporting facts (SHRIX
and, by the same vehicle family, Twelve and Schroder GAIA, are NAV-priced open-end funds rather than
exchange-traded) are directly sourced; the specific term "OTC-marked" applied to that fact is D8's own
synthesis. Reported as such rather than either waved through as verbatim-cited or flagged as a defect.

**The D6.2 primary-source re-check used the same publicly available PDFs the second pass used** (SEC
background PDF, BFI-hosted working paper), fetched independently this pass rather than reused, but not a
fresh route to the final peer-reviewed RFS text. This is the same standard of verification the corpus
applies elsewhere to this specific paper (already peer-reviewed and identified, per the first pass's
Phase A), not a new gap.

**The staleness sweep covers the window between the smoothing commit and the time of this check
(2026-07-25, 03:27 through 03:58) and the specific assertions enumerated above.** It is not a claim that
every sentence in `_plan.md` was individually re-verified against `git log` - it is a targeted check of
every assertion this pass identified as claiming a measurement, script, or citation status does not exist,
is unrun, or is open, per the team lead's explicit instruction that this is a repeat-offender category.

**D4's exhaustiveness finding is this pass's own logical reading of the table, not a primary-source or
code check.** There is no external authority to verify a taxonomy's completeness against; the finding
rests on enumerating the possible sign/significance/benchmark combinations against the four stated rows.
