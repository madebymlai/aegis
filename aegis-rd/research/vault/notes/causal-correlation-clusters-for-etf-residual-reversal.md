---
title: Causal Correlation Clusters for ETF Residual Reversal
date: 2026-07-20
topic: convergent-strategy-design
status: falsified-current-rule
aliases:
  - ETF correlation-bucket reversal
  - ETF cluster residual reversal
related:
  - "[[stock-specific-short-term-reversal-as-liquidity-provision]]"
  - "[[etf-flow-discount-liquidity-composition-hypothesis]]"
  - "[[what-is-a-strategy]]"
  - "[[allocating-and-rebalancing-a-multi-strategy-book]]"
tags:
  - note
  - etf
  - reversal
  - clustering
  - statistical-arbitrage
  - negative-result
---

# Causal Correlation Clusters for ETF Residual Reversal

> [!abstract] Research verdict
> **The exact UCITS ETF OHLCV rule failed its five-year implementation test.** It earned only +1.02% gross and became negative above roughly 1.2 basis points of one-way execution cost. Published work still supports the broader research architecture—correlation-based economic groupings, residual mean reversion, ETF price deviations, and non-fundamental demand—but this particular composition is not buildable alpha and should not receive live capital.

## The proposed behaviour

An ETF sometimes moves differently from statistically close peers because a temporary order, inventory or liquidity imbalance hits that wrapper more strongly than the common exposure. The proposed trade removes the peer move, buys a sufficiently negative ETF-specific residual, shorts a sufficiently positive one, and closes when the residual normalizes or its short horizon expires.

This is narrower than generic mean reversion:

$$
r_{i,t}
= \underbrace{\beta_i r_{\text{peer},t}}_{\text{shared exposure}}
+ \underbrace{\epsilon_{i,t}}_{\text{wrapper-specific move}}.
$$

Only reversal of $\epsilon_{i,t}$ is the proposed return fact. Correlation identifies candidate peers; **correlation does not itself imply that their spread is stationary or will converge**.

## What the evidence establishes

### 1. Residual clustering is a defensible way to discover peers

Mantegna showed that correlation-derived distances and hierarchical trees can recover a meaningful economic taxonomy from returns.[^mantegna] This supports using prices to discover peer structure instead of requiring hand-maintained industry labels. It does not establish a trading premium.

The correlation matrix must be treated as an estimate, not truth. Laloux and co-authors found that much of the eigenvalue spectrum of empirical financial correlation matrices was consistent with noise and warned against blind use of sample correlations.[^laloux] Raw ETF correlations also contain broad risk-on/risk-off and asset-class moves. Clustering those raw returns can group securities because they share market beta, then mistake a beta difference for a temporary dislocation.

Direct statistical-arbitrage evidence therefore uses **residual**, not raw, returns. Avellaneda and Lee removed common components using PCA or sector ETFs and modeled the remaining returns as mean reverting. Their reported after-cost performance was positive in 1997–2007 but degraded after 2002, while volume-aware signals improved their ETF-factor implementation.[^avellaneda] Jin, Cucuringu and Cartea likewise cluster correlations of market-residual stock returns, then buy within-cluster losers and short winners. Their 2000–2022 study reports roughly 10–12% annualized returns and Sharpe ratios around one, with low market correlation.[^jin]

Those results support the **architecture**, not the proposed ETF strategy. Jin et al. study stocks, trade a broad book every three days, use several clustering choices, and do not establish executable ETF results after spreads and shorting costs. Their Fama–French industry benchmark performs similarly on headline Sharpe, so the incremental benefit of elaborate clustering is not overwhelming.[^jin]

### 2. Similar ETFs can exhibit short-lived relative-price deviations

Petäjistö documents ETF prices deviating from NAV and uses the cross-section of similar ETFs to reduce stale-NAV contamination. He reports economically meaningful pricing bands and substantial abnormal returns before transaction costs from short-term mean reversion.[^petajisto] This is unusually close to the proposed peer-relative object, but it depends on fund similarity and NAV analysis that OHLCV alone cannot reproduce.

