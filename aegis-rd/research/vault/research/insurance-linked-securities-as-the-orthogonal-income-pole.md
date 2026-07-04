---
title: Insurance-Linked Securities as the Orthogonal Income Pole
date: 2026-07-04
topic: carry
distilled-into:
tags:
  - article
---

# Insurance-Linked Securities as the Orthogonal Income Pole

> [!abstract] One-line takeaway
> The floor's co-crash problem has a second, independent fix on the concave side: replace credit carry - whose crash factor *is* the global recession - with catastrophe bonds, whose crash factor is physical and meteorological (hurricane wind speed, earthquake magnitude) and therefore orthogonal to the financial cycle. A cat bond is still a short-gamma income pole (collect a floating spread, occasionally lose the principal to a triggering disaster), so it keeps its family membership; what changes is that its jump risk does not fire in the states where the trend pole is bought. This does not require anti-correlation - which a long-only pole cannot reach - only orthogonality, and orthogonality maximizes the rebalancing premium. The UCITS wrapper, which we had written off as a tiny watchlist item, is in fact a $19bn fund universe with multiple institutional-grade strategies.

This article is the concave-side companion to [[carry-diversifies-only-a-divergent-trend]]. That piece established (and, on our own book, ultimately narrowed) the convex-side story: the reliable convex pole is a divergent TSMOM, not a static safe-haven - and once our own divergent pole's co-crash is decomposed to a single fast crash, the existing credit carry already diversifies it at the horizon the floor operates. This piece takes an independent route to robustness: fix the *concave* pole so its crash factor no longer overlaps anything financial at all. It is not required by the convex-side finding - it is a *stronger* concave pole, valuable on its own terms and composable with a divergent convex pole.

## Credit's crash factor is the recession; a cat bond's is the weather

[[the-skew-is-the-product]] pinned credit's crash-beta to a precise address - duration-times-spread in the BB-B belt, structurally a short put on the firm's assets - and that is exactly why credit carry cannot escape the recession factor: the thing it is paid to bear is corporate default, which clusters in the same downturns that a crisis book exists to survive. Koijen, Moskowitz, Pedersen and Vrugt generalize it: carry across equities, fixed income, currencies, commodities and options co-crashes in global recessions, liquidity crises and volatility spikes. No amount of construction inside the financial-carry universe removes a factor that is common to the whole universe.

A catastrophe bond breaks the common factor by sourcing its premium outside finance entirely. The investor receives a floating-rate coupon - a risk-free base (SOFR) plus an insurance spread - and in exchange underwrites a defined natural-catastrophe layer: if a qualifying hurricane, earthquake or windstorm exceeds the bond's trigger, principal is written down to pay claims. The default risk is "entirely physical and meteorological." An Atlantic hurricane is not caused by a recession, and a recession is not caused by an earthquake, so the trigger event is decoupled from GDP, central-bank policy, corporate defaults and equity drawdowns by construction. The pole stays concave - small positive carry most of the time, an occasional large idiosyncratic loss - but the axis of its concavity is peril severity, not the business cycle.

## Orthogonal is the right target, not anti-correlated

It is tempting to ask a concave pole to *mirror* the convex pole - to gain when trend loses. A long-only sleeve cannot do that (Patton: the gains from exploiting asymmetric dependence are "limited" for short-sales-constrained investors), and [[carry-diversifies-only-a-divergent-trend]] retired the "downside correlation <= 0" screen for that reason. Cat bonds reframe the target correctly: the floor does not need an anti-trend, it needs *non-co-crashing income*, and orthogonality (correlation near zero) is both achievable and, it turns out, optimal. The returned deep-research synthesis makes the mechanism explicit with the closed form for the rebalancing premium between two equal-volatility poles, `RP = sigma^2 * (1 - rho) / 4`: any correlation strictly below one yields a positive premium, and the premium is *largest* as correlation falls toward and below zero.[^rp][^insead] A genuinely orthogonal income pole (rho ~ 0) therefore extracts close to the maximum rebalancing premium a given volatility budget allows, without needing the negative-beta crisis hedge a long-only book cannot buy. That is a cleaner objective than chasing skew depth, and cat bonds are built for it.

## The evidence, and the honest caveat

