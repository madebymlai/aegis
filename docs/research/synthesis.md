# Strategy Synthesis

Source: convergence of Perplexity and Gemini deep research on
`docs/research/researcher.txt`. See `raw-results.md` for full outputs
and divergence notes.

Architecture: one regime-aware rotation strategy. The regime gate
determines how the allocation budget is split between an offensive
and a defensive sleeve. Within each sleeve, the same core logic
applies: rank by momentum, gate with absolute momentum, size
positions. This is one strategy component, not two — the regime
state is an input, not a strategy selector.

---

## Regime detection

The portfolio operates in one of three states, evaluated at every
decision bar.

| State | Condition | Allocation target |
|-------|-----------|-------------------|
| **Risk-on** | Both canary assets have positive momentum | Offensive sleeve only |
| **Mixed** | Exactly one canary asset has negative momentum | 50% offensive / 50% defensive |
| **Risk-off** | Both canary assets have negative momentum | Defensive sleeve only |

Canary assets: **SPY** and **TLT**.

Canary signal per asset: multi-period momentum score (see indicators
below). Positive = healthy, zero or negative = stressed.

Why SPY + TLT: they represent the two dominant macro risk factors
(equity beta and duration). When both break down simultaneously, the
macro environment is hostile to nearly all risk assets. Both research
sources converged on this pair as the gate — Perplexity via SPY
absolute momentum, Gemini via Keller's canary universe.

---

## Offensive sleeve: momentum rotation with vol-aware sizing

Budget: 100% in risk-on, 50% in mixed, 0% in risk-off.

Universe: IWM, EEM, GLD, DBC, VNQ, XLE, XLU (7 symbols).

SPY and TLT are excluded from the investable pool — they serve as
canary sentinels, informing the regime without competing for
allocation.

### Logic

1. Rank offensive assets by momentum score (descending).
2. Select top N (3-4).
3. Gate each selected asset with absolute momentum: if its momentum
   score is negative, replace its allocation with cash (NaN).
4. Size surviving positions by inverse realized volatility, then
   normalize to sum to the offensive sleeve's budget.

### Why this combination

- Cross-sectional momentum ranking picks relative winners
  (Asness et al., Moskowitz et al.).
- Absolute momentum gate removes assets in structural downtrends even
  if they rank well relatively — prevents catching falling knives
  (Antonacci).
- Inverse-vol sizing equalizes risk contribution across held positions
  so one volatile asset doesn't dominate the portfolio
  (Harvey et al.).

---

## Defensive sleeve: safe-haven momentum rotation

Budget: 0% in risk-on, 50% in mixed, 100% in risk-off.

Universe: TLT, GLD, UUP (3 symbols).

### Logic

1. Rank defensive assets by momentum score (descending).
2. Select the top 1-2.
3. Gate with absolute momentum: if the best defensive asset has
   negative momentum, go to cash (all NaN).
4. Equal-weight among survivors.

### Why these three

- TLT: flight-to-quality in equity drawdowns (unless rates are rising).
- GLD: inflation hedge and crisis hedge when bonds fail (2022 regime).
- UUP: ultimate safe haven when both stocks and bonds sell off
  (dollar strength in global stress).

The three cover the main risk-off scenarios: deflation scare (TLT
wins), inflation scare (GLD wins), global deleveraging (UUP wins).

---

## Indicators

All computed daily on close prices. Two market indicators.

### Dropped: RM ratio (price / SMA)

Evaluated as a candidate additional gate. Hardened OOS testing
(`research/prototypes/rm_vs_momentum_score_v2.py`) across 13 rolling
OOS splits (2013-2025), 4 lookback values, per asset class, with
10bps round-trip costs showed:

- For equities, bonds, REITs: RM vetoes the most profitable entries
  (early recovery trades where momentum turns positive before price
  crosses the SMA). Score>RM bucket returns +0.85% to +1.29% at 20d
  vs +0.28% to +0.33% for BothIN. RM hurts.
- For commodities (GLD, DBC) and currency (UUP): RM veto is
  marginally correct. These asset classes are more mean-reverting.
- Across time: unstable. RM helps in 6 of 13 OOS years, hurts in 7.

The momentum score's own sign (> 0) already handles the absolute
gate. RM adds a slower, lagging duplicate that costs more than it
saves on 7 of 10 symbols.

### 1. Multi-period momentum score

Per-asset composite trend strength across four horizons.

```
R(Δ) = (Close(t) / Close(t - Δ))^(252/Δ) - 1

Score(t) = 12·R(21) + 4·R(63) + 2·R(126) + 1·R(252)
```

Horizons: 21d (1mo), 63d (3mo), 126d (6mo), 252d (12mo).
Weighting: front-loaded toward recent momentum (40% from 1mo).

Roles:
- Canary signal: sign of score for SPY and TLT determines regime.
- Offensive ranking: score determines which assets get allocation.
- Defensive ranking: score determines which safe haven gets capital.
- Absolute momentum gate: negative score = excluded.

