---
title: Demeter Credit Carry Rewrite Design
date: 2026-07-13
topic: carry
distilled-into:
tags:
  - note
  - carry
  - demeter
---

# Demeter Credit Carry Rewrite Design

> [!abstract] Decision
> Demeter cannot be repaired by making its current FRED richness scalar more active. Its two-ETF universe is too coarse for carry selection, but the UCITS opportunity set can be widened into distinct maturity and quality buckets. The old experiments also confounded a noisy distribution-yield estimator with the credit mechanism and judged the floor on a crisis objective that structurally favors trend. Rebuild it as a sparse, full-budget, duration-budgeted credit-yield strategy with an honest static control. It keeps the `carry` name only if it delivers positive income, negative multi-month asymmetry and positive marginal value beside the locked trend stream. Otherwise it is `credit_income`, not the floor's concave pole.

## Question and scope

The research question is whether a small, long-only, UCITS-constrained book can implement a genuine corporate-credit carry sleeve by selecting across investable maturity and quality buckets, rather than merely hold two coupon-paying ETFs.

In scope are the credit premium, a screened UCITS ETF opportunity set, point-in-time public data, monthly decisions, full use of Trader's assigned sleeve budget, sparse holdings, and the pole's contribution beside the locked trend stream. Individual-bond ranking, account-level derivatives, short credit, and proprietary index histories are out of scope.

The prior was that expected net carry should be yield minus expected loss, fees and hedge costs, then converted into a 0-1 budget-utilization scalar. The evidence changed that design. Expected loss is economically essential but not a clean public ETF-level observable; switching the entire sleeve on and off also liquidates the negative-skew inventory the roster hired it to hold.

## Why the current construction is not the target

Credit carry has a precise generic definition: the return earned if market conditions do not change. In corporate bonds it is credit spread plus roll-down on the credit curve, measured after separating the duration-matched Treasury return.[^koijen] FTSE Russell reaches a closely related implementation through yield, spread and Treasury-curve roll-down under constant OAS, then compares maturity buckets while matching interest-rate exposure.[^ftse]

Demeter's current `DBAA - DGS10` input does none of that. It broadcasts one coarse Baa macro spread to both SDHY and LQDH, although one is short-duration high yield and the other is long-maturity investment grade with an embedded Treasury-futures hedge. With `carry_gain=0`, even that proxy is inert. The promoted stream is therefore static credit exposure sized by trailing ETF volatility, not observed credit carry.

The local evidence does not cleanly kill credit carry. The first mixed 20-asset proxy ranked wrappers on trailing cash distributions divided by price. It omitted commodity roll carry, mixed coupons with ETF distribution policy and capital-gain distributions, and produced only mild negative skew (`-0.13`) on its selected absolute book. The later floor summary rounded a related reconstruction to roughly zero and [[graveyard]] generalized that result too far.

The credit-only UCITS experiment points the other way. Its static stream recorded quarterly skew of `-0.49`; routing spread richness into exposure deepened it to `-0.75`. That experiment was rejected because adding credit did not beat trend-only in crisis-conditional return. The same diary later recognized that this objective is structurally unsuitable: a concave income pole is paid to lose in those states, so it cannot be required to improve the convex pole's worst-state payoff. What failed was crisis orthogonality, not family membership.

The rewrite therefore treats all earlier results as diagnostics, not a kill. [[the-tiered-strategy-roster]] requires the floor to own both signs of skew, while [[the-skew-is-the-product]] identifies duration-times-spread as credit's crash-beta inventory. A construction that improves standalone Sharpe by cutting DTS would still repeat a real role failure, but credit must be retested under the correct estimator and portfolio-level objective.

## What the broad-to-narrow search settled

### The broad credit premium exists; a separate carry alpha is fragile

Duration-hedged corporate credit has earned a positive long-run premium, but the cross-sectional carry factor is much less secure than the market premium. Israel, Palhares and Richardson find that value and momentum explain returns more reliably than carry in their bond-level tests.[^ipr] The strongest current counter-source is the 2026 corporate-bond factor replication: after correcting shared-price measurement error and ex-post filtering, only 26 of 432 factor specifications survive false-discovery control, concentrated in credit-spread value; most factors do not improve on the bond-market factor.[^drr]