The ETF pairs-trading literature is supportive but not decisive. Recent work finds that apparent profitability depends on the stability of cointegration and on short trading windows.[^chen] The result is a warning against equating high rolling correlation with a durable convergence anchor.

### 3. There are plausible payers, but OHLCV cannot identify them

ETF shares trade in a secondary market while authorized participants create or redeem large blocks against baskets in the primary market.[^sec] Brown, Davies and Ringgenberg show that primary-market creations and redemptions reveal non-fundamental demand: high-flow ETFs subsequently underperform low-flow ETFs, consistent with temporary price pressure transmitted through arbitrage.[^brown] Ben-David, Franzoni and Moussawi independently find that ETF arbitrage propagates liquidity shocks and increases the mean-reverting component of underlying-stock prices.[^bendavid]

This supports a plausible payer story: impatient ETF investors, market makers managing inventory, or arbitrageurs transmitting a wrapper-level shock. But **daily OHLCV volume is not primary-market flow**. It measures secondary-market trading and does not reveal creations, redemptions, shares outstanding, authorized-participant inventory, NAV or the initiating trader. An OHLCV prototype can establish a return pattern; it cannot establish which payer generated it.

### 4. Duplicate wrappers are a separate mechanism and a serious confounder

ETFs tracking the same or very similar indices can have sharply different secondary-market liquidity. Khomyn, Putniņš and Zoican find that more liquid same-index ETFs attract short-horizon traders, trade far more, and can charge higher fees; competition also fragments liquidity.[^khomyn] Consequently, a nearly identical pair is not operationally symmetric even when its economic exposure is close.

Duplicate wrappers may offer the cleanest law-of-one-price anchor, but they can also create false backtest profits through stale closes, unequal spreads or trading the illiquid wrapper at an unavailable mark. They should be reported as a separate stratum, not allowed to validate the broader claim that correlation-learned clusters generate alpha. OHLCV correlation alone cannot prove that two funds track the same index; benchmark, leverage, currency hedge, distribution and derivative-overlay metadata are required.

## Evidence versus design inference

| Claim | Status |
| --- | --- |
| Return correlations can recover economically meaningful groups | **Established** as a descriptive result[^mantegna] |
| Sample correlation matrices are noisy | **Established**[^laloux] |
| Residual mean-reversion portfolios have produced historical returns | **Established in stock portfolios; decayed and implementation-sensitive**[^avellaneda][^jin] |
| Similar ETFs and ETF-versus-NAV prices can temporarily diverge | **Established**[^petajisto] |
| ETF primary-market flow reveals non-fundamental demand | **Established, but requires shares/flow data absent from OHLCV**[^brown] |
| A rolling ETF correlation cluster supplies a valid convergence anchor | **Design inference** |
| A five-day ETF residual reverses after next-session execution and costs | **New hypothesis** |
| The return is paid by ETF-specific liquidity demand | **Plausible mechanism, not identifiable from OHLCV** |
| Cluster discovery improves on simple hand-built peers or nearest pairs | **New hypothesis** |

## What an OHLCV prototype can honestly test

OHLCV can support adjusted daily returns, dollar-volume screens, rolling volatility, causal correlation estimates, residual deviations and next-session simulated returns. It is sufficient to ask:

> Do large, causally measured deviations from a frozen ETF peer basket reverse over the next few sessions strongly enough to survive conservative price-only cost assumptions?

OHLCV cannot independently support:

- point-in-time fund category, benchmark or leverage status;
- creations, redemptions or historical shares outstanding;
- NAV or intraday indicative value;
- bid–ask spread, depth, locate availability or borrow fee;
- delisted ETFs unless the vendor supplies them;
- a causal distinction between wrapper pressure and a genuine exposure change;
- exact treatment of distributions unless prices are fully adjusted.

The prototype must therefore call itself a **price-only residual-reversal test**, not an ETF-flow strategy or proof of executable alpha.

## Minimal causal prototype implied by the research

> [!note] Design inference
> The choices below are a deliberately simple falsification design derived from the evidence. They are not published optimal parameters.

### Universe

