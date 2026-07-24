---
title: "Budgeting Convexity - argument blueprint"
paper: "Budgeting Convexity"
status: Phase 3 (argumentation) - blueprint drafted, awaiting user approval
tags:
  - argument
---

# Budgeting Convexity - argument blueprint (Phase 3)

Argument Builder deliverable. Input: the approved [[research/budgeting-convexity/_outline|outline]]
and [[research/budgeting-convexity/_sources|source corpus]]. This is the claim-evidence-reasoning
backbone the draft writer follows. Discipline pattern: **Theory -> Evidence -> Interpretation**
(social-science / quantitative-finance), with each claim led by its **ex-ante rationale** per
[[research/README|research/README]] before any confirming evidence.

> [!warning] Checkpoint (Phase 3 -> 4)
> Drafting begins only after this blueprint is **approved**. Contest any sub-argument, counter, or
> strength rating here.

## Central thesis

Diversification is an order of operations over failure modes on the convexity axis: budget **risk**
across the roster, source convexity **structurally**, and treat skew as a **classifier you observe**,
not a budget you solve. It holds because (1) stress co-movement is governed by the sign of convexity,
not the mechanism label, and both poles are durably paid; (2) skew's sign is knowable ex-ante but its
magnitude is estimation-fragile, so skew classifies but cannot budget; (3) a mechanism-count book
collapses to one short-gamma position, so roles must be ordered so each tier fixes the failure below
it; and (4) return-timing of convexity fails out of sample while structural sourcing plus
risk-conditioning survives.

The four sub-arguments discharge every clause of the thesis: SA1 fixes the axis, SA2 the "classify
not budget" verb, SA3 the "order of operations," SA4 the "budget risk / source structurally / observe"
verbs.

## Sub-arguments

### Sub-Argument 1 (Ch2): Convexity is the organizing axis, and both poles are durably paid

- **Evidence** (axis, primary): Lempériere et al. (2017) - the cross-sectional Sharpe lines up with
  negative skew, not volatility; trend is the clean positive-skew outlier. [COI: CFM]
- **Evidence** (axis, independent methods that guard the COI): Lettau-Maggiori-Weber (2014)
  downside-beta CAPM jointly prices FX / equity / options / commodities / bonds (74% vs -17% for
  CAPM); Bollerslev-Todorov (2011) isolate jump-tail fear as ~2/3 of the equity premium. Two
  no-COI routes to the same axis.
- **Evidence** (payers): short pole - variance sellers are paid as crash compensation (Carr-Wu;
  Bollerslev-Tauchen-Zhou); long pole - trend is a lookback straddle (Fung-Hsieh) with hedgers
  paying speculators (Moskowitz-Ooi-Pedersen; risk-premium reading, Kang-Rouwenhorst-Tang).
- **Evidence** (persistence): Shleifer-Vishny and De Long et al. - both payers persist because
  arbitrage is capital-constrained and noise-trader risk is itself priced; McLean-Pontiff bounds
  post-publication decay.
- **Reasoning**: If both the reward and the stress co-movement track the sign of convexity, and each
  pole rests on a mechanism-fixed payer that limits-to-arbitrage keeps in place, then convexity - not
  the mechanism label - is the stable axis on which to organize a book. Three independent methods
  converge on the same axis, which is what makes it load-bearing rather than one house's artifact.
- **Counter-argument**: The axis literature is heavily CFM / AQR authored (product COI); the "skew
  premium" could be a data-mined artifact or repackaged volatility exposure.
- **Rebuttal** (concede and triangulate): Concede the COI on Lempériere and Ilmanen outright; the
  load is carried by the independent, no-COI methods (Lettau-Maggiori-Weber downside-beta CAPM;
  Bollerslev-Todorov jump tails) that reach the same axis by different routes, with McLean-Pontiff
  bounding decay. Not a refutation of the COI, a triangulation past it.