This distinction determines the benchmark. Static credit exposure is not a straw man. It is the primary control and may be the correct implementation for this constrained book. The active design must prove incremental value rather than inherit the result of bond-level carry papers.

### OAS is observable compensation, not net expected return

Credit spread mixes expected loss, liquidity, taxes and risk premium. Nozawa's peer-reviewed variance decomposition finds that expected credit loss and expected excess return each explain about half of cross-sectional spread variance; for the market portfolio, time-series spread variation is mainly risk-premium variation.[^nozawa] A live formula that treats OAS as pure return is wrong, but subtracting a guessed ETF-level default loss is false precision.

Expected loss therefore leaves the first implementation contract. OAS is used as a carry and valuation descriptor. Default loss, recoveries and liquidity enter realized attribution and tail reports until a causal, point-in-time probability-of-default and recovery source exists. A future expected-loss model must be a separately validated challenger, not an untestable adjustment embedded in the base signal.

### Timing is a challenger, not the definition of carry

There is peer-reviewed evidence for moving-average timing of OAS-sorted IG and HY portfolios after modeled costs.[^bektic] The counter-case is material: a broad tactical-credit sweep finds its gain concentrated in 2000-2003 and 2008-2009, with annualized return falling from 2.9% to 1.6% when those episodes are removed.[^hoffstein] The newest replication evidence also says credit-spread value survives more often than raw carry, but it studies bond-level cross-sections rather than a two-ETF time-series switch.[^drr]

The active candidate is therefore a slow within-quality maturity tilt, not a hard risk-off gate or an unconstrained HY-versus-IG timing trade. It selects short versus broad exposure separately inside IG and HY, remains fully invested in the assigned credit sleeve, and holds the IG/HY capital split fixed so the maturity signal cannot become an unconstrained quality-timing trade. A cash gate belongs to a different, convex strategy because it changes the pole's payoff shape.

### Public ETF data support a historical yield-and-duration selector

BlackRock publishes current holdings, distributions, YTM and duration for both funds. LQDH's February 2026 factsheet, for example, reports 4.68% YTM, 4.66% trailing yield, 0.25% TER and -0.15 years effective interest-rate duration.[^lqdh] The public UCITS holdings files provide the exact historical securities and fund weights but omit security-level yields. A separate first-party US iShares product-data endpoint provides point-in-time bond-level yield-to-worst and modified duration for arbitrary historical dates.[^blackrock-product-data]

The two surfaces can be joined by ISIN without substituting US ETF weights for the investable UCITS funds. `SLQD`, `SHYG`, `LQD` and `HYG` supply the security analytics; `SDIG`, `SDHY`, `LQDE` and `IHYU` supply the actual point-in-time portfolio weights. This is a security-level market-data join, not a return-series proxy. It survives differences in issuer caps because only bonds actually held by each UCITS fund enter its aggregate.

A complete monthly probe from August 2020 through June 2026 reproduced all 71 month-ends for all four funds. Minimum matched fixed-income weight was 95.13% for `SDIG`, 97.58% for `SDHY`, 99.27% for `LQDE` and 98.30% for `IHYU`; median coverage exceeded 99.4% for every fund. Representative UCITS-weighted YTW and modified-duration estimates were 0.76% and 2.62 for `SDIG`, 4.27% and 2.73 for `SDHY`, 2.12% and 9.82 for `LQDE`, and 4.38% and 4.28 for `IHYU` on 31 August 2020. On 30 June 2026 they were 4.62% and 2.24, 7.17% and 2.58, 5.34% and 8.15, and 6.65% and 3.81 respectively.

This establishes historical and live **YTW and duration**, not exact OAS, spread duration or option-adjusted credit-curve roll-down. BlackRock defines the reported field as yield-to-worst for callable bonds and states that it excludes fund fees.[^blackrock-shyg] The base candidate can therefore use lagged UCITS-weighted YTW minus TER and a duration budget. OAS/DTS and roll-down remain nullable diagnostics or later licensed-data enhancements; they must not be synthesized and relabelled as observed.

