---
title: Cash-merger completion probability model
date: 2026-07-16
tags:
  - demeter
  - convergence
  - merger-arbitrage
  - research-design
---

# Cash-merger completion probability model

Related: [[cash-merger-breadth-standalone-or-sub-engine]], [[massive-data-for-cash-merger-convergence]], [[finding-a-buildable-convergent-engine]], [[the-tiered-strategy-roster]].

> [!decision]
> There is no trustworthy free `completion_probability` field to consume. Massive and SEC supply point-in-time evidence and outcome labels; Demeter must estimate a calibrated probability, or decline the trade. The market-implied probability is the mandatory baseline, not the alpha.

## Economic baseline

For a cash offer with current target price $P_t$, discounted cash consideration $O_t$, and estimated break value $B_t$:

$$
q_{mkt,t}=\frac{P_t-B_t}{O_t-B_t}.
$$

This is a state-price approximation, not a forecast guaranteed to equal the physical completion probability. Samuelson and Rosenthal establish that target-price movements contain information about tender-offer success; later time-varying work similarly finds target and bidder price movements informative.[^samuelson][^barone]

Demeter should estimate only a residual probability update:

$$
\operatorname{logit}(q_{model,t})=
\operatorname{logit}(q_{mkt,t})+f(X_t).
$$

If $f$ does not improve strictly out-of-time Brier score and log loss over $q_{mkt}$, set $f=0$ and claim no selection edge.

## Free point-in-time training data

| Need | Source | Use |
| --- | --- | --- |
| Filing discovery and issuer identity | Massive EDGAR Index or SEC EDGAR | CIK, ticker, accession, form and filing date |
| Agreement and amendment text | Massive ticker/CIK-filtered 8-K Text; SEC exhibits | consideration, financing conditions, outside date, termination fees, regulatory and vote conditions, amendments |
| Completion and termination labels | Target 8-K filings and delisting filings | one terminal label per deal |
| Tender-offer state | SEC Schedule TO and SC 14D-9 filings | bidder ownership, board response, extensions and tender results |
| Regulatory milestones | FTC/DOJ merger-review and early-termination records | clearance, second-request and challenge state where publicly observable |
| Prices | Massive point-in-time/delisted aggregates | spread, unaffected price, volatility, liquidity and price-path evidence |

Massive's 8-K Text endpoint accepts ticker, CIK, form type and filing-date filters, but is an early-access beta; the adapter must preserve the source accession and fail closed if history is unavailable.[^massive]

The FTC explains that HSR review can end through early termination, expiry of the waiting period, a second request, consent resolution or challenge. These are state transitions, not one static `regulatory_risk` flag.[^ftc]

## First credible model

Use one row per deal at announcement for the first model; do not duplicate long-running deals into hundreds of pseudo-independent daily observations.

1. Restrict the universe to definitive, all-cash acquisitions of listed U.S. common shares.
2. Label completion versus termination/repricing from later filings.
3. Fit a penalized logistic residual model with `logit(q_market)` as an offset.
4. Use a chronological expanding-window evaluation and calibrate only on past data.
5. Score probability quality with Brier score, log loss and reliability curves; accuracy is inappropriate for rare breaks.
6. Trade only when the conservative lower confidence bound for $q_model-q_market$ covers trading costs and model uncertainty.

Initial structured features:

- tender offer versus shareholder-vote merger;
- friendly/hostile board response and competing bidder;
- bidder toehold or voting agreement;
- financing condition and acquirer funding capacity;
- target and acquirer termination fees relative to transaction value;
- regulatory jurisdictions, observable HSR state and public challenge;
- outside date, elapsed time and extensions;
- offer amendments or reductions;
- consideration premium and market-implied probability;
- target volatility, liquidity and post-announcement price path.

Walkling's logistic study finds success related to obtainable-share variables such as bid premium, solicitation fees and bidder ownership, while opposition and competing bids reduce success.[^walkling] A later 4,000-deal risk-model study reports out-of-sample improvement from a statistical success model, establishing the right validation target but not providing a downloadable live probability feed.[^daul]

