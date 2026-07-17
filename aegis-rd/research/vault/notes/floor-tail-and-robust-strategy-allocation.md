---
title: "Floor, Tail, and Robust Strategy Allocation"
date: 2026-07-17
topic: strategy-roster design and robust allocation across heterogeneous sleeves
distilled-into:
tags:
  - article
---

# Floor, Tail, and Robust Strategy Allocation

> [!abstract] One-line takeaway
> Keep the Floor/Target/Expansion roster, but do not mistake it for an optimizer: require distinct economic jobs and bad-state diversification first, allocate ordinary sleeves with slow static risk budgets and a shrunk covariance estimate, size the tail by coverage-versus-carry, and treat “many uncorrelated [[what-is-a-strategy|strategies]]” as the Expansion tier—not as a replacement for crisis design.

## The answer is a hybrid, not a choice

The question “Floor plus tail, or a bunch of uncorrelated strategies?” mixes two different decisions. [[the-tiered-strategy-roster]] is a **roster policy**: it says which failures the book must survive. An allocator says how much of each accepted sleeve to hold. Neither can replace the other.

The Floor/Target/Expansion design is directionally right because it begins with economic jobs rather than a correlation matrix:

- the **Floor** combines an ordinary-market return engine with a responder to persistent dislocations;
- the **Target** fills only the responder's residual speed gap;
- **Expansion** adds return sources that are independent of both.

The improvement is to make low correlation a gate on every addition, including correlation in bad states, while retaining those job constraints. The robust destination is therefore **a floor plus a small residual tail plus an expanding set of genuinely independent strategies**. It is not a permanent two-sleeve book, and it is not an unconstrained collection of streams selected from one benign-period correlation matrix.

## Why unconditional “uncorrelated” is not enough

Correlation is a useful description of a sample, not a durable economic property. Longin and Solnik find that international equity correlations rise in bear markets but not in bull markets; Ang and Chen independently find that US stock portfolios are much more correlated with the market during downside moves, especially extreme ones.[^longin][^ang] This is the exact state in which a book needs diversification most.

Strategy labels do not fix the problem. Several apparently different premia can all be ways of selling insurance. Lempérière et al. find a broad relationship between excess return and negative tail skew across equity, credit, carry, and short-volatility strategies; trend is the important positive-skew exception.[^lemp] A value sleeve, a carry sleeve, and a liquidity-provision sleeve can have modest full-sample correlation yet share the same deleveraging or funding-liquidity failure. Conversely, trend's lookback-straddle-like payoff is economically different from ordinary beta and many convergent premia, which is why it can diversify persistent directional crises rather than merely look different in normal data.[^fung]

Common implementation can reconnect supposedly separate signals. Khandani and Lo's reconstruction of the August 2007 quant unwind shows how common exposures and forced deleveraging produced simultaneous losses across long/short equity strategies.[^quantunwind] It is a concrete warning against counting backtests instead of tracing counterparties, crowding, financing, and exit liquidity.

So the acceptance test for a new sleeve should be stronger than low full-sample correlation:

1. What pays it, and what causes that mechanism to fail?
2. Does it add a job or an independent risk axis the book lacks?
3. Is its dependence still acceptable on the Floor's worst days, in crisis windows, and under plausible common-factor shocks?
4. Does it improve the whole book after turnover, financing, and wrapper costs?

This is the useful content of the “floor” concept. It prevents a covariance estimator from declaring five versions of the same short-tail trade to be five diversifiers.

## No allocator dominates; complexity must earn its inputs

DeMiguel, Garlappi, and Uppal compared fourteen optimizing rules across seven datasets. None consistently beat `1/N` out of sample on Sharpe, certainty-equivalent return, and turnover; their calibration required roughly 3,000 months for a 25-asset mean-variance optimizer to beat the naive benchmark.[^demiguel] The result does not make equal capital optimal. It says an allocator that estimates more weakly identified quantities must clear a very high bar.

For heterogeneous strategy sleeves, the practical ranking is:

