---
title: Mean Reversion Unbiased Survey - Ranked Candidates
date: 2026-07-20
topic: mean-reversion
tags:
  - note
  - external-research
---

# Mean-Reversion Trading: An Unbiased Survey of the Evidence (2026)

**Method note.** This survey used open web/academic search (Exa) only — no priors imposed on asset class or construction. Sources span SSRN/arXiv/peer-reviewed journals, practitioner research (Quantpedia, CXO Advisory, Concretum, CAIA), industry post-mortems (MSCI, Resonanz Capital, FT), and forum/GitHub material (flagged and mostly discounted — see "Noise" note at the end). For every candidate, "works" is qualified by universe, sample period, gross/net-of-cost status, and recency. Counter-evidence was actively sought for every entry, including for the strongest candidates.

---

## Ranked Candidates — Real Strategies (all five questions answered)

### 1. Index reconstitution arbitrage/reversal (S&P 500, Russell, Nikkei 225, MSCI)

**Evidence strength: Strongest.** This is the closest thing in the survey to a mechanically-guaranteed edge, replicated across four decades and multiple countries, with the counterparty identified by name.

- **State.** A stock is formulaically scheduled for addition to or deletion from a widely-tracked index (Russell's rule-based May ranking / late-June effective date; S&P committee announcement with a fixed effective date; MSCI's semi-annual reconstitution calendar; Nikkei 225 committee changes).
- **Action.** Between announcement and the effective date, go long anticipated additions / short anticipated deletions ("trading ahead of index funds"); on or just after the effective date, take the opposite side — short newly added names / long newly deleted ones — to harvest the documented post-event reversal, or simply supply liquidity into the reconstitution-day imbalance.
- **Exit.** Close the anticipation leg the day before the effective date, before forced index-fund flow arrives; close the reversal leg over the following days to months as the price partially mean-reverts.
- **Payer.** Passive/index-tracking funds, which are contractually and career-risk-bound to minimize tracking error and therefore must trade at the reconstitution date regardless of price — a textbook "mandated, price-insensitive counterparty." Madhavan (2003, *FAJ*) called this "the Russell reconstitution effect"; a long-short additions-minus-deletions portfolio returned a mean 14.9% in June 1996–2002.
- **Failure condition, stated ex ante.** The edge should shrink toward zero as speculator competition rises (a Harvard Business School model of this trade explicitly derives that "trading costs decline as speculator competition increases," and one paper argues observed reconstitution-day price impact is now small precisely because pre-positioning has already absorbed it) or if indices move to phased/gradual reconstitution instead of single-day resets.

**Key figures.** Madhavan (*FAJ* 2003): Russell 3000 additions-minus-deletions mean 14.9% in June, 1996–2002. Ontario Securities Commission (2025) and MSCI reconstitution-rigidity paper (SSRN 4476422, 2006–2023, 56 markets) confirm the pattern persists into the current decade. Discretionary S&P 500 deletions have beaten additions by 22% in the following year (SSRN 4099610).

**Best counter-evidence.** Russell 2000 short-interest study (2022) finds *persistent*, not purely temporary, price effects for deletions, and argues the "arbitrage game" evidence is more mixed than the classic price-pressure story implies. Nikkei 225 evidence (Japan) shows *permanent* price effects for both additions and deletions despite temporary reversals — i.e., in some markets a chunk of the "mispricing" is real information, not pure liquidity noise, so a reversal trader is also fighting a genuine repricing. Capacity is real-world limited: index funds hold ~$16T benchmarked to Russell alone, but the arbitrage side is "typically undiversified... involves high trading costs and price risk," per Madhavan himself.

---

### 2. Overnight-to-intraday reversal (CO−OC) across multi-asset futures

**Evidence strength: Strong, recent, multi-asset.**

- **State.** At the market open, cross-sectional dispersion of overnight (close-to-open) returns is elevated — the paper's own predictor variable for the strategy's forward profitability.
- **Action.** Long the assets with the lowest overnight returns, short those with the highest, executed at the open, across equity-index, interest-rate, commodity, and currency futures simultaneously.
- **Exit.** Close at the same day's close (the position is purely intraday) or, in the weekly variant, over the week.
- **Payer.** The paper attributes returns to an "asset-specific market maker liquidity provision mechanism" — i.e., dealers/market-makers earn compensation from whoever is creating overnight order imbalance (retail overnight sentiment flow, forced overnight rebalancing), and the effect is *not* explained by investor sentiment indices, macro news, or VIX, but specifically by realized overnight return dispersion, which is the liquidity-provider's risk gauge.
- **Failure condition.** If cross-sectional overnight-return dispersion is compressed by more electronic liquidity provision at the open (which is exactly the mechanism the paper says drives the return), the strategy should decay; it is also a high-turnover, daily-rebalanced strategy, so a widening of realistic trading costs is a second explicit kill condition.

