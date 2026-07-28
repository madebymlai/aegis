---
title: "Budgeting Convexity - Stage 3' re-review verification"
paper: "Budgeting Convexity"
status: "Stage 3' re-review complete - Accept"
tags:
  - review
  - stage3
  - re-review
---

# Budgeting Convexity - Stage 3' re-review verification

Targeted verification (`academic-paper-reviewer`, `re-review` mode: EIC-only, Round-1 cards reused,
no fresh panel) of whether the three Required Revisions from
[[research/budgeting-convexity/_review|_review]] were addressed in
[[research/budgeting-convexity/_draft|_draft]], per the author's claims in
[[research/budgeting-convexity/_revision|_revision]]. No changes were made to any input file.

## Judge Record (#539)

- **Verification judge**: Claude (Sonnet 5, model id `claude-sonnet-5`) - this session.
- **Round-1 panel provenance**: unknown (provenance block absent). `_review.md` carries a "Reviewer
  configuration" table (Seat/Identity/Focus) but no "Review Panel Provenance" (#540) block naming
  per-seat model identity; no such block was introduced retroactively.
- **Independent cross-model pass**: not_configured.
- **Prompt/rubric surfaces**: `re_review_mode_protocol.md` (Re-Review Mode / Verification Logic /
  New Issue Detection sections), applied against `_review.md` Part 2 (Editorial Decision, Top
  Blocking Issues) and Part 3 (Revision Roadmap, Required + Suggested + Priority 3 checklist).
