---
title: Accessible Ordinary-Market Strategies After an Open Search
date: 2026-07-17
topic: strategy-roster
status: research-decision
aliases:
  - The €5k ordinary-market strategy search
related:
  - "[[the-tiered-strategy-roster]]"
  - "[[finding-a-buildable-convergent-engine]]"
  - "[[what-can-fill-the-concave-floor-at-eur-5000-now]]"
  - "[[building-the-tiered-roster-after-demeter-v2]]"
  - "[[cash-merger-breadth-standalone-or-sub-engine]]"
tags:
  - research
  - demeter
  - strategy-search
  - corporate-actions
  - strategy-design
  - implementation
---

# Accessible Ordinary-Market Strategies After an Open Search

> [!abstract] Decision
> **A holding is not a [[what-is-a-strategy|strategy]].** CATB, JCL0, credit, cash and option-income ETFs may be useful exposures, but “buy the asset” does not supply the missing Demeter strategy. A qualifying strategy needs a repeatable signal, an action rule, an exit rule, and a reason the edge should recur.
>
> The wide-to-narrow search found **no ready-to-promote low-data strategy** for a €5,000 EU-retail IBKR account. Convergence is not mandatory: the job is positive ordinary-market return from a repeatable rule that diversifies Atalanta's slow non-equity time-series trend. The research frontier therefore has three lanes: a **public-filings special-situations scanner**, a one-ETF **turn-of-month/public-flow rule**, and **cross-sectional sector or country relative-strength rotation**. A volatility-managed equity rule is the tactical-allocation control. All remain research candidates, not allocations.
>
> Do not subscribe to merger or credit data yet. First test whether free SEC filings plus prices produce enough *live, executable* opportunities after IBKR deadlines, FX, spreads and fixed commissions. If they do not, leave the Floor strategy seat empty; static exposures belong in asset allocation, not under a strategy label.

## The strategy contract

A new ordinary-market candidate must declare all five elements:

1. **State:** the observable condition that creates an opportunity.
2. **Action:** exactly what is bought, tendered, subscribed or sold.
3. **Exit:** a date, corporate-action settlement, spread close, rebalance or state transition.
4. **Payer / edge:** the constrained actor, administrative rule or behavioral flow that pays the strategy.
5. **Failure:** the event that defeats the intended exit or makes costs dominate.

This excludes a static bond, cat-bond or CLO allocation. Those have risk premia, but no changing state and no action rule beyond holding. It also excludes threshold rebalancing by itself: rebalancing is portfolio policy unless a separately evidenced state predicts a return or risk change.

**Convergence is one design, not the job definition.** A cross-sectional rotation, seasonal public-flow rule or tactical exposure rule can qualify if its return driver is distinct from Atalanta, its costs fit the account, and it improves the complete book. Conversely, a beautifully convergent rule that is too sparse or expensive does not qualify. Admission is based on marginal portfolio utility and mechanism independence, not payoff-shape vocabulary.

The account constraints remain binding: approximately €5,000, EU retail/PRIIPs access, no account-level derivatives, whole-share API execution, public/free inputs preferred, and IBKR's current €1.25 minimum under tiered European stock/ETF pricing.[^ibkrfees] A viable strategy therefore needs few tickets, slow turnover and meaningful euros per event.

## Search method: genuinely wide, then narrow

The first Exa phase did not name preferred mechanisms. Representative queries were:

> [!info]- Open-ended queries recorded before narrowing
> - “Original empirical research on repeatable public-market trading rules for small unlevered investors where each opportunity has an observable signal, a dated or state-defined exit, and inputs available from prices or public filings; survey broadly without naming a preferred event or asset class.”
> - “What institutional constraints, forced flows, issuance mechanics, governance events, or calendar mechanics create repeatable temporary mispricings that an unlevered long-only public-market investor can trade infrequently using public information?”
> - “Original research on small-capital market strategies built around public corporate actions or exchange mechanisms, with explicit entry and exit rules and realistic transaction costs, no derivatives or short selling.”
> - “Which low-frequency price-only trading rules have a genuine buy signal and exit rule, work on liquid listed funds or indices, and earn in non-crisis markets after implementation costs? Search all rule families without assuming momentum or reversal.”
> - “Map every documented source of positive expected return in public markets that a small unlevered investor can access. Organize by who pays and why, not by asset-class labels.”
> - “What portfolio designs can generate ordinary-market compounding while retaining protection from persistent dislocations, without requiring a dedicated short-volatility or convergence strategy?”

