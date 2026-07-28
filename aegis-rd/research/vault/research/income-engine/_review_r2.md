---
title: "Convergent Engine - Reviewer 2 report"
date: 2026-07-25
tags:
  - review
  - income-engine
  - referee-report
---

# Reviewer 2: research methodology, statistical inference, performance measurement

Independent assessment written before reading `_argument.md`, then reconciled against it per the
review protocol. Section headers state which claims are mine, which overlap with `_argument.md`, and
where I disagree with it.

## Recommendation: Major Revision

The plan's inferential architecture is unusually disciplined for a plan-stage document: it names its
own falsification structure in advance, tracks a prohibition list of 37 things the draft may not claim,
carries commit-hash provenance for every measured number, and has already survived one internal
adversarial pass that produced real repairs (D6, D7). None of the problems below require abandoning a
decision already taken. But several of them are foundational to how the paper's one reported empirical
result gets read, and they need to be closed **before** drafting begins, not polished into the prose
afterward: the chronology behind the verdict table's "indeterminate" criterion is asserted rather than
demonstrated (M2), the "role redundant" benchmark the table requires is not shown to exist anywhere in
the corpus (M5), two different figures for the same downside-correlation guard remain unreconciled and
already-flagged as unfit to quote (M8), and the commission-discharge language in `_synthesis.md`
overstates what D7's own epistemics permit the paper to claim (M3-M4). None of these are objections to
the plan's decisions; they are objections to whether the plan has yet built what its own decisions
require.

## Summary of the claim, in my own words

The paper argues that a convergent (short-convexity) sleeve is not a mechanism but a portfolio role:
an occupant earns its seat by (1) delivering positive expected return in ordinary markets, (2) doing so
by genuinely selling convexity rather than by some behaviour that happens to have no crash to place,
(3) placing that crash inventory's loss where the book's convex responder pole does not also fail, and
(4) being ranked by its marginal certainty-equivalent contribution to the paired book (ΔΘ̂, a
manipulation-proof power-utility statistic borrowed from a companion article) rather than by standalone
smoothness. Clause 1 is stated, following D7, as an ex-ante claim that realised returns cannot verify
(a peso-problem argument), so the paper's only genuine empirical test targets clauses 3 and 4 jointly.
A five-row verdict table pre-registers how any single candidate's ΔΘ̂ measurement should be read, one
candidate (`carry_floor`) has actually been measured and reads indeterminate, and that result is fenced
to one paragraph on the ground that a single non-significant candidate cannot speak to an existence
claim about the role.

## Major concerns

### 1. D4's five-row table mixes two logical types, and only one of the two is operationally usable

Four rows (indeterminate, candidate fails, role redundant, seat earned) are mutually exclusive and
jointly exhaustive **for a single candidate's single measurement**: they partition on whether the
interval spans zero, and if not, on the sign and size of the point estimate relative to a benchmark.
The fifth row, role dead, is a different kind of claim: a universal statement that the role's clauses
are jointly unsatisfiable **for every candidate, across a space the plan itself says nobody can
enumerate**. `_argument.md` already reaches this conclusion independently, in stronger and more
concrete terms than I would put it myself: it notes the 27-cell composite re-rank, a clean multi-cell
negative result, was read as "no floor partner on this universe and window" rather than as role death,
and concludes the third verdict is "operationally a verdict nobody will ever actually render... a
hostile referee calls this unfalsifiable-in-practice wearing falsifiable clothing." I agree with that
finding and credit it to `_argument.md` rather than claim it as my own.

