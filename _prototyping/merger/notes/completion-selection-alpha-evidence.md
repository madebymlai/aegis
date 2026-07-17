---
title: Completion Selection Alpha — Evidence and Model Boundary
date: 2026-07-17
topic: demeter-cash-merger
status: research-note
related:
  - "[[current-fixed-cash-universe-2026-07-17]]"
  - "[[finding-a-buildable-convergent-engine]]"
  - "[[the-tiered-strategy-roster]]"
tags:
  - note
  - demeter
  - merger-arbitrage
  - completion-model
  - model-selection
---

# Completion Selection Alpha — Evidence and Model Boundary

> [!abstract] Decision
> Make selection a replaceable deep module, but do not call the first replacement alpha. The strongest buildable first challenger is a **market-anchored, regularized completion model**: calibrated market-implied completion probability is the nested baseline, while a small set of point-in-time deal-card and lifecycle features may only explain residual completion odds. Promote it only if a forward-chaining out-of-sample test beats the calibrated market baseline on proper probability scores and improves the same net portfolio after costs.

The literature establishes that completion forecasting beyond a stock-spread baseline is possible in some settings. It does not establish that a model trained on large institutional deals, optionable targets, or paid news transports to a small-deal U.S. cash-merger universe. The research task is therefore not to select published coefficients. It is to build a falsifiable seam through which competing completion models can be evaluated without changing eligibility, payoff accounting, sizing, or execution.

## Keep the three economic layers separate

| Layer | What it earns | Required estimate | What would falsify it |
| --- | --- | --- | --- |
| Contractual convergence | The spread for bearing completion and break risk | Market-implied probability, payoff on completion, payoff on break, time and costs | The diversified baseline has non-positive net full-cycle payoff |
| Selection alpha | Better deal-outcome forecasts than the market baseline | A causal model probability that improves on calibrated market-implied probability | No out-of-sample improvement in proper scores or net paired returns |
| Access or capacity rent | A wider net spread for risks that a small account can bear but scaled capital cannot | Residual spread or return after controlling for completion and downside risk, liquidity and costs | Small/messy deals have no positive residual return advantage |

These are not interchangeable. A high market-implied completion probability can identify a safer spread without being alpha. A model can forecast completion better while failing to generate an executable return improvement. A small deal can have a wide spread because it is genuinely worse, not because institutions cannot exploit it.

## What has credible incremental evidence

### 1. Point-in-time structured context is the closest direct precedent

A July 2026 arXiv study constructed 1,648 public-target deals from 2022–2025 and used temporal train, validation and test splits. Its structured XGBoost baseline combined market-implied probability with 26 point-in-time fields covering deal economics, ownership, consideration, legal/process terms, bid dynamics and termination fees. On 404 held-out deals announced from February through December 2025, XGBoost improved class-balanced Brier score for positive-versus-negative outcomes from `0.199` for a Platt-calibrated market probability to `0.186`. For strict completion-versus-termination, XGBoost scored `0.164`; the authors' finetuned long-context system scored `0.126`.[^jajal]

This is the most direct evidence that structured information can add to a calibrated market baseline. It is not a ready-made Demeter model:

- The paper is a new preprint, not a replicated result.
- It excluded deals below roughly `$1 billion`, while the present access thesis concerns smaller deals.
- Its full system used 1,244 training-and-validation deals, millions of timestamped commercial documents, specialist-designed research agents and a finetuned model.
- Its structured result reports the feature set jointly; it does not prove that any one clause or milestone has portable alpha.

The paper nevertheless gives a sound benchmark shape: market probability must be an input and baseline, deal documents must be point-in-time, evaluation must split by announcement time, and probability accuracy—not classification accuracy—is the first test.

### 2. Announcement-day media text beat price information, but the source is not currently practical

Buehlmaier and Zechner trained a rolling-quarter naive Bayes classifier on announcement-day press and newswire text. Their 1999–2009 sample used 130,589 Factiva articles and 1,107 U.S. mergers. The media score predicted eventual completion out of sample and was unrelated to announcement-day stock returns. It also predicted the following twelve trading days: a one-standard-deviation increase in media-implied completion probability increased the subsequent merger-arbitrage return by about `1.2` percentage points, and excluding the lowest 28% of scores increased reported annualized alpha by `9.3` percentage points.[^media]

This is genuine evidence of information not immediately in the price, but it is a poor first adapter here. The study manually constructed 2,400 Factiva entity queries, excluded challenged deals and heavily regulated industries, and relied on a paid historical news corpus. Replacing Factiva with SEC text would create a new hypothesis, not reproduce the result.