Use a small curated set of liquid, unlevered, non-inverse ETFs with adjusted OHLCV and enough history. Keep international funds, option overlays, currency-hedged products, commodity pools and duplicate same-index wrappers either excluded or separately labeled. A fixed present-day universe creates survivorship bias, so the result remains exploratory unless historical listings and delistings are supplied.

### Peer formation

At each month-end:

1. Use only returns available through that close.
2. Estimate broad common components from the preceding year; retain a naive raw-correlation version only as a mandatory baseline.
3. Cluster the **residual returns** with one simple deterministic method such as average-linkage hierarchical clustering.
4. Require at least three usable members per cluster.
5. Freeze cluster membership and residualization coefficients for the next month.

Freezing is essential. Rebuilding today's peers with tomorrow's returns causes look-ahead; rebuilding daily also turns cluster instability into hidden turnover and lets the convergence anchor move while the trade is open.

### Signal

For ETF $i$, form a leave-one-out peer return from the other frozen cluster members and estimate its peer beta using formation data only. The short-horizon displacement is:

$$
D_{i,t}^{(h)}
= \sum_{s=t-h+1}^{t}
\left(r_{i,s}-\widehat\beta_{i}r_{-i,\operatorname{cluster},s}\right),
$$

standardized by prior residual volatility. Leave-one-out construction prevents the traded ETF from mechanically pulling its own benchmark toward itself.

### Position output

At the next executable session, long sufficiently negative residuals and short sufficiently positive residuals. Neutralize dollars within each cluster before the surrounding allocator applies sleeve risk scaling and its existing drift bands. Do not use volume as directional proof; at most use lagged dollar volume as a tradability gate or report whether larger residuals coincide with abnormal activity.

### Exit

End the trade when the residual substantially normalizes, when the frozen cluster expires, or after a short fixed maximum horizon. The hard horizon prevents a failed convergence claim from silently becoming a long-term contrarian bet. A cluster re-estimation must not retroactively change the entry anchor.

### Mandatory comparisons

The prototype is informative only if it reports:

- raw-correlation clusters versus common-factor-residual clusters;
- data-driven clusters versus simple manually declared asset groups;
- leave-one-out cluster baskets versus the nearest single peer;
- duplicate wrappers separately from non-duplicate clusters;
- signal-close marks versus next-open or next-session execution;
- zero costs and conservative spread/borrow haircuts;
- one-, three-, five- and ten-session forward residual returns without selecting the best horizon as the answer;
- cluster membership stability and turnover.

## UCITS-only IB Gateway audit

On 2026-07-20 the prototype qualified exact London USD listings through the paper
IB Gateway and loaded daily history through 2026-07-17. The candidate set contains
only UCITS ETFs. CSPX is the non-traded broad-market input; the surviving peer set is
IUIT, SXLK and XUTC for U.S. technology, and IUHC, SXLV and XUHC for U.S. health care.
The issuer documents identify the corresponding products as UCITS ETFs and list their
London exchange lines.[^ishares-tech][^ishares-health][^spdr-tech][^spdr-health][^xtrackers-tech][^xtrackers-health]

The audit loaded 362–382 daily observations per surviving peer. All six passed IB
qualification for the connected account and a $250,000 trailing median daily
dollar-volume screen. The financial candidates IUFS, SXLF and XUFN were excluded as a
family: XUFN failed the liquidity floor, leaving fewer than the required three
independent liquid funds. This is a prototype eligibility result, not a claim about
future liquidity or executable spread.

The frozen residual-correlation state recovered the two manually understood families
with 100% membership overlap against the prior monthly snapshot. No member crossed the
predeclared $|z| \ge 3$ entry boundary on 2026-07-17, so the correct prototype output was
no entry. This is evidence that the state model behaves coherently on one live snapshot;
it is not evidence of after-cost alpha.

## Five-year causal backtest

> [!failure] The exact rule does not survive plausible execution costs
> The current UCITS implementation produced a small gross return but required too much
> turnover. It should not be promoted as a standalone alpha.

