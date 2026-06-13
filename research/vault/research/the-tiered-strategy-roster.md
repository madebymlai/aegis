---
title: "The Tiered Strategy Roster: Floor, Target, Expansion"
date: "2026-06-11"
topic: strategy-taxonomy
distilled-into:
tags:
  - article
---

# The Tiered Strategy Roster: Floor, Target, Expansion

> [!abstract] One-line takeaway
> The strategies an allocator needs are not a count, they are an order of operations: cover both signs of skew (floor - trend ⊕ carry/mean-reversion), split the convex pole by speed (target - add tail/defensive), then add an off-axis stream (expansion - add market-neutral). Each tier fixes a failure the previous one cannot.

## The question is order, not count

"How many strategies does an allocator need" is the wrong question. It invites a list of mechanisms and a book that looks varied while behaving as one position. The right question is which *failure modes* the roster must cover and in what order, because each strategy earns its slot by surviving a regime the others do not.

That reframing comes straight from the convexity axis: a strategy's diversifying value is set by the sign and speed of its convexity to the shocks that move all risk assets at once, not by its signal logic. The full argument is in [[convexity-as-the-axis-of-strategy-diversification]]; this note turns that axis into a build order. A family is a target a candidate is built toward and then *verified* against, on its realized stream - the gates for that are in [[verifying-strategy-family-membership]].

## Floor: both signs of skew

The irreducible minimum is two roles of opposite convexity - a trend/momentum sleeve (long gamma, positive skew) and a carry or mean-reversion sleeve (short gamma, negative skew). The short-gamma sleeve is the income engine: it collects the premium that structurally accrues to sellers of crash risk and compounds it through calm markets. The long-gamma sleeve is the drawdown payer: it bleeds a little in calm and pays out in dislocation, buying the income engine time to recover. Holding both is what makes the pair a portfolio; holding either alone is one position wearing several tickers.

The trend pole carries a substrate requirement that is easy to miss: its long gamma is to *its own* universe's moves, so the universe must be one whose moves are *sustained trends*, not reversals. An equity-dominated book fails this - its move-magnitude is nearly collinear with equities, so there is no separable trend axis, and a lagged signal is wrong-footed on every fast equity reversal, realizing *short* gamma under a trend label. A non-equity book (rates, FX, commodities) decorrelates the trend axis from equities and restores the long-gamma profile, which is why managed-futures trend programs are built on broad cross-asset futures rather than equity baskets. The trend sleeve's substrate is therefore not merely "wide" but "non-equity-dominated"; breadth that only adds correlated equity sectors dilutes the convex tail rather than building it.

The convergent/divergent split that institutional fund-of-funds allocators use is this same floor under different names - divergent (convex - trend, macro) strategies supply diversification in stress, convergent (concave - relative-value, carry) strategies supply the calm-market carry.[^bf][^jai] The recurring construction error is to fill both floor slots from the *same* pole. A roster whose two "diversifiers" are a trend follower and a crash hedge owns two long-gamma sleeves and no income, and the two bleed together through every quiet, range-bound year. The missing piece is almost always the concave sleeve, precisely because it is the one that quietly loses in the dislocations the convex sleeve is bought for.

## Target: split the convex pole by speed

The third role is tail/defensive, and it is not a new direction on the axis - it is the convex pole split by *speed*. Trend is lagged long gamma: a move must establish before the strategy is positioned, so it harvests protracted bear markets (the dot-com grind) and misses sudden gaps (1987, March 2020). A tail sleeve is immediate long gamma for exactly the crash trend arrives too late for. AQR's comparison of index puts against trend draws the same line - puts returned over 40% in the fast COVID crash, trend did its best work in drawn-out bears - and because the slow drawdowns do more lasting damage to compounding, trend is the workhorse and tail the supplement.[^aqrtail]

The ordering is deliberate, and it points further than "target tier": a *permanent, standing* tail sleeve degrades long-term compounding, because explicit crash insurance pays the full premium every calm day and the negative carry is the price of the immediacy.[^aqrtail] So tail is best deployed *episodically* - sized up when valuation dispersion is extreme or a risk-mitigation mandate applies, sized down otherwise - rather than held as a constant allocation. Trend remains the *standing* defensive engine because it has a round-trip recovery advantage the option leg lacks: it participates in the rebound and keeps its drawdown gains, where rolled puts decay and expire worthless if the crash does not come.[^aqrtail] When tail is held, it earns its slot only as a sized overlay, ideally sourced from a convex anomaly - a haven that pays in stress without the structural bleed - rather than from rented volatility whose decay *is* the premium. The instrument-level version of that trade-off is in [[always-on-convexity-from-listed-instruments]], and havens' regime-dependence in [[havens-at-regime-turning-points]].

## Expansion: add an off-axis stream