That broad phase surfaced:

- corporate-action and event rules;
- closed-end-fund/investment-trust discount convergence;
- institutional month-end and rebalance flows;
- liquidity provision and short-horizon reversal;
- rights offerings and issuance concessions;
- risk-arbitrage and relative-value rules;
- factor and price-only timing rules;
- constant rebalancing and volatility scaling;
- packaged market-neutral/alternative strategies;
- static risk-premium exposures.

Only then did the narrow phase name odd-lot tenders, SPAC redemption, rights, investment-trust catalysts, turn-of-month, merger arbitrage and ETF reversal. The static-exposure results are retained below as benchmarks, not promoted as strategies.

## Ranked strategy shortlist

### 1. Catalyst-backed investment-trust discount convergence

**Contract**

- **State:** a listed closed-end fund trades at a wide discount to a current, independently observable NAV **and** has a dated tender, liquidation, open-ending proposal, continuation vote or asset-realization program.
- **Action:** buy only when conservative post-cost value at the catalyst exceeds market price by a fixed hurdle.
- **Exit:** tender/liquidation proceeds, the catalyst date, or a predeclared discount-close threshold—whichever comes first.
- **Payer:** incumbent holders or constrained sellers discount uncertain governance and timing; the catalyst creates a path to NAV.
- **Failure:** vote fails, terms change, NAV falls, the catalyst is delayed, discount remains wide, or GBP/stamp/spread costs consume the edge.

This is the cleanest sparse true-convergence rule found. Generic “buy the widest discount” is not enough: closed-end-fund discounts can persist because arbitrage is costly and managerial contracts, sentiment and asset illiquidity are real.[^pontiff][^berkstanton] The catalyst is load-bearing. Primary research on activist open-ending attempts documents material discount effects around campaigns to unlock closed-end-fund NAV.[^activist]

**Why it is not ready:** UK investment trusts add stale/estimated NAV, 0.5% stamp duty on purchases, GBP conversion, wide spreads and corporate-action-specific terms. Aegis also lacks a causal RNS/catalyst tape. The first test is an opportunity census, not a backtest: can free issuer/RNS/AIC data identify at least ten clean historical events and several live candidates without hindsight?

**Rank:** best mechanism; research first.

### 2. SPAC redemption / liquidation spread

**Contract**

- **State:** a pre-combination SPAC common share trades below conservative cash-in-trust per redeemable share before an extension or combination vote, and the filings preserve redemption rights for a secondary-market buyer.
- **Action:** buy common shares only—never warrants or post-merger equity—and submit the redemption election before the broker's earlier deadline.
- **Exit:** receive trust cash at redemption/liquidation; otherwise exit before de-SPAC exposure begins.
- **Payer:** complexity, deadline risk, limited capacity and investors unwilling to process a voluntary corporate action.
- **Failure:** missed eligibility/deadline, changed trust expenses/taxes, redemption restriction, settlement failure, price/FX move, or accidental conversion into post-merger risk.

The structure is real: SPAC shareholders receive a redemption choice around de-SPAC or extension votes, and the 2024 SEC rules enhanced disclosure around sponsor compensation, conflicts and dilution.[^spacrule] The literature also shows why the exit rule must be absolute: post-merger SPAC economics contain severe dilution and agency conflicts; the trade is the cash claim, not the company.[^soberspac][^spacincentives]

**Why it is not ready:** the search did not find clean modern primary evidence that a secondary buyer's below-trust redemption spread remains positive after all costs. The opportunity set has shrunk, trust-value reconstruction is filing-specific, and broker eligibility/deadlines must be tested. IBKR supports voluntary corporate-action elections and currently lists “all other” corporate actions as free, but its own submission deadline can precede the issuer's.[^ibkrca][^ibkrfeesother]

**Rank:** strongest US-filings tracer because payoff and exit are explicit; one paper/live what-if before any capital.

### 3. Odd-lot issuer self-tender priority

**Contract**