The walk-forward run requested IB daily history from 2020-12-07 through 2026-07-17 so the
146-session formation and snapshot warm-up did not consume the requested evaluation
horizon. The five-year signal window contains 1,236 sessions from 2021-07-08 through
2026-07-14. Every 21 sessions, the rule selects complete peer families using trailing
60-session dollar volume known at the formation date and freezes their peer map. Each
target is formed at a close, executed at the next session's open, and earns the following
open-to-open total return. The accounting charges all target changes, a fixed short-borrow
haircut and terminal liquidation.

| Result | Value |
| --- | ---: |
| Gross total return | +1.02% |
| Net total return at 10 bps one-way cost and 100 bps annual borrow | -5.87% |
| Annualized net return | -1.22% |
| Annualized volatility | 0.79% |
| Net Sharpe, zero cash rate | -1.56 |
| Maximum drawdown | -6.08% |
| Entries / exits | 52 / 52 |
| Exposed sessions | 104 |
| Total one-way turnover | 68.50× |

The failure is not confined to an unusually harsh 10-basis-point assumption. Holding the
borrow haircut at 100 basis points annually, net total return was only +0.12% at one basis
point and -0.56% at two basis points. The implied break-even is about 1.2 basis points per
one-way turnover. That is below a defensible all-in spread, slippage and commission
allowance for the less-liquid London lines in this universe.

This remains an optimistic research result. The candidate list is today's curated survivor
set rather than a point-in-time historical UCITS master, although liquidity and complete
family membership are now evaluated point-in-time inside that set. OHLCV also does not
reveal historical spreads, depth, locates or borrow fees. Those limitations cannot rescue
a rule whose measured break-even cost is already close to one basis point; they make the
negative deployment conclusion stronger.

## Failure conditions

Reject the hypothesis if residual losers do not outperform residual winners after next-session entry; the sign vanishes under a modest cost haircut; results come primarily from illiquid or duplicate wrappers; raw clusters perform only because they load on common market moves; clusters change too quickly to provide a stable anchor; the effect is concentrated in international stale-close mismatches; or an equal-weight/manual peer baseline matches the complicated learner.

Also reject the payer claim—even if a price pattern remains—unless later shares-outstanding, NAV or flow data links the residual to non-fundamental ETF demand. A useful OHLCV alpha and a verified behavioural explanation are two separate conclusions.

## Bottom line

Correlation buckets are a credible way to replace complicated industry/news cleaning **for ETFs**, where each instrument already represents a diversified exposure. They do not clean the signal automatically. The defensible sequence is:

$$
\text{common-factor removal}
\rightarrow \text{causal frozen peer discovery}
\rightarrow \text{leave-one-out displacement}
\rightarrow \text{test for reversal}.
$$

This was a better falsification target than generic ETF dip-buying because the peer map and residual construction were causal and explicit. The test nevertheless rejects the exact fixed rule: its gross return is too small relative to turnover. Further parameter search on the same sample would be data mining, not evidence. Any future reversal candidate should introduce a materially different information source or lower-turnover mechanism and receive a new untouched evaluation.

## Sources