Market-neutral and relative-value are the fourth tier because they sit *off* the skew axis entirely - near-zero net gamma, low correlation to either pole, returns driven by cross-sectional dispersion rather than by which regime the market is in. They are the diversifier of diversifiers, and they belong last for two reasons. They add the least to a book that has not yet covered both signs and both speeds. And they are the most sensitive to breadth: a ranking strategy needs a wide cross-section to separate winners from losers, and a thin universe starves it. Ilmanen's case for harvesting many low-correlated premia in parallel is the steady state this tier aims at, but only once the floor and target are in place.[^ilm]

## Why this order and not another

Each tier answers a failure the one below cannot. The floor fixes the worst one - a single-sign book that is undiversified by construction. The target fixes the floor's blind spot - the fast crash the lagged convex sleeve sleeps through. The expansion fixes the residual - dependence on regime itself - by adding a stream that does not care about regime.

Adding tiers out of order buys little. A tail overlay on a single-sign book still has no income; a market-neutral sleeve on a book with no convexity still has nothing to pay it in a crash. More strategies is not more diversification: an allocator with three long-gamma sleeves and no short-gamma one is less diversified than one holding a single matched pair.

## The upgrade path

A taxonomy that cannot grow without breaking its contract is a dead end. The roster scales along three horizons, none of which touches the return-stream contract the allocator consumes, so each is additive.

First, decompose sub-roles inside the existing families before adding new ones. The trend sleeve splits cleanly by horizon - a short-term sleeve (roughly 5-to-20-day signals) and a medium/long sleeve (50-to-200-day) behave differently enough in whipsaw to be distinct Locked Candidates, letting the allocator trade speed against stability without leaving the family (the horizon trade-off is in [[trend-following-in-whipsaw-regimes]] and [[relative-vs-absolute-momentum-in-small-universes]]).

Second, widen the asset universe along orthogonal, non-equity axes. Going from the current book to a larger set of independent macro drivers - the rate curve, real rates, currencies, and broad and single commodities - raises the number of *independent* bets, not merely the nominal count, the lever that most directly lifts a small book's risk-adjusted ceiling. Adding correlated equity exposure would raise the count while diluting the convex tail (the substrate requirement above); the construction that actually adds breadth, and the point where it saturates, are in [[the-orthogonal-non-equity-trend-universe]].

Third, add a fifth family only when a genuinely new payoff shape is available. The natural candidate is volatility-arbitrage or liquidity-provision: a near-zero-beta sleeve that harvests the volatility risk premium by selling implied and buying realized protection - a convex/concave hybrid that sits apart from the four regime roles (the VRP mechanics are in [[convexity-as-the-axis-of-strategy-diversification]]).

## Breadth and capacity

Two numbers bound the roster: how wide it can be across families, and how deep within one.

Breadth is richer than the asset count suggests. By Grinold's Fundamental Law, risk-adjusted skill scales with the square root of the number of independent bets, $IR \approx IC \times \sqrt{BR}$.[^grinold] A naive reading caps a ten-instrument universe at ten bets, but breadth is set by *independent* bets, not nominal assets: highly correlated assets collapse to a few effective bets, while near-orthogonal cross-asset ETFs preserve them. One practitioner estimate puts the effective number of independent bets in a ten-ETF cross-asset book near 6.8, far above what a same-size single-sector book would deliver.[^resolve] This softens, without removing, the breadth limit on the market-neutral expansion tier: the universe is thin in names but not in orthogonal risk.

Depth within a family is capped by redundancy. Adding strategies helps only while they stay uncorrelated; the marginal variance reduction from the $M$-th strategy in a family of uniform pairwise correlation $\rho$ is

$$\frac{\partial \sigma_p^2}{\partial M} = -\frac{\sigma^2(1-\rho)}{M^2}$$

which decays as $1/M^2$. At a redundancy ceiling of $\rho \approx 0.65$ the benefit is meaningful from one strategy to two, modest from two to three, and negligible past three. A workable default follows: cap a family at roughly three active, non-redundant Locked Candidates, and enforce a within-family correlation ceiling (realized-return $\rho \lesssim 0.65$ over a rolling year) above which the lower-Sharpe candidate is retired or merged. These specific cut points are engineering defaults, not laws.

## Limitations

Tail's tier rank is genuinely contested. AQR's own reading leans against a standing tail sleeve at all, on the grounds that its bleed costs more than the slow-drawdown protection trend already supplies.[^aqrtail] Treat "tail = target tier" as the median view, not a settled one, and let the convexity-per-bleed evidence decide per universe.

The expansion tier is breadth-limited, though less than the raw count implies. Cross-sectional market-neutral wants many names to rank, and a ten-instrument book is thin on that axis - but its near-orthogonal cross-asset structure preserves an estimated ~6.8 independent bets (see Breadth and capacity), so the fourth tier is constrained, not foreclosed. Whether it earns its slot at this universe size is an empirical question, not a foregone one.

