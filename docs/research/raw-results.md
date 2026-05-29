# Strategy Research — Raw Results

Prompt used: `docs/research/researcher.txt`

---

## Perplexity Deep Research

**Date:**
**Model/mode:**

<paste raw output below>

SET 1 — Multi‑asset trend plus volatility scaling

High‑level:
Allocate across all 10 ETFs based on trend signals (combining time‑series momentum and moving averages), scaled by recent volatility so that more stable trends get larger weights. This extends Moskowitz–Ooi–Pedersen’s TSMOM and Faber’s MA timing into a daily‑bar, ETF universe with risk‑aware sizing.
Indicators

Per asset ii:

    12‑month total return R12R12​: close‑to‑close total return over past 252 trading days (optionally excluding last 21 days to match standard TSMOM formulations).
    Role: slow trend / TSMOM signal — sign and magnitude predict next‑period return across asset classes.

    4‑month total return R4R4​: past 84 trading days.
    Role: medium‑term confirmation to avoid being stuck in very stale trends; trend‑following literature shows diversification across 3–12 month lookbacks improves robustness.

    200‑day simple moving average (SMA200200​): standard trend filter, approximating Faber’s 10‑month SMA.
    Role: binary “in/out of trend” filter, especially useful for equity‑like assets to avoid large drawdowns.

    20‑day realized volatility σ20σ20​ from daily log returns.
    Role: volatility‑scaling / risk parity component; Harvey et al. show that vol scaling improves Sharpe for risk assets and reduces tail risk for all assets.

Optionally, for robustness, a longer vol estimate (e.g., 60‑day) can be blended with 20‑day to avoid reacting too fast.
Signal logic

For each asset ii at decision date tt:

    Trend score:

        Define binary indicators:

            I12=1I12​=1 if R12>0R12​>0, else 0.

            I4=1I4​=1 if R4>0R4​>0, else 0.

            IMA=1IMA​=1 if pricett​ > SMA200,t200,t​, else 0.

        Trend strength Si=I12+I4+IMASi​=I12​+I4​+IMA​ (0–3).

    Trend filter:

        Asset is eligible if Si≥2Si​≥2 (at least two of three conditions are bullish).

        For equities (SPY, IWM, EEM, VNQ, XLE, XLU), require IMA=1IMA​=1 as one of the two to be eligible; this leans on Faber’s finding that MA filters are especially effective for equity drawdown control.

    Vol‑scaled raw weights:

        For eligible assets, set
        wiraw=Siσ20,i.
        wiraw​=σ20,i​Si​​.

        For ineligible assets, wiraw=0wiraw​=0.

        Normalize: wi=wiraw/∑jwjrawwi​=wiraw​/∑j​wjraw​.

    Risk‑off fallback:

        If no asset passes the trend filter (rare but possible in synchronized sell‑offs), allocate equally between TLT and GLD (0.5/0.5), reflecting evidence that trend‑following and vol targeting often migrate to bonds and gold in crises.

This combines TSMOM (sign of 12‑month return), multi‑horizon trend (12‑ and 4‑month) and MA timing into a single strength score, then blends that with inverse‑vol sizing as in TSMOM implementations that scale positions by realized vol.
Rebalance cadence

    Every 5 trading days (weekly).

        Compute indicators daily but only rebalance weekly to cap turnover; given trend horizons of 4–12 months, signals change slowly, so weekly is sufficient.

        With 10 assets, a full rebalance touches up to 10 positions, i.e., ~10 trades/week ≈ 2 trades/day; in practice fewer positions change, so realized average is close to your target 1 trade/day.

You can add a minimum change threshold (e.g., ignore weight changes < 1 percentage point) to further dampen micro‑rotations.
Asset scope

    All 10 ETFs participate, but their behavior differs by class:

        Equities (SPY, IWM, EEM, VNQ, XLE, XLU): trend and MA filters are particularly meaningful; evidence for TSMOM and MA timing is strongest here.

        TLT, GLD, DBC, UUP: TSMOM is documented for bond, commodity and currency futures; ETF proxies should inherit much of this. MA filters are still useful but perhaps less critical than for equities.

        UUP is a low‑vol diversifier; trend signals will often be weak; it naturally receives smaller weights via inverse‑vol scaling unless its trend score is high.

Parameter ranges

What to optimize:

    R12R12​ lookback: 8–16 months (168–336 trading days). Standard TSMOM uses 12 months; variations around this are robust.

    R4R4​ lookback: 3–6 months (63–126 days); empirical trend papers often find 3–12 month windows effective and recommend combining several.

    MA length: 150–250 days; 200‑day (≈10 months) is the classic approximation of Faber’s 10‑month SMA on monthly data.

    Vol window σ20σ20​: 10–40 days; Harvey et al. use half‑life 20 days in examples, and trend implementations often use 20‑30 day vol.

    Rebalance period: 5–10 trading days; shorter increases turnover without much signal gain given slow horizon; longer risks missing turning points.

Expected trade profile

    Holding period: typically several months; trends persist 3–12 months on average per TSMOM findings.

    Turnover: weekly rebalance with slow signals and thresholding likely yields ~20–40% portfolio turnover per month, translating into roughly 1 trade/day across the universe.

    Cross‑asset behavior:

        In strong equity bull trends, equities will dominate weights, especially higher‑trend ones like SPY/IWM/XLE, with some allocation to trend‑positive TLT/GLD/DBC.

        In crises where equities breach MA and have negative 12‑month returns, weights migrate to TLT, GLD, and occasionally UUP, mimicking managed futures behaviour documented to be crisis‑friendly.

Evidence

    TSMOM profitability across equities, bonds, commodities, currencies with 12‑month lookback and 1‑month holding.

    Moving‑average timing rules stochastically dominating buy‑and‑hold on equity portfolios and improving drawdowns.

    Volatility scaling improving Sharpe for risk assets and reducing tail risk for all assets.

    Combining multiple trend horizons for robustness in trend‑following systems.

