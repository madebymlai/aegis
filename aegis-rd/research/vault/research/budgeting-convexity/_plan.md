---
title: "Budgeting Convexity - chapter plan"
paper: "Budgeting Convexity"
status: pipeline Stage 3 peer review in progress (5-panel subagent)
tags:
  - plan
---

# Budgeting Convexity - chapter plan

Plan-mode deliverable for the architecture paper. Produced by Socratic dialogue; it is the
hand-off input to `academic-paper` **full** mode (Phase 0 config -> Phase 1 literature -> ...).
The brief is [[research/budgeting-convexity/_brief|_brief]]; this supersedes it on structure.

> [!note] Status: Phases 1-2 done, Phase 3 blueprint drafted, awaiting approval
> Phase 1 go/no-go **passed** (both claims survived, sharpened - see below). Paper Configuration
> Record **confirmed 2026-07-24** (below). Phase 1 Source Corpus complete in
> [[research/budgeting-convexity/_sources|_sources]]; Phase 2 outline + evidence map approved in
> [[research/budgeting-convexity/_outline|_outline]]. Phase 3 argument blueprint drafted in
> [[research/budgeting-convexity/_argument|_argument]] - **awaiting user approval before Phase 4
> (drafting)**.

## Paper Configuration Record (Phase 0, confirmed 2026-07-24)

| Parameter | Value |
|---|---|
| Type | Theoretical (framework paper); template `theoretical_paper` |
| Discipline | Quantitative finance / investment management (multi-asset construction, risk premia, tail risk) |
| Target journal | Journal of Portfolio Management style (register anchor, not a submission commitment) |
| Citation format | APA 7th (convertible to Chicago author-date later) |
| Output | Combined - Markdown source of truth + LaTeX + PDF to `papers/` |
| Body language / Abstract | English / English-only |
| Word-count target | 7,500 words |
| Co-authors / Funding | Single-author / no funding; source-side COI (AQR/practitioner cites) disclosed in-text |
| Style profile | null (discipline defaults) |
| Domain evidence profile | general_social_science (advisory; switch to cs_ml if Phase 1 down-weights arXiv/SSRN preprints) |
| Citation verification | strict |
| Operational mode | full |

## INSIGHT collection

- **[INSIGHT: thesis]** Diversification is an order of operations over failure modes, organized
  on the convexity axis. Convexity (sign of skew) defines the poles a book must span and the
  net-convex property it must hold; the economic job builds the roster (Floor / Target /
  Expansion); allocation budgets **risk**, not skew.
- **[INSIGHT: contribution]** The load-bearing claim is a *market* claim: realized skew is a
  tail-dominated, horizon-unstable, asset-class-specific statistic, so it cannot anchor a stable
  allocation target. Net-convexity is therefore sourced **structurally** (trend, a robust
  long-gamma anomaly) and **verified by observation**, not solved as a live constraint.
- **[INSIGHT: evidence-standard]** Per [[research/README|research/README]] "Behaviours, not
  strategies": every claim carries an **ex-ante economic rationale** that fixes the effect's sign
  from first principles *before* any test. Market behaviour and that rationale are the proof. Our
  ADRs, allocator code, and run diaries are the *estimate* tier - labeled in-sample confirmation,
  never the discovery.

## Spine (one line)

Axis = convexity (defines the poles + the net-convex property) · Lens = economic job (builds the
roster) · Construction = budget risk, source convexity structurally, observe skew and never
budget it.

## Chapter plan

Each chapter establishes one link in the argument. Word counts provisional.

| # | Chapter | Core argument (the one claim) | Evidence / sources | ~words |
|---|---|---|---|---|
| 1 | Introduction | The question is *order, not count*; a mechanism-diverse book is one short-gamma position that pays out in the single regime where every insurance seller is hit. State the thesis. | framing; roster capstone | 800 |
| 2 | The convexity axis and its two poles | Stress co-movement is governed by the **sign of convexity** to the common shock, not the mechanism label; two poles, each with a **durable payer** (structural insurance demand short-gamma; a behavioural/hedger anomaly long-gamma). | Lempériere/CFM line; Lettau-Maggiori-Weber downside-beta; Bollerslev-Todorov jump tails; Fung-Hsieh straddle; Ilmanen | 1,400 |
| 3 | Why convexity classifies but cannot budget (**pivot**) | Skew is tail-dominated, horizon-unstable, asset-class-specific; its **sign** is knowable ex-ante, its **magnitude** is not - so it labels a pole but cannot anchor a budget. | Harvey-Siddique 25-yr (sign stable, magnitude swings 2.1-3.9%); Koijen et al. + BNP (carry skew asset-class-specific); Pyun (VRP timing unstable); skew-as-third-moment fragility | 1,200 |
| 4 | The roster (all tiers) | The order of operations; each tier fixes a failure the one below cannot. **Floor** = convergent income engine ⊕ persistent-crisis responder (opposite convexity; one funds, one responds). **Target** = immediate defense / the tail, closing the responder's *speed gap* (the fast V-crash trend sleeps through); a role, not a timer. **Expansion** = off-axis market-neutral, breadth-gated, last. Failure the order avoids: the over-diversified book. | Baltussen DAR4020; AQR put-vs-trend; Bhansali carry+trend; over-diversification (Brown et al.); breadth (Grinold/Meucci) | 1,800 |
| 5 | The construction | Realize the roster: budget **risk** (ERC/HRP + down-only vol ceiling); net-convexity **by construction**, not solved; **observe** skew; the tail's **convexity-premium budget** (where "Budgeting Convexity" literally lives). Reject live regime-timing. Role verification stated as a tail-aware **principle**, deferred to the seats. | vol-target down-only (Bongaerts et al.; Harvey et al.); ERC/HRP (Roncalli); DeMiguel 1/N; ADR-0004 as *labeled illustration only* | 1,600 |
| 6 | Conclusion | Restate contribution; limits (this is the integrative paper - roles are asserted and reconciled once the seats deepen; expect a revision round); the three seats as future work. | - | 700 |

