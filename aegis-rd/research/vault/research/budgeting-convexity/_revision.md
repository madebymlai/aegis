---
title: "Budgeting Convexity - Stage 4 revision log"
paper: "Budgeting Convexity"
status: "Stage 4 revision round 1 complete"
tags:
  - revision
  - stage4
---

# Stage 4 revision log (round 1)

Response to the Stage 3 editorial verdict (**Major Revision**) in
[[research/budgeting-convexity/_review|_review]]. Per the project workflow rule, the review findings
were frozen into a closed FIX / WONTFIX docket and classified against the paper's governing standards
(the vault research/README ex-ante-rationale and risk-vs-return discipline, the paper's own COI-flag
and triangulate practice, and the argument blueprint `_argument.md`). Only FIX items were addressed.

## FIX items addressed

| Roadmap ID | Severity | Location | Action taken | Status |
|---|---|---|---|---|
| R1 | Major (P1) | 4.4 | Restored the planned non-uniqueness concession from `_argument.md` SA3: the order is non-arbitrary but not unique/optimal; a different author could narrate another ordering; and the ordered-vs-unordered-ERC comparison plus per-role proof are deferred to the seat papers (folds in R1 W4 / DA alternative-path). | Resolved |
| R2 | Major (P1) | 5.4 | Rebalanced the monetization evidence: named the one peer-reviewed anchor (Bhansali et al. 2020, JPM) and COI-flagged it (LongTail Alpha); COI-flagged One River and Man Group in-text as product-sellers cited as illustration; scoped the firm claim to the narrower peer-reviewed Israelov result and framed monetization as a design lean, not a settled finding. | Resolved |
| R3 | Major (P1) | 5.5 | Added direct engagement with the leverage-effect / asymmetric-volatility entanglement: conceded that de-risking on rising vol resembles lagging return-timing, then distinguished the two by what each must get right (risk-conditioning is indifferent to the sign of the next return; timing must forecast it, which is what arbitrage prices away). | Resolved |
| S1 | Minor (P2) | 4.3 + refs | COI-flagged Choueifaty & Coignard (2008) in-text (first author's firm TOBAM markets a fund on the metric) and in the reference list. | Resolved |
| S2 | Minor (P2) | 6 | Added one paragraph on implementation/governance friction (mandate rigidity vs a convexity-role taxonomy; tail-sleeve cost; discipline to hold through calm, extended from Shleifer-Vishny) plus a one-line reflexivity answer (publication does not shrink structural payers because they are not informational). | Resolved |
| S3 | Minor (P2) | 3.5 | Added one sentence formalizing the ordinal/repeatedly-resampled (ranking) vs cardinal/point-estimate (budgeting) distinction. | Resolved |
| S4 | Minor (P2) | 2.3 | Scope-noted that the risk-premium reading of trend is a deliberate choice, acknowledging the under-reaction / information-diffusion alternative in Moskowitz-Ooi-Pedersen (2012) itself. | Resolved |
| nit-1 | P3 | 5.1, 5.3 | Fixed in-text citation-by-title: "(Empirical Economics, 2026)" -> "(Trucíos, 2026)"; "(When simplicity beats optimization, 2026)" -> "(Feng, 2026)". | Resolved |
| nit-2 | P3 | 4.2 | Reconciled "Al Fallouji" (in-text) to "Al-Fallouji" (matches reference list). | Resolved |

## WONTFIX items (documented, with rationale)

| Item | Source | Rationale |
|---|---|---|
| Backtest an unordered ERC blend of the same sleeves; test a rolling, shrinkage-regularized book-level skew tilt | DA "Ignored Alternative Paths"; R1 W4 | Require new empirical work the paper explicitly defers to the seat papers. Not listed as a Required or Suggested revision. Addressed textually inside R1 by naming the ordered-vs-unordered comparison as a seat-paper task rather than running it here. |
| "Is the roster doing real work beyond a factor-level risk-budgeted portfolio?" | DA "Unexamined Premise" | Same reason: an empirical question for the seats. Flagged as an observation, not a required revision. The Ch6 limits already scope per-role proof to the follow-on studies. |
| Split 60-90-word sentences in Sections 3 and 5 | EIC / R1 Minor Issues (P3) | Writing Quality scored Strong (78-80) by three reviewers, "dense but professional," specialist audience. Rewriting many lines for a cosmetic gain risks introducing error and expands the change surface with no substantive benefit. Deliberately not actioned. |
| Reference-list re-alphabetization (Dao, Feng, Trucíos) | P3 checklist | Already tracked in `_integrity.md` as deferred to Phase 7 formatting; unchanged. |

## Regression / word-count check

- Body total: **7,564 words** vs 7,500 target (+0.9%, within +/-10%).
- Per-section: Ch1-Ch5 all within +/-15%. **Ch6 is +25.6%** (879 vs 700), driven by the
  reviewer-mandated governance paragraph (S2) landing in the conclusion; accepted as a deliberate
  consequence of the revision rather than trimmed, since the overall total is on target and the content
  is reviewer-requested.
- Em dashes: 0. House style intact.
- No new claim-fidelity distortions introduced; the four fixed at Stage 2.5 remain fixed.
- Scope discipline: no content added beyond the FIX docket; every edit traces to a roadmap ID.

## Stage 3' re-review outcome (round 1) and closeout fix

Stage 3' re-review ([[research/budgeting-convexity/_rereview|_rereview]]) returned **Accept**: all
three Required Revisions FULLY_ADDRESSED against independent verification, all four Suggested
Revisions fully implemented, all Priority 3 nits fixed or transparently deferred, WONTFIX deferrals
judged legitimate scoping for an integrative paper. One new minor issue was found:

| Roadmap ID | Severity | Location | Action taken | Status |
|---|---|---|---|---|
| NEW-1 | Minor (internal-consistency) | 5.4 closing sentence | Side-effect of the R2 hedge: the paragraph closed by re-asserting monetization ("earned back through monetization") two sentences after downgrading it to "a design lean rather than a settled finding." Carried the hedge through to the final sentence ("designed to be earned back... though the size of that monetization edge is the design lean advanced here rather than a settled result"). Classified FIX (on this round's changed lines, reviewer-flagged, low-risk); applied at re-review closeout rather than deferred. | Resolved |

Post-fix checks: em dashes still 0; no new claim added, only the existing hedge propagated; §5.4 no
longer re-asserts a claim it just downgraded.

## Stage 4.5 final-integrity corrections (round 2 body fixes)

The Stage 4.5 gate ([[research/budgeting-convexity/_integrity_final|_integrity_final]]) returned
**FAIL** on two MAJOR_DISTORTION claim-fidelity findings that Stage 2.5 missed. The gate corrected all
bibliographic defects itself; body prose is the author's to fix, and all four claim findings were
classified FIX and applied:

| ID | Severity | Location | Action taken | Status |
|---|---|---|---|---|
| MD-1 | MAJOR_DISTORTION | 2.2 | The draft attributed "compensation for bearing the risk of discrete losses" to Bollerslev, Tauchen & Zhou (2009), whose model is a long-run-risk / volatility-of-volatility equilibrium with no jump process. Re-attributed BTZ to what it shows (return predictability traced to time-varying uncertainty about future volatility) and assigned the jump-loss mechanism to Bollerslev & Todorov (2011), already established in 2.1. | Resolved |
| MD-2 | MAJOR_DISTORTION | 5.5 | The draft grouped Uysal & Mulvey (2021) with Costa-Kwon and Fleming-Kirby-Ostdiek under "not a forecast of return or of a crash." Uysal & Mulvey in fact drive their overlay from a supervised estimate of recession / market-contraction probability, contradicting the sentence on its own terms. **Rejected the option of dropping the citation** (that would delete the disconfirming case and is precisely the cherry-picking the Devil's Advocate screens for). Instead sorted the three studies explicitly: the two that condition purely on risk are named as such, and Uysal & Mulvey is conceded to fall on the far side of the paper's own line, counted as evidence that regime-conditional allocation beats static allocation but not as support for the risk-conditioning distinction, with its forecasting layer explicitly not adopted. The distinction now cuts the paper's own evidence, which is stronger than asserting it. | Resolved |
| MD-3 | MINOR_DISTORTION | 3.2 | Harvey & Siddique (2023) magnitude bookends ("one and a half to nearly five percent") matched neither the source's headline range (2.1-3.9%) nor its robustness span. Restated as "roughly two to four percent in their headline estimates and considerably wider across their robustness specifications." | Resolved |
| MD-4 | MINOR_DISTORTION | 4.3 | The squared-diversification-ratio-as-independent-factors formalization is attributed in the secondary literature to the 2012/2013 follow-up rather than unambiguously to Choueifaty & Coignard (2008). Softened to "commonly read as," which keeps the certain attribution (the ratio itself is theirs) without asserting the 2008 paper states the squared reading. No new unverified reference introduced this late. | Resolved |

Reference-list defects (dangling Meucci 2009 citation, Lempérière author initial, dead Lassance-Vrins
DOI, Brown et al. year/volume, Baltas-Salinas pages, the mis-dated "AQR 2020b", One River byline,
dropped Cederburg 4th author) were found and corrected by the gate itself and re-verified in-pass.
IL-MINOR-1 and IL-MINOR-3 are now **closed**; IL-MINOR-2 (alphabetization + DOI backfill) remains
tracked for Phase 7 formatting.

Post-fix checks: em dashes 0; body 7,892 words (+5.2% vs 7,500 target, within +/-10%); semicolons
within budget.

## Post-gate round 3: the VRP / intermediary-capacity challenge (2.2, 2.4, 6)

Stage 4.5 passed (PASS WITH NOTES), but Stage 5 was held because an external research sweep attacked
the paper's foundation. The sweep's sources were verified independently before any edit
([[research/budgeting-convexity/_challenge-verification|_challenge-verification]]). Outcome: the
linchpin is real (Dew-Becker & Giglio, Chicago Fed WP 2025-17, verbatim: "Synthetic options never, over
the last 100 years, had negative alpha"), but the inference drawn from it overreaches on three counts.

| ID | Location | Finding | Action taken |
|---|---|---|---|
| CH-1 | 2.2 | **Logic gap, valid on first principles alone.** The section treated inelastic demand as sufficient for premium persistence. It is necessary, not sufficient: a price-insensitive buyer facing abundant sellers pays little. The section never argued seller capacity is constrained. | Added the sufficiency qualification and gave the short pole its actual mechanism via Gârleanu, Pedersen & Poteshman (2009): option prices move with end-user net demand because market makers cannot hedge perfectly, which is why index options carry the premium and single-stock options do not. The pole is now "paid for bearing unhedgeable risk where the intermediary's capacity binds." |
| CH-2 | 2.4 | **Taxonomy incomplete.** Informational (decays on publication) vs structural (persists) has no slot for a premium immune to publication but sensitive to capital. | Added the third decay mode with its ex-ante rationale, evidenced in two unrelated markets: Dew-Becker & Giglio (2025) on the S&P 500 VRP earning ~zero since around 2010, and Tomunen (2026) on cat-bond premia proportional to the intermediary's capital constraint, decaying post-crisis and barely reacting to the record 2017 losses. |
| CH-3 | 2.4 | **The sweep's strong claim does not survive.** It read "no negative alpha on synthetic options" as evidence against a jump/crash premium. | **Rejected.** The synthetic options are daily delta-hedged and cannot span a jump by construction, and the authors themselves say a jump-tied premium would appear in the wedge between traded and synthetic returns, not in the synthetic leg's alpha. Also the break date is unsettled (2012 in their own statistics, 2017 in Bates, 2022). Both cautions are stated in-text so the paper concedes the compression without conceding the stronger claim. |
| CH-4 | 6 | **Reflexivity answer aimed at the wrong side.** It defended the demand side ("hedgers do not read journals") against a threat that runs through supply. | Rewritten to concede the supply-side exposure directly and answer it with the stated condition rather than a claim of immunity. |
| CH-5 | 6 | **Consistency regression created by CH-2.** The conclusion still read "structural rather than informational," the binary just declared incomplete. | Changed to "rests on constraint rather than on information," which covers both structural demand and intermediary capacity. |

**Design intent (longevity).** The change is to the *form* of the persistence claim, not its content.
A categorical claim ("structural, therefore persists") is falsified the moment one premium compresses.
A conditional, monitorable claim ("pays while specialist capacity is constrained, and here is what to
watch") survives that, and matches the vault standard that an ex-ante rationale fixes the sign before
any test. The thesis is untouched; the short pole is not retired.

New references added, all verified: Bates (2022), Dew-Becker & Giglio (2025, flagged in the entry as a
Federal Reserve working paper and not peer-reviewed), Gârleanu, Pedersen & Poteshman (2009),
Tomunen (2026).

**Deliberately not cited:** the "shadow gamma" result (dealers' crash-scenario short exposure persisting
even where conventional local gamma flipped) would have defended 2.2, but the only source is an
unpublished conference paper whose authors and title could not be pinned down. Not put into a paper that
just cleared a strict integrity gate. **Handed to the affected seat** rather than left in this log:
recorded as an open, do-not-cite-until-sourced lead in
[[research/convergent-engine/_brief|③ convergent-engine]] (which owns the short pole), with a
cross-reference in [[research/v-crash-defense/_brief|④ v-crash-defense]] (dealer positioning is already
on its microstructure list). The same hand-off carries the verified constraint finding, since it changes
③'s premise: the seat inherits an ex-ante admission gate, a positive definition for its thesis line, and
a prior question on ILS orthogonality.

**Word budget is now out of tolerance and needs a decision.** Body is 8,497 words vs the Phase 0 target
of 7,500, or +13.3%, outside the +/-10% band. Concentrated in Ch2 (1,879 vs 1,400, +34%), which is where
the new argument landed. The prose was tightened once already; further cuts would remove substance
rather than flab. Either the Phase 0 target moves to reflect a paper that now carries an additional
substantive argument, or a dedicated whole-paper tightening pass runs before finalize.

### Round-3 integrity re-check outcome

Verdict **PASS WITH NOTES** (unchanged). All four new references verified independently by the gate
(fetched fresh rather than trusting the challenge report or my own lookups). Sections 2.2, 2.4 and 6 all
claim-faithful, including the load-bearing caution that a jump-tied premium lives in the wedge rather
than in the synthetic leg's alpha. Consistency sweep found **no stale categorical-persistence
dependency** in Ch4, Ch5 or the Introduction: those passages describe the buyer's demand motive, which
is a different claim from the seller's premium size, so 2.4's capacity conditioning does not contradict
them.

| ID | Severity | Location | Action taken | Status |
|---|---|---|---|---|
| CH-6 | MINOR_DISTORTION | 2.4 | One citation was carrying two different break dates. "Estimated at 2012 in their own statistical work" was attributed to Dew-Becker & Giglio (2025), but WP 2025-17 only ever says "around 2010"; the precise August 2012 figure belongs to the authors' **sibling** paper (conditionally accepted, *Critical Finance Review*, 2026), which the paper does not cite. Fixed by simplification rather than by adding a reference at the finalize boundary, consistent with the MD-4 call: the sentence now reads "the break date is also unsettled, with Bates (2022) placing it at 2017 rather than 2010 on separate methodology." Accurate to the cited source, removes the internal inconsistency, and the paragraph's point (direction survives, date does not) is unaffected. | Resolved |

Gate transparency note recorded: the exact "hedge different states" footnote underpinning caution (c)
was confirmed structurally against WP 2025-17 by the gate's own reading, but the verbatim footnote rests
partly on the challenge-verification agent's earlier lookup rather than a fully fresh one. Non-blocking.

Phase 7 additions: the Dew-Becker & Giglio entry is alphabetically misplaced (sits before DeMiguel),
folded into IL-MINOR-2 with the other alphabetization work.

## Next

Targeted integrity re-check on the new 2.2 / 2.4 / 6 passages and the four new references, then the
word-budget decision, then Stage 5 FINALIZE and Stage 6 PROCESS SUMMARY.

## Formatting decisions of record (Stage 5)

| Parameter | Value | Rationale |
|---|---|---|
| Line spacing | **Single** (`\singlespacing`) | Explicit author decision, overriding the skill template's APA `\doublespacing` default. Recorded here as a Paper Configuration Record parameter rather than an ad-hoc edit, which is the condition set when this was last discussed. APA double spacing is a manuscript-preparation convention that exists to leave room for reviewer markup; this artifact is the reading deliverable on the `papers/` shelf, not a submission, and the author has chosen the format to match the use. 29 pages to 19. If the paper is ever prepared for submission, this reverts to `\doublespacing` and the orphan controls below are needed again. |
| Abstract spacing | Single, same as body | Follows the body setting. |
| Orphan/widow control | None required | Two `\enlargethispage` calls were needed under double spacing, where the title page pushed one word of the keywords line onto page 2 and the Conclusion's final line fell onto a page of its own. Both were verified vestigial at single spacing (identical 19-page output, no page under 40 words, with and without them) and removed rather than left as dead directives. |
| Byline | `madebymlai` / Aegis | Author-supplied. The `[AUTHOR NAME]` placeholder existed only because no byline had been given and one must never be inferred from git config or email. |
| Engine | XeLaTeX | pdfLaTeX compiled clean but silently mangled the Romanian comma-below-s in "Roșu" into a broken composite; T1 fontenc lacks the glyph and degrades rather than erroring. Caught by extracting the PDF text layer rather than trusting the compile log. |

Shipped PDF: 19 pages. Em dashes 0; placeholders 0; banned phrase 0; COI disclosures 15 of 15; no
thin pages; accented names all render as correct single glyphs.

**Carry-forward for the seat papers:** the byline and the spacing choice live only in the
generated `.tex`, not in `_draft.md`, so a regeneration from source loses them. Before papers 2-4 run
through the same template, the byline belongs in the Phase 0 configuration.
