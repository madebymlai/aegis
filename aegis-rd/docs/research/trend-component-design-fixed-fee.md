# Design memo — convex, low-turnover trend/momentum components for the €5k UCITS sleeve (`atalanta`)

Date: 2026-06-27 · Repo: `/home/laimk/git/aegis` (`aegis-rd/`) · Branch: `market-data-unification-live-research-parity`
Scope: **design/proposal only** (no repo code changed, no backtests run this pass). Author: trend-component design agent.
Champion to beat: `atalanta.trendStraddleBufferedLongOnly` on `research/configs/atalanta/trend_etf4_eur.yaml`, ranked on `trend_convexity_payoff`.

---

## 0. The one finding that reframes everything (verified against the engine + vbt source)

The handoff lists "rebalance-cadence … **cannot be expressed today** (missing mechanism — needs code)" and "buffer snaps to full target." Both are real problems, but the **root cause is narrower and the fix is smaller than stated**: it lives entirely in the *strategy component*, not the engine.

**How `target_weights` becomes trades (traced this session):**
`exposure_validation`/`portfolios.py:122` builds the book with
`vbt.PFO.from_filled_allocations(masked, valid_only=True, nonzero_only=False, unique_only=False)`
→ `Portfolio.from_optimizer(pf_method="from_orders", size_type="targetpercent", …)` (`portfolios.py:26,129`).

The allocation/rebalance points are selected by `get_alloc_points_nb` (vbt source, read this session):
- `valid_only=True` → **a row that is all-NaN is skipped (the book HOLDS, no trade)**.
- `nonzero_only=False` → an all-zero row **is** a rebalance point (an explicit de-risk-to-cash is honoured).
- `unique_only=False` → **a row identical to the previous one is STILL a rebalance point.**

Consequence, confirmed by the vbt maintainer (Discord 1108370923951755304: with `from_orders`+`targetpercent`, "positions are rebalanced daily … set allocation rows to NaN where rebalancing is skipped, actual values only at rebalance points"):

> Every current `atalanta` strategy emits a **finite weight on every bar** (the buffer carries the *same* finite value forward, it never emits NaN). With `unique_only=False` that makes **every bar an allocation point**, and under `targetpercent` the engine re-trades each bar to pull the drifted weights back to the (constant) target — i.e. it **trims winners and tops up losers every single day**. The `_apply_buffer` no-trade band only stops the *target* from jumping; it does **not** stop the daily drift-correction trades. That is the structural fill firehose, and it is also mildly **anti-convex** (it suppresses the let-winners-run drift).

**So the highest-leverage mechanism is: emit `np.nan` on no-trade bars.** That single change (a) makes rebalance cadence and event-driven trading expressible *inside a component today, no engine change*, and (b) lets weights drift between trades — which Hoffstein shows is a *free* momentum/convexity tilt (see §2.1). It is the keystone every Group-A proposal below depends on.

> Honesty flag: I have **not** run a fill count this pass, so I state the *magnitude* of the reduction as a hypothesis to confirm in the A/B. The *mechanism* (NaN row ⇒ hold; finite-every-row ⇒ daily rebalance) is a verified vbt fact, not an assertion.

**Second reframing — the handoff's G–P anchor is the wrong cost model.** Gârleanu–Pedersen "trade partially toward the aim" is derived for **quadratic/proportional** costs and prescribes a *smooth* partial step every period.¹ Our binding cost is a **fixed €1.25 per order**. For *fixed* costs the optimal control is **impulse control** (Korn 1998²; Eastham–Hastings 1988; Øksendal–Sulem): change the book only **finitely often**, and the rigorous result (Holden & Holden 2013³) is that with **fixed/flat cost elements you rebalance from outside a no-trade region to an *interior* point — *never* a full rebalance**. Proportional costs → trade to the *edge* of the band (Leland 1996⁴); fixed costs → trade *past* the edge to the *interior*, rarely. The current design violates both: it trades every bar **and** snaps to the full target.