**Key figures.** The CO-OC strategy's Sharpe is reported as roughly 2–5× larger than the conventional close-to-close reversal strategy across four asset classes (interest rates: Sharpe 2.18; commodities: 3.54; currencies: 1.53; and implausibly large equity-index figures up to Sharpe ~27, which the paper does not fully cost-adjust). A separate sector-ETF study (1999–2025, 27 years) confirms overnight/daytime reversal strategies "consistently outperform" buy-and-hold before costs, but that "outperformance decreases significantly when transaction costs are taken into account," even at institutional 1bp cost assumptions.

**Best counter-evidence.** The headline Sharpe ratios (some >10) are a red flag for unrealistic cost assumptions on a daily-turnover strategy; the sector-ETF paper's own honest finding is that after-cost outperformance survives but is materially smaller than the gross number suggests. Separately, Lou-Polk-Skouras (2019, *JFE*) show that for many well-known factor premia (value, profitability, investment), returns actually accrue *intraday*, not overnight — reversal-related premia are the exception, not the rule, so this is a narrow, mechanism-specific effect rather than a general "overnight is where the edge is" claim.

---

### 3. Commodity futures term-structure (backwardation/contango) mean reversion

**Evidence strength: Strong, decades of theory + evidence, though newer independent verification is thin.**

- **State.** The futures curve is backwardated (near-month price > deferred) beyond a statistical threshold, or a calendar spread's price has moved a defined number of standard deviations (Bollinger-band entry) from its own historical mean.
- **Action.** Go long the calendar spread (long near-month/short deferred) when backwardated and stretched below the band, or short it when in contango and stretched above; positions sized with a dynamically estimated (Kalman-filter) hedge ratio between the two legs.
- **Exit.** Close when the spread reverts to the Bollinger-band mean, or at a fixed holding-period stop.
- **Payer.** Commercial hedgers (producers who sell forward, consumers who buy forward) who, per the Keynesian "normal backwardation" and inventory/storage theory (Gorton-Hayashi-Rouwenhorst, *Review of Finance*), pay a risk premium to speculators for warehousing price risk when inventories are scarce — a textbook insurance-buyer/insurance-seller counterparty relationship tied to observable inventory levels.
- **Failure condition.** A structural, sustained shift to persistent contango (glut-driven, low convenience yield) across the tested commodities, or the risk-adjusted return of the calendar-spread strategy falling to zero across rolling 5-year out-of-sample windows.

**Key figures.** Energy-futures calendar-spread study (1992–2013, 22 years, bootstrap-tested, realistic transaction costs): Sharpe ratios "in excess of 2" for WTI crude and natural gas front-month/second-month spreads. Gorton-Hayashi-Rouwenhorst (31 commodities, 1969–2010/1971–2010): high-basis (backwardated) commodity portfolios "significantly outperform" low-basis portfolios, tied directly to independently measured inventory data — a genuine fundamentals-linked story, not a pure price pattern.

**Best counter-evidence.** A separate agricultural-futures paper (corn, wheat, soybean, soybean oil, soybean meal) using long-horizon regression and variance-ratio tests finds "mean reversion does *not* exist" in those futures prices, and multi-year rollover hedging does not improve producer returns relative to routine annual hedging — directly contradicting the "commodities always mean-revert" framing for that commodity subset. Most of the strongest, most recent (post-2015) verification is in energy; the agricultural and metals literature is more mixed, and no source found extends the calendar-spread backtest past 2013–2014 with current data, which is a real recency gap.

---

### 4. FX carry with long-run/PPP mean-reversion and crash-risk conditioning

**Evidence strength: Strong and current (2024–2025 papers), but paired with the best-documented crash risk in this survey.**