| Method | What it estimates | Strength | Main failure | Role in Aegis |
| --- | --- | --- | --- | --- |
| Equal capital (`1/N`) | Nothing | Stable, transparent benchmark | A high-volatility sleeve dominates risk | Mandatory challenger, not the default |
| Inverse volatility | Each sleeve's volatility | Stable; becomes ERC when correlations are effectively uniform | Ignores clusters and bad-state dependence | Strong baseline for a small, near-orthogonal roster |
| ERC / risk budgeting | Volatility and covariance | Expresses operator risk shares without estimating returns | Raw correlations are noisy; variance misdescribes convex sleeves | Default for ordinary Floor/Expansion sleeves, with shrinkage and caps |
| HRP | Covariance plus an estimated cluster tree | Avoids covariance inversion and can help when many assets have real hierarchy | Tree instability; weak benefit at small `N`; grouping can be economically false | Do not estimate the roster's hierarchy; use declared economic groups |
| Minimum variance | Covariance, often its inverse | Directly targets low variance | Concentration and estimation-error amplification; can zero the crisis sleeve | Challenger only, with shrinkage and hard bounds |
| Mean-variance / max Sharpe | Covariance and expected returns | Optimizes the desired quantity in a known world | Expected-return error dominates and weights become unstable | Exclude from the live sleeve allocator |
| CVaR/skew/tail optimizer | Sparse tail observations and higher dependence | Can encode the objective directly | Rare-event estimation error is worse than covariance error | Use scenarios and coverage constraints instead of live optimized weights |

ERC is a defensible middle ground. Maillard, Roncalli, and Teiletche show that equal-risk-contribution portfolio volatility lies between minimum variance and equal weight and characterize ERC as a minimum-variance-like portfolio with a diversification constraint.[^erc] With near-uniform correlations, ERC collapses toward inverse volatility. That makes **diagonal risk budgeting the serious baseline** for a roster deliberately built to be orthogonal—not an unsophisticated straw man.

Full covariance is still useful, but the raw sample covariance should not be trusted literally. Ledoit and Wolf show that shrinking the sample covariance matrix reduces the estimation error that most disrupts portfolio optimizers; Jagannathan and Ma show that even simple weight constraints help because they act like covariance shrinkage.[^lw][^jm] For Aegis, the robust form is therefore a shrunk covariance feeding bounded risk budgets, with slow updates and explicit group caps. Any extra performance from the off-diagonal terms must beat the diagonal allocator out of sample after turnover.

HRP does not solve a pressing Aegis problem. López de Prado's original HRP method is valuable when covariance is singular or the investable universe contains a genuine hierarchy, and its original simulations beat traditional risk parity and the Critical Line Algorithm on out-of-sample variance.[^hrp] But Aegis has a small number of semantically distinct sleeves and already knows their economic groups. Estimating a dendrogram from a short return history would throw away that stronger information. Recent real-world comparisons also find that `1/N` can beat HRP across their experimental settings, reinforcing that HRP is a hypothesis rather than a universal upgrade.[^hrpcheck] The part worth keeping is top-down group budgeting; the part to avoid is letting an unstable tree redefine the groups.

## Floor and tail need different sizing rules

The ordinary sleeves can be allocated by risk contribution. The tail cannot be treated as merely another volatile return stream.

A variance allocator observes a standing tail sleeve's high volatility and gives it little capital, even though the sleeve was purchased for payoff at a specific stress attachment. In calm samples it can also observe persistent bleed and optimize the sleeve toward zero. Neither result answers the actual question: how much liquidity should the hedge deliver in the gap before trend can react, and how much annual carry is the book willing to pay for it?

The current tiering already contains the better rule. Size the Target by **coverage at a defined shock, subject to an annual carry budget and reliability/capacity limits**; then pass only its capped risk share into the book-level plumbing. Israelov's evidence explains why the cap should be small: a standing protective-put program is generally less effective per unit of expected return than simply reducing the risky exposure, except when the purchase and maturity happen to surround the sudden crash.[^puts] AQR's put-versus-trend comparison makes the complementary timing clear: puts are best at abrupt gaps, while trend is better suited to drawn-out bears.[^puttrend]

This means the Target is not automatically mandatory. It earns a slot only if the observed fast-gap shortfall is material and an available instrument supplies enough net coverage per unit of bleed. If not, the honest alternatives are more persistent-crisis trend, lower gross exposure, or a reliable pre-existing defensive factor—not manufacturing a costly “tail” label. The Target is a **residual hedge**, not the foundation of the book.

