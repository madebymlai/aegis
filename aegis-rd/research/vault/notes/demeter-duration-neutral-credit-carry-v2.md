---
title: Demeter Duration-Neutral Credit Carry V2
date: 2026-07-13
topic: credit-carry
status: proposed
related:
  - "[[the-tiered-strategy-roster]]"
  - "[[demeter-credit-carry-rewrite-design]]"
  - "[[paired-floor-strategy-evaluation]]"
tags:
  - note
  - demeter
  - carry
  - credit
  - portfolio-construction
---

# Demeter Duration-Neutral Credit Carry V2

> [!abstract] Decision
> The completed V2 experiment used four unhedged USD share classes. Its active-versus-static result remains informative about the weak maturity-selection opportunity, but it is not a clean test of the floor sleeve in an EUR-base book because USD/EUR translation dominated recent wrapper returns. The next run must retain the same USD corporate-credit exposures through genuine EUR-hedged share classes. Continue to compare one static equal-weight control with one long-only active portfolio whose IG/HY weights and contemporaneous modified duration exactly match that control.

## Sleeve contract

The floor in [[the-tiered-strategy-roster]] needs a concave income engine opposite Atalanta's convex trend stream. Demeter therefore earns its slot by collecting a calm-market premium net of costs while accepting that trend, not carry, pays in dislocations. Merely lowering volatility through shorter duration does not satisfy that contract.

The existing credit-bucket rewrite repaired the old distribution-yield measurement and made the experiment causal and executable. Its locked winner nevertheless selected the strongest duration controls (`25` basis points of duration penalty and a `4.0` duration cap), while the paired floor read showed lower drawdown and higher Sharpe but lower MPPM certainty equivalent. That makes the present strategy a valid `credit_income` challenger, not evidence of a carry premium.

## What the primary evidence says

Koijen, Moskowitz, Pedersen and Vrugt define credit carry as credit spread over the risk-free rate plus roll-down on the credit curve, using duration-adjusted portfolios.[^koijen] FTSE Russell reaches the same construction conclusion operationally: maximize carry while matching the starting index's duration, because otherwise excess performance can be an interest-rate exposure. Its unconstrained corporate implementation exceeded 200% annual turnover, and bucket caps materially reduced that turnover.[^ftse]

MSCI uses bond-level OAS as its corporate-bond carry descriptor, standardizes it inside the parent universe, and applies selection and turnover buffers.[^msci] Israel, Palhares and Richardson show why risk control is not cosmetic in corporate bonds: spreads and durations vary far more than equity betas, so characteristic portfolios can inherit large market exposures; they use duration-times-spread to organize ex-ante credit beta.[^ipr] Andreani, Palhares and Richardson further warn that total bond returns are not credit excess returns and that duration matching is more accurate than maturity matching when isolating the credit component.[^returns]

> [!warning] Honest name for the free-data signal
> The public iShares analytics surface used by Aegis exposes bond-level yield-to-worst and modified duration but not OAS or effective spread duration. V2 can therefore produce a **duration-matched Treasury excess-yield proxy**, not OAS and not complete credit carry. Credit-curve roll-down and expected loss remain absent. Code, reports and articles must preserve that distinction.

Modified-duration neutrality removes the principal Treasury-rate confound, but it does not guarantee spread-duration or DTS neutrality. With only four funds and no public spread-duration field, matching total capital, IG/HY weight, modified duration and DTS simultaneously would generally eliminate the remaining active degree of freedom. V2 must therefore report proxy DTS, approximately `modified_duration × excess_yield_proxy`, and reject a carry interpretation if the active result is explained by consistently taking more of that credit beta.

## Signal contract

Use the existing dated UCITS holdings and matching US iShares security analytics. For each matched bond $j$ in fund $i$ at observation date $t$:

$$
x_{j,t} = y^{\mathrm{YTW}}_{j,t} - y^{\mathrm{UST}}_t(D_{j,t})
$$

