---
title: "Budgeting Convexity - outline and evidence map"
paper: "Budgeting Convexity"
status: Phase 2 (architecture) - outline drafted, awaiting user approval
tags:
  - outline
---

# Budgeting Convexity - outline and evidence map (Phase 2)

Structure Architect deliverable. Inputs: [[research/budgeting-convexity/_plan|chapter plan]]
(locked spine, INSIGHTs, word budgets) and [[research/budgeting-convexity/_sources|source
corpus]] (annotated, tagged). This is the blueprint the draft writer follows; it is not a draft.

> [!warning] Checkpoint (Phase 2 -> 3)
> Per the skill's IRON RULE, drafting does not begin until this outline is **approved**. Request
> restructuring here, not after the draft exists.

## Structure pattern: Theoretical Analysis (Pattern 3)

A framework paper. It builds one construct - diversification as an order of operations on the
convexity axis - by moving from axis (Ch2) through a pivot that rejects the naive lever (Ch3) to
the framework (Ch4) and its realization (Ch5). Not IMRaD: there is no original dataset here; the
per-role empirical proofs live in the three seat papers. Our own runs, ADRs, and allocator are
cited only as the **estimate tier** (labeled in-sample illustration), never as discovery, per
[[research/README|research/README]].

## The argument as a sub-question chain

Plan mode produced no formal RQ Brief, so the spine's links stand in as sub-questions (SQ). Each
chapter answers exactly one; every outline section below names the SQ it serves.

- **SQ1** (Ch1, framing) - Does a book's survival turn on the *count* of mechanisms it harvests, or
  on the *order* in which it spans failure modes?
- **SQ2** (Ch2) - What governs stress co-movement, and does each pole of that axis have a payer who
  keeps paying?
- **SQ3** (Ch3, pivot) - Can the classifier that names the poles (skew) also anchor an allocation
  budget?
- **SQ4** (Ch4) - In what order must the roles be assembled so each tier fixes the failure the tier
  below cannot?
- **SQ5** (Ch5) - How is the roster realized in construction without budgeting skew or timing
  returns?
- **SQ6** (Ch6) - What does this integrative paper assert now, and what does it owe the seats?

## Overview

The paper opens on a hook that reframes the field's question (Ch1), establishes the convexity axis
and its two durably-paid poles (Ch2), then pivots on the load-bearing claim that skew classifies
those poles but cannot budget them (Ch3). With the naive lever removed, the organizing variable
becomes the economic job: Ch4 builds the tiered roster as an order of operations, each tier fixing
the failure below it. Ch5 realizes the roster - budget risk, source convexity structurally, observe
skew, size the tail as a convexity-premium budget - and scopes out live return-timing while
conceding regime-conditional *risk* sizing as a contested refinement. Ch6 states what is asserted
versus deferred to the seats.

---

## Detailed outline

### 1. Introduction (~800 words)

**Purpose.** Reframe the field's question from count to order, deliver the hook, name the gap, and
land the thesis the reader carries out of the chapter.
**Serves.** SQ1 - framing (no sub-question binding).

**Content.**
- 1.1 The hook: a mechanism-diverse book is one short-gamma position (~300)
  - Carry, macro, stat-arb, managed futures look varied; their low correlations are conditional and
    collapse in the single regime where every insurance seller is hit at once. The book that looks
    most diversified is the one most exposed. Image seeded by the axis literature (forward-ref Ch2).
- 1.2 The gap: the field counts mechanisms and treats skew as a lever (~250)
  - The literature asks "how many low-correlated premia should I harvest" and counts mechanisms;
    where it reaches for skew it balances skew as a lever rather than reading it as a classifier.
    The survival question is *which failure modes the book spans, and in what order*.
- 1.3 Thesis and roadmap (~250)
  - Thesis (verbatim from plan): diversification is an order of operations over failure modes on the
    convexity axis - budget risk across the roster, source convexity structurally, and treat skew as
    a classifier you observe, not a budget you solve. One-paragraph roadmap of Ch2-6.

**Sources.** Framing chapter; minimal citation. Forward-references Lempériere et al. (axis image)
and Brown et al. (over-diversification, paid off in Ch4). No claim here that is not discharged later.
**Transition.** The hook asserts a common axis under the labels; Ch2 must prove that axis exists and
that each pole is paid.

