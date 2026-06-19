---
title: "Verifying Strategy-Family Membership from the Return Stream"
date: "2026-06-11"
topic: strategy-taxonomy
distilled-into:
tags:
  - article
---

# Verifying Strategy-Family Membership from the Return Stream

> [!abstract] One-line takeaway
> A strategy earns its family label only if its realized return stream passes objective gates - four measured signatures (own-return skew, quadratic convexity, crisis-conditional return, regime-conditional beta) against a common benchmark, over multi-year windows. Declaration is not membership; the stream is.

## Why verification, not declaration

A strategy does not get to call itself a trend follower or a crash hedge. The taxonomy classifies by *realized behavior* - the sign and speed of a strategy's convexity to the shocks that move all risk assets at once (the argument in [[convexity-as-the-axis-of-strategy-diversification]]) - and behavior can only be measured after the fact, on the frozen return stream of a Locked Candidate. Mechanism labels drift: a strategy authored as momentum can behave concavely once costs, caps, and a particular universe are applied. So membership is a verification problem, and the [[the-tiered-strategy-roster|tiered roster]] is only as trustworthy as the gates that admit candidates to each tier.

Four signatures, measured against a single reference benchmark (SPY as the dominant macro risk factor in our universe), are enough to place a stream and to catch label drift.

## The four signatures

### Own-return skewness

$$S = \frac{\mathbb{E}\left[(R_{p,t}-\mu_p)^3\right]}{\sigma_p^3}$$

The static asymmetry of the candidate's own return distribution: convex sleeves are right-skewed (rare large gains), concave sleeves left-skewed (rare large losses). The horizon matters. Trend-following shows little skew at monthly frequency but becomes significantly right-skewed at quarterly horizons, because the long-gamma payoff accumulates over the life of a move rather than within any single month.[^fh] Verify skew at the horizon where the family's payoff actually expresses, not only monthly.

### Standardized quadratic convexity

Regress the candidate's return on the benchmark and its square, with the benchmark standardized by its own volatility so the coefficient is scale-invariant across assets and frequencies:

$$R_{p,t} = \alpha + \beta_1\left(\frac{R_{b,t}}{\sigma_b}\right) + \beta_2\left(\frac{R_{b,t}}{\sigma_b}\right)^2 + \epsilon_t$$

This is the Treynor-Mazuy market-timing regression, whose squared-benchmark coefficient $\beta_2$ measures convexity directly.[^tm] A positive $\beta_2$ is a convex "smile" (the sleeve does better the larger the move, in either direction); a negative $\beta_2$ is a concave "frown" that gives back in the tails. The vertex of the parabola,

$$X_{\text{turn}} = -\frac{\beta_1}{2\beta_2}$$

locates the benchmark move at which the strategy's expected return stops falling and starts rising - a compact description of where a convex sleeve switches on.

Like skew, $\beta_2$ has to be measured at the horizon where the payoff expresses. The convex term is a multi-period object: a trend follower holding a position proportional to its accumulated trend earns a cumulative P&L equal to one-half the difference between the squared price move over the whole holding period and the sum of squared daily moves, so the convexity lives entirely in the macro-horizon squared-move term.[^cfmconv] Estimated on *daily* returns - where the position reflects the past trend, not today's move - $\beta_2$ collapses toward zero even for a genuinely long-gamma stream, because the daily regression is dominated by noise and the per-bar payoff carries almost none of the accumulated gamma. Fit $\beta_2$ on monthly or quarterly compounded returns, the same horizon at which the family's skew becomes visible; a daily Treynor-Mazuy fit will read a convex trend sleeve as flat.

### Crisis-conditional return

The conditional mean return of the strategy when the benchmark falls in its worst decile. This isolates tail behavior from the full-sample average, which is dominated by calm periods. A convex sleeve should be non-negative here; a concave sleeve is negative by construction (it is the victim of the dislocation); a tail sleeve should be strongly positive. It is the conditional generalization of down-capture, and the estimation problem it inherits is the subject of [[measuring-crisis-alpha]].