### 3. Target options contain incremental information, but this is another market signal

Van Tassel estimated a deal-specific risk-neutral success probability from the joint target stock and option surface. In 738 cash deals with suitable options, the model produced adjusted `R²` of `34%` in outcome regressions versus `14%` for share-implied probability. Rolling monthly forecasts trained only on resolved earlier deals continued to outperform the share-implied and reduced-form option baselines through the sample.[^vantassel]

This is strong evidence that a second market can improve on the stock spread. It is not independent fundamental analysis, and it is not broadly executable for the current universe: the test conditions on targets with listed options, and small targets may have no useful surface. The later Bester–Martinez–Roşu model also reports substantially greater explanatory power than a naive stock-price probability, but its reported outcome regression averages estimated probabilities over portions of the deal's realized life; that is useful model evidence, not a causal entry rule for this prototype.[^bester]

### 4. Non-price stock reactions are a credible low-cost challenger, not yet a proven adapter

Lee studies the target's change in trading volume, bid-ask spread and return volatility during the two weeks around announcement. The combined non-price reaction predicts renegotiation, slower resolution and failure after controlling for the arbitrage spread and announcement return; a low-predicted-failure portfolio also has positive abnormal returns.[^lee]

IBKR market data could make this family relatively inexpensive to reproduce. However, the accessible paper record does not establish the same clean temporal horse race against a calibrated market probability that the 2026 structured study provides. It should be a second challenger after the model/evaluation seam exists, with entry delayed until its feature window has closed.

## What does **not** yet qualify as selection alpha

- **Raw spread or raw `q_market`.** These are the market forecast and risk premium being challenged.
- **A calibrated transformation of `q_market`.** Calibration can turn a risk-neutral or misspecified probability into a better physical forecast, but the resulting improvement is baseline repair, not independent alpha.
- **A clause by itself.** Financing conditions, termination fees, MAE provisions, go-shops and outside dates allocate negotiated risk. Contract studies find associations with completion or spread, but clauses are endogenous choices and are public at entry.[^clauses]
- **A passed shareholder vote or regulatory clearance.** These are essential state updates. Unless a model anticipates their effect before the price, reacting to them is lifecycle accounting rather than demonstrated alpha.
- **Current hedge-fund holdings.** Cao, Goldie, Liang and Petrasek find hedge funds beat a naive risk-arbitrage portfolio by `3.7%` annually, but attribute the advantage to managing break downside rather than predicting or influencing completion.[^cao]
- **Small size.** The classic U.S. limited-arbitrage evidence reports higher, not lower, returns with target size after controlling for its completion-risk proxy; it interprets size as dollar selling pressure.[^baker] A small-deal capacity rent remains a separate empirical claim.

## The minimal deep interface

The caller should know only that a selection engine forecasts one immutable batch of causally complete deal snapshots. It should not know how features are fetched, normalized, cached, calibrated or combined. The batch keeps one fitted artifact and training cutoff atomic across the monthly cross-section and allows vectorized implementations without widening the interface.

```python
class CompletionSelectionEngine(Protocol):
    identity: SelectionEngineIdentity

    def forecast(
        self,
        cases: tuple[CompletionCase, ...],
    ) -> tuple[CompletionForecast, ...]: ...
```

`CompletionCase` should contain the stable domain inputs already owned by the event and valuation layers: event identity, causal timestamps, contractual cash payoff, current executable mark, market-implied baseline and modeled break payoff. It must not expose a growing bag of model-specific columns or size/liquidity variables belonging to the separate access-rent test.

`SelectionResult` and its immutable assessments should jointly record:

- one batch-atomic `engine_id`, model-artifact identity and training cutoff;
- `as_of` and latest feature timestamp;
- raw and calibrated market baseline probabilities;
- model completion probability;
- completion, break and gross expected payoff under the same payoff assumptions, with portfolio costs recorded separately;
- an eligibility/rank score and compact reason codes.

The deep implementation owns point-in-time feature assembly, missing-data policy, fitted artifact loading and forecast validation. Position sizing consumes assessments but remains outside the selection engine. That keeps a selector swap from silently changing name caps, break-loss limits, whole-share sizing or execution costs.

Two implementations are needed immediately:

1. `MarketImpliedSelectionEngine`: the control. It uses only the calibrated market probability and the existing payoff model.
2. `ResidualCompletionSelectionEngine`: the future challenger. It begins at the calibrated market log-odds and may learn only a residual adjustment from causal features.

A useful first statistical form is deliberately nested:

$$
\operatorname{logit}(p_{model,i,t})
=
\operatorname{logit}(p_{market,cal,i,t})
+ \beta^\top x_{i,t}.
$$

