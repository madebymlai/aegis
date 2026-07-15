---
title: FX Carry Is Not Yet a Small-Account Demeter Replacement
date: 2026-07-14
topic: fx-carry
status: decision
related:
  - "[[the-tiered-strategy-roster]]"
  - "[[the-skew-is-the-product]]"
  - "[[choosing-the-concave-income-pole]]"
  - "[[demeter-duration-neutral-credit-carry-v2]]"
tags:
  - note
  - carry
  - fx
  - demeter
  - concavity
  - execution
---

# FX Carry Is Not Yet a Small-Account Demeter Replacement

> [!note] Status
> Primary-source research decision, not a promotion test. The economic case is strong enough to seed a shadow experiment, but the current EUR 5,000 IBKR spot route fails the financing and execution screen before a backtest.

> [!abstract] Decision
> Cross-sectional G10 FX carry is a cleaner research target than the current short-credit ETF variants: its signal is observable and its dollar-neutral form has the negative skew Demeter is hired to supply. It is **not** a proven stronger contemporary premium or a better deployable sleeve for this small account. Academic implementations use forwards, while IBKR retail offers spot; below IBKR's cash-interest thresholds the long currencies earn no interest, the short currencies pay benchmark plus a spread, and each order pays a USD 2 minimum. Keep static short credit as the provisional deployable control, keep CATB as the preferred orthogonal successor, and admit FX carry only as a shadow challenger after an executable financing test.

## The economic case is better than the vehicle

FX carry is the canonical version of carry. A one-month currency forward has carry equal to the foreign short rate minus the base short rate, up to a scaling factor close to one, and the signal predicts returns both across currencies and through time.[^kmpv] In the standard cross-sectional construction, sort currencies on forward discount, buy the high-rate basket and sell the low-rate basket. The high-minus-low spread earned about `4.8%` per year after transaction costs in the original six-portfolio study, and its common factor explained roughly `70%` of average-return variation across those portfolios.[^lrv]

That is a cleaner research contract than the present credit variants. [[demeter-duration-neutral-credit-carry-v2]] had to approximate OAS and roll-down using public yield-to-worst and Treasury duration matching, then found only `3.1 bp/year` of average ex-ante active pickup. Static short credit remains real income, but its active signal was not demonstrated carry. FX forward discount is directly observable and does not need bond-level OAS, spread duration, stale holdings or an ETF richness proxy.

Cleaner is not the same as stronger today. A 48-country, 36-year study subjected profitable carry rules to reality-check and stepwise data-snooping tests. Strategies selected in one period generally failed in the next, with consistency concentrated in `1998-2005`.[^hsu] The old average premium establishes a mechanism and a candidate family, not a live return forecast. This is another reason to require a locked out-of-sample shadow run rather than transfer a published Sharpe.

The gain is not a free source of orthogonality. FX carry, credit and other carry trades all tend to lose when global volatility rises, liquidity worsens and recession risk arrives.[^kmpv][^menkhoff] FX therefore changes the immediate payer from corporate default and spread liquidity to currency and funding risk, but it remains another financial short-volatility claim. It is a more distinct payer than another credit ETF, not the physical-risk payer diversification offered by CATB in [[choosing-the-concave-income-pole]].

## Only one construction fits the Demeter role

“FX carry” contains different products:

| Construction | Position | Observed shape | Demeter fit |
| --- | --- | --- | --- |
| Cross-sectional HML | Long high-rate currencies, short low-rate currencies, neutral to the base currency by construction | Positive mean, strong negative skew, downside-factor exposure | Yes, as a concave challenger |
| Country-level time series | Long or short each currency against the base according to its own forward discount | Diversified, but retains base-currency and directional effects | Contested |
| Dollar carry | Long a foreign basket and short USD when the average foreign rate exceeds USD, reverse otherwise | Higher historical Sharpe, minimal skew and no measured downside exposure | No, wrong payoff product |

The distinction is empirical, not semantic. Dollar-neutral G10 carry has substantial downside risk and high negative skew, while diversified dollar carry has minimal skew and no measured downside exposure.[^dhl] The dollar-carry strategy is also a different, largely uncorrelated premium from cross-sectional HML.[^lrv-dollar] For an EUR-base book, importing the USD result would additionally make a base-currency bet whose transfer is unproved.