Crucially, this signature is *horizon-sensitive in sign*, exactly as $\beta_2$ is, and the daily form has a blind spot. Measured on the benchmark's worst *days* it reads **negative even for a genuinely convex slow-crisis sleeve**, because trend lags a fast shock and co-crashes on the way down: on our non-equity Atalanta book the worst-decile-*day* return is about -29 bps long-only, yet over the benchmark's worst *quarters* the same book is a positive payer - the slow, 2022-style grinds it is actually built for. A trend sleeve is a *slow*-crisis payer, blind to crashes that complete inside its rebalance interval (the split is [[divergent-vs-defensive-crash-resistance]]; fast shocks are a separate sleeve's job, [[detecting-fast-crashes-from-price]]). So the load-bearing form of this signature is the **crisis-conditional return** (shipped as `crisis_quarter_return`): the annualized stream return when the benchmark does badly, with the downside conditioning *smoothed* (each multi-month window weighted by the benchmark's shortfall below its mean - no quantile cutoff) and *averaged over a 2-6 month horizon band*. Both choices matter: a single horizon and a hard quantile made the value swing several-fold across defensible settings, while the smooth, band-averaged form is design-stable (long-only about +5%/yr, L/S about +10%, ordering invariant). A conditional *mean* (not a third moment) is far more split-stable than skew. But its *magnitude* is not trustworthy - only a couple of crises sit in any sample, so its block-bootstrap CI is wide and straddles zero; trust the **sign and the cross-book ordering**, not the number. Read alongside the daily `crash_day_return`, the pair exposes the horizon flip directly.

### Regime-conditional beta

Partition the benchmark return distribution into three regimes - bear (below the 16th percentile, roughly a one-standard-deviation down move), normal (16th to 84th), and bull (above the 84th) - and estimate the local benchmark beta within each. A strategy's market sensitivity is not constant across regimes, and the bear-regime beta is the one that matters for defense: a genuine defensive sleeve must show a strongly negative bear-regime beta, translating benchmark losses into strategy gains, even when its full-sample beta looks benign.

### Own-gamma to trend efficiency (the trend family's primary test)

The four signatures above are all measured against an external benchmark, which makes them *crisis-alpha* tests: they ask whether the sleeve is convex to *equity* moves. For the trend family that convexity is a breadth-dependent byproduct, not the core identity - a trend sleeve is long-gamma to *its own* universe's moves (the lookback straddle is on the sleeve's own instruments), and it only expresses as equity-crisis convexity when the book carries enough non-equity legs to trend while equities fall. So the trend family's primary membership test is own-gamma: regress the sleeve's return on its universe's realized trend *efficiency* - directional travel over total travel, the ratio at the heart of the CFM identity[^cfmconv] - not on the benchmark. A genuine trend sleeve gains in efficiently-trending months and bleeds in chop; a positive, significant loading is the long-gamma signature. Measuring against raw move *magnitude* instead conflates sustained trends with choppy high-volatility months and mis-reads a long-gamma sleeve as flat.

This makes the universe a membership precondition, not a free choice. A trend signal realizes long gamma only where the book's move-magnitude is not collinear with the equity benchmark; on an equity-dominated universe the trend axis collapses into equity beta, and a lagged signal is wrong-footed on every fast reversal, realizing *short* gamma under a trend label. The substrate sets the sign of the gamma before any construction choice does, and benchmark-relative $\beta_2$ turns positive only once own-gamma is positive - which is why own-gamma is the primary trend test and SPY-$\beta_2$, crisis-conditional return, and bear-regime beta are the *secondary*, breadth-dependent crisis-alpha signatures.

## Per-family target signatures

The four signatures combine into a per-family gate. The signs and orderings are well-determined by the payoff logic;[^conv] the specific cut points below are proposed engineering defaults, to be recalibrated on our own verified candidates rather than trusted as laws.

| Family | Quarterly skew $S$ | Convexity $\beta_2$ | Crisis-cond. return | Bear-regime beta | Linear beta $\beta_1$ | Window |
|---|---|---|---|---|---|---|
| Trend / Momentum | positive (≈ ≥ 0.5) | ≥ 0 | ≥ 0 | ≤ 0 | low, ≈ [−0.1, +0.1] | 36-60mo |
| Carry / Mean-Reversion | negative | ≤ 0 | < 0 | ≥ 0 (loses in bear) | moderate +, ≥ 0.20 | 36-60mo |
| Tail / Defensive | strongly positive | ≥ 0 | strongly positive | strongly negative | negative, ≤ 0 | 60mo |
| Market-Neutral | ≈ 0 (±~0.2) | ≈ 0 (±~0.05) | ≈ 0 | ≈ 0 (±~0.1) | ≈ 0 (±~0.05) | 36mo |