This SET is essentially a long‑only managed‑futures‑style allocation applied to ETFs, mapped into a target‑weight framework.
Risks and failure modes

    Whipsaws in sideways markets: Trend filters lag; in choppy, low‑vol regimes, MA and TSMOM signals can flip repeatedly, generating losses and extra trading. This is the classic trend‑following trade‑off.

    Trend crowding / capacity: While the universe is small, trend‑following is a crowded style; correlations to other trend managers can spike in crises, though the long‑only ETF implementation mitigates some issues.

    Bond and commodity nuances: Harvey et al. show vol targeting boosts Sharpe primarily for equities and credit, with negligible Sharpe gain for bonds, currencies and commodities (though tail risk still improves). Over‑reliance on vol scaling for TLT/GLD/DBC may add complexity without much edge; keep those parameters conservative.

    Parameter overfitting: There is a wide range of plausible lookbacks; over‑tuning to this 10‑asset universe risks curve‑fitting. Using canonical values (e.g., 12‑ and 4‑month, 200d MA) and testing robustness bands is important.

SET 2 — Dual momentum‑style rotation with equity focus and defensive sleeve

High‑level:
Use relative momentum within equities to choose leaders, gated by absolute equity trend; when equity momentum is weak, rotate into defensive assets (TLT, GLD, UUP, XLU/VNQ) based on their own momentum. This is inspired by Antonacci’s GEM dual momentum but extended to a 10‑ETF universe with cross‑sectional rotation, still using daily data and a 1–2 week rebalance.
Indicators

    Lookback returns:

        12‑month total return R12R12​ for each ETF (as in GEM and cross‑asset momentum literature).

        6‑month total return R6R6​ to get some sensitivity to more recent relative performance and avoid overly stale rankings.

    Absolute momentum for US equity:

        12‑month R12R12​ for SPY: used as primary “risk‑on vs risk‑off” gauge, as in GEM.

    Slow trend filter for risk‑off assets:

        200‑day MA for TLT and GLD; if both are below MA with negative 12‑month returns, we treat “risk‑off” assets as unattractive and hold more cash‑like exposure (here approximated with UUP or simply under‑investing).

No extra oscillators; the edge is primarily in the momentum/relative strength combination, per academic evidence.
Signal logic

Partition the universe:

    Equity‑risk assets: SPY, IWM, EEM, VNQ, XLE, XLU.

    Defensive assets: TLT, GLD, UUP, DBC (DBC is more cyclical but can serve as a diversifier).

At each decision date tt:

    Risk‑on vs risk‑off decision (absolute momentum, GEM‑style):

        If R12SPY>0R12SPY​>0, we are risk‑on.

        If R12SPY≤0R12SPY​≤0, we are risk‑off.
        This mirrors GEM’s use of 12‑month S&P 500 return vs cash as the absolute momentum gate.

    Risk‑on branch: equity cross‑sectional momentum

        Compute composite equity momentum score for each equity‑risk asset:
        Mi=0.5⋅rank(R12,i)+0.5⋅rank(R6,i)
        Mi​=0.5⋅rank(R12,i​)+0.5⋅rank(R6,i​)

        (ranks within equity‑risk subset, rescaled to ).

        Select top KeKe​ (e.g., 3) equities by MiMi​.

        Set raw weights: equal among top KeKe​, e.g., wiequity=1/Kewiequity​=1/Ke​.

        Allocate a fixed sleeve (e.g., 80%) to this equity basket; remaining 20% goes to best momentum defensive assets (see below) to maintain some diversification, acknowledging Asness et al.’s finding that combining value/momentum or risk/diversifiers tends to improve robustness.

    Risk‑off branch: defensive cross‑sectional momentum

        Compute momentum scores MjMj​ on TLT, GLD, UUP, XLU, VNQ using same 12/6‑month combination.

        Filter out any asset with both negative 12‑month return and price < 200‑day MA to avoid catching a falling knife (leveraging MA timing evidence).

        Allocate 100% to the top KdKd​ (e.g., 2) defensive assets equally. If none pass, park in UUP or the least bad asset.

    Portfolio weights:

        Risk‑on:

            80% into equity leaders (top KeKe​), equal weight.

            20% into defensive leaders (top 1–2 among TLT, GLD, UUP, DBC).

        Risk‑off:

            100% into top KdKd​ defensives.

This structure mirrors GEM (switching between equities and bonds based on absolute and relative momentum) but with more diversification across multiple equity and defensive ETFs.
Rebalance cadence

    Every 10 trading days (~2 weeks).

        GEM and many ETF rotation strategies use monthly data to keep turnover low.

        Here, moving to bi‑weekly trading on daily data should still yield relatively slow signal changes because 6–12 month lookbacks dominate, but ensures closer to your ~1 trade/day limit.

        With Ke=3Ke​=3 and Kd=2Kd​=2, maximum trades per rebalance are limited (selling assets that drop out of the top groups and buying replacements).

Asset scope

    All 10 ETFs are potentially used, but structurally:

        Equities dominate in risk‑on regimes, with small defensive buffers.

        TLT and GLD are primary risk‑off anchors, with UUP and XLU/VNQ as diversifiers.

        DBC is treated as a cyclical diversifier rather than core risk‑off; it may have high momentum in inflationary commodity booms.

Parameter ranges

    Lookbacks:

        12‑month: fixed or 9–15 months, as in dual momentum and cross‑asset momentum literature.

        6‑month: 3–9 months.

    KeKe​: 2–4 (number of equity leaders). Too small increases concentration; too large dilutes momentum.

    KdKd​: 1–3.

    Equity sleeve share in risk‑on: 60–90%.

    Rebalance period: 10–20 trading days.

These should be stress‑tested via walk‑forward splits, but they sit squarely within ranges used in practice and research.
Expected trade profile

    Holding period:

        In strong trends, leading equities and defensives may stay in the top ranks for many months; rotation is mostly at turning points and relative leadership shifts.

    Turnover:

        Bi‑weekly rebalance with 5 active positions (3 equity, 2 defensive) implies at most 5 sells and 5 buys per rebalance, but typically fewer, so ~0.5–1 trades/day.

    Cross‑asset behavior:

        In global equity bull markets, portfolio is mostly SPY/IWM/EEM/VNQ/XLE with a small TLT/GLD/UUP sleeve.

        In equity bear markets (negative SPY 12‑month), portfolio swings into TLT/GLD/UUP/XLU, consistent with evidence that Treasuries and some defensives perform well in equity stress.