- **Reviewer configuration**: `round1_cards_reused`. The Round-1 Reviewer Configuration Cards (EIC,
  R1 Methodology, R2 Domain, R3 Perspective, Devil's Advocate) in `_review.md` were read and reused
  verbatim as the yardstick; `field_analyst_agent` was not re-invoked and no persona was regenerated
  over the revised text.
- **Evidence seen by the judge**: full text of the revised manuscript (`_draft.md`, all 803 lines,
  Abstract through References), the Response to Reviewers (`_revision.md`, complete), the Round-1
  Editorial Decision + Revision Roadmap (`_review.md`, complete), and the argument blueprint
  (`_argument.md`, Sub-Argument 3 and Sub-Argument 4, for continuity checking against the planned
  concessions the roadmap cited). No apply report (`.apply-report.json`) exists for this revision
  round; the revision was not made through a patch-apply toolchain, so no `output_draft_hash` check
  applies.
- **Judging budget**: one complete read-through of `_draft.md`, `_review.md`, and `_revision.md`;
  targeted greps against the draft for em-dash count, residual citation-by-title strings, hyphenation
  of "Al-Fallouji," and ERC/unordered-blend language; a comparison read of `_argument.md` Sub-Argument
  3 against the restored Section 4.4 concession. No sub-agents were spawned; single EIC-only pass, as
  the mode specifies.

This verification round ran on the same model family that drove the revisions; over-optimization to
this judge's latent biases is possible (Ren et al. 2026, arXiv:2607.13104 §8.1.2).

## Decision

**Accept.**

All three Required Revisions are FULLY_ADDRESSED and independently verified against the actual
manuscript text (not the author's say-so). All four Suggested Revisions are FULLY_ADDRESSED (100%,
above the 80% bar). All Priority 3 nits are either fixed or legitimately, transparently deferred. One
minor new wrinkle (NEW-1, a residual sentence-level tension in Section 5.4) was found during
verification; it is cosmetic, does not reopen any of the three Major gaps, and does not warrant
another revision round.

## Revision Response Checklist

### Priority 1 - Required Revisions

| # | Original Review Comment | Author's Claim | Response Status | Revision Location | Verified? | Cross-model (#539) | Quality Assessment |
|---|---|---|---|---|---|---|---|
| R1 | "Restore the planned non-uniqueness concession in Section 4.4... state that the Floor-Target-Expansion order is non-arbitrary... but not claimed unique or provably optimal, with per-role optimality deferred to the seat papers, matching `_argument.md` Sub-Argument 3's rebuttal" (Roadmap R1; DA-M1) | "Restored the planned non-uniqueness concession from `_argument.md` SA3... folds in R1 W4 / DA alternative-path" | FULLY_ADDRESSED | Section 4.4, closing paragraph | Yes | not_configured | Verified against `_draft.md:406-411`: "This much the evidence compels: fewer and more purposeful sleeves beat counting, and each tier here is forced by a named, documented failure the tier below it cannot repair. What the evidence does not compel is that this particular sequence is the only defensible one. The order defended here is non-arbitrary rather than unique or provably optimal, and a different author could narrate an alternative ordering from the same failure-mode logic. Showing that the ordered roster does real work beyond an unordered, equal-risk-contribution blend of the same sleeves, and that each role holds on its own terms, is the task of the seat papers rather than a claim settled here." This tracks the planned rebuttal in `_argument.md` Sub-Argument 3 almost verbatim ("The order is not claimed unique or optimal; it is claimed non-arbitrary... Concede that the specific roster is one instantiation and defer per-role optimality to the seats") and additionally folds in the ERC-blend comparison that both R1's W4 and the Devil's Advocate's "Ignored Alternative Paths" independently asked for. The concession sits in the same section as the confident claim (4.4), not deferred to Ch6 alone, which was EIC/R1's specific complaint. It genuinely defuses the rhetorical overclaim: the paper no longer implies the order is derivationally compelled, only that it is non-arbitrary, and it names the exact deferred test rather than gesturing at "future work." The empirical alternative-ordering question is properly left to the seat papers per the paper's own stated integrative scope, which is a legitimate deferral, not an evasion (see Decision Rationale). |
| R2 | "Rebalance Section 5.4's evidentiary base: add a peer-reviewed, non-COI corroboration... if one exists, or explicitly COI-flag One River / Man Group / LongTail Alpha as is done for CFM/AQR/PIMCO elsewhere, and soften the claim's framing to match what the peer-reviewed anchors... actually establish" (Roadmap R2; DA-M3) | "Rebalanced the monetization evidence: named the one peer-reviewed anchor (Bhansali et al. 2020, JPM) and COI-flagged it (LongTail Alpha); COI-flagged One River and Man Group in-text as product-sellers cited as illustration; scoped the firm claim to the narrower peer-reviewed Israelov result and framed monetization as a design lean, not a settled finding" | FULLY_ADDRESSED | Section 5.4 | Yes | not_configured | Verified against `_draft.md:485-510`. In-text COI flags now present for all three: Bhansali et al. ("published in this journal but authored at LongTail Alpha, which runs tail-hedging mandates of the kind it studies"), One River ("whose firm sells convex-overlay strategies"), Man Group ("whose firm sells trend and overlay products") - matching the reference-list brackets (`[COI: LongTail Alpha; peer-reviewed]`, `[COI: practitioner, One River sells convex-overlay strategies]`, `[COI: practitioner, Man sells trend/overlay products]`). The claim is explicitly rescoped: "Read conservatively, what the peer-reviewed record firmly establishes is the narrower Israelov result, that a standing, unmanaged put is usually dominated by simply holding less risk. The stronger monetization claim rests on evidence that is real but conflicted, so the paper advances it as a design lean rather than as a settled finding." This is a more precise treatment than even the Round-1 review's own phrasing, which had grouped Bhansali/LongTail Alpha with the two undisputed white papers as "three non-peer-reviewed practitioner pieces" - the revision correctly separates Bhansali (peer-reviewed in JPM, but COI'd) from One River/Man Group (non-peer-reviewed practitioner pieces), which is a more honest, not less honest, accounting. The revision chose the roadmap's "or" branch (flag + soften) rather than sourcing new corroboration, which the roadmap explicitly permits. See NEW-1 below for one residual wrinkle in the section's closing sentence. |
| R3 | "Add direct engagement, in Section 5.5, with the leverage-effect / asymmetric-volatility literature, explaining precisely why a risk-conditioning rule that de-risks on rising realized volatility is not simply a lagging return-timing rule, sharpening the distinction beyond 'risk is more stationary and estimable'" (Roadmap R3; DA-M2) | "Added direct engagement with the leverage-effect / asymmetric-volatility entanglement: conceded that de-risking on rising vol resembles lagging return-timing, then distinguished the two by what each must get right (risk-conditioning is indifferent to the sign of the next return; timing must forecast it, which is what arbitrage prices away)" | FULLY_ADDRESSED | Section 5.5 | Yes | not_configured | Verified against `_draft.md:531-541`: "This distinction has to survive an obvious objection. Realized volatility and forward returns are empirically entangled through the leverage effect, since volatility spikes tend to coincide with falling prices, so a rule that cuts exposure when realized volatility rises will often cut it into a declining market, which resembles a lagging return-timing rule. The reply is that the two rules differ in what they must get right to add value. A risk-conditioning rule reduces variance and tail exposure whether or not the market has mispriced anything, and it is indifferent to the sign of the next return; it does not need a forecast to be correct. A return-timing rule earns its keep only if it forecasts that next return, which is the forecast that limits-to-arbitrage prices away." This directly engages the entanglement rather than asserting the boundary is clean, concedes the resemblance at face value before rebutting it, and the distinction is logically sound: a variance/tail-reduction rule's value proposition does not require the *sign* of the next return to be correctly forecast, whereas a timing rule's edge is entirely that forecast, which is exactly what Section 2.4's limits-to-arbitrage argument prices away. This closes the exact gap R1 and the Devil's Advocate (DA-M2) both raised. |

