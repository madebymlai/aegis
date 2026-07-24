---
title: "Budgeting Convexity - Stage 4.5 final integrity verification"
paper: "Budgeting Convexity"
status: "Stage 4.5 FINAL INTEGRITY - PASS WITH NOTES (round 3: VRP-challenge-driven edits to 2.2/2.4/6 re-verified, 1 new non-blocking MINOR_DISTORTION found; round 1 FAIL and round 2 PASS WITH NOTES history retained below)"
tags:
  - integrity
  - stage4.5
---

# Academic Integrity Verification Report - Final Integrity (Stage 4.5)

## Verification mode and level

**Mode 2: Final Verification** (Stage 4.5, post-revision, pre-finalize). **Level: strict.**
Phase A was executed as a **fresh, independent** re-verification of every reference, performed as if
Stage 2.5 had never happened. Nothing below was accepted on the strength of a prior stage's conclusion;
every verdict has its own live-lookup audit trail dated 2026-07-24.

## Verdict

**PASS WITH NOTES.** *(Updated after round 3 - see "Round 3: VRP-challenge edits (2.2/2.4/6) and four new
references" below. The round-1 verdict was FAIL and round 2 was PASS WITH NOTES; both are preserved as-is
in this document rather than erased, per the instruction that the record of what was caught is part of
the gate's value.)*

**Round 3 in one line:** all four newly-added references independently VERIFIED; two of the three
re-verified passages (Section 2.2, Section 6) are fully clean; Section 2.4 is clean except for one new,
non-blocking **MINOR_DISTORTION** (a break-year figure attributed to the wrong paper within the same
citation) - see below. The gate remains PASS WITH NOTES.

**Round 1 (this section, unchanged from first pass): FAIL.** All bibliographic (Phase A) defects found
that session were corrected in-pass and re-verified: zero SERIOUS and zero MEDIUM reference issues
remained. However, two **MAJOR_DISTORTION** claim-fidelity findings in body prose were open (Phase B/E) -
both newly caught at this gate, both missed at Stage 2.5. Per the Verdict Criteria, any MAJOR_DISTORTION
fails the gate regardless of how much else passes, and edits to body prose were outside the editing
mandate for that pass, so FAIL was reported rather than softened to PASS WITH NOTES.

**Round 2 (author-applied fixes, re-verified fresh this session): PASS WITH NOTES.** The author fixed
both MAJOR_DISTORTION items (Section 2.2 BTZ/jump mechanism misattribution; Section 5.5 Uysal & Mulvey
risk-vs-return framing) and both MINOR_DISTORTION items (Section 3.2 Harvey & Siddique magnitude range;
Section 4.3 Choueifaty & Coignard squared-DR attribution). All four corrected passages were independently
re-verified against primary sources this session (not from memory, not by re-reading the proposed
rewords and assuming they were applied correctly) and all four are now clean - see the round 2 section
below for the full trail. Per the Verdict Criteria table, the paper now has zero SERIOUS, zero MEDIUM,
zero MAJOR_DISTORTION, and zero UNVERIFIABLE, but retains one non-blocking UNVERIFIABLE_ACCESS (Feng
2026 exact wording, paywalled) and several non-blocking MINOR reference-formatting items deferred to
Phase 7 (IL-MINOR-2, IL-MINOR-7). That combination is exactly the PASS WITH NOTES condition, not a bare
PASS.

## Per-phase summary table

| Phase | Coverage | Result |
|---|---|---|
| A1/A2 Reference existence + bibliographic accuracy | 55 of 55 cited works (54 original + 1 dangling citation discovered) | 7 defects found, **all 7 corrected and re-verified this session** |
| A3 Ghost citation (both directions) | Full text vs. full reference list | 1 dangling citation found (Meucci, 2009) and fixed by adding the entry; 0 orphan references |
| B Citation-context / claim fidelity | 100% of in-text citations, all sections | Round 1: 2 MAJOR_DISTORTION (open), 2 MINOR_DISTORTION. **Round 2: all 4 fixed and re-verified clean; 0 open** |
| C3 Figure/table caption fidelity | N/A - no figures or tables in this integrative paper | PASS WITH NOTES (trace-unavailable / not-applicable, reasoning recorded below) |
| C4 Experiment provenance | N/A - no experiments; legacy no-passport path | PASS WITH NOTES (`{status: no_experiments_declared}` equivalent, recorded below) |
| D Originality (>=50% + 100% revision-touched) | 15 characteristic-sentence spot checks across all 6 chapters, incl. all 7 revision-touched paragraphs | Clean - 0 CLOSE_MATCH, 0 VERBATIM |
| E Claim verification (100%) | All quantitative/factual claims traced | Round 1: 2 MAJOR_DISTORTION (open), 1 UNVERIFIABLE_ACCESS (Feng 2026 wording, non-blocking). **Round 2: both MAJOR_DISTORTION fixed and re-verified clean**; UNVERIFIABLE_ACCESS remains (non-blocking) |
| E6 Claim-strength drift (revision rounds) | A genuine prior draft WAS recovered via `git show` (see below) - full diff run against all revision-touched passages | **CLEAR** - every change matches its authorized roadmap item; zero unauthorized strengthening or hedge-dropping |
| 7-mode AI-research-failure checklist | All 7 modes | All CLEAR (Mode 2 CLEAR after in-pass correction; see table) |

## A note on E6: a prior draft was actually recoverable

The dispatch brief assumed no prior-draft snapshot exists because the revision edited in place. I checked
anyway: `git log -- .../budgeting-convexity/_draft.md` shows one tracked commit (`5898886e`, the initial
757-line scaffold commit, predating the Stage 3 review and Stage 4 revision round). `_review.md`,
`_revision.md`, and `_rereview.md` are untracked, confirming this commit is genuinely pre-revision. I ran
`git show 5898886e:.../_draft.md` and diffed it against the current text. This let me do a **real** E6
check rather than skip it. Every substantive addition in the diff maps cleanly to a documented roadmap
item:

| Diff location | Change | Roadmap item | Direction |
|---|---|---|---|
| 2.3 | Added under-reaction scope note for Moskowitz-Ooi-Pedersen (2012) | S4 | Hedge added |
| 3.5 | Added ordinal/cardinal distinction sentence | S3 | Precision added, no strength change |
| 4.2 | "Al Fallouji" -> "Al-Fallouji" | nit-2 | Cosmetic |
| 4.3 | Added Choueifaty & Coignard TOBAM COI flag | S1 | Disclosure added |
| 4.4 | Added non-uniqueness concession paragraph | R1 | Hedge added |
| 5.1 | "(Empirical Economics, 2026)" -> "(Trucíos, 2026)" | nit-1 | Citation-form fix |
| 5.3 | "(When simplicity beats optimization, 2026)" -> "(Feng, 2026)" | nit-1 | Citation-form fix |
| 5.4 | Full monetization paragraph rewrite: COI flags added to Bhansali/One River/Man Group, claim narrowed to the Israelov result, "design lean not settled finding" hedge added and carried to the closing sentence | R2 + NEW-1 | Claim weakened/scoped, not strengthened |
| 5.5 | Added leverage-effect/asymmetric-volatility paragraph (concedes entanglement, then distinguishes by what each rule must get right) | R3 | Objection conceded, then a narrower, more defensible distinction restated |
| Ch6 | Added two-practical-limits paragraph (switching cost + monetized-sleeve discipline + reflexivity Q&A, explicitly hedged "We think not, because...") | S2 | New content, appropriately hedged, grounded in already-cited McLean-Pontiff material |

No addition strengthens a claim beyond what its citation supports, and no existing hedge was dropped.
**E6 verdict: CLEAR**, evidenced (not skipped).

---

## Phase A: full reference table (55 entries - all cited works, including 1 dangling citation found this session)

Legend: **F** = defect found and corrected this session; all corrected entries were re-verified after the
fix. Rows without **F** had zero Phase A2 issues from this session's fresh lookup.

| # | Reference (as it now reads) | Verdict | Audit trail |
|---|---|---|---|
| 1 | Anghel, Caraiani, Roșu, & Roșu (2023), *Critical Finance Review* 12(1-4), 309-354 | VERIFIED | Publisher/working-paper PDF fetched; DOI 10.1561/104.00000133 confirmed (not yet in ref list - MINOR, deferred with IL-MINOR-2) |
| 2 | Asif, Frömmel, & Mende (2022), *IRFA* 80, 102045 | VERIFIED | ScienceDirect + RePEc, DOI 10.1016/j.irfa.2022.102045 confirmed |
| 3 | AQR (2020a), *Tail risk hedging* | VERIFIED | aqr.com white paper + JSI 1(1) 2021 republication both confirmed |
| 4 **F** | Asvanunt, A., Nielsen, L. N., & Villalon, D. (2015). *Working your tail off*, JOI 24(2), 134-145 | was **MISMATCH** (cited as "AQR, 2020b", corporate author, wrong year) -> **FIXED, now VERIFIED** | AQR's own site dates the piece June 1 2015; PM-Research/CrossRef confirm real named authors Asvanunt, Nielsen, Villalon, JOI 24(2):134-145, DOI 10.3905/joi.2015.24.2.134. Manuscript's own quoted claim ("direct hedging adds value only for an investor who can both time short-term crashes and unwind... very shortly after") is a near-verbatim match to this paper's actual abstract - confirms this is the right underlying source, just mislabeled |
| 5 **F** | Baltas & Salinas (2022), JPM 48(4), 194-219 | was MEDIUM (pages listed as 133-152) -> **FIXED** | pm-research.com article URL itself + Google Scholar profile both give 194-219 |
| 6 | Baltussen, Martens, & van der Linden (2026), FAJ 82(1), 6-34 | VERIFIED | tandfonline + SSRN 5815464 confirm; page range confirmed by DOI resolution only (not independently cross-sourced - noted, not a defect) |
| 7 | Baltussen, Swinkels, & van Vliet (2021), JFE 142(3), 1128-1154 | VERIFIED | ScienceDirect + SSRN 3325720, DOI 10.1016/j.jfineco.2021.06.030 |
| 8 | Bhansali, Chang, Holdom, & Rappaport (2020), JPM 47(1) | VERIFIED | pm-research.com + SSRN 3668370; LongTail Alpha COI independently confirmed |
| 9 | Bhansali, Davis, Dorsten, & Rennison (2015), JPM 41(4), 82-90 | VERIFIED | jpm.iijournals.com + SSRN 2579089; PIMCO COI confirmed |
| 10 | Bollerslev, Tauchen, & Zhou (2009), RFS 22(11), 4463-4492 | VERIFIED (bibliographic) | Duke PDF + Oxford Academic; **see Phase B - the claim attached to this citation is a MAJOR_DISTORTION**, not a reference defect |
| 11 | Bollerslev & Todorov (2011), JF 66(6), 2165-2211 | VERIFIED | Wiley + working-paper PDF |
| 12 | Bongaerts, Kang, & van Dijk (2020), FAJ 76(4), 54-71 | VERIFIED | Open-access repub.eur.nl PDF read in full |
| 13 | Dao, Hoehener, Lempérière, Nguyen, T.-T., Seager, & Bouchaud (2017), arXiv:1708.07637 | VERIFIED | arxiv.org/abs/1708.07637 fetched directly, all 6 authors confirmed |
| 14 **F** | Brown, Gregoriou, & Pascalau (2012), *Review of Asset Pricing Studies* 2(1), 89-110 | was **SERIOUS** (cited as 2011, vol. 1) -> **FIXED** | RePEc/econpapers + Wiley cross-citation + NYU Stern press release all confirm the formal publication is Vol. 2, Issue 1, 2012 (the 2009-2011 SSRN posting was a pre-publication working paper). Both in-text citations (Section 4.4, two instances) corrected to match |
| 15 | Brunnermeier, Nagel, & Pedersen (2008), NBER Macro Annual 23, 313-347 | VERIFIED | NBER/RePEc/SSRN converge on 313-347 (Crossref shows 313-348, a 1-page discrepancy treated as a source-metadata artifact given 3-source majority agreement) |
| 16 | Carli, Deguest, & Martellini (2014), EDHEC-Risk working paper | VERIFIED | climateinstitute.edhec.edu publication page |
| 17 | Carr & Wu (2009), RFS 22(3), 1311-1341 | VERIFIED | Oxford Academic DOI 10.1093/rfs/hhn038 |
| 18 | Cederburg, O'Doherty, Wang, & Yan (2020), JFE 138(1), 95-117 | VERIFIED (ref-list entry was always correct) | JFE cover page + body fetched directly; **in-text citation was dropping the 4th author "Yan" - fixed as a MINOR citation-form consistency correction** |
| 19 | Choueifaty & Coignard (2008), JPM 35(1), 40-51 | VERIFIED; COI VERIFIED | tobam.fr-hosted PDF + jpm.pm-research.com; Yves Choueifaty confirmed founder of TOBAM, Anti-Benchmark(R) funds confirmed built on this metric. One claim (DR-squared = independent risk factors) is a MINOR_DISTORTION - see Phase B |
| 20 | Costa & Kwon (2019), Quantitative Finance 19(3), 453-471 | VERIFIED | tandfonline DOI 10.1080/14697688.2018.1486036 |
| 21 | De Long, Shleifer, Summers, & Waldmann (1990), JPE 98(4), 703-738 | VERIFIED | RePEc/ideas.repec.org |
| 22 | DeMiguel, Garlappi, & Uppal (2009), RFS 22(5), 1915-1953 | VERIFIED | Oxford Academic |
| 23 | Trucíos (2026), Empirical Economics 70(3), Art. 58 | VERIFIED | DOI 10.1007/s00181-026-02900-x, Semantic Scholar abstract fetched directly |
| 24 | Fleming, Kirby, & Ostdiek (2001), JF 56(1), 329-352 | VERIFIED | Full text fetched (rice.edu PDF) |
| 25 | Fung & Hsieh (2001), RFS 14(2), 313-341 | VERIFIED | Oxford Academic |
| 26 | Gromb & Vayanos (2010), Annual Review of Financial Economics 2, 251-275 | VERIFIED | annualreviews.org |
| 27 | Grinold (1989), JPM 15(3), 30-37 | VERIFIED | Standard, widely-cited; scirp.org reference page |
| 28 | Harvey & Siddique (2000), JF 55(3), 1263-1295 | VERIFIED | Wiley + Duke faculty PDF, DOI 10.1111/0022-1082.00247 (not yet in ref list - MINOR, IL-MINOR-2) |
| 29 | Harvey & Siddique (2023), Critical Finance Review 12(1-4), 355-366 | VERIFIED (bibliographic) | Full PDF fetched, DOI 10.1561/104.00000134 confirmed exactly. One claim (magnitude range) is MINOR_DISTORTION - see Phase B |
| 30 | Hurst, Ooi, & Pedersen (2017), JPM 44(1), 15-29 | VERIFIED | aqr.com + SSRN 2993026; AQR affiliation confirmed |
| 31 | Ilmanen (2012), FAJ 68(5), 26-36 | VERIFIED | rpc.cfainstitute.org + aqr.com; AQR affiliation confirmed |
| 32 | Israelov (2019), JAI 21(3), 6-33 | VERIFIED | Full text fetched (AQR-hosted PDF), title page confirms AQR affiliation |
| 33 | Israelov & Nielsen (2015), JPM 41(4), 108-120 | VERIFIED | AQR site + CFA Institute digest, DOI 10.3905/jpm.2015.41.4.108 |
| 34 | Kang, Rouwenhorst, & Tang (2020), JF 75(1), 377-417 | VERIFIED | Wiley DOI 10.1111/jofi.12845 |
| 35 | Koijen, Moskowitz, Pedersen, & Vrugt (2018), JFE 127(2), 197-225 | VERIFIED | Published PDF fetched, DOI 10.1016/j.jfineco.2017.11.002 confirmed (not yet in ref list - MINOR, IL-MINOR-2); AQR affiliation (Pedersen) confirmed from the paper's own author block |
| 36 **F** | Lassance & Vrins (2023), EJOR 310(1), 302-314, DOI 10.1016/j.ejor.2023.02.014 | was **SERIOUS** (DOI 10.1016/j.ejor.2023.02.199 is a dead/non-resolving DOI) -> **FIXED. Closes IL-MINOR-1** | ScienceDirect + RePEc/IDEAS + UCLouvain repository all confirm vol/pages (310(1), 302-314) were already correct; the DOI itself was wrong. IL-MINOR-1 previously mis-described this as a volume/pages gap - it was actually the DOI, now corrected and confirmed |
| 37 | Le, Kourtis, & Markellos (2023), Journal of Futures Markets 43(6), 734-770 | VERIFIED | Full text fetched (UEA repository mirror), DOI 10.1002/fut.22408 confirmed exactly |
| 38 **F** | Lempérière, Deremble, Nguyen, T.-T., Seager, Potters, & Bouchaud (2017), Quantitative Finance 17(1), 1-14 | was **SERIOUS** (3rd author printed as "Nguyen, T.-L.", a mashup with co-author Dao's initials from the companion paper cited two sentences later) -> **FIXED** | arXiv 1409.7720 + RePEc + SSRN all confirm the co-author is Trung-Tu Nguyen (T.-T.), a distinct CFM researcher from Tung-Lam Dao (T.-L.) of the companion 2017 paper |
| 39 | Lettau, Maggiori, & Weber (2014), JFE 114(2), 197-225 | VERIFIED | RePEc + NBER w18844 |
| 40 | Lopez de Prado (2016), JPM 42(4), 59-69 | VERIFIED | jpm.pm-research.com, DOI 10.3905/jpm.2016.42.4.059 |
| 41 | Maillard, Roncalli, & Teiletche (2010), JPM 36(4), 60-70 | VERIFIED | SSRN 1271972, DOI 10.3905/jpm.2010.36.4.060 |
| 42 | Man Group (2022), *Creating portfolio convexity* | VERIFIED | man.com/maninstitute PDF, authors van Dooijeweert & van Hemert confirmed; content (positive average return, put-like convexity) matches the manuscript's claim |
| 43 | Martellini & Ziemann (2010), RFS 23(4), 1467-1502 | VERIFIED (bibliographic) | Oxford Academic, DOI 10.1093/rfs/hhp099 (not yet in ref list - MINOR, IL-MINOR-2). **Claim-fidelity independently re-derived - the Stage 2.5 fix is confirmed faithful** (see Phase B) |
| 44 | McLean & Pontiff (2016), JF 71(1), 5-32 | VERIFIED | Wiley DOI 10.1111/jofi.12365 |
| 45 **F** | Meucci, A. (2009). Managing diversification. *Risk*, 22(5), 74-79 | was a **dangling citation** (cited twice in-text, lines 359 & 380, with NO reference-list entry at all) -> **entry added, now VERIFIED** | SSRN 1358533 + risk.net + top1000funds.com PDF (which quotes the paper's own formula) all confirm the real work and its exact formula: N_Ent = exp(entropy of the diversification distribution). This matches the manuscript's description ("effective number of bets, the exponential of the entropy of the uncorrelated risk contributions") precisely |
| 46 | Moskowitz, Ooi, & Pedersen (2012), JFE 104(2), 228-250 | VERIFIED | Full Elsevier PDF fetched; AQR affiliation (Ooi) confirmed on the paper itself |
| 47 | Noguer i Alonso & Al-Fallouji (2026), arXiv:2607.00883 | VERIFIED | arxiv.org/abs/2607.00883 fetched directly (MINOR: arXiv spells the 2nd author "Al Fallouji", no hyphen; manuscript uses "Al-Fallouji" throughout - a deliberate Stage-4 edit, left as is) |
| 48 | Olszewski & Zhou (2013), Journal of Derivatives & Hedge Funds 19(4), 311-320 | VERIFIED. **IL-MINOR-3 re-confirmed accurate** | Publisher/Mendeley metadata literally renders the surname "Olszweski" - the manuscript's footnote is correct; standard spelling retained deliberately |
| 49 **F** | One River. (2024). *The convexity (re)balancing act* (P. Kazley & S. Wang) | was **MISMATCH** (cited as "(O. Nieuwenhuizen)", who does not appear anywhere in the document) -> **FIXED** | Fetched the actual PDF cover page directly: byline reads "Patrick Kazley / Stacy Wang"; no Nieuwenhuizen anywhere, including the acknowledgments line |
| 50 | Capital Fund Management (2018), White Paper No. 266 | VERIFIED | cfm.com-hosted PDF fetched in full, formula for trend P&L confirmed to match the manuscript's description exactly |
| 51 | Pyun (2019), JFE 132(1), 150-174 | VERIFIED | Crossref + paper's own PDF (DOI 10.1016/j.jfineco.2018.10.002, not yet in ref list - MINOR, IL-MINOR-2) |
| 52 | Schwalbach & Auret (2025), Investment Analysts Journal 54(3), 364-386 | VERIFIED (bibliographic). **Claim-fidelity independently re-confirmed** | tandfonline DOI 10.1080/10293523.2025.2553254. I personally fetched the abstract/body text and found the exact sentence: "Table 8 summarises results across nine such episodes... The Portable Alpha portfolio outperformed ACWI in all but one event, where it underperformed only marginally" - a precise, verbatim match to the manuscript's claim. Stage 2.5's fix is confirmed correct |
| 53 | Shleifer & Vishny (1997), JF 52(1), 35-55 | VERIFIED | Wiley DOI, Stanford-hosted PDF; used at three separate load-bearing points (Section 2.4, Section 6) - all uses checked, all faithful |
| 54 | Uysal & Mulvey (2021), JFDS 3(2), 87-108 | VERIFIED (bibliographic) | doi.org/10.3905/jfds.2021.1.057, Princeton repository confirms pages 87-108, DOI, and volume/issue (manuscript's ref-list entry omits vol/issue/pages/DOI entirely - MINOR completeness gap, IL-MINOR-2-adjacent). **Claim-fidelity: MAJOR_DISTORTION** - see Phase B |
| 55 | Feng, X. (2026), Financial Markets and Portfolio Management | VERIFIED | CrossRef API + Semantic Scholar, DOI 10.1007/s11408-026-00499-8, author "Xuan Feng" confirmed; volume/issue not yet assigned (article was days-old online-first at check time - not an error). Exact claim wording is paywalled - **UNVERIFIABLE_ACCESS**, non-blocking |

**Phase A3 ghost-citation check, full document, both directions:** every one of the 54 originally-listed
reference entries is cited in-text at least once (confirmed by exhaustive cross-read); zero orphan
references. One dangling citation found (Meucci, 2009 - see #45) and closed by adding its entry. After
this fix: **zero orphan, zero dangling.**

---

## Phase B/E: claim-fidelity findings

100% of in-text citations across all six chapters were checked against their primary source this
session (abstracts, full working papers, or publisher pages fetched directly - not from memory). The
great majority are VERIFIED with the source text quoted or closely paraphrased in the audit trail above
and in the four subordinate verification passes. Below are every finding that is **not** a clean
VERIFIED, in descending severity.

### MAJOR_DISTORTION #1 - Section 2.2, Bollerslev, Tauchen, & Zhou (2009) mechanism misattribution

**STATUS: RESOLVED in round 2 - see "Round 2: targeted re-verification" below for the fresh
independent re-check of the corrected text. This subsection is left as originally written, as the
historical record of what was found.**

**Manuscript text (as it read at round 1, since corrected):** "Bollerslev, Tauchen, and Zhou (2009) show
that the same premium forecasts returns precisely because it is compensation for bearing the risk of
discrete losses."

**What the source actually shows:** Bollerslev, Tauchen, & Zhou (2009), "Expected Stock Returns and
Variance Risk Premia" (RFS 22(11):4463-4492), is built entirely on "a stylized self-contained general
equilibrium model incorporating the effects of time-varying economic uncertainty" - an extension of the
Bansal-Yaron long-run-risk model with Epstein-Zin preferences and stochastic volatility-of-volatility.
The paper's own text is explicit that it "explicitly exclude[s] predictability in consumption growth,
focusing instead on... richer... volatility dynamics" - there is no jump/discrete-loss process anywhere
in the model. The "fear of discrete crashes" / jump-risk mechanism the manuscript attaches to this paper
is actually the contribution of **Bollerslev & Todorov (2011)** - cited in the very next sentence of the
same paragraph. This is a clean case of mechanism-attribution bleed between two adjacent, co-authored
papers in the same citation cluster.

**Proposed faithful reword (for the author to apply; I did not touch this sentence):** attribute the
"premium forecasts returns" finding to BTZ (2009) on its own terms (a time-varying economic-uncertainty /
volatility-of-volatility channel), and reserve the "compensation for discrete/jump losses" claim for
Bollerslev & Todorov (2011) alone. For example: *"Bollerslev, Tauchen, and Zhou (2009) show that the
same premium forecasts returns, a predictability their equilibrium model traces to time-varying economic
uncertainty about future volatility. Bollerslev and Todorov (2011) show that this compensation is, in
large part, specifically compensation for the risk of discrete, jump-driven losses."*

### MAJOR_DISTORTION #2 - Section 5.5, Uysal & Mulvey (2021) risk-vs-return framing

**STATUS: RESOLVED in round 2 - see "Round 2: targeted re-verification" below. The author rejected
option (a) below (dropping the citation) as evidence-suppression and instead applied a variant of option
(b). This subsection is left as originally written, as the historical record of what was found.**

**Manuscript text (as it read at round 1, since corrected):** "What every one of these results conditions on is risk,
meaning a regime's covariance, a volatility level, or a rates-volatility index, and not a forecast of
return or of a crash," citing Costa & Kwon (2019), Uysal & Mulvey (2021), and Fleming, Kirby, & Ostdiek
(2001) together as the evidentiary basis for the paper's central risk-conditioning-vs-return-timing
distinction.

**What the source actually shows:** Uysal & Mulvey (2021)'s own abstract states their regime-prediction
component applies "supervised learning algorithms... to estimate **the probability of an upcoming
recession or a stock market contraction**," and that "the probability estimates are linked to a dynamic
investment overlay strategy." A stock-market-contraction probability is, on its face, a forecast of
return direction / crash likelihood - not a covariance, volatility-level, or rates-volatility-index
signal, which is exactly the three-way exemplar list the sentence itself offers. This directly
contradicts the sentence's explicit claim that the cited evidence is "not a forecast of return or of a
crash," for this one citation specifically. Fleming, Kirby, & Ostdiek (2001) is unambiguously pure
risk-conditioning (confirmed via a direct primary-source quote: "the portfolio weights in this strategy
ignore any time variation in expected returns"), and Costa & Kwon (2019)'s end-objective is a risk-parity
allocation - but Uysal & Mulvey's own stated mechanism is a contraction-probability forecast, which sits
uneasily inside a paragraph whose entire argument depends on the risk/return distinction being exact.

**Proposed handling (for the author; I did not touch this sentence):** either (a) drop Uysal & Mulvey
from this specific three-item list, since Costa & Kwon and Fleming-Kirby-Ostdiek alone cleanly establish
the point, or (b) add a qualifying clause narrowing what is claimed about it - e.g., noting that its
regime layer forecasts a contraction probability that feeds a risk-parity overlay, which is a different
case from the other two if the paper wants to keep citing it elsewhere for a related but distinct point.

### MINOR_DISTORTION (non-blocking, notes only)

**STATUS: both items below RESOLVED in round 2 - see "Round 2: targeted re-verification" below. Left
as originally written, as the historical record of what was found.**

- **Section 3.2, Harvey & Siddique (2023):** the manuscript's "on the order of one and a half to nearly
  five percent" magnitude-range figure does not match the source's own explicitly-stated range ("2.1% to
  3.9%," Table 1), though the paper's broader robustness tables do swing as wide as 0.83%-7.07%. The
  qualitative point - sign stable, magnitude highly unstable - is fully supported; only the specific
  numeric bookends aren't drawn from an explicit statement in the source. Non-blocking.
- **Section 4.3, Choueifaty & Coignard (2008):** the specific mathematical claim that "the diversification
  ratio['s]... square is the number of independent risk factors in the book" is real math, but independent
  secondary sourcing attributes this specific squared-DR-as-effective-bets formalization more precisely to
  the 2012 follow-up paper (Choueifaty, Froidure, & Reynier), not unambiguously to the 2008 paper cited
  here. I could not extract clean primary text from the 2008 PDF to rule this in or out directly. The
  "closely related" hedge already in the sentence partially covers this. Non-blocking.

### UNVERIFIABLE_ACCESS (non-blocking per the Verdict Criteria table)

- **Section 5.3, Feng (2026):** the specific wording "once estimation risk and honest recursive
  implementation are imposed, volatility management and factor optimization do not beat simple
  diversification" is thematically consistent with the confirmed title/abstract snippet, but the full text
  is paywalled and I could not independently trace the exact wording this session.

### Re-confirmed (independently re-derived from primary sources, not merely re-checked against Stage 2.5's conclusion)

- **Section 3.4, Martellini & Ziemann (2010) and Lassance & Vrins (2023):** both re-derived fresh from the
  primary text. The current draft's "dominates... only once substantially improved... estimators are used"
  (Martellini-Ziemann) and "deliberately moving off the mean-variance-efficient frontier and accepting a
  higher variance" (Lassance-Vrins) are faithful, precise characterizations. The Stage 2.5 corrections were
  correct and remain correct.
- **Section 5.2, Bongaerts, Kang, & van Dijk (2020):** re-derived fresh from the open-access primary PDF.
  The current text's "conditional strategy... improves Sharpe ratios and cuts drawdowns with materially
  lower turnover and leverage" is a faithful match to the paper's own language. Confirmed the manuscript
  does **not** mischaracterize this as "down-only" - that framing is correctly reserved for the motivating
  system's own implementation choice, labeled as illustration only.
- **Section 5.4, Schwalbach & Auret (2025):** re-derived fresh (see reference #52 above) - a precise,
  near-verbatim confirmation of "all but one of nine crisis episodes."
- **Section 2.3, Moskowitz, Ooi, & Pedersen (2012) dual reading:** confirmed the source paper genuinely
  offers both the hedger-paid risk-premium reading and the under-reaction/slow-information-diffusion
  reading (the paper's own abstract cites "sentiment theories of initial under-reaction and delayed
  over-reaction," and a footnote cites Hong & Stein 1999 for slow information diffusion specifically).

### Paper-specific standards checks

- **Section 5.2 must not call the aegis book "unlevered":** **PASS.** The text explicitly states "not the
  book's use of leverage, which it runs up to that cap," correctly distinguishing the down-only ceiling
  from a claim about leverage level.
- **Section 5.4 closing sentence must carry the "design lean" hedge consistently:** **PASS.** The final
  clause ("though the size of that monetization edge is the design lean advanced here rather than a
  settled result") is the sentence's last word and is not walked back.
- **Zero em dashes (house style):** **PASS.** The em-dash-count check against `_draft.md` returns 0.
- **Skew as classifier, never a book-level budget; risk-conditioning allowed, return/crash-forecasting
  forbidden:** held throughout, with the single exception of the Uysal & Mulvey framing issue above.

---

## Phase C: internal consistency (paper-type notes, as instructed)

**C3 (figure/table caption fidelity):** Not applicable. This is a theoretical/integrative paper with no
figures and no tables anywhere in the manuscript (confirmed by a full read of the text). There is no
Figure Package because none was ever produced, and none was claimed. Per the C3 severity map, an absent
figure package on a paper with no figures is the trace-unavailable / not-applicable path, not a FAIL.
**PASS WITH NOTES** (advisory, non-blocking).

**C4 (experiment provenance):** Not applicable. `ARS_PASSPORT_RESET` was never set for this paper; no
Material Passport pipeline was ever invoked, because this is a manually-authored integrative paper with
no original experiments. Every reference to the "aegis" allocator in Sections 5.2 and 5.3 is explicitly
and repeatedly labeled "as a labeled illustration only" and framed as "never as evidence for a claim" (see
the framing sentence that opens Section 5). This is the legacy no-passport path, equivalent to `{status:
no_experiments_declared}`. Recorded explicitly rather than silently omitted, per instructions.
**PASS WITH NOTES** (advisory, non-blocking).

**E4 (scope-conformance advisory):** `[E4-SKIPPED: no scope context]` - no RQ Brief scope was provided to
this gate.

**E5 (novelty-claim classification):** No category-2 primacy assertions ("Y was the first to...") were
found anywhere in the manuscript. The paper explicitly disclaims an estimator-novelty framing ("The
contribution is a reordering of the construction problem rather than a new estimator," Section 6). N/A,
nothing to classify.

---

## 7-mode AI-research-failure checklist (mandatory, blocking, re-run fresh at Stage 4.5)

| Mode | Status | Evidence |
|---|---|---|
| 1. Implementation bug in results | **CLEAR** | No own-computed numerical results anywhere; every quantitative figure in the paper traces to an external cited source, all checked in Phase B/E above |
| 2. Hallucinated citation | **CLEAR after in-pass correction** | Fresh verification found 7 genuine bibliographic defects (1 author-initial mashup, 1 dead DOI, 1 page-range error, 1 year/volume error, 1 dangling citation, 1 wrong-author/wrong-year mismatch, 1 wrong-author mismatch) that Stage 2.5 missed. All 7 corrected and re-verified this session; see the Edits Applied section below. No remaining fabrication of any kind - every one of the 55 cited works is a real, existing publication |
| 3. Hallucinated experimental result | **CLEAR (N/A)** | No experiments run by this paper; every empirical result is attributed to and traced to an external source |
| 4. Shortcut reliance | **CLEAR (N/A by paper type)** | No trained model or own empirical result exists to exhibit shortcut reliance |
| 5. Bug reframed as insight | **CLEAR** | Scanned for "surprisingly / unexpectedly / counterintuitively / contrary to" language; the paper's central hook (a diversified-by-count book is secretly one position) is explicitly grounded in Brown, Gregoriou & Pascalau (2012, corrected this session), not an unexplained own-result |
| 6. Methodology fabrication | **CLEAR (N/A)** | No Methods-of-runs section; the paper is a transparent literature synthesis and argument. The one reference to the motivating "aegis" system is explicitly labeled illustration only, never methods-disclosure |
| 7. Frame-lock | **CLEAR** | Ch6 explicitly scopes what is asserted vs. deferred, leaves regime-conditional risk sizing "genuinely contested rather than resolved," and names the precise conditions under which "the order of operations defended here would have to be rebuilt." No "in hindsight" / "we realized later" language found anywhere |

No mode SUSPECTED. Mode 2's history (SUSPECTED-then-resolved-in-pass) is recorded honestly rather than
rounded up to a clean CLEAR with no history, per the spirit of the mandate.

---

## Issue list (sorted by severity, reflecting state AFTER the corrections applied this session)

### SERIOUS - all resolved in this pass

| ID | # | Category | Location | Issue | Correction applied | Source |
|---|---|---|---|---|---|---|
| IL-SERIOUS-1 | 1 | Reference (A3, dangling citation) | Section 4.3, in-text (lines 359, 380); References | "Meucci (2009)" cited twice, no reference-list entry existed | Added: "Meucci, A. (2009). Managing diversification. *Risk, 22*(5), 74-79." | SSRN 1358533; risk.net; top1000funds.com PDF |
| IL-SERIOUS-2 | 2 | Reference (A2, author error) | References - Lempérière et al. (2017) | 3rd author printed "Nguyen, T.-L." (mashup with Dao's initials from the companion paper) | Corrected to "Nguyen, T.-T." | arXiv:1409.7720; RePEc; SSRN |
| IL-SERIOUS-3 | 3 | Reference (A2, DOI error) | References - Lassance & Vrins (2023) | DOI 10.1016/j.ejor.2023.02.199 does not resolve (404) | Corrected to 10.1016/j.ejor.2023.02.014. **Closes IL-MINOR-1** | ScienceDirect; RePEc/IDEAS; UCLouvain repository |
| IL-SERIOUS-4 | 4 | Reference (A2, year/volume error) | References + Section 4.4 (2 in-text instances) - Brown, Gregoriou, & Pascalau | Cited as (2011), Vol. 1; formal publication is (2012), Vol. 2 | Corrected year and volume in reference list and both in-text citations; added DOI 10.1093/rapstu/rar003 | RePEc; Wiley cross-citation; NYU Stern press release |
| IL-SERIOUS-5 | 5 | Reference (A1, author/year mismatch) | References + Section 5.5 in-text - "AQR (2020b)" | Cited as a corporate-authored 2020 AQR piece; is actually Asvanunt, Nielsen, & Villalon (2015), JOI 24(2):134-145 | Reference entry replaced with correct authors/year/venue/DOI; in-text citation updated to match | AQR's own site (dated June 1, 2015); pm-research.com; Semantic Scholar |
| IL-SERIOUS-6 | 6 | Reference (A1, author mismatch) | References - One River (2024) | Cited as "(O. Nieuwenhuizen)"; actual bylined authors are Patrick Kazley and Stacy Wang | Corrected author attribution | Direct PDF fetch of the cover page |

### MEDIUM - resolved in this pass

| ID | # | Category | Location | Issue | Correction applied | Source |
|---|---|---|---|---|---|---|
| IL-MEDIUM-1 | 1 | Reference (A2, page-number error) | References - Baltas & Salinas (2022) | Pages listed as 133-152 | Corrected to 194-219 | pm-research.com article URL; Google Scholar profile |

### MAJOR_DISTORTION - RESOLVED in round 2 (was OPEN at round 1; body prose fixed by the author and independently re-verified this session)

| ID | # | Location | Issue (as found at round 1) | Round 2 resolution |
|---|---|---|---|---|
| IL-MAJOR-1 | 1 | Section 2.2 | "Bollerslev, Tauchen, and Zhou (2009)... compensation for bearing the risk of discrete losses" misattributes a jump/tail mechanism that belongs to Bollerslev & Todorov (2011) | Author applied the proposed reword. Re-verified fresh against both primary sources (Duke RFS PDF; Kellogg jrp.pdf) - BTZ (2009) now correctly attributed only to the time-varying-uncertainty/vol-of-vol channel, jump-loss claim now rests solely on Bollerslev & Todorov (2011), and the back-reference to Section 2.1's "two-thirds of equity premium / more than half of variance risk premium" figures is itself confirmed accurate against the primary source ("fears of rare events account for roughly two-thirds of the total expected excess return"; "more than half of the historically observed variance risk premium is directly attributable to disaster risk") and does not double-count. **CLEAN.** |
| IL-MAJOR-2 | 2 | Section 5.5 | Uysal & Mulvey (2021) is grouped with two purely risk-conditioning citations under a claim that none of the three forecast "return or... a crash," but Uysal & Mulvey's own mechanism explicitly forecasts a recession/contraction probability | Author rejected dropping the citation (evidence-suppression) and instead sorted the three studies explicitly by what each conditions on, conceding Uysal & Mulvey falls on the far side of the paper's own line. Re-verified fresh against all three primary sources: Fleming-Kirby-Ostdiek's own text states weights "ignore any time variation in expected returns" (near-verbatim match); Costa & Kwon's regime-switching ERC portfolio is confirmed covariance-conditioned; Uysal & Mulvey's own abstract confirms the overlay is driven by a supervised recession/contraction-probability estimate. No contradiction found with Section 5.3, the leverage-effect paragraph (5.5, immediately following), or the Ch6 limits paragraph, which already says regime-conditional risk sizing is "left genuinely contested rather than resolved." **CLEAN.** |

### MINOR (recommended, non-blocking)

| ID | # | Category | Location | Issue | Suggestion |
|---|---|---|---|---|---|
| IL-MINOR-1 (was open, now CLOSED) | 1 | Reference | Lassance & Vrins (2023) | Previously described as "volume/pages pending" | Volume/pages were always correct; the DOI was the actual defect and is now fixed (see IL-SERIOUS-3). Confirmed closed |
| IL-MINOR-2 | 2 | Formatting | References, whole list | Alphabetization (Dao, Feng, Trucíos out of order) + DOI backfill for ~20 canonical classics | Confirmed still tracked, deferred to Phase 7 formatting as originally planned - cosmetic, not a gate issue. Newly-confirmed DOIs available for that pass: Harvey & Siddique (2000) 10.1111/0022-1082.00247; Koijen et al. (2018) 10.1016/j.jfineco.2017.11.002; Brunnermeier et al. (2008) 10.1086/593088; Martellini & Ziemann (2010) 10.1093/rfs/hhp099; Pyun (2019) 10.1016/j.jfineco.2018.10.002; Anghel et al. (2023) 10.1561/104.00000133 |
| IL-MINOR-3 | 3 | Reference | Olszewski & Zhou (2013) | Publisher byline spells the surname "Olszweski" | Re-confirmed accurate via publisher/Mendeley metadata this session. Note remains accurate, no action needed - **closed as confirmed-accurate** |
| IL-MINOR-4 | 4 | Citation form | Section 5.3, in-text - Cederburg, O'Doherty, Wang, & Yan (2020) | In-text citation dropped the 4th author "Yan" while the reference-list entry lists all four | Fixed - in-text citation now reads "Cederburg, O'Doherty, Wang, and Yan (2020)" |
| IL-MINOR-5 (RESOLVED round 2) | 5 | Claim precision | Section 3.2, Harvey & Siddique (2023) | Magnitude range "1.5% to nearly 5%" does not match the source's own explicitly-stated range | Author restated as "roughly two to four percent in their headline estimates and considerably wider across their robustness specifications." Re-verified fresh against the primary PDF: headline reproduction range is stated verbatim as "2.1% to 3.9%" (Table 1), and out-of-sample/breakpoint robustness figures range from 1.4% to 6.3%/5.7% depending on choices - both bookends now faithful. **CLOSED.** |
| IL-MINOR-6 (RESOLVED round 2) | 6 | Citation attribution | Section 4.3, Choueifaty & Coignard (2008) | The specific squared-DR-as-independent-risk-factors property may belong more precisely to the 2012 follow-up paper | Author softened "is" to "commonly read as" and kept the 2008 citation only for the diversification ratio itself. Re-verified fresh: independent secondary sourcing (Portfolio Optimizer blog; NUIM conference paper) confirms the squared-DR-as-independent-risk-factors formalization is attributed to Choueifaty, Froidure, & Reynier's 2011 follow-up ("Properties of the Most Diversified Portfolio"), not stated in the 2008 paper itself, which only defines the ratio. The softened wording no longer over-asserts. **CLOSED.** |
| IL-MINOR-7 | 7 | Reference completeness | Uysal & Mulvey (2021) | Reference entry omits volume/issue/pages/DOI (JFDS 3(2), 87-108, DOI 10.3905/jfds.2021.1.057) | Deferred to Phase 7 formatting alongside IL-MINOR-2 |

---

## Edits I applied this session (all confined to the reference list, per the editing boundary)

1. `Meucci, A. (2009). Managing diversification. *Risk, 22*(5), 74-79.` - **added** (new entry, closes a dangling citation).
2. `AQR. (2020b)...` - **replaced** with `Asvanunt, A., Nielsen, L. N., & Villalon, D. (2015)...`; matching in-text citation (Section 5.5) updated from "(AQR, 2020b)" to "(Asvanunt, Nielsen, & Villalon, 2015)".
3. Baltas & Salinas (2022) - pages `133-152` -> `194-219`.
4. Brown, Gregoriou, & Pascalau - year `2011` -> `2012`, volume `1` -> `2`, DOI added; both in-text citations (Section 4.4) updated to `(2012)`.
5. Lassance & Vrins (2023) - DOI `10.1016/j.ejor.2023.02.199` -> `10.1016/j.ejor.2023.02.014`; removed the now-resolved "volume/pages pending" note.
6. Lempérière et al. (2017) - `Nguyen, T.-L.` -> `Nguyen, T.-T.`.
7. One River (2024) - `(O. Nieuwenhuizen)` -> `(P. Kazley & S. Wang)`.
8. Cederburg, O'Doherty, & Wang (2020) in-text citation (Section 5.3) -> `Cederburg, O'Doherty, Wang, and Yan (2020)` (matching the reference list, which was already complete).

Every fix above was re-verified with a fresh lookup **after** applying it (confirmed via grep against the
saved file - see the audit trail rows in the Phase A table).

**Zero body-prose claim-fidelity edits were made.** The two MAJOR_DISTORTION items above are reported with
quoted text and a proposed reword each, for the author to apply as an authorial judgment call, per the
editing boundary in the dispatch brief.

---

## Tool-limitation disclaimer

Phase D (originality) used heuristic web search (WebSearch + Exa) for a 15-paragraph spot check spanning
all 6 chapters and 100% of the revision-touched paragraphs (>=50%+ coverage target met). This is not
Turnitin/iThenticate and cannot certify zero plagiarism; it is a preliminary screen. Several primary
sources (AQR white papers, One River PDF, Capital Fund Management PDF) were retrieved as PDFs whose raw
text extraction was partially binary/unreadable via WebFetch in a few cases; where this happened, I
either read the file directly with the PDF-capable Read tool (successful for the One River byline) or
cross-confirmed via multiple independent secondary sources converging on the same wording (noted
per-reference in the audit trail above), rather than passing an unconfirmed claim through as VERIFIED.
Two claims (Feng 2026's exact wording; and one secondary attempt at Schwalbach & Auret before I found
the primary quote directly) were paywalled on first attempt; Feng (2026) remains UNVERIFIABLE_ACCESS
(non-blocking), while Schwalbach & Auret (2025) was successfully resolved to VERIFIED via a second,
successful primary-source fetch.

---

## Verification audit trail (summary)

- **Verification date:** 2026-07-24.
- **Method:** Live web search and page fetch this session (WebSearch, `mcp__exa__web_search_exa`,
  `mcp__exa__web_fetch_exa`, and direct PDF reads via the Read tool) for every one of the 55 cited works
  and every claim-bearing sentence attached to them. No verdict in this report rests on model memory.
- **Division of labor:** four parallel sub-agents performed the initial fresh Phase A/B pass on Sections
  2, 3, 4, and 5 respectively (each with its own recorded search-query -> result-URL -> confirmed-fields
  trail, reproduced in the Phase A table above); I then independently re-verified every finding that
  would result in an edit to the file or a MAJOR_DISTORTION classification, via my own separate live
  searches and fetches (documented inline above - the Lempérière initials, the BTZ 2009 model structure,
  the Lassance-Vrins and Baltas-Salinas bibliographic fields, the Brown-Gregoriou-Pascalau year/volume,
  the Meucci formula, the Asvanunt et al. paper, the One River byline via direct PDF read, and the
  Schwalbach & Auret crisis-episode figure via direct primary-source fetch), before applying any edit or
  finalizing any severity call.
- **Originality spot-check:** 15 characteristic-sentence WebSearch queries, one per sampled paragraph,
  covering all 7 revision-touched paragraphs (Sections 2.3, 3.5, 4.3, 4.4, 5.4, 5.5, Ch6) at 100% plus an
  additional 8-paragraph sample drawn from every other section, for >=50% total paragraph coverage. Zero
  close-match or verbatim hits.
- **E6 baseline:** a genuine pre-revision draft was recovered via `git show 5898886e:.../\_draft.md`
  (757 lines, predating Stage 3 review) and diffed in full against the current 804-line draft; every
  substantive addition traced to a specific roadmap item from `_revision.md` / `_rereview.md`.

---

## Round 2: targeted re-verification (corrected passages only) - 2026-07-24

Per the gate's correction process ("after corrections complete, re-verify only the corrected items"),
Phase A and the full Phase B/E sweep from round 1 stand unchanged and were **not** re-run. This section
covers only the four passages the author fixed in response to round 1 (`_revision.md`, "Stage 4.5
final-integrity corrections (round 2 body fixes)": MD-1 through MD-4), plus the cross-cutting checks the
correction request asked for. Every source below was re-fetched live this session; none of this rests on
the round-1 findings being assumed still valid.

### MD-1 (Section 2.2) - CLEAN

Current text: "Carr and Wu (2009) document a large and systematically negative variance risk premium
across equity indices, and Bollerslev, Tauchen, and Zhou (2009) show that the same premium forecasts
returns, a predictability their equilibrium model traces to time-varying uncertainty about future
volatility. That the compensation is in large part specifically for discrete, jump-driven losses is the
separate finding of Bollerslev and Todorov (2011), recovered from option prices in Section 2.1."

- Re-fetched Bollerslev, Tauchen, & Zhou (2009) (Duke RFS PDF + Oxford Academic + SSRN + RePEc, four
  independent sources). Confirmed: the paper is built on "a stylized self-contained general equilibrium
  model incorporating the effects of time-varying economic uncertainty," an extension of Bansal-Yaron
  long-run risk with "stochastically time-varying volatility-of-volatility," and explicitly states the
  variance risk premium's return-forecasting power is attributable to "the factor associated with the
  volatility of consumption growth volatility." No jump/discrete-loss process anywhere in the model. The
  sentence now attributes to BTZ (2009) exactly this and nothing more. **Faithful.**
- Re-fetched Bollerslev & Todorov (2011) (Kellogg jrp.pdf + Wiley + TSE-FR + RePEc). Confirmed the jump-loss
  mechanism is entirely theirs: "the compensation for rare events accounts for a large fraction of the
  average equity and variance risk premia," decomposed via an "Investor Fears index." The sentence's
  attribution is now exclusive to this paper. **Faithful.**
- Back-reference check (the specific ask): Section 2.1 (lines 124-127) states Bollerslev & Todorov (2011)
  show "the fear of discrete crashes accounts for roughly two-thirds of the equity premium and more than
  half of the variance risk premium." Re-verified against the same jrp.pdf primary text: "the median of
  the estimated equity risk premia due to rare events equals 5.2%... compared to the prototypical estimate
  of 8%... our results imply that fears of rare events account for roughly two-thirds of the total expected
  excess return," and separately, "on average more than half of the historically observed variance risk
  premium is directly attributable to disaster risk." Both figures are stated near-verbatim in the primary
  source. The 2.2 sentence's back-reference to 2.1 is therefore accurate, and because 2.2 only points to
  where the jump-decomposition finding was "recovered from option prices" without restating the specific
  percentages, there is no double-counting and no contradiction between the two sections. **Clean.**

### MD-2 (Section 5.5) - CLEAN

Current text sorts three studies: "Fleming, Kirby, and Ostdiek (2001) condition on volatility alone, and
their weights ignore any time variation in expected returns. Costa and Kwon (2019) condition on a
regime's covariance and end in a risk-parity allocation. Uysal and Mulvey (2021) go further, driving
their overlay from a supervised estimate of the probability of an upcoming recession or market
contraction, which is a forecast of the crash and therefore falls on the far side of the line drawn
here. We read that study as evidence that regime-conditional allocation can beat static allocation, not
as support for the risk-conditioning distinction itself, and the construction proposed here does not
adopt its forecasting layer."

- Fleming, Kirby, & Ostdiek (2001), re-fetched (Rice University PDF + Wiley + RePEc + SSRN): primary text
  states verbatim, "Because the portfolio weights in this strategy ignore any time variation in expected
  returns, our methodology for measuring the value of volatility timing should yield conservative
  results." This is a near-exact match to the manuscript's characterization. **Faithful.**
- Costa & Kwon (2019), re-fetched (Taylor & Francis DOI page + ResearchGate PDF): the model is a "Markov
  regime-switching factor model of returns" feeding a regime-switching covariance matrix into an ERC/risk
  parity optimization, with the paper's own conclusion that "a regime-switching risk parity portfolio can
  consistently outperform its nominal counterpart." Confirmed covariance-conditioned, ending in a
  risk-parity allocation, exactly as stated. **Faithful.**
- Uysal & Mulvey (2021), re-fetched (JFDS DOI page + Princeton repository + Semantic Scholar): abstract
  confirms "supervised learning algorithms... to estimate the probability of an upcoming recession or a
  stock market contraction," with "probability estimates... linked to a dynamic investment overlay
  strategy" that "improves risk-adjusted returns... over nominal risk parity." This is exactly a
  recession/contraction-probability forecast driving the overlay, matching the manuscript's description
  precisely, including the concession that it "falls on the far side of the line" and that its
  forecasting layer is "not adopted." **Faithful.**
- Cross-reference check (the specific ask): grepped the full draft for every "Uysal"/"Mulvey" occurrence -
  only the reference-list entry and this one paragraph (lines 526-538). Section 5.3 (lines 467-487) does
  not mention Uysal & Mulvey and makes a separate, self-contained argument about net-convexity by
  construction (Cederburg et al. 2020; Feng 2026) with no dependency on this citation. The leverage-effect
  paragraph immediately follows in the same subsection (lines 539-550) and reinforces the same
  risk-conditioning-vs-return-timing distinction without leaning on Uysal & Mulvey specifically. The Ch6
  limits paragraph (lines 587-589) already states "Regime-conditional risk sizing is left genuinely
  contested rather than resolved," which is consistent with, not contradicted by, the new concession. **No
  contradiction found anywhere else in the manuscript.**

### MD-3 (Section 3.2) - CLEAN

Current text: "...its estimated magnitude swings across a wide range, from roughly two to four percent in
their headline estimates and considerably wider across their robustness specifications depending on
research choices..."

- Harvey & Siddique (2023), re-fetched in full (Duke PDF + Critical Finance Review DOI page + ivo-welch.info
  mirror). Table 1 ("Reproducing Realized Skewness Premium and Robustness") states verbatim: "The table
  shows considerable variation - from 2.1% to 3.9% - in the premium." This is the paper's own headline
  reproduction range, and "roughly two to four percent" is a faithful rounding of it. Separately, the
  out-of-sample/breakpoint robustness analysis reports premiums as low as 1.4% (first out-of-sample
  subperiod) and as high as 6.3% (10/90 breakpoint, equal-weighted) / 5.7% (10/90, first subperiod,
  value-weighted), confirming "considerably wider across their robustness specifications depending on
  research choices." **Faithful, both bookends confirmed from the primary source.**

### MD-4 (Section 4.3) - CLEAN

Current text: "...Choueifaty and Coignard (2008), whose diversification-ratio metric underpins a fund
marketed by the first author's firm TOBAM, give the closely related diversification ratio, whose square
is commonly read as the number of independent risk factors in the book."

- Choueifaty & Coignard (2008), re-fetched (tobam.fr-hosted PDF + pm-research.com + SSRN): confirmed the
  2008 paper defines and originates the diversification ratio itself ("we define the diversification
  ratio of any portfolio P... as the following..."), which the sentence still attributes to them with
  certainty. **Faithful for the ratio itself.**
- The squared-DR-as-independent-risk-factors reading, re-checked against two independent secondary
  sources (a NUIM/IEEE conference paper's citation list, and a 2023 Portfolio Optimizer blog post
  specifically tracing the claim's provenance): both attribute the "DR² = effective number of independent
  risk factors" interpretation to Choueifaty, Froidure, & Reynier's 2011 follow-up paper ("Properties of
  the Most Diversified Portfolio," *Journal of Investment Strategies*), not to the 2008 original. The
  manuscript's "commonly read as" hedge accurately reflects that this is a secondary-literature reading
  rather than a claim the 2008 paper itself makes, without inventing a new reference this late in the
  pipeline. **Faithful; no over-assertion.**

### Cross-cutting checks requested alongside MD-1 through MD-4

- **Em-dash count:** the em-dash-count check against `_draft.md` returns **0**. House style intact after
  the round-2 edits.
- **Meucci (2009) entry:** re-checked. Reference-list entry (line 781) reads "Meucci, A. (2009). Managing
  diversification. *Risk, 22*(5), 74-79." and both in-text citations (lines 362, 383) read "Meucci
  (2009)," consistent in author/year on both sides. **Still correctly formatted, unaffected by the round-2
  edits.**
- **No new claim-strength drift (E6 spot-check on the four round-2 passages only):** MD-1 is a pure
  re-attribution (moves a finding from one paper to the correct one; no claim is strengthened or weakened
  in aggregate, since the paper's overall position - two independent payer mechanisms - is unchanged).
  MD-2 explicitly *weakens* the paper's claim about Uysal & Mulvey (concedes it sits on the far side of the
  risk/return line, rather than asserting it as clean support) - the authorized direction for a
  correction. MD-3 replaces an inaccurate numeric range with an accurate, and if anything *wider* and more
  conservative, one - a correction toward greater honesty about estimation uncertainty, not a strengthened
  claim. MD-4 softens "is" to "commonly read as" - a hedge added, not removed. **All four moves are
  corrections or weakenings; none strengthens a claim beyond what its source supports. E6 verdict for
  round 2: CLEAR.**
- **Body word count:** author-reported 7,892 words (+5.2% vs. 7,500 target). Independently re-counted this
  session (words in the body text between the Abstract heading and the References heading, markdown
  heading lines excluded): approximately 8,010-8,140 depending on whether heading text itself is included -
  consistent with the author's figure within normal counting-methodology variance, and comfortably inside
  the +/-10% tolerance band (7,500-8,250) either way. **Within tolerance, confirmed.**

### Round 2 outcome

All four corrected passages (MD-1, MD-2, MD-3, MD-4) are independently re-verified as clean against fresh
primary-source lookups performed this session. No residual claim-fidelity issue was found in any of the
four, and no new issue was introduced by the edits. Combined with round 1's zero SERIOUS / zero MEDIUM /
zero UNVERIFIABLE (reference-list defects all corrected and re-verified in round 1), the paper now meets
the PASS WITH NOTES condition: zero SERIOUS, zero MEDIUM, zero MAJOR_DISTORTION, zero UNVERIFIABLE, with
one non-blocking UNVERIFIABLE_ACCESS (Feng 2026 exact wording, paywalled) and non-blocking MINOR
reference-formatting items already deferred to Phase 7 (IL-MINOR-2 alphabetization/DOI backfill,
IL-MINOR-7 Uysal & Mulvey reference-entry completeness).

**Final verdict: PASS WITH NOTES.**

Residual notes carried to Phase 7 (formatting only, non-blocking, unchanged from round 1):
IL-MINOR-2 (reference-list alphabetization + DOI backfill for ~20 canonical classics, with DOIs already
supplied in round 1) and IL-MINOR-7 (Uysal & Mulvey reference entry missing volume/issue/pages/DOI -
`3(2), 87-108`, DOI `10.3905/jfds.2021.1.057`, confirmed this session). The Feng (2026) UNVERIFIABLE_ACCESS
note also carries forward unchanged; the paywalled source was not re-attempted this round since it falls
outside the four corrected passages.

## Round 3: VRP-challenge edits (2.2/2.4/6) and four new references - 2026-07-24

**Scope, stated up front.** An external research sweep challenged the durability claim underlying
Sections 2.2/2.4 (the short-convexity pole's payer). A separate agent (`vrp-challenge-verify`) verified
that sweep against primary sources in [[research/budgeting-convexity/_challenge-verification|
_challenge-verification]]; the author then made scoped edits to Sections 2.2, 2.4, and 6, and added four
new references. Per this round's instruction, I re-verified **only**: the four new references (fresh,
independent Phase A - not trusting the challenge-verification report's or the author's prior lookups),
the three changed passages (Phase B/E), and a targeted consistency sweep for any place elsewhere in the
paper still asserting the categorical (unconditional) version of the persistence claim. Phase A on the
other ~55 references, Phase D, and the 7-mode checklist were **not** re-run this round; rounds 1 and 2
stand as recorded above. I read the challenge-verification report for context but did not treat its
lookups as a substitute for my own - every source below was independently fetched this session, and one
of my own fetches (the actual text of the cited Dew-Becker & Giglio working paper, read at length across
three separate fetches) surfaced a finding the challenge-verification report did not flag, described
under Section 2.4 below.

### Phase A: four new references, each independently verified

| # | Reference as it appears in `_draft.md` | Verdict | Independent lookup performed this session |
|---|---|---|---|
| 1 | Bates, D. S. (2022). Empirical option pricing models. *Annual Review of Financial Economics, 14*, 369-389. https://doi.org/10.1146/annurev-financial-111720-091255 | **VERIFIED** | DOI resolved directly to the Annual Reviews article page (vol. 14, pp. 369-389, first published as Review in Advance March 2, 2022, volume date November 2022). Cross-checked independently against RePEc/IDEAS, SSRN (abstract_id=4267976), and the NBER working-paper precursor (w29554) - all four sources agree on title, author, volume, pages, and DOI. |
| 2 | Dew-Becker, I., & Giglio, S. (2025). *The decline of the variance risk premium: Evidence from traded and synthetic options* (WP 2025-17). Federal Reserve Bank of Chicago. https://doi.org/10.21033/wp-2025-17 [flagged as not peer-reviewed] | **VERIFIED, including the "not peer-reviewed" flag** | Fetched the paper directly from the Chicago Fed (both the working-paper landing page and the full PDF, ~30,000 characters read across three fetches) and cross-checked via RePEc/IDEAS, Fed in Print, and EconBiz - all agree on title, authors, WP number, date (September 4, 2025), and DOI. The document itself states "Working papers are not edited, and all opinions are the responsibility of the author(s)," confirming the non-peer-reviewed flag. I found no evidence this specific title has since been journal-published. **Important distinction surfaced by this check:** the same two authors have a *different*, S&P-500-specific paper - "The decline of the S&P 500 variance risk premium" (Dew-Becker & Giglio, 2026) - that **is** conditionally accepted at *Critical Finance Review*. That paper is not cited in `_draft.md` and is a separate, narrower study (S&P 500 option strategies only, 1987-2025) built on the same research program. Conflating the two matters for one finding below. |
| 3 | Gârleanu, N., Pedersen, L. H., & Poteshman, A. M. (2009). Demand-based option pricing. *The Review of Financial Studies, 22*(10), 4259-4299. https://doi.org/10.1093/rfs/hhp005 | **VERIFIED** | DOI resolved directly to the RFS article. Independently cross-checked against RePEc/IDEAS, EconPapers, the original NBER working paper (w11843), SSRN, and four separately-hosted full-text PDF copies (NYU Stern, UC Berkeley/Haas, Wharton, and the NBER working-paper PDF) - all agree on 2009, vol. 22, issue 10, pp. 4259-4299, DOI hhp005. (One scraped-metadata cache mislabeled the year as 2005 - that is the NBER working-paper predecessor's year, not the journal publication's; four independent bibliographic sources confirm 2009 as the RFS publication year, and the PDF footer itself reads "The Author 2009... Advance Access publication February 25, 2009.") |
| 4 | Tomunen, T. (2026). Failure to share natural disaster risk. *The Review of Financial Studies, 39*(3), 661-701. https://doi.org/10.1093/rfs/hhaf055 | **VERIFIED** | DOI resolved directly to the RFS article (Advance Access dated 2025-08-06). The RePEc/IDEAS journal table of contents for "2026, Volume 39, Issue 3" lists this exact entry - "661-701 Failure to Share Natural Disaster Risk by Tuomas Tomunen" - confirming the definitive volume/issue/page assignment. The 2026 citation year (rather than the 2025 online-first date) matches this paper's own established house style for other online-first-then-annual-volume journal articles (Trucíos 2026, Baltussen, Martens, & van der Linden 2026, Feng 2026, Noguer i Alonso & Al-Fallouji 2026 all follow the same convention already in the reference list), so this is not a new inconsistency. |

All four new references: **VERIFIED, 0 defects.**

### Section 2.2 - new material (inelastic demand necessary but not sufficient; Gârleanu, Pedersen, & Poteshman)

**CLEAN.** The added passage states two things and attributes both to GPP (2009): (a) option prices move
with end-user net demand because market makers cannot hedge perfectly and must be paid to absorb the
imbalance; (b) index options, where end users are net buyers, carry the premium while single-stock
options, where end users are net suppliers, do not.

Both are confirmed verbatim in GPP's own text, read independently across four hosted copies of the paper
(NYU Stern, Berkeley, Wharton, NBER):

- On (a): "even intermediaries cannot hedge options perfectly - that is, even they face incomplete
  markets... In light of these facts, we consider how options are priced by competitive risk-averse
  dealers who cannot hedge perfectly... dealers face significant unhedgeable risk and are compensated for
  bearing it."
- On (b): "We are the first to document that end-users have a net long position in S&P 500 index options
  with large net positions in out-of-the-money (OTM) puts... Since options are in zero net supply, this
  implies that dealers are short index options" and "index options are expensive (i.e. have a large risk
  premium)... end users are net buyers of index options," contrasted with "end-users are net short
  single-stock options - not long, as in the case of index options" and "in the equity option market,
  unlike the index-option market, end users are net suppliers of options... single-stock options appear
  cheaper."

The manuscript's framing - "inelastic demand is necessary, however, and not sufficient" because the
premium also "depends on the capacity of the side selling protection" - is a faithful gloss on GPP's model
logic: their entire pricing effect is generated by the dealer's *limited* capacity to hedge; a demand
imbalance facing dealers who could hedge perfectly would carry no price effect at all. No distortion
found.

### Section 2.4 - new third-decay-mode paragraphs

**(a) SPX VRP "earned approximately zero since around 2010," dated to the dealer-net-index-gamma flip.**
**VERIFIED**, against the actually-cited WP 2025-17 itself (not the sibling paper): "there is a break in
the returns somewhere around 2010. In the period since 2010, in fact, the alphas of the traded options
have converged to zero" and, on the gamma mechanism specifically, "We show that the net S&P 500 gamma
exposure of dealers and market makers for Cboe options shifted from being consistently negative to being
zero or positive following the financial crisis." Both figures are in the cited paper's own text, tied to
the same post-crisis timing the manuscript describes.

**(b) Tomunen: premium proportional to intermediary capital constraint; post-crisis fall from
institutional inflows; muted response to 2017 losses.** **VERIFIED**, independently. Tomunen's own
working-paper draft (ASU seminar-paper version of the same study): "I also find that the premium has
decreased significantly after the financial crisis and seems to have become less responsive to the
occurrence of disasters," and "this decrease in premium is associated with a gradual increase in
available capital for the specialist funds... a gradual but large inflow of new institutional capital
into the specialist funds." The manuscript's specific "2017" detail I could not re-find verbatim in the
sources I fetched this session, but the underlying mechanism is independently corroborated by contemporary
market reporting on the actual 2017 hurricane season: despite a record ~$100-136B insured-loss year,
cat-bond/ILS capital was quickly replenished and rate increases were muted ("the availability of capital
has not diminished, despite the estimated $136 billion of insurance industry losses suffered in 2017...
Continued supply of capital has helped curtail widespread increases in risk-adjusted rates" - Willis Re,
via Artemis.bm, Jan. 2018). This is independent corroboration of the mechanism, not a direct quote of
Tomunen's own "2017" sentence, so I treat this specific sub-clause as supported rather than re-verified
word-for-word.

**(c) Most important caution: jump risk lives in the wedge between traded and synthetic returns, not in
the synthetic leg's alpha, so the century-long zero-alpha result dates a compression rather than
disproving a jump premium.** **CLEAN, structurally confirmed.** I independently read WP 2025-17's own
theoretical section (Section 2, "Interpreting synthetic option returns"): the paper states three
conditions required for the synthetic leg's alpha to cleanly measure risk preferences, the third being
that the *unspanned* part of the synthetic return - which is exactly where a path-dependent, jump-driven
component would live - "not be priced," and flags its own Section 3.4 as the place that tests what that
unspanned component correlates with. This confirms structurally that the paper's own framework treats
jump-risk pricing as a question about the *unspanned/wedge* component, not about the synthetic leg's
headline alpha - precisely the distinction the manuscript's caution draws. I did not re-fetch the
specific "hedge different states" footnote quoted in `_challenge-verification.md` word-for-word this
session, so that exact phrasing rests on the prior agent's lookup rather than a fresh one of mine, but the
structural reading independently confirms the same conclusion from the paper's own stated methodology.
This is the one sub-item in this round where I did not fully repeat the other agent's lookup from
scratch; I flag that rather than silently presenting it as identically re-verified.

**(d) Bates (2022) genuinely dates the break to 2017 on separate methodology.** **VERIFIED**, found
independently (not via the challenge-verification report): Dew-Becker & Giglio's own S&P-500-specific
paper states directly, "Bates (2022) also finds a decline in premia, but dates it somewhat later than us
- 2017 instead of 2012," and separately describes Bates's method as using "a weekly instead of daily
delta hedge... data through 2020."

**New finding (MINOR_DISTORTION, not previously flagged): a break-year figure is attributed to the wrong
paper within the same citation.** The manuscript reads: "The break date is also unsettled, estimated at
2012 in their own statistical work and placed at 2017 by Bates (2022) on separate methodology." "Their own
statistical work" reads naturally as the cited Dew-Becker and Giglio (2025) reference - the same one cited
two sentences earlier in the same paragraph for "approximately zero since around 2010." But I read the
actually-cited WP 2025-17 at length (roughly 30,000 characters, across Sections 1-3.2) and it consistently
gives its own break estimate as "around 2010," never 2012. The precise "August 2012" figure instead comes
from the *different*, uncited sibling paper identified in the Phase A table above (Dew-Becker & Giglio,
2026, "The decline of the S&P 500 variance risk premium," conditionally accepted *Critical Finance
Review*), which states explicitly: "the analysis takes August 2012 as its baseline break date, based on
the timing of a shift of the net holdings of dealers." That paper is not in `_draft.md`'s reference list.

So within this one paragraph, the same in-text citation is used for two different break-year figures
(2010 and 2012), and the 2012 figure actually belongs to a paper the manuscript does not cite. The
paragraph's overall point - that the precise break date is unsettled across sources and only the
direction is load-bearing - survives regardless, and I do not believe this rises to MAJOR_DISTORTION,
since it does not change what any claim asserts about the world, only which of two closely related papers
a specific number should be attributed to. But it is a genuine citation-fidelity slip on newly-added
content, not a pre-existing issue, so I am not softening it away. **Proposed faithful fix (author's call,
not applied by me): replace "estimated at 2012" with "estimated at around 2010," matching the actually-
cited paper's own language and removing the internal inconsistency with the earlier sentence in the same
paragraph.** No new reference addition is required either way.

### Section 6 - rewritten reflexivity paragraph and "structural rather than informational" fix

**CLEAN.** The reflexivity paragraph now concedes supply-side erosion directly: "The short pole's premium
is rent on constrained risk-bearing capacity, and capacity responds to capital rather than to publication,
so anything drawing capital toward selling protection compresses the premium whether or not a paper is
written... the answer is not to claim immunity but to state the condition and watch it." This is a
faithful restatement of the capacity-based mechanism established in the revised Section 2.4, and directly
answers the reflexivity question rather than dodging it.

The opening-paragraph fix - "backed by a payer whose incentive rests on constraint rather than on
information" (replacing the old "structural rather than informational") - resolves exactly the issue it
was meant to: the old binary asserted an either/or that Section 2.4 now explicitly declares incomplete (a
third, capital-driven decay mode). The new phrasing names the mechanism (constraint) rather than
asserting a category (structural) that the rest of the paper no longer treats as sufficient on its own.
Clean.

### Consistency sweep: any remaining categorical-persistence claim elsewhere?

I checked the two locations flagged as highest-risk (Section 4's Floor income-role assignment and Section
5's construction sections) plus the Introduction's two preview sentences that describe Section 2's payers
as "structural," since those predate this round's edit and could plausibly go stale.

**Found: no stale dependency.** Two things kept this from becoming a problem:

1. Section 2.2's own load-bearing sentence for the Floor income-role assignment already reads, before
   this round's edit: the roster treats the short pole "as an income source with a stated condition rather
   than a temporary edge" - language that was already conditional going into this round, so Section 2.4's
   new capacity-based development is a refinement of an already-qualified claim, not a contradiction of an
   unqualified one. Section 4.1 (the Floor) itself makes no persistence claim of its own beyond describing
   the sleeve's design; it inherits the (already-conditional) claim from Section 2 rather than restating a
   stronger version.
2. The Introduction's two preview sentences ("each of its poles is anchored by a payer whose incentive to
   keep paying is structural," lines 88 and 99) describe the *payer's* (the insurance buyer's / hedger's)
   motive for demanding protection, which is a different claim from how much premium the *seller* realizes
   once specialist capacity is accounted for. Section 2.4's new conditional framing narrows the latter
   (premium size, capacity-dependent), not the former (demand persistence, which nothing in this round's
   edits disputes). Read this way the preview sentences are not stale; they describe a claim the revision
   did not touch.

Section 5 (5.3 net-convexity-by-construction, 5.4 the tail budget, 5.5 risk-conditioning) makes no
appeal to short-pole premium permanence at all - 5.3 and 5.4 argue from market-timing-fails-out-of-sample
evidence and from the Israelov/monetization literature, neither of which depends on the short pole's
premium being unconditional. No stale reference found there either.

### Reference-list mechanical check (new item, folded into the existing Phase 7 tracking rather than fixed here)

The newly-inserted Dew-Becker & Giglio (2025) entry is alphabetically out of place: it currently sits
between "De Long, J. B., Shleifer, A., Summers, L. H., & Waldmann, R. J. (1990)" and "DeMiguel, V.,
Garlappi, L., & Uppal, R. (2009)," but letter-by-letter APA ordering (De Long < DeMiguel < Dew-Becker,
comparing the third character L < M < w) places it *after* DeMiguel, not before. This is a mechanical,
bibliographic-metadata issue I am authorized to fix directly, but the paper has an established, explicit
precedent (recorded in `_revision.md`'s round-1 WONTFIX table) of batching reference-list
re-alphabetization into a single Phase 7 formatting pass rather than fixing entries piecemeal at each
gate, and this round's instruction was to keep the footprint to the changed passages and new references
only. I am therefore reporting rather than fixing it: **add "Dew-Becker, I., & Giglio, S. (2025)" to the
existing IL-MINOR-2 reference-list-alphabetization item**, alongside the already-tracked Dao, Feng, and
Trucíos entries.

### Word count (independently re-counted, not accepted on the author's figure alone)

Author-reported: 8,502 words (+13.4% vs. the 7,500 target), concentrated in Chapter 2 (+34%), flagged by
the author as a known, deliberate consequence of this round with a decision pending. Independently
recounted this session (words in the body text between the Introduction and References headings): 8,499
words including heading text, 8,337 excluding it - materially consistent with the author's figure within
normal counting-methodology variance. **Confirmed: +13.4% is a real overage, genuinely outside the +/-10%
tolerance band.** This is a scope/formatting matter rather than a claim-fidelity or citation-verification
finding, so it does not affect this gate's verdict, but per this gate's practice of not silently dropping
a tolerance breach, I am recording it as a flagged, non-blocking item for whoever makes the pending
length decision.

### Round 3 outcome

- **Phase A (4 new references): 4/4 VERIFIED, 0 defects.**
- **Section 2.2: CLEAN.**
- **Section 2.4: CLEAN except one new, non-blocking MINOR_DISTORTION** - the "2012" break-year figure
  attributed to "their own statistical work" belongs to a different, uncited sibling paper; the actually-
  cited paper's own figure is "around 2010." Proposed fix given above; not applied by me.
- **Section 6: CLEAN.**
- **Consistency sweep: no stale categorical-persistence claim found** in Section 4, Section 5, or the
  Introduction's preview sentences.
- **New MINOR (non-blocking, folded into IL-MINOR-2):** Dew-Becker & Giglio (2025) reference-list entry
  is alphabetically misplaced.
- **Word count: independently confirmed at +13.4%, outside tolerance**, author-flagged as pending and
  non-blocking for this gate.

Per the Verdict Criteria table, one new MINOR_DISTORTION does not change the gate's status: PASS WITH
NOTES requires zero SERIOUS, zero MEDIUM, zero MAJOR_DISTORTION, and zero UNVERIFIABLE, which remains true
after this round (the new finding is MINOR_DISTORTION, not MAJOR_DISTORTION), and the paper continues to
carry MINOR-tier and UNVERIFIABLE_ACCESS items, which is exactly the PASS-WITH-NOTES condition rather than
a bare PASS.

**Final verdict: PASS WITH NOTES (unchanged from round 2).**

Residual notes carried to Phase 7 (all non-blocking):

- **New, this round:** the "2012 vs. 2010" break-year MINOR_DISTORTION in Section 2.4 (fix proposed
  above, author's call); the Dew-Becker & Giglio reference-list alphabetization slip (folded into
  IL-MINOR-2); the word-count overage now at +13.4% (author-flagged, decision pending, not mine to
  resolve).
- **Carried forward unchanged:** IL-MINOR-2 (reference-list alphabetization + DOI backfill for ~20
  canonical classics) and the Feng (2026) UNVERIFIABLE_ACCESS note (paywalled; not re-attempted this round
  since it falls outside the three changed passages). IL-MINOR-7 (Uysal & Mulvey reference completeness)
  is now closed per team-lead's confirmation that the volume/issue/pages/DOI were banked into `_draft.md`.