Evidence

    Value and Momentum Everywhere: robust momentum across asset classes supports relative momentum rankings among ETFs.

    Antonacci’s GEM: dual momentum between US stocks, ex‑US stocks and bonds with 12‑month lookbacks and monthly rebalance has worked in and out of sample since 1950.

    ETF rotation studies: monthly momentum‑based rotation among SPY/EEM/TLT has beaten buy‑and‑hold with lower drawdowns over 20+ years, albeit with a tough 2022.

    Sector rotation and macro sector momentum further support cross‑sectional momentum across equity sectors and styles.

Risks and failure modes

    Momentum crashes: Momentum strategies can suffer during sharp market reversals, especially when leaders become laggards quickly (e.g., post‑crisis rebounds). The dual momentum risk‑off gate mitigates but does not eliminate this.

    Regime dependency: GEM‑style approaches do well when there is a clear equity vs bond divergence and long secular bond bull markets; they can struggle if both equities and long bonds are weak (e.g., inflation shocks). Including GLD and DBC helps, but backtests show 2022‑style environments to be challenging.

    Concentration risk: Even with Ke=3,Kd=2Ke​=3,Kd​=2, this SET can be concentrated (e.g., mostly SPY and TLT). This is partly intentional but increases idiosyncratic ETF risk.

    Trade frequency: If you push rebalance down to weekly, turnover rises; if you keep it monthly, trade frequency may fall below your target. Bi‑weekly is a compromise but needs empirical verification.

SET 3 — Inverse‑vol / risk‑parity core with trend gating

High‑level:
Use a risk‑parity style inverse‑vol allocation across all 10 assets as the baseline, but gate risk assets (equities, commodities, REITs) with slow trend filters so that in downtrends their risk contribution is reduced and shifted to Treasuries and gold. This combines evidence that vol targeting improves Sharpe and tail risk with MA/TSMOM timing.
Indicators

    20‑day and 60‑day realized volatility σ20,σ60σ20​,σ60​ for each ETF.

        Role: capture short‑ and medium‑term volatility; combined for more stable risk estimates, as in Harvey et al. and risk parity implementations.

    60‑day correlation matrix between ETF returns.

        Role: optional enhancement to move from pure inverse‑vol to true risk parity (equal risk contributions incorporating correlations).

    Slow trend filter per asset:

        Either 200‑day MA or 12‑month return sign, as in SET 1 and Faber’s work.

        For simplicity, define trend flag Ti=1Ti​=1 if price > SMA200200​ and 0 otherwise.

    Equity stress indicator:

        Fraction of equity‑risk assets (SPY, IWM, EEM, VNQ, XLE, XLU) with Ti=0Ti​=0.

        Role: detect high‑vol, bearish equity regimes where conditional vol‑targeting and allocation toward Treasuries has been shown to help.

Signal logic

    Baseline inverse‑vol weights:

        Compute blended volatility σ~i=0.5σ20,i+0.5σ60,iσ~i​=0.5σ20,i​+0.5σ60,i​.

        Set raw risk‑parity weight proxy wibase=1/σ~iwibase​=1/σ~i​.

        Normalize to sum to 1.

    This is a simplified form of risk parity; full equal risk contribution would adjust for correlations but is more complex.

    Trend gating for risk assets:

        For equities, VNQ, XLE, DBC: multiply baseline weights by trend flag TiTi​. If Ti=0Ti​=0, reduce weight (e.g., set to α⋅wibaseα⋅wibase​ with α∈[0,0.3]α∈[0,0.3] or to zero).

        For TLT and GLD: do not fully zero out in downtrends; allow them to retain at least baseline weights, since they often act as crisis hedges and vol‑targeting is less about Sharpe and more about tail risk there.

    Equity stress overlay:

        If more than, say, half of equity‑risk assets have Ti=0Ti​=0, treat this as a high‑vol equity regime.

        In this state, increase the risk budget for TLT and GLD by reallocating some of the suppressed equity/DBC weights to them, mirroring findings that dynamic allocation from equities to Treasuries during high‑vol states can generate extra excess returns on top of vol targeting.

        For example:

            Compute total weight cut from risk assets due to Ti=0Ti​=0.

            Reallocate 70% of this to TLT and 30% to GLD (or optimize that ratio).

    Normalization:

        After trend gating and stress overlay, renormalize all weights to sum to 1.

        Optionally cap individual weights (e.g., max 30–40%) to avoid extreme concentration in TLT or GLD as seen in unconstrained minimum‑variance portfolios.

Rebalance cadence

    Every 10 trading days, matching your target trade frequency:

        Vol estimates and MAs change slowly; 10‑day updates are enough.

        In quiet regimes, weights move gradually; in high‑vol regimes, changes are larger but less frequent due to trend filters.

Asset scope

    All 10 ETFs, with differentiation:

        Equities, VNQ, XLE, DBC: trend‑gated risk assets; their weights shrink in downtrends.

        TLT, GLD, UUP, XLU: “defensive”/stability assets that pick up risk budget during equity stress.

Parameter ranges

    Vol windows: σ20σ20​ and σ60σ60​ are standard; you might explore 10–30 and 40–90 day windows respectively.

    MA length: 150–250 days.

    Equity downtrend multiplier αα: 0–0.5 (0 = fully zeroed, 0.5 = half weight retained).

    Equity stress threshold: 40–60% of equities in downtrend.

    Rebalance: 5–15 trading days.

    Max per‑asset cap: 25–40%.

Expected trade profile

    Holding period: dominated by slow vol/trend dynamics; positions in low‑vol trend‑up assets (e.g., XLU, TLT, GLD) can persist for months.

    Turnover: in normal regimes, adjustments are small; equity stress regimes trigger more sizable reallocations but relatively infrequently. Expect turnover somewhat lower than SET 1, but with 10‑day rebalance and multiple assets in play, you should still average around 1 trade/day.

    Cross‑asset behavior:

        In calm bull markets, equities and VNQ/XLE get decent risk‑parity weights; TLT/GLD remain meaningful but smaller.

        In high‑vol equity bear markets, equity weights are cut and reallocated towards TLT/GLD, echoing conditional vol‑targeting suggestions in the literature.

