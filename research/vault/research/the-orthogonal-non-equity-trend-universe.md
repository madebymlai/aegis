---
title: The Orthogonal Non-Equity Trend Universe
date: 2026-06-13
topic: universe-design
distilled-into:
tags:
  - article
---

# The Orthogonal Non-Equity Trend Universe

> [!abstract] One-line takeaway
> A trend sleeve's edge is bounded by the number of *independent* macro trends its universe spans, not by its ticker count: an equity-dominated book collapses to roughly one such bet, a book rebuilt around rates, currencies and commodities restores several, and the liquid non-equity ETF universe saturates near 15-22 independent macro axes (about 25 names) past which more tickers add correlation and cost, not breadth.

## Breadth is the binding constraint

Time-series momentum earns a premium across asset classes, and it earns the most where many markets make large, sustained moves at once.[^mop] The premium's statistical significance is contested - a careful peer-reviewed re-examination finds it fragile to specification[^huang] - but the delivery of whatever premium exists turns on breadth. Grinold's law sets risk-adjusted skill at $IR \approx IC \times \sqrt{BR}$, where breadth is the number of *independent* bets, not the nominal asset count.[^grinold] For a single-signal trend program the information coefficient is roughly fixed by the signal; breadth is the lever left to pull, and the universe is where you pull it.

Equities are where that lever jams. An equity-dominated book's day-to-day variance collapses onto a single dominant eigenvector - in a principal-component decomposition the first component routinely explains the large majority of cross-sectional variance and behaves as a proxy for equity beta.[^factor] In stress the cross-asset correlations converge further toward one, so sectors and regions that looked diversified win and lose together.[^turtle] A lagged trend signal on such a book has effectively one axis to read, and it is wrong-footed on every fast equity reversal, realizing the short-gamma opposite of the long-gamma payoff it is meant to produce. That substrate requirement is argued in [[the-tiered-strategy-roster]] and [[convexity-as-the-axis-of-strategy-diversification]]; the job here is to construct the universe that satisfies it.

The construction principle is to rebuild the book around drivers orthogonal to equities and to each other: the sovereign rate curve, real versus nominal rates, the dollar against other currencies, and physical commodities. Managed-futures programs are built this way for the same reason, and the practitioner case for the cross-asset "optimal market mix" is that breadth across uncorrelated macro themes, not depth in any one of them, is what makes trend pay.[^man][^ra][^gs]

## Counting independent bets

The breadth claim becomes precise through the effective number of bets. Under an equicorrelation idealization, where every pair of assets shares the same correlation $\rho$, a book of $N$ assets carries

$$N_{\text{eff}} = \frac{N}{1 + (N-1)\rho}$$

independent bets.[^resolve] Read the same fifty-name book two ways. At an equity-book correlation of $\rho \approx 0.85$, $N_{\text{eff}} = 50 / (1 + 49 \times 0.85) \approx 1.17$: fifty tickers, one bet. At a non-equity correlation of $\rho \approx 0.20$, $N_{\text{eff}} = 50 / (1 + 49 \times 0.20) \approx 4.63$: nearly four times the effective breadth from the identical count. The lever is $\rho$, not $N$. This is why a ten-instrument cross-asset book can carry more harvestable breadth than a fifty-name equity-sector book, and why adding correlated names to a book buys almost nothing.

The single-$\rho$ form is an idealization. A real cross-asset matrix has block structure - rates cluster, metals cluster - so the honest measure is the participation ratio of the correlation matrix's eigenvalues rather than one average number. The equicorrelation formula is the right intuition pump and the wrong final answer; it overstates breadth wherever blocks are tighter than the average and understates it wherever they are looser.

## What spans orthogonal macro risk

A candidate earns a slot on five criteria, in priority order.