## Portfolio consequence

A probability model does not make a sparse deal safe. Mitchell and Pulvino's diversified simulation capped each position at 5% and put unused capital in the risk-free asset during low deal flow; their broad 4,750-deal evidence also shows merger arbitrage behaves like short index puts in severe market declines.[^mitchell]

Therefore:

- use an absolute per-deal loss budget, not only a relative `1.5/N` cap;
- hold cash when breadth is insufficient;
- size from expected break contribution under $q_model$, including probability uncertainty;
- do not promote the model until the paired [[the-tiered-strategy-roster|floor]] utility is positive on untouched later deals.

## Immediate recommendation

Do not search for a vendor field to replace `0.90`. Build the labeled event tape first. The first deliverable is a market-baseline model whose prediction is exactly $q_{mkt}$; the second is a small, regularized residual model. If the residual cannot beat the market baseline out of time, Demeter may still test a broadly diversified merger-risk premium, but it has no deal-selection alpha.

## Prototype result — 2026-07-16

The Massive-only throwaway prototype queried documented JSON endpoints, not HTML:

- 3,000 `merger_agreement` disclosure rows yielded only 35 unique, conservatively parsed fixed-cash candidates through 2025-12-31.
- A time-spread 24-candidate pass produced nine observations satisfying target-price history, an observable lifecycle resolution and $B<P<O$; the 11 omitted candidates added only five more provisional observations.
- The optimistic upper bound was therefore 14 observations, far below the predeclared 15-deal initial training window and with too few failures for chronological held-out predictions.
- A strict RVNC replay correctly observed $6.66 \rightarrow 3.10 \rightarrow 3.65$ and completion at $3.65$. Receipt of the original $6.66$ consideration is labeled a repricing failure, not a completion success.
- BATL supplied a genuine break observation with $q_{mkt}\approx0.52$; the old fixed $q=0.90$ was an unsupported override.

No residual model was fitted and no probability was authorized for the strategy. The blocker is historical labeled breadth, not the ability of Massive 8-K Text to represent amendments. A future attempt needs the complete cohort over materially longer history and stricter structured extraction of target identity, original consideration, amendments and terminal outcomes.

[^samuelson]: William Samuelson and Leonard Rosenthal, “Price Movements as Indicators of Tender Offer Success,” *Journal of Finance* 41(2), 1986, pp. 481–499. DOI: [10.1111/j.1540-6261.1986.tb05050.x](https://doi.org/10.1111/j.1540-6261.1986.tb05050.x).
[^barone]: Giovanni Barone-Adesi and Giuseppe Corvasce, “The Time-Varying Prediction of Successful Mergers,” Swiss Finance Institute Research Paper 09-22. [RePEc record](https://ideas.repec.org/p/chf/rpseri/rp0922.html).
[^massive]: Massive, [“8-K Text”](https://massive.com/docs/rest/stocks/filings/8-k-text), accessed 2026-07-16.
[^ftc]: Federal Trade Commission, [“Premerger Notification and the Merger Review Process”](https://www.ftc.gov/advice-guidance/competition-guidance/guide-antitrust-laws/mergers/premerger-notification-merger-review-process), accessed 2026-07-16.
[^walkling]: Ralph A. Walkling, “Predicting Tender Offer Success: A Logistic Analysis,” *Journal of Financial and Quantitative Analysis* 20(4), 1985, pp. 461–478. [Drexel record](https://researchdiscovery.drexel.edu/esploro/outputs/journalArticle/Predicting-Tender-Offer-Success-A-Logistic/991021881391504721).
[^daul]: Stéphane Daul, “Extensions of the Merger Arbitrage Risk Model,” 2008. [SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1548411).
[^mitchell]: Mark Mitchell and Todd Pulvino, “Characteristics of Risk and Return in Risk Arbitrage,” *Journal of Finance* 56(6), 2001, pp. 2135–2175. [Paper](https://andreisimonov.com/N4106/pdf/MitchellPulvinoJFDec2001.pdf).