- **State.** A currency's interest-rate differential sits above/below the cross-sectional median, and/or its exchange rate is estimated (via PPP or BEER models) to be significantly misaligned from a slow-moving (3–12-year half-life) equilibrium; optionally, an FX-option risk-reversal signal is monitored for elevated predicted crash probability.
- **Action.** Long high-yield/undervalued currencies, short low-yield/overvalued currencies in a G10 basket, weighted by interest differential and/or misalignment; when the crash-risk signal fires, replace or hedge the position with FX options rather than holding unhedged.
- **Exit.** Monthly/quarterly rebalance to updated differentials and equilibrium estimates; conditional hedge triggered by rising VIX, widening TED spread, or a repriced risk-reversal.
- **Payer.** A composite of (a) a genuine risk premium — carry-trade losses cluster exactly in high-VIX, funding-liquidity-stress states (Brunnermeier-Nagel-Pedersen, *JF* 2008/NBER), consistent with compensation for crash risk, and (b) underreaction — target-country central banks/governments and low-yield-country savers who systematically forgo yield for safety, sustaining the UIP violation that carry harvests.
- **Failure condition, stated ex ante.** If carry-trade losses stopped clustering specifically in high-VIX/high-TED-spread states (the model's own falsifiable prediction), the crash-risk-compensation story would be wrong and the excess return would look more like pure inefficiency due to self-correct. A second explicit failure: if a "hedged" (crash-protected) version of carry earned *the same* average payoff as the unhedged version — evidence against a risk-premium interpretation — which is in fact what several papers below report.

**Key figures.** "Boosting Carry with Equilibrium Exchange Rate Estimates" (2024, *Open Economies Review*; ECB working paper): a half-life PPP-based strategy (HL10) achieves annualized mean returns above 4%, beating a naive carry benchmark's 3.38%. Long-run interest-rate-differential carry (2025, ideas.repec.org): 2.48% annualized excess return with higher Sharpe, lower turnover, and *less* negative skew than classic carry. A conditionally-hedged carry strategy (2022, *Journal of International Financial Markets*) reports the hedged version outperforms the unhedged one on a Sharpe basis, undercutting the pure peso-problem explanation.

**Best counter-evidence — genuinely contested, not settled.** Two camps of NBER-tier papers disagree on the *mechanism*, which matters for durability. Burnside-Eichenbaum-Kleshchelski-Rebelo argue carry returns are almost entirely a peso problem (rare, un-sampled catastrophic loss), meaning the in-sample Sharpe ratio is an *illusion* that will eventually be corrected by an out-of-sample crash big enough to erase the cumulative gain — precisely what happened to yen carry traders in 1998, 2007–08. Brunnermeier-Nagel-Pedersen counter that losses are *not* rare-tail-only but recur regularly around VIX spikes, making it a genuine (if intermittent) risk premium rather than a pure illusion — but this is an active academic disagreement, not resolved consensus. Either way, the strategy carries **documented, real, repeated crash episodes** (1998, 2008, 2015 CHF, 2024 August yen unwind), so "works" here means "works with fat left-tail risk baked in by design," not "works smoothly."

---

### 5. Closed-end fund (CEF) discount mean reversion

**Evidence strength: Strong and old (40+ years of replication), but small/capacity-constrained.**

- **State.** A CEF's price-to-NAV discount, modeled parametrically as a function of its current level *and* its own recent history (not just current level), places it in the highest-expected-return quintile relative to peers.
- **Action.** Go long the highest-expected-return quintile of CEFs, short (or underweight) the lowest, rebalanced monthly.
- **Exit.** Standard periodic rebalance (monthly), or exit early if a fund converges to NAV via open-ending/liquidation/tender.
- **Payer.** Retail-dominated, sentiment-driven noise traders who set CEF prices away from NAV (the classic Lee-Shleifer-Thaler "investor sentiment index" story), a mispricing that professional capital cannot fully close because arbitraging a CEF discount to zero requires forcing conversion or liquidation of the trust — a genuine, named limits-to-arbitrage friction, not just "the market hasn't noticed yet."
- **Failure condition.** Patro-Piccotti-Wu (2016) explicitly test and report *no* decline in strategy returns between the first and second half of their sample — they treat "no decay across sub-periods" as the diagnostic that would need to reverse for the anomaly to be considered arbitraged away; a finding of significant sub-period decay would falsify durability.

**Key figures.** Patro, Piccotti & Wu (2016, *Journal of Financial Research*, 377 US CEFs, 1984–2011): five-factor-risk-adjusted annualized alpha of 17.4%, information-value estimate up to 18.2%/year. Kohl (2013)/Aggeborn-Leander (2021), Swedish CEFs, net of transaction costs and modeled trading capacity: 7.4%–14.6% annualized abnormal return.

**Best counter-evidence.** This is a genuinely small, low-capacity opportunity — the Swedish study explicitly builds a "trading capacity" model because the naive strategy cannot scale; the US study's own long/short quintile portfolio is drawn from a shrinking universe (fewer CEFs exist today than in the 1990s, and much of the space is now dominated by activist arbitrageurs who compress the widest discounts directly). No 2020s-vintage US study was found updating the Patro et al. figures, which is a real recency gap for this candidate specifically.

---

### 6. Volatility risk premium harvesting via VIX-linked ETNs (eVRP + term-structure signal)

**Evidence strength: Credible, current, professionally reproduced backtest — but flagged by an independent industry source as structurally compressing, and with the worst tail-risk precedent in this survey.**

- **State.** Expected volatility risk premium is positive (VIX minus realized 10-day SPY volatility > 0) **and** the VIX term structure is in contango (VIX < VIX3M).
- **Action.** Allocate to a short-vol ETN (e.g., SVXY) sized dynamically at roughly VIX/100 of the portfolio (more exposure exactly when VIX — and the premium — is higher); flip to long-vol (VXX) when both signals turn negative; hold cash in the mixed-signal case.
- **Exit.** Rebalance whenever the position drifts >2% from target, executed via market-on-close order.
- **Payer.** Institutional/retail hedgers and portfolio insurers who systematically buy downside protection (options, variance swaps) because the pool of risk-averse buyers structurally exceeds the pool of willing risk-warehousers — a genuine insurance-premium relationship, explicitly documented: the VIX has overestimated realized volatility roughly 80% of the time over two decades.
- **Failure condition, stated by the paper's own logic and independently confirmed.** A sustained volatility regime that keeps eVRP negative or the curve backwardated for an extended period would starve the strategy of trades; a single violent vol spike large enough to overwhelm the dynamic-sizing rule's buffer (precedent: XIV, -96% in one day, February 2018) would be a genuine, not hypothetical, failure.

**Key figures.** Zarattini, Mele & Aziz ("The Volatility Edge," Concretum Research/Quantpedia Award 2026 finalist), Jan 2008–May 2025, realistic transaction costs (5bps): CAGR 16.3%, Sharpe 1.00, max drawdown -12% (adjusted), correlation to S&P 500 ~0.12–0.15. A related beta-neutral term-structure-spread variant (short front-month VIXY / long mid-term VIXM) reports Sharpe approaching ~2.0 at higher allocation, 2019–2025.

**Best counter-evidence — from an independent, non-marketing source.** CAIA's "Option Selling Has Become Consensus" (2024) directly measures the trailing 3-year volatility risk premium and finds it "was 2.5 points on average before 2006" and has been compressing — "almost no risk premium at all on a trailing 3-year basis even before [the] GFC and the March 2020 crash," implying forward-looking expected returns to option-selling were arguably negative by mid-2008 and early 2020 on a probability-weighted basis, precisely because the strategy has become crowded ("evergreen asset class for income generation" marketing narrative vs. the actual, deteriorating up/down capture data the article documents for CBOE benchmark indices). Bhansali & Harris (2018, *FAJ*) and the peer-reviewed Volmageddon post-mortem (Augustin, Cheng & Van den Bergen, 2021, *FAJ*) independently document that short-vol strategies are mechanically self-destabilizing in a crowded trade — hedge/leverage rebalancing amplifies the very spike that kills the position. This is a strategy where the sizing discipline is not optional risk management but the entire difference between "steady premium" and "wipeout," and where a credible, non-promotional industry source argues the raw premium itself is shrinking as more capital chases it.

---

## Marginal / Mixed-Evidence Candidates (weaker ranking, included for completeness)

### 7. Equity dispersion trading (short index variance / long single-stock variance)

Answers all five questions (state = calm/low-correlation VIX regime; action = short index vol, long single-name vol on ~50 names; exit = regime-based de-grossing when realized correlation spikes; payer = systemic-crash-protection buyers who overpay for portfolio-level insurance relative to single-name insurance; failure = a correlation shock, stated ex ante as the trade's structural risk). A rules-based S&P 500 backtest (2006–2025) reports 4.8% annualized, Sharpe 0.62 gross, falling to ~0.38 net of realistic single-stock-options costs, with Sharpe flipping from 1.4 in low-VIX months to **-0.3** in high-VIX months — a textbook peso-problem shape. **Counter-evidence is contemporaneous and severe**: a documented March 2026 event saw a JPMorgan dispersion-tracking index post its worst month since 2011 (-4.9%) as implied correlation surged from ~15 to ~40, and industry commentary (Resonanz Capital) explicitly calls dispersion "one of the most crowded relative-value trades of the past three years," with managers actively redesigning baskets in response. Ranked below the Tier-1 group because the crowding/decay signal is not hypothetical but has already fired recently.

### 8. Crypto funding-rate arbitrage / cash-and-carry basis trade

Fully answerable on all five questions historically (state = funding rate materially above the cost hurdle; action = long spot, short perpetual, delta-neutral; exit = funding compresses below the cost threshold; payer = leveraged directional longs paying funding to shorts; failure = funding flips negative or compresses persistently near zero). This is the single best-documented case of **real-time decay** in the entire survey: annualized yields fell from 15–25% (2021 bull market) to 8–12% (2022–23) to **below 4%** by mid-2024 (BitMEX's own report, KuCoin coverage) — below the US risk-free rate — as automated capital (including protocols like Ethena built explicitly around the trade) saturated the majors. A 2025 peer-reviewed study (funding arbitrage across BTC/ETH/XRP/BNB/SOL, CEX+DEX) still finds positive, low-correlation-to-HODL returns, but industry sources report the edge has now migrated to newer, less mature instruments (e.g., BitMEX "TradFi perps" on gold/oil, reporting triple-digit annualized spreads in 2026) — i.e., the mechanism still works, but only in the newest, least crowded corners, and decays measurably within weeks in any venue once found (documented: a 13.7% APR funding rate compresses to 2.7% APR within ~72 hours of arbitrage capital arriving).

### 9. Pairs trading / statistical arbitrage (distance method, cointegration, PCA/graph-clustering)

Evidence is genuinely mixed rather than clearly positive or negative. A Chinese-equities study (2005–2024) reports the classic distance method still nets 81bps/month after time-varying costs; a Polish-market PCA/ETF/LSTM replication of Avellaneda-Lee found strong 2017–2019 profits (Sharpe up to 2.63) but only the ETF-based variant remained profitable through COVID-19, with PCA and LSTM variants failing outright in that stress period. A 2024 US-equities graph-clustering stat-arb study found the base strategy's own transaction costs were **roughly four times larger than its net profit**, turning a positive gross Sharpe (1.10) into a near-flat net one (0.28) — profitability survived only after adding machine-learning trade filtering on top. **This is the strategy family with the most internally-contradictory evidence in the survey**: it clearly generates a statistically real, mean-reverting residual return pattern, but whether *that specific implementation, after specific costs, in a specific period* nets out positive is highly sensitive to engineering choices that vary study to study — a fair summary is "the underlying effect is real; a specific tradable strategy built on it is not guaranteed to survive costs without considerable added engineering."

---

## Evidence of a Return, Not Yet a Strategy

These candidates have credible, real return/mispricing evidence but cannot honestly be given all five answers — either the "action" is not accessible to anyone but a narrow class of institutional balance sheets, or the "exit"/"failure" conditions are unresolved in the literature itself.

- **Interest-rate swap-spread arbitrage.** Real, historically profitable (mean monthly excess returns 0.31–0.55%, Duarte-Longstaff-Yu), and the underlying mean-reversion (swap spread toward a "fundamental" level) is empirically documented (NY Fed, 2006). But post-2008, swap spreads for long maturities are *structurally negative* — an apparent textbook arbitrage that persists precisely because Basel III leverage-ratio capital charges make it uneconomical for regulated dealers to close (NY Fed 2018: at required 6% leverage ratios, ROE on the trade tops out near 6–7.5%, far below typical hurdle rates). The trade is also famous as LTCM's largest single loss driver. Who this "works" for today, at what size, and under what capital structure is genuinely unresolved in the literature — it reads more as a persistent, capital-constrained *risk premium* for whoever can supply balance sheet than as an actionable retail/fund strategy with a clean entry/exit rule.

- **Cross-sectional short-term (weekly/monthly) equity reversal — the classic Jegadeesh/Lehmann anomaly.** Included here deliberately as the survey's clearest *negative* result, because the mandate calls for hunting counter-evidence as hard as support. A 2023 SSRN paper states plainly that "the classic short-term reversal effect has steadily weakened over time, to the point of now having vanished entirely in most regions." An independent leak-safe CRSP backtest (2000–2024) confirms this quantitatively: in-sample (2000–2018) net Sharpe at realistic 7bps costs was a modest +0.34, but out-of-sample (2019–2024) it falls to **-0.15** — the strategy loses money net of costs in the most recent five years tested, with a deflated Sharpe (accounting for the number of configurations tried) of only 0.20. The mechanism is well understood and itself explains the decay: Cheng, Hameed, Subrahmanyam & Titman (*JFQA* 2017) show the effect is driven by temporary *institutional exits* from loser stocks reducing liquidity provision, and a companion conference paper explicitly finds "the magnitudes of the reversals... are lower in the post-2000 period, which is consistent with active [but] uninformed investors (e.g., high-frequency traders) reacting more quickly" — i.e., the exact liquidity-provision gap the anomaly depended on has been competed away by faster capital. Enhanced variants (industry/sector-residual construction, machine-learning-estimated conditional expected returns, EWMA turnover control) can restore a positive net Sharpe in-sample, but each such enhancement is itself an unvalidated, not-yet-out-of-sample-tested research finding rather than a settled strategy — this belongs here, not in the ranked list above.

- **ETF premium/discount arbitrage.** Real and well-modeled (Ornstein-Uhlenbeck-with-jumps fits), but the literature's own headline finding is that the create/redeem authorized-participant mechanism works so well that "the median long-term mean premium of U.S. equity ETFs is zero" — i.e., this is a case where the textbook arbitrage mechanism has essentially already closed the loop for domestic equity ETFs. Persistent, larger premiums remain for international-equity and taxable-bond ETFs facing higher arbitrage barriers, but exploiting them requires AP-level creation/redemption access, not something available to an ordinary trader — so for the "who can actually do this and how" test, it fails outside a narrow institutional set.

---

## A Note on Search Noise

A meaningful fraction of results returned by open web search for "mean reversion strategy" are low-credibility marketing material: paid product listings claiming implausible track records (one cTrader "Limit-Reversion Scalper" listing claimed a 43%/year CAGR and +71,940% cumulative return over 14 years, sold for €149–€2,497/year), SEO-optimized blog posts citing unverifiable "2025 backtests," and what appear to be AI-generated trading-journal blogs with suspiciously specific daily P&L narration. These were excluded from the ranked evidence above; they are noted here only because their volume is itself informative — mean reversion is one of the most heavily marketed retail-strategy categories, which is a soft signal that genuine, durable edges in this space are scarcer than the content volume suggests, and that skepticism of any claimed strategy with an unrealistically smooth or large track record is warranted by default.

---

## Full Source List

**Index reconstitution / rebalancing**
- Madhavan, A. "The Russell Reconstitution Effect." *Financial Analysts Journal* 59(4), 2003. https://www.tandfonline.com/doi/abs/10.2469/faj.v59.n4.2545
- "Index-Tracking Rigidity and Arbitrage Opportunities in MSCI Index Reconstitutions." SSRN 4476422. https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4476422
- "The Avoidable Costs of Index Rebalancing." SSRN 4099610. https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4099610
- "Russell index reconstitutions and short interest." *ScienceDirect*, 2022. https://www.sciencedirect.com/science/article/abs/pii/S1062976920301265
- "The impacts of index rebalancing and their implications: evidence from Japan." *ScienceDirect*. https://www.sciencedirect.com/science/article/abs/pii/S1042443105000442
- "Optimal Index-Linked Rebalancing with Anticipatory Trading." Harvard Business School working paper. https://www.hbs.edu/faculty/Pages/item.aspx?num=68993

**Overnight/intraday reversal**
- Overnight-intraday reversal in equity index/rate/commodity/currency futures (CO-OC strategy). https://assets.super.so/e46b77e7-ee08-445e-b43f-4ffd88ae0a0e/files/c953a0e6-e93e-4bf7-b839-45a90cedced4.pdf
- Salotra, Katikireddy, Anumolu, Pinsky. "A Comparative Analysis of Overnight vs. Daytime Static and Momentum Strategies Across Sector ETFs." *Risks* 14(4), 2026. https://ideas.repec.org/a/gam/jrisks/v14y2026i4p84-d1916263.html
- Lou, D., Polk, C., Skouras, S. "A tug of war: Overnight versus intraday expected returns." *Journal of Financial Economics*, 2019. https://doi.org/10.1016/j.jfineco.2019.03.011
- Barardehi, Bogousslavsky, Muravyev. "What Drives Momentum and Reversal? Evidence from Day and Night Signals." *Review of Financial Studies*, 2022. https://doi.org/10.1093/rfs/hhag036

**Commodity term structure / mean reversion**
- "Trading on mean-reversion in energy futures markets." *ScienceDirect*. https://www.sciencedirect.com/science/article/abs/pii/S014098831500208X
- Gorton, Hayashi, Rouwenhorst. "The Fundamentals of Commodity Futures Returns." NBER w13249. https://www.nber.org/system/files/working_papers/w13249/w13249.pdf
- "An Update on Empirical Relationships in the Commodity Futures Markets." CME Group, 2014. https://www.cmegroup.com/trading/agricultural/files/an-update-on-empirical-relationships-in-the-commodity-futures-markets.pdf
- Yoon & Brorsen. "Can Multiyear Rollover Hedging Increase Mean Returns?" https://ideas.repec.org/a/ags/joaaec/43713.html (counter-evidence: no mean reversion found in grain futures)
- Leung, Li, Li, Wang. "Speculative Futures Trading Under Mean Reversion." SSRN 2695405.

**FX carry / PPP mean reversion**
- "Boosting Carry with Equilibrium Exchange Rate Estimates." *Open Economies Review*, 2024; ECB WP 2731. https://link.springer.com/article/10.1007/s11079-024-09795-0
- Kaebi & Ferreira Batista Martins. "Long-Run Interest Rate Differentials and the Profitability of Currency Carry." 2025. https://ideas.repec.org/p/hhs/oruesi/2025_010.html
- Brunnermeier, Nagel, Pedersen. "Carry Trades and Currency Crashes." NBER w14473; *J. Political Economy*/Chicago Journals. https://www.nber.org/system/files/working_papers/w14473/w14473.pdf
- Burnside, Eichenbaum, Kleshchelski, Rebelo. "Do Peso Problems Explain the Returns to the Carry Trade?" NBER w14054. https://www.nber.org/system/files/working_papers/w14054/revisions/w14054.rev2.pdf
- "Conditionally-hedged currency carry trades." *ScienceDirect*, 2022. https://www.sciencedirect.com/science/article/abs/pii/S1042443122000737
- Jorda & Taylor. "The Carry Trade and Fundamentals: Nothing to Fear But FEER Itself." NBER w15518.

**Closed-end fund discounts**
- Patro, Piccotti, Wu. "Exploiting Closed-End Fund Discounts: A Systematic Examination of Alphas." *Journal of Financial Research*, 2017. https://doi.org/10.1111/jfir.12122
- Aggeborn Leander, I. "Exploiting Discount Mean Reversion and High Discounts." CBS thesis, 2021. https://research-api.cbs.dk/ws/portalfiles/portal/68332054/1148327_Exploiting_Discount_Mean_Reversion_and_High_Discounts_Isak_Aggeborn_Leander_2021.05.17.pdf
- Kohl, N. "Closed-End Fund Abnormal Returns and Discount Mean-Reversion." SSRN 2294410, 2013.

**Volatility risk premium**
- Zarattini, Mele, Aziz. "The Volatility Edge: A Dual Approach for VIX ETNs Trading." Concretum Research, 2025–2026. https://concretumgroup.com/wp-content/uploads/2026/02/The-Volatility-Edge.pdf ; https://concretumgroup.substack.com/p/the-volatility-edge
- CXO Advisory. "Practical Capture of the Volatility Risk Premium?" 2025. https://www.cxoadvisory.com/volatility-effects/practical-capture-of-the-volatility-risk-premium/
- "Option Selling Has Become Consensus: Its Impacts." CAIA, 2024. https://caia.org/blog/2024/04/28/option-selling-has-become-consensus-its-impacts
- Bhansali, V., Harris, L. "Everybody's Doing It: Short Volatility Strategies and Shadow Financial Insurers." *Financial Analysts Journal*, 2018. https://doi.org/10.2469/faj.v74.n2.6
- Augustin, Cheng, Van den Bergen. "Volmageddon and the Failure of Short Volatility Products." *Financial Analysts Journal*, 2021. https://doi.org/10.1080/0015198x.2021.1913040
- Valuelytica. "Volatility Term Structure Arbitrage." 2026. https://valuelytica.substack.com/p/volatility-term-structure-arbitrage

**Dispersion trading**
- Quant Decoded. "Dispersion Trade Paid 4.8% at Sharpe 0.62 — Until Crises Ate the Alpha." 2026. https://quantdecoded.com/en/dispersion-trade-correlation-risk-premium-backtest
- Resonanz Capital. "After the Correlation Shock: How March 2026 Broke — and Reshaped — a Popular Vol Trade." 2026. https://resonanzcapital.com/insights/after-the-correlation-shock-how-march-2026-broke-and-reshaped-a-popular-vol-trade

**Crypto funding-rate / basis arbitrage**
- Werapun et al. "Exploring Risk and Return Profiles of Funding Rate Arbitrage on CEX and DEX." 2025. https://doi.org/10.1016/j.bcra.2025.100354
- BitMEX. "The Crypto Carry Trade Is Dead: TradFi Perps Yield 361.6% Annualised." 2026. https://www.bitmex.com/blog/crypto-carry-trade-death
- KuCoin. "BitMEX Reports Collapse of Crypto Arbitrage Strategy Amid Market Saturation." https://www.kucoin.com/news/flash/bitmex-reports-collapse-of-crypto-arbitrage-strategy-amid-market-saturation
- AInvest. "Crypto Arbitrage and Funding Rate Evolution in a Saturated Market." 2026. https://www.ainvest.com/news/crypto-arbitrage-funding-rate-evolution-saturated-market-assessing-diminishing-returns-institutionalization-2601/

**Pairs trading / statistical arbitrage**
- Sun, Y. "Performance of Pairs Trading Strategies Based on Various Copula Methods." *JRFM* 18(9), 2025. https://doi.org/10.3390/jrfm18090506
- "Statistical arbitrage in multi-pair trading strategy based on graph clustering algorithms in US equities market." arXiv 2406.10695. https://arxiv.org/html/2406.10695v1
- Polish WIG20/mWIG40 PCA/ETF/LSTM Avellaneda-Lee replication (thesis).

**Swap spread arbitrage**
- Duarte, Longstaff, Yu. "Risk and Return in Fixed-Income Arbitrage: Nickels in Front of a Steamroller?" UCLA Anderson working paper / eScholarship. https://escholarship.org/uc/item/6zx6m7fp
- Hanson, Malkhozov, Venter. "Demand-and-supply imbalance risk and long-term swap spreads." *Journal of Financial Economics*, 2024. https://doi.org/10.1016/j.jfineco.2024.103814
- Jermann, U. "Negative Swap Spreads and Limited Arbitrage." *Review of Financial Studies*, 2019. https://doi.org/10.1093/rfs/hhz030
- NY Fed. "Negative Swap Spreads" (Boyarchenko et al., 2018) and "Trading Risk, Market Liquidity, and Convergence Trading" (2006). https://www.newyorkfed.org/medialibrary/media/research/epr/2018/epr_2018_negative-swap-spreads_boyarchenko.pdf ; https://www.newyorkfed.org/medialibrary/media/research/epr/2006/EPRvol12no1.pdf

**Short-term equity reversal (decay evidence)**
- "Reversing the Trend of Short-Term Reversal." SSRN 4575689, 2023. https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4575689
- andrewzhang615-star/equity-statarb. GitHub — leak-safe CRSP backtest, out-of-sample 2019–2024 decay. https://github.com/andrewzhang615-star/equity-statarb
- Cheng, Hameed, Subrahmanyam, Titman. "Short-Term Reversals: The Effects of Past Returns and Institutional Exits." *JFQA*, 2017. https://doi.org/10.1017/s0022109016000958
- Da, Liu, Schaumburg. "Decomposing Short-Term Return Reversal." SSRN 1551025.
- Han, Kang, Lee. "Mispricing and correction in short-term returns" (ML-based STER). *ScienceDirect*, 2026.
- Falck, Rej, Thesmar. "When Systematic Strategies Decay." SSRN 3845928.
- Quantpedia. "In-Sample vs. Out-Of-Sample Analysis of Trading Strategies" (McLean-Pontiff decay synthesis). https://quantpedia.com/in-sample-vs-out-of-sample-analysis-of-trading-strategies/

**ETF premium/discount arbitrage**
- "Premiums and discounts in ETFs: An analysis of the arbitrage mechanism." *ScienceDirect*. https://www.sciencedirect.com/science/article/abs/pii/S1044028314000167
- FCA. "ETF (Mis)pricing." Occasional Paper 68. https://www.fca.org.uk/publication/occasional-papers/op68-etf-mispricing.pdf
- Ontario Securities Commission. "An Empirical Analysis of Canadian ETF Liquidity and the Effectiveness of the Arbitrage Mechanism." 2025. https://www.osc.ca/sites/default/files/2025-06/pub_20250619_osc-etf-study.pdf

**Crowding / quant-fund stress (systemic counter-evidence)**
- MSCI. "Unraveling Summer 2025's Quant Fund Wobble." 2025. https://www.msci.com/research-and-insights/blog-post/unraveling-summer-2025s-quant-fund-wobble
- Resonanz Capital. "Understanding the 2025 Quant Unwind: A Practical Guide." 2025. https://resonanzcapital.com/insights/crowding-deleveraging-a-manual-for-the-next-quant-unwind
- Financial Times. "Inside the 'rolling thunder' quant crises of 2025." 2025. https://www.ft.com/content/4300b622-42b2-4fbb-bfcf-016e1b112bf9
