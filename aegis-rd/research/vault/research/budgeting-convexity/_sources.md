---
title: "Budgeting Convexity - source corpus"
paper: "Budgeting Convexity"
status: Phase 1 (literature) - source corpus
tags:
  - sources
---

# Budgeting Convexity - source corpus (Phase 1)

Annotated bibliography + literature matrix for the architecture paper. The plan is
[[research/budgeting-convexity/_plan|_plan]]; the config is confirmed there.

## Search strategy

Sources were gathered three ways and each claim leads with its **ex-ante rationale**, per
[[research/README|research/README]] ("a backtest estimates an effect we already expect; it never
discovers one"):

1. **Legacy citations re-validated** - the footnotes of the folded articles, treated as leads not
   facts, confirmed against the primary source.
2. **Independent Exa scan (2026-07-24)** - the go/no-go pass, run for *both* confirming and
   contradicting evidence on the two load-bearing claims.
3. **Gap fills** - limits-to-arbitrage (persistence foundation) and ERC/HRP robustness
   (construction basis).

Flags: **[F]** foundation, **[PRO]** confirms a load-bearing claim, **[CON]** genuine
counter-evidence carried on purpose, **COI** conflict of interest noted. Peer-reviewed unless
marked *preprint* / *practitioner*.

## Two honest caveats the corpus forces (carry into drafting)

- **Skew: cross-sectional ranking vs book-level budgeting.** Realized skew is a *robust
  cross-sectional predictor* (Baltas-Salinas) even though *book-level net-skew budgeting* fails.
  The paper must argue the latter, and explicitly not claim skew is a mere passive label.
- **Risk-budgeting robustness is not HRP magic.** ERC / inverse-vol / HRP all beat
  *mean-variance* out of sample by sidestepping return estimation (DeMiguel), but HRP does **not**
  reliably beat other risk-based methods or Ledoit-Wolf shrinkage (Empirical Economics 2026). The
  construction claim is "budget risk, do not optimize returns," not "HRP is superior."

---

## Chapter 2 - The convexity axis and its two poles

- **Lempériere, Deremble, Nguyen, Seager, Potters & Bouchaud (2017)**, "Risk Premia: Asymmetric
  Tail Risks and Excess Returns," *Quantitative Finance* 17(1). [F] Sharpe lines up with *negative
  skew*, not volatility; trend the clean positive-skew outlier. **COI** (CFM runs the strategies).
- **Bouchaud et al. (2017)**, "Trends & Risk Premia: Update," arXiv:1708.07637. [F] Puts SR = 1/3 -
  zeta/4 on the line and extends it OOS to option strangles. *preprint*, **COI** (CFM).
- **Lettau, Maggiori & Weber (2014)**, "Conditional risk premia in currency markets and other
  asset classes," *JFE* 114(2). [F] Downside-beta CAPM jointly prices FX/equity/options/commodities/
  bonds (74% vs -17% for CAPM). The axis by an independent method, no product COI.
- **Bollerslev & Todorov (2011)**, "Tails, Fears, and Risk Premia," *Journal of Finance* 66(6). [F]
  Jump-tail fear is ~2/3 of the equity premium and >half the VRP - the price of the crash,
  separated from variance. Independent method, no COI.
- **Fung & Hsieh (2001)**, "The Risk in Hedge Fund Strategies," *RFS* 14(2). [F] Trend replicates
  lookback straddles - structurally long gamma. The payoff-algebra basis for the long pole.
- **Capital Fund Management (2018)**, "The Convexity of Trend Following." Trend P&L = one-half
  (squared cumulative move - summed squared daily moves): convexity is a multi-period quantity,
  capped by vol-scaling. **COI** (CFM). Grounds the "vol-targeting caps the tail" tension.
- **Ilmanen (2012)**, "Do Financial Markets Reward Buying or Selling Insurance...," *FAJ* 68(5).
  Buying insurance is poorly rewarded across asset classes - the cross-asset restatement. **COI** (AQR).
- **Carr & Wu (2009)**, "Variance Risk Premiums," *RFS* 22(3); **Bollerslev, Tauchen & Zhou
  (2009)**, *RFS* 22(11). Variance sellers earn a premium as crash compensation - the short pole's payer.

## Chapter 2/3 - The durable payer (ex-ante persistence rationale)

- **Shleifer & Vishny (1997)**, "The Limits of Arbitrage," *Journal of Finance* 52(1). [F] Anomalies
  persist where arbitrage is capital-constrained and idiosyncratically risky; arbitrageurs are
  *least* able to correct mispricing precisely when it is largest. The first-principles reason a
  premium is not competed away - the paper's core persistence argument.
- **De Long, Shleifer, Summers & Waldmann (1990)**, "Noise Trader Risk in Financial Markets,"
  *JPE* 98(4). [F] Unpredictable sentiment is itself a priced risk that deters arbitrage - prices
  diverge from fundamentals even absent fundamental risk. Underpins the behavioural pole.
- **Gromb & Vayanos (2010)**, "Limits of Arbitrage," *Annual Review of Financial Economics* 2.
  Survey nesting risk, short-sale, leverage/margin, and equity-capital constraints - the menu of
  reasons a payer cannot leave. Independent, no COI.
- **McLean & Pontiff (2016)**, "Does Academic Research Destroy Stock Return Predictability?,"
  *Journal of Finance* 71(1). Returns 26% lower OOS, 58% post-publication - the survivorship /
  publication-bias guard the whole research stance rests on.
- **Brunnermeier, Nagel & Pedersen (2008)**, "Carry Trades and Currency Crashes." Funding-liquidity
  unwinds of crowded positions produce carry's negative skew; VIX spikes coincide. **COI** (AQR).
  The *mechanism* that fixes carry's skew sign ex-ante (present in FX, absent where it does not apply).
- **Moskowitz, Ooi & Pedersen (2012)**, "Time Series Momentum," *JFE* 104(2). Speculators profit
  from hedgers; straddle-like exposure to large moves. **COI** (AQR).
- **Kang, Rouwenhorst & Tang (2020)**, "A Tale of Two Premiums," *Journal of Finance* 75(1).
  Hedgers pay speculators an insurance premium at long horizons - the risk-premium counter-reading
  of trend income; disciplines the "pure alpha" label. No COI.

## Chapter 3 - Why convexity classifies but cannot budget (the pivot)

- **Harvey & Siddique (2000)**, "Conditional Skewness in Asset Pricing Tests," *Journal of Finance*
  55(3). [F] Systematic (co)skewness is priced, ~3.6%/yr. The classifier's origin.
- **Harvey & Siddique (2023)**, "Conditional Skewness in Asset Pricing: 25 Years of OOS Evidence,"
  *Critical Finance Review* 12. [PRO] Premium's *sign* always positive OOS where HML/momentum flip;
  magnitude swings 1.4-4.7% by research choice; "very challenging to measure higher moments."
  Sign stable, magnitude not - the pivot in one source.
- **Anghel, Caraiani, A. Rosu & I. Rosu (2023)**, "Systematic Skewness: Two Decades Later," *CFR*.
  [PRO/CON] Replicates the premium but the HS proxy is "very noisy," pricing evidence
  "inconclusive," not significant at 90%. Confirms magnitude instability; a candid mixed result.
- **Koijen, Moskowitz, Pedersen & Vrugt (2018)**, "Carry," *JFE* 127(2). [PRO] Currency/options
  carry strongly negative-skewed, but equities/Treasuries/credit carry *positive*-skewed, and the
  diversified global carry factor has *negligible* skewness. Skew is not a universal property. **COI** (AQR).
- **Lassance & Vrins**, "Portfolio Selection: A Target-Distribution Approach" / OMVE. [PRO] No OOS
  benefit to moving off the mean-variance-efficient frontier; higher-moment optimization exacerbates
  estimation risk. You cannot budget on skew directly.
- **Martellini & Ziemann (2010)**, "Improved Estimates of Higher-Order Comoments," *RFS* 23(4).
  [PRO] Higher-moment portfolios cannot beat minimum-variance even with robust moment estimates.
- **Baltas & Salinas (2022)**, "Cross-Asset Skew," *JPM* 48(4). [CON] Realized skew is a *pervasive
  cross-sectional* predictor across commodities/bonds/equities/FX; cross-asset skew Sharpe 0.73,
  robust across measures. The counter to carry into the pivot: skew ranks, even if it cannot budget.
- **Le et al. (2023)**, "Modeling skewness in portfolio choice," *J. Futures Markets*. [CON]
  Option-implied skew forecasts realized skew (up to 35% R2) and improves portfolios - realized
  skew is noisy but option-implied skew is usable.
- **Pyun (2019)**, "Variance risk in aggregate stock returns and time-varying return predictability,"
  *JFE* 132(1). VRP predictive coefficients unstable OOS - timing convexity inherits that instability.

## Chapter 4 - The roster (all tiers)

- **Baltussen, Martens & van der Linden (2026)**, "The Best Defensive Strategies: Two Centuries of
  Evidence," *FAJ* 82(1). [F] DAR4020 (defensive-factor selection) and trend are the most robust
  complementary defenses: DAR arrives with negative beta at onset, trend improves as dislocation
  persists. The Target-tier and Floor-responder benchmark.
- **Bhansali, Davis, Dorsten & Rennison (2015)**, "Carry and Trend in Lots of Places," *JPM*.
  Carry and trend mutually diversifying across 20 markets 1960-2014, most in extremes. **COI** (PIMCO).
- **Olszewski & Zhou (2013)**, "Strategy diversification: momentum and carry in FX," *J. Derivatives
  & Hedge Funds* 19(4). Equal-weight FX momentum+carry lifts Sharpe 0.79/0.63 -> 0.98, Calmar +71%/+289%.
- **Hurst, Ooi & Pedersen (2017)**, "A Century of Evidence on Trend-Following," *JPM* 44(1). Positive
  every decade since 1880, best in low-correlation environments - the substrate requirement. **COI** (AQR).
- **Asif, Frömmel & Mende (2022)**, "The crisis alpha of managed futures: Myth or reality?," *IRFA*
  80. Peer-reviewed confirmation (outside the CTA industry) that trend earns crisis alpha from fast
  de-risking, not a static hedge. Corroborates Greyserman & Kaminski (2014).
- **Baltussen, Swinkels & van Vliet (2021)**, "Global Factor Premiums," *JFE* 142(3). 24
  factor/asset combos 1800-2016 survive multiple-testing controls - the Expansion tier's basis.
- **Brown, Gregoriou & Pascalau (2011)**, "Diversification in Funds of Hedge Funds: Is It Possible to
  Overdiversify?," *RAPS* 1(1). Past ~20 funds, over-diversification *raises* left-tail risk and
  lowers returns - the failure the order exists to avoid.
- **Grinold (1989)**, "The Fundamental Law of Active Management," *JPM* 15(3). IR ~ IC * sqrt(BR),
  breadth = *independent* bets. **Meucci (2009)**, "Managing Diversification," *Risk* 22(5) -
  effective number of bets = exponential entropy of uncorrelated risk. **Choueifaty & Coignard
  (2008)**, "Toward Maximum Diversification," *JPM* 35(1) - diversification ratio squared = independent
  factors. The breadth measures for the Expansion tier.
- **Carli, Deguest & Martellini (2014)**, "Improved Risk Reporting with Factor-Based Diversification
  Measures," EDHEC. Effective number of bets predicts performance *specifically in bear markets* -
  orthogonal breadth pays in stress.
- **AQR (2020)**, "Tail Risk Hedging: Contrasting Put and Trend Strategies." [PRO] Puts pay in fast
  crashes, trend in protracted bears; slow drawdowns do more damage, so trend is the workhorse and
  puts the supplement. The Target-tier speed-gap argument. **COI** (AQR).

## Chapter 5 - The construction

- **DeMiguel, Garlappi & Uppal (2009)**, "Optimal Versus Naive Diversification," *RFS* 22(5). [F]
  No optimizing model consistently beats 1/N OOS - the estimation window needed is far longer than
  available. Why the construction budgets *risk*, never forecasts returns.
- **Maillard, Roncalli & Teiletche (2010)**, "The Properties of Equally Weighted Risk Contribution
  Portfolios," *JPM* 36(4). The ERC foundation used across sleeves.
- **Lopez de Prado (2016)**, "Building Diversified Portfolios that Outperform Out-of-Sample," *JPM*
  42(4). HRP: cluster, quasi-diagonalize, recursive bisection - avoids inverting the covariance.
  The hierarchical (group) seam.
- **Empirical Economics (2026)**, "Hierarchical risk clustering versus traditional risk-based
  portfolios." [CON] HRP does **not** reliably beat other risk-based methods OOS (and Ledoit-Wolf
  shrinkage often wins). The honest caveat: risk-budgeting robustness is generic, not HRP-specific.