### 2. The convexity axis and its two poles (~1,400 words)

**Purpose.** Establish that stress co-movement is governed by the **sign of convexity** to the
common shock, not the mechanism label; name the two poles; give each a durable payer.
**Serves.** SQ2.

**Content.**
- 2.1 The axis: reward lines up with the sign of convexity, not the mechanism (~450)
  - Lempériere et al. (2017): the Sharpe cross-section lines up with negative skew, not volatility;
    trend is the clean positive-skew outlier. Bouchaud et al. (2017) extends the line OOS. Guard the
    CFM conflict by triangulating with two independent methods: Lettau-Maggiori-Weber downside-beta
    CAPM prices FX / equity / options / commodities / bonds jointly (74% vs -17% for CAPM);
    Bollerslev-Todorov isolate jump-tail fear as the price of the crash.
- 2.2 The short pole and its payer (~450)
  - Insurance-selling / short-gamma. Variance sellers earn a premium as crash compensation
    (Carr-Wu; Bollerslev-Tauchen-Zhou). Ilmanen (2012) restates cross-asset: buying insurance is
    poorly rewarded everywhere. Payer = structural, price-insensitive insurance demand.
- 2.3 The long pole and its payer (~300)
  - Trend is structurally long gamma: Fung-Hsieh lookback-straddle identity; CFM (2018) shows the
    convexity is a multi-period quantity capped by vol-scaling (flags the Ch5 tension). Payer =
    hedgers paying speculators (Moskowitz-Ooi-Pedersen); Kang-Rouwenhorst-Tang read this as an
    insurance premium at long horizons, disciplining any "pure alpha" label.
- 2.4 Why the payers stay: the durable-payer foundation (~200)
  - Shleifer-Vishny and De Long et al.: anomalies persist where arbitrage is capital-constrained and
    noise-trader risk is itself priced. Gromb-Vayanos surveys the constraint menu; McLean-Pontiff
    supplies the publication-decay guard the whole stance rests on. This is the ex-ante reason both
    payers keep paying, stated once and reused by every later persistence claim.

**Sources.** Lempériere; Bouchaud; Lettau-Maggiori-Weber; Bollerslev-Todorov; Carr-Wu;
Bollerslev-Tauchen-Zhou; Ilmanen; Fung-Hsieh; CFM 2018; Moskowitz-Ooi-Pedersen;
Kang-Rouwenhorst-Tang; Shleifer-Vishny; De Long et al.; Gromb-Vayanos; McLean-Pontiff.
**Transition.** Both poles were *identified* by the sign of skew, which invites using skew as the
allocation variable. Ch3 shows why that inference fails.

### 3. Why convexity classifies but cannot budget - the pivot (~1,200 words)

**Purpose.** The load-bearing pivot. The sign of skew is knowable ex-ante; its magnitude is not; so
skew labels a pole but cannot anchor a budget. Honor Guardrail 1 (do not overclaim).
**Serves.** SQ3.

**Content.**
- 3.1 Ex-ante: the third moment is tail-dominated (~300)
  - State the rationale *before* the evidence. The third moment averages cubed deviations, so a few
    tail prints dominate it: high estimator variance, liable to flip on one crisis print. The *sign*
    (which tail is fat) is identifiable; the *magnitude* is not. Budgeting needs the magnitude;
    classifying needs only the sign. A statistical property, not a finding.
- 3.2 The evidence estimates it: sign stable, magnitude swings (~350)
  - Harvey-Siddique (2000) origin of the priced classifier; Harvey-Siddique (2023, 25 yr OOS): sign
    always positive where HML / momentum flip, magnitude swings 1.4-4.7% by research choice, "very
    challenging to measure higher moments." Anghel et al. (2023): proxy "very noisy," pricing
    "inconclusive." The fragility claim from [[skewness-in-asset-returns]] (that claim only).
- 3.3 Skew is asset-class-specific, not universal (~250)
  - Koijen et al.: currency / options carry strongly negative-skewed, but equity / Treasury / credit
    carry positive-skewed, and the diversified global carry factor has negligible skew. The mechanism
    fixes the sign ex-ante: Brunnermeier-Nagel-Pedersen tie carry's negative skew to funding-liquidity
    unwinds of crowded positions, present in FX and absent where that mechanism does not apply. So
    "is this carry concave" is answered by mechanism, before any measurement.
