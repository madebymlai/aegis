---
title: Strategy-Sleeve Architecture Beyond Trend, Carry and Tail
date: 2026-07-14
topic: strategy-roster
status: source-capture
related:
  - "[[the-tiered-strategy-roster]]"
  - "[[building-the-tiered-roster-after-demeter-v2]]"
  - "[[paired-floor-strategy-evaluation]]"
  - "[[what-can-fill-the-concave-floor-at-eur-5000-now]]"
tags:
  - note
  - research
  - strategy-allocation
  - crisis-alpha
  - alternative-risk-premia
  - small-account
---

# Strategy-Sleeve Architecture Beyond Trend, Carry and Tail

> [!abstract] Decision
> **Trend + a convergent income engine + tail is the right minimum viable architecture, but not the strongest institutional end-state.** The more durable top-level model is functional: **a convergent income engine, a persistent-crisis responder, a fast-crash response, and an optional off-axis alpha ensemble**. Carry is one candidate mechanism for the convergent role, not a required implementation. The fourth role can improve the architecture when implemented with many liquid long/short factors, but it is not credibly available in a €5,000 account. Therefore the current tiered roster should keep trend, a provisional income/harvesting engine, and a separately budgeted tail target, while leaving expansion deliberately empty. Do not fill the convergent role with a [[what-is-a-strategy|strategy]] that merely has negative skew.

## The allocator should classify jobs, not strategy labels

The central error in many strategy rosters is to treat every attractive backtest as another peer sleeve. Carry, value, defensive equity, trend, reversal and puts do not do the same job. Their economic functions and expected failure states differ.

| Roster job | Strongest institutional benchmark | Economic purpose | Expected payoff and principal failure | Aegis / €5,000 constraint |
| --- | --- | --- | --- | --- |
| **Convergent income engine** | A diversified long/short convergence-premium portfolio; cross-asset carry is the best-documented generic benchmark, while credit, catastrophe-insurance, merger-arbitrage and defined-risk volatility premia are candidate implementations[^carry] | Earn positive full-cycle return in ordinary markets and finance the defensive jobs | Construction-dependent, not inherently short gamma: many insurance and liquidity premia are concave, but diversified carry can have little aggregate skew; losses arrive when the priced convergence mechanism breaks or common recession, liquidity and volatility shocks dominate | Demeter owns the job, not a preferred label. Admit only a low-turnover expression whose net premium, loss trigger and marginal whole-book utility survive executable costs; an empty role is valid |
| **Persistent-crisis responder** | Broad, volatility-scaled multi-asset time-series trend across equity-index, bond, currency and commodity markets[^tsmom] | Adapt after a directional dislocation persists long enough for signals to reposition | Straddle-like exposure to large moves and often positive skew at the strategy horizon; vulnerable at turning points, sharp reversals and range-bound whipsaw | Atalanta owns this job. A packaged implementation is feasible, but the benchmark requires genuine market breadth rather than an equity timing rule |
| **Immediate defense** | `DAR4020`-like defensive factor selection; reserve explicit puts for residual gap-speed or contractual-convexity needs[^baltussen] | Respond at the start of a drawdown, before trend has adapted | DAR obtains immediate protection from a pre-existing negative portfolio beta, not contractual convexity; puts are convex on impact but carry persistent premium drag | Aegis owns this job. Institutional DAR ranks 25 long/short factors and needs shorting, volatility scaling and cheap execution, so it is a benchmark rather than a credible €5,000 implementation; any explicit hedge must be small and cost-budgeted |
| **Off-axis alpha ensemble** | A diversified beta-neutral long/short ensemble of value, cross-sectional momentum, quality/defensive and other independently validated factor premia[^global-factors] | Earn from cross-sectional dispersion without duplicating the engine, trend or immediate-defense mechanisms | Neither convergent nor convex by definition; the desired shape is positive full-cycle return with low residual market beta, while crowding, momentum reversal, value traps and implementation costs remain strategy-specific failures | Expansion owns this job. The evidence relies on broad universes, shorts and cheap rebalancing; at €5,000, leave the tier empty until a vehicle reproduces those properties after fees |

The table is a **job specification**, not a shopping list. Its “strongest institutional benchmark” column identifies the cleanest researched expression of each function, not the next retail product to buy. The small-book conclusions are inferences from the instruments and portfolio construction used by those papers: multi-asset futures and forwards for trend; 25 long/short factors for DAR; and broad dollar-neutral cross-sections for factor portfolios.