where both yields are first converted to the same compounding convention, $D_{j,t}$ is modified duration, and $y^{\mathrm{UST}}_t(D)$ is the fitted nominal Treasury curve evaluated at that duration. Aggregate through actual UCITS holding weights and subtract the fund's annual expense ratio:

$$
c_{i,t} = \frac{\sum_j h_{i,j,t}x_{j,t}}{\sum_j h_{i,j,t}} - \mathrm{TER}_i
$$

The Treasury source is the Federal Reserve Board's Gürkaynak-Sack-Wright nominal curve. It supplies daily Svensson parameters and fitted zero-coupon yields from 1961 onward, is normally updated weekly, and can revise historical vintages.[^gsw-data][^gsw-paper] The external-data module must consequently own fetch, schema validation, content-addressed immutable caching, atomic publication, vintage identity and selection of the latest cached snapshot when the network is unavailable. For every holdings observation, use only a Treasury curve dated on or before the holdings `as_of_date`.

The proxy is computed security by security before aggregation. Subtracting one Treasury yield from an already aggregated fund YTW would mix bonds with different durations and coupon structures and is not acceptable.

## Portfolio contract

The completed V2 experiment used these four comparable but currency-unhedged USD UCITS lines:

- `SDIG.LSEETF`: short IG;
- `LQDE.LSEETF`: broad IG;
- `SDHY.LSEETF`: short HY;
- `IHYU.LSEETF`: broad HY.

### EUR-base correction

Trading an unhedged USD share class on an EUR exchange does not hedge its currency exposure. For the next EUR-base experiment, replace each bucket with a share class whose mandate explicitly hedges the underlying USD portfolio into EUR:

| Bucket | Completed experiment | EUR-hedged replacement | ISIN | EUR trading line |
| --- | --- | --- | --- | --- |
| Short IG | `SDIG.LSEETF` | UBS BBG US Liquid Corporate 1-5 UCITS ETF hEUR acc | `LU1048315243` | `UEF8`, Xetra |
| Broad IG | `LQDE.LSEETF` | iShares USD Corporate Bond UCITS ETF EUR Hedged (Dist) | `IE00BF3N6Y61` | `LQEE`, LSE |
| Short HY | `SDHY.LSEETF` | PIMCO US Short-Term High Yield Corporate Bond UCITS ETF EUR Hedged Acc | `IE00BD26N851` | `STEA`, LSE |
| Broad HY | `IHYU.LSEETF` | iShares USD High Yield Corporate Bond UCITS ETF EUR Hedged (Dist) | `IE00BF3N7102` | `IHYE`, LSE or Xetra |

All four replacements preserve USD corporate-credit exposure while reducing USD/EUR translation at the share-class level.[^ubs-uef8][^blackrock-lqee][^pimco-short-hy][^blackrock-ihye] Their common history begins on 11 December 2017, when the PIMCO EUR-hedged short-HY share classes launched, so they cover the full 2020-2026 evaluation window.

Prefer accumulating `STEA` (`IE00BD26N851`) for the short-HY bucket. It retains income inside the ETF, avoiding cash drag and dependence on dividend reinvestment or perfectly adjusted distributions. `STHE` (`IE00BF8HV600`) is the distributing share class of the same underlying PIMCO fund and is the fallback if IBKR cannot qualify or trade `STEA`; it distributes monthly and has broader exchange coverage. Both are EUR hedged, launched on 11 December 2017 and charge the same `0.60%` management fee.[^pimco-short-hy]

#### IBKR validation — 14 July 2026

All four preferred ISINs qualified through Aegis's normal Nautilus/IBKR provider on the running paper gateway. The UBS fund does **not** qualify under the researched Xetra ticker `UEF8`: IBKR's canonical local symbol is `CBUS5E`, its primary exchange is `EBS`, and the provider's MIC-canonical instrument ID is `CBUS5E.XBRU`. No local-symbol override or raw-contract bypass is allowed. Because its last-trade history is thin, future configs must declare it as `CBUS5E.XBRU:QUOTE`; that declaration preserves `CBUS5E.XBRU` as the executable instrument while sourcing BID and ASK bars and marking at their derived midpoint.