- 3.4 You cannot budget on skew directly (~150)
  - Lassance-Vrins: no OOS benefit to moving off the mean-variance-efficient frontier;
    Martellini-Ziemann: higher-moment portfolios cannot beat minimum-variance even with robust
    comoment estimates. Higher-moment optimization exacerbates estimation risk.
- 3.5 Guardrail: skew still ranks cross-sectionally (~150)
  - Concede the real counter-evidence. Baltas-Salinas: realized skew is a pervasive *cross-sectional*
    predictor (cross-asset skew Sharpe 0.73); Le et al.: option-implied skew is forecastable and
    usable. Distinguish **book-level net-skew budgeting** (refuted) from **cross-sectional skew
    ranking / option-implied skew** (a real, tradeable signal). Never say skew is a passive label.
    Pyun on VRP-timing instability closes the section.

**Transition.** If skew classifies but cannot budget, the organizing variable is not a moment but
the economic job. Ch4 builds the roster by job.

### 4. The roster, all tiers (~1,800 words)

**Purpose.** The framework core: the order of operations, each tier fixing a failure the tier below
cannot, with the over-diversified book as the failure the order exists to avoid.
**Serves.** SQ4.

**Content.**
- 4.1 The Floor: two opposite-convexity poles, one funds, one responds (~500)
  - Convergent income engine (short pole) paired with a persistent-crisis responder (long pole).
    Carry and trend are mutually diversifying, most in the extremes (Bhansali et al.; Olszewski-Zhou
    on FX momentum+carry). Trend is positive every decade and best in low-correlation substrate
    (Hurst-Ooi-Pedersen). Its crisis alpha comes from fast de-risking, confirmed outside the CTA
    industry (Asif-Frömmel-Mende). One sleeve funds the wait; the other pays in the drawdown.
- 4.2 The Target: the tail, closing the responder's speed gap (~500)
  - Trend is late by construction (its signal must cross zero), so the persistent-crisis responder
    sleeps through the fast V-crash. The Target is immediate defense. AQR Put-vs-Trend: puts pay in
    fast crashes, trend in protracted bears, and slow drawdowns do more damage, so trend is the
    workhorse and the tail is the supplement. Baltussen DAR4020: a defensive-factor sleeve arrives
    with negative beta at onset while trend improves as dislocation persists - the two-defense
    benchmark. The speed gap is formalized analytically by Noguer i Alonso-Al Fallouji (puts reprice
    on impact; trend is late). A role, not a timer (the no-timing discipline is Ch5).
- 4.3 The Expansion: off-axis, breadth-gated, last (~450)
  - Off-axis market-neutral sleeves whose payoff is breadth, added last. Grinold's fundamental law
    (IR ~ IC * sqrt(BR), breadth = *independent* bets); Meucci's effective number of bets;
    Choueifaty-Coignard's diversification ratio. Carli-Deguest-Martellini: the effective number of
    bets predicts performance specifically in bear markets, so orthogonal breadth pays in stress.
    Baltussen-Swinkels-van Vliet supply the vetted factor basis. Gated: admitted only when it adds
    an independent bet, never for its label.
- 4.4 The failure the order avoids: over-diversification (~350)
  - Brown-Gregoriou-Pascalau: past roughly twenty funds, over-diversification *raises* left-tail
    risk and lowers returns. The mechanism-count book collapses into one short-gamma position - the
    Ch1 hook, now paid off. The order of operations is the antidote: each tier earns its slot by
    fixing a named failure, not by adding a label.

**Transition.** The roster names roles and their order; Ch5 realizes them - how to size and hold
them without budgeting skew or timing returns.

### 5. The construction (~1,600 words)

**Purpose.** Realize the roster. Budget risk (ERC/HRP plus a down-only vol ceiling); deliver
net-convexity by construction not by live solve; observe skew; size the tail as a convexity-premium
budget (where the title lives); reject live return-timing; honor Guardrail 2. Our ADR-0004 and
allocator appear only as **labeled in-sample illustration**.
**Serves.** SQ5.