1. **Macro independence.** Low correlation to the equity market and to the names already chosen, spanning a distinct driver. Two long-duration Treasury funds are one bet, not two; the second has to add a new axis or it does not belong.
2. **Pure non-equity.** Exclude instruments dominated by equity beta - sector and country and emerging-market *equity*, most REITs, energy-equity. Credit is the trap inside this rule: high-yield and emerging-market sovereign spreads blow out with stocks precisely in a crisis, so credit is half-equity and must be flagged, not counted as a clean diversifier.[^turtle]
3. **Trend persistence.** Favour drivers that move in sustained directional regimes - rate cycles, currency cycles, commodity super-cycles - over fast mean-reverting chop. A decorrelated instrument that only whipsaws is not a trend substrate.
4. **Liquidity.** Real assets under management and daily volume, enough to rebalance without outsized impact; keep the liquid leader of any two near-duplicates.
5. **Clean history.** Daily data back to at least 2018 so the out-of-sample window spans the 2018 volatility spikes, the 2020 crash and the 2022 tightening cycle.

The asset-class map these criteria produce is the orthogonal spine of the book: duration across the curve (short, intermediate, long nominal, plus zero-coupon and ex-US sovereign), inflation-linked real rates, the dollar and developed and emerging currency crosses, broad commodities, and the single-commodity sectors - energy (crude, gasoline, natural gas), metals (precious and industrial), and agriculture (grains and softs). Each is a separate macro axis, and the design is to occupy the axes, not to crowd any one of them.

## The orthogonality plateau

Adding names helps only while each addition carries new independent risk, and marginal orthogonality falls as the book grows. The first twenty or so names capture the major macro drivers at a low average pairwise correlation (on the order of $\rho \approx 0.15$ to $0.25$), so the effective-bet count expands efficiently. The next tier, out to roughly thirty names, introduces granular single-commodity markets and specific curve points - wheat, soybeans, platinum, an intermediate-duration bucket - which are genuinely idiosyncratic in their supply shocks but are still tied to the broad sectors sitting above them, lifting the average correlation toward $\rho \approx 0.35$ and slowing the expansion. Beyond thirty, the additions are largely redundant: a second long-Treasury index alongside the first, an alternative inflation-linked construction alongside the original, an ex-US bond fund whose rate and currency content is already held through separate duration and FX positions. The average correlation drifts toward $\rho \approx 0.45$ and the effective-bet count flattens.

The implication is a ceiling. The liquid non-equity ETF universe is spanned by approximately 15 to 22 independent macro axes. Expanding the tradeable book to fifty names does not buy fifty bets; it dilutes the average momentum signal and adds turnover and cost while the effective breadth sits flat. The practical recommendation is to concentrate testing on the first twenty-five names - the broad classes plus their first non-redundant refinements - and to expect the diversification benefit of the cross-asset trend book to plateau beyond that. This estimate is reasoning from average correlations, not a measurement of held-out trend P&L; it is the prior the breadth-saturation run exists to confirm or refute (see Limitations).

## Survivorship and roll-cost traps

Two construction traps bias a backtest before any signal is computed.

The first is survivorship. Only currently listed, liquid instruments belong in a tier. The iPath single-commodity ETNs - cocoa, coffee, cotton, copper - were redeemed by their issuer in 2023, and specialty currency funds such as the yuan ETF were delisted in the same window;[^etn] their pre-redemption price history is real but untradeable going forward, so a tier built on them imports survivorship bias and an avoidable ETN credit risk. Substitute structurally stable, currently active funds even at some cost in history.

The second is roll cost. A commodity ETF's trend is only as clean as its futures roll. Front-month trackers can dislocate violently - the best-known crude tracker had its mandate rewritten after April 2020, when near-month WTI printed negative and the fund could not hold the front contract.[^uso] Optimized-roll and laddered-strip products (Optimum Yield, twelve-month strips, dynamic-roll broad indices) are built to mitigate roll-yield drag and survive curve dislocations, and they give a trend signal a cleaner price series to read than a naive front-month fund on the same underlying.

## The tiered universe

The construction below is the candidate universe to validate, ordered by marginal orthogonality and nested so each tier contains the previous one plus its additions. It is a design to be tested on our own pipeline, not a verified result; where two funds give near-identical exposure the more liquid one is kept.