| Role | Config identity | ISIN | IB primary exchange | Local symbol | Currency | Security / stock type | conId | Minimum price increment at reference price |
| --- | --- | --- | --- | --- | --- | --- | ---: | ---: |
| Short IG | `CBUS5E.XBRU:QUOTE` | `LU1048315243` | `EBS` | `CBUS5E` | EUR | `STK` / `ETF` | `189557184` | `0.0005` |
| Broad IG | `LQEE.LSEETF` | `IE00BF3N6Y61` | `LSEETF` | `LQEE` | EUR | `STK` / `ETF` | `290399231` | `0.0005` |
| Short HY | `STEA.LSEETF` | `IE00BD26N851` | `LSEETF` | `STEA` | EUR | `STK` / `ETF` | `299621493` | `0.02` |
| Broad HY | `IHYE.LSEETF` | `IE00BF3N7102` | `LSEETF` | `IHYE` | EUR | `STK` / `ETF` | `309787178` | `0.0005` |
| Short-HY fallback | `STHE.LSEETF` | `IE00BF8HV600` | `LSEETF` | `STHE` | EUR | `STK` / `ETF` | `136481004` | `0.01` |

IBKR `ADJUSTED_LAST` was requested through the normal Aegis history seam for the exact `2020-08-10` through `2026-07-01` window. Every series covers both endpoints, is unique, and contains no null or non-positive close. `STEA`, `LQEE`, `IHYE`, and fallback `STHE` returned respectively `1,464`, `1,484`, `1,487`, and `1,487` observations, each with a maximum five-day calendar gap. `CBUS5E` returned only `1,339` adjusted-last observations and a twelve-day maximum gap. The config-level `:QUOTE` path resolves that execution-marking weakness: normal provider requests returned `1,510` BID and `1,510` ASK observations over the same endpoints, unique and aligned, with a five-day maximum calendar gap.

The delayed feed available to this gateway did not expose a current sided quote outside market hours. The final historical `CBUS5E` quote on 1 July 2026 was EUR `15.286` bid and `15.300` ask, a EUR `0.014` or roughly `9.2` basis-point spread around the midpoint. Delayed reference last/close prices implied one-share notionals of approximately EUR `15.23` for `CBUS5E`, `125.88` for `STEA`, `3.57` for `LQEE`, `3.89` for `IHYE`, and `71.78` for `STHE`. Non-transmitting IBKR `whatIf` checks accepted one share of every line as `PreSubmitted`, without a warning or reject reason; `STEA` therefore remains the preferred short-HY line and `STHE` is only a fallback. IBKR estimated EUR `3.00` commission for each London order and a EUR `3.00`–`3.75` range for `CBUS5E`. The completed config's EUR `1.25` fixed fee plus `5` basis points would model only about EUR `1.25`–`1.31` for these one-share orders, so the EUR-hedged baseline must correct or conservatively stress that cost assumption before comparison.

Do not silently splice these returns into the completed unhedged run: build new static hedged configs, rerun the candidates over identical windows and report the currency-translation change explicitly. The live-oriented pair is `CBUS5E.XBRU:QUOTE` plus `STEA.LSEETF`; the four-fund research comparator adds `LQEE.LSEETF` and `IHYE.LSEETF`.

The static control is

$$
w_{0,t} = (0.25, 0.25, 0.25, 0.25)
$$

and its contemporaneous duration target is

$$
D_{0,t} = d_t^\top w_{0,t}.
$$

At each monthly rebalance, choose active weights $w_t$ that maximize aggregate excess-yield proxy subject to:

$$
\begin{aligned}
\max_{w_t}\quad & c_t^\top w_t \\
\text{subject to}\quad
& \mathbf{1}^\top w_t = 1, \\
& w_{\mathrm{SDIG},t} + w_{\mathrm{LQDE},t} = 0.50, \\
& w_{\mathrm{SDHY},t} + w_{\mathrm{IHYU},t} = 0.50, \\
& d_t^\top w_t = D_{0,t}, \\
& 0.05 \leq w_{i,t} \leq 0.45.
\end{aligned}
$$