The first shadow specification should therefore be **cross-sectional, base-neutral G10 carry**, not a directional EUR-versus-basket rule. Use one-month forward discounts or matched short-rate differentials known at the decision time, monthly rebalance, equal risk across currency legs, and explicit bid/ask roll costs. Report country and base-currency exposures so a hidden dollar trade cannot masquerade as a concave pole.

## Volatility targeting is a shape decision

Primary evidence disagrees on the standalone benefit. Inverse-variance management increased FX-carry Sharpe and alpha in Moreira and Muir,[^mm] while a broader volatility-targeting study found negligible Sharpe improvement for currencies even though scaling down in high volatility reduced extreme left-tail returns.[^harvey] Both mechanisms spend the property Demeter wants: exposure falls when the crash state arrives, so negative skew is compressed. This is the FX instance of [[the-skew-is-the-product]].

Do not optimize the shadow candidate on standalone Sharpe. Compare three preregistered shapes at the same ex-ante risk budget:

1. fixed gross exposure;
2. capped inverse-volatility exposure;
3. scale-down-only volatility control with no low-volatility levering above the fixed-gross cap.

Gate every variant on robust multi-month skew, downside beta/correlation, worst-window loss and marginal certainty-equivalent contribution beside locked Atalanta. Treat a sign flip in skew as a product failure even if Sharpe improves. Gross notional, per-currency concentration and margin headroom must be hard limits, not outputs of a volatility optimizer.

## IBKR spot does not deliver small-account forward carry

The academic trade is normally a zero-cost forward. IBKR's retail disclosure says its retail FX transactions are **spot**, not forwards.[^ib-risk] Spot can reproduce forward economics only if the investor receives and pays cash rates close to the relevant money-market curves. The small account does not.

As of 14 July 2026, IBKR pays zero on the first currency-specific cash tier, including EUR `10,000`, USD `10,000`, GBP `8,000`, AUD `15,000`, JPY `5,000,000`, MXN `200,000` and ZAR `150,000`. Accounts below USD `100,000` NAV receive only a proportional fraction of the quoted credit rate above those thresholds.[^ib-interest] Debit balances have no matching free tier: the first tier is generally benchmark plus `1.5%` for G10 currencies and wider for several emerging currencies, accrued daily and posted monthly.[^ib-debit] At EUR `5,000`, a diversified long basket sits below every material credit threshold while each funding-currency short balance pays the full debit schedule. The broker, not covered interest parity, captures most or all of the theoretical rate differential.

Execution adds a second barrier. IBKR charges `0.20 bp` of spot notional with a USD `2.00` minimum per order.[^ib-commission] Normal IDEALPRO minimums are roughly EUR `20,000`, USD `25,000`, GBP `20,000` and JPY `2,500,000`.[^ib-size] Smaller orders are odd lots whose limit prices are not displayed through IDEALPRO and are generally executed within one pip of the interbank best bid or offer, according to IBKR's retail disclosure.[^ib-risk] A monthly four-long/four-short basket can therefore pay at least USD `16` to enter or rebalance before spread, then repeat minima as legs change. That is structurally worse than the current two-ETF static control for a EUR `5,000` book.

Listed futures do not solve the sizing problem. CME Micro FX contracts are `12,500` EUR, `10,000` AUD, `6,250` GBP, `12,500` CHF and `1,250,000` JPY, each one-tenth of the standard contract.[^cme-micro] One contract is already roughly more than the whole EUR `5,000` book and about four to nine times a `28%` Demeter sleeve before forming both sides of HML. Integer contracts make cross-sectional weights unusably coarse. Raising the gross cap cannot fix missing carry credit, order minima, directionality or contract granularity; it only increases the loss and margin budget.

### Aegis implementation boundary

The research data schema is not the blocker. `DataConfig.instruments` accepts tradeable cash-FX identifiers with an explicit `:MID` mark, while `exchange` remains conversion-only (`aegis-rd/research/aegis_research/configuration/config_schema_guide.py`). A base-neutral FX candidate can therefore be researched without changing the schema.

Two runtime seams prevent a config-only live replacement:

- `FinancingModule._charge_debit_interest` charges configured interest on negative net currency cash, while `test_net_positive_currency_charges_no_interest` explicitly confirms that positive net currency cash receives no credit (`aegis-trader/aegis_trader/trader/financing.py`, `aegis-trader/tests/unit/test_financing.py`). A backtest cannot represent spot carry until the positive-cash side and IBKR thresholds are modeled.
- The live trader sends `AT_THE_CLOSE` for every rebalance order (`aegis-trader/aegis_trader/trader/node.py`, `aegis-trader/aegis_trader/trader/strategy.py`). IBKR lists MOC support for CFD, FUT, STK and WAR, but not CASH.[^ib-order-types] Cash FX therefore needs an asset-valid execution policy before it can share the production path.