- **Tier 0 - Essentials (10):** `TLT, GLD, UUP, PDBC, USL, DBB, DBA, FXY, TIP, BWX`
- **Tier 1 - First expansion (20):** `+ EDV, EMLC, SLV, UNG, FXE, CORN, CPER, SHY, LQD, FXA`
- **Tier 2 - Refinement (25):** `+ WEAT, BNO, FXF, IEF, HYG`
- **Tier 3 - Refinement (30):** `+ SOYB, FXC, PPLT, STIP, BKLN`
- **Tier 4 - Refinement (35):** `+ VGLT, CANE, UGA, FXB, ANGL`
- **Tier 5 - Refinement (40):** `+ SCHP, PALL, IEI, COMT, EMB`
- **Tier 6 - Refinement (45):** `+ USDU, BNDX, USO, VTIP, BCI`
- **Tier 7 - Refinement (50):** `+ GOVT, DBP, DJP, UNL, EMHY`

Tier 0 fixes the orthogonal core - long nominal duration, gold, the dollar, a broad optimized-roll commodity basket, a clean crude strip, industrial metals, agriculture, a funding-currency haven, real rates, and ex-US sovereign duration-plus-currency. Tier 1 splits the rate curve, adds emerging-market local-currency rates, a second precious metal, an energy source uncorrelated with crude (natural gas), euro and Australian-dollar currency axes, single grains, copper, and investment-grade credit. Tiers 2 and beyond are the refinement region: real on the margin through Tier 2, then increasingly redundant. The recommendation that follows from the plateau is to treat Tier 0 through Tier 2 (twenty-five names) as the working universe and Tiers 3 through 7 as the redundancy region kept to *confirm* the plateau, not to run in production.

## Limitations

- **The single-$\rho$ count is an idealization.** Effective breadth depends on the correlation matrix's eigenvalue spread (participation ratio), not one average correlation; the worked $N_{\text{eff}}$ numbers illustrate the mechanism, they do not measure this book.
- **Correlations are regime-dependent and rise toward one in crises.**[^turtle] Static full-sample $\rho$ overstates the breadth actually available in stress - exactly when the convex payoff is wanted - so the realized plateau may sit lower than the calm-market estimate.
- **The plateau is reasoning, not measurement.** The 15-22 axes and the 25-name ceiling come from average correlations, not from held-out trend quality. Only the breadth-saturation run decides where the marginal name stops paying.
- **Thin single-commodity trends may be noise.** Some refinement-tier funds (natural gas, sugar, wheat, soybeans) move on idiosyncratic supply shocks that may be unharvestable noise rather than persistent trend; per-instrument trend persistence is unverified.
- **Credit trades orthogonality for collinearity.** The credit names (high-yield, fallen-angel, emerging-market sovereign and high-yield, floating-rate loans, investment-grade) decorrelate in calm and re-correlate with equities in a crisis; their slot is conditional on that trade being acceptable.
- **Daily bars can miss gap convexity.** yfinance daily prices with next-open ETF execution may underweight the gap component of the convex payoff (the measurement-frequency caveat in [[convexity-as-the-axis-of-strategy-diversification]]).

## Strategy hypotheses this could seed

- [x] **Breadth saturates - refined to a peak, not a plateau.** Tested 2026-06-13 (pinned-champion diagnostic, cumulative tiers 10-40): own-gamma trend quality peaks at Tier 1 (20 names) - $\beta_2$ +0.0015, trend-efficiency t +2.82, rolling $\beta_2$>0 13/13 - then *degrades* through the refinement tiers ($\beta_2$ -> +0.0001, rolling 8/13, Sharpe 0.26 -> 0.12 by 40 names). Realized orthogonality runs backwards past the essentials core: corr(book move, SPY move) rises 0.50 -> 0.58 as the less-orthogonal refinement names (credit, EM, silver, copper) are added. "Stop at ~25" is directionally right but the optimum is ~20, and the refinement tiers dilute convexity rather than plateauing. Confirmed by formal per-tier aerd grids (24 candidates x 5 held-out splits each): best-by-Sharpe held-out Sharpe peaks at Tier 1 (+0.152) and declines past 25, and re-optimization keeps lb252 throughout - the knee survives re-optimization. See [[runs/atalanta/2026-06-13]].
- [ ] **Orthogonality, not count, is the mechanism.** The realized correlation between book move-magnitude and equity-market move-magnitude falls as orthogonal tiers are added, and held-out trend quality tracks that correlation rather than the nominal name count.
- [ ] **Roll method matters.** Optimized-roll commodity proxies (`PDBC, DBO, USL, UNL, COMT, BCI`) produce cleaner trend extraction than naive front-month trackers (`USO, UNG`) on the same underlying.
- [ ] **Survivorship discipline is free.** Restricting to currently listed, liquid funds (excluding redeemed ETNs) avoids backtest bias without materially reducing the spanned macro axes versus a history-maximizing book.