This leaves one active maturity-curve degree of freedom while holding quality, total capital and rate duration fixed. The bounds limit concentration and ensure the result is a continuous allocation rather than the current one-fund-per-quality selector. They are one preregistered engineering choice, not a sweep dimension. If inputs are unavailable, stale, or the constrained solve fails, emit the static control rather than cash or last-known active weights.

The active implementation has no learned `duration_penalty_bps` or `max_modified_duration`. Its candidate space contains exactly two declared alternatives: static and active. Existing portfolio drift bands and the native cost-bearing simulator remain authoritative; a separate signal hurdle or turnover optimizer is out of scope for this issue.

## Evaluation and stop rule

First compare active with static on identical windows and report:

- realized excess return and MPPM certainty-equivalent delta net of all modeled costs;
- realized duration difference, which must be numerically negligible at every rebalance;
- IG/HY weight difference, which must be zero by construction;
- proxy-DTS difference and return attribution, reported as a residual risk rather than declared neutral;
- turnover, trade count and fixed-fee burden;
- calm-market income, skew, worst month, drawdown and downside L-skew;
- active-weight occupancy and how much expected excess yield the optimizer adds over static.

Only after that comparison should a locked active Candidate be passed to the paired floor evaluator beside locked Atalanta. The fixed `60/40` evaluator remains a diagnostic and is not the live Trader's allocation rule. Promotion requires stable positive marginal certainty-equivalent contribution and the intended concave income shape; improved Sharpe caused only by lower duration is explicitly disallowed.

Complete the engineering issue even if active loses. If the duration-neutral active portfolio cannot beat static credit after costs, retain static credit only as an income allocation and stop tuning this four-fund credit-carry hypothesis. The next material upgrade would require genuine OAS/spread-duration and credit-curve roll-down data, not another penalty grid.

## Turnover research and post-run decision

> [!failure] The turnover overlay cannot rescue this signal
> The active implementation behaved as designed, but the constrained signal offered only about `3.1` basis points per year of average ex-ante proxy pickup. Its approximately `3` basis points per year of realized gross advantage is consistent with that small opportunity. Trading more efficiently may preserve those few basis points; it cannot turn them into a material carry premium.

The broad transaction-cost literature agrees on a no-trade region, but the destination after a breach depends on the cost shape. With proportional costs, trading to the band boundary is generally optimal. A fixed fee instead creates an impulse decision: do nothing inside the region, but move to an interior target once a trade is worthwhile.[^liu] Aegis already represents this distinction through its shared drift-band gate and `destination_fraction`; Demeter's fixed-fee configuration correctly uses the full target as the destination. Adding a second weight-distance gate inside the strategy would duplicate execution policy and make the signal depend on the size of one deployment book.

Predictable-return research adds a separate point: the desired portfolio itself should account for signal decay. Gârleanu and Pedersen show that costly trading should move partially toward a forward-looking aim and should give more weight to persistent predictors.[^dynamic-trading] Empirically, Novy-Marx and Velikov find that signal-aware buy/hold banding preserves factor exposure better than simply rebalancing less frequently.[^cost-mitigation] This is not the same as Aegis's realized-weight drift band: signal banding asks whether a holding remains sufficiently attractive, whereas the drift band asks whether the realized portfolio is sufficiently far from its current target.

FTSE Russell's fixed-income carry research offers the closest domain precedent. It keeps monthly optimization but reports that a longer, twelve-month carry horizon stabilizes allocations and materially reduces turnover.[^ftse] That result does not justify replacing Demeter's monthly observation with an arbitrary quarterly schedule. It says the signal horizon and expected holding horizon must be matched; it does not say that slower execution can save an economically negligible signal.

