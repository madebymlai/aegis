---
title: ETF Flow–Discount–Liquidity Composition Hypothesis
date: 2026-07-20
topic: convergent-strategy-design
status: active-research
aliases:
  - FDL hypothesis
  - ETF FDL
related:
  - "[[the-tiered-strategy-roster]]"
  - "[[what-is-a-strategy]]"
  - "[[a-behavioural-atlas-of-ordinary-markets]]"
  - "[[finding-a-buildable-convergent-engine]]"
  - "[[audit-of-the-behaviour-first-futures-carry-proposal]]"
tags:
  - note
  - demeter
  - etf
  - flows
  - liquidity
  - convergence
  - alpha-hypothesis
---

# ETF Flow–Discount–Liquidity Composition Hypothesis

> [!abstract] Stateful decision
> **FDL is the leading genuinely composed hypothesis from the behaviour-first search, but it is not yet a strategy or demonstrated alpha.** Primary-market ETF flow is the strongest established return predictor. Liquidity mismatch is an established reason arbitrage may be slow, especially in corporate-bond ETFs, but its usable public proxy is unresolved. ETF premium or discount is an intuitive relative-value observable, yet the strongest flow paper finds premium changes weak and bond-fund NAV can be stale. The research burden is therefore to prove that discount and liquidity add incremental, causal, after-cost information beyond flow alone.

## What FDL means

FDL is shorthand for three proposed observations, not three accepted signals:

| Term | Intended information | Current status |
| --- | --- | --- |
| **F — primary-market flow** | Creation or redemption activity reveals that authorized participants responded to a relative pricing disturbance and can expose non-fundamental demand transmitted between ETF shares and underlying assets | **Established behaviour and published predictor** |
| **D — discount or premium** | The signed distance between an ETF's executable price and a causally available estimate of underlying value supplies direction and a convergence anchor | **Contested measurement and weak standalone predictor** |
| **L — liquidity mismatch** | A gap between the tradability of ETF shares and the underlying basket, together with limited arbitrage capacity, determines whether a disturbance persists long enough to trade | **Established mechanism; signal proxy unresolved** |

The proposed causal interaction is:

$$
\text{non-fundamental demand revealed by flow}
+ \text{valid relative-value displacement}
+ \text{slow arbitrage caused by liquidity mismatch}
\rightarrow
\text{temporary return forecast}
$$

This is economically attractive because the components appear to provide different information:

- **F supplies evidence that a disturbance occurred.** It is not secondary-market ETF volume, dollar AUM growth or ordinary investor subscription estimates. It is the change in ETF shares caused by primary-market creations or redemptions.
- **D is intended to supply direction and an endpoint.** It must represent an actual price-to-value gap rather than an ETF price correctly discovering stale underlying quotes.
- **L is intended to supply persistence.** It should distinguish a gap that competitive arbitrage closes immediately from one that remains because the basket is costly, incomplete, illiquid or uncertain.

If D or L does not add information beyond F, the composition fails even if a flow-only strategy remains profitable.

## What the evidence currently establishes

Brown, Davies and Ringgenberg model primary-market ETF flow as the observable footprint left when authorized participants arbitrage relative mispricing. Their empirical result is directionally clear: high-flow ETFs subsequently underperform low-flow ETFs, and a short-high/long-low portfolio earns significant excess return in their sample.[^brown] Their theory also makes a subtle distinction that matters here. Authorized participants can eliminate the **relative** ETF-versus-NAV discrepancy while transmitting the original disturbance into both ETF and underlying prices. Flow can therefore remain informative after the visible premium has already closed.

That paper is adverse evidence against installing D as a compulsory filter. It explicitly finds ETF flows to be strong signals of non-fundamental demand while ETF premium changes are not, consistent with competitive authorized participants quickly eliminating relative-price gaps.[^brown] A same-sign flow-and-premium gate could consequently discard the strongest flow observations rather than improve them.

Liquidity mismatch is nevertheless real. Pan and Zeng show that the conflict between ETF liquidity and underlying-asset illiquidity changes authorized participants' arbitrage capacity in corporate-bond ETFs.[^panzeng] The BIS documents why: bond creation and redemption baskets can cover only a small fraction of holdings, change frequently, differ between creations and redemptions, and reflect dealer inventory as well as gap-closing activity.[^bis] This weakens the simple textbook claim that a reported ETF discount is a directly deliverable arbitrage.