The Floor also should not be optimized to a trailing skew target. Higher moments are tail-sample fragile, and the existing Aegis re-validation already found a live skew constraint could become infeasible when both poles were temporarily concave. The stronger design is the one now recorded in the Trader ADR: fixed conviction/risk shares deliver the intended shape by construction; realized skew is observed and routed back to RD calibration rather than chased live. This is consistent with using the roster as a prior that the short sample is not allowed to erase.

## Volatility and drawdown overlays are controls, not alpha

A book-level volatility ceiling is compatible with the static roster because it measures the amount of risk being carried rather than forecasting which sleeve will win. It should not be justified as a guaranteed Sharpe enhancement. Cederburg et al. test 103 equity strategies and find that volatility-managed versions do not systematically outperform directly; implementable out-of-sample variants generally have lower Sharpe and certainty-equivalent returns because the relevant relationships are structurally unstable.[^cederburg] The robust benefit is risk containment when volatility rises, which supports Aegis's current **down-only ceiling** rather than leverage in calm periods.

A gradual drawdown de-lever can be retained as a second, path-dependent safety layer, but it pays its premium during V-shaped recoveries. The purpose is survival and a thinner left tail, not return timing. It should be monotone, capped, slow to recalibrate, and tested explicitly on crash-and-reversal sequences.

## Recommendation for Aegis

Keep the current architecture, but narrow the claim. Floor/Target/Expansion is not “the best allocator”; it is a strong **prior over failure modes**. The allocator underneath it should remain deliberately boring.

1. **Roster first.** Require the ordinary-market engine and persistent-crisis responder before adding more streams. Add a Target only for a measured fast-gap residual. Add Expansion sleeves when they introduce a new mechanism and pass bad-state dependence tests.
2. **Static top-down budgets.** Allocate risk across declared economic groups, then within groups. Do not let an estimated HRP tree overwrite the roster.
3. **Diagonal baseline, shrunk-covariance challenger.** Run fixed risk shares scaled by inverse volatility as the reference. Feed ERC a covariance shrunk toward its diagonal or a simple group structure, with min/max sleeve and group weights. Retain full covariance only if it improves held-out risk tracking and net outcomes consistently.
4. **No expected-return optimization.** Do not use trailing Sharpe, recent performance, or mean estimates in live weights. Any tactical view belongs in RD with a separate validation burden.
5. **Tail outside ordinary variance logic.** Set the Target from coverage, carry, and reliability; cap it; monetize upside asymmetrically; and never enlarge it merely because a calm-window covariance makes the book appear safe.
6. **Stress the dependence, not just the volatility.** Report ordinary correlation, downside/crisis correlation, common-factor exposure, and marginal whole-book drawdown. A candidate passes only if its mechanism and realized stream agree.
7. **Preserve the down-only vol ceiling and gradual drawdown control.** Judge both on realized tail containment, turnover, and recovery behavior—not on an in-sample Sharpe claim.

The concise decision is: **do not replace Floor + tail with “uncorrelated strategies.” Make Floor + residual tail the coverage constraints, then use genuinely uncorrelated strategies to expand the book.** For a small strategy roster, robust selection and hard role constraints matter more than a more elaborate optimizer.

## Strategy hypotheses this could seed

- [ ] **Diagonal versus shrunk ERC.** Compare fixed group risk shares with inverse-vol within groups against ERC using raw and Ledoit–Wolf-shrunk sleeve covariance, held out by regime; require improvement in book-vol tracking and worst-window drawdown after turnover.
- [ ] **Unconditional versus bad-state diversification.** Rank candidate Expansion sleeves once by full-sample correlation and once by worst-decile / Floor-drawdown dependence; test whether the latter better predicts next-window marginal drawdown reduction.
- [ ] **Target earns its slot.** Compare trend-only at lower gross with trend plus the available tail wrapper at matched long-run return or carry budget; keep the Target only if fast-gap expected-shortfall improvement survives bleed, fees, and monetization rules.
- [ ] **Economic groups versus estimated HRP groups.** On a deliberately widened future roster, compare declared Floor/Target/Expansion hierarchy with rolling HRP clusters; require stability and held-out risk improvement before estimated grouping can influence budgets.
- [ ] **Tail-aware constraints versus tail optimization.** Compare fixed crisis-coverage constraints with rolling CVaR/skew-optimized weights; expect the fixed constraint to be more stable because the optimizer has too few independent tail observations.

## Sources

