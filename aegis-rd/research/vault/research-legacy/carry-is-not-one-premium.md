---
title: "Carry Is Not One Premium"
date: "2026-07-11"
topic: carry
distilled-into:
tags:
  - article
---

# Carry Is Not One Premium

> [!abstract] One-line takeaway
> Carry is a common accounting definition, not a common economic bet: it is the return under unchanged market conditions, while the reason that return may persist, reverse, or crash differs by asset class.

## Start from an invariant definition

Carry is the return an instrument would earn if the relevant market state did not change over the holding period. This futures-based definition is observable before the trade and gives the identity

$$\text{expected return}=\text{carry}+\text{expected price appreciation}.$$

It does not say expected price appreciation is zero. Uncovered interest parity and the expectations hypothesis are precisely claims that adverse price movement offsets the quoted carry. A carry signal becomes an expected-return signal only when that offset is incomplete.[^koijen]

This distinction prevents three common errors. Yield is not total return. A steep curve is not automatically profitable. A high quoted premium can be the market's warning that adverse repricing is likely. Carry should therefore be recorded alongside the later price-change component, not used as its substitute.

## One measurement language, several mechanisms

In currencies, carry is the interest-rate differential, and the other side is partly a global-volatility and funding-liquidity exposure. High-rate currencies tend to lose when global FX volatility rises, while funding currencies hedge that state.[^menkhoff] In commodities, basis reflects scarcity, inventories, and convenience yield; low inventories are associated with backwardation and higher subsequent futures risk premia.[^gorton] In government bonds, carry combines curve slope with roll-down, but duration makes raw carry mechanically larger, so comparisons require duration normalization.[^koijen] In credit, spread plus roll-down is payment for default, downgrade, liquidity, and recession exposure. In options, theta and volatility-surface roll-down are explicit insurance premia.

Those mechanisms can coexist in one portfolio without being interchangeable. A commodity producer's hedge demand, a leveraged FX investor's funding constraint, and an option buyer's crash insurance demand are different counterparties with different reasons for paying. The shared label is useful for return decomposition, not proof of a single latent premium.

| Carry family | What is collected | Structural payer | Primary failure state |
|---|---|---|---|
| FX | Interest differential | Hedgers and constrained borrowers | Funding unwind and funding-currency rally |
| Commodity | Curve slope and convenience yield | Producers, consumers, and inventory holders | Scarcity shock and curve inversion |
| Credit | Spread above expected default loss | Borrowers and protection demand | Default, downgrade, and liquidity shock |
| Rates | Curve roll-down and term premium | Duration hedgers and borrowers | Inflation and rate repricing |
| Equity | Dividend and implied financing carry | Firms' capital demand and financing markets | Growth and valuation shock |
| Volatility | Implied variance above subsequently realized variance | Protection buyers | Jump and volatility explosion |

This table is a research prior, not an attribution result. The marginal payer can change, and several rows can load on the same intermediary constraint.

## Six distinctions that keep the taxonomy honest

**Mechanical accrual is not expected excess return.** Carry states what happens if the market state is unchanged. The price can move enough to offset it.

**Carry level is not carry richness.** A yield is a level. Richness asks whether it is high relative to expected loss, history, comparable instruments, and risk. [[what-makes-a-convergent-sleeve-an-income-engine]] develops this distinction for credit.

**Cross-sectional carry is not time-series carry.** The first buys high-carry assets and sells low-carry peers. The second takes exposure when an asset's own carry clears a reference level. They differ in beta, breadth, and crash exposure.

**Gross carry is not financing-adjusted carry.** Financing, collateral remuneration, borrow, margin, and currency hedging must be included exactly once, under a declared numeraire.

**Expected carry is not realized roll return.** Curve convergence, spot repricing, and curve reshaping occur during the holding period. No price gap is collected merely because contracts are exchanged.

**Carry is not value, momentum, or beta.** High carry can coincide with cheapness, prior returns, duration, dollar, credit, commodity, or volatility exposure. Attribution must test those alternatives rather than relabel them.

## Decompose the return before optimizing it

$$
R = C_{\text{mechanical}} + \Delta P_{\text{spot}} + \Delta P_{\text{curve}}
+ F_{\text{financing}} + Y_{\text{collateral}} + X_{\text{FX}} - K_{\text{costs}}.
$$

Some terms are zero or combined for particular instruments, but none may be silently counted twice. This identity shows whether a backtest harvested the intended premium or benefited from falling rates, dollar exposure, market beta, or a collateral convention.

## Static income and dynamic selection

A long-high, short-low carry portfolio earns from two sources. Static carry is what yesterday's positions earn if states do not change. Dynamic carry comes from changing weights as signals and relative rankings move.[^koijen] This matters because turnover, migration between ranks, and rebalancing can make a strategy look better than the underlying income stream. A credible report should show static carry, price appreciation, weight-change contribution, financing, and costs separately.

The taxonomy also sharpens diversification. Low average correlation between carry sleeves does not imply independent tail risk. Their ordinary mechanisms differ, but recession, volatility, liquidity, and deleveraging shocks can make them fail together. Commodity implementations are treated separately in [[commodity-carry-constructions]].