What I would add, as my own contribution: the table does not say **which** of two very different
routes is meant to settle the row, and the ambiguity matters for whether the row can ever bind anyone.
One route is empirical: keep testing candidates and declare the role dead once enough of them have
failed. That route has no stopping rule anywhere in the plan, no answer to "how many candidates, across
how many venues and windows, before permanence is asserted," and given the corpus's own quantifier
("nobody can enumerate the candidate space") it is not clear a stopping rule could even be written. The
other route is structural: an a priori argument, in D2/D6.4's register, that clauses 2 and 3 are
provably incompatible given the roster this paper is nested inside (selling convexity necessarily means
selling into the Target's own wing). That route is a proof, not a measurement, and belongs with the
paper's argument sections, not with a table that otherwise reports statistical verdicts. As written, D4
reads as though the empirical route settles the row ("the four clauses are jointly unsatisfiable"
phrased as an outcome of testing), while the actual textual support for it (D2's derivation) is
structural. **Remedy:** state explicitly which route governs role dead. If structural, move the clause
out of the verdict table into the argument proper and say plainly that no accumulation of empirical
non-results can establish it. If empirical, name the stopping rule in advance.

### 2. The chronology behind D4's "indeterminate" criterion is asserted, not demonstrated

This is my own finding; `_argument.md` does not raise it. D4 states that the indeterminate row "was
added after the first Stage 2.5 gate and it is a repair to the taxonomy, not a concession to a number...
The row would be correct even if nothing had ever been measured." That is exactly the right defence
against the suspicion the assignment raises (was the taxonomy shaped around a known unfavourable
result), but it is asserted in prose rather than demonstrated. The plan's own text gives concrete reason
to doubt any un-timestamped chronology claim in this specific document: D8 records, twice, that the plan
was caught stating something false about measurement status because a commit landed in the repo while
the plan was being drafted ("the vault is being committed to by another session while this plan is
written, so a plan artifact goes stale against a moving repo... this is the second finding of the same
shape"). A pipeline that has already been caught twice writing prose that outran the repo's actual state
is not a pipeline whose "we designed this before we saw the number" claim should be accepted on its own
word. **Remedy:** cite the commit hash and timestamp at which D4's table, specifically the
interval-spans-zero criterion for indeterminate, was fixed, and show it predates both the loader
(`aegis-rd-n77e`) and the commit that produced ΔΘ̂ = -0.014055. This is a cheap check against the repo's
own history and it is the single most important thing that would make D8's fencing (see concern 4)
straightforwardly honest rather than merely asserted to be so.

### 3. The commission-discharge language overstates what D7's own epistemics permit

This is my own finding. `_synthesis.md` §2 states that "'each role holds on its own terms' is squarely
ours and ΔΘ̂ is the instrument," and that the role "holds when all three [now four] clauses hold
simultaneously for at least one candidate." `_argument.md`'s own per-section stress test of the
commission section takes this framing as settled ("the seat paper discharges the first fully") and does
not test it against D7, which is a later addition to the plan and directly undercuts it. D7 states
plainly that compensation adequacy is unverifiable on realised returns, that the seat must therefore be
"admitted on rationale" rather than verified, and that the forward cap needed to bound the unverifiable
risk "the corpus does not currently supply." Put those two documents next to each other and there is a
real tension: ΔΘ̂, the instrument `_synthesis.md` names as discharging "each role holds on its own
terms," is a joint statistic over placement and contribution (clauses 3 and 4). It does not, and by D7's
own argument cannot, check whether the income (clause 1) is adequate compensation for the risk being
carried. So "seat earned" in D4's table never actually tests clause 1; that clause is admitted purely on
ex-ante rationale and left permanently unguarded except by a cap that does not yet exist. That may be an
entirely defensible position under the vault's own backtest-estimates-not-discovers epistemology, but
"discharges... fully" is not an accurate description of it. **Remedy:** reconcile the language in
`_synthesis.md` and the eventual §9/conclusion with D7's more circumspect framing before drafting.
Wherever "the role holds" is asserted, say explicitly that this covers clauses 2 through 4, and that
clause 1 remains ex-ante only, pending the cap D7 names as owed.

### 4. Answering the assignment directly: D7 does not leave the thesis empirically empty, but it leaves its central risk unguarded, and the paper's summary language should say so

`_argument.md`'s own weakest-point #3 flags that D3's "indifference" framing, prior to D7, oversold its
resolution of the peso problem: a positive ΔΘ̂ is equally consistent with "fairly priced" and with "a
peso-problem trade that has not yet paid its bill," and D4's protocol has no defence against the second
reading for a positive result. Reading the plan's revision history, D7 is visibly the authors' answer to
exactly that objection, replacing "indifference" with "admit on rationale, bound by a forward cap, never
claim verification." I agree that this is a genuine improvement (see "What the paper gets right"), and
it directly answers the assignment's framing question: no, the thesis is not globally empirically empty,
because clauses 2 through 4 carry real, testable content (structural admission criteria plus the ΔΘ̂
placement/contribution test). What D7 does **not** do is supply the safety mechanism it says the seat
needs. The gap the plan honestly names ("the corpus does not currently supply one... whether that
suffices has not been argued anywhere") is exactly the property most referees and most allocators will
ask about first: is this seat's compensation minimally adequate for the tail risk it warehouses, or is
it collecting nickels in front of a steamroller that has not yet arrived in the sample? The honest
answer, on the plan's own terms, is "we do not know and cannot know from realised returns, and we have
not yet built the bound that would let us act safely regardless." That is a coherent position, but it
belongs in the paper's thesis-level language (abstract, §1), qualifying "the role holds" as conditional
on a cap not yet built, not three levels down in a decision note only the drafting stage will see. On
whether ①'s §4.4 commission ("each role holds on its own terms") can be discharged at all under D7's
epistemics: partially. The structural half (does a coherent, well-specified role exist, with derivable
admission criteria) can be discharged and, per M1, largely already is. The adequacy half cannot be
discharged by this paper's methods, and the paper should say so as a scope statement rather than let the
commission-discharge language imply otherwise.

### 5. The "role redundant" benchmark is not shown to exist anywhere in the corpus

This is my own finding; `_argument.md` does not raise it. D4's "role redundant" row requires ΔΘ̂ > 0
with an interval excluding zero "but below simply holding more responder." ΔΘ̂ is already defined as
Θ(blend) minus Θ(responder alone), so "seat earned"'s further requirement, "above the responder-only
benchmark," cannot be the same quantity ΔΘ̂ already nets out, or the two rows collapse into one. The only
reading that keeps the rows distinct is an opportunity-cost comparison: Θ(responder scaled up to consume
the risk budget the convergent candidate would have used) minus Θ(responder at its current mandate
weight). That is a legitimate comparison, and I do not think it strays into the allocation-theoretic
territory the metric's own Limitations section disclaims, since it is still a with/without ranking
between two fully specified books rather than a claim about how much of one book's value "belongs" to a
sleeve. But it is a second statistic, not currently named as implemented anywhere in `_sources.md`,
`_buildability.md`, or D8's own reported measurement, which reports only ΔΘ̂ and downside correlation for
one candidate against the responder-alone baseline. As written, the table cannot today distinguish role
redundant from seat earned in practice, because the comparison that would do so has not been shown to
be built. **Remedy:** specify the "more responder" comparison precisely (how much more, at what fixed
risk budget or capital) and confirm it exists in the codebase, or, like the fast-segment loss the
synthesis already flags as an owed research obligation (`_synthesis.md` gap 6), name it as owed rather
than presenting the table as a functioning four-way discriminator today.

### 6. Repeated-look risk across time is a separate multiplicity problem from the cross-candidate one the plan already handles

This is my own finding. The metric article correctly cites White's Reality Check and Hansen's SPA test
for the multiplicity introduced by searching a grid of candidates, and the plan is right to treat that
as solved machinery. But D8's own framing of §8's shape ("reports the measured instance, then
pre-registers what would move it **off indeterminate**") is, read carefully, a commitment to re-run the
same test on the same growing daily series as more data accrues. Re-running a test repeatedly and
stopping the first time the confidence interval excludes zero is optional stopping: it inflates the
effective false-positive rate relative to a single pre-specified look, and neither Politis-Romano's
stationary bootstrap nor Ledoit-Wolf's studentized interval correct for it, because both are designed
for inference within a single sample, not for a sequence of samples examined repeatedly over time.
**Remedy:** state a re-test cadence in advance (for example, annual, or tied to a fixed number of
additional trading days) and either a sequential-testing correction or an explicit statement that any
future "seat earned" reading from a repeated look is provisional until confirmed by a single,
non-cherry-picked test at the pre-declared cadence.

### 7. Whether `carry_floor` itself carries an unstated selection history

This is my own question, not a finding; I could not resolve it from the documents available to me.
D8 reports one candidate (`carry_floor`) at the book's mandated tilt. If this candidate's construction
was fixed independent of any ΔΘ̂-informed search (i.e., it is simply the desk's one live, mandate-driven
occupant), the single-test framing is clean and no correction is owed. If `carry_floor` was chosen,
even informally, because earlier exploration (including the 27-cell composite re-rank, which the plan
says used a related evaluation apparatus) suggested it was more promising than alternatives, then the
paper owes it exactly the correction its own cited machinery already knows how to apply (White 2000,
Hansen 2005), and the corroboration D8 offers ("corroborates the -0.0115 archived from a superseded
implementation") should state clearly whether that superseded implementation was itself a selected
winner or a fixed, pre-specified candidate. **Remedy:** state explicitly in §8 whether `carry_floor`'s
parameters were fixed independent of any ΔΘ̂-informed search.

### 8. The two unreconciled downside-correlation figures must be closed before either is quoted

D8 already flags this as an open item ("+0.2724... and +0.253... Not chased down. §8 must reconcile the
two or report neither"), so I am not discovering it, only elevating its status. This is squarely inside
my mandate (measurement architecture) and it is a live blocking item, not a stylistic footnote: two
different pipelines produce different values for what is presented as the same guard statistic, and
neither figure should appear in a draft until the discrepancy is understood, whether as a genuine
horizon effect (one-month versus the 2-6 month band the shape reports use) or as a pipeline
inconsistency. **Remedy:** treat this reconciliation as a hard blocker on the same footing D8 already
gave the ΔΘ̂ loader premise, to be closed before any drafting session that touches §8, not discovered
mid-draft.

## Minor concerns

- **ρ sensitivity is not shown for the reported result.** The metric article's own guidance states
  rankings are "fairly stable" across ρ ∈ [2,5] but "should be verified per sweep." D8 reports the
  single-book measurement at ρ = 3.0 only; a one-line sensitivity report across the stated range would
  cost little and would materially strengthen confidence that "indeterminate" is not itself an artefact
  of one risk-aversion parameter choice.
- **The stationary bootstrap's block-length selection is not stated.** Report the method used (for
  example, Politis-White automatic block-length selection) alongside the reported intervals, for
  reproducibility.
- **The overlapping-window/inference distinction should be stated explicitly in §8, not only inherited
  from the source article.** The plan correctly distinguishes descriptive shape statistics computed on
  overlapping 2-6 month windows from the inferential confidence intervals computed by block-bootstrapping
  the underlying daily pairs. This is the right discipline and it is well cited (Politis-Romano,
  Ledoit-Wolf), but the paper's own §8 should restate the distinction rather than assume the reader
  imports it from a companion article.
- **The smoothing-profile measurement (ξ = 1.0000, negative first-order autocorrelation as evidence of
  bounce rather than staleness) is genuinely well-executed diagnostic work** and should stay scoped
  exactly as written, to this sleeve and this feed, rather than generalised in the drafting stage's
  prose.

## What the paper gets right

- The plan's own revision history shows real adversarial engagement, not box-ticking: the indeterminate
  row was added because the original table could only ever ratchet toward pessimism; the seat-earned row
  was added because the original table named no way to succeed; D6 produced five concrete repairs after
  `_argument.md`'s stress test; and the vol-matching concern flagged in an earlier stress-test pass was
  closed, correctly in my independent reading, with a controlled measurement (12/12 correct placement
  decisions under the floating-volatility convention against 9/12 under vol-matching at the live sleeve's
  own drift) rather than by assertion.
- D7's move from "indifference" to "admit on rationale, bound by forward cap, never claim verification"
  is a genuine methodological improvement over the position it replaces, and it correctly locates where
  the peso problem actually bites (adequacy, not the fair-versus-excess question D3 originally framed).
- The Tasche scope correction is precise and mathematically checkable: a CRRA certainty equivalent is not
  homogeneous of degree 1 (Θ(λr) ≈ λμ − (ρ/2)λ²σ² under the stated approximation, not λΘ(r)), so
  Proposition 2.2's Euler/RORAC guarantees genuinely do not transfer, and the plan correctly restricts
  itself to borrowing only the with-minus-without arithmetic.
- `_synthesis.md` §5's 37-item prohibition list is an unusually strong pre-commitment device against
  scope creep and post-hoc reinterpretation, and it is the kind of binding mechanism a methodology
  reviewer usually has to demand rather than find already built.
- Commit-hash-level provenance for every measured number (`aegis-rd-n77e`, `110507ad`, `03ece3b7`,
  `aegis-rd-600y`) is good practice and is exactly what made concern 2 above checkable in principle, even
  though the check itself has not yet been performed in the document as written.

## Novelty statement

The paper's methodological contribution is not a new statistic. ΔΘ̂ is inherited wholesale from the
companion role article, itself a direct application of Goetzmann-Ingersoll-Spiegel-Welch's
manipulation-proof performance measure. The contribution, from a methodology standpoint, is the
falsification protocol built around that statistic for a specific claim shape (does a portfolio role
exist, evidenced by at least one admissible occupant) rather than the more common claim shape the cited
literature addresses (does a specific strategy or factor earn a premium). Most of the performance-
measurement literature this paper draws on (GISW, Tasche, the MPPM/Doubt-Ratio pair) stops at defining a
ranking statistic; comparatively little of it engages with how to pre-register a decision procedure that
distinguishes an underpowered null from a genuine negative result for an existence claim. That is a real
and useful contribution if it is finished. It is also, precisely, the part still under construction: the
role-dead row's stopping rule (concern 1), the role-redundant benchmark (concern 5), and the repeated-
look discipline (concern 6) are the falsification protocol's own load-bearing joints, and none of them
is yet fully specified.

## Note on independence

Per the review protocol: concerns 2, 3 (as applied against `_synthesis.md`'s specific "discharges...
fully" language), 5, 6, 7, and the formal mutual-exclusivity/exhaustiveness check underlying concern 1
are my own, reached before I read `_argument.md`. Concern 1's headline finding (role dead is
unfalsifiable in practice) and concern 4's framing (D3's original "indifference" oversold its resolution
of the peso problem) were already identified by `_argument.md`; I have credited them there and added
only the two-epistemic-routes distinction (concern 1) and the direct answer to whether D7 leaves the
thesis empirically empty (concern 4), which `_argument.md` does not address since D7 postdates its
stress test. Concern 8 was already self-flagged by the plan (D8's own reconciliation note); I have
elevated its status rather than discovered it. I did not find grounds to disagree with any conclusion
`_argument.md` reaches within its own scope (D5, §6's dependency on the Target tier, §7's sign-inversion
claim); those fall outside this reviewer's assigned mandate and I have not re-litigated them here.