The same evidence weakens D again. During stressed bond markets, ETF prices may incorporate current information faster than NAVs built from stale underlying quotes. The Bank of England and BIS therefore warn that a reported discount can be price discovery rather than mispricing.[^boe][^bis] An ETF close minus official end-of-day NAV is not automatically an independent anchor.

> [!warning] Load-bearing distinction
> **Relative-price convergence and fundamental-price reversal are not the same trade.** The Brown mechanism says primary-market flow may reveal a disturbance even after ETF and NAV have reconverged to each other. The FDL hypothesis must decide whether it predicts reversal of the ETF, reversal of the underlying basket, closure of a live premium, or some hedged combination. Mixing these endpoints would make the strategy unfalsifiable.

## What is genuinely new

The existing evidence supports the components separately to unequal degrees. It does not yet establish the triple interaction:

$$
F \times D \times L.
$$

The novel claim is not that high flow predicts low returns. That is the published flow rule. The new claim would be:

> A causally measured valuation displacement and a causally measured arbitrage constraint identify the subset of primary-market flow shocks whose subsequent reversal is stronger, slower or more executable than flow alone predicts.

This claim qualifies as **composition** only if the interaction adds stable predictive information after every main effect and lower-order interaction is included. Otherwise the result is one of:

- **replication** — the Brown flow rule survives unchanged;
- **adaptation** — the flow rule survives with cost or universe changes;
- **conditioning without alpha** — D or L changes risk or turnover but not expected return;
- **failed composition** — the triple interaction is redundant, unstable or negative; or
- **speculation** — proxies are chosen after inspecting combined returns.

## Required statistical shape

The minimum nested panel specification is:

$$
r_{i,t+h}
= \alpha
+ \beta_F F_{i,t}
+ \beta_D D_{i,t}
+ \beta_L L_{i,t}
+ \beta_{FD}F_{i,t}D_{i,t}
+ \beta_{FL}F_{i,t}L_{i,t}
+ \beta_{DL}D_{i,t}L_{i,t}
+ \beta_{FDL}F_{i,t}D_{i,t}L_{i,t}
+ \Gamma X_{i,t}
+ \varepsilon_{i,t+h}.
$$

The exact estimator must respect the panel, cross-sectional dependence, overlapping horizons and repeated ETF observations. $X$ must include the return and flow controls needed to separate reversal from ordinary momentum, beta, asset-class effects and fund characteristics. The regression is a diagnostic contract, not permission to data-mine transformations.

The interaction earns promotion only if:

1. $\beta_{FDL}$ has a preregistered economic sign and survives dependent-data inference;
2. its incremental out-of-sample forecast improves on F alone and every lower-order model;
3. ranked portfolios show a stable monotonic relation, not one extreme cell;
4. the result survives causal publication lags, dead funds, revisions and realistic costs;
5. the result is not confined to one crisis or one ETF category unless the rule is explicitly narrowed before prospective testing; and
6. the full strategy adds marginal whole-book utility beside broad trend at matched risk.

A tree, threshold model or conditional ranker may later represent nonlinear interaction, but it must beat this transparent nested baseline and be frozen before prospective evaluation.

## Data contract that must be proved first

The hypothesis cannot be evaluated from OHLCV alone. A causal historical and live dataset needs:

- ETF identifier history, inception, closure, merger, split and share-class lineage;
- dated shares outstanding or actual creations and redemptions, including the publication timestamp and revisions;
- executable ETF price, spread, volume and short availability;
- contemporaneous official NAV, intraday indicative value where economically meaningful, valuation timestamp and underlying market close conventions;
- point-in-time holdings and creation/redemption baskets where the chosen L proxy requires them;
- underlying-asset liquidity measures available on the same causal clock;
- fund category, leverage/inverse status, currency, domicile, replication method and distribution treatment;
- borrow fee, recall risk, commission, FX, tax and financing assumptions; and
- survivorship-free returns for closed ETFs.

Three common substitutions are invalid:

1. **Dollar fund flow from AUM changes is not F** unless price appreciation is removed and the resulting measure is shown to match primary-market share creation/redemption.
2. **Secondary-market volume is not F.** Most ETF trading does not create or redeem shares.
3. **ETF trading liquidity is not L.** L is the mismatch between the ETF and the economic basket the arbitrageur must warehouse or deliver.

The first research deliverable is therefore a source-by-field matrix with frequency, latency, history, survivorship coverage, revision policy, license and cost. If no causal and affordable L or D measure exists, the interaction is currently unbuildable even though the mechanism is credible.