### Sub-Argument 2 (Ch3, LOAD-BEARING PIVOT): Skew classifies but cannot budget

- **Ex-ante rationale (stated first)**: The third moment averages cubed deviations, so a few tail
  prints dominate it - high estimator variance, liable to flip on one crisis print. The *sign* (which
  tail is fat) is identifiable; the *magnitude* is not. Budgeting needs the magnitude; classifying
  needs only the sign. This is a statistical property, not a finding, so it fixes the claim before
  any test.
- **Evidence** (sign stable, magnitude not): Harvey-Siddique (2023, 25-yr OOS) - the premium's sign
  is always positive where HML / momentum flip, magnitude swings 1.4-4.7% by research choice;
  Anghel et al. (2023) - the proxy is "very noisy," pricing "inconclusive."
- **Evidence** (asset-class-specific, mechanism-fixed): Koijen et al. (2018) - carry skew is strongly
  negative in FX / options, positive in equity / Treasury / credit, negligible for diversified global
  carry; Brunnermeier-Nagel-Pedersen fix the sign by mechanism (funding-liquidity unwinds), present
  in FX, absent where the mechanism does not apply.
- **Evidence** (you cannot budget on it): Lassance-Vrins - no OOS benefit to moving off the
  mean-variance-efficient frontier; Martellini-Ziemann - higher-moment portfolios cannot beat GMV
  even with robust comoments. Higher-moment optimization exacerbates estimation risk.
- **Reasoning**: A statistic whose sign is mechanism-determined but whose magnitude is
  estimation-fragile and asset-class-specific can label a pole (a sign decision) yet cannot anchor a
  budget (a magnitude decision). The evidence estimates exactly what the ex-ante property predicts.
- **Counter-argument** (real, carried): Baltas-Salinas (2022) - realized skew is a robust
  *cross-sectional* predictor (cross-asset skew Sharpe 0.73); Le et al. (2023) - option-implied skew
  is forecastable and improves portfolios. Skew is tradeable.
- **Rebuttal** (concede and limit - Guardrail 1): Concede fully, then distinguish **book-level
  net-skew budgeting** (refuted) from **cross-sectional skew ranking / option-implied skew** (a real,
  tradeable signal). The paper claims only that the former fails and explicitly denies skew is a
  passive label. The concession sharpens the pivot rather than weakening it.

### Sub-Argument 3 (Ch4): Order of operations beats mechanism count

- **Evidence** (the failure the order avoids): Brown-Gregoriou-Pascalau (2011) - past roughly twenty
  funds, over-diversification *raises* left-tail risk and lowers returns.
- **Evidence** (Floor: one funds, one responds): carry and trend are mutually diversifying, most in
  the extremes (Bhansali et al.; Olszewski-Zhou); trend is positive every decade and best in
  low-correlation substrate (Hurst-Ooi-Pedersen); its crisis alpha comes from fast de-risking,
  confirmed outside the CTA industry (Asif-Frömmel-Mende).
