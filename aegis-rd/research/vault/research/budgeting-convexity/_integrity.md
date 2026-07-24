---
title: "Budgeting Convexity - Stage 2.5 integrity verification"
paper: "Budgeting Convexity"
status: Stage 2.5 INTEGRITY - PASS WITH NOTES
tags:
  - integrity
  - stage2.5
---

# Academic Integrity Verification Report

## Verification mode
Initial Verification (pipeline Stage 2.5, pre-review). Level: strict.

## Verdict
**PASS WITH NOTES.** Every cited source was verified to exist and to be correctly attributed. Every
SERIOUS / MEDIUM / MAJOR-distortion issue found during the pass was corrected in the same pass and
re-verified. One MINOR note remains (a single exact volume/page field), plus cosmetic DOI backfill and
APA re-alphabetization deferred to Phase 7 formatting. Under the pipeline IRON RULE this releases to
Stage 3.

## Verification summary

| Category | Total | Verified | Issues (all resolved in-pass) |
|---|---|---|---|
| Reference existence (Phase A1) | ~48 | ~48 | 0 NOT_FOUND, 0 fabrications |
| Bibliographic accuracy (Phase A2) | ~48 | ~48 | 1 title, 1 author-list, several page/DOI backfills |
| Ghost citations (Phase A3) | - | - | 0 orphan, 0 dangling (after AQR split + WYTO entry added) |
| Citation-context / claim fidelity (Phase B / E) | key claims | - | 3 MAJOR_DISTORTION found and corrected |
| Originality (Phase D) | spot-check | clean | 0 close-match, 0 verbatim (prose is original) |
| 7-mode AI-research-failure checklist | 7 | 7 CLEAR | 0 SUSPECTED |

## Corrections made during the pass (the value of the gate)

Verification was done by live web lookup (Exa), not memory. It confirmed every source and forced the
following corrections, now applied to the draft:

### Bibliographic (Phase A2)

- **Anghel et al. (2023)** title was wrong: "Systematic Skewness: Two Decades Later" corrected to
  **"Asset Pricing with Systematic Skewness: Two Decades Later"** (CFR 12(1-4):309-354).
- **Bouchaud et al. (2017)** carried a partially-hallucinated author list (Ciliberti, Majewski, Ronia).
  The real authors are **Dao, Hoehener, Lempérière, Nguyen, Seager & Bouchaud** (arXiv:1708.07637);
  in-text updated to Dao et al. (2017).
- **Lempérière** was mis-spelled "Lempeeriere" throughout; corrected.
- **"Monetization Matters"** is a JPM 2020 article by **Bhansali, Chang, Holdom & Rappaport** (DOI
  10.3905/jpm.2020.1.181), not a bare LongTail Alpha white paper; entry and in-text upgraded.
- **AQR (2020)** split into 2020a (Contrasting Put and Trend) and 2020b (Working Your Tail Off) so the
  5.5 citation resolves to a listed reference (was a near-dangling citation).
- DOIs / pages added for 25 references verified this session.

### Claim faithfulness (Phase B / E) - the most important catches

Reading the sources closely surfaced four places where the draft asserted more than the cited work
supports. A real citation attached to a claim it does not make is the failure this gate exists for.

1. **Martellini & Ziemann (2010), Section 3.4 - MAJOR.** Draft said higher-moment portfolios "struggle
   to beat minimum-variance out of sample." The paper finds the opposite: with improved comoment
   estimators they *dominate* mean-variance out of sample. Rewrote 3.4 to the faithful, weaker claim
   (higher-moment optimization works only with elaborate estimation and buys a modest, method-dependent
   edge), which still supports "you cannot size a book on a raw net-skew target."
2. **Lassance & Vrins (2023), Section 3.4 - MAJOR.** Draft implied "no OOS benefit." The paper shows a
   method that *does* improve higher moments as a compromise accepting higher variance. Reframed.