The distinction is exact: **research candidate yes; config-only live replacement no**. Fixing either runtime seam alone is insufficient because the broker economics and small-order geometry remain binding.

### Accounting contract for any executable test

IBKR displays both a virtual FX portfolio and real currency cash balances; the virtual position can include conversions and may not equal the cash actually financed.[^ib-position] The authoritative daily return must be:

$$
r_t = \text{spot mark-to-market}_t + \text{credited settled-cash interest}_t - \text{debited settled-cash interest}_t - \text{commission}_t - \text{spread/slippage}_t.
$$

Reconcile real currency balances, settled cash, accrued interest and monthly interest postings to statements. Respect value dates and currency holidays. Never combine a forward-return backtest with IBKR spot financing assumptions, and never infer carry from the TWS virtual P&L alone. Tax treatment is entity and jurisdiction specific and remains outside this research decision.

## Failure states

- **Funding unwind:** high-rate currencies crash and funding currencies rally when risk appetite and funding liquidity fall.[^bnp]
- **Volatility shock:** high-rate currencies load negatively on innovations in global FX volatility.[^menkhoff]
- **Crowding and margin spiral:** the August 2024 yen-carry unwind showed margin increases and procyclical deleveraging amplifying an initial macro shock.[^bis]
- **Serial drawdown:** negative skew can emerge through persistent sequences of daily losses, so daily jump metrics understate the multi-month tail.[^dhl]
- **Construction drift:** a directional base-currency position or aggressive volatility timing can remove the required concavity while improving standalone Sharpe.
- **Broker basis:** spot credit and debit schedules, thresholds and entity rules can make live carry materially different from forward points.
- **Small-order drag:** commission minima and odd-lot execution overwhelm a diversified small basket.
- **Data and roll error:** stale forward points, holiday mismatches, indicative rather than executable quotes and omitted bid/ask rolls manufacture carry.
- **Leverage liquidation:** a low-volatility target can lever exposure immediately before volatility jumps, exhausting margin headroom at the worst time.

## Recommendation and next evidence

> [!decision] Shadow challenger, not replacement
> Do not replace the provisional short-credit ETF sleeve with IBKR spot FX carry at the current account size, and do not treat this as a config-only change. Create no production config. Research one base-neutral G10 forward-carry shadow stream with executable bid/ask forward data, and separately replay the same targets through IBKR's actual spot credit/debit schedule. Stop if broker-financed expected carry is non-positive before spot moves or if order minima consume a material share of gross carry. Promote only if the executable stream beats static credit on marginal certainty equivalent beside Atalanta while retaining the mandated negative-skew and downside shape.

This leaves the roster order unchanged: static credit is the deployable but provisional control; CATB remains the preferred orthogonal successor when its vehicle history matures; cross-sectional FX carry becomes the best **liquid research challenger** only if a forward-like execution route survives the small-account screen.

## Sources

[^kmpv]: Koijen, R. S. J., Moskowitz, T. J., Pedersen, L. H. and Vrugt, E. B., “Carry,” *Journal of Financial Economics* 127(2), 2018. Defines carry and documents cross-sectional and time-series return prediction, with common recession, liquidity and volatility exposure. https://www.nber.org/system/files/working_papers/w19325/w19325.pdf

[^lrv]: Lustig, H., Roussanov, N. and Verdelhan, A., “Common Risk Factors in Currency Markets,” *Review of Financial Studies* 24(11), 2011. Builds the forward-discount-sorted HML FX factor and reports its after-cost premium and explanatory share. https://www.nber.org/system/files/working_papers/w14082/w14082.pdf

[^hsu]: Hsu, P.-H., Taylor, M. P., Wang, Z. and Li, Y., “The Out-of-Sample Performance of Carry Trades,” *Journal of International Money and Finance* 143, 2024. Applies data-snooping corrections across 48 countries and 36 years and finds unstable subsequent profitability. https://doi.org/10.1016/j.jimonfin.2024.103063

[^lrv-dollar]: Lustig, H., Roussanov, N. and Verdelhan, A., “Countercyclical Currency Risk Premia,” *Journal of Financial Economics* 111(3), 2014. Separates dollar-neutral cross-sectional carry from directional dollar carry. https://www.nber.org/system/files/working_papers/w16427/revisions/w16427.rev2.pdf