Evidence

    Harvey et al. show volatility‑scaled equity portfolios and risk‑parity style portfolios across equities, bonds and commodities achieve higher Sharpe and reduced left‑tail outcomes, with vol scaling particularly beneficial for risk assets.

    Risk parity tutorials and ETF research demonstrate that inverse‑vol or risk‑parity weights across equities and bonds deliver more balanced risk and competitive returns versus equal weight portfolios.

    MA trend filters have a long history of improving drawdowns on equity and multi‑asset portfolios.

    Conditional volatility targeting papers show that dynamic allocation from equities to Treasuries during high‑volatility states generates additional excess returns and reduces drawdowns versus unconditional vol targeting.

Risks and failure modes

    Bond/equity correlation regime shifts: Risk parity assumes low or negative stock‑bond correlation; when both sell off together (e.g., inflation shock), concentrating into TLT can be harmful. GLD and UUP help but may not fully offset this.

    Estimation error in vol/covariances: With only 10 assets, covariance estimation can be noisy, especially with short windows; simplifying to inverse‑vol rather than full risk parity reduces but does not eliminate this.

    Under‑participation in equity rallies: Trend‑gating can leave the portfolio underweight equities during sharp V‑shaped recoveries, lagging a simple 60/40 or SET 2, especially if MA filters are slow.

    Complexity vs edge: Compared to SET 1, this SET adds covariance estimation and more state logic. The incremental edge versus a simpler trend+vol scheme is plausible but not guaranteed; empirical testing is needed.

How I’d prioritize the SETs

    SET 1 (Multi‑asset trend + vol scaling) is the most structurally robust and closest to well‑documented managed‑futures style strategies adapted to long‑only ETFs, with strong cross‑asset evidence and straightforward implementation.

    SET 2 (Dual momentum‑style rotation) is attractive if you want a more concentrated, equity‑centric profile with clear, interpretable decisions and a lot of literature and practitioner experience behind it, but it is more exposed to momentum crashes and regime shifts like 2022.

    SET 3 (Risk‑parity with trend gating) is conceptually sound and aligns with institutional risk‑parity practice, but adds estimation risk and complexity; its edge vs SET 1 is more about risk‑distribution preferences than clear incremental alpha.

All three satisfy your constraints (daily OHLCV, long‑only target weights, multi‑asset, modest turnover) and have published evidence for their core building blocks; the real work from here is in your rolling OOS validation, parameter robustness checks, and interaction with transaction costs and your specific execution layer.

---

## Gemini Deep Research

**Date:**
**Model/mode:**

<paste raw output below>

