---
title: "Budgeting Convexity - paper creation process record"
paper: "Budgeting Convexity"
status: "Stage 6 process summary - pipeline complete"
tags:
  - process-record
  - stage6
---

# Paper Creation Process Record

**Paper.** *Budgeting Convexity: Diversification as an Order of Operations over Failure Modes*
**Author.** madebymlai (Aegis)
**Pipeline.** `academic-pipeline` v3.19.0, full 10-stage orchestration
**Run date.** 2026-07-23 to 2026-07-24
**Type.** Theoretical / integrative framework paper. No original experiments, datasets, or numerical
results of its own; per-role empirical proof is deferred by design to three named follow-on studies.
**Deliverable.** `papers/budgeting-convexity.pdf` (29 pages, APA manuscript format, XeLaTeX)

---

## 1. What the paper argues

Diversification is an order of operations over failure modes on the convexity axis: budget risk across
the roster, source convexity structurally, and treat skew as a classifier to observe rather than a
budget to solve. The claim the argument rests on is a market claim, that realized skew is
tail-dominated, horizon-unstable and asset-class-specific, so it can label a pole but cannot anchor a
stable allocation target.

The paper is explicitly integrative. It asserts roles at the roster level and hands per-role proof to
three seat papers: crisis-responder, convergent-engine, and v-crash-defense.

---

## 2. Stage-by-stage history