Four source-level distinctions keep the jobs from collapsing into labels:

- **Convergence is an economic mechanism, not a skew statistic.** Koijen et al. find that carry predicts returns across multiple asset classes and that carry sleeves can fail together around global recessions, liquidity stress and volatility shocks, yet their diversified global carry factor has little aggregate skew.[^carry] Negative skew can reveal a financing or insurance exposure, but it neither proves convergence nor qualifies an engine.
- **Trend is adaptive rather than pre-positioned insurance.** Moskowitz, Ooi and Pedersen find that diversified time-series momentum performs best in extreme markets and has a straddle-like nonlinear relation to market returns, but their 2008–09 path also shows losses before the trend is established and when it reverses sharply.[^tsmom] The 220-year defensive comparison confirms that trend tends to improve as a drawdown persists.[^baltussen]
- **Immediate defense does not have to mean puts.** Baltussen, Martens and van der Linden find that `DAR4020` typically arrives with negative 60/40 beta, while trend is slower at drawdown onset; the two are complementary across stages. Their construction goes long the 40% of 25 factors with the lowest rolling correlation to 60/40 and shorts the highest-correlation 20%, adding net factor-premium exposure to the original symmetric DAR.[^baltussen] This is a stronger institutional benchmark than continuous put buying, but it is not contractual convexity and is not directly portable to Aegis.
- **Off-axis alpha must be orthogonal by exposure, not by name.** Baltussen, Swinkels and van Vliet test 24 factor/asset-class combinations across equities, bonds, commodities and currencies from 1800–2016; most factor premia remain strong out of sample and are generally unrelated to market, downside or macroeconomic risks.[^global-factors] That supports a diversified long/short factor ensemble as an institutional expansion benchmark, while the breadth and implementation assumptions explain why a long-only retail “factor ETF” is not equivalent.

“Carry” is therefore only shorthand for the first job. If credit carry fails, the role does not require another FX-carry trade or an option overwrite. It requires a **deployable convergent premium whose dominant loss trigger is understood and acceptably independent of the rest of the roster**. Catastrophe-insurance risk is attractive for that reason; equity put writing is much less so because it reloads the same financial-crash state.

## What the strongest long-run evidence changes

The most relevant recent comparison is Baltussen, Martens and van der Linden's 2026 *Financial Analysts Journal* study of defensive strategies over 220 years.[^baltussen] It finds that low-risk, quality and value equity factors help in bad markets, but multi-asset Defensive Absolute Return (DAR) and trend provide the most robust, complementary drawdown protection. The return-enhanced `DAR4020` construction ranks 25 long/short factors by their rolling correlation to a 60/40 portfolio, goes long the 40% with the lowest correlation and short the 20% with the highest, and thereby combines an immediate negative-beta stance with a net long exposure to factor premia. Trend tends to help later in persistent drawdowns; DAR tends to arrive already defensive.

That is a stronger **ideal** architecture than trend plus a generic tail hedge because it seeks positive full-cycle return from both defensive components. It does not, however, map into one retail ETF or a small custom account. It relies on a broad, dynamically ranked, long/short factor universe, volatility scaling and cheap execution. The correct lesson for Aegis is architectural—**separate immediate from adaptive defense and prefer defenses with positive full-cycle expectancy**—not “replace the current roster with DAR4020.” The study also evaluates defense around a 60/40 benchmark, not Aegis's strategy-only book, so its exact rankings and weights cannot be imported.

Earlier evidence points in the same direction. Harvey et al. find that one-month index puts were the most reliable of the crisis hedges they studied but were very costly outside crises; time-series momentum and beta-neutral quality long/short had positive expected returns, different mechanisms and historically uncorrelated returns.[^harvey] Hurst, Ooi and Pedersen report that trend following was positive in eight of the ten worst drawdowns of a global 60/40 portfolio over their 1880–2016 sample.[^hurst] More granular CTA research finds that crisis performance came from diversification across markets and rapid exposure reduction—less than 15 days in the studied episodes—not from a permanent equity short.[^asif]

This evidence supports a staged defense:

1. an immediate, pre-positioned response;
2. a slower adaptive responder that can profit if the dislocation persists;
3. ordinary-market engines that finance the book.

