# The allocator realizes a static risk budget by volatility targeting

Status: accepted (implementation pending; refines the scaling step of ADR-0001 and feeds
the netting of ADR-0002)

Aegis Trader gains an **Allocator**: a pure module that turns each sleeve's signed target
weights into the **budget-scaled** vector the rebalancer nets, replacing ADR-0001's static
*capital* `Sleeve Budget` multiply (`scaled = w · budget`) with a **static *risk* budget
realized by volatility targeting**. The risk policy is static config; the capital weight is
a deterministic function of the static risk share, the sleeve's **realized** volatility, and
a book volatility target — `capital_weight_s = risk_share_s · (σ_target / σ̂_s)`, scaled so
the netted book targets a constant volatility.

This does **not** cross ADR-0001's line that live, return-conditioned allocation is alpha
and must live in RD as an Execution Bundle. The allocator conditions only on **realized
volatility — a risk quantity computed from bars Trader already buffers — never on a return
or regime forecast**. It is risk control of the same class as the per-instrument drift band
and the gross/net caps (ADR-0002), which also read market state yet encode no return view.
What ADR-0001 called "static budgets" is therefore refined to **static *risk* budgets**: the
risk *shares* are frozen config, and the *capital weights* float inversely with realized vol
to hold those shares. Crossing from a volatility input to a return forecast is exactly the
line that would make it alpha and push it back to RD.

**Risk is budgeted hierarchically, top-down by group.** Sleeves belong to **risk groups** —
**Floor / Target / Expansion** (the Tiered Strategy Roster). The budget is allocated across
groups first, then within each group, so a cluster of correlated sleeves cannot silently
dominate the book's risk.

- **Floor** (both signs of skew): a small-N conviction tilt of **~0.60 trend / ~0.40 carry**
  of the floor's risk, held **net-convex** (book quarterly skew ≥ 0). The trend pole is the
  *standing* crisis engine; carry is the income overlay.
- **Target** (tail): a **fixed, small convexity budget** sized highest-efficiency-first
  (convex payoff per unit carry × crisis reliability), **with no timer**. The rebalancer's
  tight `band_up` / loose `band_down` (ADR-0002) monetizes it; the allocator only sets its
  small risk share.
- **Expansion** (market-neutral): off-axis and breadth-gated — **zero risk until a wider
  universe earns it**.

**Within a multi-name sleeve**, weights default to **Equal Risk Contribution** (robust, no
return forecast), never a return-driven optimizer.

**The rebalance fires on sleeve-weight bands with partial reversion.** Vol-targeting nudges
each sleeve's scalar every period; to avoid churn the allocator re-scales a sleeve only when
its weight drifts past a band, and then **partially** (toward, not all the way to, target) —
cutting turnover while letting winners run. The per-instrument drift band and the
realized-book gate (ADR-0002) are unchanged and remain authoritative downstream.

## Considered options

