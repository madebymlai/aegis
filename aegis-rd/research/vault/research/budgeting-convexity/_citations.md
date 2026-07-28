---
title: "Budgeting Convexity - Phase 5a citation audit"
paper: "Budgeting Convexity"
status: Phase 5a citation compliance - report
tags:
  - phase5a
  - citations
---

# Phase 5a citation audit report

Citation-compliance pass on the [[research/budgeting-convexity/_draft|draft]]. Verification level:
**strict**. Format: APA 7th, in-text `(Author, Year)` / `Author (Year)`, consistent throughout.

## Method and coverage

Highest-risk references were verified by live web lookup (Exa) on 2026-07-24: every reference
published 2019 or later, every field previously marked pending, and every practitioner or preprint
item. Twenty of the classic, long-established references (pre-2019, top-tier journals) were carried
from the Phase 1 corpus, which was itself built by an Exa scan plus legacy-footnote re-validation;
they are not individually re-verified in this pass and are flagged below for the independent 100%
check at the Stage 2.5 integrity gate.

- **Verified via web search this pass:** 15 references (DOIs added, metadata corrected).
- **Corrections forced by verification:** 1 title, 4 claim-faithfulness edits to the draft body.
- **Fabricated citations detected:** none. Every source resolves to a real publication.
- **Citation orphans (in-text without a reference entry, or vice versa):** none found.

## Corrections applied

### Title / metadata corrections

- **Anghel, Caraiani, Roșu & Roșu (2023)** - title corrected from "Systematic Skewness: Two Decades
  Later" to **"Asset Pricing with Systematic Skewness: Two Decades Later"**; Critical Finance Review
  12(1-4), 309-354. The in-text claim (proxy "very noisy," pricing "inconclusive," HS return 2.58%
  not significant at 90%) is confirmed by the source.
- **Baltussen, Martens & van der Linden (2026)** - third author initial corrected to L. (Lodewijk);
  FAJ 82(1), 6-34; DOI added. DAR4020 and the immediate-vs-late speed-gap claim confirmed verbatim.
- **Lassance & Vrins (2023)** - venue resolved to **European Journal of Operational Research** (was
  pending); DOI added.
- **Asif, Frömmel & Mende (2022)** - author spelling corrected (Frömmel); IRFA 80, 102045; DOI added.
- **Noguer i Alonso & Al-Fallouji (2026)** - co-author corrected to Al-Fallouji; arXiv:2607.00883;
  full subtitle added. The immediate-repricing-vs-late-signal separation is confirmed verbatim.
- **Le, Kourtis & Markellos (2023)**, **Feng (2026)**, **Trucíos (2026)** - full author lists
  resolved (were pending); DOIs added.
- DOIs and page ranges added for Harvey & Siddique (2023), Baltas & Salinas (2022), Baltussen,
  Swinkels & van Vliet (2021), Bongaerts, Kang & van Dijk (2020), Cederburg, O'Doherty, Wang & Yan
  (2020), Costa & Kwon (2019).

### Claim-faithfulness corrections to the draft body (L3 checks)

Verification read the sources closely enough to catch three places where the draft asserted more than
the cited work supports. These are the most important fixes in the pass, because a real citation
attached to a claim it does not make is worse than a missing one.

1. **Lassance & Vrins (2023), Section 3.4.** The draft said their approach shows "no reliable
   out-of-sample benefit" to moving off the mean-variance frontier. The paper actually shows the
   opposite in part: its MEKL method *does* improve higher moments out of sample, as a compromise that
   accepts higher variance. Rewrote 3.4 to say higher moments cannot be optimized on *directly with
   stability*, which the source and Martellini-Ziemann support, rather than that no benefit exists.
2. **Bongaerts, Kang & van Dijk (2020), Section 5.2.** The draft attributed "down-only volatility
   targeting" to the paper. The paper's conditional strategy actually de-levers in high-volatility
   states and *levers up* in low-volatility extremes, with low turnover. Rewrote 5.2 to attribute to
   the source what it shows (conditional beats conventional continuous targeting; keep leverage low),
   and to frame the strictly down-only ceiling as the motivating system's constrained-book
   implementation choice, labeled illustration only.
3. **Schwalbach & Auret (2025), Section 5.4.** The draft said the overlay improved outcomes "across
   all nine crises." The paper reports outperformance in **all but one** of nine crisis episodes.
   Corrected.

A fourth edit sharpened the Asif et al. (2022) sentence to the paper's specific finding (exposure cut
to the crisis market in under fifteen days), replacing a looser paraphrase.

## References carried from the Phase 1 corpus, pending Stage 2.5 independent verification

The following long-established references were not re-verified by web lookup in this pass and carry no
DOI yet. They are standard, top-tier, and high-confidence, but strict mode requires the Stage 2.5
integrity gate to verify all of them independently and backfill DOIs: Lempeeriere et al. (2017),
Bouchaud et al. (2017), Lettau-Maggiori-Weber (2014), Bollerslev-Todorov (2011), Carr-Wu (2009),
Bollerslev-Tauchen-Zhou (2009), Fung-Hsieh (2001), CFM (2018), Ilmanen (2012), Shleifer-Vishny (1997),
De Long et al. (1990), Gromb-Vayanos (2010), McLean-Pontiff (2016), Brunnermeier-Nagel-Pedersen
(2008), Moskowitz-Ooi-Pedersen (2012), Kang-Rouwenhorst-Tang (2020), Harvey-Siddique (2000), Koijen et
al. (2018), Martellini-Ziemann (2010), DeMiguel-Garlappi-Uppal (2009), Maillard-Roncalli-Teiletche
(2010), Lopez de Prado (2016), Grinold (1989), Meucci (2009), Choueifaty-Coignard (2008),
Brown-Gregoriou-Pascalau (2011), Bhansali et al. (2015), Hurst-Ooi-Pedersen (2017), Olszewski-Zhou
(2013), Carli-Deguest-Martellini (2014), Israelov-Nielsen (2015), Israelov (2019), Fleming-Kirby-Ostdiek
(2001), and the AQR, One River, Man Group, and LongTail Alpha practitioner pieces.

## Conflict-of-interest disclosures carried in-text

CFM (Lempeeriere, Bouchaud, CFM 2018), AQR (Ilmanen, Moskowitz-Ooi-Pedersen, Hurst-Ooi-Pedersen,
Put-vs-Trend, Israelov, Koijen), and PIMCO (Bhansali) are flagged at first use in the draft. The
load-bearing steps rest on no-COI anchors (Lettau-Maggiori-Weber, Bollerslev-Todorov, Shleifer-Vishny,
DeMiguel, Brown et al., Trucíos).

## Status

Citation form is consistent and no orphans or fabrications were found. 15 references are web-verified
with DOIs; the balance is queued for the Stage 2.5 integrity gate's independent 100% verification,
which is the pipeline's designated place for it.