| Stage | Activity | Outcome |
|---|---|---|
| 0 | Configuration record | Theoretical paper, JPM register anchor (not a submission commitment), APA 7th, 7,500-word target, citation verification level **strict** |
| 1 | Go / no-go on the two central claims | **GO**, both claims sharpened rather than confirmed; two guardrails imposed that survived into the final text |
| 2 (P2) | Outline + evidence map | 6 chapters, 18 subsections, ~40 sources tagged pro / con / context with conflict-of-interest marks |
| 2 (P3) | Argument blueprint | Central thesis plus four sub-arguments, each with a named rebuttal strategy |
| 2 (P4) | Draft, v3.6.6 generator-evaluator contract | Round 1 self-scored **F3 (revise)** at roughly 20% under target; round 2 **F0 (accept)** |
| 2 (P5) | Citation audit + abstract | ~15 sources web-verified, several bibliographic corrections, 4 claim-faithfulness fixes |
| 2.5 | Integrity gate | **PASS WITH NOTES** |
| 3 | Peer review, 5 independent panels | **Major Revision** (EIC Minor, R1 Major, R2 Major, R3 Minor, plus Devil's Advocate) |
| 4 | Revision | 3 Required + 4 Suggested + 3 nits addressed against a frozen FIX / WONTFIX docket |
| 3' | Targeted re-review | **Accept**; one new minor issue found and closed |
| 4.5 | Final integrity gate | **FAIL** on two claim distortions, corrected, then **PASS WITH NOTES** across three rounds |
| post-gate | External challenge to Sections 2.2 / 2.4 | Sources verified independently; challenge partly upheld, partly rejected; three sections revised |
| 5 | Finalize | Markdown, LaTeX, PDF |
| 6 | This record | Pipeline complete |

---

## 3. Division of labour

**The author decided.** Every consequential choice in this run was human. The AI proposed and executed;
it did not choose.

- Scope and sequencing of the pipeline, and the 7,500-word target
- The evidence standard: every claim leads with an ex-ante economic rationale, because "a backtest
  estimates an effect we already expect; it never discovers one"
- The estimate-tier rule: the aegis allocator, ADRs and run diaries are labelled in-sample
  illustration, never proof
- The risk-versus-return line: conditioning on volatility, covariance or regime is allowed;
  forecasting returns or crashes is not
- That Section 5.2 must not describe the book as unlevered
- House style: no em dashes, plus one further stock phrase prohibited mid-run and removed from the
  draft, the generated sources and the compiled PDF
- That the paper carries no AI disclosure statement
- The byline, the file layout, and the decision to keep APA double spacing rather than deviate for
  readability
- The instruction that made the difference to quality: apply the skills correctly rather than
  approximately

**The AI performed.** Literature search and source verification, drafting against the writer contract,
self-scoring, the five reviewer personas, integrity verification, revision execution, and formatting.
All subordinate to the decisions above.

**Subagents dispatched.** Stage 3 review, Stage 3' re-review, Stage 4.5 integrity (three rounds), the
external-challenge verification, and Stage 5 formatting. Each ran with fresh context so that
verification was independent of the work being verified.

---

## 4. What the quality gates actually caught

The gates were not ceremonial. They found real defects that would otherwise have shipped.

**Fabrication and misattribution.**
- A partially hallucinated author list on Bouchaud et al. (2017), corrected to Dao et al.
- A citation to "AQR (2020b)" that was actually a 2015 paper by Asvanunt, Nielsen and Villalon
- A One River byline naming an author who does not appear in the document
- Meucci (2009), cited twice in Section 4.3 with **no reference-list entry at all**, missed entirely by
  the first integrity pass and caught by the second

**Claim distortions, where a real source was attached to a claim it does not make.** Seven in total.
Four at Stage 2.5, including Martellini and Ziemann (2010) asserted backwards (the draft said such
portfolios struggle to beat minimum-variance; the paper finds they dominate it with improved
estimators). Three more at Stage 4.5, most seriously:

- Section 2.2 credited Bollerslev, Tauchen and Zhou (2009) with a discrete-loss compensation mechanism.
  Their model has no jump process; that finding belongs to Bollerslev and Todorov (2011).
- Section 5.5 grouped Uysal and Mulvey (2021) under evidence that is "not a forecast of return or of a
  crash", when their overlay is driven by a supervised recession-probability estimate. The paper
  contradicted itself on its own central distinction.

**A silent typographic corruption.** pdfLaTeX compiled with exit code 0 and no warnings while mangling
the Romanian comma-below-s in "Roșu" into a broken composite. Caught only by extracting the PDF text
layer rather than trusting the compile log. Resolved by switching to XeLaTeX.

**Reference ordering.** Five alphabetization errors, two of them long-standing and never previously
flagged.

---

## 5. Decisions worth recording

**Concede rather than delete.** When Stage 4.5 found that Uysal and Mulvey contradicted the sentence
citing it, the proposed fix was to drop the citation. That was rejected: removing the one study that
embarrasses a claim is the cherry-picking the adversarial reviewer exists to catch. The paragraph
instead sorts the three cited studies explicitly and concedes that one falls on the far side of the
paper's own line. The distinction now cuts the paper's own evidence, which is a stronger position than
asserting it.

**Verify a challenge before acting on it.** An external research sweep argued that Section 2.2's
foundation was wrong. Rather than revising on its say-so, its sources were independently verified. The
result split: the central paper was real and said what was claimed, but the inference drawn from it
overreached, because the synthetic options at issue are delta-hedged and cannot span jumps by
construction, a limitation the authors themselves state. The paper therefore concedes the documented
compression without conceding the stronger claim.

**Change the form of a claim, not its content.** The same episode exposed a genuine gap: Section 2.2
treated inelastic demand as sufficient for a premium to persist, when it is only necessary. The fix
turned a categorical claim into a conditional, monitorable one. A paper asserting that a premium
persists is falsified the moment one compresses; a paper naming the condition and what to watch
survives that. This was the single most valuable change of the run.

**Do not add sources late.** Two opportunities to add a reference near the finalize boundary were
declined in favour of rewording, so that nothing entered the paper without passing the same
verification everything else had.

**Scope discipline on review findings.** Findings were frozen into a closed docket and classified FIX
or WONTFIX before any edit. Four items were deliberately not actioned, each with a recorded reason.

---

## 6. Where things went wrong

Two process failures, recorded because the record is worth less without them.

**The skills were initially applied loosely.** The first draft was written without reading the writer
contract. The author caught this and required the correct methodology. Re-running it properly
immediately surfaced that the draft was 20% under target, which the informal approach had missed.

**A concurrent-writer collision.** The formatting agent was believed closed and its work was taken over
directly in the main session. It was in fact still live. Both parties then wrote to the same three
paths, and the agent reasonably concluded an unidentified process was clobbering the deliverable on a
loop. It stopped and escalated rather than racing, which was the correct call and prevented a corrupted
output. Fault was the main session's for not verifying closure. Its build was ultimately discarded
because it predated four author decisions, and a read-only diff confirmed the shipped Markdown differed
from it only in whitespace and byline.

---

## 7. Final artifacts

| Artifact | Location |
|---|---|
| Final PDF | `papers/budgeting-convexity.pdf` |
| Markdown and LaTeX sources | `research/budgeting-convexity/budgeting-convexity.{md,tex}` |
| Working draft | `_draft.md` |
| Plan, outline, argument blueprint | `_plan.md`, `_outline.md`, `_argument.md` |
| Integrity reports | `_integrity.md` (Stage 2.5), `_integrity_final.md` (Stage 4.5, three rounds) |
| Review and re-review | `_review.md`, `_rereview.md` |
| Revision log and decisions of record | `_revision.md` |
| External challenge verification | `_challenge-verification.md` |

**Verified on the shipped PDF.** 29 pages; em dashes 0; author placeholders 0; COI disclosures 15 of
15 preserved; no page under 30 words; all accented names render as correct single glyphs.

---

## 8. Carried forward

- **Three seat papers** inherit fixed job descriptions and a payer to verify. The convergent-engine
  brief additionally inherits the intermediary-capacity framing from Section 2.4, an unverified
  "shadow gamma" lead marked do-not-cite-until-sourced, and a caution that an admission gate built on
  dealer positioning sits close to the return-forecasting line this paper draws.
- **Template carry-forward.** The byline and two orphan-control fixes live only in the generated
  LaTeX, so regenerating from source loses them. The byline belongs in the Phase 0 configuration
  before the seat papers run through the same template.
- **Open cosmetic items.** A small number of DOI backfills for canonical classics; one paywalled
  source recorded as access-limited rather than verified.