It does **not** imply that every account must hold puts continuously. Put protection can be too expensive, and the newest two-century comparison finds it less cost-effective than the best factor and trend defenses.[^baltussen] The tail tier should therefore be governed by a small premium budget and an explicit speed requirement. If the available vehicle cannot meet those gates after fees, zero is a valid temporary allocation.

## Why the obvious alternative architectures are weaker here

### Alternative-risk-premia stack: value + momentum + carry + defensive

A broad style-premia stack is an excellent institutional return architecture. Value and momentum have appeared across markets and asset classes, and their negative relationship has historically improved the combined portfolio.[^valmom] Diversification across value, momentum, carry and defensive styles can be deeper than owning more securities inside one market.

But a style-premia stack is not automatically a crisis architecture. Carry premia share recession, liquidity and volatility exposure even when their unconditional pairwise correlations look modest.[^carry] Negative skew is common across equity, bond, currency, credit and option-selling premia; trend is the major positive-skew exception.[^lemp] Momentum in a cross-sectional equity portfolio is also not the same strategy as multi-asset time-series trend. A retail long-only “factor ETF” can retain substantial market beta and cannot reproduce the beta-neutral long/short factor evidence.

Verdict: **stronger as a diversified institutional engine, not a replacement for the role-separated Aegis defense.** At €5,000 it is more likely to create small, correlated factor tilts and fee drag than independent sleeves.

### Defensive equity: quality, low beta and value

Defensive equity is useful but belongs in the return-engine or expansion discussion, not the explicit-insurance tier. Beta-neutral quality long/short has credible crisis evidence and complements trend.[^harvey] The `DAR4020` evidence also includes defensive equity factors among its raw material.[^baltussen]

The accessible long-only version is a different payoff. It remains long equities, and low-beta portfolios can suffer when funding constraints tighten and security betas compress toward one.[^bab] Without a short junk/high-beta leg and sufficient cross-sectional breadth, “defensive equity” is an equity-risk modifier rather than independent crisis alpha.

Verdict: **a plausible future off-axis component only if a vehicle demonstrates low residual beta and reasonable fees; not a tail substitute.**

### Value and short-horizon reversal

Value can complement momentum over long horizons, but it can experience prolonged relative drawdowns and requires breadth. Short-term reversal is economically closer to liquidity provision: Nagel finds its expected return and Sharpe rise with VIX, consistent with compensation for supplying liquidity when it is scarce.[^nagel] That is not free crisis alpha. The strategy turns over quickly just when spreads, price impact and operational error matter most.

Verdict: **keep reversal in execution logic at small scale, not as a separately funded sleeve.** A genuine long/short value or reversal sleeve requires more names, shorting and cheaper trading than the account supports.

### Volatility risk premium / short gamma

Option selling is the cleanest expression of a convergent, negative-skew engine. It can earn an insurance premium in ordinary markets, but it is not a diversifier from a financial crash; it is one of the positions that needs trend and tail protection. It should be judged by whole-cycle certainty equivalent, worst gap, collateral mechanics and capped loss—not by income yield.

The premium is also not timeless. Dew-Becker's 2025 Chicago Fed working paper finds that delta-hedged option alphas and information ratios declined materially over the recent 15-year period, with common put and straddle information ratios converging toward zero by 2020.[^dewbecker] This is not proof that all volatility selling is dead, but it raises the evidence bar for using put writing as the roster's sole return engine.

Verdict: **valid engine family, poor default for Aegis now.** Use only a defined-loss, fully collateralized implementation whose net premium survives current executable data.

### Tail-only or trend-only defense

Neither subsumes the other. Puts are pre-positioned and can pay in a sudden gap; trend must observe and react. Trend has historically earned a positive full-cycle return and can benefit through extended crises, but it is vulnerable to whipsaw and violent reversal. Time-series momentum's 2008 gains and 2009 reversal losses illustrate that path dependence.[^tsmom]

Verdict: **trend should be the standing defensive engine; tail is a small speed supplement.** Treating both as equal-risk sleeves would overpay for the same broad purpose and mismeasure the tail sleeve's risk.

## Allocation: simple functional budgets, not a backtest optimizer