FRED's ICE BofA OAS series are acceptable point-in-time market context when matched separately to HY and IG. They do not become fund-level analytics merely because the funds track nearby universes. Every report must label index proxy and fund observation separately.

## The opportunity set must be widened before the strategy is specified

Two ETFs are a design choice, not a mandate constraint, but a larger ticker count is not automatically a better cross-section. The narrow Exa pass rejected the earlier mixed-provider ladder in favor of a four-fund, same-manager, same-index-family grid. It changes one named economic axis at a time and has complete instrument history for the test window.

| Quality | Short maturity | Broad maturity |
| --- | --- | --- |
| Investment grade | `SDIG.LSEETF` — iBoxx USD Liquid IG 0-5 | `LQDE.LSEETF` — iBoxx USD Liquid IG |
| High yield | `SDHY.LSEETF` — iBoxx USD Liquid HY 0-5 Capped | `IHYU.LSEETF` — iBoxx USD Liquid HY Capped |

All four are physical, distributing USD UCITS share classes listed on the LSE. The two short funds launched in October 2013; broad HY launched in September 2011; broad IG launched in May 2003. BlackRock states monthly index rebalancing for the broad funds and reports the corresponding iBoxx benchmarks.[^sdig][^sdhy][^ihyu][^lqde] The shared construction does not make the funds identical, but it removes provider, currency, distribution-policy and broad benchmark-family changes from the primary comparison.

`SDIG`, not the accumulating `SDIA` line, is the short-IG research instrument. Both are share classes of the same fund and benchmark, but `SDIG` pays quarterly distributions. Using distributing classes throughout keeps cash-income attribution observable while adjusted prices remain the source for total return.

`LQDH.LSEETF` is retained as a fifth **mechanism challenger**, not as another point in the maturity rank. It follows the iBoxx USD Liquid IG Interest Rate Hedged Index and uses derivatives to reduce Treasury duration.[^lqdh] Its near-zero effective *interest-rate* duration is not spread duration, and its hedge makes an `LQDH`-versus-`LQDE` comparison a test of duration removal rather than credit-curve selection.

The other broad-screen candidates are excluded from the primary universe:

- VUSC, SYBR and SYBN change benchmark provider or issuer universe while changing maturity, so they add confounding before they add information.
- XUHY is a useful later sensitivity because its lower fee comes with a different Bloomberg very-liquid, ex-144A universe.
- European target-maturity UCITS ETFs arrived too late to support the 2020-2026 experiment without synthetic history.
- DBXM sells European crossover CDS protection through a synthetic EUR wrapper; it is a separate pure-spread strategy, not a USD bond bucket.

The resulting shape is deliberately small: four rankable buckets plus one hedge challenger, with at most two live holdings. One IG and one HY leg may be selected inside their respective maturity pairs; the strategy must not convert a maturity comparison into an unconstrained quality bet. This gives each decision a counterfactual—short versus broad at the same quality—and avoids pretending that several overlapping broad funds provide independent carry observations.

### IBKR validation

The paper gateway qualified all five USD LSEETF contracts on 13 July 2026 as `stockType=ETF`: `SDIG` (`conId=136370290`), `LQDE` (`37080143`), `LQDH` (`134770201`), `SDHY` (`136370296`) and `IHYU` (`94305746`). Read-only `ADJUSTED_LAST` requests covered `[2020-08-10, 2026-07-01]` for every instrument. `LQDE`, `SDHY` and `IHYU` returned 1,487 observations, `SDIG` 1,486 and `LQDH` 1,484. The small calendar gaps must be exposed by alignment diagnostics; they are not a reason to manufacture observations. Contract qualification and history availability establish implementability, not strategy merit or live liquidity.

## Refined experiment

### Control: static credit income

The control spends 100% of the sleeve budget in a fixed, diversified subset of the screened credit universe. Its IG/HY weights are fixed ex ante, not recomputed from standalone price volatility. Until spread duration is observed, use fixed documented quality weights and call the control `credit_income_static`; do not manufacture DTS from modified duration or from LQDH's near-zero *interest-rate* duration.

The control answers whether the broad credit premium and distributions are useful beside trend. It is a valid outcome if no active signal beats it.

### Candidate: sparse duration-budgeted bucket selection