## Sources

[^mop]: Moskowitz, Ooi & Pedersen, "Time Series Momentum", Journal of Financial Economics 104(2):228-250, 2012 - trend premium across 58 instruments in four asset classes, strongest in extreme up and down markets. https://w4.stern.nyu.edu/facdir/lpederse/papers/TimeSeriesMomentum.pdf
[^huang]: Huang, Li, Wang & Zhou, "Time-series momentum: Is it there?", Journal of Financial Economics 135(3):774-794, 2020 - peer-reviewed, COI-free re-examination finding TSMOM's significance fragile to specification; the counter to MOP. https://down.aefweb.net/WorkingPapers/w717.pdf
[^grinold]: Grinold, "The Fundamental Law of Active Management", Journal of Portfolio Management 15(3):30-37, 1989 - $IR \approx IC \times \sqrt{BR}$, with breadth measured by the number of independent bets, not nominal assets.
[^resolve]: ReSolve Asset Management, "Tactical Alpha and the Fundamental Law of Active Management, Part I" - effective number of independent bets via the correlation-matrix participation ratio; $N_{\text{eff}} = N/(1+(N-1)\rho)$ is the equicorrelation special case. Practitioner source whose pro-TAA argument relies on uncorrelated assets (COI). https://investresolve.com/tactical-alpha-theory-practice-pt-i-fundamental-law-of-active-management/
[^man]: Man Group, "A Trend Following Deep Dive: The Optimal Market Mix for a Trend Follower" - the optimal trend book spans many uncorrelated cross-asset markets; breadth across macro themes, not depth in one, drives the premium. CTA COI. https://www.man.com/insights/trend-following-optimal-market-mix
[^ra]: Research Affiliates, "Systematic Global Macro" - cross-asset macro trend and value premia across rates, currencies and commodities. https://www.researchaffiliates.com/insights/publications/articles/563-systematic-global-macro
[^gs]: Goldman Sachs Research, "Investing in Everything, Everywhere, All at Once", 2025 - the diversification benefit of spanning the full cross-asset opportunity set. https://www.gspublishing.com/content/research/en/reports/2025/10/15/21c88473-1287-408f-97f8-36c7a80340cb.html
[^turtle]: TurtleTrader, "Correlation Issues for Trend Following Traders: Why They Win and Lose Together" - instruments that look diversified converge in stress, so a book trades as fewer effective bets than its count. Practitioner. https://www.turtletrader.com/sheep/
[^factor]: Jurczenko (ed.), "Factor Investing: From Traditional to Alternative Risk Premia", ISTE Press / Elsevier, 2017 - equity-dominated books concentrate variance on a single dominant market factor; the first principal component explains the large majority of cross-sectional variance. https://dokumen.pub/factor-investing-from-traditional-to-alternative-risk-premia-1785482017-9781785482014.html
[^etn]: Barclays, "Barclays Announces the Redemption of 21 iPath ETNs", Business Wire, 18 April 2023 (redemption effective June 2023; cocoa, coffee, cotton and copper trackers among them); the WisdomTree Chinese Yuan ETF was delisted later in 2023. Pre-redemption series are untradeable forward and carry ETN credit risk. https://www.businesswire.com/news/home/20230418005326/en/Barclays-Announces-the-Redemption-of-21-iPath-ETNs
[^uso]: Aranca, "US Oil ETFs - A good investment opportunity or a high-risk bet?" - the front-month WTI tracker dislocated when April-2020 crude printed negative and its mandate was rewritten toward a diversified strip; the case for optimized-roll commodity products over naive front-month funds. https://www.aranca.com/knowledge-library/articles/investment-research/us-oil-etfs-investment-risk