3. **Bongaerts, Kang & van Dijk (2020), Section 5.2 - MAJOR.** Draft attributed "down-only vol
   targeting" to the paper. Their conditional strategy de-levers in high-vol and *levers up* in low-vol
   extremes. Rewrote 5.2 to attribute the actual finding (conditional beats conventional; low leverage)
   and to frame the strictly down-only ceiling as the motivating system's implementation choice.
4. **Schwalbach & Auret (2025), Section 5.4 - MEDIUM.** "All nine crises" corrected to "all but one of
   nine crisis episodes."

## Phase D: originality

The body prose is original authored text. Spot-checks of characteristic sentences returned no external
matches beyond common-knowledge domain phrasing. No verbatim or close-match paragraphs. (Heuristic
WebSearch screen, not professional plagiarism software.)

## Phase E: claim verification

Quantitative claims were traced to sources and confirmed: Harvey-Siddique coskewness premium ~3.6%/yr
and OOS 1.4-4.7% (verified); Baltas-Salinas cross-asset skew Sharpe 0.72-0.73 (verified);
Olszewski-Zhou Sharpe 0.79/0.63 to 0.98, Calmar +71%/+289% (verified); Brown et al. over-diversification
past ~20 funds raising left-tail risk (verified); McLean-Pontiff 26% OOS / 58% post-publication decline
(verified). The four distortions above were the only claim-fidelity failures, all corrected.

## 7-mode AI-research-failure checklist (mandatory, blocking)

This is a theoretical / integrative paper with no original experiments, datasets, or numerical results
reported as its own findings; the one reference to our own system (ADR-0004 / allocator) is labeled
in-sample illustration and reports no numbers as discoveries.

| Mode | Status | Evidence |
|---|---|---|
| 1 Implementation bug in results | CLEAR | No own-computed numbers; all figures are from cited external literature |
| 2 Hallucinated citation | CLEAR | ~48 references web-verified; corrections applied; no fabrications |
| 3 Hallucinated experimental result | CLEAR | No experimental results claimed; empirical proofs explicitly deferred to seat papers |
| 4 Shortcut reliance | CLEAR (N/A by paper type) | No trained model / empirical result of our own |
| 5 Bug reframed as insight | CLEAR | The counterintuitive hook is grounded in Brown et al., not an unexplained own-result |
| 6 Methodology fabrication | CLEAR | No Methods-of-runs section; method is transparent argument/synthesis |
| 7 Frame-lock | CLEAR | Framing survived the go/no-go and the pivot sharpening; integrative-paper limits disclosed in Ch6 |

No mode SUSPECTED; none INSUFFICIENT EVIDENCE. Checklist does not block.

## Issue list (final state)

### SERIOUS / MEDIUM / MAJOR
All found issues (1 title, 1 author-list, 4 claim-faithfulness distortions) were **corrected in this
pass and re-verified**. None outstanding.

### MINOR (notes, non-blocking)
| ID | Category | Location | Note |
|----|----------|----------|------|
| IL-MINOR-1 | Reference | Lassance & Vrins (2023) | Exact EJOR volume/pages pending final confirmation; existence, authors, venue, DOI confirmed |
| IL-MINOR-2 | Formatting | References | Dao et al. and Feng entries re-alphabetize at Phase 7; DOI backfill for ~20 canonical classics is cosmetic |
| IL-MINOR-3 | Reference | Olszewski & Zhou (2013) | Publisher byline spells surname "Olszweski"; standard spelling retained with a note |

## Tool-limitation disclaimer

Originality screening (Phase D) used heuristic WebSearch, not Turnitin/iThenticate. Reference
verification used Exa web search item by item; the Semantic Scholar batch API layer (Phase A0) was not
invoked in this environment. Stage 4.5 will re-verify all references fresh and independently as the
pipeline's designed backstop.

## Audit trail

Every reference reached a VERIFIED verdict via at least one web lookup this session (queries recorded
in the conversation): the 15 recent/pending sources first, then the 5 practitioner pieces, then the
~26 canonical journal classics in four batches. Verification date: 2026-07-24.