**Content.**
- 5.1 Budget risk, not returns (~400)
  - DeMiguel-Garlappi-Uppal: no optimizing model consistently beats 1/N OOS, because the estimation
    window it needs exceeds what exists. So the construction budgets risk: Maillard-Roncalli-Teiletche
    ERC across sleeves; Lopez de Prado HRP for the hierarchical group seam. Honest caveat carried:
    Empirical Economics (2026) shows HRP does not reliably beat other risk-based methods or
    Ledoit-Wolf shrinkage. The claim is "budget risk, do not optimize returns," not "HRP is superior."
- 5.2 The down-only vol ceiling (~300)
  - Bongaerts-Kang-van Dijk: conditional, down-only vol targeting improves Sharpe and cuts drawdowns
    for constrained books. Down-only means de-lever, not peg - up-scaling is clamped. (ADR-0004
    amendment cited here as labeled in-sample illustration of one sound implementation, not as proof.)
- 5.3 Net-convexity by construction, not solved (~350)
  - The live net-skew solve is rejected: window-unstable, can go infeasible and halt the book.
    Instead a fixed conviction tilt plus a convexity-premium tail delivers the net-convex property,
    and skew is *observed* (a recorded measurement, never a constraint). The market evidence that
    scaled-signal convexity timing fails: Cederburg-O'Doherty-Wang (vol-managed gains are
    spanning-regression artifacts of structural instability); "When simplicity beats optimization"
    (FMPM 2026). ADR-0004's removal of the live solve is the estimate-tier illustration.
- 5.4 The tail as a convexity-premium budget - where "Budgeting Convexity" lives (~350)
  - The tail is sized as a cost budget and monetized, not held by default. Israelov-Nielsen "Still
    Not Cheap" and Israelov "Pathetic Protection": standing puts deliver worse drawdown-per-return
    than simply holding less risk, except against sudden gaps. Monetization matters: One River
    (disciplined rebalancing beats no-rebalance), Man Group (overlays reach put-like convexity at a
    positive average return), LongTail Alpha (active monetization beats passive hold). Schwalbach-Auret
    show slow-plus-fast complementarity improving all nine crises studied.
- 5.5 Reject live return-timing; the contested refinement (Guardrail 2) (~200)
  - Return / crash *timing* of protection fails OOS (AQR "Working Your Tail Off"; recap 5.3). But
    regime-conditional *risk* sizing is defensible-but-contested and lands on the permitted side of
    the risk-vs-return line (ADR-0001 amended): Costa-Kwon, Uysal-Mulvey, and
    Fleming-Kirby-Ostdiek / Andersen-Bollerslev show risk timing pays where return timing does not.
    Scope it as a refinement, never rejected, never adopted here. Role verification is stated as a
    tail-aware principle and deferred to the seats.

**Transition.** Construction realizes the roster under honest constraints; Ch6 states what is
asserted now and what is owed.

### 6. Conclusion (~700 words)

**Purpose.** Restate the contribution, state the limits honestly, hand the roles to the seats.
**Serves.** SQ6.

**Content.**
- 6.1 Contribution restated (~250)
  - Diversification is an order of operations on the convexity axis: skew classifies but does not
    budget; convexity is sourced structurally and observed, not solved; risk is the allocation lever.
- 6.2 Limits (~250)
  - This is the integrative paper. Roles are asserted and reconciled once, at roster level; the
    per-role economic proofs live in the seats, so a revision round is expected once they deepen.
    Regime-conditional risk sizing is left contested. No live OOS edge is claimed for HRP over
    inverse-vol or shrinkage.
- 6.3 Future work: the three seats (~200)
  - ② crisis-responder (Floor responder), ③ convergent-engine (Floor income), ④ v-crash-defense
    (Target tail). Expansion has no seat yet - a future fifth family, breadth-gated.

**Sources.** Synthesis; no new citations.

---

## Evidence map

Every Phase 1 source assigned to at least one section. Stance is relative to the paper's claims:
**F** foundation, **PRO** confirms, **CON** genuine counter carried on purpose, **ctx** context.
COI / type flagged. Our own articles and ADRs are listed last as the estimate tier, not external
evidence.

### Chapter 2 - axis and poles