**Net design thesis:** *trade rarely (impulse gate, NaN-hold between), and when you trade, move only part-way to an interior target (never snap-to-full); let the book drift in between (convexity for free).* Everything below is a concrete realisation of that thesis, ranked by leverage at €5k.

---

## 1. Measurement discipline (unchanged, restated for every proposal)

Rank on `trend_convexity_payoff` (benchmark-free, magnitude-aware, 2–6 mo band; `research/aegis_research/metrics/custom/convexity.py`). **Never** Sharpe/Calmar/UPI. For *every* proposal report the **triple together**: `trend_convexity_payoff` **and** `fills/yr` **and** `fees-as-%NAV` (plus net CAGR for context). At €5k the €1.25 floor is the whole game, so the decision rule is:

> **A proposal wins only if it holds-or-raises convexity AND cuts fills/yr.** A design that lifts convexity but lifts turnover more is a **regression**.

Infra note: `total_fees_paid` already exists (`metrics/stats.py:46`). Add two cheap reads to the A/B harness — `fills_per_year = pf.orders.count() / years` and `fees_pct_nav = total_fees_paid / init_cash / years`. `pf.orders.count()` is native vbt; no new engine code.

**Cost-structure corollary (important and easy to get wrong):** under a *fixed* per-order fee, only the **count** of fills matters, not their size. So the high-leverage levers are the ones that cut the *number* of fills (cadence, hysteresis/state-stickiness, no daily drift-retargeting, "don't trade if the benefit < €1.25"). Levers that only shrink trade *size* (classic G–P smoothing, vol-scaling precision) barely touch the €1.25 floor and are **low** leverage here. This is why several "obvious" turnover ideas are de-prioritised below.

---

## 2. Proposals, ranked by leverage at €5k

| # | Proposal | Layer | Code? | Primary effect | Kills fills? | Lifts convexity? |
|---|----------|-------|-------|----------------|--------------|------------------|
| **P1** | **Impulse-control rebalancing** (NaN-hold gate: cadence ∪ band ∪ state-change; + partial-to-interior step) | strategy | **yes (new)** | the keystone — makes "trade rarely + partway" expressible | **yes, large** | yes (drift = free pyramid) |
| **P2** | **Hysteresis / discrete sticky STATE** (Schmitt-trigger on score; optional Donchian-breakout state indicator) | indicator+strategy | **yes (new)** | removes near-zero whipsaw; events become rare | yes | yes (rides breakouts, bounded chop) |
| **P3** | **Smoother multi-timescale estimator** (EWMAC ensemble / log-price regression slope) | indicator | **yes (new)** | fewer false flips → fewer state changes | yes (compounding) | yes (steadier slow-horizon conviction) |
| **P4** | **Freeze/slow the vol estimate + discretise conviction** | strategy | yes (small) / param | stops daily vol-jitter re-targeting | yes — but **mostly subsumed by P1** | neutral |
| **P5** | **Breadth-/short-as-a-fee-budget** (turnover-adjusted convexity per name; cheap-borrow short mechanism) | process+config | partial (exists) | "does name N+1 earn its fee?" | enables, not direct | yes (independent macro bets) |

P1 is the single highest-impact change and the enabler for P2–P5. Recommended build order: **P1 → P3 → P2 → P4 → P5.** (P3 before P2 because a smoother signal makes the discrete state machine far more stable.)

---

### P1 — Impulse-control rebalancing (`atalanta.trendStraddleImpulse`, long-only)  ← **highest leverage, code-required**

**Idea.** Compute the same long-only FORGO conviction target as the champion *every bar*, but **only emit a finite row (a rebalance point) on "event" bars; emit `np.nan` on all other bars (hold).** Events = `cadence tick` ∪ `L1 band breach` ∪ `trend-state change`. On an event, move only a **fraction κ toward** the fresh target (interior point), **except cut exits in full** (preserve de-risk). Between events the book **drifts** with prices.

This one component subsumes the champion's levers (`entry_band`, `buffer_band`) and adds the two missing ones (`rebalance_period`, `adjust_fraction κ`). At its *neutral* settings it is already strictly better than the champion, because even with `period=0, κ=1` it **holds (NaN) between band breaches** instead of re-trading the constant target daily.