The uncorrelated claim is strong but not unconditional, and the floor should be built on the conditional truth. Cat bonds earned positive returns through the 2008 global financial crisis and were essentially untouched by the 2020 pandemic; even in 2022, when equities and bonds fell together for the first time in half a century, cat-bond losses were far smaller.[^schroders][^nb] Across 2002-2017, mean-variance spanning tests find cat bonds open portfolios that were previously unattainable and improve the time-varying Sharpe and maximum-diversification ratios, "particularly during episodes of crisis and of high volatility."[^ang] The caveat is the 2008 liquidity channel: Carayannopoulos and Perez show cat bonds are zero-beta only in non-crisis periods - with the Lehman collapse their returns became significantly correlated to the market as forced sellers liquidated whatever they could - though the *magnitude* of that hedge-ratio change was far smaller than for any other asset, and post-2009 structural improvements returned betas to pre-crisis levels.[^cp] The balanced reading (matching the multi-asset study that classes cat bonds a strong *diversifier* but a poor *hedge*, and a safe haven only post-crisis) is that cat bonds are orthogonal in all normal and most crisis states, with a residual liquidity co-movement in a Lehman-scale funding seizure - a far weaker and rarer link than credit's structural recession beta.[^role]

## Investability: a $19bn UCITS universe, not a watchlist footnote

We had earlier filed UCITS cat bonds as a tiny instrument under regulatory challenge. That is stale. By end-2025 the UCITS catastrophe-bond fund sector held about $19.12bn across multiple strategies - roughly 31% of all outstanding cat-bond risk capital - having grown $5.3bn (about 39%) in the year.[^artemis] The institutional-grade, investable expressions:

- **Twelve Cat Bond Fund** (Twelve Securis), the largest UCITS cat-bond strategy at ~$4.55bn, weekly-liquid.[^artemis][^twelve]
- **Schroder GAIA Cat Bond Fund** (~$4.05bn), fortnightly liquidity, positive-month ratio ~77.5%.[^artemis]
- **Fermat, Icosa, Plenum, Franklin K2, Leadenhall** UCITS ILS funds fill out the sector.[^artemis][^franklin]
- **KRC Cat Bond UCITS ETF** (ticker CATB / C47B, ISIN IE000UWJUW87, King Ridge / HANetf, TER 1.28%): Europe's first listed cat-bond ETF, launched December 2025 - genuinely exchange-traded but still nascent (~$13m), so today the *funds* are the deployable pole and the ETF is one to watch.[^hanetf]

The one real friction is cadence: cat-bond funds are weekly or fortnightly liquid, not daily, so a pole built on them rebalances on a weekly-or-slower schedule. That is not a defect for this role - the horizon argument in [[carry-diversifies-only-a-divergent-trend]] says the floor should be measured and rebalanced at monthly, not daily, frequency anyway, because daily correlations are contaminated by microstructure gapping while the structural (macro) relationship lives at lower frequency.[^rp] The illiquidity even helps enforce the correct measurement horizon.

## What this changes

The floor now has two orthogonal levers, and they compose. Recast the convex pole as TSMOM and the credit-carry pole becomes accretive ([[carry-diversifies-only-a-divergent-trend]]); recast the concave pole as cat bonds and its crash factor leaves the financial cycle entirely. A book with a TSMOM convex pole and a cat-bond concave pole is decoupled from *both* sides - the convex pole is long the dislocations, the concave pole's losses are meteorological - which is the closest a long-only UCITS construction can come to the straddle-and-orthogonal-income ideal. Credit carry does not disappear from the roster; it reverts to what the evidence supports - a standalone income sleeve ranked on income, not a floor diversifier it structurally cannot be on this universe.

## Strategy hypotheses

- [ ] **The cat-bond concave pole.** Substitute credit carry with a UCITS cat-bond fund stream (Plenum CAT Bond UCITS Index or Twelve Cat Bond Fund NAV) in the concave pole. Pre-register (from the returned synthesis): conditional correlation to the trend pole <= 0.05 across regimes including the Q1 2020 liquidity crisis and the 2022 rate drawdown, and a positive rebalancing premium over the full sample. Test at weekly/monthly frequency, not daily.
- [ ] **Compose both fixes.** Build the floor as TSMOM convex pole + cat-bond concave pole and compare its composite CE contribution and crisis-window capture against (a) TSMOM + credit carry and (b) static-basket + credit carry (the incumbent). Expect the double fix to dominate both.
- [ ] **Liquidity-stress guard.** Verify the residual 2008-style liquidity co-movement is small enough not to break the pole: measure the cat-bond pole's drawdown-overlap with the trend pole in the worst funding-stress weeks, not just average correlation.

## Sources

[^rp]: "Resolving the Convex-Concave Portfolio Constraint" (returned deep-research synthesis, 2026-07-04, on file at `/tmp/carry-floor-deep-research-brief.md` response). Gives the rebalancing premium `RP = sigma^2 (1 - rho) / 4` (positive for any rho < 1, maximized as rho falls) and the horizon argument (daily correlations contaminated by microstructure and autocorrelation; DCC-MIDAS shows the structural stock-bond and carry-trend relationship lives at monthly frequency). Secondary; its primary citations are logged below and in the run diary.