- **State:** a Schedule TO explicitly gives holders of fewer than 100 shares priority over proration, and the lowest conservative tender outcome exceeds price plus all costs by a hurdle.
- **Action:** buy no more than 99 shares, verify beneficial-owner aggregation and eligibility dates, then tender all shares.
- **Exit:** cash tender settlement; abandon before the election deadline if an amendment removes the edge.
- **Payer:** issuers exempt small holders from proration to avoid the administration of residual odd lots; capacity is deliberately tiny.
- **Failure:** offer withdrawal/amendment, Dutch-auction clearing below the assumed price, odd-lot aggregation, missed broker deadline, market loss if tender fails, FX or tax.

SEC Schedule TO filings and amendments are free through EDGAR, whose submissions APIs require no paid dataset.[^edgar] IBKR's corporate-action manager supports Dutch-auction elections.[^ibkrca]

But this is a **falsification candidate**, not a rediscovered free lunch. A 2021 re-examination found that the large tendering profits documented in older samples disappeared in 2000–2015.[^tenderreexam] The odd-lot clause may still create isolated contractual spreads, but no kept primary evidence establishes a dependable modern stream.

**Rank:** easiest bounded-capital corporate-action pilot; likely too sparse to be a sleeve.

### 4. Turn-of-month payment-cycle rule

**Contract**

- **State:** a fixed calendar window around month-end, defined once rather than optimized.
- **Action:** hold one liquid equity UCITS ETF only during the preregistered window; otherwise hold EUR cash.
- **Exit:** close at the fixed end of the window.
- **Payer:** recurring institutional cash needs and month-end portfolio flows.
- **Failure:** anomaly decay, overnight gap risk, taxes/spreads, or the €1.25 ticket floor exceeding the edge.

The primary evidence is stronger than for generic calendar folklore. McConnell and Xu document that US equity excess returns concentrate around the turn of the month; Etula et al. connect cross-market patterns to institutional month-end cash needs.[^tom][^dashcash] Recent work argues that payment-cycle pressure reverses and survives transaction costs out of sample, but it remains a working paper and must not set parameters after inspection.[^paymentreversal]

Operationally, one entry and exit per month means 24 orders per year: at the €1.25 minimum, €30 annually is already 60 bp of the entire €5,000 book and much more of a small sleeve. The better first use is therefore an **execution overlay**: time an equity allocation or already-required rebalance within the window without creating extra round trips.

**Rank:** best price-only benchmark; unlikely to fund a separate sleeve after retail costs.

### 5. Cross-sectional sector/country relative-strength rotation

**Contract**

- **State:** once monthly, rank a fixed set of liquid UCITS sector or country ETFs by a preregistered trailing relative-return measure.
- **Action:** hold the top one or two whole-share ETFs, with a wide incumbent/challenger buffer; unselected capital stays in cash or the strategic baseline.
- **Exit:** monthly rebalance only when a challenger clears the buffer, or when the holding leaves the broader retain set.
- **Payer:** gradual information diffusion and institutional capital moving across industries or regions.
- **Failure:** momentum reversal, common equity crash, narrow breadth, lookback mining and retail ticket drag.

Industry momentum is well documented in the original stock-level research, and later primary work tests whether industry and country momentum transfers to ETFs.[^industrymomentum][^etfmomentum] This is a genuine repeatable strategy using free adjusted prices, monthly decisions and long-only instruments.

It is also the closest competitor to Atalanta, so overlap is the first gate. Atalanta is slow **time-series** trend on non-equity macro assets; this rule is **cross-sectional** relative strength on equity sectors or countries and remains invested in the strongest member. That is a different signal and substrate, but both are momentum and both can be wrong-footed by sharp reversals. It belongs naturally in Expansion unless the aligned return stream shows low dependence and improves ordinary-market compounding without weakening crises.

**Rank:** best continuous price-only strategy; high overlap risk, so compare against equal-weight equity and Atalanta before tuning.

### 6. Volatility-managed equity or factor exposure

**Contract**

- **State:** prior-month realized variance of one broad equity or factor ETF.
- **Action:** scale the next month's ETF/cash exposure inversely with the frozen variance estimate, subject to a no-trade band and no leverage.
- **Exit:** resize monthly only when the band is crossed.
- **Payer:** the underlying equity/factor premium; the rule seeks to avoid states where variance rises more than expected return.
- **Failure:** volatility whipsaw, overnight gaps, cash drag and duplication of parent risk controls.

