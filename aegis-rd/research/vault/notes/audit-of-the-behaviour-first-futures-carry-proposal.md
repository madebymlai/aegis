---
title: Audit of the Behaviour-First Futures Carry Proposal
date: 2026-07-20
topic: convergent-strategy-design
status: active-research
related:
  - "[[the-tiered-strategy-roster]]"
  - "[[carry-is-not-one-premium]]"
  - "[[commodity-carry-constructions]]"
  - "[[finding-a-buildable-convergent-engine]]"
tags:
  - note
  - demeter
  - carry
  - futures
  - research-audit
---

# Audit of the Behaviour-First Futures Carry Proposal

> [!abstract] Decision
> The report found a legitimate **candidate family**, but it did not establish alpha and its exact rule is not ready to implement. The original cadence preference materially steered the search toward monthly, twelve-month-smoothed carry. That bias does not invalidate cross-asset carry; it invalidates the claim that this is the strongest behaviour-first winner across all cadences. The correct next step is a small, preregistered futures-curve feasibility and residual-return study—not promotion into Demeter.

## What survived the audit

Cross-asset carry has a real economic and empirical basis. Koijen et al. define carry as the return under unchanged market conditions and find predictive evidence across several asset classes, while also showing that common recession, liquidity and volatility risks matter.[^koijen] This makes carry a plausible candidate for the ordinary-market seat beside trend, but the premium is not automatically alpha. As [[carry-is-not-one-premium]] stresses, the realized return also contains spot repricing, curve change, financing, collateral, currency translation and costs.

The report also made two sound implementation choices: use actual futures curves rather than an ETF's distribution yield, and test marginal whole-book utility beside trend rather than promote on standalone Sharpe. Slow signals and turnover control are credible challengers. They are not, however, established constants of the best strategy.

## Cadence bias was material

The report did not discover monthly trading and twelve-month smoothing from an open comparison. It installed them in the winner's definition, used slow implementation as a reason to prefer carry, and rejected faster candidates partly for their cadence and operational burden. It never separated:

- the cadence at which new information is observed;
- the cadence at which target weights are recomputed;
- the realized cadence of trades after a no-trade policy.

That omission matters in Aegis. The shared `DriftBand` holds the realized weight inside directional absolute weight bands and trades only on a breach; the same gate is used to preserve research/live parity.[^drift] Therefore a daily signal evaluation need not imply daily trading. The report's proposed “10% of current gross position” band is also not the Aegis contract: Aegis applies configured directional weight-point widths around the target, with an optional interior destination.

The corrected conclusion is narrower:

> Monthly smoothed carry is a defensible low-turnover candidate generated under a slow-cadence prior. It is not yet the cadence-optimal or globally strongest convergence strategy.

## Other prompt-induced biases

Cadence was not the only leading influence. The brief also carried:

- **adverse-prior anchoring**, because failed credit-fund, catastrophe-bond, merger and reversal implementations were summarized before the wide search and could be mistaken for family-level verdicts;
- **data-availability and operational-simplicity bias**, because public inexpensive data, sparse positions and low infrastructure burden were allowed to influence the mechanism ranking rather than being reported as a separate buildability ranking;
- **published-premium bias**, because demanding a literature-backed complete rule naturally favors mature factors over novel but falsifiable behavioural hypotheses;
- **payer-story bias**, because an economically satisfying narrative can appear stronger than the empirical identification supporting it;
- **forced-winner bias**, because requiring a single complete algorithm encouraged unsupported numerical choices; and
- **holdout leakage**, because the brief itself highlighted the post-2022 regime, making that period part of the researcher's information set before it was later labelled untouched.

The portfolio-role constraints are not errors: requiring complementarity with trend, positive marginal whole-book utility, causal information and realistic costs is the mandate. The correction is to map candidates independently, rank evidence strength separately from buildability, treat prior failures as implementation-specific, and permit an unresolved experiment instead of a fabricated winner.

## Clarified intended research process

> [!important] Objective
> The objective is not to select the published strategy family that best fits Demeter. It is to research recurrent market behaviours and compose independently supported behaviours into a distinct, causal return hypothesis for the convergent seat.

