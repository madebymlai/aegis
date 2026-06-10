---
title: Site Index
tags:
  - index
  - sites
---

# Site Index

Useful sites found during research, organized by category. Add a one-line note on *why* each site is useful.

## Documentation

- [VectorBT PRO docs](https://vectorbt.pro/) - backtesting engine used by Aegis RD

## Data sources

- [World Gold Council - Goldhub](https://www.gold.org/goldhub/data/gold-returns) - gold annual/period returns; COI (industry body), use for uncontested price figures only

## Strategy research

- [AQR - A Century of Evidence on Trend-Following Investing](https://www.chesler.us/resources/academia/A_Century_of_Evidence_on_Trend_Following.pdf) - 1903-2012 trend returns, positive in 9/10 worst 60/40 drawdowns; AQR product paper (COI), hypothetical returns
- [AQR - A Changing Stock-Bond Correlation](https://www.aqr.com/Insights/Research/Journal-Article/A-Changing-Stock-Bond-Correlation) - macro regime model for when bonds stop hedging stocks; AQR COI on the prescription, sound analysis
- [Hedgeweek - CTAs deliver record returns 2022](https://www.hedgeweek.com/trend-followers-turn-leaders-ctas-deliver-record-returns-2022/) - SG Trend Index +27.3% in 2022, best year since 2000
- [NY Fed Liberty Street - The Global Dash for Cash in March 2020](https://libertystreeteconomics.newyorkfed.org/2022/07/the-global-dash-for-cash-in-march-2020/) - why even safe havens were sold for USD in the COVID crash
- [Graham Capital - Trend-Following Primer](https://www.grahamcapital.com/blog/trend-following-primer/) - candid CTA account of why trend gave no protection in fast Q4-2018 reversal
- [Revisiting the Structure of Trend Premia (arXiv 2510.23150, 2025)](https://arxiv.org/html/2510.23150v2) - adjacent trend lookbacks are 0.84-0.90 correlated; a short+long barbell beats dense layering
- [Bruder & Gaussel 2011 / Newfound - Trend: Convexity & Premium](https://blog.thinknewfound.com/2019/02/trend-convexity-premium/) - trend payoff = option convexity + trading-impact premium
- [Baz et al. - Dissecting Investment Strategies in the Cross Section and Time Series (Man/AHL, 2015)](https://www.cmegroup.com/education/files/dissecting-investment-strategies-in-the-cross-section-and-time-series.pdf) - canonical signal-smoothing / response-function reference; CTA COI
- [Portfolio Optimizer - The Turbulence Index: Measuring Financial Risk](https://portfoliooptimizer.io/blog/the-turbulence-index-measuring-financial-risk/) - daily Mahalanobis turbulence formula, percentile-to-cash throttle, ~2-week persistence; practitioner with code
- [Portfolio Optimizer - The Absorption Ratio: Measuring Financial Risk Part 2](https://portfoliooptimizer.io/blog/the-absorption-ratio-measuring-financial-risk/) - AR formula and a replication that found AR *decreases* before crashes (sign-flip vs the original); slow weekly cadence
- [Eurizon SLJ Capital - The Dollar Smile](https://www.eurizonsljcapital.com/dollar-smile/) - Jen's original dollar-smile framework; the dollar gains in risk-off (left) and US rate shocks (right); author's own firm (high COI), mechanism only
- [Portfolio Optimizer - Range-Based Volatility Estimators](https://portfoliooptimizer.io/blog/range-based-volatility-estimators-overview-and-examples-of-usage/) - Parkinson/Garman-Klass/Rogers-Satchell/Yang-Zhang formulas and the overnight-gap understatement caveat; practitioner with derivations
- [Volatility Box - Volatility Regime Detection](https://volatilitybox.com/research/volatility-regime-detection/) - practitioner VIX-vs-MA crossover regime claims (unverified lead/false-positive figures); benchmark against an in-bar trigger, do not trust the numbers
- [Kaminski - Reflections on Ten Years in Trend Following (AlphaSimplex, 2020)](https://www.alphasimplex.com/assets/files/2020.09---10-years-of-trend-following---kaminski.pdf) - crisis windows defined as equity-drawdown episodes; crisis alpha averaged across episodes; CTA COI

## Papers & journals

- [Moskowitz, Ooi & Pedersen 2012 - Time Series Momentum (JFE)](https://w4.stern.nyu.edu/facdir/lpederse/papers/TimeSeriesMomentum.pdf) - foundational TSMOM, profits best in extreme markets, speculators vs hedgers
- [Huang, Li, Wang & Zhou 2020 - Time-series momentum: Is it there? (JFE)](https://down.aefweb.net/WorkingPapers/w717.pdf) - peer-reviewed, COI-free rebuttal of TSMOM significance
- [Baur & Lucey 2010 - Is Gold a Hedge or a Safe Haven? (Financial Review)](https://onlinelibrary.wiley.com/doi/abs/10.1111/j.1540-6288.2010.00244.x) - canonical hedge vs safe-haven definitions
- [Baur & McDermott 2010 - Is Gold a Safe Haven? International Evidence (JBF)](https://www.sciencedirect.com/science/article/abs/pii/S0378426609003343) - gold a safe haven for US/Europe, not for all markets
- [Connolly, Stivers & Sun 2005 - Stock Market Uncertainty and the Stock-Bond Return Relation (JFQA)](https://www.scirp.org/reference/referencespapers?referenceid=1688305) - stock-bond comovement turns negative when VIX spikes
- [Vayanos 2004 - Flight to Quality, Flight to Liquidity, and the Pricing of Risk (NBER)](https://www.nber.org/system/files/working_papers/w10327/w10327.pdf) - mechanism: rising vol raises effective risk aversion, drives flight to safe/liquid assets
- [Ranaldo & Soderlind 2010 - Safe Haven Currencies (Review of Finance)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=999382) - CHF/JPY/USD appreciate in risk-off
- [Baele, Bekaert, Inghelbrecht & Wei 2020 - Flights to Safety (RFS)](https://academic.oup.com/rfs/article-abstract/33/2/689/5512368) - FTS days are <2% of sample, ~2.7% bond-equity differential; rare and episodic
- [Frazzini & Pedersen 2014 - Betting Against Beta (JFE)](https://pages.stern.nyu.edu/~afrazzin/pdf/Betting%20Against%20Beta%20-%20Frazzini%20and%20Pedersen.pdf) - leverage constraints make low-beta cheap; US BAB Sharpe ~0.78 since 1926
- [Baker, Bradley & Wurgler 2011 - Benchmarks as Limits to Arbitrage (FAJ)](https://pages.stern.nyu.edu/~jwurgler/papers/faj-benchmarks.pdf) - low-vol anomaly; $1 low-vol -> $59.55 vs $0.58 high-vol, 1968-2008
- [Blitz & van Vliet 2007 - The Volatility Effect (JPM)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=980865) - global low-vol premium; Robeco COI
- [Ang, Hodrick, Xing & Zhang 2006 - The Cross-Section of Volatility and Expected Returns (JF)](https://onlinelibrary.wiley.com/doi/10.1111/j.1540-6261.2006.00836.x) - IVOL puzzle, COI-free anchor for low-risk anomaly
- [Novy-Marx & Velikov 2022 - Betting Against Betting Against Beta (JFE)](https://mysimon.rochester.edu/novy-marx/research/BABAB.pdf) - peer-reviewed, COI-free counter: BAB Sharpe is a micro-cap construction artifact
- [Fung & Hsieh 2001 - The Risk in Hedge Fund Strategies (RFS)](https://people.duke.edu/~dah7/TheRiskinHedgeFundStrategies.pdf) - trend payoff = lookback straddle; origin of the convexity/whipsaw characterization
- [Harvey et al. 2018 - The Impact of Volatility Targeting (JPM)](https://people.duke.edu/~charvey/Research/Published_Papers/P135_The_impact_of.pdf) - vol-scaling lifts Sharpe only for equity/credit; main benefit is drawdown reduction; Man COI
- [Garg, Goulding, Harvey & Mazzoleni 2023 - Momentum Turning Points (JFE)](https://www.sciencedirect.com/science/article/abs/pii/S0304405X23001034) - fast/slow blend beats either alone; signal disagreement flags whipsaw turning points
- [AQR - You Can't Always Trend When You Want (JPM, 2020)](https://jpm.pm-research.com/content/46/4/52) - trend's weak years come from muted move size, not filterable regimes; the key anti-filter counter
- [Moreira & Muir 2017 - Volatility-Managed Portfolios (JF)](https://amoreira2.github.io/alan-moreira.github.io/VolPortfolios_published.pdf) - in-sample case for scaling down in high vol
- [Cederburg, O'Doherty, Wang & Yang 2020 - On the Performance of Volatility-Managed Portfolios (JFE)](https://www.lehigh.edu/~xuy219/research/COWY.pdf) - OOS counter: vol-managed Sharpe gains generally vanish
- [Chekhlov, Uryasev & Zabarankin 2005 - Drawdown Measure in Portfolio Optimization (IJTAF)](https://www.cis.upenn.edu/~mkearns/finread/drawdown.pdf) - CDaR definition; tunable average-to-max drawdown, convex and optimizable
- [Rockafellar & Uryasev 2000 - Optimization of Conditional Value-at-Risk (J. Risk)](https://www.financerisks.com/filedati/WP/paper/CVaR%20Portfolio%20Optimization.pdf) - CVaR / expected shortfall, coherent and LP-tractable
- [Magdon-Ismail & Atiya 2004 - An Analysis of the Maximum Drawdown Risk Measure (Risk)](https://www.cs.rpi.edu/~magdon/ps/journal/drawdown_RISK04.pdf) - MaxDD grows with track length and is noisy; optimizing on it overfits the worst episode
- [Varga-Haszonits & Kondor 2008 - The Instability of Downside Risk Measures (arXiv)](https://arxiv.org/abs/0811.0800) - VaR/ES/semivariance estimation error diverges when tail data is scarce
- [Guttal, Raghavendra, Goel & Hoarau 2016 - Financial Meltdowns Are Not Critical Transitions (PLoS ONE)](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0144198) - 115yr test: rising variance leads crashes but cannot time them (7 false alarms); the key neutral counter to price-based early warning
- [Kritzman & Li 2010 - Skulls, Financial Turbulence, and Risk Management (FAJ)](https://www.tandfonline.com/doi/abs/10.2469/faj.v66.n5.3) - turbulence = Mahalanobis distance of the return vector; persistence not prediction; authors market turbulence products (COI)
- [Kritzman, Li, Page & Rigobon 2011 - Principal Components as a Measure of Systemic Risk (JPM)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1633027) - the absorption ratio; claimed ~1mo lead before declines, State Street product (COI), contested by replication
- [Forbes & Rigobon 2002 - No Contagion, Only Interdependence (JF)](https://onlinelibrary.wiley.com/doi/10.1111/0022-1082.00494) - correlation spikes are a volatility-conditioning artifact; a correlation-spike trigger is coincident, not leading
- [Cheema, Faff & Szulczyk 2022 - How safe are the safe haven assets? (IRFA)](https://www.sciencedirect.com/science/article/pii/S1057521922001934) - safe-haven character is regime-dependent; Treasuries and gold failed across GFC vs COVID, the dollar held best
- [Avdjiev, Bruno, Koch & Shin 2019 - The Dollar as a Global Risk Factor (IMF Econ Rev / BIS WP695)](https://www.bis.org/publ/work695.pdf) - a stronger broad dollar tightens global financial conditions; the dollar-beta / dollar-as-risk-factor anchor
- [Lustig, Roussanov & Verdelhan 2011 - Common Risk Factors in Currency Markets (RFS / NBER w14082)](https://www.nber.org/system/files/working_papers/w14082/w14082.pdf) - dollar carry earns a premium for being long USD in bad global states
- [Habib & Stracca 2011 - What makes a safe haven currency? (ECB WP1288)](https://www.ecb.europa.eu/pub/pdf/scpwps/ecbwp1288.pdf) - safe-haven currencies; the dollar's haven status is messier than the yen's or franc's
- [Maurer, To & Tran - The US dollar: Not a traditional safe haven (CEPR VoxEU)](https://cepr.org/voxeu/columns/us-dollar-not-traditional-safe-haven) - the dollar appreciates only temporarily in risk-off; haven role rests on the convenience yield; strongest bearish-dollar counter
- [Politis & Romano 1994 - The Stationary Bootstrap (JASA)](https://www.tandfonline.com/doi/abs/10.1080/01621459.1994.10476870) - random-length block resampling for error bars on path-dependent statistics; the regularization tool for few crisis windows
- [Bailey, Borwein, Lopez de Prado & Zhu - The Probability of Backtest Overfitting](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2326253) - overfit probability grows with number of trials; the load-bearing source against single-window optimization
- [Bailey & Lopez de Prado 2014 - The Deflated Sharpe Ratio (JPM)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460551) - deflate performance by trials/skew/kurtosis; motivates penalizing a one-window crisis statistic
- [Parkinson 1980 - The Extreme Value Method for Estimating the Variance of the Rate of Return (J. Business)](https://www.jstor.org/stable/2352357) - high-low range vol estimator, ~5x more efficient than close-to-close
- [Garman & Klass 1980 - On the Estimation of Security Price Volatilities from Historical Data (J. Business)](https://www.jstor.org/stable/2352358) - OHLC range vol estimator, ~7.4x efficiency; assumes no overnight gap
- [Yang & Zhang 2000 - Drift-Independent Volatility Estimation from High, Low, Open, Close (J. Business)](https://www.jstor.org/stable/10.1086/209650) - the one range estimator with an overnight-jump term; robust to gaps, the primary fast-vol trigger
- [Lou, Polk & Skouras 2019 - A Tug of War: Overnight Versus Intraday Expected Returns (JFE)](https://www.sciencedirect.com/science/article/abs/pii/S0304405X19300650) - overnight (close-to-open) and intraday components are distinct; overnight carries downside-risk info
- [Karpoff 1987 - The Relation between Price Changes and Trading Volume: A Survey (JFQA)](https://www.cambridge.org/core/journals/journal-of-financial-and-quantitative-analysis/article/abs/relation-between-price-changes-and-trading-volume-a-survey/DBE2C70FA41E390EB8FA418BBFFD76C8) - volume is contemporaneous with volatility (shared latent driver), not a precursor; volume is a coincident-to-lagging crash signal
- [Whaley 2009 - Understanding the VIX (JPM)](https://jpm.iijournals.com/content/35/3/98) - VIX is the implied vol of SPX options; the negative-asymmetric contemporaneous link is why VIX mirrors the drop rather than leading it
- [Giot 2005 - Relationships Between Implied Volatility Indexes and Stock Index Returns (JPM)](https://jpm.pm-research.com/content/31/3/92) - tests VIX as a leading indicator; the only forward signal is contrarian (high VIX -> positive forward returns); the key VIX-not-leading counter
- [Bollerslev, Tauchen & Zhou 2009 - Expected Stock Returns and Variance Risk Premia (RFS)](https://public.econ.duke.edu/~boller/Published_Papers/rfs_09.pdf) - the variance risk premium predicts returns at a quarterly horizon; needs intraday RV, wrong horizon for fast-crash onset
- [Pyun 2019 - Variance risk in aggregate stock returns and time-varying return predictability (JFE)](https://www.sciencedirect.com/science/article/abs/pii/S0304405X18302782) - VRP predictive coefficients are unstable OOS; the peer-reviewed counter to relying on the variance risk premium

## Blogs & newsletters

- [QuantPedia - Why Did Trend-Following Underperform Last Decade?](https://quantpedia.com/why-did-trend-following-underperform-in-the-last-decade/) - documents the ~2011-2019 trend "lost decade"
- [Evidence Investor - Deep Dive: Low-Volatility Investing](https://www.evidenceinvestor.com/post/low-volatility-investing) - low-vol decay and crowding; "only works when it's cheap"
- [Morningstar - How Low-Volatility ETFs Fared in Market Turmoil](https://www.morningstar.com/funds/how-3-types-low-volatility-etfs-have-fared-during-recent-market-turmoil) - USMV/SPLV drawdowns vs SPY in 2020 and 2022
- [Macrosynergy - Detecting trends and mean reversion with the Hurst exponent](https://macrosynergy.com/research/detecting-trends-and-mean-reversion-with-the-hurst-exponent/) - why Hurst/efficiency-ratio regime filters are lagging meta-filters, not signals
- [StockCharts - Kaufman's Adaptive Moving Average (Efficiency Ratio)](https://chartschool.stockcharts.com/table-of-contents/technical-indicators-and-overlays/technical-overlays/kaufmans-adaptive-moving-average-kama) - Efficiency Ratio definition for trend-vs-range regime gating

## Tools

- [Bacon - Practical Portfolio Performance Measurement and Attribution (Wiley)](https://www.wiley.com/en-us/Practical+Portfolio+Performance+Measurement+and+Attribution) - standard definitions for Calmar/MAR, Sterling, Burke, Martin/UPI, Pain ratios
- [Morningstar - Up/Down Capture methodology](https://ycharts.com/glossary/terms/upside_downside_ratio) - down-capture as a defensive-asymmetry metric; below 100 defensive, negative gains in crashes
- [Goldsticker - Up-market capture minus down-market capture (Pensions & Investments, 2018)](https://www.pionline.com/article/20180628/ONLINE/180629854/commentary-up-market-capture-minus-down-market-capture/) - the capture spread as a single ranking number; penalizes a smooth-but-dead sleeve
- [LongTailAlpha - Tail Risk Hedging Performance: Measuring What Counts (2021)](https://www.longtailalpha.com/wp-content/uploads/2021/11/Tail-Risk-Hedging-Performance-Measurement.pdf) - practitioner case for crisis-gain / drawdown-reduction metrics over Sharpe; tail-fund COI

## Communities

-
