# Terminal out-of-sample practice for fixed-rule trading strategies

**Date:** 2026-07-21  
**Question:** Do practitioners reserve a terminal out-of-sample period when selecting fixed parameters for non-ML trading strategies, and does Aegis Future-in-Past Replay need one?

## Verdict

Yes—**if Aegis intends to claim that its selected Candidate has been tested out of sample**, it needs a terminal period that did not participate in Candidate ranking. The established name is a **terminal out-of-sample (OOS) test** or **forward test**, not walk-forward analysis and not “future-in-past” in external-facing methodology.

The distinction is fundamental:

- Replaying every fixed Candidate causally across Development establishes that each Candidate's *trades* used only information available at the time.
- Ranking those Candidates on the whole Development period makes the *selection* in-sample: the winning parameters were learned with hindsight over that period.
- Replaying the frozen winner on the later untouched period is the first historical result in which both the trading decisions and the parameter choice were fixed before the scored observations.

If Aegis removes the terminal OOS phase, the Development replay remains a valid historical simulation and parameter comparison, but it must not be presented as validation or evidence of post-selection generalization. QuantConnect states this directly: after parameters are optimized, that historical period is in-sample; it recommends optimizing on older history and testing the chosen values on more recent history, or using walk-forward optimization instead. [QuantConnect parameter optimization documentation](https://www.quantconnect.com/docs/v2/writing-algorithms/optimization/parameters)

## What practitioners actually use

This protocol is present in mainstream tooling for deterministic trading rules, not only in machine learning:

- QuantConnect supports an organization-level recent OOS holdout that ordinary Development backtests cannot access, specifically leaving data for testing after Development. [QuantConnect backtesting documentation](https://www.quantconnect.com/docs/v2/cloud-platform/backtesting/getting-started)
- MetaTrader 5 calls the same design **forward testing**: optimize Expert Advisor parameter combinations on the first part, then rerun selected results on the latest, non-optimized part. Its built-in choices reserve one half, one third, one quarter, or a custom terminal period. [MetaTrader 5 Strategy Tester documentation](https://www.metatrader5.com/en/terminal/help/algotrading/strategy_optimization)
- The CFA Institute Research Foundation describes OOS testing as fitting on the in-sample data and then running a final test on held-out data; it explicitly identifies the most recent historical period as a possible holdout. [Ronald Kahn, *The Future of Investment Management*, pp. 61–62](https://rpc.cfainstitute.org/-/media/documents/book/rf-publication/2018/future-of-investment-management-kahn.pdf)

Those sources describe the shape Aegis needs: an older optimization/development period followed by a newer, non-optimized test period with frozen rules.

## Why this is not walk-forward optimization

Walk-forward optimization repeatedly fits parameters on trailing historical windows and applies the newly selected parameters going forward. QuantConnect defines it as periodically adjusting strategy logic or parameters from a trailing window; its example reruns a parameter search monthly and updates the strategy to that session's winner. [QuantConnect walk-forward optimization documentation](https://www.quantconnect.com/docs/v2/writing-algorithms/optimization/walk-forward-optimization)

TradeStation likewise defines walk-forward analysis as multiple runs, each comparing optimizer-seen in-sample data with unseen OOS data. [TradeStation Walk-Forward documentation](https://help.tradestation.com/10_00/eng/tradestationhelp/optimize/walk_forward.htm)

Therefore:

| Protocol | When parameters are selected | Parameters through history | What it answers |
|---|---|---|---|
| Fixed Candidate backtest | Before simulation, but possibly chosen after inspecting the same history | Fixed | How this rule would have traded historically |
| Terminal OOS / forward test | Once on older Development data | Fixed for the OOS period | How the frozen selection performed on later unseen history |
| Walk-forward optimization | Repeatedly from each trailing training window | May change each forward period | How a periodic re-optimization policy would have performed |
| Paper/live test | Before genuinely arriving market data | Fixed unless the live policy changes it | How the implementation behaves prospectively, including live operational effects |

Aegis's requirement that one parameter set remain consistent means walk-forward optimization is not the target protocol. Running the fixed winner over rolling reporting windows would still be one continuous fixed-parameter backtest; the windows would not make it WFA or add OOS independence.

## Do practitioners keep parameters static?

There is no single industry-wide policy. Practitioners use both fixed methodologies and explicitly adaptive ones, but **updating signals or positions is not the same operation as re-optimizing strategy parameters**.

Published systematic methodologies provide clear examples of long-lived parameter rules:

- AQR's updated Time Series Momentum factor continues to use a 12-month signal and one-month holding period while publishing new monthly returns. The observations and positions advance each month; the published lookback and holding-period parameters do not get reselected from a grid each month. [AQR Time Series Momentum data set](https://www.aqr.com/Insights/Datasets/Time-Series-Momentum-Factors-Monthly)
- MSCI's July 2025 Momentum Index methodology fixes its signal construction at equal parts 6-month and 12-month risk-adjusted momentum. The index is rebalanced quarterly and can rebalance conditionally after a volatility trigger. Current prices, volatility estimates, constituents, and weights therefore change under a documented formula; the 6/12-month signal parameters are not re-optimized at each review. [MSCI Momentum Indexes Methodology](https://www.msci.com/indexes/documents/methodology/2_MSCI_Momentum_Indexes_Methodology_20250725.pdf)
- Man AHL reports that its family of moving-average crossover speeds, or variations of them, has been used for about three decades. Its stated response to there being no universally perfect trend speed is to diversify across predefined speeds, with positions volatility-scaled, rather than repeatedly choose the most recent backtest winner. [Man AHL, “The Need for Speed in Trend-Following Strategies”](https://www.man.com/insights/need-for-speed-trend-following)

Periodic re-optimization also exists, but it is an explicit trading policy. QuantConnect's WFO example searches a fixed Candidate grid on a trailing year at the beginning of every month and replaces the strategy's EMA parameters with that session's winner. QuantConnect also warns that increasing optimization frequency increases the chance of overfitting. [QuantConnect walk-forward optimization documentation](https://www.quantconnect.com/docs/v2/writing-algorithms/optimization/walk-forward-optimization)

Deployed systematic methods are not necessarily frozen forever. Man AHL describes continuous monitoring, possible reevaluation after alpha degradation, and comparisons between old and updated model vintages. This is evidence of governed research and model replacement, not evidence that every portfolio rebalance automatically reranks a parameter grid. That distinction is an inference from Man's description of monitoring and version changes. [Man AHL, “Conviction in the Systematic Hunt for Alpha”](https://www.man.com/insights/conviction-the-systematic-hunt)

The operations should remain separate in Aegis:

| Operation | Example | Parameter policy |
|---|---|---|
| Signal/state update | Recalculate momentum or volatility from the newest causal observations | Formula parameters stay fixed |
| Portfolio rebalance | Trade toward targets generated by the current signal | Formula parameters stay fixed |
| Fixed multi-speed model | Combine several predeclared trend horizons | Blend definition stays fixed |
| Walk-forward re-optimization | Rerank a grid on a trailing window and install its winner | Parameters may change at each scheduled fit |
| Governed model revision | Research, validate, and deploy a new version | Old version is replaced through a separate decision |

For Aegis's deterministic non-ML Strategies, the fixed policy is the better match: freeze one Candidate for the entire evidence-generating Run, while continuing to update causal indicators and rebalance positions normally. A future model improvement should create a new version and new validation lineage. If Aegis later supports scheduled re-optimization, that must be modeled as a different Strategy policy and tested end-to-end as WFO; it must not be smuggled into replay as an implementation detail.

## The holdout is necessary but not sufficient

A single terminal holdout does not eliminate backtest overfitting. Bailey, Borwein, López de Prado, and Zhu find that ordinary holdout methods can be unreliable for investment backtests and propose combinatorially symmetric cross-validation to estimate the probability of backtest overfitting. [Bailey et al., “The Probability of Backtest Overfitting”](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2326253)

The same authors show that trying more alternative strategy configurations increases the probability of obtaining impressive simulated performance through overfitting. [Bailey et al., “Pseudo-Mathematics and Financial Charlatanism”](https://scholarworks.wmich.edu/math_pubs/40/)

This creates two operational requirements for Aegis:

1. The OOS result must not feed Candidate ranking, parameter changes, Strategy changes, cost-model changes, or acceptance thresholds. If it does, that period has become Development data for the next iteration.
2. Aegis should retain separate controls or evidence for Candidate-search breadth, parameter sensitivity, and repeated trials. A terminal OOS result complements those controls; it does not replace them.

The winner is the only decision-bearing OOS test. Replaying predeclared median and worst representatives can diagnose whether Development ranking has any OOS ordering signal, and MetaTrader similarly forward-tests a preselected fraction of its best optimization runs. But Aegis must not promote a different representative after viewing OOS results; doing so would select on the holdout. [MetaTrader 5 Strategy Tester documentation](https://www.metatrader5.com/en/terminal/help/algotrading/strategy_optimization)

## Recommended Aegis contract

Keep `held_out_start` and describe the phases using established terms:

```text
Development / in-sample
    causally replay all fixed Candidates
    calculate one full-period Metric set per Candidate
    rank once and freeze the selected Candidate and diagnostic representatives

Terminal out-of-sample / forward test
    replay only the frozen set on later history
    use preceding rows only for causal indicator warmup
    start a fresh portfolio at the boundary
    report OOS Metrics without reranking or adapting
```

This is a **fixed-split terminal OOS protocol**, not WFA. “Future-in-Past Replay” can remain the Aegis module name for its causal simulation mechanics, but the Run evidence should label Development Metrics as in-sample and Held-out Metrics as terminal OOS.

The holdout should be optional only for exploratory Runs that make no validation claim. For an optimization result eligible to be called validated, it should be required. There is no universally correct fraction in the practitioner sources: MetaTrader exposes several fractions and a custom boundary, while QuantConnect lets organizations choose a duration. Aegis should therefore require an explicit timestamp rather than invent a universal percentage. [MetaTrader 5 Strategy Tester documentation](https://www.metatrader5.com/en/terminal/help/algotrading/strategy_optimization), [QuantConnect backtesting documentation](https://www.quantconnect.com/docs/v2/cloud-platform/backtesting/getting-started)

After historical OOS validation, paper trading remains a distinct and stronger prospective stage. QuantConnect defines paper trading as running real-time data through the algorithm with fictional capital and recommends it before real-money deployment; its reconciliation documentation also shows why historical and live execution can diverge through data timing, fills, costs, and brokerage behavior. [QuantConnect paper-trading documentation](https://www.quantconnect.com/docs/v2/cloud-platform/live-trading/brokerages/quantconnect-paper-trading), [QuantConnect live reconciliation documentation](https://www.quantconnect.com/docs/v2/cloud-platform/live-trading/reconciliation)