There is no source-supported universal weight such as `60/40` for trend and carry. The existing 70-month Aegis paired test showed that the fixed `60%` trend / `40%` credit mix improved realized Sharpe and drawdown but reduced certainty equivalent, with all primary bootstrap intervals crossing zero.[^paired] That result supports role plausibility, not an optimized production allocation.

For the small account, use this hierarchy:

1. **Fund the engine and trend with simple, stable risk budgets.** Equal ex-ante sleeve risk is a defensible neutral starting point, but it is an engineering prior rather than a proven optimum. Use long windows, caps and conservative volatility estimates. Scale risky sleeves down; do not lever a tiny account up merely to equalize risk.
2. **Budget tail by annual cost, not observed volatility.** A quiet put sleeve can report low realized volatility immediately before losing its full premium or paying explosively. Set the maximum annual premium drag and maximum single-position loss in advance.
3. **Give expansion zero weight until a real implementation passes.** When an off-axis sleeve qualifies, carve its initial risk budget from the convergent engine; do not increase total portfolio risk or weaken the trend/tail jobs to make room.
4. **Rebalance with wide drift bands and low frequency.** At €5,000, minimum commissions, bid–ask spreads and whole-share constraints can overwhelm small theoretical reallocations. The goal is stable role exposure, not continuous covariance precision.
5. **Do not time sleeves from recent performance.** A century-scale study of value, momentum, carry and defensive premia across six asset classes finds that factor-timing evidence is weak and inconsistent, with likely gains too modest to survive implementation frictions.[^timing] Regime stories can set risk caps; they should not drive tactical winner-chasing.

DeMiguel, Garlappi and Uppal's comparison of 14 portfolio optimizers across seven datasets is the right warning: none consistently beat `1/N` out of sample on Sharpe, certainty equivalent and turnover because estimation error offset the theoretical gain.[^demiguel] That is asset-allocation evidence rather than a direct test of these sleeves, so it does not prove equal weighting is optimal. It does support choosing transparent fixed budgets over estimated expected-return optimization with a short, reused sample.

## Implication for the current tiered roster

The current roster is closer to the right architecture than a four-factor shopping list:

| Current tier | Functional interpretation | Decision now |
| --- | --- | --- |
| Atalanta trend floor | Persistent-crisis responder | Keep locked; measure speed and reversal losses explicitly |
| Provisional credit/CATB pole | Convergent income engine | Keep the role; prefer the most orthogonal net premium, not the strongest recent yield |
| Tail target | Fast-crash response | Keep separate and cost-capped; do not require it to have positive stand-alone Sharpe |
| Empty expansion | Off-axis alpha ensemble | Keep empty until a beta-neutral, breadth-capable implementation exists |

The long-term upgrade path is **not** “add more carry.” It is to replace a weak convergent implementation with a better one, then add a genuinely independent alpha ensemble if account size, wrapper availability and evidence eventually permit it. `DAR4020`, beta-neutral quality and diversified long/short style premia define what that fourth role should resemble. They are research benchmarks, not current retail candidates.

> [!important] Bottom line
> At €5,000, the strongest architecture is the one that can remain sparse. Trend + a real ordinary-market engine + a small fast-crash budget is functionally complete. A fourth sleeve is valuable only when it adds a new mechanism after costs. Until then, cash and an empty expansion tier are stronger than a weak value, reversal, defensive-equity or short-vol proxy.

## What would change this decision

- A UCITS vehicle demonstrating beta-neutral quality/DAR-like returns, broad underlying implementation, acceptable liquidity and a small minimum would justify reopening expansion.
- Current executable evidence that a defined-loss volatility-risk-premium vehicle retains positive certainty equivalent after all costs would make it a valid engine challenger, not a diversifier.
- Failure of trend across sustained dislocations—not merely a fast gap or reversal—would challenge its persistent-crisis role.
- A tail implementation whose premium drag consumes the engine's expected net return should be defunded until a cheaper speed solution exists.
- More capital can change feasibility before it changes theory: breadth, shorting access and fixed-cost dilution are the binding gates for the fourth role.

## Sources

[^baltussen]: Baltussen, G., Martens, M. and van der Linden, L. (2026), “The Best Defensive Strategies: Two Centuries of Evidence,” *Financial Analysts Journal* 82(1), 6–34. The paper documents the 25-factor `DAR4020` construction, its immediate negative-beta defense, trend's slower response in early drawdowns, and their complementary performance over the 1800–2021 sample. https://www.tandfonline.com/doi/full/10.1080/0015198X.2025.2602270