## Construct, stress, and condition the portfolio

Normalize duration, volatility, financing, and currency exposure before sizing. Begin with equal risk by mechanism, slow volatility estimates, and caps by instrument, asset class, funding currency, and cluster. Covariance optimization should be a challenger: across broader allocation problems, 14 optimized policies failed to beat 1/N consistently out of sample because estimation error overwhelmed theoretical efficiency.[^demiguel]

Expose rank versus z-score weights, cross-sectional versus time-series formation, neutrality constraints, long-short versus long-only implementation, position caps, and buffers. Neutralization is an experiment. Removing dollar, duration, commodity, or credit beta may isolate carry, or remove the risk for which carry is paid. Show raw and neutralized versions and how much premium disappears.

FX funding unwinds, rate inflation shocks, credit defaults, commodity scarcity, and option-volatility jumps are distinct tails. They become one event when margins rise, dealer capacity falls, and investors reduce risk together. Measure stress-state correlation and co-expected-shortfall, not only ordinary correlation. Crowding proxies include positioning relative to open interest, flows, carry extremity, dealer inventories, margin changes, and turnover relative to stressed depth.

Conditioning must distinguish timing return, risk, leverage, premium existence, and strategy identity. A volatility mute may improve Sharpe by removing the negative skew for which carry is paid. Prefer slow causal states and monotone throttles; freeze the state, lag, threshold, and fallback exposure; and count every attempted rule. Carry strategies selected in sample are generally unstable later after data-snooping corrections.[^hsu]

## A carry-specific trust checklist

- Yield or spread is not total expected return, and roll yield is not earned without convergence.
- Overlapping contracts create serial dependence; stale bond prices inflate smoothness; bid-ask bounce can manufacture predictability.
- Backfilled curves, hindsight contract selection, and reuse of one noisy price in signal and next return can leak information.
- Financing and collateral must be counted once; defaults, delistings, and failed currencies must remain in the universe.
- Long-only proxies can embed beta absent from an academic long-short factor.
- Preserve every tried signal, horizon, threshold, universe, and weighting rule; deflate performance for selection and non-normality.[^dsr]

## Design rule

Define the invariant first, then specify five asset-specific items: market state held constant, observable carry quote, expected adverse price adjustment, structural counterparty, and dominant tail state. Only compare signals after duration, volatility, financing, and currency exposure are normalized. This turns “carry” from a slogan into an auditable family of trades.

Signal horizon, rebalance horizon, and expected convergence horizon must match. Estimate persistence and forward returns at non-overlapping horizons, then trade no faster than the information decays.

## Limitations

The invariant definition is model-free, but implementation is not. Synthetic futures, interpolation, option surfaces, credit curves, and collateral conventions introduce choices. Koijen et al. provide the unifying empirical anchor but several authors are AQR-affiliated. The mechanism map above is a synthesis across literatures, not evidence that each mechanism is uniquely identified.

## Strategy hypotheses this could seed

- [ ] Decomposing each sleeve into static carry and price appreciation predicts its tail behavior better than the headline carry signal alone.
- [ ] A mechanism-balanced carry portfolio has lower conditional drawdown than a portfolio diversified only by asset-class labels at matched volatility.
- [ ] Duration- and financing-normalized carry rankings are more stable out of sample than raw-yield rankings.

## Sources

[^koijen]: Koijen, Moskowitz, Pedersen and Vrugt, "Carry", *Journal of Financial Economics* 127(2), 2018 - defines carry as return under unchanged prices, decomposes static and dynamic returns, and tests it across eight asset classes; Moskowitz and Pedersen are AQR-affiliated. https://doi.org/10.1016/j.jfineco.2017.11.002
[^menkhoff]: Menkhoff, Sarno, Schmeling and Schrimpf, "Carry Trades and Global Foreign Exchange Volatility", *Journal of Finance* 67(2), 2012 - global FX volatility risk prices the currency carry cross-section. https://doi.org/10.1111/j.1540-6261.2012.01728.x
[^gorton]: Gorton, Hayashi and Rouwenhorst, "The Fundamentals of Commodity Futures Returns", *Review of Finance* 17(1), 2013 - connects basis and subsequent futures returns to inventories and the theory of storage. https://www.nber.org/papers/w13249
[^demiguel]: DeMiguel, Garlappi and Uppal, "Optimal Versus Naive Diversification", *Review of Financial Studies* 22(5), 2009 - 14 optimized models do not consistently beat 1/N out of sample. https://doi.org/10.1093/rfs/hhm075
[^hsu]: Hsu, Taylor, Wang and Li, "The Out-of-Sample Performance of Carry Trades", *Journal of International Money and Finance* 143, 2024 - finds instability after data-snooping corrections. https://doi.org/10.1016/j.jimonfin.2024.103063
[^dsr]: Bailey and López de Prado, "The Deflated Sharpe Ratio", *Journal of Portfolio Management* 40(5), 2014 - adjusts Sharpe inference for selection and non-normal returns. https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460551