Cross-model not configured for this run; every Priority 1 row carries `not_configured` per the
single-family disclosure above.

### Priority 2 - Suggested Revisions

| # | Original Review Comment | Response Status | Notes |
|---|---|---|---|
| S1 | COI-flag Choueifaty & Coignard (2008), consistent with the paper's own disclosure practice | FULLY_ADDRESSED | `_draft.md:360-362` in-text: "Choueifaty and Coignard (2008), whose diversification-ratio metric underpins a fund marketed by the first author's firm TOBAM" - prose style matching the paper's other in-text COI disclosures (e.g. Bhansali/PIMCO, Koijen et al./AQR). Reference list `:684-685` carries the matching bracket: `[COI: TOBAM markets a fund built on the diversification-ratio metric]`. |
| S2 | Add a paragraph (Ch5 or Ch6) on implementation/governance friction + a one-line reflexivity answer | FULLY_ADDRESSED | `_draft.md:588-599` (Ch6): covers mandate rigidity ("most policy statements allocate by asset class or manager type rather than by convexity role... re-underwriting the mandate"), tail-sleeve cost and discipline to hold through calm (extending Shleifer & Vishny, 1997, to "the allocator's own seat"), and closes with the direct reflexivity answer: "could publishing this framework shrink the very payers it relies on? We think not, because those payers are structural rather than informational." All three roadmap elements land in one paragraph, as the roadmap allowed. |
| S3 | Formalize the ordinal (ranking) vs cardinal (budgeting) distinction in 3.5 | FULLY_ADDRESSED | `_draft.md:280-283`: "The difference is between an ordinal, repeatedly resampled comparison and a cardinal, point-estimate target: a cross-sectional rank only has to order assets correctly on average across many rebalances, which the noisy third moment can manage, whereas a book-level budget needs the magnitude of a single net figure to hold still, which it cannot." Matches the requested formalization precisely. |
| S4 | Scope-note the risk-premium reading of trend's return in 2.3 against the underreaction alternative in Moskowitz-Ooi-Pedersen (2012) | FULLY_ADDRESSED | `_draft.md:167-170`: "The risk-premium reading is adopted deliberately, because it is what the persistence argument of Section 2.4 requires; the same literature also offers an under-reaction and slow-information-diffusion account of time-series momentum (Moskowitz, Ooi, and Pedersen, 2012), which is compatible with a hedger-paid premium and which the argument here does not need to adjudicate." Names the choice as deliberate and cites the alternative in the same source, exactly as requested. |