Plus: Abstract (bilingual), AI Disclosure, References (all mandatory).

## Chapter 1 - locked

- **Hook / urgency.** An allocator who diversifies by *mechanism* (carry, macro, stat-arb,
  managed futures) ends with a book that looks varied and is secretly **one short-gamma
  position**, all due in the single regime where every insurance seller is hit at once. The book
  that looks most diversified is the one most exposed.
- **Gap (one sentence).** The field asks *"how many low-correlated premia should I harvest"* and
  **counts mechanisms**, when the question that decides survival is *which failure modes the book
  spans, and in what order* - and where it reaches for skew, it treats skew as a **lever to
  balance** rather than a **classifier to read**.
- **Thesis the reader holds leaving Chapter 1.** *Diversification is an order of operations over
  failure modes on the convexity axis - budget risk across the roster, source convexity
  structurally, and treat skew as a classifier you observe, not a budget you solve.*

## Carried sources vs cut

- **Carried (mine for evidence):** [[convexity-as-the-axis-of-strategy-diversification]],
  [[skewness-in-asset-returns]] (fragility claim only), [[the-tiered-strategy-roster]],
  [[allocating-and-rebalancing-a-multi-strategy-book]].
- **Cut as carried articles:** [[measuring-crisis-alpha]] (measurement machinery -> seat papers),
  [[when-conditioning-pays]] (one line if at all), the low-vol / betting-against-beta and skew
  pricing-channel digressions. Prior knowledge, drawn on only where a sentence needs it.

## Tier -> seat mapping (implementation deferred)

- Floor responder -> [[research/crisis-responder/_brief|② crisis-responder]]
- Floor income -> [[research/convergent-engine/_brief|③ convergent-engine]]
- Target tail -> [[research/v-crash-defense/_brief|④ v-crash-defense]]
- Expansion -> no seat yet (future fifth family, breadth-gated)

## Title decision

Keep **"Budgeting Convexity"** only if it names the tail's convexity-premium budget plus
risk-budgeting across the roster. **Drop the "by the sign of skew" subtitle** - it implies the
skew-balancing the evidence refutes. Final subtitle TBD at Phase 0.

## Phase 1 go/no-go - VERDICT: GO (both claims survive, sharpened)

Independent Exa scan (2026-07-24, pro + contra). Neither claim collapsed; the contra evidence
kills the naive version of each and forces a sharper, more defensible one. Two guardrails the
draft must honor (below).

### Claim 1 - skew classifies, it cannot budget: **supported, sharpened**

- **Ex-ante rationale (fixes the sign before any test).** The third moment averages *cubed*
  deviations, so a few tail prints dominate it: high estimator variance, liable to flip on one
  crisis observation - a statistical first principle, not a finding. So the *sign* (which tail is
  fat) is identifiable while the *magnitude* is an unreliable target; budgeting needs the
  magnitude, classifying needs only the sign. Carry's negative skew comes from one mechanism -
  funding-liquidity unwinds of crowded leveraged positions (BNP) - present in FX, largely absent
  in bond/credit/equity carry, so "is this carry concave" is fixed by whether that mechanism
  applies, before any measurement. The evidence below *estimates* what this predicts.
- **Confirming.** Higher-moment portfolio *optimization* has no reliable OOS benefit (Lassance &
  Vrins; Martellini & Ziemann 2010 - higher-moment portfolios cannot beat GMV even with robust
  estimates). Coskew estimate is noisy and the premium *magnitude* swings 1.4-4.7% by research
  choice while its *sign* stays positive where HML/momentum flip (Harvey-Siddique 2023; Anghel et
  al. 2023, "inconclusive," not significant at 90%). Carry skew is asset-class-specific, more
  strongly than the legacy note: currency/options carry strongly negative-skewed, but equities /
  US Treasuries / credit carry *positive*-skewed, and the diversified global carry factor has
  *negligible* skewness (Koijen et al.).