These are objective gates, implemented as Aegis RD custom Metrics and run during research so the Candidate Store stays populated with verified, regime-complementary streams. The "crisis-conditional return" column is the horizon-resolved `crisis_quarter_return` (smooth downside weight, 2-6 month band, annualized), not the daily `crash_day_return` whose sign inverts for a slow-crisis sleeve; gate on its sign and ordering, not its magnitude (the block-bootstrap CI is wide).

## Limitations

Verification is slow. Confirming a behavioral profile needs multi-year windows (36 to 60 months), and the rarer the regime a family is defined against - tail being the extreme - the longer it takes to observe enough crisis episodes to trust the signature. This is the central cost of a behavior-based taxonomy versus a mechanism-based one, which can be read off instantly but means less.

Skew is tail-fragile *and* horizon-unstable. The third moment is dominated by a few extreme observations, finite-sample biased, and its sign flips with measurement frequency: the same Atalanta long-only book reads skew -0.28 daily, +2.20 weekly, +1.08 monthly, and +2.48 quarterly, and its per-split quarterly skew swings with a standard deviation (about 1.16) as large as the signal itself. A single full-sample skew number is false precision. If a *moment* is genuinely needed, prefer L-skewness - Hosking's ratio of linear combinations of order statistics, which carries the lowest root-mean-squared error among skew estimators and is near-unbiased in small samples[^hosking][^robustskew] - or the medcouple, a 25%-breakdown robust skewness bounded in [-1, 1].[^medcouple] But to *rank* a convex sleeve, do not rank on a moment at all: rank on the crisis-quarter conditional mean above, which measures the economically relevant property (does it pay when the benchmark bleeds?) with a low-variance estimator at the horizon where the payoff lives.

The thresholds are heuristics. The numeric cut points come from practitioner practice, not peer-reviewed estimation; treat the signs as well-grounded and the magnitudes as starting values to calibrate.

The functional form is a choice. The quadratic Treynor-Mazuy model is one way to capture non-linearity; the Henriksson-Merton up/down dummy regression is another, and they can disagree at the margin.[^tm] Every conditional metric also inherits the benchmark choice: swap SPY for a 60/40 book and the crisis-conditional and regime-beta numbers move with it.

## Strategy hypotheses this could seed

- [ ] **Build the gates.** Implement skew (quarterly), the Treynor-Mazuy $\beta_2$, crisis-conditional return, and regime-conditional beta as Aegis RD custom Metrics, and confirm they sort existing Candidates into the predicted poles.
- [ ] **Horizon matters.** Show that quarterly-horizon skew separates the trend sleeve from noise where monthly skew does not, on our own candidates.
- [x] **Convexity horizon.** Show that $\beta_2$ measured on monthly/quarterly compounded returns is positive for a trend stream whose *daily* $\beta_2$ is ≈ 0, and set the gate's convexity horizon accordingly rather than fitting Treynor-Mazuy on daily bars. **Methodology stands, but no hidden convexity in our trend sleeve (2026-06-12):** for the Atalanta straddle $\beta_2$ is ≈ 0 at daily and goes slightly *negative* at monthly/quarterly (-0.0028, -0.0071), so the flat reading is genuine, not a horizon artifact. Still fit $\beta_2$ at the payoff horizon as a rule; just do not expect it to rescue a sleeve whose convexity is actually absent. See [[runs/atalanta/2026-06-12#H1 - convexity measurement horizon (diagnostic)]].
- [x] **Own-gamma is the trend test.** A trend sleeve's membership tracks its loading on its own universe's trend efficiency, not benchmark $\beta_2$, and an equity-dominated substrate inverts the sign to short gamma. **Confirmed 2026-06-12:** [[runs/atalanta/2026-06-12|substrate test]].
- [x] **Crisis-conditional horizon flip, and a stabilized metric.** The benchmark's worst-*day* conditional return reads negative for a genuine slow-crisis trend sleeve (it co-crashes; trend lags), while the multi-month conditional return reads positive - the convexity only appears at the multi-month horizon. **Confirmed and shipped 2026-06-17:** `crash_day_return` about -29 bps long-only vs a positive multi-month payoff (about +5%/yr). The first cut (single 3-month horizon, worst quintile) proved knob-unstable - the value swung several-fold across horizon and quantile choices - so `crisis_quarter_return` was **reimplemented** with a smooth mean-shortfall downside weight and a 2-6 month horizon-band average (annualized), collapsing the design spread 3-7x while preserving the cross-book ordering. The irreducible magnitude uncertainty is a wide post-hoc block-bootstrap CI that straddles zero, so rank on sign/ordering, not magnitude. See [[runs/atalanta/2026-06-17]].
- [x] **Skew is not a rankable key here.** Moment skew is frequency-unstable (same book: -0.28 d / +2.20 w / +1.08 m / +2.48 q) and per-split noisy (std about 1.16, as large as the signal), so it cannot be a trustworthy ranking objective; the smooth, band-averaged crisis-conditional return (sign/ordering) is the stable replacement. **Confirmed 2026-06-17**, same run diary.
- [ ] **Calibrate, don't import.** Fit the per-family thresholds on our verified candidates and compare against the practitioner defaults; report where they differ.
- [ ] **Label stability.** Test whether family labels survive across rolling 36 and 60-month windows or drift, and flag any candidate whose membership is window-dependent.