[^mantegna]: Rosario N. Mantegna, [“Hierarchical Structure in Financial Markets,”](https://doi.org/10.1007/s100510050929) *European Physical Journal B* 11 (1999), 193–197. The primary descriptive source for correlation-derived financial taxonomies.

[^laloux]: Laurent Laloux, Pierre Cizeau, Jean-Philippe Bouchaud and Marc Potters, [“Noise Dressing of Financial Correlation Matrices,”](https://doi.org/10.1103/PhysRevLett.83.1467) *Physical Review Letters* 83 (1999), 1467–1470. Primary evidence that much empirical correlation structure can be sampling noise.

[^avellaneda]: Marco Avellaneda and Jeong-Hyun Lee, [“Statistical Arbitrage in the US Equities Market,”](https://doi.org/10.1080/14697680903124632) *Quantitative Finance* 10 (2010), 761–782. Primary residual mean-reversion evidence using PCA and ETF factors, including performance decay and volume-aware signals.

[^jin]: Qi Jin, Mihai Cucuringu and Álvaro Cartea, [“Correlation Matrix Clustering for Statistical Arbitrage Portfolios,”](https://doi.org/10.1145/3604237.3626894) ICAIF 2023. The closest direct evidence for residual-correlation clustering followed by within-cluster contrarian portfolios, but on stocks rather than ETFs.

[^petajisto]: Antti Petäjistö, [“Inefficiencies in the Pricing of Exchange-Traded Funds,”](https://doi.org/10.2469/faj.v73.n1.7) *Financial Analysts Journal* 73 (2017), 24–54. Primary evidence for short-term ETF price deviations and cross-sectional peer pricing; reported strategy returns are before transaction costs.

[^chen]: Kezhong Chen and Constantinos Alexiou, [“Cointegration-Based Pairs Trading: Identifying and Exploiting Similar Exchange-Traded Funds,”](https://doi.org/10.1057/s41260-025-00416-0) *Journal of Asset Management* (2025). Recent ETF-specific evidence that pair profitability is conditional on unstable cointegration relationships.

[^sec]: SEC Office of Investor Education and Advocacy, [“Updated Investor Bulletin: Exchange-Traded Funds,”](https://www.investor.gov/introduction-investing/general-resources/news-alerts/alerts-bulletins/investor-bulletins-24) 23 February 2023. Official source for secondary-market trading and authorized-participant creation/redemption mechanics.

[^brown]: David C. Brown, Shaun W. Davies and Matthew C. Ringgenberg, [“ETF Arbitrage, Non-Fundamental Demand, and Return Predictability,”](https://doi.org/10.1093/rof/rfaa027) *Review of Finance* 25 (2021), 937–972. Primary evidence that creations/redemptions reveal non-fundamental demand and predict reversal.

[^bendavid]: Itzhak Ben-David, Francesco Franzoni and Rabih Moussawi, [“Do ETFs Increase Volatility?”](https://doi.org/10.1111/jofi.12727) *Journal of Finance* 73 (2018), 2471–2535. Primary evidence that ETF arbitrage can transmit liquidity shocks and increase mean-reverting price noise.

[^khomyn]: Marta Khomyn, Tālis J. Putniņš and Marius Zoican, [“The Value of ETF Liquidity,”](https://doi.org/10.1093/rfs/hhae041) *Review of Financial Studies* (2024). Primary evidence on liquidity clienteles and fragmentation among competing same-index ETFs.

[^ishares-tech]: BlackRock, [iShares S&P 500 Information Technology Sector UCITS ETF](https://www.ishares.com/uk/individual/en/products/280510/ishares-sp-500-information-technology-sector-ucits-etf?siteEntryPassthrough=true). Official product and listing information for IUIT.

[^ishares-health]: BlackRock, [iShares S&P 500 Health Care Sector UCITS ETF](https://www.ishares.com/uk/individual/en/products/280507/ishares-sp-500-health-care-sector-ucits-etf?siteEntryPassthrough=true&switchLocale=y). Official product and listing information for IUHC.

[^spdr-tech]: State Street, [State Street SPDR S&P U.S. Technology Select Sector UCITS ETF](https://www.ssga.com/uk/en_gb/intermediary/etfs/state-street-spdr-sp-us-technology-select-sector-ucits-etf-acc-zpdt-gy). Official product information for the SXLK London line.

[^spdr-health]: State Street, [State Street SPDR S&P U.S. Health Care Select Sector UCITS ETF](https://www.ssga.com/uk/en_gb/intermediary/etfs/state-street-spdr-sp-us-health-care-select-sector-ucits-etf-acc-zpdh-gy). Official product information for the SXLV London line.

[^xtrackers-tech]: DWS, [Xtrackers MSCI USA Information Technology UCITS ETF factsheet](https://etf.dws.com/download/asset/b3cc4fb7-fcdb-4adc-87cf-f945a5f190aa). Official fund and listing information for XUTC.

[^xtrackers-health]: DWS, [Xtrackers MSCI USA Health Care UCITS ETF factsheet](https://etf.dws.com/en-gb/AssetDownload/Index/6ddcc07e-5af6-4d6e-85bd-186c53ecc5e2/Factsheet.pdf). Official fund and listing information for XUHC.