For each leg, the indicator emits an explicitly typed observation:

- matched market OAS and its source date;
- slow richness, defined from information available at that date only;
- fund YTM and TER when a contemporaneous issuer snapshot exists;
- spread duration and DTS only when directly sourced with verified semantics;
- freshness and provenance, distinguishing fund analytics from index proxies.

The strategy compares lagged net YTW within the IG and HY maturity pairs monthly, selects one bucket from each pair, and spends the full sleeve budget across those two holdings while preserving the control's IG/HY capital split. Modified duration is an observed risk descriptor and may impose a pre-registered portfolio range. It is not renamed spread duration, and `modified_duration × excess_yield` may be reported only as an explicitly named proxy, never as observed DTS. Partial rebalancing or a narrow band controls turnover without allowing a wide drift band to turn the pole into momentum. Missing or stale active context returns the static allocation, not zeros and not cash.

This is a credit carry-and-value challenger implemented across ETF risk buckets. It approximates, but is not equivalent to, the bond-level carry portfolios in the literature, and its name should say so in code and reports.

### Attribution

Realized total return is decomposed into:

- cash distributions;
- ex-distribution price return;
- currency translation;
- explicit trading costs;
- an embedded-fund residual containing spread repricing, defaults, fees and LQDH hedge results that public data cannot separate cleanly.

Report the residual honestly. Do not infer hedge cost from LQDH's effective duration or count distributions twice through adjusted prices.

## Selection contract

The family is selected between the static control and active candidate on paired held-out blocks. The active candidate receives no presumption of superiority.

The ranker is the candidate's marginal certainty-equivalent contribution to the locked trend composite, as required by [[what-makes-a-convergent-sleeve-an-income-engine]] and [[the-skew-is-the-product]]. Standalone income utility remains diagnostic.

The primary standalone experiment uses four expanding walk-forward folds. Each fold holds out a fixed 252-session year; the selection window begins with 504 sessions and expands through all prior observations. This matches the cumulative information set available to a slow monthly strategy, retains the latest observations in the final fold, and avoids tuning a rolling-history length. Rolling-window results may be reported as robustness evidence but cannot replace the preregistered expanding result.

Required reports are:

- realized distribution income and total return attribution;
- average and stability of modified duration, plus DTS only when directly measurable;
- multi-month downside L-skew and physical-return risk asymmetry;
- worst-decile multi-month loss in capital units;
- ordinary and downside beta/correlation to the locked trend stream;
- turnover, fees and stale-signal fallback frequency;
- signal monotonicity and neighboring-parameter stability.

The winning construction requires all of the following:

1. It has positive realized income and improves paired held-out composite utility over trend-only at a fixed sleeve weight. For the active candidate, the comparator is also the static control.
2. Its contribution is not concentrated in one easing year, one crisis or one parameter cell.
3. It retains the pre-registered quality split and modified-duration range, and exhibits the required negative multi-month asymmetry. DTS is an additional test only when directly measurable.
4. It does not worsen the composite's stress-state co-movement beyond the incumbent.
5. Every historical signal value is reproducible from data available on that date.

If the static control wins and clears the role contract, retain it as the deliberately simple Demeter champion. If the winner contributes useful income but fails the concavity contract, rename the family to `credit_income` and remove it from the roster's concave seat. If neither construction improves the composite, retire credit from Demeter rather than optimize the label.

## Data-contract acceptance test

The active selector is established only when one immutable row can be reproduced for every decision date and candidate. The minimum row is:

| Field | Meaning |
| --- | --- |
| `decision_date` | Month-end whose information set is being used |
| `available_at` | First timestamp at which the observation could have been known |
| `instrument_id` | Exact ETF line the observation describes |
| `reference_index` | Index actually measured; never inferred from the ticker |
| `ytw`, `oas`, `spread_duration` | Point-in-time inputs, nullable individually but not silently substituted |
| `ter`, `hedge_cost` | Known deductions; unknown hedge cost remains explicitly missing |
| `source_url`, `source_date`, `content_hash` | Provenance and immutable replay identity |
| `match_quality` | `fund`, `exact_index`, `bucket_proxy`, or `unusable` |