4/4 (100%) of Suggested Revisions have a substantive response, above the 80% bar.

### Priority 3 - Nice to Fix

| # | Original Review Comment | Response Status |
|---|---|---|
| N1 | "(Empirical Economics, 2026)" -> "(Trucíos, 2026)" | FULLY_ADDRESSED - `_draft.md:442` now reads "(Trucíos, 2026)"; no residual citation-by-title string found anywhere in the draft (verified by grep). |
| N2 | "(When simplicity beats optimization, 2026)" -> "(Feng, 2026)" | FULLY_ADDRESSED - `_draft.md:479` now reads "(Feng, 2026)"; no residual string found. |
| N3 | "Al Fallouji" (in-text) -> "Al-Fallouji" (reference list) | FULLY_ADDRESSED - `_draft.md:332` now reads "Al-Fallouji," matching the reference-list entry at `:772`; no un-hyphenated "Al Fallouji" remains anywhere in the draft. |
| N4 | Split 60-90-word sentences in Sections 3 and 5 | WONTFIX, rationale given (`_revision.md`: Writing Quality scored Strong by three reviewers; rewriting risks introducing error for a cosmetic gain). Legitimate scoping; does not affect decision per protocol. |
| N5 | Reference-list re-alphabetization (Dao et al., Feng, Trucíos) | Confirmed still deferred and still tracked. The draft's own inline notes ("re-alphabetize to 'D' at formatting," "re-alphabetize to 'F' at formatting") remain in place at `_draft.md:666` and `:802-803`; Trucíos (`:697-699`) sits between DeMiguel and Fleming, out of strict alphabetical order, consistent with the Phase 7 formatting deferral already logged in `_integrity.md`. Not touched, not silently dropped. |

Priority 3 items do not affect the Decision per protocol; all are either fixed or transparently
deferred with a stated rationale.

## New Issues (Discovered During Revision)

| # | Type | Location | Description |
|---|---|---|---|
| NEW-1 | Internal-consistency wrinkle (minor) | Section 5.4, closing sentence | The R2 fix inserts a genuine epistemic downgrade mid-paragraph - "The stronger monetization claim rests on evidence that is real but conflicted, so the paper advances it as a design lean rather than as a settled finding" - but the paragraph's final sentence reverts to unqualified language two sentences later: "The tail is therefore a budget line, sized against the cost of simply de-risking and **earned back through monetization** rather than through holding to the next crash" (`_draft.md:508-510`). Before the revision, the whole paragraph spoke with uniform confidence, so no internal tension existed; the new hedge in the middle now sits awkwardly next to the unhedged "therefore... earned back through monetization" close, which reads as quietly re-asserting the very claim the sentence before it just downgraded to a "design lean." This does not reopen the Major gap - the COI flags, the honest anchor-naming, and the rescoping are all present and correct - but a careful copy-edit pass (e.g., "...and is designed to be earned back through monetization, though the specific rebalancing edge remains a lean rather than a settled result") would remove the residual tension. Minor severity; does not block Accept; flagged for Stage 4.5 / final-polish attention rather than another R&R round. |