[^harvey]: Harvey, C. R. et al. (2019), “The Best of Strategies for the Worst of Times: Can Portfolios Be Crisis Proofed?” *Journal of Portfolio Management* 45(5). The study compares passive and dynamic crisis hedges and identifies time-series momentum plus beta-neutral quality long/short as complementary positive-expectancy defenses; its authors include researchers affiliated with Man Group. https://people.duke.edu/~charvey/Research/Published_Papers/P140_The_best_of.pdf

[^hurst]: Hurst, B., Ooi, Y. H. and Pedersen, L. H. (2017), “A Century of Evidence on Trend-Following Investing.” The long historical reconstruction is produced by AQR-affiliated authors and includes simulated results, so its implementation assumptions matter. https://fairmodel.econ.yale.edu/ec439/hurst.pdf

[^asif]: Asif, R., Frömmel, M. and Mende, A. (2022), “The crisis alpha of managed futures: Myth or reality?” *International Review of Financial Analysis* 80. https://doi.org/10.1016/j.irfa.2022.102001

[^valmom]: Asness, C. S., Moskowitz, T. J. and Pedersen, L. H. (2013), “Value and Momentum Everywhere,” *Journal of Finance* 68(3). https://pages.stern.nyu.edu/~lpederse/papers/ValMomEverywhere.pdf

[^carry]: Koijen, R. S. J., Moskowitz, T. J., Pedersen, L. H. and Vrugt, E. B. (2018), “Carry,” *Journal of Financial Economics* 127(2). https://www.nber.org/system/files/working_papers/w19325/w19325.pdf

[^lemp]: Lempérière, Y. et al. (2017), “Risk Premia: Asymmetric Tail Risks and Excess Returns,” *Quantitative Finance* 17(1). https://doi.org/10.1080/14697688.2016.1183035

[^bab]: Frazzini, A. and Pedersen, L. H. (2014), “Betting Against Beta,” *Journal of Financial Economics* 111(1). https://www.nber.org/system/files/working_papers/w16601/w16601.pdf

[^nagel]: Nagel, S. (2012), “Evaporating Liquidity,” *Review of Financial Studies* 25(7). https://www.nber.org/system/files/working_papers/w17653/w17653.pdf

[^dewbecker]: Dew-Becker, I. (2025), “The Decline of the Variance Risk Premium: Evidence from Traded and Synthetic Options,” Federal Reserve Bank of Chicago Working Paper 2025-17. This is a current central-bank working paper, not yet the same evidentiary tier as a replicated peer-reviewed result. https://www.chicagofed.org/-/media/publications/working-papers/2025/wp2025-17.pdf?sc_lang=en

[^tsmom]: Moskowitz, T. J., Ooi, Y. H. and Pedersen, L. H. (2012), “Time Series Momentum,” *Journal of Financial Economics* 104(2). https://w4.stern.nyu.edu/facdir/lpederse/papers/TimeSeriesMomentum.pdf

[^timing]: Ilmanen, A. et al. (2021), “How Do Factor Premia Vary Over Time? A Century of Evidence,” *Journal of Investment Management* 19(4). https://spinup-000d1a-wp-offload-media.s3.amazonaws.com/faculty/wp-content/uploads/sites/3/2021/08/HowDoFactorPremiaVaryOverTime_JOIM.pdf

[^demiguel]: DeMiguel, V., Garlappi, L. and Uppal, R. (2009), “Optimal Versus Naive Diversification: How Inefficient Is the 1/N Portfolio Strategy?” *Review of Financial Studies* 22(5). https://doi.org/10.1093/rfs/hhm075

[^global-factors]: Baltussen, G., Swinkels, L. and van Vliet, P. (2021), “Global Factor Premiums,” *Journal of Financial Economics* 142(3), 1128–1154. The authors test 24 factor/asset-class combinations across global equities, government bonds, commodities and currencies using replication and new-sample evidence from 1800–2016, with multiple-testing controls. https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3325720

[^paired]: [[paired-floor-strategy-evaluation]]. The July 2026 Aegis evaluation uses 70 monthly observations and labels its reused-history inference as descriptive rather than fresh out of sample.