Quantitative Tactical Asset Allocation and Turnover-Controlled Portfolio SystemsDynamic Multi-Asset Strategy Families: A Comparative SurveyTactical asset allocation across a diverse, multi-asset universe requires a systematic framework to balance capital growth with structural drawdown protection. In designing a system for the ten exchange-traded funds spanning equities (SPY, IWM, EEM, XLE, XLU), long-duration US Treasuries (TLT), commodities (DBC), gold (GLD), and currencies (UUP), several broad families of quantitative strategies present viable candidates. The ultimate selection depends on their capacity to process daily close data, handle target-weight allocations without explicit entry or exit signals, and target an expected trade frequency of approximately one trade per day across the combined universe.The first family is comprised of cross-sectional and time-series momentum strategies, which exploit the well-documented tendency of outperforming assets to continue their outperformance over medium-term horizons. In these systems, assets are ranked relative to one another, and capital is rotated into the top-performing tier. While highly effective at capturing strong macro trends in equities, real estate, and commodities, pure relative strength momentum models suffer from high turnover and severe drawdown vulnerabilities during rapid trend reversals and macroeconomic regime shifts. Under daily close-on-close execution, unconstrained momentum models frequently trigger excessive trading, leading to high transaction costs that erode tactical alpha.The second family consists of optimized risk-budgeting and minimum-variance formulations. Rather than attempting to forecast expected returns, which are notoriously noisy and prone to extreme estimation errors, risk-based frameworks rely on estimated asset volatilities and pairwise correlations to construct diversified portfolios. Minimum-variance optimization and equal risk contribution algorithms determine allocations that minimize the overall portfolio variance or distribute risk exposure equally across the selected holdings. These portfolios exhibit high stability and superior risk-adjusted performance out-of-sample. However, risk-only models are structurally passive with respect to returns and can remain heavily exposed to assets in persistent, long-term downward trends if those assets exhibit low volatility or correlation.The third family encompasses regime-gated canary momentum systems, which decouple trend-following risk detection from the investable universe. Developed extensively by Keller and Keuning, these strategies utilize the absolute momentum of a designated sub-universe of highly sensitive macro assets (such as emerging market equities and aggregate bonds) to determine the broad market regime. When any canary asset flags a breakdown in momentum, the strategy rapidly retreats to defensive holdings. This family provides robust, responsive crash protection while maintaining high capital efficiency during positive regimes.A fourth family, emerging from fixed-income rotation literature, utilizes median-based allocation rules. In contrast to standard momentum strategies that buy the strongest winners and sell the worst losers, median-rotation models hold the middle-ranked assets. Rigorous walk-forward evaluations of duration-rotation strategies across the Treasury yield curve demonstrate that holding the median cohort delivers superior risk-adjusted returns and shallower drawdowns compared to traditional momentum. This alternative momentum anomaly suggests that in certain highly mean-reverting asset classes, such as sovereign fixed income, the middle cohort represents a more stable tactical exposure.Indicator Mechanics, Asset Behavior, and Execution FrictionsTo construct a robust daily close-on-close tactical system, the interaction between indicator mechanics, cross-asset correlations, and trade execution constraints must be analyzed. The asset universe presents a specific structural challenge: correlations between the five primary asset classes are historically low, but correlations within the equity slice—consisting of SPY, IWM, EEM, XLE, and XLU—are moderate to high. A simple unconstrained cross-sectional momentum sort will frequently over-concentrate the portfolio in multiple equity ETFs during equity bull markets, exposing the capital pool to severe joint drawdowns when the broader equity market experiences a systemic shock. Consequently, any viable allocation model must incorporate a mechanism, such as minimum-variance optimization or equal risk budgeting, to dynamically penalize highly correlated assets.Asset behavior also varies across macroeconomic regimes, particularly during inflationary periods. Traditional tactical systems historically relied on long-duration government bonds (TLT) as a reliable defensive asset. However, during periods of rising interest rates and sticky inflation, equities and long-duration bonds experience high positive correlation, leading to simultaneous drawdowns. To manage this risk, the defensive candidate pool must expand beyond Treasuries to include inflation-insensitive assets, such as commodities (DBC), gold (GLD), or short-duration cash proxies (represented by UUP or cash equivalents), and employ absolute momentum filters that penalize assets in structural downtrends.Under daily execution, the target trade frequency of approximately one trade per day across the combined ten-symbol universe imposes a severe execution constraint. Rebalancing ten assets daily generates massive turnover, incurring substantial transaction costs and slippage that degrade performance. Conversely, rebalancing too slowly (e.g., monthly) introduces execution lag, making the strategy slow to react to rapid market inflections. This trade-off requires a drift-aware weight tracking framework and a conditional rebalancing threshold.Between rebalancing dates, asset price changes cause the actual portfolio weights to drift from the target weights. If the portfolio is invested in assets with returns $R_i(t)$, the drifted weights on any day $t$ are modeled as:$$w_i^{\text{drift}}(t) = w_i(t_0) \cdot \frac{P_i(t)/P_i(t_0)}{\sum_{j=1}^{10} w_j(t_0) \cdot \left(P_j(t)/P_j(t_0)\right)}$$where $t_0$ is the last rebalance date, $w_i(t_0)$ is the target weight established on that date, and $P_i(t)$ is the close price of asset $i$ on day $t$.Ignoring this drift in the backtest or execution engine creates a "phantom turnover budget," where the system calculates transaction costs against target weights rather than realized, drifted holdings. By implementing a drift-aware weight tracking algorithm, the target weight vector $w^*(t)$ emitted by the tactical strategy is compared directly to the current drifted weight vector $w^{\text{drift}}(t)$. A rebalance is executed if and only if the absolute turnover deviation exceeds a specified threshold $\tau$ :$$\sum_{i=1}^{10} |w^*_i(t) - w^{\text{drift}}_i(t)| \ge \tau$$This conditional rebalancing threshold prevents high-frequency noise from triggering minor trades, effectively dampening trade frequency to the desired target of one trade per day, while preserving the system's ability to execute immediate portfolio adjustments during major market shifts.Specification of High-Confidence Strategy ConfigurationsTo implement this tactical system, two highly concrete, defensible strategy specifications (SETs) are defined below in order of analytical confidence. Both models operate exclusively on 1D close prices (OHLCV-only inputs), emit a cross-sectional allocation frame at each rebalance point, and output target weights (with NaN signifying complete exclusion from the portfolio).SET 1: Classical Adaptive Asset Allocation with Volatility-Regulated RebalancingThis configuration integrates cross-sectional momentum filters with minimum-variance portfolio optimization, controlled by a daily drift-aware turnover threshold.IndicatorsThe strategy estimates parameters daily using rolling lookback windows applied to close prices.Log Momentum ($M_i(t)$): Calculated over a lookback window of $L_M = 126$ trading days:$$M_i(t) = \ln\left(\frac{P_i(t)}{P_i(t - L_M)}\right)$$Realized Volatility ($\sigma_i(t)$): Calculated over a short lookback window of $L_V = 20$ trading days to ensure rapid responsiveness to market risk :$$\sigma_i(t) = \sqrt{\frac{252}{L_V - 1} \sum_{k=0}^{L_V-1} \left(R_i(t-k) - \bar{R}_i\right)^2}$$where $R_i(t) = \ln(P_i(t)/P_i(t-1))$ and $\bar{R}_i$ is the mean daily return over the window $L_V$.Pairwise Correlation ($\rho_{ij}(t)$): Estimated over a stable, medium-term lookback window of $L_C = 126$ trading days to avoid rank deficiency :$$\rho_{ij}(t) = \frac{\sum_{k=0}^{L_C-1} (R_i(t-k) - \bar{R}_i)(R_j(t-k) - \bar{R}_j)}{\sqrt{\sum_{k=0}^{L_C-1} (R_i(t-k) - \bar{R}_i)^2 \sum_{k=0}^{L_C-1} (R_j(t-k) - \bar{R}_j)^2}}$$Weighted Covariance Matrix ($\Sigma(t)$): Combines stable correlations with highly responsive localized volatilities :$$\Sigma_{ij}(t) = \rho_{ij}(t) \cdot \sigma_i(t) \cdot \sigma_j(t)$$Signal LogicAt the daily close, the allocation frame is computed via the following sequence:Rank all ten assets in the universe by their log momentum $M_i(t)$ in descending order.Select the top $N = 5$ assets (the top 50% of the universe) to form the candidate investment pool.Apply an absolute momentum trend-following filter to each selected asset: if $M_i(t) \le 0$, the asset is discarded from the active pool.Let $K$ represent the number of assets that successfully pass the absolute momentum filter ($0 \le K \le N$).If $K = 0$, the strategy outputs target weights of NaN for all ten symbols, signaling a 100% defensive retreat to cash downstream.If $K > 0$, construct a sub-covariance matrix $\Sigma_K(t)$ containing only the qualified assets. Solve the constrained quadratic minimum-variance problem to find the optimal target weight vector $w^*(t)$ :$$\min_{w} \ w^T \Sigma_K(t) w$$$$\text{subject to: } \sum_{i=1}^K w_i = 1, \quad w_i \ge w_{\min}, \quad w_i \le w_{\max}$$where $w_{\min} = 0.10$ and $w_{\max} = 0.60$ represent structural allocation bounds designed to prevent extreme concentration while maintaining high diversification. Excluded assets (not in the qualified $K$ pool) receive a target weight of NaN.Rebalance Cadence and ExecutionEvaluated daily at the close. The system tracks the daily drifted weight vector $w^{\text{drift}}(t)$ of the portfolio. A trade execution is triggered if and only if the absolute turnover deviation between the newly calculated optimal target weights $w^*(t)$ and the drifted weights $w^{\text{drift}}(t)$ meets or exceeds the turnover threshold $\tau = 0.08$ (8% absolute turnover barrier) :$$\sum_{i=1}^{10} |w^*_i(t) - w^{\text{drift}}_i(t)| \ge 0.08$$If this condition is met, the target weights are updated and executed close-on-close. Otherwise, the weights are frozen at their current drifted values, preventing high-frequency trading noise.Asset ScopeApplies to all ten symbols in the universe (SPY, IWM, EEM, TLT, GLD, DBC, VNQ, UUP, XLE, XLU). High equity-beta assets (equities, energy, utilities, real estate) compete dynamically with safe-havens (bonds, cash, dollar, gold). When risky assets experience downward momentum, the selection pool naturally rotates into fixed income (TLT), currencies (UUP), or cash (NaN), optimized via the covariance matrix to capture the lowest-risk combination.Plausible Parameter Ranges for Optimization$L_M$ (Momentum lookback): $60 - 252$ trading days. Balances trend responsiveness against noise filtration.$L_V$ (Volatility estimation): $10 - 60$ trading days. Captured risk spikes must balance parameter variance.$L_C$ (Correlation estimation): $60 - 252$ trading days. Longer horizons are necessary for covariance matrix stability.$\tau$ (Turnover threshold): $0.05 - 0.20$. Directly scales the average holding period and trade frequency.$w_{\max}$ (Single-asset maximum weight): $0.40 - 0.80$. Limits the maximum allowable concentration in any single asset class.Expected Trade ProfileUnder daily close execution with $\tau = 0.08$, a portfolio-wide rebalance is triggered approximately 1.5 times per month on average. Because only 5 assets are held simultaneously, a rebalance event generates roughly 3 to 5 target adjustments. This achieves the target frequency of approximately one trade per day across the combined portfolio, with an average asset holding period of 15 to 25 trading days.Published EvidenceThe theoretical and empirical framework for Adaptive Asset Allocation is extensively documented by Butler, Philbrick, Gordillo, and Varadi (2012) in Adaptive Asset Allocation: A Primer, published on the SSRN network. Further validation of the minimum-variance optimization overlay on cross-sectional momentum filters is presented by Keller (2014) in Momentum, Markowitz, and Smart Beta: A Tactical, Analytical and Practical Look at Modern Portfolio Theory. These studies demonstrate that AAA portfolios deliver more stable return paths and shallower drawdowns compared to static risk parity and market-cap weighted benchmarks.Risks and Failure ModesThe primary vulnerability of minimum-variance optimization is input estimation error, particularly during sudden, non-stationary market regimes. If volatilities and correlations spike simultaneously across all asset classes—as observed during liquidity panics or rapid, unexpected interest rate hikes—the covariance matrix may fail to provide diversification. In such scenarios, the portfolio's realized volatility will exceed the target, and assets that historically exhibited negative correlation may draw down together.SET 2: Defensive Canary Tactical Rotation with Execution HysteresisThis configuration utilizes a highly sensitive multi-period canary signal to identify systemic stress, combined with cross-sectional relative momentum ranking to select offensive and defensive assets.IndicatorsAnnualized Multi-Period Momentum Score ($\text{Score}_i(t)$): Gages absolute trend strength across four distinct horizons. To ensure short-term responsiveness is mathematically preserved without underweighting front-month data, returns are annualized at each horizon :$$R_{i, m}(t) = \left( \frac{P_i(t)}{P_i(t - \Delta_m)} \right)^{\frac{252}{\Delta_m}} - 1$$where $\Delta_m \in \{21, 63, 126, 252\}$ represents the trading days in 1, 3, 6, and 12-month horizons.$$\text{Score}_i(t) = 12 \cdot R_{i, 21}(t) + 4 \cdot R_{i, 63}(t) + 2 \cdot R_{i, 126}(t) + 1 \cdot R_{i, 252}(t)$$This canonical weighting places 40% of the overall score on the most recent 1-month annualized return, providing rapid signaling.Relative Momentum Ratio ($RM_i(t)$): Compares the current close price relative to the 13-month simple moving average :$$RM_i(t) = \frac{P_i(t)}{\frac{1}{13} \sum_{k=0}^{12} P_{month-end}(t - 21k)}$$Signal LogicAt each daily close, the strategy classifies the ten symbols into specific functional sleeves to evaluate and construct allocations:Canary Sentinel Universe: SPY and TLT.Offensive Asset Universe: IWM, EEM, GLD, DBC, VNQ, XLE, XLU (7 symbols).Defensive Asset Universe: UUP, TLT, GLD (3 symbols).First, calculate the annualized momentum score $\text{Score}_j(t)$ for the two canary assets: SPY and TLT. Count the number of canary assets with negative or flat momentum, denoted as $n_{bad}$ :$$n_{bad} = \sum_{j \in \{\text{SPY}, \text{TLT}\}} \mathbb{I}\left(\text{Score}_j(t) \le 0\right)$$Second, determine the Cash-Bond Fraction ($CBF(t)$), which dictates the allocation split between the offensive and defensive asset sleeves:$$CBF(t) = \frac{n_{bad}}{2}$$If $n_{bad} = 0$: $CBF(t) = 0.00$. The portfolio is fully offensive.If $n_{bad} = 1$: $CBF(t) = 0.50$. The portfolio is defensive-hedged, allocating 50% to the offensive sleeve and 50% to the defensive sleeve.If $n_{bad} = 2$: $CBF(t) = 1.00$. The portfolio is fully defensive, allocating 100% to the defensive sleeve.Third, determine allocations within each sleeve:Offensive Sleeve Allocation (Total Weight $= 1 - CBF(t)$): Rank the seven offensive assets by their Relative Momentum Ratio $RM_i(t)$. Select the top $T = 3$ performing assets. Allocate equally to them: $w_i = (1 - CBF(t)) / 3$. Apply an absolute momentum filter: if any of the selected top 3 assets has $RM_i(t) < 1.00$, replace that asset's share entirely with cash (output NaN).Defensive Sleeve Allocation (Total Weight $= CBF(t)$): Rank the three defensive assets (UUP, TLT, GLD) by their Relative Momentum Ratio $RM_i(t)$. Select the single best defensive asset $D^*$. Allocate the entire defensive weight to this asset: $w_{D^*} = CBF(t)$. Apply the absolute cash filter: if $RM_{D^*}(t) < 1.00$, replace this defensive exposure entirely with cash (output NaN).Rebalance Cadence and ExecutionEvaluated on a fixed bi-weekly scheduled rebalance cadence (every ten trading days). To satisfy the daily close-on-close setup while preventing high-frequency trading between scheduled dates, the strategy implements execution hysteresis. At each daily close, the system calculates the daily drifted weight of the existing holdings. If the canary status shifts abruptly (e.g., $n_{bad}$ changes from $0$ to $1$ or $2$), the scheduled bi-weekly rebalance is bypassed, and an immediate emergency rebalance is executed at the close to shift capital to the defensive sleeve. Under normal market conditions, minor daily weight changes are ignored.Asset ScopeApplies to the ten-asset universe. The functional classification is supported by asset characteristics: SPY and TLT represent the macro debt-and-equity canary indicators ; the offensive sleeve captures high-beta return drivers ; and the defensive sleeve utilizes the safe-haven properties of gold (GLD), long Treasuries (TLT), and the US dollar index (UUP) to preserve capital.Plausible Parameter Ranges for OptimizationCanary breadth threshold $B$: Fixed at $2$ (matching the SPY and TLT pair).$T$ (Top offensive assets): $2 - 4$ assets. Controls the concentration of the offensive sleeve.Momentum lookback periods: Can be optimized within bounds $$ trading days to adjust short-term sensitivity.Sleeve allocation targets: Fully binary ($0\%$, $50\%$, $100\%$) or continuous linear fractions based on the exact count of negative canary indicators.Expected Trade ProfileScheduled bi-weekly rebalancing, combined with the daily canary regime monitoring, yields an average of $0.6$ to $1.2$ trades per day across the combined universe. During stable trends, the portfolio rebalances every ten days, adjusting weights across the 3 or 4 held assets. During trend inflections, the canary trigger immediately rotates the entire portfolio into cash or defensive assets, generating highly concentrated trade clusters that match the daily close target execution profile.Published EvidenceThe theoretical basis for Canary Regime Gating was published by Keller and Keuning (2018) in Breadth Momentum and the Canary Universe: Defensive Asset Allocation (DAA), on the SSRN network. The integration of annualized multi-period momentum scoring and its outperformance over static portfolios is further validated by Kipnis (2019) in Ilya Kipnis' Defensive Adaptive Asset Allocation (KDA). Keller's research demonstrates that utilizing a separate canary universe dramatically reduces the cash drag typically associated with trend-following strategies while preserving drawdown protection.Risks and Failure ModesThe primary risk is whipsaw during volatile, directionless sideways markets. If SPY or TLT frequently cross their multi-period momentum thresholds back and forth, the strategy will repeatedly trigger transaction costs by rotating between offensive assets and defensive cash proxies without capturing a sustained trend. This risk is mitigated by the relative momentum moving average denominator, which acts as a smoothing filter.Comparative Performance and Validation ProtocolsTo evaluate these tactical configurations, their historical risk, return, and operational characteristics must be compared against a standard benchmark. The following table provides estimated performance metrics compiled from empirical backtesting literature on multi-asset tactical allocation.Operational MetricS&P 500 Equity BenchmarkSET 1: Adaptive Asset AllocationSET 2: Defensive Canary Tactical RotationTypical Annualized Return$9.5\% - 11.5\%$ $11.0\% - 14.0\%$ $12.0\% - 16.0\%$ Typical Maximum Drawdown$-33.0\% \text{ to } -55.0\%$ $-11.0\% \text{ to } -15.0\%$ $-9.0\% \text{ to } -17.0\%$ Typical Sharpe Ratio$0.50 - 0.65$ $0.85 - 1.05$ $0.90 - 1.20$ Annual Portfolio Turnover$5\% - 15\%$ $250\% - 300\%$ $400\% - 480\%$ Expected Trade FrequencyMinimal (< 5 trades/year)~1.0 trade/day (DATT $\tau = 0.08$)~0.8 trades/day (Bi-weekly + Canary bypass)Core Regime Asset PoolNone (100% Equity)Integrated Covariance OptimizationSPY & TLT Gating Primary Structural Failure ModeProlonged Equity Bear MarketsHigh Volatility Correlation SpikesSideways Volatile WhipsawsTo prevent overfitting and ensure structural robustness under estimation error, the validation system must implement a strict rolling out-of-sample walk-forward protocol.First, divide the historical data into an in-sample selection set (e.g., $3$ years) and a held-out evaluation set (e.g., $1$ year).Second, within each in-sample selection set, run optimization sweeps over the parameter grids ($L_M, L_V, L_C, \tau, T$). The objective is not to maximize the Sharpe ratio, but to find the parameter region characterized by stable, risk-adjusted returns and consistent trade frequency.Third, freeze the selected parameters and execute the model out-of-sample on the held-out evaluation set. Roll the windows forward by one year, expanding the historical sample, and repeat the walk-forward calibration.Finally, the simulated execution engine must incorporate a transaction cost penalty of at least $0.10\%$ (10 basis points) one-way to account for the bid-ask spread and broker commissions. This penalty must act directly on the daily drifted holdings of the portfolio ($w^{\text{drift}}$), ensuring that the turnover-control mechanism is penalizing the actual trades executed rather than notional target changes. By utilizing this rigorous validation protocol, the system can confirm the structural viability and out-of-sample robustness of the selected tactical asset allocation configuration.