Optimize: the four horizon lengths and their weights.

### 2. Realized volatility

Short-window annualized standard deviation of log returns.

```
σ(t) = std(log_returns, window=Lv) * sqrt(252)
```

Default Lv = 20.

Roles:
- Inverse-vol position sizing in the offensive sleeve.
- Not used for ranking or gating — purely for sizing.

Optimize: Lv in range 10-40.

### Dropped: Turnover threshold as indicator

Originally listed here as indicator #3. Removed because the
turnover gate computes `sum(|w_target - w_drift|)` — it needs the
strategy's target weights and the portfolio's drifted weights, neither
of which are available to the indicator contract (which only receives
OHLCV market data). The previous implementation faked this by
computing drift from an equal-weight baseline, which is a different
calculation.

The turnover threshold is now a **strategy-internal parameter** (tau)
on the regime rotation strategy. See strategy section below.

---

## Rebalance cadence and turnover gate

Indicators computed daily. The strategy computes new target weights
daily but does not always act on them. Execution is gated by a
turnover threshold that lives inside the strategy component:

```
turnover(t) = sum(|w_target(t) - w_drift(t)|)
rebalance if turnover(t) >= tau OR regime changed
```

- `w_target(t)`: weights the strategy wants right now.
- `w_drift(t)`: current portfolio weights after price drift since
  last rebalance.
- `tau`: minimum absolute turnover to trigger a rebalance
  (default 0.08 = 8%).

Rules:
- Canary regime flip (risk-on ↔ mixed ↔ risk-off) triggers
  immediate rebalance regardless of tau.
- Within a stable regime, rebalance only when drift exceeds tau.
- Expected effective frequency: ~1 trade/day across all symbols.
- Typical holding period: 15-25 trading days per position.

This gate cannot be an indicator component because it requires the
strategy's own output (target weights) and the portfolio's state
(drifted weights), neither of which are available to the indicator
contract.

---

## Parameter summary

| Parameter | Owner | Default | Optimize range | Affects |
|-----------|-------|---------|---------------|---------|
| Momentum horizons (h1-h4) | indicator | 21, 63, 126, 252 | 15-30, 42-84, 100-180, 200-300 | Score sensitivity |
| Momentum weights (w1-w4) | indicator | 12, 4, 2, 1 | relative ratios | Short vs long term bias |
| Vol window (Lv) | indicator | 20 | 10-40 | Sizing responsiveness |
| Top N offensive | strategy | 3 | 2-4 | Concentration vs diversification |
| Top K defensive | strategy | 1 | 1-2 | Defensive concentration |
| Turnover threshold (tau) | strategy | 0.08 | 0.05-0.20 | Trade frequency |

---

## Meta-architecture: RF strategy allocator

This strategy is designed to be one input to a future random forest
meta-allocator. The RF does not look at market data — it sits above
multiple strategies and learns which strategy's output to trust (or
how to blend them) based on strategy-level features: recent
performance, agreement/disagreement between strategies, regime state,
confidence metrics.

The RF adds value only when the strategies underneath have genuinely
different views of the market. Three momentum variants split by
regime would mostly agree — the RF would have nothing to learn.
The goal is 2-3 strategies with maximally different philosophies:

```
Market data
  → Strategy 1: momentum rotation (this document)
  → Strategy 2: (structurally different — e.g. mean-reversion,
                  carry, risk-parity, or ML-based)
  → Strategy 3: (structurally different)
      ↓
  Each produces a target_weights frame
      ↓
  RF allocator selects or blends based on strategy-level features
      ↓
  Final allocation to portfolio layer
```

Design constraint for future strategies: they should disagree with
this momentum rotator in meaningful market conditions. A strategy
that always agrees adds no information to the RF. Prioritize
strategies with different return drivers — not different parameters
on the same driver.

The regime gate stays inside this strategy (canary is a simple
binary decision, not worth delegating to the RF). The RF's job is
the harder question: which *philosophy* works now.

---

## Failure modes

| Scenario | What breaks | Mitigation |
|----------|------------|------------|
| Sideways chop | Canary flips repeatedly, high turnover | tau threshold dampens; front-loaded momentum weighting smooths |
| V-shaped recovery | Momentum lags, misses the bounce | Short-horizon weighting (1mo = 40%) helps; still structurally late |
| Stocks and bonds down together | TLT fails as defensive; canary fires correctly but defensive sleeve suffers | GLD and UUP provide alternatives; all-NaN (cash) is the last resort |
| Low-vol trending market | Few rebalances, potential underperformance vs buy-and-hold | Acceptable — system prioritizes risk-adjusted returns, not raw return |
| Correlation spike across all assets | Inverse-vol sizing doesn't account for correlation | Could add covariance (Gemini approach) but adds estimation noise with only 10 assets; test empirically |