An input qualifies for the active historical rank only if it passes all of these tests:

1. **Economic match:** it measures the same quality and maturity bucket. A broad HY OAS is not an `SDHY` 0-5 OAS, and an ETF's effective interest-rate duration is not spread duration.
2. **Window coverage:** it covers at least 90% of scheduled month-ends from August 2020 through June 2026, including 2020 and 2022. Filling the missing early regime from current observations is prohibited.
3. **Causal timestamp:** the publication or close timestamp is known. A month-end observation first published in the following month enters only after publication.
4. **Immutable replay:** the raw response is content-addressed and validation rejects changed historical observations. Live refresh may append a newer snapshot but never rewrite the input selected for an old run.
5. **Live continuity:** the same source continues to update. A transient outage may use the newest previously fetched observation within a declared freshness window; stale context falls back to the static allocation.
6. **Cross-check:** selected dates reconcile to issuer factsheets or index documentation within a declared tolerance, and unit, percentage/basis-point and duration semantics are tested.

### What the free sources currently establish

FRED exposes exact daily ICE BofA broad IG and HY OAS/yield series and 1-3/3-5 IG subsets.[^fred-ig13][^fred-ig35][^fred-hy] They are useful market proxies, but they do not complete this contract:

- since April 2026 the ICE BofA series exposed through FRED are limited to a rolling three-year window; direct API and ALFRED-vintage checks on 13 July 2026 began on 14 July 2023, so they cannot reproduce the 2020 start;
- FRED exposes no corresponding 1-3 or 3-5 US HY series, so it cannot distinguish `SDHY` from `IHYU`;
- combining 1-3 and 3-5 IG observations would require point-in-time index weights and still would not match iBoxx eligibility exactly.

FRED API Version 2 was tested with an authenticated account against release `209`.[^fred-v2] The complete 192-series response contained no pre-restriction observations for the relevant ICE series: broad IG, IG 1-3, IG 3-5, broad HY, HY effective yield and HY semi-annual YTW all began on 14 July 2023. Version 2 therefore does not bypass ICE's rolling-history restriction, and FRED still contains no US HY maturity series. FRED remains useful for the full-history Treasury curve and for post-2023 broad credit context; it is not the maturity selector.

The broader FRED catalogue was also searched by maturity, rating and geography. Its US HY family provides broad, BB, single-B and CCC-and-lower OAS, effective yield, semi-annual YTW and total-return series. It does not publish a US HY maturity split. The investable UCITS screen does not contain clean BB-only, B-only and CCC-only peers, so changing the grid to rating buckets would replace one proxy problem with another.

Two ICE-family UCITS funds improve benchmark alignment but do not repair the intended comparison. `HYUS.LSEETF` tracks the ICE BofA US High Yield Constrained Index, close to FRED's broad HY family, but launched on 5 April 2022 and therefore misses the start of the test window.[^hyus] `STHY.LSEETF` tracks the ICE BofA 0-5 Year US High Yield Constrained Index and has sufficient return history, but FRED publishes no matching 0-5 analytics.[^sthy] Replacing `IHYU` and `SDHY` with these funds changes the wrapper while leaving the missing short-HY signal unresolved.

The four-fund iBoxx grid is therefore both the best **economic universe** and an executable free-data universe for the intended maturity-within-quality experiment. FRED is no longer on the critical path. A separate `short_credit_quality_tilt` based on broad IG-versus-HY ICE OAS would answer a different question—quality timing at roughly constant maturity—and must not replace or be relabelled as the four-bucket yield selector.

BlackRock's public UCITS holdings download accepts an `asOfDate` and returned verified files throughout the full test window.[^blackrock-holdings] Its rows provide actual UCITS holdings, weights and ISINs. The US product-data endpoint accepts the same `asOfDate` and supplies `yieldToWorst` and `modifiedDuration` for the same securities. Joining them solves the maturity-observation problem without coupon-over-price reconstruction and without using current holdings in past decisions.

The present verdict is therefore:

> [!success] The free-data yield selector is established
> Free first-party data support a causal 2020-2026 `SDIG`-versus-`LQDE` and `SDHY`-versus-`IHYU` rank on UCITS-weighted security-level YTW and modified duration. This is sufficient to implement and test `yield_proxy_bucket_selector`. It is not sufficient to call the signal observed option-adjusted credit carry, because exact OAS, spread duration and credit-curve roll-down remain unavailable.