## Candidate five-question strategy contract

The current answers are deliberately incomplete. [[what-is-a-strategy]] requires that the missing parts be resolved before implementation.

### State

A primary-market flow disturbance has been observed after its true publication time. A separately measured valuation displacement and arbitrage-capacity constraint may condition eligibility **only if** they add incremental predictive information in the locked interaction test. The eligible ETF categories, signal horizons and directions remain research questions.

### Action

The published control is long low-flow ETFs and short high-flow ETFs. The composed candidate may trade ETF shares, the underlying exposure, or a hedged relative-value position, but the chosen instrument must match the claimed endpoint. Direction cannot be inferred mechanically from a reported premium when NAV may be stale. The strategy should emit a stable internal composition or unit-risk target; the allocator owns sleeve risk and whole-book leverage.

### Exit

The exit must follow the measured mechanism: decay of the flow forecast, closure of a valid relative-value displacement, disappearance of the liquidity constraint, signal reversal, or a frozen maximum information horizon. Which one dominates must be learned from causal impulse-response evidence, not selected from the best backtest.

### Payer

The provisional payer is an investor or institution submitting non-fundamental demand and valuing immediacy more than price, while authorized participants and other specialists transmit or warehouse the disturbance. Competition does not erase it immediately when capital, inventory, basket or underlying-liquidity constraints bind. The research must distinguish the AP as arbitrageur from the original demand-side payer.

### Failure

The composition is killed if D and L do not improve the flow-only forecast after costs and causal timing; if reported discounts are predominantly stale-NAV price discovery; if no reproducible public L proxy exists; if shorting and turnover consume the edge; or if the candidate does not improve the complete trend-paired return stream. A profitable F-only result does not rescue FDL—it reclassifies the result as replication or adaptation.

## Baselines and decisive experiment

Before inspecting combined returns, freeze a small model ladder:

1. F only;
2. D only;
3. L only;
4. F + D and $F\times D$;
5. F + L and $F\times L$;
6. D + L and $D\times L$;
7. all main effects and pairwise interactions;
8. the full FDL interaction.

Each must be compared with cash, passive same-instrument exposure, ordinary short-horizon reversal, asset-class and factor controls, broad trend alone, and trend plus the candidate at matched whole-book risk. Report gross forecast strength separately from executable net return so a data discovery is not silently converted into a retail trading claim.

The cheapest decisive sequence is:

1. reproduce the published F result on a survivorship-safe sample;
2. audit D across asset classes and identify where it is a valid anchor rather than stale-price noise;
3. identify one public, causal L proxy and show that it predicts convergence speed without using future baskets or dealer data;
4. preregister the full nested interaction and its economic sign;
5. run a rolling or time-split test with the actual model-search ledger;
6. freeze any surviving rule and begin prospective paper or small-risk observation.

> [!success] Bottom line
> FDL is worth a dedicated research round because it is a real composition question, not another renamed factor. Its burden of proof is unusually clear: **D and L must improve F**. Until that happens, the durable conclusion is “flow is prior art; FDL is an unresolved alpha hypothesis; Demeter remains unfilled.”

## Sources

[^brown]: Brown, Davies and Ringgenberg, “ETF Arbitrage, Non-Fundamental Demand, and Return Predictability.” The paper identifies primary-market creation/redemption as the observable signal and reports that premium changes are not strong signals in its sample. https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2872414
[^panzeng]: Pan and Zeng, “ETF Arbitrage under Liquidity Mismatch.” The paper develops and tests the role of underlying illiquidity and authorized-participant arbitrage capacity in corporate-bond ETFs. https://scholar.harvard.edu/files/yaozeng/files/etf_arbitrage_liquidity_mismatch.pdf
[^bis]: Todorov, “The Anatomy of Bond ETF Arbitrage,” *BIS Quarterly Review*, March 2021. It documents basket/holding misalignment, changing baskets, underlying-liquidity mismatch and arbitrage-independent AP incentives. https://www.bis.org/publ/qtrpdf/r_qt2103d.htm
[^boe]: Bank of England, “Assessing the Resilience of Market-Based Finance,” 2021. It explains why bond-ETF discounts during stress can reveal stale underlying NAV rather than ETF mispricing. https://www.bankofengland.co.uk/report/2021/assessing-the-resilience-of-market-based-finance