## Sources

[^tm]: Treynor, Mazuy, "Can Mutual Funds Outguess the Market?", Harvard Business Review 44, 1966 - the quadratic market-timing regression whose squared-benchmark coefficient measures convexity; the Henriksson-Merton (1981) up/down dummy regression is the option-style alternative.
[^fh]: Fung, Hsieh, "The Risk in Hedge Fund Strategies: Theory and Evidence from Trend Followers", Review of Financial Studies 14(2):313-341, 2001 - trend payoff replicates a lookback straddle (long gamma), so its right-skew accumulates over the move and emerges at longer horizons. https://academic.oup.com/rfs/article-abstract/14/2/313/1600868
[^cfmconv]: "The Convexity of Trend Following", Capital Fund Management, 2018 - decomposes a trend follower's cumulative P&L as one-half the difference between the squared cumulative move and the summed squared daily moves; the convex term is the long-horizon variance, which is a multi-period quantity (so it must be measured over the move, not bar by bar) and is capped by any sizing rule that scales the position down as the move grows. https://www.cfm.com/wp-content/uploads/2022/12/266-2018-The-Convexity-of-trend-following.pdf
[^conv]: Informa Connect, "Assessing the Risk-Profile of Quant Strategies: the Convexity vs Skewness" (practitioner) - classifies systematic strategies by realized convexity and skewness; practitioner framing, not peer-reviewed. https://informaconnect.com/assessing-risk-profile-of-quant-strategies-the-convexity-vs-skewness/
[^hosking]: Hosking, J. R. M., "L-Moments: Analysis and Estimation of Distributions Using Linear Combinations of Order Statistics", JRSS-B 52(1):105-124, 1990. Because L-moments are linear in the order statistics, L-skewness ($\tau_3$) is far less sample-variable and more outlier-robust than the conventional cubed third moment, and is well-defined whenever the mean exists. https://rss.onlinelibrary.wiley.com/doi/10.1111/j.2517-6161.1990.tb01775.x
[^robustskew]: Bastianin, A., "Robust measures of skewness and kurtosis for macroeconomic and financial time series", Univ. Milano-Bicocca WP 408, 2019. Monte Carlo over twelve estimators and nine distributions finds L-moments and trimmed L-moments the most outlier-resistant and lowest-RMSE skew/kurtosis estimators, confirmed on 128 FRED-MD series. https://ideas.repec.org/p/mib/wpaper/408.html
[^medcouple]: Brys, G., Hubert, M. & Struyf, A., "A Robust Measure of Skewness", Journal of Computational and Graphical Statistics 13(4):996-1017, 2004. The medcouple is a median of pairwise kernels with a 25% breakdown value and bounded influence function, bounded in [-1, 1]; the overall winner among robust skewness measures. https://wis.kuleuven.be/statdatascience/robust/papers/2004/medcouple.pdf
