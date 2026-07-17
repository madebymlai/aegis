---
title: Choosing the Concave Income Pole
date: 2026-07-13
topic: strategy-roster
status: decision
related:
  - "[[the-tiered-strategy-roster]]"
  - "[[short-horizon-reversal-in-small-cross-sections]]"
  - "[[insurance-linked-securities-as-the-orthogonal-income-pole]]"
  - "[[demeter-duration-neutral-credit-carry-v2]]"
tags:
  - note
  - carry
  - mean-reversion
  - concavity
  - demeter
---

# Choosing the Concave Income Pole

> [!abstract] Decision
> Carry has the stronger direct claim on the roster's calm-income job. Short-horizon mean reversion is primarily paid liquidity provision and belongs first in execution. The strongest eventual concave pole is not one universal signal but a small set of independent payers, with insurance carry preferred when its vehicle and evidence are adequate.

## Carry and mean reversion are different businesses

Carry is an accrual conditional on prices not moving: interest differential, curve roll, credit spread, option premium or insurance spread. Koijen, Moskowitz, Pedersen and Vrugt apply that definition across equities, bonds, commodities, Treasuries, credit and options. Their individual carry strategies average a `0.8` Sharpe and the diversified cross-asset portfolio reaches `1.2`; averaging the signal over twelve months preserves a `1.1` Sharpe while cutting turnover by about half.[^kmpv] Bhansali et al. independently find carry and trend mutually diversifying across twenty markets and four asset classes.[^carrytrend] Carry therefore matches the calm-income mandate, although not every carry has negative skew and global versions share recession, liquidity and volatility drawdowns.

Short-horizon mean reversion is paid for a different service. Its counterparty demands immediacy, and the reverter warehouses a transient price displacement until order flow clears. Nagel shows that reversal returns proxy for liquidity provision and that their expected return and conditional Sharpe rise sharply with VIX during market turmoil.[^nagel] That state dependence makes reversal a poor synonym for a quiet-market coupon. Live institutional trade data make short-term reversal the least scalable major equity anomaly, with estimated net return of only `1.52%` per year in the standard construction.[^fim] A peer-reviewed pairs-trading follow-up finds about `30 bp` per month after commissions, impact and borrow fees over 1963-2009, but both pairs and industry-relative contrarian strategies are largely unprofitable after 2002.[^pairs]

The practical prescription follows the mechanism: use reversal first to time trades the parent strategy already wants, and promote it to a sleeve only when a broad, liquid cross-section and measured execution costs support it. The project-level reversal evidence already reached the same conclusion in [[short-horizon-reversal-in-small-cross-sections]].

## The alternatives are other payers, not cleverer labels

Merger arbitrage collects deal spread rather than market yield. Mitchell and Pulvino find `4%` annual excess return after transaction costs across 4,750 deals, but the payoff becomes equity-sensitive in severe market declines and resembles an uncovered short put.[^mitchell] Baker and Savasoglu trace `0.6-0.9%` monthly abnormal returns over 1981-1996 to deal-completion risk, target size and limited arbitrage capital.[^bakersavasoglu] It is a genuine concave income candidate with a different immediate payer, but not an escape from tail risk.

Catastrophe bonds are the cleanest orthogonal member because their principal-loss trigger is physical rather than recessionary. Mean-variance spanning tests over 2002-2017 find that they open portfolios not attainable from traditional assets and factors, especially during crisis and high-volatility periods. A separate crisis study finds a Lehman liquidity beta, but far smaller than conventional risky assets.[^catdiv][^catcrisis]

The resulting ordering is a synthesis rather than a demonstrated dominance result:

1. Prefer insurance carry when the vehicle and evidence are adequate.
2. Use low-turnover credit carry as the liquid fallback.
3. Treat merger arbitrage as an event-driven challenger.
4. Keep short-horizon reversal in execution until breadth and costs prove it can stand alone.
5. Do not use direct short volatility as the default. It is the purest negative-skew premium but the weakest payer diversification, because it sells the same financial crash around which the convex tiers are organized.[^skewpremia]