The completed `2020-08-10` through `2026-07-01` history contains `71` monthly observations:

| Diagnostic | Result |
|---|---:|
| Mean active proxy pickup over static | `3.1 bp/year` |
| Median active proxy pickup | `2.7 bp/year` |
| Maximum active proxy pickup | `12.0 bp/year` |
| IG edge autocorrelation, 1 / 3 months | `0.882 / 0.747` |
| HY edge autocorrelation, 1 / 3 months | `0.701 / 0.439` |
| Optimized weight autocorrelation, 1 / 3 months | `0.720 / 0.712` |
| Pickup autocorrelation, 1 / 3 months | `0.434 / -0.202` |
| Target one-way turnover, annualized | `29.4%` |
| Months with a target change above 2 percentage points | `14.1%` |
| Months at a 5% or 45% fund bound | `0%` |
| Maximum duration constraint residual | `6.7e-16` |
| Maximum quality constraint residual | `0` |
| Mean proxy-DTS residual | `-0.078`, with range `[-0.740, 0.701]` |

The native cost-bearing comparison confirms the same economics. Static returned `9.95%` with `EUR 10.44` of modeled fees. Active returned `9.40%` with `EUR 47.45` of fees. Adding the fee difference back implies only about `0.19` percentage points of gross active benefit over the full history, or roughly `3` basis points annually. Static also led on held-out carry income utility, and the two candidates were statistically indistinguishable across the four expanding folds.

> [!decision] One path forward
> Do **not** add a Demeter-specific cost hurdle, sweep wider drift bands, or change the calendar to quarterly. Record the active portfolio as a clean falsification and retain the static equal-weight credit allocation only as `credit_income`, not demonstrated carry. The next active Demeter research path must enlarge the gross opportunity set with genuine OAS, spread duration and credit-curve roll-down, or a materially broader investable universe. A generic signal-hysteresis facility may still be valuable to Aegis, but it belongs in a separate execution-design issue and must consume current holdings and the resolved cost model rather than embedding the `EUR 5,000` book in this strategy.

### Evaluator test boundary

Adding all of `scripts/tests` to Pytest's default `testpaths` is not the correct cleanup. Pytest supports both configured default discovery and explicit file or directory selection; keeping a check outside `testpaths` is therefore an intentional suite boundary, not an uncollected accident.[^pytest-discovery]

- Tests of `research.aegis_research.floor_evaluation` exercise authoritative statistical code and belong under the normal `tests/unit/research/aegis_research/` suite.
- Subprocess checks of the thin `scripts/floor_gate.py` argument and JSON interface belong in `scripts/tests/` and should remain explicit script checks.
- Do not broaden `testpaths` to include all script checks. Move the three evaluator-unit tests into the normal suite and leave only the two CLI smoke checks beside the script.

## Sources