[^insead]: Rebalancing-premium-as-strangle and volatility-harvesting literature the synthesis draws on: "The Rebalancing Premium" (INSEAD) https://sites.insead.edu/facultyresearch/research/doc.cfm?did=57836 ; "Chasing Down the Rebalancing Premium" (SOA) https://www.soa.org/globalassets/assets/library/newsletters/risks-and-rewards/2020/september/rr-2020-09-glacy.pdf ; "Maximizing the Rebalancing Premium" (ReSolve) https://investresolve.com/inc/uploads/pdf/maximizing-the-rebalancing-premium.pdf - fixed-weight rebalancing replicates selling European strangles; premium of 1.2-3.3% p.a. in risk-balanced books.

[^schroders]: Schroders (2025). "Diversification, (un)correlation and long-term returns: the case for insurance-linked securities." https://www.schroders.com/en-ch/ch/professional/insights/diversification-un-correlation-and-long-term-returns-the-case-for-insurance-linked-securities/ - cat bonds positive through the GFC, near-untouched in 2020, far smaller losses than stocks/bonds in 2022; "the only truly uncorrelated asset class." Manager COI.

[^nb]: Neuberger Berman. "Catastrophe Bonds: An Uncorrelated Asset Class Amid Global Macroeconomic Uncertainty" / ILS insights. https://www.nb.com/en/global/insights - "No recession ever caused an earthquake, and an Atlantic hurricane is unlikely to trigger a sell-off in the S&P 500." Manager COI.

[^ang]: Ang, A. et al. "Diversification benefits of cat bonds: an in-depth examination." Financial Markets, Institutions & Instruments. https://onlinelibrary.wiley.com/doi/10.1111/fmii.12134 - 2002-2017 spanning tests: cat bonds create previously unattainable portfolios and raise the time-varying Sharpe and maximum-diversification ratio, especially in crisis/high-vol episodes.

[^cp]: Carayannopoulos, P., Perez, M. F. (2014). "Diversification through Catastrophe Bonds: Lessons from the Subprime Financial Crisis." Geneva Papers on Risk and Insurance 40(1). https://doi.org/10.1057/gpp.2014.14 - cat bonds are zero-beta only in non-crisis periods; the Lehman collapse made returns significantly market-correlated via forced liquidation, but the hedge-ratio change was far smaller than other assets and betas normalized post-2009. The honest caveat to the "uncorrelated" claim.

[^role]: "The role of catastrophe bonds in an international multi-asset portfolio: Diversifier, hedge, or safe haven?" Finance Research Letters. https://www.sciencedirect.com/science/article/abs/pii/S1544612319302971 - cat bonds are an effective diversifier against all asset classes, a poor hedge, and a strong safe haven against extreme equity declines only in the post-crisis period.

[^artemis]: Artemis (2026). "UCITS catastrophe bond funds added $5.3bn+ in 2025, reaching $19.12bn AUM." https://www.artemis.bm/news/ucits-catastrophe-bond-funds-added-5-3bn-in-2025-reaching-19-12bn-aum/ - sector ~$19.12bn end-2025, ~31% of outstanding cat-bond risk capital, +$5.3bn (~39%) in 2025; largest strategies Twelve Cat Bond Fund $4.55bn, Schroder GAIA $4.05bn, Fermat fastest-growing; also Icosa, Plenum, Franklin K2, Leadenhall. Verified by fetch 2026-07-04.

[^twelve]: Artemis. "Twelve Cat Bond Fund becomes first UCITS strategy to surpass $4 billion in assets." https://www.artemis.bm/news/twelve-cat-bond-fund-becomes-first-ucits-strategy-to-surpass-4-billion-in-assets/ - Twelve Securis; ISIN IE00BD2B6X61; ~$4.55bn end-2025; weekly liquidity.

[^franklin]: Franklin Templeton. "Franklin Cat Bond UCITS Fund - W (acc) USD - LU3047210656." https://www.franklintempleton.lu/our-funds/price-and-performance/products/42012/BC/franklin-cat-bond-ucits-fund/LU3047210656 - actively managed UCITS cat-bond fund (verified real 2026-07-04).

[^hanetf]: HANetf. "KRC Cat Bond UCITS ETF." https://hanetf.com/fund/catb-cat-bond-etf/ - ISIN IE000UWJUW87, ticker CATB (USD) / ILS (GBP) / C47B (Xetra); HANetf II ICAV, investment manager King Ridge Capital Advisors; TER 1.28%; launched Dec 2025 (Xetra, Borsa Italiana), LSE Jan 2026; ~$12.9m NAV as of Jul 2026. Europe's first listed cat-bond ETF; nascent. Verified by fetch 2026-07-04.