- **Bongaerts, Kang & van Dijk (2020)**, "Conditional Volatility Targeting," *FAJ* 76(4). [PRO]
  Down-only / unlevered vol targeting improves Sharpe and cuts drawdowns for constrained books - the
  down-only ceiling.
- **Cederburg, O'Doherty & Wang (2020)**, "On the Performance of Volatility-Managed Portfolios,"
  *JFE* 138(1). [PRO] Vol-managed portfolios do not systematically outperform OOS; the gains are
  spanning-regression artifacts from structural instability. Timing convexity via a scaled signal fails.
- **"When simplicity beats optimization" (2026)**, *FMPM*. [PRO] Vol management + factor MV
  optimization do not beat simple diversification once estimation risk and recursive implementation
  are honest. Simple diversification is hard to beat.
- **Israelov & Nielsen (2015)** "Still Not Cheap," *JPM* 41(4); **Israelov (2019)** "Pathetic
  Protection," *JAI*. Standing protective puts deliver worse drawdown-per-return than holding less
  risk, except against sudden gaps - the tail as a cost budget, not a default. **COI** (AQR).
- **Costa & Kwon (2019)**, "Risk parity portfolio optimization under a Markov regime-switching
  framework," *Quantitative Finance* 19(3). [CON] Regime-switching risk parity *consistently
  outperforms* the nominal OOS. Lands on the permitted *risk-conditioning* side of the line.
