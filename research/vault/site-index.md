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
- [Antonacci - Optimal Momentum (dual momentum papers and rebuttals)](https://www.optimalmomentum.com/) - GEM rules, extended backtests, and the fragility rebuttal; high COI (sells the result), index-level pre-cost numbers
- [Faber - Relative Strength Strategies for Investing (Cambria, 2010)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1585517) - top-k rotation tables incl. turnover (281-378%/yr) and the relative-only vs trend-filtered drawdown gap; Cambria COI
- [Newfound - Fragility Case Study: Dual Momentum GEM](https://blog.thinknewfound.com/2019/01/fragility-case-study-dual-momentum-gem/) - 2,151bp single-year spread from a one-month lookback change; the spec-luck exhibit
- [Newfound - Quantifying Timing Luck](https://blog.thinknewfound.com/2018/01/quantifying-timing-luck/) - rebalance-day dispersion formula; 150bp/yr from trade date alone in small-N tactical books
- [ReSolve - Global Equity Momentum: A Craftsman's Perspective](https://investresolve.com/inc/uploads/pdf/global-equity-momentum-a-craftsmans-perspective.pdf) - 1,226-spec GEM replication with block bootstrap; published spec indistinguishable from the median; ensemble COI
- [ReSolve - Tactical Alpha and the Fundamental Law](https://investresolve.com/tactical-alpha-theory-practice-pt-i-fundamental-law-of-active-management/) - effective-breadth math for small asset-class universes; their pro-TAA argument requires uncorrelated assets (cuts against correlated-block ranks)
- [Keller & Keuning - PAA / VAA breadth-momentum papers (SSRN)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2759734) - breadth-driven cash fraction as small-N crash protection (external echo of our breadth throttle); heavy in-sample tuning, COI
- [Allocate Smartly - TAA strategy tracker](https://allocatesmartly.com/tactical-asset-allocation-performance-during-the-2022-bear-market/) - net-of-cost tracking of ~60 published TAA strategies; the 2022 rate-sensitive-fallback split and the middling-2023 read
- [Top Traders Unplugged - Trend Following Performance Reports](https://www.toptradersunplugged.com/trend-following-performance-report-december-2023/) - monthly SG Trend / BTOP50 index prints; SG Trend 2023 -4.16%
- [Szado 2020 - Portfolio Diversification Potential of Long VIX Futures (Cboe)](https://cdn.cboe.com/resources/education/research_publications/Szado_Portfolio_Diversification_LONG_VIX_fut_&_opt_June_15_2020.pdf) - the quantified 5%-VIX-sleeve ledger (return 7.5->4%/yr for MaxDD -34.8->-27%, 2006-17); Cboe-funded COI, honest about drag
- [Six Figure Investing - VIX ETP mechanics and the Feb-2018 post-mortem](https://www.sixfigureinvesting.com/2019/02/what-caused-the-february-5th-2018-volatility-spike-xiv-termination/) - best practitioner source on VIX ETP roll/settlement mechanics; the 4pm-close vs 4:15pm-settlement artifact
- [AMF 2018 - The impact of VIX products in the February 2018 volatility episode](https://www.amf-france.org/sites/institutionnel/files/contenu_simple/lettre_ou_cahier/risques_tendances/Heightened%20volatility%20in%20early%20February%202018%20the%20impact%20of%20VIX%20products.pdf) - regulator post-mortem, no COI; ETF-vs-ETN distinction and the rebalancing feedback loop
- [Lavaca Capital via Cboe Insights - The VIX Index and Muted Volatility in 2022](https://www.cboe.com/insights/posts/the-vix-index-and-muted-volatility-in-2022/) - why the 2022 grind starved vol products: VIX 28.7 vs 37.4 historical norm for comparable drawdowns
- [ETF Stream - Why Barclays suspended VXX creations (2022)](https://www.etfstream.com/articles/why-barclays-suspended-vxx-and-oil-etn-creations) - the ETN structural hazard realized: $15.2bn over-issuance, creation halt, 15% premiums
- [RCM Alternatives - Is the CTA Sky Falling (Again)? (Mar 2018)](https://www.rcmalternatives.com/2018/03/is-the-cta-sky-falling-again/) - SG CTA Index worst month since Nov 2001 in Feb-2018; CTAs were long equities into the fast crash
- [BarclayHedge - SG Prime Services index tables](https://portal.barclayhedge.com/cgi-bin/indices/displayHfIndex.cgi?indexCat=SG-Prime-Services-Indices&indexName=SG-Trend-Index) - public annual return series for SG Trend / SG CTA indices
- [AQR - Chasing Your Own Tail (Risk), Revisited (2019)](https://www.aqr.com/Insights/Research/White-Papers/Chasing-Your-Own-Tail-Risk-Revisited) - 2.0%/yr put-protection drag in both samples; fn24 denominator math (3% sleeve needs ~805% payoff); fn25 concedes the variance-drag channel; AQR COI
- [AQR - Tail Risk Hedging: Contrasting Put and Trend Strategies (2020)](https://www.aqr.com/Insights/Research/White-Papers/Tail-Risk-Hedging-Contrasting-Put-and-Trend-Strategies) - all six put variants bled every decade 1985-2020; puts win fast crashes 10/10, trend wins grinds; Eurekahedge tail index ~-2%/yr since 2008
- [Universa/Spitznagel - The Volatility Tax (2018)](https://operators.macro-ops.com/wp-content/uploads/2019/01/Universa_Mark-Spitznagel_Volatility-Tax.pdf) - the geometric-vs-arithmetic insurance argument from the pro camp; SEVERE COI, use the math not the numbers
- [Aaron Brown (Bloomberg Opinion, 2023) - Universa's return is legit, with an asterisk](https://www.bloomberg.com/opinion/articles/2023-04-06) - adversarial denominator hygiene: the 3,612% is on premium spent; portfolio-level March-2020 effect ~+12.8pp
- [Bhansali/LongTail Alpha - Monetization Matters (2020)](https://www.longtailalpha.com/wp-content/uploads/2020/07/Monetization-Matters.pdf) - held-to-expiry round-trips destroy even 70x payoffs; monetization multiples by crash type; SEVERE COI
- [Salt Financial - Are Low Volatility Strategies Broken? (2020)](https://saltfinancial.com/insights/blog/are-low-volatility-strategies-broken/) - min-vol fell as much as the market in the 2020 gap crash (USMV -35.7%); attenuation is not convexity
- [Duffie 2020 - Still the World's Safe Haven? (Brookings)](https://www.brookings.edu/articles/still-the-worlds-safe-haven/) - the March-2020 Treasury dash-for-cash; safe-haven holdings face wrong-way liquidity risk at the equity low

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
- [Goyal & Jegadeesh 2018 - Cross-Sectional and Time-Series Tests of Return Predictability (RFS)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2610288) - TSMOM minus CSMOM = time-varying net-long exposure; the subsumption claim is a scaling artifact
- [Daniel & Moskowitz 2016 - Momentum Crashes (JFE)](https://www.nber.org/papers/w20439) - momentum crashes are short-leg events in post-bear rebounds; long winners lag the recovery for years
- [Barroso & Santa-Clara 2015 - Momentum Has Its Moments (JFE)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2041429) - vol-scaling momentum: Sharpe 0.53 to 0.97, max drawdown -97% to -45%
- [Asness, Moskowitz & Pedersen 2013 - Value and Momentum Everywhere (JF)](https://onlinelibrary.wiley.com/doi/10.1111/jofi.12021) - CSMOM Sharpe by asset class: country equities 0.73, commodities 0.63, bonds 0.06; rank value needs a heterogeneous cross-section
- [McLean & Pontiff 2016 - Does Academic Research Destroy Stock Return Predictability? (JF)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2156623) - 26% OOS / 58% post-publication decay across 97 predictors; the base-rate haircut for any published rule
- [Lewellen 2002 - Momentum and Autocorrelation in Stock Returns (RFS)](https://faculty.tuck.dartmouth.edu/images/uploads/faculty/jonathan-lewellen/Momentum.pdf) - portfolio-level momentum runs on cross-serial covariance, not own-trend; fragile mechanism in correlated blocks
- [Blitz & van Vliet 2008 - Global Tactical Cross-Asset Allocation (JPM)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1079975) - momentum+value rotation works at N=12 asset classes, 1986-2007; Robeco COI
- [Bird, Gao & Yeung 2017 - TS and CS momentum under alternative implementations (AJM)](https://journals.sagepub.com/doi/abs/10.1177/0312896215619965) - head-to-head implementation comparison; TSMOM's edge is market-state-varying exposure
- [Eraker & Wu 2017 - Explaining the negative returns to volatility claims (JFE)](https://ideas.repec.org/a/eee/jfinec/v125y2017i1p72-98.html) - constant-maturity 1-mo VIX futures lose ~30%/yr as an equilibrium variance risk premium; the decay will not close
- [Whaley 2013 - Trading Volatility: At What Cost? (JPM)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2261387) - VIX ETP contango trap by the VIX's designer; ~80% of days in contango; prefer mid-term products
- [Simon & Campasano 2014 - The VIX Futures Basis (J. Derivatives)](https://github.com/emintham/Papers/blob/master/Simon,Campasano-%20The%20VIX%20Futures%20Basis:%20Evidence%20and%20Trading%20Strategies.pdf) - contango frequency conditional on VIX level (78-91% when VIX < 20)
- [Augustin, Cheng & Van den Bergen 2021 - Volmageddon and the Failure of Short Volatility Products (FAJ)](https://rpc.cfainstitute.org/research/financial-analysts-journal/2021/volmageddon-failure-short-volatility-products) - the Feb-5-2018 rebalancing feedback loop; the spike was real and intraday-delivered
- [Deng, McCann & Wang 2012 - Are VIX Futures ETPs Effective Hedges? (JII)](https://www.slcg.com/files/research-papers/Are_VIX_Futures_ETPs_Effective_Hedges.pdf) - short-term ETPs ineffective buy-and-hold hedges (roll yield); litigation-consultancy COI
- [Campbell, Pflueger & Viceira 2020 - Macroeconomic Drivers of Bond and Equity Risks (JPE)](https://www.journals.uchicago.edu/doi/abs/10.1086/707766) - bond beta to stocks is a macro-regime variable; switched sign ~2001, can switch back; why duration fails rate-shock crashes
- [Israelov 2019 - Pathetic Protection (JAI)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2934538) - PPUT 1986-2016 matched by 36.5% SPX + 63.5% cash with better drawdowns; put alpha -1.8%/yr; AQR COI
- [Ilmanen 2012 - Do Financial Markets Reward Buying or Selling Insurance? (FAJ)](https://www.tandfonline.com/doi/abs/10.2469/faj.v68.n5.7) - buying catastrophe insurance is poorly rewarded across asset classes; AQR COI
- [Litterman 2011 - Who Should Hedge Tail Risk? (FAJ)](https://www.tandfonline.com/doi/abs/10.2469/faj.v67.n3.5) - tail insurance is the most expensive way to cut equity risk; equilibrium framing
- [Peters & Adamou - Insurance makes wealth grow faster (arXiv/AAS)](https://arxiv.org/abs/1507.04655) - peer-reviewed ergodicity result: expectation-reducing insurance can raise time-average growth; the COI-free backbone of the volatility-tax argument
- [Sepp 2018 - Trend-Following for Tail-Risk Hedging (SSRN 3167787)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3167787) - trend convexity depends on measurement frequency, flat-to-negative at daily/weekly horizons; why CTAs miss fast crashes

## Blogs & newsletters

- [QuantPedia - Why Did Trend-Following Underperform Last Decade?](https://quantpedia.com/why-did-trend-following-underperform-in-the-last-decade/) - documents the ~2011-2019 trend "lost decade"
- [Evidence Investor - Deep Dive: Low-Volatility Investing](https://www.evidenceinvestor.com/post/low-volatility-investing) - low-vol decay and crowding; "only works when it's cheap"
- [Morningstar - How Low-Volatility ETFs Fared in Market Turmoil](https://www.morningstar.com/funds/how-3-types-low-volatility-etfs-have-fared-during-recent-market-turmoil) - USMV/SPLV drawdowns vs SPY in 2020 and 2022
- [Macrosynergy - Detecting trends and mean reversion with the Hurst exponent](https://macrosynergy.com/research/detecting-trends-and-mean-reversion-with-the-hurst-exponent/) - why Hurst/efficiency-ratio regime filters are lagging meta-filters, not signals
- [StockCharts - Kaufman's Adaptive Moving Average (Efficiency Ratio)](https://chartschool.stockcharts.com/table-of-contents/technical-indicators-and-overlays/technical-overlays/kaufmans-adaptive-moving-average-kama) - Efficiency Ratio definition for trend-vs-range regime gating
- [Morningstar - Why Tactical-Allocation Funds Failed Again](https://www.morningstar.com/funds/why-tactical-allocation-funds-failedagain) - live category data: tactical funds entered 2023 at ~40% equity / 29% cash and missed the recovery
- [Aissaoui - Dual Momentum pre/post-publication performance](https://www.linkedin.com/pulse/dual-momentum-pre-post-publication-performance-abdennour-aissaoui) - GEM 2014-2021: 5.89% CAGR at higher vol, -33.7% max drawdown vs -22.7% in the backtest; single-source, drawdown corroborated by trackers

## Tools

- [Bacon - Practical Portfolio Performance Measurement and Attribution (Wiley)](https://www.wiley.com/en-us/Practical+Portfolio+Performance+Measurement+and+Attribution) - standard definitions for Calmar/MAR, Sterling, Burke, Martin/UPI, Pain ratios
- [Morningstar - Up/Down Capture methodology](https://ycharts.com/glossary/terms/upside_downside_ratio) - down-capture as a defensive-asymmetry metric; below 100 defensive, negative gains in crashes
- [Goldsticker - Up-market capture minus down-market capture (Pensions & Investments, 2018)](https://www.pionline.com/article/20180628/ONLINE/180629854/commentary-up-market-capture-minus-down-market-capture/) - the capture spread as a single ranking number; penalizes a smooth-but-dead sleeve
- [LongTailAlpha - Tail Risk Hedging Performance: Measuring What Counts (2021)](https://www.longtailalpha.com/wp-content/uploads/2021/11/Tail-Risk-Hedging-Performance-Measurement.pdf) - practitioner case for crisis-gain / drawdown-reduction metrics over Sharpe; tail-fund COI

## Communities

-