The implementation contract is: retrieve both issuer surfaces for a common as-of date; content-address and atomically cache the raw responses; join only exact ISINs; reject a fund-date below 90% matched fixed-income weight; aggregate YTW and modified duration with the UCITS weights; deduct the documented TER; make the observation tradable no earlier than the next session; and fall back to the static credit allocation when a fresh common snapshot cannot be obtained. Live refresh repeats the identical operation on the newest common date. A Treasury-curve excess-yield estimate may be reported under that exact name, but it must not be called OAS. The static control remains mandatory because a now-observable active signal has not yet demonstrated incremental portfolio value.

## First implementation result

Run `20260713T200047206608Z_demeter_eu_credit_bucket_yield` executed the seven preregistered cells over four expanding walk-forward folds. Each fold used a fixed 252-session held-out year and an expanding prior selection history. The leading active cell used a 25 bp-per-duration-year penalty and a four-year portfolio modified-duration cap. Its mean held-out standalone carry-income utility was `0.0112`, versus `0.0085` for the static broad-credit control. Mean held-out Sharpe was `0.44` versus `0.39`, and mean held-out total return was `1.72%` versus `1.60%`. The difference is economically small and the leading active cell made only the initial two fund purchases in each held-out fold.

The earlier scratch `floor_gate.py` result is superseded by the locked-config evaluator in [[paired-floor-strategy-evaluation]]. That evaluator reproduces the actual locked Atalanta and active Demeter Candidates through the production simulation path and compares a fixed monthly `60/40` return mix without hindsight leg-volatility normalization. Over 70 complete common months, the composite raises Sharpe from `1.34` to `1.51`, improves maximum drawdown from `-10.47%` to `-4.79%`, and improves the worst month from `-7.08%` to `-3.36%`. Full-sample carry/trend correlation is `0.004`; conditional correlation in trend's seven worst-decile months is `-0.814`.

The price is material. Annualized return falls from `14.19%` to `10.29%`, and MPPM certainty equivalent falls from `12.28%` to `9.37%`, a `-2.91` percentage-point marginal contribution. Paired circular-block bootstrap intervals at `1`, `3` and `6` months contain zero for both MPPM delta and Sharpe delta. Because both Candidates were selected on overlapping history, these intervals are descriptive rather than fresh out-of-sample evidence.

> [!warning] Retain as a challenger, not a promoted concave pole
> The free-data YTW proxy is causal and executable, and the locked active Candidate is genuinely diversifying and drawdown-reducing beside locked trend on this history. It does not yet demonstrate stable positive marginal economic value, and its standalone advantage is chiefly a persistent duration choice rather than recurring carry selection. Keep it as a reproducible `credit_income` challenger; do not call it observed OAS carry or treat the July 2026 reused-history comparison as a promotion test.

## Source grades and unresolved data work

- Koijen et al.: peer-reviewed JFE, generic carry origin, AQR affiliation.[^koijen]
- Nozawa: peer-reviewed Journal of Finance and Federal Reserve working version, no product conflict.[^nozawa]
- Dickerson, Robotti and Rossetti: 2026 working paper with open code and data, not yet peer-reviewed.[^drr]
- FTSE Russell: index-provider methodology with construction detail and product conflict.[^ftse]
- Bektic and Regele: peer-reviewed tactical-credit result, mild industry conflict.[^bektic]
- BlackRock pages and factsheets: authoritative instrument facts, not evidence of an expected-return edge.[^lqdh]
- IHYU's official page establishes the selected broad-HY instrument and its comparability to SDHY; it does not establish a premium.[^ihyu]

The economic instrument screen and the minimum free-data contract are closed. The next step is to implement the four-bucket source and `yield_proxy_bucket_selector`, then compare it with `credit_income_static` under the preregistered portfolio-level tests. Exact OAS, spread duration and credit-curve roll-down remain optional licensed-data upgrades rather than blockers for this narrower experiment.

## Sources