Moreira and Muir report higher Sharpe ratios from inverse-variance scaling across equity factors and other premia.[^volmanaged] This is a strategy rather than an asset because state changes cause exposure changes under a fixed rule. Yet Aegis already volatility-targets sleeves and delevers on drawdown. A standalone version may be the same risk decision implemented twice, violating information hiding at the portfolio level.

**Rank:** useful tactical-allocation control; reject if its return is explained by the existing allocator's volatility and delevering path.

### 7. Rights-offering value transfer

**Contract**

- **State:** a tradable right plus subscription cash costs less than delivered-share value after dilution, fees, timing and a large uncertainty reserve.
- **Action:** buy rights and exercise, or buy the parent before record date only when entitlement is certain and economical.
- **Exit:** sell delivered shares after settlement or at a fixed convergence threshold.
- **Payer:** shareholder nonparticipation, complexity and temporary financing demand.
- **Failure:** oversubscription/proration, delayed delivery, price collapse, non-transferable rights, withholding/tax, or broker ineligibility.

Primary research documents valuable rights going unexercised and shows that subscription periods and liquidity affect take-up.[^rightsnonparticipation][^rightsliquidity] That establishes a mechanism, not a ready trading rule. Every market has different entitlement, settlement and broker handling, and the account must reserve the full subscription cash.

**Rank:** retain in the scanner taxonomy; do not prototype before tender/SPAC operations are proven.

## Explicit rejects and demotions

| Candidate | Decision | Reason |
| --- | --- | --- |
| Direct fixed-cash merger arbitrage | **Blocked, not disproved** | It is a true strategy, but the free discovery tape has not yet achieved the breadth shown by the literature. See [[cash-merger-breadth-standalone-or-sub-engine]]. A cheap fund can be a benchmark, not proof of a self-run rule. |
| Generic investment-trust discount | **Reject** | Discount without a dated catalyst is value exposure, not convergence; it can widen indefinitely. |
| Short-horizon ETF/stock reversal | **Reject as sleeve** | Prices are free, but turnover, shorts, borrow and breadth are not. Live institutional work finds reversal the most cost-constrained major anomaly.[^reversalcost] Aegis's own naive version lost net; see [[short-horizon-reversal-in-small-cross-sections]]. |
| Simple pairs trading | **Reject** | Pair choice is specification mining and structural breaks dominate a tiny book; shorting and borrow remain. |
| Threshold/constant rebalancing | **Portfolio rule** | Cover's guarantee is relative to the best hindsight constant-rebalanced portfolio, not positive finite-sample income after costs.[^cover] No separate payer means no separate sleeve. |
| Auction concessions | **Reject now** | Sovereign/corporate auctions require bond execution, allocation and often large denominations; an ETF cannot isolate the dated concession. |
| Ex-dividend and tax calendar rules | **Reject now** | Edge is investor-tax and market-structure specific; gross distributions are not returns, and repeated trades face spread/withholding. |
| Spin-offs / buyback announcement drift | **Expansion research** | Repeatable event signals exist, but exit is not contractual convergence and returns retain equity/factor exposure. |
| Packaged market-neutral UCITS | **Benchmark/external manager** | The manager has a strategy, but Aegis is only holding a fund. High management/performance fees and share-class access make it a comparator, not Demeter's self-run strategy. |

## Static exposures are not the answer

The earlier search surfaced CATB, AAA CLOs, fallen angels, target-maturity bonds, AT1, convertibles, put-write and enhanced commodity ETFs. They may be valuable **assets** or manager wrappers, but they do not satisfy the strategy contract:

| Exposure | What it can do | What it cannot claim |
| --- | --- | --- |
| CATB | Add catastrophe-insurance risk largely outside the financial cycle | A repeatable Aegis signal/action/exit rule |
| JCL0 / short credit / fallen angels | Supply credit and liquidity income | Independent convergence or proof of Floor utility |
| E50PW / covered calls | Sell option insurance inside a wrapper | Low crash dependence merely because it distributes income |
| Cash / iBonds | Set a hurdle and preserve capital | Alpha or a convergent engine |
| WCOE / commodity roll | Add commodity risk-premium exposure | Stable ordinary-market income independent of Atalanta |

The distinction matters empirically. The latest Floor re-verification found `corr(trend, carry) = +0.173`, and trend-only beat every tested carry weight on Sharpe, UPI, max drawdown and crisis return.[[runs/floor/2026-07-03]] Static credit did not become a strategy because it had a yield.

