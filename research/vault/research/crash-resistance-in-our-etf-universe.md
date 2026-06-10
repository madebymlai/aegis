---
title: Crash-Resistance in Our ETF Universe
date: 2026-06-10
topic: crisis-alpha
distilled-into:
tags:
  - article
---

# Crash-Resistance in Our ETF Universe

> [!abstract] One-line takeaway
> Our ten yfinance ETFs already contain both halves of a divergent crash-hedge - TLT and GLD for growth-shock flight-to-safety, DBC, XLE and UUP for inflation-shock crashes - so a sleeve that *gains* in a crash is expressible here with no new data; the only open question is selection, and time-series momentum across the same ten is the regime-agnostic way to let the data pick the haven.

This maps the edges graded in [[divergent-vs-defensive-crash-resistance]] onto the fixed universe `SPY, IWM, EEM, TLT, GLD, DBC, VNQ, UUP, XLE, XLU` (yfinance, daily OHLCV). The framing question from that article carries over: we want a sleeve whose *rising return* an allocator can read as "a crash is starting," which means we need the divergent edges (assets that gain), not the defensive one (assets that lose less). The good news is that the universe was, by accident or design, assembled with both flight-to-safety regimes covered. The constraint is that ten instruments is a thin book, and the 2018-2025 window most runs use contains only a handful of crash episodes, so the danger is fitting to three or four events.

## What the universe already contains

Sorting the ten by crash behaviour, not asset class, is the useful cut:

- **Risk assets we hedge against** - `SPY` (S&P 500), `IWM` (Russell 2000, higher beta), `EEM` (EM equity, high beta and dollar-sensitive). These fall in every crash; `IWM` and `EEM` fall hardest.
- **Growth-shock havens** - `TLT` (20-year Treasuries) and `GLD` (gold). They rally when a growth or risk shock sends capital fleeing to quality, and they are exactly the assets that failed or wobbled in 2022 (`TLT`) and the March-2020 dash-for-cash (`GLD`).[^aqrcorr][^nyfed]
- **Inflation-shock havens** - `DBC` (broad commodities), `XLE` (energy), and `UUP` (long US dollar). These are the assets that *rose* in 2022 while both stocks and bonds fell: energy and commodities led, and the dollar index gained roughly 15% on the year.[^hedgeweek][^wgc]
- **The dual-regime standout** - `UUP`. The dollar spiked in the March-2020 liquidity scramble *and* climbed through 2022's rate shock, the one instrument here that worked in both crash types.[^nyfed][^wgc]
- **Not havens, despite appearances** - `VNQ` (REITs) and `XLU` (utilities). Both are rate-sensitive: REITs are equity-like and fell hard in 2020 and 2022, and utilities are the defensive-equity cushion from the prior article - they lose less but rarely gain, and they took the 2022 rate leg on the chin. Treat `XLU` as a survival tilt, not a signal, and `VNQ` as a risk asset.

The headline is the split between the two haven baskets. `TLT`/`GLD` cover the growth-shock crash; `DBC`/`XLE`/`UUP` cover the inflation-shock crash. That is the complementarity from the prior article made concrete in tickers - and it is why no single static hedge works across all crashes in this universe.

## Expressing flight-to-safety: a regime-selected haven basket

The most direct sleeve is long-only across the haven set, weighted toward whichever havens are working. The crude version - always long `TLT`/`GLD`/`UUP` - is the one that breaks in 2022, because `TLT` is in it and `TLT` was a loss engine that year.[^aqrcorr] The honest version conditions on regime: tilt to `TLT`/`GLD` when volatility rises *and* inflation is quiescent (the post-2000 default), and to `DBC`/`XLE`/`UUP` when the shock is an inflation or rate shock. The problem is that naming the regime in advance is exactly what the literature says is hard, and we have no clean inflation-regime signal inside a price-only OHLCV feed. A price-based proxy - which haven basket is itself trending up - is available, but that is just time-series momentum by another name, which argues for expressing the whole thing as momentum rather than hand-coded regime rules.

## Expressing trend-following crisis alpha: signed momentum across all ten

The Strategy contract emits *signed* target weights and the simulator reads Direction from the sign, so long/short time-series momentum is expressible directly: go long positively-trending instruments, short negatively-trending ones, size by inverse volatility. This is the regime-agnostic answer to the selection problem - the sleeve does not need to be told whether the crash is a growth or inflation shock, because it mechanically rotates into whatever is trending. In 2020 that meant long `TLT`/`UUP`; in 2022 it meant short `SPY`/`IWM`/`EEM` and long `XLE`/`DBC`/`UUP`, which is precisely the positioning that gave managed futures its banner 2022.[^hedgeweek] The cost is the one the prior article flagged: momentum needs a *sustained* trend, so this sleeve will give little protection in a fast V-shaped shock like Q4 2018 or the first weeks of the COVID crash, and it will whipsaw on sharp reversals.[^graham]

Two universe-specific cautions. Ten instruments is a thin trend book - the century-of-evidence results lean on 50-plus markets across four asset classes for diversification, and a ten-ETF version concentrates risk in a few correlated bets, so its crisis-alpha smile will be noisier than the literature's.[^aqrcentury] And the long/short version can take large short equity positions; the Allocation Policy's gross and net caps, plus Financing Carry on the shorts, are what keep that book honest and must be set deliberately rather than left to default.

## The dual-regime sleeve and the allocator tell