[^dhl]: Daniel, K., Hodrick, R. J. and Lu, Z., “The Carry Trade: Risks and Drawdowns,” *Critical Finance Review* 6(2), 2017. Decomposes dollar-neutral and dollar-carry returns and documents construction-dependent skew and serial-loss drawdowns. https://www.kentdaniel.net/papers/published/dhl_cfr.pdf

[^bnp]: Brunnermeier, M. K., Nagel, S. and Pedersen, L. H., “Carry Trades and Currency Crashes,” *NBER Macroeconomics Annual* 23, 2009. Links carry crashes to funding constraints, declining risk appetite and position unwinds. https://www.nber.org/system/files/working_papers/w14473/w14473.pdf

[^menkhoff]: Menkhoff, L., Sarno, L., Schmeling, M. and Schrimpf, A., “Carry Trades and Global Foreign Exchange Volatility,” *Journal of Finance* 67(2), 2012. High-rate currencies lose when global FX volatility unexpectedly rises. https://doi.org/10.1111/j.1540-6261.2012.01728.x

[^mm]: Moreira, A. and Muir, T., “Volatility-Managed Portfolios,” *Journal of Finance* 72(4), 2017. Tests inverse-variance scaling, including on currency carry. https://www.nber.org/system/files/working_papers/w22208/w22208.pdf

[^harvey]: Harvey, C. R., Hoyle, E., Korgaonkar, R., Rattray, S., Sargaison, M. and van Hemert, O., “The Impact of Volatility Targeting,” *Journal of Portfolio Management* 45(1), 2018. Finds smaller tails but negligible currency Sharpe improvement. https://people.duke.edu/~charvey/Research/Published_Papers/P135_The_impact_of.pdf

[^bis]: Aquilina, M., Lombardi, M. J., Schrimpf, A. and Sushko, V., “The Market Turbulence and Carry Trade Unwind of August 2024,” BIS Bulletin 90, 2024. Official event analysis of leverage, crowding, margin increases and procyclical deleveraging. https://www.bis.org/publ/bisbull90.htm

[^ib-interest]: Interactive Brokers, “Interest Rates.” Currency-specific zero-rate thresholds and NAV scaling for positive settled cash, accessed 14 July 2026. https://www.interactivebrokers.com/en/accounts/fees/pricing-interest-rates.php

[^ib-debit]: Interactive Brokers, “Margin Rates and Financing” and “Margin Interest Calculations.” Debit tiers, daily accrual, settlement basis and monthly posting, accessed 14 July 2026. https://www.interactivebrokers.com/en/trading/margin-rates.php and https://www.interactivebrokers.com/en/trading/margin-calculation-details.php

[^ib-commission]: Interactive Brokers, “Commissions Spot Currencies.” Tier-one `0.20 bp` pricing and USD `2.00` minimum per order, accessed 14 July 2026. https://www.interactivebrokers.com/en/pricing/commissions-spot-currencies.php

[^ib-size]: Interactive Brokers, “Spot Currency Minimum/Maximum Order Sizes.” IDEALPRO order-size table, accessed 14 July 2026. https://www.interactivebrokers.com/en/trading/forexOrderSize.php

[^ib-order-types]: Interactive Brokers, “Order Types.” Lists CASH for plain market orders but not among the supported products for Market-on-Close orders, accessed 14 July 2026. https://www.interactivebrokers.com/campus/ibkr-api-page/order-types/

[^ib-risk]: Interactive Brokers, “Risk Disclosure Statement for Forex Trading and IB Multi-Currency Accounts.” Retail spot-only product statement, odd-lot treatment, leverage and dealer-counterparty risks. https://www.interactivebrokers.com/Universal/servlet/Registration.formSampleView?ad=forex_mult_curr_risk_disclosure.jsp

[^ib-position]: Interactive Brokers, “FX Portfolio - Virtual FX Position.” Distinguishes virtual FX P&L positions from real currency cash balances. https://qa.interactivebrokers.ca/en/software/tws/usersguidebook/realtimeactivitymonitoring/fxportfolio.htm

[^cme-micro]: CME Group, “Micro FX Futures.” Official contract-size table for Micro EUR/USD, AUD/USD, GBP/USD, CHF/USD and JPY/USD futures, accessed 14 July 2026. https://www.cmegroup.com/markets/microsuite/fx.html