**Invariants preserved.** Absolute/time-series momentum & de-risk-in-downtrend (the score and the FORGO clip are unchanged; exits are taken in full — see below). FORGO/cash-when-flat & gross ≤ 1 (a convex step `held + κ(fresh−held)` with κ∈[0,1] between two long-only books that are each ≥0 and gross≤1 stays ≥0 and gross≤1 — the nonneg orthant and the L1 ball are convex). Long-only ≥ 0. Windowed-compute (signal/vol come from the indicators unchanged). Net-of-cost framing (the entire point).

**Manifest / param_space (sketch, conforms to the contract):**
```python
COMPONENT_MANIFEST = {
    "family": "strategies", "id": "atalanta.trendStraddleImpulse", "version": "1.0.0",
    "input_names": ["Close"], "output_name": "target_weights",
    "param_names": ["entry_band", "buffer_band", "rebalance_period", "adjust_fraction"],
    "consumes_outputs": ["trend_score", "realized_vol"],
    "defaults": {"entry_band": 0.0, "buffer_band": 0.20, "rebalance_period": 21, "adjust_fraction": 0.5},
    "owns_portfolio": False,
}
def param_space():
    return {
        "entry_band":       vbt.Param([0.0, 0.05]),
        "buffer_band":      vbt.Param([0.10, 0.20, 0.30]),
        "rebalance_period": vbt.Param([0, 21, 63]),     # 0 = event-only (no calendar tick); 21≈monthly, 63≈quarterly
        "adjust_fraction":  vbt.Param([0.25, 0.5, 1.0]),# 1.0 = snap-to-full (impulse off); <1 = interior step
    }
```

**Run / gate mechanism (pseudocode — the load-bearing part):**
```python
def _candidate_weights(score_2d, vol_2d, entry_band):   # unchanged FORGO target, every bar
    vol  = np.maximum(vol_2d, _MIN_VOL)
    raw  = np.where(np.abs(score_2d) > entry_band, score_2d / vol, 0.0)
    raw  = np.where(np.isfinite(raw), raw, 0.0)
    gross = np.abs(raw).sum(axis=1, keepdims=True)       # pre-clip (signed) gross
    raw  = np.maximum(raw, 0.0)                          # long-only: dropped shorts -> cash
    return raw / np.where(gross > 0, gross, 1.0)         # gross <= 1

def _impulse_gate(target, period, band, kappa):
    out  = np.full_like(target, np.nan)                  # NaN = HOLD (no rebalance point)
    held = target[0].copy(); out[0] = held               # establish book on bar 0
    last = 0
    for t in range(1, len(target)):
        fresh = target[t]
        cadence_due  = period > 0 and (t - last) >= period
        band_breach  = np.abs(fresh - held).sum() > band
        state_change = np.any((held > 0) != (fresh > 0)) # a name entered/left the book
        if cadence_due or band_breach or state_change:
            # impulse step: cut exits/decreases IN FULL (de-risk), add to winners PARTIALLY (pyramid)
            step = np.where(fresh < held, fresh, held + kappa * (fresh - held))
            out[t] = held = step                         # finite row => one rebalance point
            last = t
        # else: out[t] stays NaN  => engine holds drifted shares, ZERO fills this bar
    return out
```
The asymmetry `np.where(fresh < held, fresh, …)` is deliberate and convexity-optimal: **cut losers fast, add to winners slowly** — it guarantees a downtrend flip exits *fully* (de-risk invariant intact) while adds ramp in slowly (fixed-cost-optimal + manufactures the right tail). A symmetric κ on the whole move is the simpler baseline; ship the asymmetric variant as the recommended default.