---

## Convergence Notes

### SET mapping

| # | Perplexity | Gemini | Same family? |
|---|-----------|--------|-------------|
| 1 | Multi-asset trend + vol scaling (TSMOM + MA + inverse-vol) | Adaptive Asset Allocation (momentum + min-variance optimization) | **Yes** — both are momentum-filtered, vol-aware multi-asset allocation |
| 2 | Dual momentum rotation (GEM-style, equity vs defensive) | Defensive Canary Tactical Rotation (Keller DAA/KDA) | **Yes** — both are regime-gated rotation with offensive/defensive sleeves |
| 3 | Inverse-vol risk parity + trend gating | (not produced) | Perplexity only |

### Indicator convergence

| Indicator | Perplexity | Gemini | Agree? |
|-----------|-----------|--------|--------|
| Medium-term momentum (3-12mo return) | R12 + R4 (252d, 84d) | Log momentum 126d + multi-period (21/63/126/252d) | **Yes** — both use ~6mo as primary, longer as confirmation |
| SMA / MA trend filter | 200d SMA binary gate | Absolute momentum gate (M > 0) and RM ratio (price / 13mo SMA) | **Yes** — both use MA or equivalent as trend gatekeeper |
| Realized volatility | 20d (optionally blended with 60d) | 20d for vol, 126d for correlations | **Yes** — short vol window, longer for stability |
| Correlation / covariance | Not in SET 1-2; mentioned in SET 3 | Full covariance matrix in SET 1 (min-variance) | **Diverge** — Gemini relies on covariance optimization; Perplexity uses simpler inverse-vol |
| Multi-period momentum scoring | Not explicit (uses two discrete lookbacks) | Explicit annualized 4-horizon weighted score (12R1 + 4R3 + 2R6 + 1R12) | **Diverge** — Gemini's scoring is more structured |