With all coefficients zero, the challenger collapses exactly to the baseline. Regularization and a short, preregistered feature list make it harder for a small sample to manufacture an apparent improvement. A later XGBoost or text model can implement the same interface without touching book construction.

## First realistic feature adapter

Start with a **deal-card plus lifecycle residual model**, because its inputs are available from timestamped SEC filings and it most closely resembles the structured challenger that beat the calibrated market baseline in the 2026 temporal test.[^jajal]

Use only fields that can be reconstructed at the forecast timestamp:

| Feature family | First-pass fields | Source and timestamp rule |
| --- | --- | --- |
| Contract commitment | financing condition; buyer and target termination fee divided by deal value; MAE exit right; tender versus vote; outside date | Definitive agreement or proxy; available at SEC acceptance time |
| Approval burden | target vote required; buyer vote required; number/type of named regulatory regimes; controlling-holder support | Agreement/proxy and beneficial-ownership filings; never use later ownership snapshots for an earlier forecast |
| Lifecycle progress | vote result; regulatory clearance; tender acceptance; amendment; outside-date extension | Filing or regulator publication timestamp; tradable no earlier than the next market decision point |
| Timing | deal age; days to company-guided close; days to outside date; guidance delay or acceleration | Use only guidance published by the as-of date; absence is a separate state |
| Financing state | committed financing; financing update; acquirer distress or credit deterioration | Filed commitment documents and point-in-time market data |

Do not start with free-form LLM judgments. First prove that deterministic extraction and a regularized nested model add information. Do not include target size or liquidity in this first completion model: reserve them for the separate access-rent test, so a result cannot be relabeled after the fact.

The next adapter should add Lee-style announcement microstructure only after ten trading days of causal observations. The option-surface adapter comes later and should return `unavailable`, not a guessed probability, when the target lacks a reliable surface.

## Falsification protocol

### Probability test

1. Freeze a historical deal census that includes completed, broken, renegotiated and delisted targets.
2. Split by **announcement date**, not by rows. Train on the past, calibrate on a later validation block and evaluate once on a later untouched block.
3. Generate forecasts at fixed causal landmarks, initially Day 1 and monthly thereafter. If a feature requires ten days, its adapter cannot issue an earlier forecast.
4. Fit the raw-market calibrator only on previously resolved training deals.
5. Compare raw market, calibrated market and challenger on standard Brier score, class-balanced Brier score and log loss. Cluster or bootstrap by deal because repeated forecast dates are not independent.
6. Require a negative paired loss difference with a confidence interval excluding zero. Also report calibration and discrimination separately; a model that merely makes probabilities more extreme is not enough.

The existing `100` resolved / `10` adverse threshold is enough to test data plumbing and expose gross failure. It is not persuasive evidence of completion alpha. The closest direct structured precedent trained on more than 1,200 deals and evaluated on 404 held-out deals.[^jajal] Until the adverse count and holdout are materially larger, all challenger outputs remain shadow forecasts.

### Economic test

Run baseline and challenger through the **same** universe, break-value model, allocation, whole-share rounding and cost assumptions. Compare complete return streams, not only selected-deal hit rates. At minimum report:

- net return and certainty-equivalent difference;
- maximum drawdown and realized break loss;
- turnover, commissions, spread/slippage and idle cash;
- paired contribution when combined with the persistent-crisis responder;
- performance conditional on broad market drawdowns.

This matters because historical manager evidence suggests downside selection can be more valuable than completion classification.[^cao] A later `BreakValueModel` should therefore be replaceable independently of `SelectionEngine`; completion probability and loss given break are two different forecasts.

### Access-rent test

Do not bake the small-book thesis into `ResidualCompletionSelectionEngine`. After estimating completion and break risk, test whether residual net return or residual spread is related to deal size and liquidity:

$$
r_{net,i} - \widehat r_{risk,i}
=
\alpha + \gamma_1 \log(\text{deal value}_i)
+ \gamma_2 \text{liquidity}_i
+ \gamma_3 \text{retail costs}_i + \varepsilon_i.
$$

The claim earns support only if smaller or less institutionally scalable deals retain a positive net advantage after risk and costs, with stable out-of-sample behavior. The Baker–Savaşoğlu result gives the opposite size sign in an older U.S. sample, so the sign must be learned rather than assumed.[^baker]

## Recommended sequence