- **Keep the static *capital* budget** (today's `scaled = w · budget`): rejected. A capital
  budget lets a sleeve's *risk* share drift with its volatility. A ~3% **notional** `VOOL`
  tail is a dominant **risk** share — VIX futures run ~60–80% vol against ~10% for the floor —
  which is exactly why a calm-market 5-year backtest let the tail drive the book to −8.5%.
  Allocating risk, not capital, is the practitioner default.
- **A top-level mean-variance / max-Sharpe optimizer over the sleeves**: rejected. Out of
  sample no optimizer reliably beats `1/N` at this N — the estimation window needed is ~3,000
  months for 25 assets (DeMiguel/Garlappi/Uppal 2009); the gain from "optimal" diversification
  is more than offset by estimation error. A static risk budget with a small-N conviction tilt
  is the robust shape, and small N is precisely where a tilt off equal weight is defensible.
- **A regime / dispersion model that re-weights sleeves live** (size the tail up in stress,
  rotate trend↔carry by regime): rejected twice over. It is **alpha** — by ADR-0001 it must
  carry Provenance and live in RD as a composite bundle, not in Trader. And it does not work:
  tactical reallocation needs a ~66–70% hit rate just to match a static book (Sharpe 1975),
  and RD's own tail campaign found every up-sizing **trigger fired post-shock** on daily bars.
  Trend, not a timer, is the standing crisis engine.
- **Skew-neutral floor weighting** (solve the carry weight that zeroes book skew): rejected.
  RD's floor diary found that weight swings 0.15↔0.59 across windows and over-buys carry —
  deeper drawdown than trend alone and diluted crisis capture. A drawdown-payer floor should
  **keep** its positive skew, so a fixed ~0.40 carry net-convex weight replaces it.
- **A permanent or large tail allocation**: rejected. A standing tail pays the full
  crash-insurance premium every calm day and degrades compounding; the tail earns its slot
  only as a small, convexity-per-bleed-justified overlay that the rebalance monetizes.
- **Calendar rebalancing to fixed weights**: rejected. Naive periodic rebalancing is a form
  of poor market timing (coin-toss performance) and fights momentum by mechanically selling
  winners; band-triggered partial reversion cuts turnover and lets winners run.
- **Book-level vol-targeting inside a bundle**: rejected as the home for it. Per-sleeve
  signal-level risk scaling is the bundle's business, but the **book-level** risk budget
  across sleeves is Trader's, because only Trader sees the netted book and the shared NAV
  (ADR-0001). The two compose: bundles emit signals, the allocator sets cross-sleeve risk
  shares and the book vol target.

## Consequences

- **Book Config gains a risk-budget schema.** `SleeveConfig` carries a **risk share** + a
  **group** (Floor/Target/Expansion) in place of the bare capital `budget` float; `BookConfig`
  carries the **book volatility target** and per-sleeve **min/max weight bands** (the tail
  keeping ADR-0002's asymmetric `band_up`/`band_down`). Forward-First: the static `budget`
  float is replaced outright — no compatibility shim.
- **A new deep module `domain/allocator.py`.** Pure, importing no Nautilus types:
  `(per-sleeve target weights, realized-vol estimate per sleeve, risk budget) → budget-scaled
  per-sleeve weights`. The rebalancer's scaling line calls it; netting, bands, caps, and
  monetization (ADR-0002) are unchanged downstream. Small interface, deep implementation.
- **Realized-vol is a new Trader input, not a forecast.** It is estimated from the bar history
  Trader already buffers (e.g. an EWMA of sleeve returns) and is a risk quantity, so it stays
  inside Trader without becoming alpha.
- **The book de-levers on its own.** As realized vols rise the capital weights fall to hold
  the vol target — a natural de-lever, not a knee-jerk cut; gross can sit well below the cap,
  and the gross/net caps (ADR-0002) remain the authoritative ceiling.
- **Determinism / testability.** Given the same weights, vol estimates, and config the
  allocator is a pure deterministic function, unit-testable in isolation under TDD with no
  Nautilus.
- **Re-validation.** The 5-year commingled backtest re-runs under the risk-budgeted allocator;
  per-sleeve attribution (commit `5d40170`) and the realized-book gate consume the new weights
  with no change.
- **Open knobs (settled in the PRD, not here):** the across-group risk split, the book vol
  target level, the tail instrument and its convexity-unit budget, and the band widths /
  reversion fraction. These are calibration, not architecture.

## Evidence

- RD vault (`aegis-rd/research/vault/`): `the-tiered-strategy-roster` (Floor/Target/Expansion
  order of operations); `the-ucits-constrained-tail-sleeve` (episodic triggers fire post-shock
  → fixed small tail + rebalance monetization); `runs/floor/2026-06-14` (fixed ~0.40 carry,
  net-convex; skew-neutral rejected as window-unstable); `convexity-as-the-axis-of-strategy-diversification`.
- External: DeMiguel, Garlappi & Uppal (2009) `1/N` out-of-sample; Yuan, "Why Naive 1/N Is Not
  So Naive" (small-N tilt); Roncalli, equally-weighted risk contributions (ERC); Man Group,
  building a multi-strategy portfolio (hierarchical risk groups); Robeco, Dynamic 1/N (bands +
  partial reversion); Harvey et al., Strategic Rebalancing (rebalancing is concave, trend
  offsets it); Universa/Spitznagel and convexity-unit budgeting (fixed small tail, no timing).