[^longin]: Longin, F. & Solnik, B., “Extreme Correlation of International Equity Markets,” *Journal of Finance* 56(2), 2001. Using multivariate extreme-value methods, correlation rises in bear markets but not bull markets. https://www.longin.fr/Recherche_Publications/Articles_pdf/Longin_Solnik_Extreme_corelation_of_international_equity_market.pdf
[^ang]: Ang, A. & Chen, J., “Asymmetric Correlations of Equity Portfolios,” *Journal of Financial Economics* 63(3), 2002. US portfolio correlations with the market are materially greater on downside, especially extreme downside, moves. https://business.columbia.edu/sites/default/files-efs/pubfiles/1516/corr.pdf
[^lemp]: Lempérière, Y. et al., “Risk Premia: Asymmetric Tail Risks and Excess Returns,” *Quantitative Finance* 17(1), 2017. Finds a broad relation between risk-premium returns and negative skew, with trend following a notable positive-skew, positive-return exception. CFM-authored (manager conflict of interest). https://arxiv.org/abs/1409.7720
[^fung]: Fung, W. & Hsieh, D., “The Risk in Hedge Fund Strategies: Theory and Evidence from Trend Followers,” *Review of Financial Studies* 14(2), 2001. Lookback straddles explain trend-following-fund returns better than standard asset indices. https://papers.ssrn.com/sol3/papers.cfm?abstract_id=250542
[^demiguel]: DeMiguel, V., Garlappi, L. & Uppal, R., “Optimal Versus Naive Diversification: How Inefficient Is the 1/N Portfolio Strategy?”, *Review of Financial Studies* 22(5), 2009. https://www.heisetraining.at/wpblog/wp-content/uploads/2017/10/DeMiguel-et-al.-2009-Optimal-Versus-Naive-Diversification-How-Ineffici.pdf
[^erc]: Maillard, S., Roncalli, T. & Teiletche, J., “On the Properties of Equally-Weighted Risk Contributions Portfolios,” *Journal of Portfolio Management* 36(4), 2010. https://www.thierry-roncalli.com/download/erc.pdf
[^lw]: Ledoit, O. & Wolf, M., “Honey, I Shrunk the Sample Covariance Matrix,” *Journal of Portfolio Management* 30(4), 2004. The authors' page summarizes the portfolio-specific case for shrinkage and links the paper. https://ledoit.net/honey_abstract.htm
[^jm]: Jagannathan, R. & Ma, T., “Risk Reduction in Large Portfolios: Why Imposing the Wrong Constraints Helps,” *Journal of Finance* 58(4), 2003. https://www.nber.org/papers/w8922
[^hrp]: López de Prado, M., “Building Diversified Portfolios that Outperform Out of Sample,” *Journal of Portfolio Management* 42(4), 2016. Original HRP paper; avoids covariance inversion and reports favorable Monte Carlo comparisons. https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2708678
[^hrpcheck]: Deković, D. & Posedel Šimović, P., “Hierarchical Risk Parity: Efficient Implementation and Real World Analysis,” *Future Generation Computer Systems* 167, 2025. Finds `1/N` outperforms HRP on risk-adjusted returns across the authors' experimental setups, while HRP has approximately 1% lower volatility. https://doi.org/10.1016/j.future.2025.107744
[^puts]: Israelov, R., “Pathetic Protection: The Elusive Benefits of Protective Puts,” *Journal of Alternative Investments* 21(3), 2019. Author manuscript and abstract: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2934538
[^puttrend]: Ilmanen, A. et al., “Tail Risk Hedging: Contrasting Put and Trend Strategies,” AQR, 2020. Manager-authored (conflict of interest); useful for the distinct gap-versus-drawn-out-hedge mechanisms. https://images.aqr.com/-/media/AQR/Documents/Insights/White-Papers/AQR-Tail-Risk-Hedging-Contrasting-Put-and-Trend-Strategies.pdf
[^cederburg]: Cederburg, S., O'Doherty, M., Wang, F. & Yan, X., “On the Performance of Volatility-Managed Portfolios,” *Journal of Financial Economics* 138(1), 2020. https://www.lehigh.edu/~xuy219/research/COWY.pdf
[^quantunwind]: Khandani, A. & Lo, A., “What Happened to the Quants in August 2007? Evidence from Factors and Transactions Data,” *Journal of Financial Markets* 14(1), 2011. https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1288988