[^koijen]: Koijen, Moskowitz, Pedersen & Vrugt, "Carry," *Journal of Financial Economics* 127(2), 2018. Credit carry is credit spread plus credit-curve roll-down on duration-adjusted portfolios. https://pages.stern.nyu.edu/~lpederse/papers/Carry.pdf
[^ftse]: FTSE Russell, "The Carry Concept," Fixed Income Factor Research Series, 2019. Long-only carry optimization matches benchmark duration; corporate bucket caps reduce the unconstrained implementation's turnover. https://www.lseg.com/content/dam/ftse-russell/en_us/documents/research/ftse-fixed-income-factor-research-series-carry-concept.pdf
[^msci]: MSCI, "MSCI Fixed Income Carry Indexes Methodology," 2019. Uses bond-level OAS, standardized scores, quarterly rebalancing and explicit selection/turnover buffers. https://www.msci.com/eqb/methodology/meth_docs/MSCI_FI_Carry_Indexes_Methodology.pdf
[^ipr]: Israel, Palhares & Richardson, "Common Factors in Corporate Bond Returns," *Journal of Investment Management* 16(2), 2018. Uses DTS to control the large beta dispersion in corporate-bond characteristic portfolios. https://www.aqr.com/-/media/AQR/Documents/Journal-Articles/Common-Factors-in-Corporate-Bond-Returns.pdf
[^returns]: Andreani, Palhares & Richardson, "Computing corporate bond returns: a word (or two) of caution," *Review of Accounting Studies* 29, 2024. Credit excess returns require a duration-matched government component; total returns are not a substitute. https://doi.org/10.1007/s11142-023-09777-6
[^gsw-data]: Federal Reserve Board, "Nominal Yield Curve." Daily fitted nominal curve parameters and zero, par and forward yields; normally updated weekly and subject to vintage revision. https://www.federalreserve.gov/data/nominal-yield-curve.htm
[^gsw-paper]: Gürkaynak, Sack & Wright, "The U.S. Treasury Yield Curve: 1961 to the Present," *Journal of Monetary Economics* 54(8), 2007. Provides the fitted daily Treasury curve and Svensson specification. https://doi.org/10.1016/j.jmoneco.2007.06.029
[^dynamic-trading]: Gârleanu & Pedersen, "Dynamic Trading with Predictable Returns and Transaction Costs," *Journal of Finance* 68(6), 2013. Cost-aware portfolios trade partially toward a forward-looking aim and weight persistent predictors more heavily. https://doi.org/10.1111/jofi.12080
[^liu]: Liu, "Optimal Consumption and Investment with Transaction Costs and Multiple Risky Assets," *Journal of Finance* 59(1), 2004. Fixed and proportional costs produce no-trade intervals and interior post-trade targets. https://doi.org/10.1111/j.1540-6261.2004.00634.x
[^cost-mitigation]: Novy-Marx & Velikov, "Comparing Cost-Mitigation Techniques," *Financial Analysts Journal* 75(1), 2019. Signal-aware banding reduced costs with less loss of gross signal exposure than reducing rebalance frequency. https://doi.org/10.1080/0015198X.2018.1547057
[^pytest-discovery]: Pytest, "Conventions for Python test discovery" and "Good Integration Practices." Default `testpaths` and explicit command-line selection are both supported; tests should be separated according to the code boundary they exercise. https://docs.pytest.org/en/stable/explanation/goodpractices.html
[^ubs-uef8]: UBS, "UBS BBG US Liquid Corp 1-5 UCITS ETF hEUR acc" factsheet. The share class tracks USD investment-grade corporate bonds with one-to-five-year maturities, hedges to EUR and launched on 31 March 2015. https://swissfunddata.ch/sfdpub/docs/fsm-2880_67_04-20250930-en.pdf
[^blackrock-lqee]: BlackRock, "iShares $ Corp Bond UCITS ETF EUR Hedged (Dist)." Official product page for `IE00BF3N6Y61`; the EUR-hedged share class launched on 21 September 2017 and trades as `LQEE` on the London Stock Exchange. https://www.ishares.com/uk/individual/en/products/290630/ishares-corp-bond-ucits-etf
[^pimco-short-hy]: PIMCO, "PIMCO US Short-Term High Yield Corporate Bond UCITS ETF EUR (Hedged)" factsheet. `STEA` (`IE00BD26N851`) accumulates and `STHE` (`IE00BF8HV600`) distributes monthly; both track the EUR-hedged ICE BofA 0-5 Year US High Yield Constrained benchmark and share a 11 December 2017 inception date. https://docs.fundconnect.com/GetDocument.aspx?Isin=IE00BF8HV600&clientid=18svzhes-n8uj-xtdb-oidd-a58dzenasvsr&lang=en-GB&save=false&type=Factsheet
[^blackrock-ihye]: BlackRock, "iShares $ High Yield Corp Bond UCITS ETF EUR Hedged (Dist)." Official product page for `IE00BF3N7102`; the EUR-hedged share class trades as `IHYE` on the London Stock Exchange and Xetra. https://www.ishares.com/uk/individual/en/products/291745/ishares-high-yield-corp-bond-ucits-etf
