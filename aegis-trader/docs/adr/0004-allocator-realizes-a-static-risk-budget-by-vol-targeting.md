# The allocator realizes a static risk budget against the live risk structure

Status: accepted (allocator implemented in `aegis-rd-bu4` slices 1–6; knob calibration +
HITL sign-off `aegis-rd-bu4.7` pending; **amends ADR-0001's static-budget boundary** and
feeds the netting/gate of ADR-0002)

Aegis Trader gains an **Allocator**: a pure module that turns each sleeve's signed target
weights into the budget-scaled vector the rebalancer nets, replacing ADR-0001's static
*capital* `Sleeve Budget` multiply (`scaled = w · budget`) with a **static *risk* budget
solved against the book's live risk structure**.

ADR-0001 ruled that "Trader's budgets are static" and that conditioning allocations on
market state is alpha belonging to RD. **This ADR amends that boundary** (see ADR-0001,
amended). The line is not *static vs dynamic*; it is **risk-conditioning vs
return-forecasting**. The Allocator may condition weights on the *realized risk structure* —
sleeve **volatilities**, the sleeve **correlation/covariance** matrix, **drawdown** state,
and realized **skew/convexity** — to hold a frozen risk budget, target a constant book
volatility, de-lever in stress, and keep the book net-convex. None of these forecast
returns; they are estimable, comparatively stationary risk quantities, the same class as the
gross/net caps and drift bands (ADR-0002) that already read market state. What remains alpha
— and stays in RD as a provenance-carrying Execution Bundle — is any signal that encodes a
**return view**: which sleeve will outperform, or when to size the tail up on a regime /
dispersion / valuation signal. The dividing test is whether the input **forecasts returns**
or **measures risk**.

Decision points:

- **Risk, not capital, solved against the live covariance.** Each sleeve carries a frozen
  **risk share**; capital weights are solved so risk *contributions* match the budget given
  the **realized correlation/covariance** (Equal-Risk-Contribution / hierarchical risk
  parity across sleeves), then scaled so the netted book targets a constant volatility. The
  diagonal `risk_share_s · (σ_target / σ̂_s)` is only the zero-correlation degenerate case;
  the Allocator uses the off-diagonal too, so a cluster of correlated sleeves is down-weighted
  and cannot dominate the book's risk. This covariance awareness is the scope ADR-0001's
  blanket "static budgets" wrongly foreclosed.
- **Hierarchical, top-down by group.** Sleeves belong to **risk groups** — **Floor / Target /
  Expansion** (the Tiered Strategy Roster). Risk is allocated across groups first (clustered
  by realized correlation), then within each group.
  - **Floor** (both signs of skew): a small-N conviction tilt of **~0.60 trend / ~0.40 carry**
    of the floor's risk, held **net-convex** as a *live* constraint (book quarterly skew ≥ 0
    on realized returns). Trend is the standing crisis engine; carry is the income overlay.
  - **Target** (tail): a **fixed, small convexity budget**, **with no timer**. Coverage is
    denominated in **book NAV delivered at an attachment (stress) move** (e.g. −20%) and
    filled highest-efficiency-first to a coverage target, capped per-candidate by capacity and
    collectively by an **annual-carry (premium) budget** — so either the coverage target or
    the premium ceiling binds first. The rebalancer's tight `band_up` / loose `band_down`
    (ADR-0002) monetizes it.
  - **Expansion** (market-neutral): off-axis, breadth-gated — **zero risk until a wider
    universe earns it**.
- **Within a multi-name sleeve**, weights default to **Equal Risk Contribution**.
- **The book de-levers on realized drawdown / vol.** As realized volatilities rise or a
  drawdown deepens, capital weights fall to hold the vol target — a natural de-lever, not a
  return call. The gross/net caps (ADR-0002) remain the authoritative ceiling.
- **Rebalance on sleeve-weight bands with partial reversion.** The Allocator re-scales a
  sleeve only when its weight drifts past a band, and then **partially** (toward, not all the
  way to, target) — damping vol-target churn while letting winners run. The per-instrument
  drift band and the realized-book gate (ADR-0002) are unchanged and remain authoritative.

## Considered options

- **Keep the static *capital* budget** (today's `scaled = w · budget`): rejected. A capital
  budget lets a sleeve's *risk* share drift with its volatility; the ~3% **notional** `VOOL`
  tail is a dominant **risk** share (VIX futures ~60–80% vol vs ~10% for the floor), which is
  exactly why a calm-market 5-year backtest let the tail drive the book to −8.5%.
- **Diagonal vol-targeting only (ignore correlations)**: rejected as too thin — and the part
  ADR-0001's "static budgets" wrongly foreclosed. Equalising *variance* while ignoring the
  covariance still lets two correlated sleeves concentrate the book's risk (Man Group's
  hierarchy point). The Allocator uses the full covariance (ERC/HRP across sleeves).
- **A top-level mean-variance / max-Sharpe optimizer**: rejected on **research**, not on
  ADR-0001. Out of sample no optimizer reliably beats `1/N` at this N — the estimation window
  needed is ~3,000 months for 25 assets (DeMiguel/Garlappi/Uppal 2009); the gain from
  "optimal" diversification is more than offset by estimation error. Risk budgeting (ERC/HRP)
  uses only the covariance, never expected returns, so it sidesteps the estimation-error trap
  while still respecting correlations.