## Concrete next experiment

Run three deliberately different tracer lanes before any trading engine. This prevents the research from converging on corporate-action arbitrage merely because its contracts are easiest to describe.

1. **Event lane:** one special-situations opportunity ledger for catalyst-backed trusts, SPAC redemptions and odd-lot tenders.
2. **Public-flow lane:** one frozen turn-of-month window on one liquid equity UCITS ETF, tested after the exact IBKR ticket schedule.
3. **Cross-sectional lane:** monthly top-one/top-two sector or country relative strength with a wide retain band, compared with equal weight and with Atalanta.

The volatility-managed equity rule is the tactical control, not a fourth campaign.

### Inputs

- SEC submissions metadata and filing documents from free EDGAR APIs;
- free daily prices and FX;
- Schedule TO and amendments for issuer tenders;
- proxy/8-K filings for SPAC extension, combination and liquidation votes;
- issuer/RNS announcements and NAV disclosures for investment trusts;
- IBKR corporate-action notices, eligibility, internal deadlines and what-if outputs.

### One common event record

For every event, record announcement timestamp, tradable identity, eligibility/record date, action deadline, contractual cash or NAV anchor, conservative failure value, capital required, all fees/FX, exit date and source document. Do not estimate return when any term is unknown.

### Gates before a backtest

1. At least ten clean historical observations per family reconstructed without hindsight.
2. At least three live-paper observations whose terms were captured before outcome.
3. A successful IBKR paper election or support confirmation for each corporate-action type.
4. Conservative net spread above 1% of deployed capital **and** above a euro hurdle large enough to survive the fixed ticket and operational work.
5. No position can lose more than its declared event-risk budget if convergence fails.
6. Cash is the output when no event clears the hurdle; never force continuous investment.

### Kill order

1. Odd-lot tenders: kill quickly if no modern census or terms survive the 2021 anomaly-decay result.
2. SPAC redemption: kill if secondary-buyer eligibility, broker deadlines or trust-value uncertainty cannot be made deterministic.
3. Catalyst-backed trusts: continue only if free causal data supplies enough events after UK friction.
4. Turn-of-month: kill as a sleeve if the exact preregistered window does not beat cash after 24 annual minimum commissions; retain only as an execution overlay if it lowers implementation shortfall.

> [!important] Practical recommendation
> The missing ordinary-market strategy is still missing. The honest next step is **not** “buy CATB” or “buy CLOs,” and it is not “force convergence.” Test three independent rule families: public-filings events, recurring public flows, and cross-sectional ETF rotation. Catalyst-backed investment trusts are the cleanest convergence design; sector/country relative strength is the best continuous price-only design; turn-of-month is the lowest-data flow design. Promote only the rule that adds marginal utility beside Atalanta after fees and stress dependence. If none does, keep the seat empty rather than relabeling an exposure.

## Sources