- **Contra (real).** Realized skew is a robust *cross-sectional* predictor (Baltas & Salinas,
  "Cross-Asset Skew", JPM 2022, Sharpe 0.73); option-implied skew is forecastable enough to help
  (Le et al. 2023).
- **Guardrail 1.** Distinguish **book-level net-skew budgeting** (refuted) from **cross-sectional
  skew ranking / option-implied skew** (a real, tradeable signal). Never say "skew is only a
  passive label."

### Claim 2 - structural convexity beats signal-solved convexity: **supported, sharpened**

- **Ex-ante rationale (fixes the sign before any test).** To *time* crash protection you must
  forecast returns; by the README's own limits-to-arbitrage logic, a crash signal computable from
  public price data is priced into options before it fires, so its edge should not persist OOS -
  we expect price-based crash-timing to fail before testing. A *structural* convex sleeve rests
  instead on a mechanism whose sign is fixed by payoff algebra, not forecast: trend is long-gamma
  to sustained moves (Fung-Hsieh straddle identity), sustained by under-reaction / herding plus a
  hedger fee, bounded by limits to arbitrage. Risk-conditioning survives the arbitrage argument
  because realized risk (vol, covariance, regime) is comparatively stationary and estimable, not
  a return forecast - the ex-ante reason regime-conditional *risk* sizing can pay while
  return-timing cannot. The evidence below *estimates* what this predicts.
- **Confirming.** Crash/return *timing* of protection fails: "neither calm markets nor rising
  volatility have been helpful timing signals for the tail hedge" (AQR, Put-vs-Trend 2020);
  direct hedging "only delivers value when combined with the ability to time short-term crashes
  and unwind shortly after - we question investors' ability to do either" (AQR, Working Your Tail
  Off). Volatility-managed portfolios fail OOS from "structural instability in the spanning
  regressions" (Cederburg, O'Doherty & Wang, JFE 2020); "simple diversification remains
  remarkably difficult to outperform" (FMPM 2026). Structural sleeve + disciplined
  rebalancing/monetization beats passive-hold and discretionary timing (One River; Man Group;
  LongTail Alpha). Trend is late by construction (signal must cross zero) but convex insurance
  reprices on impact (Noguer i Alonso & Al Fallouji, CVaR framework 2026).
- **Contra (real).** Regime-*conditional* allocation beats static OOS in several peer-reviewed
  studies (Costa & Kwon 2019; Uysal & Mulvey 2021; regime-aware risk parity, Lancaster 2026;
  volatility timing, Andersen & Bollerslev). Cannot be waved off.
- **Guardrail 2.** What those papers condition on is *risk* (regime covariance, vol, MOVE), not a
  *return/crash forecast* - our own **risk-conditioning vs return-forecasting** line (ADR-0001
  amended). Scope the claim to: convexity must not be *return/crash-timed* (fails OOS); source it
  structurally, size by *risk-conditioning*; treat regime-conditional *risk* sizing as a
  defensible-but-contested refinement (the roster's existing "regime-parity is the contested
  alternative" hedge), never as rejected.

### New sources to carry into Phase 1 proper

- Claim 1 pro: Lassance & Vrins (OMVE, no OOS benefit off the MVE frontier); Martellini &
  Ziemann (2010); Anghel, Caraiani, A. Rosu & I. Rosu (2023, coskew replication, inconclusive).
- Claim 1 contra: Baltas & Salinas, "Cross-Asset Skew" (JPM 2022); Le et al. (2023, option-implied skew).
- Claim 2 pro: AQR "Working Your Tail Off"; Cederburg, O'Doherty & Wang (JFE 2020, vol-managed);
  "When simplicity beats optimization" (FMPM 2026); One River, "The Convexity (Re)Balancing Act";
  Man Group, "Creating Portfolio Convexity"; Noguer i Alonso & Al Fallouji (CVaR 2026).
- Claim 2 contra: Costa & Kwon (2019, regime-switching risk parity); Uysal & Mulvey (2021);
  Andersen & Bollerslev (Economic Value of Volatility Timing); Taylor (2023, vol-timing needs
  leverage, sample-dependent).

Prior leads retained: Harvey-Siddique; Koijen/BNP; Pyun; Hurst-Ooi-Pedersen / Fung-Hsieh. The
net-skew-budgeting refutation on our poles stays labeled in-sample confirmation only.

## Open planning items

- Chapter 1 core claim: **locked** (see "Chapter 1 - locked" above). Chapters 2-6 negotiated at skeleton level; per-chapter Step 2 detail can deepen in full mode's Phase 2/3 or a later plan pass.
- Word-count target and venue register unset (Phase 0).
- Contribution-sharpening (plan Step 2.5) and argument stress test (Step 3) still to run.