## Immediate Demeter decision

V2 falsified its active four-fund richness tilt, not the static credit-income control. It does not follow that V1 should survive by default. The next comparison is:

- V1 static `SDHY + LQDH`;
- V2 static four-fund control: equal weights in `SDIG`, `LQDE`, `SDHY` and `IHYU`.

Both must be reproduced through their real Component, total-return, FX, fee and portfolio-simulation paths over an identical common window. Compare standalone income shape and marginal contribution beside locked Atalanta. Do not use V2's active candidate and do not hand-build return proxies.

## Static-control comparison

The locked production-path replay covers 70 complete months from September 2020 through June 2026, the common history of Atalanta, V1 and V2 after both Demeter configs were extended to the same `2026-07-01` exclusive end. V2 is locked to `cand_c79ccb2de168e0f4017a2fe22c4ca6d9`, whose `selection_strength = 0` is the equal-weight four-fund control. Returns include the configs' total-return data, EUR conversion, transaction costs, fixed fees and drift-band execution.

| Monthly evaluation | V1: `SDHY + LQDH` | V2: four-fund control | V2 minus V1 |
|---|---:|---:|---:|
| Standalone annualized return | 4.83% | 3.51% | -1.32 pp |
| Standalone annualized volatility | 5.41% | 5.81% | +0.40 pp |
| Standalone Sharpe | 0.900 | 0.622 | -0.278 |
| Standalone MPPM certainty equivalent | 4.43% | 3.12% | -1.31 pp |
| Standalone maximum drawdown | -8.96% | -8.89% | +0.06 pp |
| 60/40 floor annualized return | 10.33% | 9.80% | -0.54 pp |
| 60/40 floor annualized volatility | 6.57% | 6.41% | -0.16 pp |
| 60/40 floor Sharpe | 1.535 | 1.496 | -0.039 |
| 60/40 floor MPPM certainty equivalent | 9.43% | 8.96% | -0.47 pp |
| 60/40 floor maximum drawdown | -5.01% | -5.34% | -0.33 pp |
| Monthly correlation to Atalanta | 0.007 | -0.092 | -0.099 |

V2 buys modestly lower whole-floor volatility and lower correlation to Atalanta, but gives up materially more return and certainty equivalent and worsens the floor's maximum drawdown by 33 basis points. Its diversification benefit does not compensate for the weaker standalone sleeve. The two carry controls themselves have `0.914` monthly correlation, so the extra funds mainly reshape the same credit exposure rather than add an independent payer.

> [!decision] Keep V1
> Retain static `SDHY + LQDH` as Demeter's credit control. Preserve V2 static as the falsification control for the duration-matched active design, not as the new champion. This is descriptive reused-history evidence rather than a fresh out-of-sample promotion test; the worst-decile correlations contain only seven observations and are not decision-grade by themselves.

## Limitations

No primary study runs a contemporary, implementation-matched horse race among credit carry, catastrophe bonds, merger arbitrage and reversal. Cat-bond evidence uses an underlying market history much longer than the current UCITS ETF wrapper; merger-arbitrage evidence is strongest in older deal samples; and reversal profitability changes materially with universe, period and cost model. Promotion must compare realizable total-return streams under identical fees, frequency and portfolio context rather than transfer published Sharpes.

## Follow-up hypotheses

- [ ] **Carry beats reversal for calm income in a constrained book.** At matched ex-ante risk and identical realized costs, a low-turnover carry candidate delivers higher return in calm months, lower turnover, and greater marginal certainty-equivalent contribution beside the divergent pole than standalone short-horizon reversal.
- [ ] **Payer diversification beats signal diversification.** A two-member convergent portfolio whose losses arise from distinct event families improves marginal certainty equivalent and worst-window tail contribution beside the divergent pole relative to either member alone.

## Sources

