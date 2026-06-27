# Maximizing a convex trend sleeve on UCITS ETFs at small size — research memo

**Date:** 2026-06-27
**Scope:** Builds on the proven negative result in the brief (§3). Research-only; no repo code touched.
**Method:** All sources via exa. Cost-honest (net of the €1.25 IBKR fee floor). Ranked on **quarterly-horizon convexity/skew**, never on Sharpe/Calmar/UPI.

---

## 0. TL;DR (read this first)

1. **The €5k account is not doomed by the fee floor — daily rebalancing × 8 sleeves was.** The proven 18.8%-of-NAV fee disaster (≈€938/yr) is a *cadence × breadth* failure, not a *NAV* failure. The same fee model run **monthly on 4 orthogonal sleeves with a wide no-trade band drops fee drag to ≈0.5–0.9% of NAV at €5k** — a ~20–30× reduction — because fills fall from ~422/yr to ~20/yr. **Cadence is the dominant lever; it is also nearly convexity-free to pull** because the convex horizon is quarterly and a slow signal barely moves between monthly rebalances.

2. **The single most effective structural move is to stop self-replicating a diversified long/short CTA at €5k and buy one that rebalances futures internally at institutional cost.** A UCITS *managed-futures ETF* now exists in Europe again (iMGP DBi, listed March 2025) — long/short across equities, bonds, commodities, FX via futures, accumulating, **0.75% TER**, buyable on IBKR for one €1.25 ticket. It delivers the diversified book **and the short leg** with *zero per-rebalance fees to you*. At €5k its 0.75% TER is cheaper than the DIY book's residual fee drag once you add the sleeves needed for real convexity — and the DIY book realized *negative* convexity (−0.038 → −0.233) while the CTA-replication strategy printed **+23% in 2022**. This is the recommendation that contradicts the negative verdict, and it is the strongest one.