| Source | Section | Stance | Note |
|---|---|---|---|
| Lempériere et al. (2017), *Quant. Finance* | 2.1 | F | COI (CFM) |
| Bouchaud et al. (2017), arXiv:1708.07637 | 2.1 | F | COI (CFM); preprint |
| Lettau, Maggiori & Weber (2014), *JFE* | 2.1 | F | independent method; no COI |
| Bollerslev & Todorov (2011), *JF* | 2.1 | F | independent; no COI |
| Carr & Wu (2009), *RFS* | 2.2 | F | short pole's payer |
| Bollerslev, Tauchen & Zhou (2009), *RFS* | 2.2 | F | short pole's payer |
| Ilmanen (2012), *FAJ* | 2.2 | PRO | COI (AQR) |
| Fung & Hsieh (2001), *RFS* | 2.3 | F | straddle identity |
| Capital Fund Management (2018) | 2.3 | F | COI (CFM); flags 5.x tension |
| Moskowitz, Ooi & Pedersen (2012), *JFE* | 2.3 | PRO | COI (AQR) |
| Kang, Rouwenhorst & Tang (2020), *JF* | 2.3 | ctx | disciplines "pure alpha" |
| Shleifer & Vishny (1997), *JF* | 2.4 | F | persistence foundation |
| De Long, Shleifer, Summers & Waldmann (1990), *JPE* | 2.4 | F | noise-trader risk |
| Gromb & Vayanos (2010), *ARFE* | 2.4 | ctx | constraint menu |
| McLean & Pontiff (2016), *JF* | 2.4 | F | publication-decay guard |

### Chapter 3 - the pivot

| Source | Section | Stance | Note |
|---|---|---|---|
| Harvey & Siddique (2000), *JF* | 3.2 | F | classifier's origin |
| Harvey & Siddique (2023), *CFR* | 3.1, 3.2 | PRO | sign stable, magnitude swings |
| Anghel et al. (2023), *CFR* | 3.2 | PRO/CON | proxy noisy; magnitude instability |
| Koijen, Moskowitz, Pedersen & Vrugt (2018), *JFE* | 3.3 | PRO | COI (AQR); asset-class-specific |
| Brunnermeier, Nagel & Pedersen (2008) | 3.3 | F | COI (AQR); fixes carry-skew sign |
| Lassance & Vrins (OMVE) | 3.4 | PRO | no OOS benefit off MVE |
| Martellini & Ziemann (2010), *RFS* | 3.4 | PRO | higher-moment cannot beat GMV |
| Baltas & Salinas (2022), *JPM* | 3.5 | CON | Guardrail 1: skew ranks |
| Le et al. (2023), *J. Futures Mkts* | 3.5 | CON | Guardrail 1: implied skew usable |
| Pyun (2019), *JFE* | 3.5 | ctx | VRP-timing instability |

### Chapter 4 - the roster

| Source | Section | Stance | Note |
|---|---|---|---|
| Bhansali, Davis, Dorsten & Rennison (2015), *JPM* | 4.1 | PRO | COI (PIMCO) |
| Olszewski & Zhou (2013), *JDHF* | 4.1 | PRO | momentum+carry Sharpe/Calmar lift |
| Hurst, Ooi & Pedersen (2017), *JPM* | 4.1 | F | COI (AQR); low-corr substrate |
| Asif, Frömmel & Mende (2022), *IRFA* | 4.1 | PRO | crisis alpha outside CTA industry |
| AQR (2020), Put-vs-Trend | 4.2 | PRO | COI (AQR); speed-gap |
| Baltussen, Martens & van der Linden (2026), *FAJ* | 4.2 | F | DAR4020 benchmark |
| Noguer i Alonso & Al Fallouji (2026), CVaR | 4.2, 5.4 | PRO | preprint; speed-gap formalized |
| Grinold (1989), *JPM* | 4.3 | F | breadth = independent bets |
| Meucci (2009), *Risk* | 4.3 | F | effective number of bets |
| Choueifaty & Coignard (2008), *JPM* | 4.3 | F | diversification ratio |
| Carli, Deguest & Martellini (2014), EDHEC | 4.3 | PRO | ENB pays in bear markets |
| Baltussen, Swinkels & van Vliet (2021), *JFE* | 4.3 | F | Expansion factor basis |
| Brown, Gregoriou & Pascalau (2011), *RAPS* | 4.4 | F | over-diversification failure |