[^koijen]: Koijen, Moskowitz, Pedersen & Vrugt, "Carry", Journal of Financial Economics 127(2):197-225, 2018. Defines credit carry as credit spread plus credit-curve roll-down on duration-adjusted portfolios; carry downturns cluster in recessions and liquidity crises. Pedersen was AQR-affiliated. https://pages.stern.nyu.edu/~lpederse/papers/Carry.pdf
[^ftse]: FTSE Russell, "The Carry Concept", Fixed Income Factor Research Series, 2019. Corporate implementation combines Treasury yield, corporate spread and Treasury-curve roll-down under constant OAS, with duration constraints and transaction-cost-aware optimization. Index-provider COI. https://www.lseg.com/content/dam/ftse-russell/en_us/documents/research/ftse-fixed-income-factor-research-series-carry-concept.pdf
[^ipr]: Israel, Palhares & Richardson, "Common Factors in Corporate Bond Returns", Journal of Investment Management 16(2):17-46, 2018. Bond-level long-only evidence favors value and momentum more strongly than carry; AQR-affiliated authors. https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2576784
[^drr]: Dickerson, Robotti & Rossetti, "The Corporate Bond Factor Replication Crisis", working paper, 2026. After correcting latent implementation and look-ahead biases, 26 of 432 specifications survive false-discovery control, concentrated in credit-spread value; open data and code. https://arxiv.org/abs/2604.07880
[^nozawa]: Nozawa, "What Drives the Cross-Section of Credit Spreads? A Variance Decomposition Approach", Journal of Finance 72(5):2045-2072, 2017. Expected credit loss and expected excess return each explain about half of cross-sectional spread variance; market time-series variation is mainly risk premium. https://doi.org/10.1111/jofi.12524
[^bektic]: Bektic & Regele, "Exploiting Uncertainty with Market Timing in Corporate Bond Markets", Journal of Asset Management 19:79-92, 2018. Moving-average timing on OAS-sorted US IG and HY portfolios survives modeled costs and factor controls; authors had asset-management affiliations. https://doi.org/10.1057/s41260-017-0063-6
[^hoffstein]: Hoffstein, "Tactical Credit", Newfound Research, 2019. Across about 1,800 HY/core switching specifications, removing 2000-2003 and 2008-2009 cuts annualized return from 2.9% to 1.6%; independent practitioner counter-case. https://blog.thinknewfound.com/2019/06/tactical-credit/
[^lqdh]: BlackRock, "iShares $ Corp Bond Interest Rate Hedged UCITS ETF", official fund page and February 2026 factsheet. Reports IE00BCLWRB83's holdings, distributions, YTM, TER and effective duration; issuer data, not return evidence. https://www.blackrock.com/ch/individual/en/products/257320/ishares-corporate-bond-interest-rate-hedged-ucits-etf
[^ihyu]: BlackRock, "iShares $ High Yield Corp Bond UCITS ETF", official fund page, data at 11 June 2026. `IE00B4PY7Y77`; iBoxx USD Liquid High Yield Capped; launched 13 September 2011; monthly rebalance; 1,349 holdings; 3.14 effective duration; 6.57% weighted YTM; 0.50% TER. Issuer data, not return evidence. https://www.ishares.com/ch/individual/en/products/251833/ishares-high-yield-corporate-bond-ucits-etf
[^sdig]: BlackRock, "iShares $ Short Duration Corp Bond UCITS ETF", official fund page. `IE00BCRY5Y77`; USD distributing LSE line `SDIG`; iBoxx USD Liquid Investment Grade 0-5; launched 16 October 2013; physical sampling; quarterly distributions; 0.20% TER. https://www.blackrock.com/uk/individual/products/258126/ishares-short-duration-corporate-bond-uci_61
[^sdhy]: BlackRock, "iShares $ Short Duration High Yield Corp Bond UCITS ETF", official fund page. `IE00BCRY6003`; USD distributing LSE line `SDHY`; iBoxx USD Liquid High Yield 0-5 Capped; launched 15 October 2013; physical sampling. https://www.blackrock.com/se/intermediaries/products/258128/ishares-short-duration-high-yield-corporate-bond-ucits-etf
[^lqde]: BlackRock, "iShares $ Corp Bond UCITS ETF", official fund page. `IE0032895942`; USD distributing LSE line `LQDE`; iBoxx USD Liquid Investment Grade; launched 16 May 2003; physical sampling; monthly rebalance; quarterly distributions; 0.20% TER. The tracked index changed from the iBoxx USD Liquid IG Top 30 to the broad iBoxx USD Liquid IG index in March 2013, before the research window. https://www.blackrock.com/uk/individual/products/251832/
[^fred-ig13]: Federal Reserve Bank of St. Louis / ICE Data Indices, "ICE BofA 1-3 Year US Corporate Index Option-Adjusted Spread", `BAMLC1A0C13Y`. Exact ICE subset definition and current availability notice. https://fred.stlouisfed.org/series/BAMLC1A0C13Y
[^fred-ig35]: Federal Reserve Bank of St. Louis / ICE Data Indices, "ICE BofA 3-5 Year US Corporate Index Option-Adjusted Spread", `BAMLC2A0C35Y`. Exact ICE subset definition and current availability notice. https://fred.stlouisfed.org/series/BAMLC2A0C35Y
[^fred-hy]: Federal Reserve Bank of St. Louis / ICE Data Indices, "ICE BofA US High Yield Index Option-Adjusted Spread", `BAMLH0A0HYM2`. Broad HY series, index construction and current availability notice. https://fred.stlouisfed.org/series/BAMLH0A0HYM2
[^fred-v2]: Federal Reserve Bank of St. Louis, "FRED API Version 2", 2025. Describes an authenticated bulk-release API intended to return observations for every series in a release and the entire history; whether ICE's newer redistribution limit also applies must be tested. https://fred.stlouisfed.org/docs/api/fred/v2/release_observations.html
[^hyus]: BlackRock, "iShares Broad $ High Yield Corp Bond UCITS ETF", official fund materials. `IE00BG0J4957`; USD distributing LSE line `HYUS`; tracks the ICE BofA US High Yield Constrained Index; launched 5 April 2022. Issuer source and benchmark-alignment evidence, not return evidence. https://www.ishares.com/ch/individual/en/products/326090/ishares-broad-high-yield-corp-bond-ucits-etf
[^sthy]: PIMCO, "PIMCO Advantage US Short-Term High Yield Corporate Bond UCITS ETF", official fund page and factsheet. `IE00B7N3YW49`; USD LSE line `STHY`; tracks the ICE BofA 0-5 Year US High Yield Constrained Index; fund inception 14 March 2012. Issuer source and benchmark-alignment evidence, not return evidence. https://www.pimco.com/gb/en/investments/etf/pimco-advantage-us-short-term-high-yield-corporate-bond-ucits-etf/artf-usd-income
[^blackrock-holdings]: BlackRock, SDHY public dated holdings endpoint. The issuer endpoint returned CSV snapshots for `asOfDate=20201231` and `asOfDate=20260630`; its fields were inspected directly on 13 July 2026. https://www.ishares.com/uk/individual/en/products/258128/fund/1506575576011.ajax?fileType=csv&fileName=SDHY_holdings&dataType=fund&asOfDate=20201231
[^blackrock-product-data]: BlackRock/iShares, US product-data `holdings.all` endpoint for SHYG. The first-party, keyless response exposes point-in-time ISIN, yield-to-worst, modified duration and other bond fields and accepted arbitrary tested `asOfDate` values from August 2020 through June 2026. The equivalent SLQD, LQD and HYG product IDs were tested through the same endpoint. https://www.ishares.com/varnish-api/blk-one01-product-data/product-data/api/v2/get-product-data?appSubType=ISHARES&appType=PRODUCT_PAGE&component=holdings.all&locale=en_US&portfolioId=258100&targetSite=us-ishares&userType=individual&excludeContent=true&asOfDate=20200831
[^blackrock-shyg]: BlackRock, "iShares 0-5 Year High Yield Corporate Bond ETF," official product page. The portfolio-characteristics definition states that the displayed yield-to-maturity field uses yield-to-worst for callable bonds and excludes fees and expenses. https://www.ishares.com/us/products/258100/ishares-05-year-high-yield-corporate-bond-etf