1. Implement the tiny `CompletionSelectionEngine.forecast` seam and preserve the frozen market policy as the control.
2. Persist both raw and past-only calibrated market probabilities; calibration is baseline maintenance.
3. Extend the historical ledger with causal deal-card, lifecycle and outcome fields.
4. Fit the nested regularized residual model only after the historical census is sufficiently broad; log every shadow forecast before resolution.
5. Add the ten-day microstructure adapter as a second independent challenger.
6. Evaluate access rent separately using size, liquidity and actual retail costs.
7. Promote no model until both the probability and paired economic tests pass out of sample.

> [!warning] Current conclusion
> There is a credible path to searching for selection alpha, not evidence that this prototype already has it. The present market-implied book is layer 1. The first model adapter is an experiment whose null hypothesis is that all residual coefficients are zero.

## Implemented seam and live diagnostic

The prototype now implements the batch interface above. `CashMergerSelector` alone owns payoff inversion, hard tradability filters, engine-response validation, ranking, break-loss sizing, whole-share rounding and modeled costs. The default `market-implied-q70` engine returns the market probability unchanged, so its recorded edge is exactly zero. The selection result persists one batch-atomic engine identity, model artifact and training cutoff; each assessment records causal timestamps, raw and calibrated-market slots, model probability, uncertainty bound, expected payoffs and edge. Deals that cannot reach the engine receive a typed exclusion reason rather than disappearing. An injected challenger is shadow-only by default: its forecasts are recorded, but `market-implied-q70` still controls the decision until the caller explicitly grants qualified-challenger authority after the falsification protocol passes.

The 2026-07-17 real-data run produced four valid market assessments and 16 `market_probability_undefined` exclusions; none of the four cleared `q_market >= 70%`. This is not evidence for or against a residual completion model. It says the current fixed 175-day discounting and beta-adjusted break-value specification fails to form the mandatory baseline for most live deals. Baseline payoff inversion must be repaired and frozen before fitting the residual challenger.

[^jajal]: Hinal Jajal et al., [“Global Merger-Arbitrage Forecasting with Language Models”](https://arxiv.org/html/2607.09921v1), 2026. See Sections 3–5 and Appendix A.2 for the temporal splits, market baseline, structured features and held-out Brier scores.
[^media]: Matthias M. M. Buehlmaier and Josef Zechner, [“Financial Media, Price Discovery, and Merger Arbitrage”](https://doi.org/10.1093/rof/rfaa037), *Review of Finance* 25(4), 2021; the [author manuscript](https://d-nb.info/1117648273/34) contains the rolling naive Bayes construction and tables.
[^vantassel]: Peter Van Tassel, [“Merger Options and Risk Arbitrage”](https://www.newyorkfed.org/medialibrary/media/research/staff_reports/sr761.pdf), Federal Reserve Bank of New York Staff Report 761, 2016, especially Table 2 and Figure 8.
[^bester]: C. Alan Bester, Victor H. Martinez and Ioanid Roşu, [“Option Prices and the Probability of Success of Cash Mergers”](https://people.hec.edu/rosu/wp-content/uploads/sites/43/2023/02/mergers_JFEC_2023.pdf), *Journal of Financial Econometrics*, 2023.
[^lee]: Sangwon Lee, [“Failure Risk, Risk Arbitrage, and Outcomes of Mergers and Acquisitions”](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2941200), working paper, 2020.
[^clauses]: John C. Coates IV, Darius Palia and Ge Wu, [“Are M&A Contract Clauses Value Relevant to Bidder and Target Shareholders?”](https://law-economic-studies.law.columbia.edu/sites/law-economic-studies.law.columbia.edu/files/content/docs/coates_palia_wu_are_ma_contract_clauses_value_relevant_to_bidder_target_shareholders_rev_2019_02_11.pdf), 2019. For more precise outcome definitions and the endogeneity of break mechanisms, see Dorothy S. Lund and Morgan Ricks, [“How Deals Die”](https://lawreview.uchicago.edu/sites/default/files/2026-06/Lin_%26_Ricks_ART%20%20-%20FINAL.pdf), *University of Chicago Law Review*, 2026.
[^cao]: Charles Cao, Bradley A. Goldie, Bing Liang and Lubomir Petrasek, [“What Is the Nature of Hedge Fund Manager Skills? Evidence from the Risk-Arbitrage Strategy”](https://doi.org/10.1017/S0022109016000387), *Journal of Financial and Quantitative Analysis* 51(3), 2016.
[^baker]: Malcolm Baker and Serkan Savaşoğlu, [“Limited Arbitrage in Mergers and Acquisitions”](https://www.hbs.edu/ris/Publication%20Files/arbitrage_af05900b-acd4-44db-8210-70a9fbc3cf6c.pdf), *Journal of Financial Economics* 64, 2002.