**Expected effect.**
- *fills/yr & fees-%NAV:* **large reduction.** Rebalance points drop from ~every bar to ~(events). With `period=63` (quarterly) + a 0.20 band, events ≈ a handful/yr per regime + the rare de-risk flip — plausibly an order-of-magnitude fewer fills than the champion. Confirm in the A/B.
- *convexity:* **up or flat.** (i) drift-between-trades = the let-winners-run tilt Hoffstein shows "naturally embeds momentum/trend and amplifies the signal";⁵ (ii) cut-fast/add-slow is the classic convex trend shape; (iii) CFM's result that trend convexity is a *swap between the long-term (filter) variance and the short-term (rebalancing) variance*⁶ ⁷ means **slowing the rebalancing timescale lengthens the short-variance leg and *preserves* the convexity** — i.e. for a slow sleeve, rare rebalancing is convexity-*friendly*, not just cost-friendly. This is the same mechanism behind the vault's "long vol window preserves skew."

**Evidence.** Korn 1998²; Holden & Holden 2013³ (fixed cost ⇒ rebalance to an *interior* point, never full); Leland 1996⁴ (band ⇒ trade to edge, ~50% turnover cut vs quarterly); Gârleanu–Pedersen 2013¹ (partial-toward-aim, the proportional-cost cousin); Carver "position buffering … trade to the *edge* of the buffer … reduces turnover without affecting performance";⁸ Hoffstein "a little but frequently" / tranching = partial implementation + drift embeds trend;⁵ CFM convexity-as-variance-swap.⁶ ⁷

**A/B plan.** Same config/splits as the champion. Sweep the grid above (×2 signal speeds lb∈{126,252}). Report the triple per cell. Decisive cells: `period=0,κ=1` (isolates the NaN-hold effect alone vs champion) and `period=63,κ=0.5` (full impulse). Win = convexity ≥ champion AND fills/yr ↓.

---

### P2 — Hysteresis / discrete sticky STATE  ← code-required (indicator + strategy)

**Idea.** The handoff's "point-to-point score flips sign near zero" is the whipsaw engine. Replace the continuous sign gate with a **Schmitt trigger**: a name is `LONG` once `score > +enter`, returns to `FLAT` only once `score < −exit` (or `< +exit_low`); inside the dead-zone the **prior state holds**. Conviction is then a *sticky discrete* state, sized {0, full} or {0, ½, full}. **State changes become the only signal-driven rebalance events** (feed straight into P1's `state_change`). This is the natural form of trend used by CTAs.