- **A live regime / dispersion model that re-weights sleeves or sizes the tail up**: rejected
  on **research** (the primary reason, not ADR-0001). Tactical reallocation needs a ~66–70%
  hit rate just to match a static book (Sharpe 1975), and RD's own tail campaign found every
  up-sizing **trigger fired post-shock** on daily bars. It is *also* return-conditioning, so
  if it is ever built it ships as an RD Execution Bundle with Provenance — never live in
  Trader. Trend, not a timer, is the standing crisis engine.
- **Skew-neutral floor weighting** (solve the carry weight that zeroes book skew): rejected.
  RD's floor diary found that weight swings 0.15↔0.59 across windows and over-buys carry —
  deeper drawdown than trend alone and diluted crisis capture. A drawdown-payer floor should
  **keep** its positive skew, so a fixed ~0.40 carry net-convex weight replaces it.
- **A permanent or large tail allocation**: rejected. A standing tail pays the full
  crash-insurance premium every calm day and degrades compounding; the tail earns its slot
  only as a small, convexity-per-bleed-justified overlay the rebalance monetizes.
- **Calendar rebalancing to fixed weights**: rejected. Naive periodic rebalancing is a form
  of poor market timing (coin-toss performance) and mechanically sells winners;
  band-triggered partial reversion cuts turnover and lets winners run.

## Consequences

- **Book Config gains a risk-budget schema.** `SleeveConfig` carries a **risk share** + a
  **group** (Floor/Target/Expansion) in place of the bare capital `budget` float; `BookConfig`
  carries the **book volatility target**, the **drawdown-de-lever** parameters, and per-sleeve
  **min/max weight bands** + a **reversion fraction** (the tail keeping ADR-0002's asymmetric
  `band_up`/`band_down`). Forward-First: the static `budget` float is replaced outright — no
  compatibility shim. The **Target tail** is sized by a `tail_convexity_budget` block — an
  `attachment` move, a `coverage_target` (NAV at that move), an optional `annual_carry_budget`
  premium ceiling, and per-candidate `payoff_at_attachment` / `annual_carry` /
  `crisis_reliability` / `capacity_risk_share` scores (efficiency derived, not stored) — whose
  resulting **risk share** feeds the same ERC / vol-target solve as every other sleeve.
- **A new deep module `domain/allocator.py`.** Pure, importing no Nautilus types:
  `(per-sleeve target weights, realized covariance estimate, risk budget) → budget-scaled
  per-sleeve weights`. It owns the ERC/HRP solve, the group hierarchy, the net-convex skew
  budget, the drawdown de-lever, and the sleeve-weight bands. It slots in at the rebalancer's
  `scaled = w · budget` seam; netting, per-instrument bands, caps, and monetization (ADR-0002)
  are unchanged downstream. Small interface, deep implementation.
- **A realized covariance/vol estimate is a new Trader input, not a forecast.** Estimated from
  the bar history Trader already buffers (e.g. an EWMA covariance of sleeve returns); it
  *measures risk*, so it stays inside Trader without becoming alpha.
- **ADR-0001 is amended, not merely refined.** The "static budgets / conditioning is alpha"
  consequence is re-drawn to "static **risk** budgets; risk-conditioning lives in Trader,
  return-forecasting in RD."
- **Determinism / testability.** Given the same weights, covariance estimate, and config the
  Allocator is a pure deterministic function — unit-testable in isolation under TDD with no
  Nautilus.
- **Re-validation.** The 5-year commingled backtest re-runs under the risk-budgeted Allocator;
  per-sleeve attribution (commit `5d40170`) and the realized-book gate consume the new weights
  with no change.
- **Open knobs (settled at re-validation in `aegis-rd-bu4.7`, not here):** the across-group
  risk split, the book vol target level, the drawdown-de-lever curve, the tail's coverage
  target / attachment / annual-carry budget and per-candidate scores, and the band widths /
  reversion fraction. Calibration, not architecture.

## Evidence

- RD vault (`aegis-rd/research/vault/`): `the-tiered-strategy-roster` (Floor/Target/Expansion
  order of operations); `the-ucits-constrained-tail-sleeve` (episodic triggers fire post-shock
  → fixed small tail + rebalance monetization); `runs/floor/2026-06-14` (fixed ~0.40 carry,
  net-convex; skew-neutral rejected as window-unstable); `convexity-as-the-axis-of-strategy-diversification`.
- External: DeMiguel, Garlappi & Uppal (2009) `1/N` out-of-sample; Yuan, "Why Naive 1/N Is Not
  So Naive" (small-N tilt); Roncalli, equally-weighted risk contributions (ERC); Man Group,
  building a multi-strategy portfolio (hierarchical, correlation-clustered risk groups);
  Robeco, Dynamic 1/N (bands + partial reversion); Harvey et al., Strategic Rebalancing
  (rebalancing is concave, trend offsets it); Universa/Spitznagel (fixed small tail, no
  timing, "crash-bang-for-the-buck"). The convexity-**premium-budget** shape now shipped is
  grounded in published practitioner policy: PSERS' Tail-Risk Mitigation Strategy (a fixed
  annual premium budget that caps spend; max yearly loss = the budget), Resonanz Capital
  (coverage target + pay-off efficiency = crisis gains ÷ premiums), and AQR's Put-vs-Trend
  study (always-on, constant budget; the cost / reliability / convexity trade-off).