- **Evidence** (Target: closes the responder's speed gap): AQR Put-vs-Trend - puts pay in fast
  crashes, trend in protracted bears, and slow drawdowns do more damage; Baltussen DAR4020 - negative
  beta at onset vs trend improving as dislocation persists; Noguer i Alonso-Al Fallouji formalize the
  gap analytically (puts reprice on impact, trend is late).
- **Evidence** (Expansion: breadth, gated): Grinold (IR ~ IC * sqrt(BR), breadth = independent bets);
  Carli-Deguest-Martellini - the effective number of bets predicts performance specifically in bear
  markets.
- **Reasoning**: Because correlations are conditional and collapse together (SA1), diversification
  cannot be a count. Each role is admitted only to fix a specific, named failure the prior tier cannot
  - income cannot respond, so add a responder; the responder is late, so add the tail; the book is
  still one-axis, so add gated breadth. The evidence documents each residual failure, and the
  over-diversification result documents the count-book's collapse directly.
- **Counter-argument**: This ordering is a rationalized description of the authors' own book, not a
  derived optimum; another investor could order the tiers differently, or a flat multi-strategy blend
  might do as well.
- **Rebuttal** (reframe, then concede and limit): The order is not claimed unique or optimal; it is
  claimed *non-arbitrary* - each step is forced by a failure the independent evidence documents
  (over-diversification, the trend speed gap, the breadth-in-stress result), not by our book. Concede
  that the specific roster is one instantiation and defer per-role optimality to the seats. The
  load-bearing claim is the *principle* (order over count), which stands on evidence external to us.

### Sub-Argument 4 (Ch5): Deliver convexity by construction and observation, not by a live solve

- **Ex-ante rationale (stated first)**: To *time* protection you must forecast returns; by
  limits-to-arbitrage, a crash signal computable from public prices is priced into options before it
  fires, so its edge should not persist OOS. A structural sleeve's convex sign is instead fixed by
  payoff algebra (Fung-Hsieh), not forecast. Risk-conditioning survives the same argument because
  realized risk (vol, covariance, regime) is comparatively stationary and estimable, not a return
  forecast. This is the ex-ante reason regime-conditional *risk* sizing can pay while return-timing
  cannot.
- **Evidence** (budget risk, not returns): DeMiguel-Garlappi-Uppal - no optimizer consistently beats
  1/N OOS; ERC (Maillard-Roncalli-Teiletche) and HRP (Lopez de Prado) as sound implementations, with
  the honest caveat that HRP does not reliably beat other risk-based methods or Ledoit-Wolf shrinkage
  (Empirical Economics 2026). Claim is "budget risk, do not optimize returns," not "HRP is superior."
- **Evidence** (timing convexity fails): Cederburg-O'Doherty-Wang - vol-managed gains are
  spanning-regression artifacts of structural instability; FMPM (2026) - simple diversification is
  hard to beat; AQR "Working Your Tail Off" - crash timing is not feasible. Down-only vol targeting
  helps constrained books (Bongaerts-Kang-van Dijk).
- **Evidence** (tail as a monetized cost budget): Israelov-Nielsen and Israelov - standing puts
  deliver worse drawdown-per-return except against gaps; One River, Man Group, and LongTail Alpha -
  disciplined rebalancing and overlays reach put-like convexity at a positive average return.
- **Reasoning**: Structural sourcing fixes the convex sign by construction; risk budgeting sizes
  without a return forecast; observing recorded skew monitors the net-convex property without making
  it a live constraint that can go infeasible and halt the book. This is precisely what the ex-ante
  argument predicts will survive OOS.
- **Counter-argument** (real, carried): Regime-conditional allocation beats static OOS in several
  peer-reviewed studies (Costa-Kwon 2019; Uysal-Mulvey 2021; Fleming-Kirby-Ostdiek vol timing). A
  live regime solve *does* pay, seemingly against "no live solve."
- **Rebuttal** (concede and limit - Guardrail 2): What those papers condition on is *risk* (regime
  covariance, vol, MOVE), not a *return / crash forecast*. On our own risk-vs-return line (ADR-0001
  amended) that is the permitted side. Scope precisely: convexity must not be return/crash-*timed*
  (fails OOS); source it structurally, size it by risk-conditioning; treat regime-conditional *risk*
  sizing as a defensible-but-contested refinement - never rejected, never adopted here. The claim
  survives, narrowed to exactly what the evidence supports.

## Logical flow

```
Ch1  Problem -> Gap -> Thesis
       (count-diverse book = one short-gamma position; skew mis-used as a lever)
   |
Ch2  SA1: axis is the sign of convexity; both poles durably paid
       (Lempériere + independent methods + payers + limits-to-arbitrage)
   |   invites "so budget by skew" ->
Ch3  SA2 (PIVOT): skew classifies but cannot budget
       (ex-ante tail-domination -> sign stable, magnitude not -> cannot anchor a budget;
        Guardrail 1: still ranks cross-sectionally)
   |   removes the naive lever -> organizing variable is the economic job ->
Ch4  SA3: order of operations over roles; each tier fixes the failure below
       (over-diversification is the failure; Floor -> Target speed gap -> gated Expansion)
   |   roster named -> how to realize it ->
Ch5  SA4: budget risk, source convexity structurally, observe skew, monetize the tail
       (timing fails OOS; risk-conditioning survives; Guardrail 2 narrows the claim)
   |
Ch6  Thesis restated -> limits (integrative paper, roles deferred) -> the three seats
```

## Argument strength assessment

| Sub-argument | Evidence strength | Logic validity | Counter-arg risk | Rating |
|---|---|---|---|---|
| SA1 - axis + payers | Strong (3 independent methods converge) | Valid | Low-Medium (product COI) | Strong (85) |
| SA2 - classify not budget (pivot) | Strong (ex-ante property + 3 streams) | Valid | Medium (must hold the ranking-vs-budgeting line) | Strong (88) |
| SA3 - order over count | Strong on the principle, Moderate on the specific roster | Qualified | Medium (rationalized-description risk) | Strong (78) |
| SA4 - construction not solve | Strong (ex-ante + 3 streams) | Valid | Medium-High (regime-conditional contra is sharp) | Strong (76) |

No sub-argument rated Adequate or Weak. Weak-argument indicators checked: no circular reasoning, no
naked appeal to authority (each cite carries a mechanism or a result), no false dichotomy (SA4
explicitly holds a third position between "solve live" and "ignore regime"), key terms (convexity,
skew sign vs magnitude, risk-conditioning vs return-forecasting) defined once and used consistently.

## Notes for draft writer

- **Register**: Journal of Portfolio Management style - direct, claim-first, no throat-clearing. No
  em dashes anywhere (house rule); use spaced hyphens or restructure. Vary paragraph length.
- **Lead with the ex-ante rationale**, then the evidence that estimates it. Never present a backtest
  or a cite as the discovery. This is the spine of every section, load-bearing in Ch3 and Ch5.
- **SA2 is the pivot** - give it the sharpest, most careful prose. The entire contribution turns on
  the sign-vs-magnitude distinction; a reviewer who collapses "skew cannot budget" into "skew is
  useless" defeats the paper, so hold Guardrail 1 explicitly in the same breath as the claim.
- **SA4 is the most contestable** - hedge the regime-conditional concession precisely on the
  risk-vs-return line; do not overclaim "no live solve ever pays," claim "return/crash timing fails,
  risk-conditioning is a contested-but-permitted refinement."
- **COI disclosure in-text**: flag CFM (Lempériere, Bouchaud, CFM 2018), AQR (Ilmanen,
  Moskowitz-Ooi-Pedersen, Hurst-Ooi-Pedersen, Put-vs-Trend, Israelov, Koijen, Brunnermeier et al.),
  PIMCO (Bhansali) at first use; lean on the no-COI anchors (Lettau-Maggiori-Weber,
  Bollerslev-Todorov, Shleifer-Vishny, DeMiguel, Brown et al.) for load-bearing steps.
- **Estimate-tier discipline**: our ADR-0004 and allocator appear only in 5.2 / 5.3 as labeled
  in-sample illustration of one sound implementation, never as proof. Do not let them carry a claim.
- **Scope honesty**: this is the integrative paper. Where a role's per-mechanism proof is thin, say
  "deferred to the seat," do not manufacture depth. Ch6 limits must state the expected revision round.

## Open items for approval

- Confirm the four sub-arguments and their order.
- Confirm the four rebuttal strategies (SA1 triangulate; SA2 concede-and-limit; SA3 reframe then
  concede; SA4 concede-and-limit on the risk-vs-return line).
- Confirm the strength ratings, especially accepting SA4 at Strong (76) with Medium-High counter-arg
  risk rather than forcing it higher than the evidence allows.