### Structural convergence

| Aspect | Perplexity | Gemini | Agree? |
|--------|-----------|--------|--------|
| Rebalance cadence | Weekly (5d) or bi-weekly (10d) | Daily with turnover threshold tau=0.08, or bi-weekly + canary bypass | **Partial** — both land on ~weekly effective frequency, different mechanisms |
| Turnover control | Min weight-change threshold | Drift-aware turnover barrier (formal L1 norm threshold) | **Same goal, Gemini more rigorous** |
| Asset-class-specific logic | Equity vs defensive partition; equities require MA gate | Canary (SPY+TLT) vs offensive vs defensive sleeves | **Yes** — both split universe into risk-on and risk-off pools |
| Risk-off destination | TLT + GLD (50/50) or best-momentum defensives | UUP, TLT, GLD ranked by momentum; or all-NaN (cash) | **Yes** — TLT and GLD are primary safe havens in both |
| Position count | 3-5 active at a time | 3-5 active at a time | **Yes** |
| Trade frequency estimate | ~1 trade/day | ~0.8-1.2 trades/day | **Yes** |

### Key citations overlap

| Source | Perplexity | Gemini |
|--------|-----------|--------|
| Moskowitz, Ooi, Pedersen — TSMOM | Yes (SET 1) | Implicit (momentum across asset classes) |
| Faber — MA timing / GTAA | Yes (SET 1, 2) | Implicit (absolute momentum filter) |
| Antonacci — GEM dual momentum | Yes (SET 2) | Implicit (regime gating concept) |
| Keller & Keuning — DAA canary | No | Yes (SET 2) |
| Kipnis — KDA | No | Yes (SET 2) |
| Butler, Philbrick et al. — AAA | No | Yes (SET 1) |
| Harvey et al. — vol scaling | Yes (SET 1, 3) | Implicit |
| Asness et al. — Value and Momentum Everywhere | Yes (SET 2) | Implicit |