The intended chain is:

\[
\text{behaviour ledger}
\rightarrow
\text{ex-ante interaction hypotheses}
\rightarrow
\text{machine-specifiable composed signals}
\rightarrow
\text{factor-residual tests}
\rightarrow
\text{prospective alpha evidence}
\]

The first research stage must therefore remain free of strategy labels and previous implementation rankings. It records actors or mechanisms, constraints, observable footprints, affected states, forecast type, information delay, horizon, decay and break state. Only after the individual behaviours are validated may the researcher combine them. Each composition must explain what unique information every behaviour supplies, why the conjunction forecasts a return, and why it should beat each constituent alone before combined returns are inspected.

Every resulting rule element must be tagged as **established**, **derived**, **borrowed** or **hypothesized**. The final result must also be classified as a **replication**, **adaptation**, **composition** or **speculation**. A known factor with execution changes may be useful, but it is not newly produced alpha. The received smoothed futures-carry proposal is currently an adaptation: it maps several behaviours to a published carry family and adds unsupported implementation choices rather than demonstrating incremental information from a new behavioural interaction.

## Why the exact rule is not evidence-backed alpha

The report combines several published ideas into a new rule: within-class demeaned ranks, a twelve-month mean, a three-times-cost hurdle, inverse-volatility sizing, equal class risk, an 8% sleeve target, 12% market caps, 40% class caps and a 10% band. The cited papers do not validate that exact bundle. Each fixed number is another research degree of freedom.

The strongest contradiction is in the proposed launch universe. In Baltas's cross-sectional results, government bonds and equity indices were the stronger sleeves, while FX and commodities had much weaker standalone Sharpe ratios; the report excludes rates but launches FX and commodities.[^baltas] The recent negative out-of-sample study is also specifically a 48-country **FX** carry study. It supports caution about the FX lane, not a blanket rejection or confirmation of all cross-asset carry.[^hsu]

“Residual alpha” must mean more than positive carry return. The exact candidate must retain positive return after:

1. passive exposure to the same markets;
2. standard trend exposure on the same contracts;
3. market, dollar, duration, commodity and volatility factors relevant to each sleeve;
4. financing, collateral, commissions, spreads, FX conversion and integer-contract loss.

Until then, the honest label is **candidate convergent risk premium**, not alpha.

## Internal design defects

1. **One curve formula is not one carry definition.** The adjacent-contract log slope is a useful primitive for many commodity futures, but equity-index futures embed financing and dividends, currency futures require correct quote orientation and interest-differential treatment, and government-bond futures require delivery-option, cheapest-to-deliver and duration treatment. Commodity agriculture and energy also need seasonal controls. A common portfolio may use asset-specific primitives; it should not pretend the raw front/second ratio is economically identical everywhere.[^koijen][^commodity]

2. **Carry is not “curve normalization.”** It is the unchanged-state return. Actual profit can be offset by spot movement and curve reshaping, and a roll price gap is not cash collected. Backtests must book the P&L of the dated contracts actually held.[^commodity]

3. **The selection rule disagrees with itself.** The action formula and pseudocode allocate across every eligible rank, while the exit rule says to hold only the top and bottom thirds. Those define different portfolios and different turnover. The research design must choose one before testing.

4. **The cost hurdle is dimensionally underspecified.** “Three times annualized round-trip cost” depends on expected holding time, turnover, contract multiplier, spread, commission, FX and integer projection. A projected trade should clear its marginal implementation cost; an arbitrary annualized multiplier is not a substitute.

5. **The 8% sleeve target duplicates the allocator's job.** The strategy should emit a stable unit-risk exposure; the allocator assigns sleeve risk and whole-book leverage. An 8% normalization can be a reporting convention, not an alpha parameter.

6. **Three names do not create a robust within-class cross-section.** `N >= 3` produces an unstable rank portfolio, especially among a few major equity-index contracts. Breadth and effective independent bets must be measured, not inferred from asset labels.

7. **The proposed holdout is contaminated.** The report used post-2022 behaviour to exclude rates and choose launch lanes, then called January 2022–June 2026 untouched. That interval is now validation data. Only a newly frozen prospective period is untouched.