Combining the two divergent expressions is the synthesis. A sleeve that holds a momentum-selected mix of the haven baskets covers both failure modes: the flight-to-safety leg catches the fast growth shocks where trend is too slow, and the momentum leg catches the slow grinds and inflation shocks where a static `TLT` hedge fails. For the eventual allocator (which does not exist yet), the *tell* is this sleeve's own return turning sharply positive while `SPY` falls - the random forest learns to read a rising haven-sleeve return, and the breadth of havens participating, as the bearish regime signal. The design implication for the sleeve is therefore to optimise for *responsiveness in crashes* (a clear, early positive swing) rather than raw full-sample Sharpe, because a sleeve that bleeds slowly in calm markets but lights up reliably at the onset of stress is a better signal generator than one tuned to never lose.

The confidence ordering is worth stating. That the universe spans both haven regimes is a direct, verifiable mapping. That long/short momentum across these ten reproduces a (noisier) crisis-alpha smile is plausible from the literature but unverified on our data and our short sample. That the combined sleeve is a good *allocator signal* - the whole motivating premise - is conjecture until both the sleeve and the allocator are built and tested together.

## Limitations

- **Few crash episodes in-sample.** The common 2018-2025 window contains essentially three stress events (Q4 2018, 2020-Q1, 2022). Any sleeve tuned to "win in crashes" on three episodes is at high risk of fitting the episodes rather than the edge; held-out validation across the splits is doing heavy lifting and may still not be enough.
- **Thin book.** Ten correlated ETFs give far less trend diversification than the managed-futures literature assumes, so crisis-alpha convexity will be weaker and less reliable here than the headline figures suggest.[^aqrcentury]
- **No inflation-regime input.** Price-only OHLCV cannot directly observe the growth-vs-inflation shock distinction that decides whether `TLT` hedges or fails;[^aqrcorr] the sleeve must infer it from price trends, which is itself an untested assumption.
- **Fast crashes remain uncovered.** Neither expression reliably gains in a one-week shock; the COVID-crash miss is a structural limit, not a tuning problem.[^graham]

## Strategy hypotheses this could seed

- [x] Long/short time-series momentum across all ten ETFs (inverse-vol sized, signed weights) produces positive returns in 2022 and 2020-Q1 but not Q4 2018 - confirm the smile and the fast-crash hole on held-out splits. **Killed 2026-06-10**: the short side never pays in this thin book - even at its best case (slow trend, risk legs only, wide band) every short-bearing candidate lost to the long-only book, and the overlay was negative in 2022 itself. The long-only half survives: slow (252d) trend rotation is flat-to-positive in every held-out year including 2022. See [[runs/aegis/2026-06-10|run diary]] and the graveyard.
- [ ] A static long `TLT`/`GLD`/`UUP` haven basket gains in 2020 but loses in 2022 - establish the regime hole that motivates momentum selection.
- [x] Adding `DBC`/`XLE` to the haven set closes the 2022 hole - test whether the inflation-shock basket recovers the year a `TLT`-only hedge loses. **Supported 2026-06-10**: the union basket (TLT/GLD/UUP/DBC/XLE, momentum-selected top-3) returned +22.1% with a +1.63 Sharpe on the 2022 held-out split, while the growth-only basket was the run's worst representative. See [[runs/aegis/2026-06-10|run diary]].
- [ ] `UUP`-heavy weighting is the single most consistent crash-gainer across both 2020 and 2022 - test the dual-regime claim on the dollar leg alone. The mechanism, the dollar's failure regimes, and the floor-vs-trigger question are worked out in [[the-dollar-as-dual-regime-haven]].
- [ ] A crash-responsive objective (early positive swing at stress onset) selects different parameters than a Sharpe objective - confirm the sleeve should be tuned as a signal, not a standalone return stream.

## Sources

[^aqrcorr]: Brixton, A. et al. (AQR), "A Changing Stock-Bond Correlation", Journal of Portfolio Management, Q1 2023. The stock-bond correlation sign depends on whether growth or inflation volatility dominates; bonds stopped hedging in 2022. AQR COI on the prescription. https://www.aqr.com/Insights/Research/Journal-Article/A-Changing-Stock-Bond-Correlation
[^nyfed]: Federal Reserve Bank of New York, "The Global Dash for Cash in March 2020", Liberty Street Economics, 2022. Even safe havens were sold for dollars in the COVID crash; USD demand dominated. https://libertystreeteconomics.newyorkfed.org/2022/07/the-global-dash-for-cash-in-march-2020/
[^hedgeweek]: Hedgeweek, "Trend followers turn leaders as CTAs deliver record returns in 2022", 2023. SG Trend Index +27.3% in 2022, driven by short bonds/rates and long dollar and energy. https://www.hedgeweek.com/trend-followers-turn-leaders-ctas-deliver-record-returns-2022/
[^wgc]: World Gold Council, Goldhub returns data, and corroborating market data on the 2022 dollar move (DXY ~+15%) and gold (+~25% in 2020, ~flat in USD in 2022). WGC is an industry body (COI); figures used are uncontested price returns. https://www.gold.org/goldhub/data/gold-returns
[^aqrcentury]: Hurst, B., Ooi, Y. & Pedersen, L., "A Century of Evidence on Trend-Following Investing", AQR, 2012. The crisis-alpha evidence rests on 59 markets across four asset classes; AQR product paper with hypothetical returns (COI). https://www.chesler.us/resources/academia/A_Century_of_Evidence_on_Trend_Following.pdf
[^graham]: Graham Capital Management, "Trend-Following Primer". Trend gave no protection in the fast Q4-2018 reversal; CTA-authored (COI) but candid on the limitation. https://www.grahamcapital.com/blog/trend-following-primer/