3. **Short-leg verdict: worth it, but not via DIY borrow or naive inverse ETFs at €5k.** The biggest convex event of the decade — 2022 — was a **short-bond event** (Man Group, AlphaSimplex, SG attribution all confirm). A long-only UCITS book captured ≈0 of it because it can only go flat in a rates bear. That foregone alpha is large (SG Trend +27% to May-2022; full-year SG CTA ≈+18–20%, its best since inception). But retail UCITS borrow is thin-to-zero and daily-reset inverse ETFs decay in chop. **The clean way to own the short leg is to let a managed-futures ETF take it for you** (rec #2). If insisting on DIY, a single **-1x government-bond UCITS ETF as a tactical, trend-gated inflation-crisis sleeve** is defensible *because daily-reset compounding helps in sustained trends* (the only time you'd hold it) — but rank it below the ETF.

4. **NAV at which DIY clears the fee floor:** the floor stops dominating around **€10k** (drag <0.3%) and is negligible by **€25k–50k** (drag ~0.1%, the asymptotic 0.05%-tiered rate). But the reframed headline is sharper: **at €5k you don't need more capital, you need fewer sleeves and a slower clock.**

---

## 1. What the literature actually pins down (building on §3/§4, not re-deriving)

The convexity claim is mechanical and the enemies are named. The useful, *non-obvious* facts for this problem:

- **Trend P&L = (long-horizon variance − short-horizon variance) of the underlying.** CFM's exact identity for an EMA trend: `M[PnL] ∝ E[EMA(returns)]² − (½/τ)·EMA(returns²)` — i.e. you make money when realized variance over the *trend timescale* exceeds the daily variance scaled up, and the payoff plotted against the underlying's move is a parabola (`y = x²`). This is the source of convexity and it is **exact even for a random walk**. *Source:* Bouchaud, Dao, Deremble, Lempérière, Nguyen, Potters, "Tail protection for long investors: Trend convexity at work," arXiv:1607.02410 (2016); CFM "The Convexity of Trend Following" (2018), https://www.cfm.com/wp-content/uploads/2022/12/266-2018-The-Convexity-of-trend-following.pdf

- **Convexity only appears when you *measure* returns over a horizon longer than (a) the signal's half-life and (b) the rebalance period.** Sepp's result is the practical key: a trend system "generates positive convexity when the return measurement period exceeds the half-life of the trend smoothing and the period of portfolio rebalancing." For **quarterly** convexity, use **monthly rebalancing + a half-life of ≈4 months** (≈ 84 trading-day half-life ≈ 126–252d lookback band). Monthly returns show *no* significant convexity for any trend speed — so the user is right to evaluate at the quarterly horizon, and wrong to ever look at daily/monthly P&L for this judgment. *Source:* Artur Sepp, "Trend-following strategies for tail-risk hedging and alpha generation" (2018), https://artursepp.com/2018/04/24/trend-following-strategies-for-tail-risk-hedging-and-alpha-generation/ ; Sepp & Rakhmonov, "Designing Robust Trend-following System," SSRN 4677166.

- **A subtle tension to respect (pressure-test of the brief's "slow = more convex" framing).** CFM is explicit that **three things *reduce* trend convexity-vs-the-underlying: (i) trending a diversified pool, (ii) capping the forecast, (iii) slowing the system.** This looks like it contradicts "slow is more convex." Resolution: CFM measures *instantaneous convexity relative to one underlying*; the user wants *quarterly crisis convexity relative to equities at low turnover*. A slow system has lower convexity-per-unit-underlying but reveals it at a longer measurement horizon and trades far less. The honest statement is therefore: **slow trend is the right choice here not because it is maximally convex, but because it puts most of its (smaller) convexity at the quarterly horizon you care about while spending almost nothing on fills.** Don't oversell slow as a free convexity lunch — it trades convexity *magnitude* for convexity *at the right horizon* + low cost.

- **The tail is everything; anything that clips the right tail destroys the reason to hold it.** Potters & Bouchaud prove the per-trade P&L is option-like and asymmetric; the win rate falls as volatility rises while the average win grows — i.e. **lose-small-often / win-big-rarely is the signature of a healthy trend book, not a bug.** This is the formal reason Sharpe/Calmar/UPI select the *least* convex book (they reward smoothness, penalizing the fat right tail). *Source:* Potters & Bouchaud, "Trend followers lose more often than they gain," arXiv physics/0508104 (2005), https://arxiv.org/abs/physics/0508104

- **The cost-optimal response to a per-trade cost is a no-trade band + partial adjustment toward a moving aim, not trade-to-target.** Gârleanu–Pedersen's two principles: *"aim in front of the target"* and *"trade partially toward the current aim,"* with slower-decaying (slower) signals getting more weight. This is the theoretical license for both the `buffer_band` lever and for trading a fraction of the gap. *Source:* Gârleanu & Pedersen, "Dynamic Trading with Predictable Returns and Transaction Costs," J. Finance 68 (2013), https://nbgarleanu.github.io/DynTrad.pdf

- **Vol-targeting helps tails for risk assets but is a turnover tax; for bonds/commodities/FX it barely moves the Sharpe.** Harvey et al. find vol-targeting's Sharpe benefit is concentrated in equities/credit (leverage effect) and "negligible" for bonds, currencies, commodities — *but* it reliably *reduces left-tail severity across all classes*. It also adds turnover (constant rebalancing to target). At €5k the turnover is the binding cost. *Source:* Harvey, Hoyle, Korgaonkar, Rattray, Sargaison, Van Hemert, "The Impact of Volatility Targeting," JPM 45(1) 2018, https://people.duke.edu/~charvey/Research/Published_Papers/P135_The_impact_of.pdf

- **Low one-sided turnover is the line between an anomaly that survives costs and one that doesn't; a buy/hold spread is the best simple mitigant.** Novy-Marx & Velikov: most anomalies with **<50%/month one-sided turnover** keep a significant net spread; higher-turnover ones don't; the single most effective fix is a **buy/hold spread** (stricter to enter than to hold) — the academic twin of the no-trade band. *Source:* Novy-Marx & Velikov, "A Taxonomy of Anomalies and Their Trading Costs," RFS 29(1) 2016 / NBER w20721, https://www.nber.org/system/files/working_papers/w20721/w20721.pdf

- **Trend's crisis record is real and it is mostly a fast/medium-signal, short-enabled phenomenon.** AQR: TSMOM positive in **8 of the 10** largest 60/40 drawdowns since 1880; the "smile" (best in extreme up/down equity years) is robust. Man Group: **faster trend measurement improves crisis alpha** because crises arrive quickly. *Sources:* Hurst, Ooi, Pedersen, "A Century of Evidence on Trend-Following Investing," JPM 2017, https://www.aqr.com/-/media/AQR/Documents/Insights/Journal-Article/AQR-JPM-Fall-2017.pdf ; Man Group, "Gaining Momentum / Trend-Following in a Crisis: A 2022 Review," https://www.man.com/insights/trend-following-2022-review

**Net design read:** slow-to-medium signal (≈4-month half-life), evaluated quarterly, with a wide no-trade band + partial adjustment, on a *minimal set of orthogonal macro sleeves*, rebalanced monthly. That is simultaneously the most convex-at-the-right-horizon and the lowest-fill design the constraints allow.

---

## 2. The ranking metric (keep the session's, with a guardrail)

Keep the **magnitude-aware, benchmark-free convexity/skew metric** the session built (net decile-tail of overlapping 2–6mo own-returns, horizon-band averaged — "lose-small / pay-big"). It is the right family: it is computed on *own* returns (no benchmark needed for a long-only sleeve), it is horizon-banded into the quarterly region where convexity exists (Sepp), and it is magnitude-aware so it rewards the fat right tail (Potters–Bouchaud) instead of penalizing it.

One guardrail: **always compute it net of the €1.25 floor**, and report it alongside **fills/yr** so a candidate can't buy convexity with turnover you can't afford. A convexity score that improves only because the book re-trades into every move is the daily-8-name trap in disguise.

---

## 3. Ranked, NAV-conditioned recommendations

Format per lever: **effect on convexity / effect on fees (as %NAV/yr) / evidence / falsification.** Fee figures use the IBKR Ireland **Tiered** schedule (0.05% of trade value, **€1.25 minimum/order**, €29 max), confirmed at https://www.interactivebrokers.ie/en/pricing/commissions-stocks-europe.php , anchored to the brief's empirical 422 fills/yr ≈ €938/yr for the failed 8-name daily book. "Fills/yr" estimates use `fills ≈ rebalances/yr × N_sleeves × p`, with `p≈0.21` calibrated from that anchor (8×252×0.21≈422) and rising modestly at lower cadence as drift accumulates.

### R1 — Replace the DIY book with a UCITS managed-futures ETF (the turnover-killer). NAV: all, especially ≤€25k.
- **Convexity:** Highest available on this substrate. It runs a diversified **long/short** futures book (10–15 contracts across equities, rates, commodities, FX) — exactly the "independent macro bets, non-equity-dominated" substrate the vault notes say convexity needs, *including the short leg a UCITS cash-ETF book cannot take.* The replicated strategy printed **+23.2% in 2022** (a short-bond/long-commodity convex event) and is 0.85–0.91 correlated to the SG CTA index.
- **Fees/yr as %NAV:** **0.75% TER, flat, all-in**, plus **one** €1.25 entry ticket. No per-rebalance fills hit *your* account — the fund rebalances futures internally at institutional cost. At €5k this *beats* the DIY residual drag once you add enough sleeves for real convexity (see R3/fee table). Accumulating share class → no dividend-driven incidental trades, no withholding-reclaim friction.
- **Evidence:** iMGP DBi Managed Futures Fund, **UCITS ETF** R-EUR `LU2951555403` / R-USD `LU2951555585`, TER 0.75%, accumulating, swap-based, Euronext Paris + LSE, launched Mar 2025; strategy live since 2016 (US DBMF) / Jan-2023 (Lux SICAV). https://www2.imgp.com/imgp-dbi-managed-futures-fund , https://www.justetf.com/en/etf-profile.html?isin=LU2951555403 , https://www.etfstream.com/articles/dbi-launches-managed-futures-etf-in-europe . Non-ETF UCITS alternatives if you prefer pure trend over CTA-beta: **Winton Trend Fund (UCITS)** (medium-term, diversified, https://www.wintonucits.com/trend-fund) and **Amundi Metori Epsilon Global Trends** (45+ futures, 10% vol target; 2022 +15.3%, but 2021 −5.8% / 2023 −5.9% — note the lumpy, convex shape). These are mutual funds (subscription, not a €1.25 exchange ticket), so rank below the ETF for this account.
- **Falsification:** Reject if (a) the ETF's swap counterparty/synthetic structure is disqualified by the user's risk policy; (b) its net-of-0.75% quarterly convexity (own-return decile-tail) fails to beat the best DIY book — unlikely given DIY realized *negative* convexity; or (c) liquidity/spread on the EUR line at €5k size exceeds the modeled cost (check the live bid/ask — it is a small, new ETF, ~€60m AUM).

### R2 — Rebalance cadence as a first-class lever: monthly, not daily. NAV: all, decisive ≤€25k.
- **Convexity:** Near-neutral. Convexity lives at the quarterly horizon; a 4-month-half-life signal barely moves in a month, so monthly capture ≈ daily capture for the right tail (Sepp). Going to *quarterly* starts to cost crisis responsiveness (Man: crises arrive fast), so **monthly is the sweet spot, quarterly is the cost-floor option.**
- **Fees/yr as %NAV (at €5k):** Daily 8-name ≈ **18.8%** (proven). Monthly 4-name ≈ **0.5–0.9%** (~20 fills/yr). Quarterly 4-name ≈ **0.25–0.45%** (~10 fills/yr). This single lever is ~20–30× of the entire problem.
- **Evidence:** Sepp (horizon-matching, above); Hoffstein: "rebalance frequency choices should be a function of the speed at which our signal decays versus implementation costs" — slow signal ⇒ infrequent rebalance is *correct*, not a compromise. https://blog.thinknewfound.com/2019/07/timing-luck-and-systematic-value/
- **Falsification:** Reject monthly if the net quarterly convexity score drops materially vs weekly at equal sleeve count (i.e. if the signal is actually fast). If it does, the signal is too fast for this account — fix the signal (R4), don't pay for daily fills.

### R3 — Fewest sleeves that span the orthogonal macro crisis drivers (not max breadth). NAV: all.
- **Convexity:** Positive *for crisis-vs-equity convexity*, with a caveat. The vault note is right that convexity needs independent macro bets (rates, commodity, gold, credit) — but CFM is right that adding instruments dilutes convexity-vs-any-single-underlying. Reconciliation: **you want the *minimum* set that spans the independent crisis engines, because at €5k each extra sleeve costs `rebalances/yr × p × €1.25` in hard fills and adds little new orthogonal information.** Breadth that helps an institution's convexity is swamped by the fill floor here (proven: 4-name −0.038 → 8-name −0.233).
- **Fees/yr as %NAV:** Linear in sleeve count. Each added sleeve at monthly cadence ≈ +`12×p×€1.25` ≈ **+€3/yr ≈ +0.06% of €5k per sleeve**; the damage is small *per sleeve at monthly cadence* — the 8-name disaster was breadth × **daily**, so fix cadence first (R2), then trim sleeves.
- **Evidence:** CFM 2018 (diversification reduces convexity-vs-underlying); brief §3 (8-name worse than 4-name net). Test **turnover-adjusted convexity per added sleeve**: does sleeve N+1 raise the net quarterly convexity score by more than its fills cost? Keep only sleeves that pay.
- **Suggested minimal spanning set (long-only DIY):** (1) global equity, (2) long duration / long Treasury (deflation-crisis engine), (3) gold, (4) broad commodity (inflation-crisis engine). That is 4 orthogonal macro crisis drivers. Adding TIPS / global-govt / USD-HY is redundant fills at €5k.
- **Falsification:** If dropping a sleeve raises net convexity (it removes fills without removing an independent crisis engine), it was redundant — drop it.

### R4 — Slow-only signal band; drop the fast end. NAV: all.
- **Convexity (at quarterly horizon):** Positive. Restrict lookbacks to ≈**126–252d** (half-life ≈ 3–6 months). Fast signals trade more *and* put their convexity at sub-monthly horizons you don't measure or want. Lempérière et al. found **fast trends have "significantly withered" while long trends have not degraded over two centuries** — the fast end is both costlier and weaker now. https://arxiv.org/abs/1404.3274
- **Fees/yr as %NAV:** Strongly positive (fewer crossings ⇒ fewer fills). Slow signal + monthly cadence are mutually reinforcing.
- **Caveat (honest):** Man Group shows *faster* signals give *better* crisis alpha. So slow-only sacrifices some fast-crisis (e.g. Feb–Mar 2020 gap) capture for cost. At €5k that trade is correct; if the user later wants the fast-crisis tail back, R1 (the ETF runs multiple speeds internally) is the cost-free way to get it.
- **Falsification:** Reject if adding a medium sleeve (~63–126d) raises net quarterly convexity by more than its fills — then the band should include medium, not slow-only.

### R5 — Wider no-trade band + partial adjustment (Gârleanu–Pedersen / buy-hold spread). NAV: all.
- **Convexity:** Near-neutral to mildly positive. A band defers small re-trades that mostly clip the right tail anyway; partial adjustment (trade, say, 50% of the gap) avoids all-or-nothing whipsaw.
- **Fees/yr as %NAV:** Positive. Push `buffer_band` beyond the 0.20–0.30 already tried; pair with a **buy/hold spread** (wider band to *establish/flip* a position than to *trim* it) — Novy-Marx & Velikov's single most effective mitigant.
- **Evidence:** Gârleanu–Pedersen (above); Novy-Marx & Velikov (above).
- **Falsification:** Reject the *wider* band where net quarterly convexity falls faster than fills — i.e. the band is now so wide it won't let the book flip into a new crisis trend. Find the knee.

### R6 — Vol-targeting: OFF (or coarse) at €5k for this universe. NAV: ≤€25k off; ≥€50k optional.
- **Convexity:** Slightly negative to keep on (constant rebalancing to target trims the right tail). Harvey et al.: for **bonds/commodities/FX the Sharpe benefit is negligible**; the benefit that survives is left-tail reduction, which you can approximate with the band + slow signal instead of continuous rescaling.
- **Fees/yr as %NAV:** Vol-targeting *adds* fills (re-scale every time vol moves). At €5k those fills hit the €1.25 floor with tiny notional — pure waste.
- **Evidence:** Harvey et al. (above).
- **Falsification:** If a *coarse, band-gated* inverse-vol size (only re-scale when target weight moves > the band) raises net convexity without raising fills materially, keep that coarse version. Reject only continuous daily vol-targeting.

### R7 — Fee-structure: Tiered, accumulating, fractional, single batched rebalance. NAV: ≤€25k.
- **Tiered beats Fixed at this size:** Tiered min **€1.25**/order vs Fixed **€3.00** (SmartRouting) / €4.00 (direct). For €5k order sizes the floor binds, so Tiered ≈ €1.25 + small exchange/clearing/reg pass-throughs (the pass-throughs + ~0.03% FX on USD lines are why the backtest's realized cost ran ≈€2.2/fill, not €1.25). https://www.interactivebrokers.ie/en/pricing/commissions-stocks-europe.php
- **Accumulating ETFs:** remove dividend-reinvestment fills and withholding/reclaim friction — fewer incidental trades.
- **Fractional shares (Tiered, same €1.25 min):** do **not** lower the floor, but let you deploy the full €5k precisely across sleeves and avoid *forced lumpy rebalances* a high share price would otherwise create. Benefit = precision/avoided no-trades, not fee reduction.
- **Prefer EUR-denominated UCITS lines** to avoid the per-conversion FX cost on USD lines (the brief's ~0.03%).
- **Batch all sleeves into one periodic rebalance date** — but note the floor is *per fill*, so batching does **not** merge sleeve orders into one ticket; it only avoids extra ad-hoc rebalances. The real fill economizer is cadence (R2), not batching.
- **Falsification:** none material; these are dominated choices at this NAV.

### R8 — Do NOT tranche / overlay portfolios at €5k (anti-recommendation). NAV: ≤€25k avoid; ≥€100k consider.
- Hoffstein's overlapping-portfolios / tranching cure for **rebalance timing luck** (split into N sub-books rebalanced on staggered days, reduces timing-luck σ by 1/N at ~constant turnover) is excellent at scale but **wrong at €5k**: it fragments each rebalance into N tiny orders, every one of which hits the €1.25 floor — multiplying the fixed cost. At €5k you *accept* timing luck and trade in fewer, larger, less-frequent tickets. *Source:* Hoffstein, "Quantifying Timing Luck," https://blog.thinknewfound.com/2018/01/quantifying-timing-luck/
- This is a clean NAV-conditioned reversal: a technique that is correct for the user's strategy at €100k is value-destroying at €5k.

---

## 4. The viability-vs-NAV curve (the key artifact)

**Fee model:** per-fill cost = `max(€1.25, 0.05% × order_notional)` + ~€0.3–0.9 pass-throughs/FX. Order notional ≈ `NAV × weight_traded`. The **floor binds whenever order notional < €2,500** (since 0.05%×2,500 = €1.25). Above that, cost converges to the **0.05% tiered rate × annual turnover**. Annual one-way turnover for the recommended slow/monthly/4-sleeve book ≈ ~150–250% ⇒ asymptotic drag ≈ **0.05% × ~2 ≈ 0.10%/yr**.

**Recommended DIY core:** 4 orthogonal sleeves, ~4-month-half-life signal, wide band + partial adjust, **monthly** rebalance ⇒ ≈ **20 fills/yr** (NAV-independent in *count*; it's signal-driven).

| NAV | Order size regime | Est. fills/yr | Est. fee/yr | **Fee drag (%NAV)** |
|---|---|---|---|---|
| €5k | floor binds (orders ~€150–1,250) | ~20 | ~€30 | **~0.6%** |
| €10k | floor binds (orders ~€300–2,500) | ~20 | ~€30 | **~0.30%** |
| €25k | floor ↔ 0.05% crossover (~€750–6,000) | ~20 | ~€38 | **~0.15%** |
| €50k | 0.05% dominates | ~20 | ~€50 | **~0.10%** |
| €100k | 0.05% dominates | ~20 | ~€100 | **~0.10%** |

**Contrast — the proven failed book** (8 sleeves, daily): €938/yr ⇒ **18.8% at €5k**, ~9.4% at €10k, ~3.8% at €25k, ~1.9% at €50k, ~0.9% at €100k. *That* book genuinely needed ~€100k to be viable.

**Reading of the curve:**
- The "**small-account tax**" of the *recommended* book at €5k is ~0.6% vs the ~0.1% a large account pays — a ~0.5%/yr premium. **Tolerable.** Trend's own expected gross is single-to-low-double-digit %; 0.5–0.6% drag does not eat it.
- **The floor stops dominating at ~€10k and is gone by ~€25–50k.** But the operative conclusion is *not* "wait until €25k." It is: **at €5k, viability is a cadence/breadth choice, not a capital constraint.** The brief's hypothesized "you need ~€X to clear the floor" is true *only if you insist on daily × many-names*; slow the clock and the requirement collapses to ~€5k.
- **DIY vs the ETF at €5k:** DIY core ≈ 0.6%/yr fee drag but realized **negative** convexity and **no short leg**. The ETF ≈ 0.75%/yr TER with **positive, complete (long/short) convexity**. On convexity-per-cost the ETF wins at €5k and stays competitive until the DIY drag falls below ~0.2% (≈€25k+), at which point a DIY book *can* make sense **if** its net convexity has been fixed (it had not been, as of §3).

---

## 5. Short-leg verdict (§6, decided)

**Verdict: the short leg is worth a lot of the convexity, but at €5k take it through a managed-futures ETF, not DIY borrow or buy-and-hold inverse ETFs.**

1. **Foregone short alpha is large and concentrated in inflation-crises.** 2022 is the proof: trend's banner year (**SG CTA ≈+18–20%, its best since 2000/2008; SG Trend ≈+27% to end-May**) was driven by **short bonds + short rates + long energy/grains + long USD**. Man Group states it directly: in 2022 "a positive bond attribution has resulted from **short bond exposure** in aggregate" — the *opposite* of the long-bond crisis alpha of 2008/2020. AlphaSimplex (Kaminski): trend is positive in **sustained** fixed-income crises but negative in short bond corrections, because it had been structurally *long* bonds for decades. *Sources:* https://www.man.com/insights/gaining-momentum-trend ; https://www.alphasimplex.com/assets/files/2023.08---crisis-or-correction---kaminski-and-zhao.pdf ; https://alpha-week.com/2022-cta-index-performance-review
   - **A long-only UCITS book's crisis convexity is structurally asymmetric:** it *has* deflation-crisis convexity (long duration + gold rally in 2008/2020) but **zero inflation-crisis convexity** (cannot short bonds in 2022 — it just sits in cash). The short leg is precisely the missing half.

2. **Cost it three ways:**
   - **(a) Genuine borrow:** not realistically available to EU retail for UCITS ETFs (thin-to-zero inventory); reject on availability, not just cost.
   - **(b) Inverse UCITS ETFs:** they exist and are cheap to *hold* — e.g. Xtrackers II Eurozone Govt Bond Short Daily Swap (`LU0321463258`, **0.15% TER**, −1x), Amundi/Lyxor Bund Future Daily −1x (`LU0530119774`, 0.20%) and −2x (`FR0010869578`, 0.20%). The objection is **daily-reset volatility decay**. *But the decay literature cuts in your favor here:* the "constant-leverage trap" (≈ `(1+r)^x · exp(−½x(x−1)σ²T)`, a drag of order `σ²T` for −1x) bites in **choppy/mean-reverting** markets; in **sustained trends** daily-reset compounding *adds* to returns. *Source:* Guedj et al., SLCG, https://www.slcg.com/files/research-papers/Leveraged%20ETFs,%20Holding%20Periods%20and%20Investment%20Shortfalls.pdf ; "Compounding Effects in Leveraged ETFs," arXiv:2504.20116 ("momentum improves compounding, mean reversion undermines it"). **Since you would only ever hold an inverse-bond ETF when the trend signal is short and trending, the path-decay objection is weakest exactly when you use it.** A −1x govt-bond ETF as a *trend-gated, monthly* inflation-crisis sleeve is therefore defensible — but you must (i) gate it strictly on the slow signal, (ii) accept it does nothing (and bleeds the small `σ²T`) when rates chop, and (iii) prefer −1x over −2x (decay scales with `x(x−1)`: −2x has 3× the −1x drag).
   - **(c) Stay flat (current default):** zero cost, zero inflation-crisis convexity. This is what produced "long-only realized ≈ 0 skew" in §3.

3. **Net it:** Short adds the entire inflation-crisis quadrant of the convexity smile (worth ~tens of % in a 2022-type year at full CTA sizing; proportionally less at a small sleeve weight). Costs: DIY = decay-in-chop (modest for −1x, real for −2x) + extra fills to gate it; ETF route = bundled into the 0.75% TER. **Above ~€0 NAV the short leg helps convexity; the question is purely the wrapper.** Recommendation: **own the short leg via R1 (managed-futures ETF) — it shorts bonds/rates with futures and no decay, sized and gated by professionals.** If the user wants a DIY toe in, add **one −1x government-bond UCITS ETF**, trend-gated and monthly, sized ≤ the other sleeves, and never the −2x for buy-and-hold. **Do not** resurrect a full DIY long/short cash-ETF book at €5k — the earlier net-negative long/short result + the fill floor + decay stack against it.

---

## 6. Config-ready parameters

Two deployable configs. State the NAV and fee model with each.

### Config A — "Buy the convexity" (RECOMMENDED at €5k). Assumes €5k, IBKR Ireland Tiered (€1.25 min).
```
instrument         : iMGP DBi Managed Futures UCITS ETF
                     EUR line ISIN LU2951555403 (or USD LU2951555585)
position           : 100% of sleeve NAV, buy-and-hold, single entry
rebalance_cadence  : none (the fund rebalances futures internally)
add_cadence        : monthly/quarterly contributions only (1 ticket each)
share_type         : accumulating (no dividend fills)
sizing_mode        : n/a (fund vol-targets ~ to its mandate)
short_leg          : included inside the fund (long/short futures)
fee_model          : 0.75% TER (all-in) + €1.25 per contribution ticket
expected_fee_drag  : 0.75%/yr + ~€1.25 per add  (≈0.75–0.85% of €5k)
ranking_metric     : net quarterly own-return decile-tail convexity (monitor only)
caveats            : swap-based (counterparty), new ETF (~€60m AUM) — check live spread at €5k size
```

### Config B — "DIY slow long-only + gated short toe" (only if a self-run book is required). Assumes €5k–€25k, Tiered.
```
universe (4–5 sleeves, EUR-denominated where possible):
  - global equity ETF            (acc)
  - long-duration / long Treasury govt ETF (acc)   # deflation-crisis engine
  - physical gold ETC
  - broad commodity ETF          (acc)              # inflation-crisis engine
  - [optional] -1x govt-bond UCITS ETF LU0321463258 (TER 0.15%)  # inflation-crisis short toe, trend-gated only

signal:
  type             : time-series momentum, EMA crossover or 200d/252d breakout
  lookback_band    : 126–252 trading days  (half-life ≈ 3–6 months; drop <63d)
  speeds           : 1–2 slow speeds only (no fast sleeve)

rebalancing:
  cadence          : MONTHLY  (quarterly = cost-floor variant; expect some lost fast-crisis capture)
  no_trade_band    : buffer_band ≈ 0.35–0.50  (wider than the 0.20–0.30 already tried)
  buy_hold_spread  : enter/flip band wider than trim band (Novy-Marx/Velikov)
  adjustment       : PARTIAL — trade ~50% of the gap to target (Gârleanu–Pedersen)
  tranching        : OFF  (fragments orders below the €1.25 floor at this NAV)

sizing:
  mode             : equal-weight or COARSE band-gated inverse-vol
                     (re-scale only when target weight moves > buffer_band; no continuous vol-target)

short_leg:
  rule             : the -1x sleeve is held ONLY when its slow signal is short AND trending;
                     -1x only (never -2x for holding); size ≤ other sleeves

fees:
  pricing          : IBKR Tiered (€1.25 min/order); accumulating ETFs; fractional ON for precision
  expected_fills   : ~16–24/yr (monthly) | ~8–12/yr (quarterly)
  expected_drag    : ~0.5–0.9% of €5k (monthly) | ~0.25–0.45% (quarterly)

ranking_metric:
  primary          : net (post-€1.25) quarterly own-return decile-tail convexity, horizon-banded 2–6mo
  guardrail        : report fills/yr beside every candidate; reject convexity bought with turnover
  forbidden        : Sharpe / Calmar / UPI for candidate selection (they pick the least-convex book)
```

---

## 7. What contradicts / pressure-tests the negative verdict (welcome)

1. **The negative verdict over-generalized from a mis-specified book.** −0.038/−0.233 convexity and 18.8% fee drag came from **daily × up-to-8 names** — the worst corner of the design space for both objectives. The result is real but it indicts *that configuration*, not "trend at €5k." Monthly × 4 orthogonal sleeves was never the thing that failed; the fee math says it lands at <1% drag.

2. **"Widening the universe hurt" is true for DIY cash ETFs and false for a futures fund.** Breadth hurt because each name = more *fills*. Inside a managed-futures ETF, breadth is free to you (internal futures rebalancing). So the correct response to "breadth helps convexity but costs turnover" is not "use fewer names" — it is "**move the breadth inside a wrapper that rebalances for free**." That inverts the breadth conclusion at the product level.

3. **"Long-only realizes ≈0 skew" is a *long-only* limit, not a *trend* limit.** The skew is in the short leg (2022). The fix is the short leg via a futures wrapper, not abandoning convexity.

4. **Slow ≠ automatically more convex (honest caveat against the brief's framing).** CFM shows slowing *reduces* convexity-vs-underlying and Man shows faster helps crisis alpha. Slow wins *here* on cost and horizon-fit, not on raw convexity. If the user ever relaxes the fee constraint (more NAV), re-introducing a medium/fast speed would *raise* convexity — the speed choice is NAV-conditioned, not absolute.

5. **Vol-targeting isn't categorically bad.** Harvey et al. show it reliably cuts left-tail severity. We turn it off at €5k purely for fills; the user shouldn't conclude vol-targeting is harmful, only that it's unaffordable per-fill at this NAV.

---

## 8. Sources (authoritative only)

- Fung & Hsieh, "The Risk in Hedge Fund Strategies: Theory and Evidence from Trend Followers," RFS 14(2) 2001 — lookback-straddle model. https://people.duke.edu/~dah7/RFS2001.pdf
- Potters & Bouchaud, "Trend followers lose more often than they gain," arXiv physics/0508104 (2005). https://arxiv.org/abs/physics/0508104
- Lempérière, Deremble, Seager, Potters, Bouchaud, "Two Centuries of Trend Following," arXiv:1404.3274 (2014). https://arxiv.org/abs/1404.3274
- Bouchaud et al., "Tail protection for long investors: Trend convexity at work," arXiv:1607.02410 (2016). https://arxiv.org/pdf/1607.02410
- CFM, "The Convexity of Trend Following" (2018). https://www.cfm.com/wp-content/uploads/2022/12/266-2018-The-Convexity-of-trend-following.pdf
- Hurst, Ooi, Pedersen, "A Century of Evidence on Trend-Following Investing," JPM 2017. https://www.aqr.com/-/media/AQR/Documents/Insights/Journal-Article/AQR-JPM-Fall-2017.pdf
- Gârleanu & Pedersen, "Dynamic Trading with Predictable Returns and Transaction Costs," J. Finance 68(6) 2013. https://nbgarleanu.github.io/DynTrad.pdf
- Harvey, Hoyle, Korgaonkar, Rattray, Sargaison, Van Hemert, "The Impact of Volatility Targeting," JPM 45(1) 2018. https://people.duke.edu/~charvey/Research/Published_Papers/P135_The_impact_of.pdf
- Sepp, "Trend-following strategies for tail-risk hedging and alpha generation" (2018). https://artursepp.com/2018/04/24/trend-following-strategies-for-tail-risk-hedging-and-alpha-generation/ ; Sepp & Rakhmonov, "Designing Robust Trend-following System," SSRN 4677166. https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4677166
- Novy-Marx & Velikov, "A Taxonomy of Anomalies and Their Trading Costs," RFS 29(1) 2016 / NBER w20721. https://www.nber.org/system/files/working_papers/w20721/w20721.pdf
- Hoffstein (Newfound), "Quantifying Timing Luck" (2018) & "Timing Luck and Systematic Value" (2019). https://blog.thinknewfound.com/2018/01/quantifying-timing-luck/ , https://blog.thinknewfound.com/2019/07/timing-luck-and-systematic-value/
- Man Group, "Gaining Momentum: Where Next for Trend-Following?" & "Trend-Following in a Crisis: A 2022 Review." https://www.man.com/insights/gaining-momentum-trend , https://www.man.com/insights/trend-following-2022-review
- AlphaSimplex (Kaminski & Zhao), "Crisis or Correction" (2023). https://www.alphasimplex.com/assets/files/2023.08---crisis-or-correction---kaminski-and-zhao.pdf
- SG/AlphaWeek, "2022 CTA Index Performance Review." https://alpha-week.com/2022-cta-index-performance-review
- Leveraged/inverse ETF decay: Guedj et al. (SLCG); "Compounding Effects in Leveraged ETFs," arXiv:2504.20116; SEC DERA note (Nov 2019). https://www.slcg.com/files/research-papers/Leveraged%20ETFs,%20Holding%20Periods%20and%20Investment%20Shortfalls.pdf , https://arxiv.org/html/2504.20116
- IBKR Ireland commissions (Tiered €1.25 min, Fixed €3/€4). https://www.interactivebrokers.ie/en/pricing/commissions-stocks-europe.php
- UCITS managed-futures / trend products: iMGP DBi Managed Futures UCITS ETF (LU2951555403 / LU2951555585). https://www2.imgp.com/imgp-dbi-managed-futures-fund , https://www.etfstream.com/articles/dbi-launches-managed-futures-etf-in-europe ; Winton Trend Fund (UCITS) https://www.wintonucits.com/trend-fund ; Amundi Metori Epsilon Global Trends. Inverse govt-bond UCITS ETFs: Xtrackers II Eurozone Govt Bond Short Daily Swap (LU0321463258); Amundi/Lyxor Bund Future Daily −1x (LU0530119774) / −2x (FR0010869578).