### Chapter 5 - the construction

| Source | Section | Stance | Note |
|---|---|---|---|
| DeMiguel, Garlappi & Uppal (2009), *RFS* | 5.1 | F | budget risk, not returns |
| Maillard, Roncalli & Teiletche (2010), *JPM* | 5.1 | F | ERC foundation |
| Lopez de Prado (2016), *JPM* | 5.1 | F | HRP / hierarchical seam |
| Empirical Economics (2026) | 5.1 | CON | Caveat 2: HRP not magic |
| Bongaerts, Kang & van Dijk (2020), *FAJ* | 5.2 | PRO | down-only vol ceiling |
| Cederburg, O'Doherty & Wang (2020), *JFE* | 5.3 | PRO | vol-managed fails OOS |
| "When simplicity beats optimization" (2026), *FMPM* | 5.3 | PRO | simple hard to beat |
| Israelov & Nielsen (2015), *JPM* | 5.4 | PRO | COI (AQR); tail as cost budget |
| Israelov (2019), *JAI* | 5.4 | PRO | COI (AQR); "pathetic protection" |
| One River (2024) | 5.4 | PRO | practitioner; rebalance beats hold |
| Man Group, Portfolio Convexity | 5.4 | PRO | practitioner; overlay convexity |
| LongTail Alpha / Bhansali (2020) | 5.4 | PRO | practitioner; monetization |
| Schwalbach & Auret (2025), *IAJ* | 5.4 | PRO | slow+fast complementarity |
| Costa & Kwon (2019), *Quant. Finance* | 5.5 | CON | Guardrail 2: risk-conditioning |
| Uysal & Mulvey (2021), *JFDS* | 5.5 | CON | Guardrail 2: regime overlay |
| Fleming, Kirby & Ostdiek / Andersen-Bollerslev (2001), *JF* | 5.5 | CON | Guardrail 2: vol timing pays |

### Estimate tier - our own artifacts (labeled in-sample illustration only, never proof)

| Artifact | Section | Role |
|---|---|---|
| [[convexity-as-the-axis-of-strategy-diversification]] | 2.x | internal prior knowledge (axis image) |
| [[skewness-in-asset-returns]] | 3.2 | internal; fragility claim only |
| [[the-tiered-strategy-roster]] | 4.x | internal prior knowledge (roster) |
| [[allocating-and-rebalancing-a-multi-strategy-book]] | 5.x | internal prior knowledge (construction) |
| aegis-trader ADR-0004 + allocator | 5.2, 5.3 | estimate tier; labeled illustration |

## Word-count summary

| Section | Target words |
|---|---|
| Abstract (English) | 250 (not in body total) |
| 1. Introduction | 800 |
| 2. The convexity axis and its two poles | 1,400 |
| 3. Why convexity classifies but cannot budget | 1,200 |
| 4. The roster, all tiers | 1,800 |
| 5. The construction | 1,600 |
| 6. Conclusion | 700 |
| **Body total** | **7,500** |
| AI disclosure + References + mandatory statements | not counted |

## Quality-gate self-check

- Structure pattern: Theoretical Analysis (recognized Pattern 3). Pass.
- Section purpose: every section has a Purpose. Pass.
- Word-count sum: 7,500, exactly on target (0% deviation). Pass.
- Evidence distribution: every Phase 1 source assigned to at least one section. Pass.
- Transition logic: specified for every chapter boundary. Pass.
- Heading levels: two levels (chapter, sub-section); within APA limits. Pass.
- Guardrails: Guardrail 1 sits in 3.5; Guardrail 2 in 5.5; both honest caveats carried (3.5, 5.1).
- User approval: **pending** - this is the Phase 2 -> 3 checkpoint.

## Open items for approval

- Confirm the sub-question chain (SQ1-SQ6) as the paper's spine, or rename.
- Confirm sub-section granularity (2-5 per chapter). If any core chapter needs Level-3 depth
  (e.g. 4.2 Target, 5.4 tail budget), say so and it deepens in Phase 3.
- Confirm the estimate-tier framing is visible enough (ADR-0004 appears only in 5.2/5.3 as labeled
  illustration).