[^ibkrfees]: Interactive Brokers Ireland, [European stocks and ETF commissions](https://www.interactivebrokers.ie/en/pricing/commissions-stocks-europe.php). Official broker schedule.

[^pontiff]: Pontiff, [“Costly Arbitrage: Evidence from Closed-End Funds”](https://doi.org/10.2307/2946683), *Quarterly Journal of Economics* 111(4), 1996. Primary empirical research.

[^berkstanton]: Berk and Stanton, [“Managerial Ability, Compensation, and the Closed-End Fund Discount”](https://faculty.haas.berkeley.edu/stanton/pdf/closed.pdf), *Journal of Finance* 62(2), 2007. Original research.

[^activist]: Bradley, Brav, Goldstein and Jiang, [“Activist Arbitrage: A Study of Open-Ending Attempts of Closed-End Funds”](https://business.columbia.edu/sites/default/files-efs/pubfiles/4118/activist_arb.pdf), 2008. Primary event-study research.

[^spacrule]: U.S. SEC, [Special Purpose Acquisition Companies, Shell Companies, and Projections—final rule](https://www.sec.gov/files/rules/final/2024/33-11265.pdf), 2024. Official regulator source.

[^soberspac]: Klausner, Ohlrogge and Ruan, [“A Sober Look at SPACs”](https://securities.stanford.edu/academic-articles/20201028-a-sober-look-at-spacs.pdf), *Yale Journal on Regulation* 39, 2022. Primary empirical/legal research.

[^spacincentives]: Feng, Nohel, Tian, Wang and Wu, [“The Incentives of SPAC Sponsors”](https://www.sec.gov/comments/s7-13-22/s71322-20156792-324947.pdf), 2023. Primary structural/empirical paper submitted to the SEC record.

[^ibkrca]: Interactive Brokers, [Corporate Action Instructions](https://www.interactivebrokers.ie/en/trading/corp-action-instructions.php). Official broker workflow.

[^ibkrfeesother]: Interactive Brokers Ireland, [Other Fees—Corporate Actions](https://www.interactivebrokers.ie/en/pricing/other-fees.php). Official broker schedule; “all other” corporate actions are listed as free, subject to event terms and deadlines.

[^edgar]: U.S. SEC, [Accessing EDGAR Data](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data) and [Developer Resources](https://www.sec.gov/about/developer-resources). Official free filing/API documentation.

[^tenderreexam]: Kadapakkam, Zhang and Yildirim, [“A Reexamination of the Tendering Profit Anomaly”](https://doi.org/10.1007/s11156-020-00935-4), *Review of Quantitative Finance and Accounting* 56, 2021. Primary empirical research; finds abnormal tendering profits disappeared in 2000–2015.

[^tom]: McConnell and Xu, [“Equity Returns at the Turn of the Month”](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=925589), *Financial Analysts Journal* 64(2), 2008. Primary empirical research.

[^dashcash]: Etula, Rinne, Suominen and Vaittinen, [“Dash for Cash: Monthly Market Impact of Institutional Liquidity Needs”](https://www.aalto.fi/sites/default/files/2021-03/dashforcashpaper_final_complete.pdf), *Review of Financial Studies* 33(1), 2020. Primary cross-market research.

[^paymentreversal]: Graziani, [“Time Series Reversal: A Payment Cycle Friction”](http://www.efmaefm.org/0EFMAMEETINGS/EFMA%20ANNUAL%20MEETINGS/2024-Lisbon/papers/JMP_GG_JAN2024.pdf), 2024 working paper. Primary but unrefereed evidence.

[^rightsnonparticipation]: Rantapuska and Knüpfer, [“Which Investors Leave Money on the Table? Evidence from Rights Issues”](https://doi.org/10.1093/rof/rfn018), *Review of Finance* 12(4), 2008. Primary empirical research.

[^rightsliquidity]: Holderness and Pontiff, [“Shareholder Nonparticipation in Valuable Rights Offerings”](https://doi.org/10.1016/j.jfineco.2016.01.011), *Journal of Financial Economics* 120(2), 2016, and Massa, Vermaelen and Xu, [“Rights Offerings, Subscription Period, Shareholder Takeup, and Liquidity”](https://doi.org/10.1017/S002210901900034X), *Journal of Financial and Quantitative Analysis* 55(4), 2020. Primary empirical research.

[^reversalcost]: Frazzini, Israel and Moskowitz, [“Trading Costs of Asset Pricing Anomalies”](https://pages.stern.nyu.edu/~afrazzin/pdf/Trading%20Cost%20of%20Asset%20Pricing%20Anomalies%20-%20Frazzini,%20Israel%20and%20Moskowitz.pdf). Primary study using live institutional trades; authors are AQR-affiliated.

[^cover]: Cover, [“Universal Portfolios”](https://isl.stanford.edu/~cover/papers/universal_portfolios.pdf), *Mathematical Finance* 1(1), 1991. Original paper.

[^industrymomentum]: Moskowitz and Grinblatt, [“Do Industries Explain Momentum?”](https://doi.org/10.1111/0022-1082.00146), *Journal of Finance* 54(4), 1999. Primary empirical research.

[^etfmomentum]: Andreu, Swinkels and Tjong-A-Tjoe, [“Can Exchange Traded Funds Be Used to Exploit Industry and Country Momentum?”](https://doi.org/10.1007/s11408-013-0207-8), *Financial Markets and Portfolio Management* 27, 2013. Primary ETF implementation research.

[^volmanaged]: Moreira and Muir, [“Volatility-Managed Portfolios”](https://www.nber.org/system/files/working_papers/w22208/w22208.pdf), *Journal of Finance* 72(4), 2017. Primary empirical research.