The floor's concave sleeve is the hardest to source, and the whole roster rests on it. If carry and mean-reversion cannot be made to pay net of costs in a given universe, the floor degrades to a single sign and loses its foundation. So the floor's feasibility, not the higher tiers, is where validation effort belongs first.

## Strategy hypotheses this could seed

- [x] **Floor pays.** Adding a concave (short-gamma) sleeve to a trend book lifts held-out crisis-conditional return at matched volatility versus trend-only - the core 2-floor claim. **Refuted on the current poles 2026-06-13** (atalanta Tier 1 trend + demeter distribution-carry, same 20-name book): the skew-neutral vol-matched composite does NOT beat both poles - it loses to trend-only. Crisis-conditional return falls *monotonically* as carry weight rises (w=0 trend +0.16% -> w=1 carry -0.21%), while skew-neutrality demands w~0.99 because the carry pole's realized skew is ~0, not negative; the two requirements conflict and the "skew-neutral floor" degenerates to carry-only. The pairing mechanism is not refuted - this carry pole is too weakly concave to anchor a skew budget (the article's own "concave sleeve is the hardest to source" warning, measured). **Update - VRP re-test, same day (`aegis-rd-ypz`):** re-sourcing the concave pole as the variance risk premium (`demeter.vol_carry`, short-vol, gate qskew -1.18) **fixes the sizing defect** - the skew budget balances at a genuine 40/60 (carry 30% of variance, qskew->0), the poles are near-uncorrelated (+0.01), and the composite beats both poles on the prescribed **multi-window compounded** crisis return (+7.27% vs +4.68% / +5.72%) at **half the drawdown** (maxdd -10.9% vs -20.5%, best Calmar) - the floor pays **as a portfolio**. It still does NOT beat trend on the worst-decile DAILY mean (structural: a short-gamma pole loses on the worst days, so it cannot add to trend's worst-day protection - tail protection is trend's job), and OOS it wins only the slow 2022 bear (1/2 windows). Verdict **iterate/partial-keep**, pending Feb-2018 in-window + a target-tier tail sleeve. See [[runs/floor/2026-06-13|run diary]].
- [ ] **Target earns its bleed.** A trend-plus-tail pair beats trend-only specifically in fast-gap windows where trend lags, by enough to justify the tail sleeve's calm-period carry on a convexity-per-bleed frontier.
- [ ] **Expansion needs breadth.** A market-neutral sleeve fails to decorrelate from both poles at roughly ten instruments (breadth-starved), confirming it as a genuine expansion that waits for a wider universe.
- [ ] **Order beats count.** Ranking candidate rosters by held-out Calmar, a matched long-and-short-gamma pair outscores three long-gamma sleeves.

## Sources

[^bf]: bfinance, "Clarifying the Case for 'Convex' or 'Divergent' Hedge Fund Strategies", bfinance insights (undated) - divergent/convex strategies deliver materially positive returns and stress-period diversification via long-volatility exposure; practitioner piece. https://www.bfinance.com/insights/clarifying-the-case-for-convex-or-divergent-hedge-fund-strategies
[^jai]: "Hedge Fund of Fund Allocations Using a Convergent and Divergent Strategy Approach", Journal of Alternative Investments 7(1):44, 2004 - formalizes the convergent/divergent split as a fund-of-funds allocation framework. https://jai.pm-research.com/content/7/1/44
[^aqrtail]: AQR, "Tail Risk Hedging: Contrasting Put and Trend Strategies", 2020 - OTM index puts return most in fast crashes (over 40% in the COVID crash), trend most in protracted bear markets; slow drawdowns do more damage to long-horizon wealth, so trend is the workhorse. AQR conflict of interest. https://www.aqr.com/Insights/Research/White-Papers/Tail-Risk-Hedging-Contrasting-Put-and-Trend-Strategies
[^ilm]: Ilmanen, "Expected Returns: An Investor's Guide to Harvesting Market Rewards", Wiley, 2011 - harvest many low-correlated premia (value, carry, trend, volatility, defensive) in parallel. https://www.goodreads.com/book/show/10982323-expected-returns
[^grinold]: Grinold, "The Fundamental Law of Active Management", Journal of Portfolio Management 15(3):30-37, 1989 - risk-adjusted skill scales as $IR \approx IC \times \sqrt{BR}$, with breadth measured by the number of *independent* bets, not nominal assets.
[^resolve]: ReSolve Asset Management, "Tactical Alpha and the Fundamental Law of Active Management, Part I" (practitioner) - effective number of independent bets via the correlation-matrix participation ratio; a small cross-asset book preserves far more breadth than its nominal count. Practitioner source (their pro-TAA argument relies on uncorrelated assets); the specific ~6.8 figure is one such estimate, not peer-reviewed. https://investresolve.com/tactical-alpha-theory-practice-pt-i-fundamental-law-of-active-management/