### Strong convergence (both agree with evidence)

1. **Momentum + trend filter + vol-awareness as the core building blocks.** Both independently arrived at: rank assets by medium-term momentum, gate with an absolute trend filter (MA or sign of return), size by inverse volatility or minimum variance. This is the highest-confidence finding.

2. **Regime-gated offensive/defensive rotation as the second family.** Both propose a binary or graduated risk-on/risk-off switch based on broad market momentum, with concentrated rotation into defensive assets (TLT, GLD, UUP) when risk is off.

3. **Weekly-ish effective rebalance cadence** with 3-5 active positions yields ~1 trade/day. Both models converge on this operational profile independently.

4. **TLT and GLD as primary defensive assets.** Both treat these as the core risk-off destination across all SETs.

5. **Whipsaw in sideways markets is the primary failure mode** for both families. Neither claims to solve it — both acknowledge it as the structural cost of trend-following.

### Divergence (investigate further)

1. **Covariance optimization vs inverse-vol simplicity.** Gemini SET 1 uses full min-variance optimization (quadratic solver with covariance matrix). Perplexity uses simple inverse-vol weighting. The question is whether the added complexity of covariance estimation actually helps with only 10 assets, or introduces estimation noise that hurts. Perplexity explicitly flags this as a risk in its SET 3. This is testable — implement both and compare on rolling OOS.

2. **Canary universe concept.** Gemini SET 2 uses a dedicated canary pair (SPY + TLT) to gate the entire portfolio, separate from the investable universe. Perplexity SET 2 uses SPY's own absolute momentum as the gate. Keller's canary approach is well-cited but adds a structural dependency on exactly two assets. Worth testing both gate mechanisms.

3. **Multi-period momentum scoring.** Gemini's 4-horizon annualized score (12R1 + 4R3 + 2R6 + R12) is more granular than Perplexity's two discrete lookbacks. The weighting toward recent returns makes it more responsive but potentially more whipsaw-prone. Testable parameter.

4. **Drift-aware turnover threshold.** Gemini introduces a formal L1-norm turnover barrier (tau) that controls trade frequency continuously. Perplexity uses fixed rebalance dates with optional min-change filters. Gemini's approach is more elegant for hitting a specific trade frequency target. This is an execution-layer concern rather than a strategy concern — could be applied to any SET.

5. **Perplexity SET 3 (risk parity + trend gating) has no Gemini counterpart.** Gemini surveyed risk-budgeting as a family but chose not to produce a standalone SET for it, instead folding min-variance into SET 1. This suggests lower independent confidence in pure risk-parity as a standalone approach for this universe.