[^kmpv]: Koijen, R. S. J., Moskowitz, T. J., Pedersen, L. H. & Vrugt, E. B., "Carry", Journal of Financial Economics 127(2):197-225, 2018 - carry predicts returns across six broad markets plus within Treasuries, credit and options; diversified cross-asset carry reaches a `1.2` Sharpe, while a twelve-month averaged signal retains `1.1` and cuts turnover about 50%. Peer-reviewed; Moskowitz and Pedersen were AQR-affiliated. https://doi.org/10.1016/j.jfineco.2017.11.002

[^carrytrend]: Bhansali, V., Davis, J., Dorsten, J. & Rennison, G., "Carry and Trend in Lots of Places", Journal of Portfolio Management, 2015 - across twenty markets and four asset classes from 1960 to 2014, carry and trend are mutually diversifying, including in extreme states. PIMCO authors. https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2579089

[^nagel]: Nagel, S., "Evaporating Liquidity", Review of Financial Studies 25(7):2005-2039, 2012 - short-term reversal returns proxy for compensation to liquidity providers; expected returns and conditional Sharpe ratios rise sharply with VIX during financial turmoil. https://www.nber.org/system/files/working_papers/w17653/w17653.pdf

[^fim]: Frazzini, A., Israel, R. & Moskowitz, T. J., "Trading Costs of Asset Pricing Anomalies", working paper, 2015 - nearly one trillion dollars of live institutional trades show short-term reversal is the most cost-constrained major anomaly; its standard portfolio's estimated net return is `1.52%` per year. AQR authors. https://pages.stern.nyu.edu/~afrazzin/pdf/Trading%20Cost%20of%20Asset%20Pricing%20Anomalies%20-%20Frazzini,%20Israel%20and%20Moskowitz.pdf

[^pairs]: Do, B. & Faff, R., "Are Pairs Trading Profits Robust to Trading Costs?", Journal of Financial Research 35(2):261-287, 2012 - well-matched industry pairs earn about `30 bp` monthly after modeled costs over 1963-2009, but pairs and industry-relative reversal are largely unprofitable after 2002. https://doi.org/10.1111/j.1475-6803.2012.01317.x

[^mitchell]: Mitchell, M. & Pulvino, T., "Characteristics of Risk and Return in Risk Arbitrage", Journal of Finance 56(6):2135-2175, 2001 - 4,750 mergers over 1963-1998 produce `4%` annual excess return after transaction costs, with put-like downside exposure in severe declines. https://doi.org/10.1111/0022-1082.00401

[^bakersavasoglu]: Baker, M. & Savasoglu, S., "Limited Arbitrage in Mergers and Acquisitions", Journal of Financial Economics 64(1):91-115, 2002 - diversified risk-arbitrage portfolios earn `0.6-0.9%` abnormal return per month over 1981-1996; returns rise with completion risk and target size and fall with arbitrage capital. https://doi.org/10.1016/S0304-405X(02)00072-7

[^catdiv]: Demers-Belanger, K. & Lai, V. S., "Diversification Benefits of Cat Bonds: An In-Depth Examination", Financial Markets, Institutions & Instruments 29(5):165-228, 2020 - 2002-2017 spanning tests find cat bonds create previously unattainable portfolios and improve time-varying diversification measures, particularly in crisis and high-volatility episodes. https://doi.org/10.1111/fmii.12134

[^catcrisis]: Carayannopoulos, P. & Perez, M. F., "Diversification through Catastrophe Bonds: Lessons from the Subprime Financial Crisis", Geneva Papers on Risk and Insurance 40(1):1-28, 2015 - cat bonds developed market correlation during Lehman through collateral and counterparty channels, but the change was far smaller than for conventional assets. https://doi.org/10.1057/gpp.2014.14

[^skewpremia]: Lempérière, Y., Deremble, C., Nguyen, T.-T., Seager, P., Potters, M. & Bouchaud, J.-P., "Risk Premia: Asymmetric Tail Risks and Excess Returns", Quantitative Finance 17(1):1-14, 2017 - across equity, carry, short-volatility, bond and credit premia, Sharpe is closely related to negative tail skew; trend is the principal positive-skew exception. CFM authors. https://doi.org/10.1080/14697688.2016.1183035