No other new issues were found. Specifically checked and clear: (1) no new or renamed in-text
citation fails to resolve to a reference-list entry (Bhansali et al. 2020, One River 2024, Man Group
2022, Choueifaty & Coignard 2008, Trucíos 2026, Feng 2026, Al-Fallouji 2026 all resolve correctly);
(2) em-dash count across the full draft is 0 (`grep -c "—"` = 0), house style intact; (3) Section
4.4's restored concession does not contradict the roster's earlier confident language in 4.1-4.3,
because 4.4 explicitly delimits what the evidence compels (fewer, purposeful, failure-forced tiers)
from what it does not (this exact sequence being unique) rather than silently undercutting the
earlier prose; (4) Section 5.5's new leverage-effect paragraph does not contradict Section 2.4's
arbitrage argument or Section 5.3's timing-fails-out-of-sample evidence - it extends the same
argument to a specific objection rather than opening a new front; (5) §5.2 still correctly declines
to describe the book as unlevered ("not the book's use of leverage, which it runs up to that cap"),
unaffected by this revision round.

## Decision Rationale

All three Required Revisions are FULLY_ADDRESSED against independent verification at the stated
manuscript locations, not merely against the author's claims in `_revision.md`. Each restores or adds
exactly the textual content the Round-1 panel and the Devil's Advocate converged on from independent
angles (SC-1/DA-M1, SC-2/DA-M2, SC-3/DA-M3), each is a text-level fix as the Round-1 Decision
Rationale anticipated (no new data, no restructured argument), and none is a rubber-stamped claim -
every one was checked by navigating to the cited section and reading the actual revised prose against
the specific concession, distinction, or rebalancing the roadmap demanded. All four Suggested
Revisions are likewise fully and correctly implemented, and all Priority 3 items are either fixed or
transparently, honestly deferred with rationale (not silently dropped).

On the WONTFIX deferrals in `_revision.md`: the unordered-ERC backtest, the regularized book-level
skew-tilt test, and the "does the roster do real work beyond a factor-level portfolio" question are
all legitimately scoped out. This paper states up front, and restates in Section 4.4's own restored
concession and in Chapter 6, that it is an integrative paper asserting roles at the roster level and
deferring per-role empirical proof to three named seat papers; judged against that stated scope
rather than against a demand for empirical work the paper never claimed to do, deferring these three
items is honest scoping, not evasion. The sentence-splitting and reference-realphabetization
deferrals are cosmetic and already correctly tracked (the latter explicitly, via inline notes in the
draft itself and the Phase 7 formatting queue in `_integrity.md`).

The one new issue found (NEW-1) is a minor, single-sentence residual tension introduced as a
side-effect of a good-faith hedge, not a new substantive gap; it does not revive any of the three
Major findings and is well below the bar that would require another revision round. Given
FULLY_ADDRESSED on all Required Revisions, >=80% (in fact 100%) on Suggested Revisions, and no
new issue of Major severity, the paper clears the bar for **Accept**.

## Residual Issues

- **NEW-1** (Section 5.4 closing sentence): recommend a light copy-edit at the next opportunity
  (Stage 4.5 integrity pass or final formatting) to carry the "design lean, not settled" hedge
  through to the paragraph's last sentence. Does not block publication-track progression.
- **Ch6 word-count overage** (not a content defect): `_revision.md` self-reports Ch6 at +25.6%
  (879 words vs. 700 target) as a deliberate, accepted consequence of landing the reviewer-mandated
  S2 governance paragraph in the conclusion, with the overall body total (7,564 words) still within
  +/-10% of target. This was disclosed and accepted by the authors, not discovered here; noted only
  for completeness, not as a re-review finding.
- **Reference-list alphabetization** (Dao et al., Feng, Trucíos): still out of strict alphabetical
  order, still correctly flagged inline and tracked for Phase 7 formatting. No action needed at this
  stage.
- **Devil's Advocate's "Unexamined Premise"** (does the roster do real work beyond a factor-level
  risk-budgeted portfolio?): properly folded into the Section 4.4 concession's deferral to the seat
  papers per the Decision Rationale above; recommend the first seat paper address this explicitly
  rather than only the narrower ERC-blend comparison, since a skeptical reader could still ask
  whether "sleeve" is the right unit of construction even after the ordering question is settled.
  Acknowledged Limitation, not a gap in this revision.