Two realisations:
- **P2a (cheap, reuses `trend_score`):** new strategy that discretises the existing score with dual thresholds + state memory. Params `enter`, `exit`, `levels∈{2,3}`.
- **P2b (ambitious, new indicator `atalanta.donchian_state`):** long-state when `Close > rolling_max(entry_window).shift(1)`, exit-to-flat when `Close < rolling_min(exit_window).shift(1)`, with `entry_window > exit_window` so the gap *is* the dead-zone. Donchian breakout is "the base layer many CTAs still use," parameter-insensitive, and structurally hysteretic.⁹ It is absolute/time-series (price vs its own past extremes) and de-risks in downtrend (exits to cash) — invariants intact. It is *naturally* low-turnover and convex: bounded losses in chop, rides the breakout (Radius Red's "it does not blow up; it grinds; losses bounded, winners compensate").⁹

**Invariants.** Absolute & de-risk (state goes FLAT in downtrend = cash). Long-only ≥ 0. Windowed-compute (rolling max/min on full series, NaN warmup). FORGO sizing reused.

**Manifest (P2b indicator) sketch:**
```python
COMPONENT_MANIFEST = {"family":"indicators","id":"atalanta.donchian_state","version":"1.0.0",
  "input_names":["Close"],"param_names":["entry_window","exit_window"],
  "output_names":["trend_state"],"defaults":{"entry_window":126,"exit_window":42}}
def param_space(): return {"entry_window": vbt.Param([126,189,252]),
                           "exit_window":  vbt.Param([21,42,63])}
# run(): state = +1 once Close>max(entry_window).shift(1); ->0 once Close<min(exit_window).shift(1);
#        carry prior state in the dead-zone (forward-fill the latch). NaN warmup.
```

**Expected effect.** *fills/yr:* down (events are rare breakouts/flips, not daily wiggle). *convexity:* up — hysteresis removes the V-recovery whipsaw and keeps the straddle-like de-risk; breakout's bounded-loss/ride-winner shape is mechanically convex. *fees-%NAV:* down with fills.

**Evidence.** Donchian/Turtle base-layer & parameter-insensitivity;⁹ Radius Red regime-conditional bounded-loss profile;⁹ Man AHL trend = long-straddle, positive skew.¹⁰ ¹¹ CFM skew⇔convexity identity.⁷

**A/B.** Swap `trend_score`→`donchian_state` (or P2a strategy) under P1's gate; sweep windows. Report triple vs champion and vs P1-on-trend_score (isolates the estimator change).

---

### P3 — Smoother multi-timescale trend estimator  ← code-required (indicator, drop-in)

**Idea.** The current score is endpoint-to-endpoint `(C_t/C_{t-lb})^{252/lb}-1`, whose **sign flips more than a smoothed estimate** → extra state changes → extra trades. Replace with either:
- **EWMAC ensemble** (Carver): `forecast = (EWMA_fast − EWMA_slow)/σ`, averaged over several speeds (e.g. {64/256, 32/128}), vol-normalised. Multi-speed averaging is steadier and is the Newfound trend-equity template (TSMOM + price−MA + MA-crossover ensemble).¹² ⁸
- **Log-price regression slope** over the window (least-squares trend), a smoother sign than the endpoint ratio.

Keep `output_names:["trend_score"]` so it is a **drop-in** for the existing indicator — the strategy is agnostic. Still absolute/time-series (price vs its own past), de-risks when fast<slow (or slope<0). NOT cross-sectional. Invariant intact.

**Expected effect.** *fills/yr:* down — fewer false flips compound through P2's state machine and P1's gate. *convexity:* up/flat — steadier conviction at the slow convex horizon; Baltas–Kosowski find a smoother TREND rule cuts portfolio turnover ~24% vs the SIGN rule **without a significant Sharpe fall**, and an efficient vol estimator cuts costs a further ~13–25% (combined ~35%).¹³ CFM: convexity is a property of the *filter timescale*, so a cleaner slow filter sharpens it.⁶

**A/B.** New indicator `atalanta.trend_score_ewmac`; run under the *same* strategy (champion or P1). Sweep speed sets. Triple vs `trend_score`. (Caution per source rules: EWMAC forecast scalars are calibration constants — derive, don't curve-fit per asset; Carver's √-time table.⁸)

---

### P4 — Freeze/slow the vol estimate + discretise conviction  ← small code / largely subsumed

The handoff's #1 ("the book drifts every bar as vol drifts"). True for the *current* every-bar engine — but **P1 already neutralises it**: if the book is only re-set on events, daily vol jitter never gets to re-target. So P4's marginal value *after P1* is only at the event bar: a **frozen vol** (recompute every `vol_refresh` bars) or **discretised conviction** ({0,½,full} buckets) shrinks the resize, so fewer band breaches → slightly fewer events. The long vol window (126/252) is already a param and is also a documented convexity lever (vault). **Recommendation:** do not build P4 standalone; fold `vol_refresh` and a `conviction_levels` discretiser into P1 *only if* the P1 A/B shows residual vol-driven events. Avoids YAGNI surface.

**Evidence.** Baltas–Kosowski efficient-vol-estimator cost reduction;¹³ vault "long vol window preserves skew."

---

### P5 — Breadth & shorting as a *fee budget*, not a free lunch  ← process + config (mechanism exists)

The handoff notes "widening the universe made it worse." §0 explains *why*: under the every-bar engine each added name adds daily drift-correction fills, so breadth's cost is linear in names. **P1 changes this** — with NaN-hold + cadence the marginal fill cost of a name collapses, so **P1 also *unlocks* affordable breadth.** Then breadth pays where it is *independent* (Man AHL: the crisis-alpha "smile" lives in rates/bonds *and* equities; restricting from long equities/bonds *enhances* crisis protection but cuts average return and hurts the other asset class — the de-risk invariant, validated).¹⁰ ¹¹

Concrete asks (low build cost):
- **Diagnostic, not a component:** a drop-one-name attribution on `trend_convexity_payoff` **and** fills/yr — "does name N+1 earn its €1.25?" Rank the macro axes (global rates, € govt, US long/short rates, inflation, credit, gold, silver, broad commodity, global equity) by *convexity-per-fill*. Expect a small, maximally-independent set to dominate at €5k.
- **Shorting mechanism already exists:** `atalanta_trend_straddle_buffered_shortmask.py` expresses "short only borrowable names" (FORGO vs redeploy). Re-use it as *cheap-borrow-only* shorting and let the research-brief track cost it against inverse-UCITS-ETF decay. No new mechanism needed here.

**Evidence.** Man AHL crisis alpha & de-risk restriction;¹⁰ Man "Creating Portfolio Convexity";¹¹ CFM "convexity diluted by diversification & implementation steps"⁶ (a *caution*: more instruments dilute single-asset convexity — argues for *few, independent* bets, not many correlated ones).

---

## 3. What I explicitly de-prioritise (and why)

- **G–P smooth partial adjustment as the headline fix** — wrong cost model (quadratic, not fixed). Use the *impulse* form (P1) instead; keep κ<1 because Holden–Holden says fixed costs ⇒ interior step, but do not chase the G–P closed form.
- **Tranching "a little but frequently" *literally*** (daily small trades) — correct for *timing luck*, fatal for a *fixed fee* (each tiny trade still costs €1.25). Keep tranching's *drift* benefit (free in P1's NaN-hold), discard its *frequency*.
- **`min_size` positional inertia** (vbt-native: ignore an order < x% of NAV; Discord 1294023422816424050) — a real "don't trade below the fee floor" lever, but it is a `from_orders` kwarg in `portfolios.py`, **not component-authorable**. Flag as a complementary *engine/config* change (cost-aware discretisation, handoff #5), not a component this pass.
- **Sigmoid response / vol-targeting / breadth-cap throttles** — already killed on this book (sell convexity), per `trendStraddleBuffered` overview. Not revisited.

## 4. Open items to verify in the supervised follow-up (not invented here)
1. **Fill-count magnitude** of P1 vs champion (run the A/B; I asserted only the *mechanism*, not the number).
2. **Per-column NaN within a valid row** (would let P2 rebalance *only the changed names*). Row-level NaN (whole-book hold) is verified and sufficient for all primary recs; per-name selective rebalance needs a `from_filled_allocations` per-column check before relying on it.
3. **EWMAC forecast scalars** — derive from Carver's table, do not fit per asset.

---

## 5. Sources (authoritative only; per handoff sourcing rules)
1. Gârleanu & Pedersen, "Dynamic Trading with Predictable Returns and Transaction Costs," *Journal of Finance* 68(6), 2013 / NBER w15205. https://onlinelibrary.wiley.com/doi/10.1111/jofi.12080 ; https://www.nber.org/system/files/working_papers/w15205/w15205.pdf — "aim in front of the target; trade *partially* toward the aim" (quadratic-cost model).
2. Korn, "Portfolio optimisation with strictly positive transaction costs and impulse control," *Finance & Stochastics* 2, 1998. https://link.springer.com/doi/10.1007/s007800050034 — fixed+proportional cost ⇒ impulse control (finitely many trades).
3. Holden & Holden, "Optimal rebalancing of portfolios with transaction costs" (Norsk Regnesentral, 2013). http://publications.nr.no/1503320049/rebalance-HLHolde-2013.pdf — proportional ⇒ rebalance to *boundary*; **fixed/flat cost ⇒ rebalance to an *interior* state, never a full rebalance.**
4. Leland, "Optimal Asset Rebalancing in the Presence of Transactions Costs," 1996. https://ideas.repec.org/p/wpa/wuwpfi/9610004.html — no-trade band, trade to nearest *edge*, ~50% turnover cut vs quarterly.
5. Hoffstein (Newfound), "Tranching, Trend, and Mean Reversion," 2020. https://blog.thinknewfound.com/2020/04/tranching-trend-and-mean-reversion/ — "a little but frequently"; drift *embeds momentum/trend and amplifies the signal." + "Rebalance Timing Luck: The Difference Between Hired and Fired," SSRN 3319045.
6. CFM, "The Convexity of Trend Following," 2018. https://www.cfm.com/wp-content/uploads/2022/12/266-2018-The-Convexity-of-trend-following.pdf — convexity mechanical vs the underlying, *diluted* by diversification & implementation.
7. Bouchaud, Dao, Deremble, Lempérière, Nguyen, Potters (CFM), "Tail protection for long investors: Trend convexity at work," arXiv:1607.02410, 2016. https://arxiv.org/pdf/1607.02410 — trend P&L = **swap between long-term (filter) variance and short-term (rebalancing) variance**; "long-vol" attribute. + CFM "Making fat right tails fatter," 2018 (skew⇔convexity identity).
8. Carver, "This Blog is Systematic" — position buffering ("trade to the *edge* of the buffer; reduces turnover without affecting performance; 10% of avg position"), EWMAC. https://qoppac.blogspot.com/2021/ ; *Systematic Trading*. Cautionary applied case: `github.com/ilahuerta-IA/carver-systematic-trading` — "EWMAC trend following not viable after [daily] swap costs … trend following needs cheap holding costs … not a parameter problem, a *structural* incompatibility" (direct analogue to our €1.25 floor).
9. Donchian/Turtle breakout as hysteretic low-turnover base layer: https://quantest.andgenie.jp/en/blog/donchian-channel-breakout/ ("N-day high in, M-day low out; many CTAs still use as base layer; parameter-insensitive"); Radius Red, "Regime-Conditional Alpha," 2026 (bounded-loss/ride-winner convex profile). https://www.radiusred.uk/blog/posts/2026-05-26-regime-conditional-alpha-validation/
10. Man AHL (Hamill, Rattray, Van Hemert), "Trend Following: Equity and Bond Crisis Alpha." https://www.man.com/insights/trend-following-equity-and-bond-crisis-alpha — positive skew (stronger for faster), long-straddle analogy, equity & bond "smile"; **restricting from long equities/bonds enhances crisis protection but cuts avg return** (de-risk invariant).
11. Man Group, "Creating Portfolio Convexity: Trend Versus Options." https://www.man.com/insights/creating-portfolio-convexity — trend "convexity smile," multi-asset diversification of a tail hedge.
12. Newfound US Trend Equity Index — ensemble (TSMOM + price−MA + MA-double-crossover) × 120 formation horizons, 20-day holding, daily-staggered (tranched). https://www.thinknewfound.com/newfound-research-us-trend-equity-index
13. Hurst, Ooi & Pedersen, "Demystifying Managed Futures," *J. Investment Management*. http://docs.lhpedersen.com/DemystifyingManagedFutures.pdf — **gross** Sharpe: daily≈weekly, decays at monthly/quarterly, *and decays faster for fast signals* (slow signals tolerate slow rebalance). Baltas & Kosowski, "Demystifying Time-Series Momentum Strategies" (CME). https://www.cmegroup.com/education/files/demystifiing-time-series-momentum-strategies.pdf — smoother TREND rule cuts turnover ~24% (no significant Sharpe fall); efficient vol estimator cuts costs ~13–25% (combined ~35%). Moskowitz, Ooi & Pedersen, "Time Series Momentum," *JFE* 2012 (monthly rebalance baseline). NBIM Discussion Note 2014 — turnover falls as look-back & holding period rise.
14. AQR (Frazzini, Israel, Moskowitz), "Trading Costs of Asset Pricing Anomalies." https://www.aqr.com/Insights/Research/Working-Paper/Trading-Costs-of-Asset-Pricing-Anomalies — portfolio-construction to cut *realised* trading cost raises net returns without style drift (momentum benefits most).
