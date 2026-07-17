---
title: "Commodity Carry Constructions"
date: "2026-07-11"
topic: carry
distilled-into:
tags:
  - article
---

# Commodity Carry Constructions

> [!abstract] One-line takeaway
> Commodity carry is not the price gap paid on roll day; it is a family of curve signals whose realized return depends on convergence, contract choice, seasonality, liquidity, and the spot-versus-term component being harvested.

## Roll yield is not a roll-day cash flow

Selling an expiring contract and buying a more expensive deferred contract compares two different instruments. The price gap is not itself a loss. P&L accrues as the held futures contract changes and, near expiry, converges toward spot. Splicing raw contract prices creates artificial jumps; back-adjusting can make a chart useful for returns while destroying its price level.[^cme]

The clean primitive is the annualized log slope between two tradable contracts, with signs declared explicitly. That signal can forecast return, but it is not the return. A backtest must calculate P&L from actual contract holdings and roll trades rather than differences in an adjusted continuous series.

## The curve contains more than one premium

Storage theory links inventories, convenience yield, and the curve. Scarce inventory raises the value of immediate ownership, tends to produce backwardation, and is associated with higher subsequent futures returns.[^gorton] Yet a basis sort mixes two outcomes. Szymanowska et al. separate spot premia from term premia and find large spot spreads of roughly 5% to 14% a year and smaller term premia of roughly 1% to 3%, often with opposite signs.[^anatomy] A strategy can classify the curve correctly and still misattribute where its profit came from.

That decomposition suggests reporting four legs: change in the held contract, convergence conditional on unchanged spot, curve-shape change, and execution/collateral. It also explains why “backwardation wins” is too coarse. Unexpected supply shocks can dominate convergence; a curve can reshape before the contract reaches expiry.

## Construction choices are economic choices

Nearby slope is responsive to scarcity but exposed to expiry effects and crowded rolls. Longer-deferred slope is smoother but usually less liquid. Fixed calendar rolls are reproducible; volume/open-interest rolls track market migration but embed an endogenous rule. Constant-maturity interpolation avoids maturity jumps but creates a synthetic daily rebalance that may not match executable trades.

Agriculture and energy require seasonal comparisons. Ranking December natural gas against January using the same raw slope as two metals contracts confounds storage seasonality with expected return. Signals should be standardized within commodity and calendar location, using only information available at formation. Contract exclusions, first-notice dates, limit moves, multipliers, and collateral yield are part of the strategy definition.

Combining term structure with momentum can improve historical commodity portfolios, but the double sort reduces breadth and may merely select the strongest inventory shocks.[^fuertes] It should be treated as an interaction hypothesis, not proof that two independent premia were combined.

| Construction | Intended harvest | Main contaminant |
|---|---|---|
| Long backwardation, short contango | Cross-sectional scarcity premium | Sector, spot beta, and seasonal composition |
| Front-versus-deferred calendar spread | Relative curve convergence | Maturity liquidity and delivery optionality |
| Constant-maturity exposure | Stable maturity return | Synthetic daily rebalancing and interpolation |
| Cross-sectional curve rank | Relative carry | Small breadth and persistent sector clusters |
| Time-series curve exposure | Absolute carry state | Net commodity beta and threshold choice |
| Hedging-pressure sort | Producer/consumer risk transfer | Delayed positioning data and crowding |
| Inventory-conditioned carry | Scarcity mechanism | Release lags, revisions, and heterogeneous units |
| Basis or curve momentum | Persistence in curve changes | Ordinary price momentum and overlapping signals |

This explains why commodity-carry skew changes sign across studies. Directional time-series portfolios, market-neutral basis ranks, and calendar spreads do not own the same spot beta, maturity, or liquidation exposure. After removing only declared nuisance exposures, the remaining P&L must still correspond to the scarcity or risk-transfer channel.

## Match horizon to convergence

Estimate how each signal forecasts returns at one, three, six, and twelve months using non-overlapping observations or overlap-robust inference. Compare that decay with the roll and rebalance schedule. Fast trading of a slow inventory signal adds cost; holding a nearby signal beyond its convergence window changes the trade. Adjacent slopes share contracts, so apparent multi-signal breadth can be duplicated information.

## A construction ladder

The least ambiguous research sequence is: executable front-versus-next slope; front-versus-deferred slope; seasonally standardized slope; then a curve model using several maturities. Each added degree of freedom must beat the simpler signal out of sample after turnover and liquidity haircuts. [[carry-is-not-one-premium]] supplies the economic interpretation and trust checks.

## Limitations

Inventory data are delayed, revised, and not comparable across commodities. The strongest anatomy estimates are in-sample averages over a limited universe. CME's decomposition is pedagogically clear but comes from an exchange. Contract liquidity and electronic trading have changed, so historical roll-cost estimates are not constants.

## Strategy hypotheses this could seed

- [ ] Seasonally standardized curve slope outperforms raw slope out of sample in agriculture and energy, with little change in metals.
- [ ] Nearby carry has higher gross predictability but lower net performance than a deferred construction because expiry and turnover costs consume the difference.
- [ ] Separating spot and term P&L reveals that most basis-sort performance is spot repricing rather than mechanical convergence.

## Sources

[^gorton]: Gorton, Hayashi and Rouwenhorst, "The Fundamentals of Commodity Futures Returns", *Review of Finance* 17(1), 2013 - basis reflects inventories and predicts futures risk premia. https://www.nber.org/papers/w13249
[^anatomy]: Szymanowska, de Roon, Nijman and van den Goorbergh, "An Anatomy of Commodity Futures Risk Premia", *Journal of Finance* 69(1), 2014 - separates spot and term premia across 21 commodity markets. https://doi.org/10.1111/jofi.12096
[^fuertes]: Fuertes, Miffre and Rallis, "Tactical Allocation in Commodity Futures Markets: Combining Momentum and Term Structure Signals", *Journal of Banking & Finance* 34(10), 2010 - documents the historical double-sort interaction; one author later became investment-industry affiliated. https://openaccess.city.ac.uk/id/eprint/6416/
[^cme]: Erb and Harvey, "Deconstructing Futures Returns: The Role of Roll Yield", CME educational paper - explains convergence and why a roll adjustment is not a traded return; exchange-hosted practitioner source. https://www.cmegroup.com/education/files/deconstructing-futures-returns-the-role-of-roll-yield.pdf
