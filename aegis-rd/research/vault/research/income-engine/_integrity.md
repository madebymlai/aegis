---
title: "Convergent Engine - Stage 2.5 integrity verification"
date: 2026-07-25
tags:
  - integrity
  - verification
  - income-engine
---

# Stage 2.5 integrity verification - convergent engine

> [!danger] VERDICT: BLOCK
> Two findings, both on the same load-bearing repair chain (D5's finding, repaired by D6.1-D6.3, which
> the stress test itself calls "the paper's most exposed load-bearing claim"):
>
> 1. **D6.2's fallen-angel mechanism is inverted relative to its own cited source.** `_plan.md` and
>    `_argument.md` both state "the tracker is the forced *buyer* of a bond that has just fallen, and
>    the compensated party is the dealer warehousing/supplying it." Dick-Nielsen and Rossi (2019, *RFS*
>    32(1):1-41) - the paper actually behind the "not replicable by other investors in the economy"
>    quote - studies index *exclusions*: the tracker is the forced **seller**, and the dealer is the
>    **buyer** who warehouses the bond and earns the non-replicable return. The vault's own
>    `income-must-accrue-not-be-captured.md`, which `_plan.md` cites for this exact quote, states the
>    direction correctly ("index trackers are the forced sellers and dealers the compensated
>    providers"). D6.2 and its parent stress-test passage in `_argument.md` both reverse it. This is one
>    of only two counterexamples propping up the paper's central repair (D5 to D6.1-D6.3); it needs
>    correction before drafting, not merely a caveat.
> 2. **D6.1's repair, and by extension §3's flagship exception, rest on a citation the corpus itself has
>    not closed.** Bassi, Behn, Grill and Waibel (2024, *JFI*) remains formally **NEEDS-VENUE-CHECK**
>    (the final peer-reviewed PDF is paywalled; the sample period and figures are corroborated three
>    ways against the working-paper predecessor but not read in the published text). `_argument.md`
>    already flags this itself ("that citation gap becomes load-bearing rather than a footnote-level
>    flag") but `_plan.md`'s D6.1 does not carry the flag forward at the point of use.
>
> Neither finding is a fabrication. Both are narrow and mechanically fixable: correct the buyer/seller
> direction in D6.2 against the primary source, and carry Bassi et al.'s NEEDS-VENUE-CHECK flag into
> D6.1's own text (or close the citation before drafting). Because both sit on the paper's single most
> exposed claim, per the stress test's own assessment, they are blocking rather than footnote-level. See
> [Phase B](#five-phase-findings) and [Load-bearing claims resting on unclosed citations](#4-load-bearing-claims-resting-on-unclosed-citations)
> below for full detail, and [What must be fixed before drafting](#5-what-must-be-fixed-before-drafting)
> for the fix.
>
> **A third item, non-blocking but real, surfaced while tracing Mode 1 at the claim level rather than
> clearing it by paper type.** `_argument.md` §8 states the ΔΘ̂ metric's scale convention "was found to
> be misdescribed and sign-flipping under a vol-matched convention," drawn from a warning callout in
> `notes/the-premium-is-rent-on-a-balance-sheet.md`. That warning has been superseded: the same-session
> bd issue tracking it (`aegis-rd-600y`) closed WONTFIX, with the floating-volatility convention
> confirmed correct by the governing article and by measurement (12/12 correct placement decisions at
> every drift tested, including the live sleeve's own, against 9/12 for the vol-matched alternative the
> warning favoured). `_argument.md` was not updated after the issue closed. Not a block reason on its
> own - it does not touch any of D1 through D6 - but listed in the fixes below because it currently
> misdescribes a resolved question as open.
>
> Everything else checked - three other named citations, all three flagged in-house numbers, both
> code-dependent claims (once traced past a stale note to the closed issues behind them), the em-dash
> convention, the fold's originality, and the frame-lock question - came back clear. This is a narrow
> block on two specific, correctable items plus one documentation-currency item, not a verdict on the
> plan's overall soundness.

## 1. The 7-mode table

| Mode | Verdict | Evidence |
|---|---|---|
| 1. Implementation bug | CLEAR on the code; a resolved false alarm is still propagating in `_argument.md` | Both code-dependent claims enumerated and traced; no bug in either. One claim's supporting vault note contains a now-superseded warning that `_argument.md` §8 has not caught up with. See below. |
| 2. Hallucinated citation | SUSPECTED (narrow) | D6.2's Dick-Nielsen and Rossi attribution is inverted. See below. |
| 3. Hallucinated experimental result | CLEAR (verified) | All three in-house numbers enumerated and traced to primary logs with matching figures. See below. |
| 4. Shortcut reliance | CLEAR - already fixed at the source, not merely fenced | See below (revised after tracing `aegis-rd-v1k7`). |
| 5. Bug reframed as novel insight | CLEAR | See below. |
| 6. Methodology fabrication | CLEAR on the letter, flagged for currency | See below. |
| 7. Frame-lock | CLEAR, one caveat | See below. |

*(Full reasoning for each mode follows in the sections below; this table is a summary, not the argument.)*

### Mode 1 - implementation bug

**Scope statement, corrected.** The team lead's first brief attributed the theoretical-paper carve-out
to Modes 1, 5 and 6 together; the reference's Open Questions section in fact names only 1, 5 and 6 for
the *log-dependence* rationale, and separately Mode 3's own detection text is log-dependent without
being named in Open Questions - the spec under-counts its own false-positive exposure on Mode 3, noted
again in Limitations below. More importantly, per the team lead's correction, this is not a pre-filter
being applied *to* the spec but the spec's own `CLEAR` definition being applied correctly: `CLEAR`
requires evidence a mode does not apply, and "this artifact makes no claim that invokes the mode" is
exactly that evidence when it can be shown by enumeration. So the method here is: enumerate every claim
in `_plan.md`, `_argument.md` and the notes they draw on that invokes Mode 1 (any assertion whose truth
depends on code *output* rather than code *existing*), and resolve each one rather than clearing the
mode at paper level.

**Enumeration.** Two claims found:

1. **D4's 27-cell composite re-rank** depends on the output of `composite_allocator_utility` /
   `delta_theta` as computed in `metrics/custom/carry.py` on 2026-07-04 (`scratchpad/cascade_rerun.py`).
2. **The new ΔΘ̂ loader result** (not yet cited in `_plan.md`, but live in `notes/the-premium-is-rent-on-a-balance-sheet.md`
   and referenced by `_argument.md` §8's caution about the metric) depends on the output of
   `evaluate_allocator_contribution` / `AllocatorContribution.earns_its_seat` in
   `research/aegis_research/metrics/custom/convergent.py`, run via the `aegis-rd-n77e` loader.

**Resolving claim 2 required tracing past the vault note's own text to the code and issue tracker,
because the note contains an internal contradiction the plan has not yet resolved.**
`the-premium-is-rent-on-a-balance-sheet.md` carries a "[!warning] Correction, same day" callout, placed
before its own "Measured 2026-07-25" result, stating that ΔΘ̂'s sign is "set by a scale convention that
the code's own docstring misdescribes," that re-levering both books to a common volatility "flips the
sign" to positive, and that "this measurement cannot currently decide whether the pole earns its seat."
Taken at face value, this would make claim 2 a live Mode 1 finding: a disclosed implementation
ambiguity feeding an unresolved-sign result.

It does not survive tracing to the code and issue tracker. `git log` on `convergent.py` shows three
same-morning commits after that warning was apparently written: `77565936` (refactor, creates
`evaluate_allocator_contribution`), `6800fb78` (fix, corrects the docstring the warning complains
about), and `4de70d6c` at 2026-07-25T02:17:06+02:00, titled *"the blend's floating volatility is the
specification, not a defect."* Its message states plainly that the audit producing the "central
confound" framing "never checked" the governing article
(`what-makes-a-convergent-sleeve-an-income-engine`) before proposing a fix, and that the article
specifies the float directly: *"the blend's volatility then floats with the correlation structure,
which is the diversification signal."* The bug this issue was tracked as, **`aegis-rd-600y`, is CLOSED
WONTFIX**, with a measured basis: on a matched-marginal fixture with known ground truth (two poles with
identical standalone statistics, differing only in whether losses land on trend's worst days), the
floating-volatility convention correctly ranks the decoupled pole ahead of the co-crashing one at
**every drift tested, including 12/12 at the live sleeve's own +4.2%/yr**, while the vol-matched
alternative the warning favoured scores only **9/12** at that same live-relevant drift. The current code
(`convergent.py:102-110, 235-260`) documents the float as intentional, citing the same source. **The
floating-volatility convention - the one that produced ΔΘ̂ = -0.014055 - is confirmed correct, not a
bug.** A related, separately-filed finding on the same thread (`aegis-rd-v1k7`, the claim that ΔΘ̂ "is
exactly Tasche's marginal risk contribution") is also **CLOSED, fixed** in the source article itself
(commit `110507ad`) - the category error identified in Mode 4 below has already been corrected at its
source, not merely flagged downstream.

**The consequence for the plan's own materials, not the code.** `notes/the-premium-is-rent-on-a-balance-sheet.md`'s
"Correction, same day" callout was never updated after `aegis-rd-600y` closed WONTFIX eight minutes
later in the same session, and it still reads as if the sign is undecided. `_argument.md` §8 draws on
that stale state directly: *"the code's own scale convention was found to be misdescribed and
sign-flipping under a vol-matched convention."* That sentence describes a concern that has since been
investigated and rejected by the person who raised it, using the governing article and a controlled
measurement, not merely reasserted. This is not an implementation bug reaching the plan - it is a
resolved implementation question whose resolution has not yet propagated from the code and issue
tracker back into the vault note and the argument document that cite it. Listed as a fix item below
because a drafting stage reading `_argument.md` §8 today would inherit the stale caution.

**Claim 1 (the 27-cell result)** uses the same floating-volatility convention by design - the
2026-07-04 run diary itself describes building it that way ("pinning each *leg* and letting the *blend*
vol float fixes it") specifically to avoid rewarding co-crashing, which is the same convention
`aegis-rd-600y` later confirmed correct. No defect found; if anything the later confirmation
strengthens confidence in this earlier result's methodology.

**Verdict: CLEAR on the code itself** - no implementation bug found in either piece of code, and the
apparent Mode 1 candidate (claim 2, via the vault note's warning) resolves to a false alarm once traced
past the note to the closed issue and the current source. **Not CLEAR on propagation** - see the fix
list in §4, since `_argument.md` currently states the false alarm as if it were still live.

### Mode 2 - hallucinated citation

This is Phase A/B's work; see the [Five-phase findings](#five-phase-findings-detail) below for the full
citation-by-citation record. Summary: of the specific citations the team lead named for checking
(Jurek, Bollerslev and Todorov 2011, Kargar, Tomunen, Dick-Nielsen and Rossi), four verified cleanly
against primary sources with the numbers and inferences the plan draws from them intact. The fifth -
Dick-Nielsen and Rossi, used in D6.2 - exists, is peer-reviewed, and the quoted phrase
("not replicable by other investors in the economy") is verbatim and accurate, but the plan inverts
which party is forced into the trade. That is attribution drift on a real source, not a hallucinated
source - a narrower defect than Mode 2 usually catches, but squarely inside what Mode 2's brief asks a
verifier to look for ("does the source actually support the claim made of it").

No other citation spot-checked in this pass (Bollerslev-Todorov's existence and abstract, the
Gospodinov-Robotti 39-of-40 figure already independently re-verified by `_sources.md`, the two flagged
in-house numbers) showed any sign of invention. The corpus's stated base rate of prior failures (one
probably-synthetic article, one sub-agent inventing figures for a real paper) did not repeat itself in
anything checked this session.

**Verdict: SUSPECTED, narrowly.** One instance, on one load-bearing decision (D6.2). See
[Load-bearing claims resting on unclosed citations](#4-load-bearing-claims-resting-on-unclosed-citations)
and the block reasons above.

### Mode 3 - hallucinated experimental result

This is the mode the team lead flagged as most important. Per the corrected scoping, the unit is the
claim, not the paper: every in-house number in `_plan.md`, `_argument.md` and the notes they rely on was
enumerated rather than cleared by "the paper is theoretical." Three such claims exist, and all three are
resolved individually below - none cleared by paper type.

**The 27-cell composite re-rank (D4's evidentiary anchor).** `_plan.md` D4 and `_synthesis.md` §4.3 both
cite "the 27-cell composite re-rank had every cell at ΔΘ̂ < 0 with downside correlation to trend in
[+0.38, +0.49]." Traced to `aegis-rd/research/vault/runs/demeter/2026-07-04.md`, section "the re-run
cascade - composite re-rank of the 27-cell grid": *"the gate promotes nothing. All 27 cells: `delta_theta`
in [-0.0189, -0.0050]... `downside corr to trend` in [+0.38, +0.49]."* Numbers match exactly. This is a
real, logged, harness-run result (`scratchpad/cascade_rerun.py`), not an invented one. **VERIFIED.**

One nuance worth carrying forward, not itself a defect: the same run diary shows that later work the
same day (sections "Lead A", "P0 diagnostic", "P2") found the co-crash in this specific 27-cell result
was substantially a single-fast-crash, daily-frequency artefact - excluding COVID and measuring monthly,
ΔΘ̂ on the re-pinned pole flips to positive (+0.007, later +0.0117 for the re-locked floor ex-crash). The
plan does not mention this follow-up. It does not need to: `_synthesis.md`'s own prohibition 2 already
restricts the 27-cell result to "usable as demonstrations of a mechanism," and D4 uses it exactly that
way (to show how a clean negative reading gets read as "no floor partner," not "role dead") rather than
as a claim that the number itself is durable. Flagging for completeness, not as a fix item.

**The variance-premium four-market prototype (the caution box in `the-payer-did-not-leave-the-supply-arrived.md`).**
Traced to `_prototyping/global_variance_premium/README.md`, run 2026-07-25. Every figure in the caution
box matches the prototype's own "Real result" section exactly: Australia's break is the cleanest and
largest in the panel (-3.85 vol-pts, p=0.0000, the only market statistically distinguishable from the US
at z=-2.64, p=0.0084); the US result is unstable across benchmarks (S&P 500 p=0.0877, Nasdaq p=0.0025,
Dow p=0.8244 - matching "p=0.088, p=0.0025, p=0.82" in the note); the panel is four markets; the measure
is the raw implied-minus-realized gap, not alpha; vehicle AUM was out of scope. **VERIFIED**, numbers
exact, and the source prototype's own README states the "raw gap ≠ alpha" limitation more prominently
than the note that cites it does.

**The ΔΘ̂ loader's own result, not yet cited anywhere in the plan.** `bd show aegis-rd-n77e` and
`the-premium-is-rent-on-a-balance-sheet.md`'s "Measured 2026-07-25" callout agree exactly: on the live
`trend_floor` vs `carry_floor` pair (1,889 common days, 2019-01-02 to 2026-06-30), ΔΘ̂ = -0.014055,
downside correlation = +0.2724, all intervals at 21/63/126 days span zero, `earns_its_seat` = False.
This corroborates an earlier archived figure (-0.0115, `carry_floor.yaml` header, 2026-07-04) from a
superseded implementation, so the sign is not a blending artefact. **VERIFIED** as a real, run,
non-fabricated result. Its reliability (not just its existence) was checked further under Mode 1: the
convention that produced this sign was investigated as a possible bug (`aegis-rd-600y`) and closed
WONTFIX with a controlled measurement confirming it is the correct convention, not an artefact. See
Mode 6 for why its *absence* from `_plan.md` matters more than its content.

**Verdict: CLEAR.** All three in-house numbers enumerated for this paper trace to real logs or
committed, run code with matching figures. No hallucinated experimental result found, and no claim was
cleared by the paper being theoretical - each of the three was individually traced to ground truth.

### Mode 4 - shortcut reliance

The paper's nearest analogue to a shortcut is treating ΔΘ̂ as if it inherited Tasche's Euler-allocation
formal guarantees, when it borrows only the arithmetic form - a proxy standing in for a harder-to-state
target without the gap being disclosed. Traced this past `_argument.md`'s own citation to ground truth,
per the tightened scoping: the bd issue tracking it, `aegis-rd-v1k7`, is **CLOSED, fixed in commit
`110507ad`**, and the fix landed in the source article itself
(`research-legacy/what-makes-a-convergent-sleeve-an-income-engine.md`) - "bullet rewritten to claim only
the with-minus-without contribution; footnote now carries Tasche's homogeneity-of-degree-1 scope
condition; two limitations added," verified by the closer against the primary source (Tasche, arXiv
0708.2542) directly. This is a stronger state than "flagged downstream": the shortcut was not just
caught and fenced in a caution sentence, the article that originally asserted it has been corrected at
its source.

**Verdict: CLEAR.** The shortcut existed, was found, and is fixed at the source as of this session -
stronger than the "adequately fenced" reading this pass first gave it before tracing the citation past
`_argument.md`'s own text to the issue tracker. `_argument.md` §8's caution sentence remains correct in
substance and should be kept, but drafting can now cite the role article itself rather than only the
correction note.

### Mode 5 - bug reframed as novel insight

Enumerated candidate claims rather than clearing by paper type: searched `_plan.md`, `_argument.md`,
`_synthesis.md` and `_buildability.md` for surprise-shaped language ("surprisingly", "unexpectedly",
"counterintuitively", "contrary to", "strikingly", "remarkably") - zero matches, so the enumeration
itself is empty by that test. One candidate remained worth checking directly regardless, since
surprise-shaped language is a heuristic for finding the mode, not a requirement for it: an artefact can
be dressed as a finding in flat, unexcited prose too.

The specific candidate the team lead named, the caution box reporting Australia flattening hardest
against the supply-arrived mechanism's predicted ordering, is disclosed with real care in its own
source note: "Weight it lightly... the US answer is itself unstable across US benchmarks... It does not
refute the supply mechanism. It does mean the mechanism is not yet confirmed by anything on this desk."
The underlying prototype's own README goes further, stating its own honest summary as "no clean pattern,
and free data covers too few markets to resolve it further - one of the two outcomes flagged as likely
before running anything." That is a disclosure discipline running ahead of what the mode is checking
for, not an artefact dressed as a finding.

**Verdict: CLEAR.** No instance found of a negative or null result being reframed as a positive
discovery.

### Mode 6 - methodology fabrication

**Does anything in `_plan.md` or `_argument.md` imply the ΔΘ̂ test has been run for this paper?**
Grepped both files (and `_synthesis.md`, `_sources.md`, `_buildability.md`) for the loader's function
name, its result figures (`0.014055`, `0.2724`, `earns_its_seat`) and `floor_evaluation` - zero
matches. The only ΔΘ̂-shaped number `_plan.md` cites is the older 27-cell composite re-rank, which
`_synthesis.md`'s own prohibition 2 fences as "our own prior runs on a specific universe and window,
usable as demonstrations of a mechanism and not as evidence for this paper's general claims," and D4
uses it exactly that way. On the letter of the text under review, this is **CLEAR**: nothing implies
the test has been run.

**But the premise behind the hard constraint has changed, and the plan does not know it yet.** The
team lead's brief states the loader "has not and cannot be [run]: no loader exists, tracked as
`aegis-rd-n77e`." That is no longer true. `bd show aegis-rd-n77e` shows the issue is still nominally
OPEN, but its own notes read: *"2026-07-25 IMPLEMENTED AND RUN, not yet committed"* - and git shows it
in fact **was** committed, at `bf8ac1ee`, 2026-07-25T01:46:16+02:00, before `_plan.md` (untracked, drafted
the same day) existed. `aegis-rd/scripts/floor_evaluation.py` and its test file
(`aegis-rd/scripts/tests/test_floor_evaluation.py`) are real, committed, and the function has run on the
seat's own live candidate pair with a real (statistically null) result - see Mode 3.

This does not make anything in the current text a violation. It does mean:

1. `_plan.md`'s "Hard constraint" row and `_pipeline-state.md`'s Stage 0 framing ("The ΔΘ̂ loader...
   is not a prerequisite and the pipeline does not wait for it... it may never imply a result") are
   *stale as a description of the world*, even though they remain correct as *instructions to the
   drafting stage* (the loader existing does not mean the paper should lean on one underpowered result,
   and the note that ran it says so itself: "the dominant fact is that the data cannot support a
   verdict in either direction").
2. There is a live risk at drafting time, not integrity-review time: if the drafting stage is told "the
   test cannot be run" without correction, and later discovers the loader mid-draft, the paper risks
   either silently omitting directly relevant new evidence, or drifting toward implying the result *is*
   the paper's own test (it is a single underpowered run on locked configs, not a candidate-space
   sweep for this seat's own construction choices - a different thing D4's three-verdict table would
   need to handle carefully).

**Verdict: CLEAR on the letter, flagged for currency.** No implication of a run test in the text
reviewed. The "no loader exists" premise itself is outdated as of today and should be corrected in
`_pipeline-state.md` and acknowledged in `_plan.md` before drafting, with the discipline of not
overclaiming the new result preserved explicitly rather than by omission.

### Mode 7 - frame-lock

**The two recorded orchestrator errors** (`_pipeline-state.md`): both cast the seat paper as correcting
①, both retracted, with a standing constraint now in force to check whether an apparent conflict is
already handled elsewhere in ① before treating it as a gap. Read `_plan.md` end to end for residue of
this framing: none found. The thesis explicitly states "① never identifies the seat with carry as a
mechanism... our contribution is construction rather than correction" (synthesis §1, echoed in the
plan's thesis paragraph), D2 states "the derivation runs entirely through ①'s own text... so it does not
correct ①," and D6.4 states the honest position plainly - "the role is falsifiable within this roster,
not in general" - rather than either defending an unqualified claim or quietly dropping the roster
dependency. This reads as the corrected framing holding, not as residual scarring.

**Is D5's repair (D6.1-D6.3) genuine or defensive?** Checked the specific mechanism D6.1 leans on: that
the "sells convexity" clause it restores is "a clause dropped from ① rather than a requirement invented
here." Read ① §4.1 directly (`budgeting-convexity.md:330-331`): *"a convergent income engine that sells
convexity and earns the calm-market carry."* Confirmed - the clause is real, in ①'s own text, not
invented to rescue D5. That is evidence for genuine repair: the fix is traceable to a source outside the
argument being repaired, not to the argument's own need for a fix. D6.2 and D6.3 likewise change the
*finding* (majority-with-named-exceptions, two failure modes rather than one durability axis) rather
than re-asserting the original clean dichotomy the stress test attacked. D6.4 concedes the stress test's
strongest point (the mandated separation is a dependency, not a portable derivation) rather than arguing
around it.

**The one caveat.** D6.2, one of the two repairs, is also where the Mode 2 attribution-drift finding
lives (the fallen-angel buyer/seller inversion). It is worth naming plainly: this does not look like
frame-lock in the sense of defending an indefensible position - the repair direction (majority claim,
named exceptions) is the right shape and the *fix* the stress test itself recommended - but the specific
counterexample was assembled quickly enough, under the pressure of repairing the paper's most exposed
claim, that its own citation was not checked against the primary source before being written down. That
is a speed-versus-verification failure sitting inside a genuine repair, not evidence the repair itself
is a defensive holding action.

**Verdict: CLEAR on frame-lock itself**, with the D6.2 citation error noted as a separate, already-counted
Mode 2 finding rather than a second frame-lock finding.

## 2. Five-phase findings {#five-phase-findings-detail}

### Phase A - references

`_sources.md` grades roughly 185 sources. Rather than trust the register wholesale, this pass
independently re-verified a sample of six load-bearing citations against primary sources, chosen for
being either named directly by the team lead or central to a repaired decision (D6.1/D6.2):

| Citation | Independently re-checked this session | Result |
|---|---|---|
| Jurek (2014, *JFE* 113(3):325-347) | Fetched via register cross-reference to `carry-as-the-short-gamma-income-pole.md` and `the-skew-is-the-product.md`; figures (3.18%/yr t=3.13, 5.31%/yr t=3.69, crash share "at most ~1/3") match `_plan.md` D1 exactly | Real, correctly cited |
| Bollerslev and Todorov (2011, *Journal of Finance* 66(6):2165-2211) | Web-verified via Wiley, RePEc, Duke Scholars - author names, year, journal, volume/issue/pages all match | Real, correctly cited |
| Kargar (2021, *JFE* 141(2):505-532) | Already independently verified by `_sources.md` §2.7 with a verbatim quote (47%/72% leverage swing); this pass did not re-fetch but cross-checked the quote's use in `_synthesis.md` §3.1 and `_plan.md` D5 | Real, correctly used as plurality evidence |
| Tomunen (2026, *RFS* 39(3):661-701) | Already independently verified by `_buildability.md` against both the working-paper draft and the published DOI abstract; this pass cross-checked the "sixteen consecutive positive years" claim against the direct quote ("in all sixteen years the estimate is positive... nine of those sixteen years are after 2010") | Real, correctly used, with the pre-publication-figures flag already carried |
| Bassi, Behn, Grill and Waibel (2024, *JFI* 58, art. 101086) | Already substantially resolved by `_sources.md` §2.1 (ECB WP 2771 predecessor, SUERF brief, BIS Basel Committee WP corroboration); formal NEEDS-VENUE-CHECK status confirmed still open (final JFI PDF paywalled) | Real, exists, **still formally unclosed** - see §4 below |
| Dick-Nielsen and Rossi | Not previously resolved in `_sources.md` (recorded there as an incomplete citation, no journal/year/title). This pass identified and verified it: "The Cost of Immediacy for Corporate Bonds," *Review of Financial Studies* 32(1):1-41, 2019, DOI `10.1093/rfs/hhy080`. Peer-reviewed, real venue | Real and now identifiable, but **misapplied in D6.2** - see Phase B |

No source checked in this sample was found UNCONFIRMED-and-treated-as-settled, CONTESTED-and-treated-as-
settled, or RETRACTED-and-cited-as-live. The register's own "already-independently-verified" claims for
Kargar, Tomunen and Gospodinov-Robotti held up on cross-reading against the direct quotes it carries.

**On the specific question the team lead asked - does any load-bearing decision rest on a source flagged
UNCONFIRMED, NEEDS-VENUE-CHECK, CONTESTED or RETRACTED?** Yes, one: **D6.1's repair and §3's flagship
exception rest on Bassi, Behn, Grill and Waibel, still NEEDS-VENUE-CHECK.** This is the single most
consequential Phase A finding and is carried into §4 below as its own section, per the team lead's
explicit instruction to flag it plainly if found.

### Phase B - citation context

Five specific pairs were named for checking. Findings, in the team lead's order:

1. **Jurek for crash-neutral carry staying significantly profitable at 3.18-5.31%/yr.** Supports both
   the specific numbers (verified against the vault's own footnote text, which itself matches the
   published abstract's t-statistics) and the inference D1 draws. Jurek's finding is precisely that
   *hedging away* the crash exposure (out-of-the-money options) leaves the strategy still significantly
   profitable, i.e. shedding the crash-risk inventory costs at most about a third of the return. That is
   exactly "the seat that sheds the inventory keeps most of the money." **Verified, sound.**
2. **Bollerslev and Todorov (2011) via ① §2.2 for compensation being "in large part specifically for
   discrete, jump-driven losses."** Confirmed the phrase paraphrases the paper's own abstract
   accurately ("the compensation for rare events accounts for a large fraction of the average equity
   and variance risk premia"). The tension D1 builds - FX carry (Jurek) shows a minority crash share
   while index options (Bollerslev-Todorov) show compensation concentrated in jump risk - **is real and
   is not an artefact of the two papers measuring different objects; it is explicitly the venues that
   differ**, and D1 says so plainly ("Jurek is G10 FX carry... that is index options. Different venue,
   possibly different crash share"). The plan does not conflate the two measurements into one claim; it
   uses the disagreement to motivate a venue-indexed crash share, which is the correct use of a genuine
   cross-venue tension. **Verified, sound.**
3. **Kargar for at least two distinct constrained intermediary types, as positive evidence for D5's
   plural taxonomy.** The verbatim figures (broker-dealers -47% leverage, bank holding companies +72%,
   2008Q1-2009Q4, opposite directions) support "at least two distinct constrained intermediary types
   moving in opposite directions" exactly. Used correctly in `_synthesis.md` §3.1 as evidence *for*
   plurality (against the brief's original one-premium unification instinct), not as a repaired single
   factor. **Verified, sound.**
4. **Tomunen for sixteen consecutive positive years with decay on inflow, D6.5's primary exhibit.**
   Verified: the point estimate does not cross zero in any of the sixteen sample years (2003-2018),
   nine of them post-2010-break, and the paper's own model zeroes the premium only for a fully
   unconstrained specialist sector it does not show has arrived. The "decay on inflow, not extinction"
   reading is the paper's own reading, independently confirmed against the published *RFS* abstract via
   DOI (`_buildability.md` §1). **Verified, sound**, with the pre-publication-figures flag correctly
   carried in the plan (D6.5 does not cite the exact percentages, only "sixteen consecutive positive
   years").
5. **Dick-Nielsen and Rossi for dealer returns "not replicable by other investors in the economy,"
   D6.2's named exception.** The quote is verbatim and accurate - confirmed directly against the
   paper's own text (fetched via the SEC's hosted background PDF, which reproduces the published
   language): *"We note that these returns are not replicable by other investors in the economy, who
   would face a possibly large bid-ask spread to implement the strategy of buying at the exclusion date
   and selling afterward."* **But the mechanism direction around that quote is inverted.** The paper
   studies index *exclusions* from the Barclays Capital investment-grade corporate bond index: the
   index tracker is the forced **seller** (it must exit a bond leaving the index on a downgrade or
   maturity-shortening trigger), and the dealer is the **buyer** who absorbs the inventory and is
   compensated - via the very quote above - for warehousing it until it can be resold. `_plan.md` D6.2
   and `_argument.md`'s parallel passage both state the reverse: "the tracker is the forced *buyer*... and
   the compensated party is the dealer warehousing/supplying it." The vault's own
   `income-must-accrue-not-be-captured.md`, cited by `_plan.md` for this exact clause, states the
   correct direction ("index trackers are the forced sellers and dealers the compensated providers"),
   so the inversion was introduced during the stress test or the plan's own drafting rather than
   inherited from the source note. **Not verified as stated; the underlying economics (a rule-compelled,
   durable, dealer-compensated, negative-skew-carrying flow) still supports D6.2's conclusion once
   corrected, but the sentence as written misdescribes its own source.**

### Phase C - statistical data

Distinguished cited-from-literature numbers (Jurek's 3.18-5.31%, Tomunen's sixteen years, Kargar's
47%/72%, Bassi's 12.5%/25%) from in-house numbers, and traced the in-house ones specifically, per the
team lead's instruction that these carry the higher risk:

- **The 27-cell composite re-rank** (D4): traced to `runs/demeter/2026-07-04.md`, exact match. See
  Mode 3 above.
- **The variance-premium four-market prototype** (caution box, `the-payer-did-not-leave-the-supply-arrived.md`):
  traced to `_prototyping/global_variance_premium/README.md`'s "Real result" section, exact match,
  including the specific p-values. See Mode 3 above.
- **The newly landed ΔΘ̂ result** (not yet in the plan): traced to `bd show aegis-rd-n77e` and
  `the-premium-is-rent-on-a-balance-sheet.md`, consistent between the two, and consistent with the
  earlier archived `-0.0115` figure from `carry_floor.yaml`. Genuine, not fabricated. See Mode 6 for
  why its absence from the plan is itself a finding, not a defect in what exists.

No in-house number checked in this pass showed drift from its logged source. This is a meaningfully
different result from a prior audit in this same vault (`research/budgeting-convexity/_challenge-verification.md`)
which did catch invented figures elsewhere in the corpus - the discipline of writing run diaries before
citing them appears to be holding for this paper's specific in-house evidence.

### Phase D - originality

**Self-plagiarism / genuine synthesis.** Read `_synthesis.md` §2 in full against the seven folded
articles' stated contributions. The fold is not a restatement: `what-makes-a-convergent-sleeve-an-income-engine`
is explicitly split across two ends of the paper (role definition vs. evaluation contract) because the
plan judges the ranking rule unintelligible before the placement argument is established;
`carry-is-not-one-premium` is promoted in position but demoted in ambition (its own "several rows may
load on one constraint" footnote is held back from being re-promoted, per `_synthesis.md`'s explicit
instruction); `insurance-linked-securities-as-the-orthogonal-income-pole` is retitled and substantially
cut, with its orthogonality headline demoted to a conditional claim on the strength of independent
primary-source verification in `_buildability.md`; `short-horizon-reversal-in-small-cross-sections` is
repurposed from an implementation verdict ("overlay first, sleeve second") into the paper's falsifying
case, a genuinely different use of the same material. This is real synthesis work, not stapling.

**AI-text characteristics: em-dash convention.** Counted em-dash occurrences (Unicode U+2014) across all
seven income-engine documents: `_plan.md`, `_argument.md`, `_synthesis.md`, `_sources.md`,
`_buildability.md`, `_brief.md`, `_pipeline-state.md`. **Zero in every file.** The vault convention
holds.

### Phase E - claims

Checked D1 through D6 for whether the claim's stated confidence matches its evidence's strength.

- **D1 (venue-indexed crash share).** Proportionate. Both underlying sources verified (Phase B item 2);
  the claim is stated as a genuine tension between venues, not resolved into a single number, and the
  plan explicitly notes "the crash-share question is open three ways" elsewhere (via `_synthesis.md`
  §4.2's peso-problem discussion, which D3 inherits).
- **D2 (strike boundary derived from ①).** Proportionate on its own terms, and the plan states its own
  limitation clearly ("the paper becomes responsible for a boundary interacting with a tier it does not
  own"). The stress test's critique (the mandate is conditional on the Target existing and being sized
  to cover the fast segment) is real and is addressed head-on by D6.4 rather than smoothed over -
  appropriately hedged claim strength.
- **D3 (fair pricing is sufficient).** Proportionate. Explicitly framed as sufficiency rather than
  necessity, and the undecidability (Burnside, Eichenbaum, Kleshchelski and Rebelo vs. Jurek) is
  disclosed rather than resolved in the paper's favour. The stress test's sharper point - that a
  *positive* future ΔΘ̂ reading would be equally consistent with fair pricing and with an unfired
  peso-problem state - is not yet addressed in `_plan.md` itself (it lives in `_argument.md` only). This
  is a real gap between the two documents worth closing before drafting (see §4), though not severe
  enough on its own to change the verdict.
- **D4 (three-verdict failure clause).** Appropriately hedged for what it is - a discipline against
  post-hoc reassignment, not an empirical result - and the plan does not claim more for it than that. The
  stress test's own finding that "role dead" is "operationally a verdict nobody will ever actually
  render" is a real limitation the plan should state explicitly in paper §1, not a defect in the
  reasoning itself.
- **D5/D6.1-D6.3 (the durable-behaviours finding, repaired).** This is where claim strength most
  directly depends on evidence quality, and it is exactly where the two block-level findings sit (D6.1's
  unclosed citation, D6.2's inverted mechanism). Once both are fixed, the repaired claim
  ("majority-with-named-exceptions") is appropriately hedged - weaker and more defensible than the
  original clean dichotomy, which is the correct direction for a repair to move in.
- **D6.4 (dependency on the Target tier, stated not repaired).** Proportionate and honest - the plan
  states the dependency as a dependency ("the role is falsifiable within this roster, not in general")
  rather than dressing it as a portable derivation.

## 3. Load-bearing claims resting on unclosed citations

This is the single most decision-relevant section, per the team lead's instruction, so it is stated
plainly rather than folded into the phase writeups above.

### Bassi, Behn, Grill and Waibel (2024) - NEEDS-VENUE-CHECK, load-bearing

**Yes, a load-bearing decision rests on this unclosed citation.** D6.1's repair - restoring the "sells
convexity" clause and using `window-dressing-at-the-regulatory-snapshot.md` as the counterexample that
satisfies D4's three stated clauses "vacuously" without it - depends on that note's mechanism being
real and well-evidenced. That note's primary source is Bassi, Behn, Grill and Waibel. The consequence
chain is direct: D6.1 repairs D5 -> D5's repair is what saves D3's "fair pricing is the designed
equilibrium" claim from its most dangerous counterexample (per `_argument.md` §2 item 1, "D5 is doing
the work of protecting D3") -> `_argument.md` §3's per-section stress test already names this exact
consequence ("if §3 leans on window dressing as its flagship durable-but-excluded example... that
citation gap becomes load-bearing rather than a footnote-level flag").

**What is and is not at risk.** The *qualitative* mechanism - dealers shrink repo books and inventory
before regulatory reporting dates because the rule constrains exactly the party best placed to arbitrage
the squeeze - is corroborated three ways independent of the paywalled final text: the 2023 ECB working
paper predecessor (same four authors, same figures, states the sample period twice), a companion SUERF
Policy Brief, and a 2026 BIS Basel Committee working paper that cites "Bassi et al (2023)" for the
identical 12.5%/25% figures. The published *JFI* 58 (2024), article 101086, is confirmed to exist with a
matching abstract via IDEAS/RePEc. So the mechanism's *existence* is high-confidence. What remains open
is formal: nobody has read the sample-period sentence in the final peer-reviewed PDF itself. `_sources.md`
already carries this as NEEDS-VENUE-CHECK (§2.1) and states plainly that the 12.5%/25% figures "may not
be cited in a paper until it is closed" (prohibition 35). `_argument.md` repeats the flag. **`_plan.md`'s
D6.1 does not** - it uses the note's mechanism claim without restating the citation's status at the
point of use, which is the gap between "the corpus knows this is open" and "the specific decision that
depends on it says so."

**This is not, on its own, disqualifying for the mechanism claim** (window dressing exists and is
rule-compelled almost by definition of the regulatory snapshot mechanic, independent of the exact
contraction percentages). It is disqualifying for treating D6.1 as fully closed while this stands open,
because D6.1 is not a peripheral decision - it is the fix for the paper's single most exposed claim.

### Dick-Nielsen and Rossi - resolved as a citation, misapplied as a mechanism

Not an unclosed citation (see Phase A/B above - fully identified, peer-reviewed, real). Listed here
because the practical consequence is the same as an unclosed citation: as currently written, D6.2 cannot
be relied on to say what its source says, and it sits in the same repair chain as the Bassi item above.
Once the buyer/seller direction is corrected, this citation is fully closed and the underlying economics
(rule-compelled forced selling, dealer-compensated warehousing, "not replicable by other investors")
support D6.2's conclusion at least as well as the version currently written - arguably better, since the
corrected direction is also what the register's own §3.9 (`Ben Dor and Xu 2011, "Fallen Angels"`,
post-downgrade underperformance then a two-year reversal) independently implies.

### Items flagged elsewhere and not reopened here

- **Aggregator-sourced fund figures in `_buildability.md`.** Already flagged in that note's own
  dedicated Limitations block (Twelve Cat Bond Fund and Schroder GAIA share-class figures via
  Investing.com; CATB's AUM via TradingView/Morningstar/justETF). None of these are load-bearing to the
  paper's argument - the paper stays theoretical and does not cite specific share classes - and the
  buildability note's own verdict paragraph already carries the flag forward correctly ("buildable
  today... its share-class numbers are aggregator-sourced"). No action needed beyond what
  `_buildability.md` already does.
- **Everything else in `_sources.md`'s blocking-items list** (§2.2-§2.9: the retracted Bai-Bali-Wen,
  the unpublished Dickerson-Robotti-Rossetti, Terstegge, Dew-Becker-Giglio's contested break date, the
  Mallory crypto wedge, Qiao-Xu-Zhang-Zhou) is already correctly fenced with prohibitions in
  `_synthesis.md` §5, and this pass found no load-bearing decision in `_plan.md` leaning on any of them
  past what the prohibitions permit.

## 4. What must be fixed before drafting

Ordered by severity. The first two are the block reasons; the rest are lower-severity items surfaced
along the way that should not themselves gate re-verification but should not be forgotten either.

1. **[BLOCKING] Correct D6.2's fallen-angel mechanism direction.** In `_plan.md` and the corresponding
   passage in `_argument.md` §1/§2, change "the tracker is the forced buyer... and the compensated party
   is the dealer warehousing/supplying it" to the direction Dick-Nielsen and Rossi (2019, *RFS*) and the
   vault's own `income-must-accrue-not-be-captured.md` actually document: the tracker is the forced
   **seller** at index exclusion, and the dealer is the **buyer** who warehouses the bond and earns the
   compensated, non-replicable return. The rest of D6.2's argument (rule-compelled, durable, negative-skew,
   passes all four clauses) survives the correction intact.
2. **[BLOCKING] Carry Bassi et al.'s NEEDS-VENUE-CHECK flag into D6.1's own text, or close the citation
   first.** Either (a) read the final *JFI* 58 (2024) article 101086 PDF directly and confirm the sample
   period and figures against it, closing the flag properly, or (b) if that is not feasible before
   drafting, add an explicit sentence to D6.1 stating that its flagship counterexample's primary source
   remains formally unclosed and that the paper should lean on the qualitative mechanism (independently
   corroborated three ways) rather than the specific percentages until it is closed. `_sources.md`
   prohibition 35 already states the rule for citing the exact figures; D6.1 needs the same discipline
   applied to the decision that depends on the note the figures live in.
3. **[HIGH] Update `_pipeline-state.md`'s Stage 0 framing and `_plan.md`'s Hard Constraint row to reflect
   that the ΔΘ̂ loader (`aegis-rd-n77e`) now exists, is committed, and has produced a real (statistically
   null) result on the seat's own candidate pair.** The "never imply as run" discipline should be
   *restated*, not dropped - the note that ran the test says its own result "cannot support a verdict in
   either direction" - but the premise that the loader does not exist is now false and should not be
   carried into drafting unexamined. The drafting stage needs to decide, deliberately, whether paper §10's
   seeded hypothesis about ΔΘ̂ should acknowledge that a preliminary, informal, underpowered measurement
   already exists, and if so, how to do that without drifting toward implying it settles anything.
4. **[MEDIUM] Update `_argument.md` §8's claim that ΔΘ̂'s scale convention "was found to be misdescribed
   and sign-flipping under a vol-matched convention."** That describes `aegis-rd-600y`, which is closed
   WONTFIX: the floating-volatility convention (the one that produced both the 27-cell result and the
   new loader result) was investigated and confirmed correct against the governing article and a
   controlled measurement, not found to be a bug. Replace the sentence with the finding that actually
   survived from that investigation - the Tasche category error, tracked separately as `aegis-rd-v1k7`
   and already fixed at the source article - so drafting does not inherit a caution against a convention
   that has since been vindicated. `notes/the-premium-is-rent-on-a-balance-sheet.md`'s own "Correction,
   same day" callout should be updated or annotated the same way, since it is the source of the stale
   framing.
5. **[MEDIUM] Close the gap between `_plan.md` D3 and `_argument.md`'s sharper peso-problem point.**
   `_argument.md` §2 item 3 identifies that a *positive* future ΔΘ̂ reading is equally consistent with fair
   pricing and with an unfired peso-problem trade, which is a sharper and more specific limitation than
   D3's "indifference" framing currently states. This should be folded into D3 (or into paper §8's
   pre-registration language) before drafting, per `_argument.md`'s own recommendation.
6. **[LOW] Cite the role article directly for the Tasche correction, not only the caution note.** Now
   that `aegis-rd-v1k7` is fixed at the source (`research-legacy/what-makes-a-convergent-sleeve-an-income-engine.md`,
   commit `110507ad`), drafting can lean on the corrected article's own bullet and footnote rather than
   relying solely on `_argument.md`'s paraphrase.
7. **[LOW, informational] The 27-cell result's own follow-up.** Not a required fix - the plan's use of
   the 27-cell result is already correctly scoped as illustrative rather than evidentiary - but drafting
   should be aware that the same-day follow-up work (`runs/demeter/2026-07-04.md`, sections "P0"-"P2")
   found the co-crash largely resolved into a single-fast-crash, daily-frequency artefact once measured
   monthly and ex-COVID. This does not change what D4 uses the 27-cell result to illustrate.

## 5. Limitations of this verification

**Sampling, not exhaustive re-verification.** `_sources.md` grades roughly 185 sources and states
plainly that it independently re-verified a subset itself, carrying the rest forward on the folded
articles' own word. This pass re-checked six of those (the five the team lead named, plus
Gospodinov-Robotti's figure spot-checked via cross-reference rather than re-fetched) against primary
sources, and read `_sources.md`'s own verification notes for a further dozen or so cited in the phase
findings above. That leaves the large majority of the register's ~185 sources - and essentially all of
the ~165 the register itself marks CITED-CONSISTENT without independent primary-source checking this
session or last - unverified by this pass specifically. A different sample could surface different
attribution-drift instances; the one found here (D6.2) was found by checking the five citations
specifically named for checking, not by an exhaustive sweep.

**Bassi, Behn, Grill and Waibel's final published text remains genuinely unclosed by this pass.** As
instructed, this is reported as-is rather than reconstructed or guessed. ScienceDirect returned a
paywall to every access attempt recorded in the vault's own prior sessions; this pass did not attempt a
fresh access route and relied on the same triangulation (working-paper predecessor, SUERF brief, BIS
working paper, DOI/abstract match) already documented in `_sources.md` and `_buildability.md`. The
sample-period sentence itself has still never been read in the peer-reviewed PDF by anyone on this desk.

**The variance-premium and 27-cell prototypes were verified by reading their logged output, not by
re-executing the code.** `_prototyping/global_variance_premium/` and the `runs/demeter/2026-07-04.md`
diary were read and their reported figures cross-checked against the vault text that cites them; this
pass did not re-run `cross_market.py` or `cascade_rerun.py` to independently reproduce the numbers from
raw data. A logged result that matches its own citation is strong evidence against fabrication but is
not the same guarantee as an independent re-run.

**Depth on ① (`budgeting-convexity.md`) was targeted, not exhaustive.** This pass read §2.2, §2.3, §2.4,
§4.1, §4.2 and §4.3 directly - the sections `_plan.md` explicitly leans on for D1, D6.1 and D6.4 - and
confirmed each cited claim against the primary text. The remaining ~700 lines of ① (§1, §3, §5, §6, the
full reference list) were not re-read line by line in this pass; the plan's own discipline of treating ①
as cite-only and not re-deriving it means most of the paper's dependency surface on ① is concentrated in
the sections checked, but a claim resting on an unchecked section cannot be ruled out.

**Phase E was a proportionality check on D1-D6 as stated, not a line-by-line audit of every sentence in
`_plan.md`.** The six decisions were each checked for whether their stated confidence matches the
evidence behind them; individual clauses within each decision that were not flagged by the stress test
or by this pass's own reading were not independently re-derived from first principles.

**No attempt was made to verify the ~15 non-academic instrument/product-documentation sources in
`_sources.md` §3.9**, since `_pipeline-state.md` and the register itself agree these are unlikely to
enter a theoretical paper's bibliography and are explicitly out of scope for the academic citation
audit.

**This verification is itself a single pass by a single reviewer.** The standing constraint recorded in
`_pipeline-state.md` - "parallel searches of one corpus are one sample" - applies to integrity
verification as much as to research. A second independent pass, particularly one that re-samples a
different set of citations than the five named here, would be the natural next check if the two
blocking items are fixed and the pipeline re-submits for verification.

**Correction to this document's own earlier framing, recorded rather than silently fixed.** An earlier
pass of this report described Modes 1, 5 and 6 as pre-filtered out for a theoretical paper on the
reference's own authority, attributed to its Open Questions section. Corrected on the team lead's
review: Open Questions names only Modes 1, 5 and 6 for the log-dependence rationale; Mode 3 is
log-dependent by its own detection text but is not named there, so the reference under-counts its own
false-positive exposure on Mode 3 specifically - worth carrying forward as a gap in the checklist
itself, not just in this paper's use of it. The correct framing is also not a pre-filter at all: the
spec's own `CLEAR` verdict is defined as "evidence the mode does not apply," and an enumeration showing
no claim invokes the mode is exactly that evidence, established by reading the artifact rather than by
exempting it. This revision reworked Modes 1, 3, 5 and 6 above to enumerate claims explicitly rather
than clear by paper type, per that correction, and the enumeration surfaced one finding (the stale
`aegis-rd-600y` warning propagating into `_argument.md` §8) that a paper-level clearing would have
missed.

**The claim-level trace for Mode 1 went two commits deeper than the vault note it started from, and
that depth was not exhaustive either.** Tracing claim 2 required reading past
`notes/the-premium-is-rent-on-a-balance-sheet.md`'s own text to `git log` on `convergent.py` and to two
bd issues (`aegis-rd-600y`, `aegis-rd-v1k7`). Both resolved cleanly and in the same direction, which is
reassuring, but this pass did not separately audit the measurement `aegis-rd-600y`'s close reason cites
(the 12/12-versus-9/12 matched-marginal fixture result) by re-running it - it was accepted on the
strength of a closed issue with a stated methodology and a verified primary-source check (Tasche, arXiv
0708.2542, for the related `aegis-rd-v1k7`), not independently reproduced.