- **Uysal & Mulvey (2021)**, "A Machine Learning Approach in Regime-Switching Risk Parity Portfolios,"
  *JFDS*. [CON] Regime overlay improves risk-adjusted returns over nominal risk parity.
- **Andersen, Bollerslev, Christoffersen & Diebold / "The Economic Value of Volatility Timing"**
  (*Journal of Finance* 2001, Fleming-Kirby-Ostdiek). [CON] Volatility (risk) timing beats static
  portfolios, robust to estimation risk and costs - risk-conditioning works; return-timing does not.
- **One River (2024)**, "The Convexity (Re)Balancing Act." [PRO] Any disciplined rebalancing of a
  convex sleeve beats no-rebalance; calendar reduces path dependency vs threshold. *practitioner*.
- **Man Group**, "Creating Portfolio Convexity: Trend Versus Options." [PRO] Systematic overlays
  deliver a near-identical convexity profile to puts at a *positive* average return. *practitioner*.
- **LongTail Alpha / Bhansali (2020)**, "Monetization Matters." [PRO] Active monetization of hedges
  improves outcomes vs passive hold - the tail is sized as a budget and monetized by rebalance. *practitioner*.
- **Schwalbach & Auret (2025)**, "Enhancing global equity returns with trend-following and tail-risk
  hedging overlays," *IAJ*. Slow trend + option tail via portable alpha improved all nine crises
  (~0.25%/mo after controls) - the slow-plus-fast complementarity.
- **Noguer i Alonso & Al Fallouji (2026)**, "Tail Risk Management with Puts and Trend Following: A
  CVaR Framework." Analytical separation: puts reprice on jump impact, trend is late (its signal must
  cross zero) but defensive in persistent drawdowns; a fixed hybrid reduces CVaR. *preprint*. The
  Floor+Target speed-gap formalized.

---

## Gaps deliberately not filled

- No new search for the axis's three-literatures, the roster benchmarks, or the VRP payer - the
  legacy citations re-validated cleanly and are primary and peer-reviewed.
- Implementation-level sourcing (how to build each sleeve) belongs to the **seat papers**, not here.

## Next: Phase 2 (architecture / outline)

Corpus is complete and mapped to chapters. Phase 2 builds the detailed outline + evidence map
(which source supports which claim in which paragraph) from this corpus and the
[[research/budgeting-convexity/_plan|chapter plan]].