8. **Twenty-four monthly live observations cannot validate a crash-sensitive premium.** They may validate plumbing and costs, but not tail behaviour or stable residual alpha.

## Aegis feasibility

The current Atalanta champion is not a futures sleeve. Its active config trades `IDTL.LSEETF`, `IGLN.LSEETF` and `WCOA.LSEETF` from daily `OHLCV`.[^atalanta] Reusing “the same futures universe already used for trend” is therefore false for the promoted configuration. Archived experiments contain a broad futures universe, but use an older config surface and are not the current champion.

Aegis does have important substrate already:

- the current run schema accepts bare roots through `data.futures` and resolves them to catalog-authoritative continuous instruments;[^schema]
- the data layer can assemble dated contract chains, select a liquid cycle from daily volume and materialize adjusted continuous OHLCV;[^chain]
- custom arrays can be loaded into the eager indicator bundle.[^arrays]

What is missing for this proposal is the deep market-data seam that exposes a **simultaneous, point-in-time front/deferred curve** to an indicator. The current continuous materializer consumes the dated legs and returns one adjusted OHLCV frame. It does not expose the pair of contemporaneous settlements, their expiries and a causal maturity gap as a configured array. Volume exists for liquid-cycle selection; no current open-interest array was found. This is a bounded capability gap, but it means the proposed indicator cannot be written honestly against today's `Close` panel alone.

## Minimal decisive research sequence

1. Prove the data contract first: point-in-time front, second and optionally deferred settlements; expiries; volume; roll identity; and actual transaction-cost inputs for a frozen root universe.
2. Define asset-specific carry primitives. Start with commodities and correctly adjusted equity/FX futures; omit rates until a proper bond-futures definition exists.
3. Preregister a small family only: cross-sectional versus time-series, raw versus one slow smoother, and daily/weekly/monthly target updates. Apply the existing Aegis drift band at each update and report both target changes and actual trades.
4. Simulate causal dated-contract P&L and account for financing, collateral and FX exactly once. Let the allocator control sleeve risk.
5. Compare cash, passive same-market exposure, trend alone, and trend plus carry at matched whole-book risk. Attribute residual return by asset class and factor.
6. Treat 2022–2026 as validation, not holdout. Freeze the final design and require new prospective evidence.

> [!success] Bottom line
> The report can lead to an alpha test, not directly to alpha. Futures carry deserves one disciplined feasibility study because its mechanism and trend distinctness are plausible. The exact monthly twelve-month-smoothed rule should not be implemented as received.

## Sources

[^koijen]: Koijen, Moskowitz, Pedersen and Vrugt, “Carry,” *Journal of Financial Economics* 127(2), 2018. https://doi.org/10.1016/j.jfineco.2017.11.002
[^baltas]: Baltas, “Optimising Cross-Asset Carry,” 2017; primary author manuscript and SSRN record. https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2968677
[^hsu]: Hsu, Taylor, Wang and Li, “The Out-of-Sample Performance of Carry Trades,” *Journal of International Money and Finance* 143, 2024. This study concerns FX carry. https://doi.org/10.1016/j.jimonfin.2024.103042
[^commodity]: [[commodity-carry-constructions]] synthesizes the executable-contract, seasonal and roll-accounting distinctions from the primary commodity literature.
[^drift]: `aegis-runtime/aegis_runtime/drift_band.py`, especially `gate` and `DriftBand.resolve`.
[^atalanta]: `aegis-rd/research/configs/atalanta/trend_floor.yaml`.
[^schema]: `aegis-rd/research/aegis_research/configuration/schema.py`, `DataConfig.futures`, and `market_data/identity.py`, `resolved_instruments`.
[^chain]: `aegis-data/aegis_data/chain.py`, `fetch_contract_chain`, and `continuous_contract_model.py`, `_materialize_frame`.
[^arrays]: `aegis-rd/research/aegis_research/market_data/adapters/catalog.py`, `_array_panels`, and `market_data/panels.py`, `market_data_bundle`.
