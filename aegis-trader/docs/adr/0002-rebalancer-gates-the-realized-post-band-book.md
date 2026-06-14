# The rebalancer gates the realized post-band book

Status: accepted (implementation pending; refines the rebalance step of ADR-0001)

Aegis Trader suppresses rebalance churn with a **drift band**: a leg trades only when its
realized weight has drifted from target by more than the band. The band means under-band
legs are *deliberately held* at their current weight `w_c`, so the book Trader actually
holds after a cycle — `{traded legs → rounded target} ∪ {held legs → w_c}` — is **not**
the all-at-target book. Therefore the **rebalancer** gates the **realized post-band,
post-round book** against the book's gross/net/per-name caps, not the requested target
book. The gate is **authoritative**; the band is **subordinate** and may only suppress
churn *within* the gate's compliance envelope.

This book gate is **not** the wheel's **Allocation Policy**. Per root ADR-0001 (amended
2026-06-14) the bundle is a pure transform and does no gating; exposure caps live in the
**Book Config**, and the rebalancer invokes the one shared `aegis-runtime` validator at
two scopes — **sleeve** (fail-closed attribution, plus the provenance assertion that the
Manifest cap ≤ the sleeve's research-validated cap) and **book** (this realized-book
invariant). Same validator, distinct scopes.

Gating the target while emitting the band-filtered book is a tolerance gap of the same
class as the NoCash tripwire (ADR-0011): each held leg is within band of target, but the
drifts sum — `N` legs nudged the same way by a directional market move give up to
`N·band` of un-gated gross/net drift through a `gross_cap` the gate never saw, and the
breach correlates with crisis days, when caps matter most. By Aegis's own "no tolerance"
stance this is a fail-closed correctness requirement, not an optimisation.

## Considered options

- **Gate the all-at-target book, then band-filter** (the naive order): rejected — it
  validates a book Trader will not hold; see the `N·band` correlated-drift breach above.
- **Per-instrument band only** (no book-level trip): rejected as insufficient. A
  per-instrument band does not bound *aggregate* drift; the book can wander far from
  intended weights with no single leg tripping. A book/sleeve-level drift trip (aggregate
  gross, net, and per-sleeve-budget deviation) is the fidelity floor that forces a fuller
  cleanup even when every leg is in-band — it only ever *adds* trades and is subordinate to
  the gate.
- **A book-level turnover throttle** ("don't rebalance unless aggregate drift > X"):
  rejected — and the mirror image of the fidelity trip above, not to be confused with it.
  The trip *adds* trades when aggregate drift is high (safe); a throttle *suppresses* trades
  when aggregate drift is low (unsafe), and can block the one trade the architecture exists
  to make. In a pure vol event the non-equity floor barely moves, so aggregate drift ≈ the
  tail's own small (2–5% sleeve) drift and stays under any throttle `X` — yet the
  per-instrument band has already tripped on the ballooned `VOOL` weight and must trim the
  spike. A throttle would block exactly that monetisation. The tail's trip must never be
  conditioned on whether the rest of the book moved. The residual concern (many small but
  cost-justified trades on a big-move day) is already handled: a band set above round-trip
  cost makes every tripped trade cost-justified by construction, sub-increment trades are
  killed by rounding / min-order-size, and a big-move day is precisely when you *should*
  rebalance. If micro-churn still bites, the knob is band *width*, not a second gate — one
  parameter, no new failure mode. KISS/YAGNI for a daily ~20-name book.
- **One symmetric band for every instrument**: rejected for the tail. In calm markets
  `VOOL` bleeds and its weight drifts *down*; a symmetric band keeps topping it back up —
  buying a decaying asset every cycle, paying the bleed plus turnover. The tail needs
  `band_up` tight (catch the spike → trim → monetise) and `band_down` loose (let it bleed
  before topping up), which a single threshold cannot express.
- **A min-cost-set solver for the gate override**: rejected for v1. When the realized book
  breaches, widening the trade set *toward target* in a deterministic order has a
  **proven compliant terminus** — the full trade-to-target book is compliant by
  construction (the overlay validates each sleeve ≤ its Manifest cap, and Sleeve Budgets
  sum `< 1` and net), so a solver is unnecessary complexity and loses reproducibility.
- **Trade-to-edge by default** (move a tripped leg only to the band rim): rejected as the
  default. Edge-parking leaves legs at the rim so they re-trip next cycle and raises
  tracking error; trade-to-target is the default, with trade-to-edge a per-book option if
  measured turnover cost bites.

## Consequences

- **Rebalance pipeline:** `targets → net by FIGI → size→qty→round → per-instrument band
  selects a tentative trade set → book-level band may widen it → assemble the realized
  post-band book → gate the realized book → if breach, widen toward target deterministically
  until compliant (fail closed if even full-target breaches) → emit (open venues only)`.
- **Band lives in weight space**, per instrument, as a pair `(band_up, band_down)`
  defaulting symmetric to the book band; `w_c = position_notional_base / NAV_base`. Trip
  when `(w_c − w_t) > band_up` (trim) or `(w_t − w_c) > band_down` (add). Overrides are
  per-sleeve / per-instrument in the Book Config. The tail sets `band_up` tight,
  `band_down` loose.
- **Trade-to-target by default**; trade-to-edge optional per book.
- **Between-rebalance drift is still accepted**, now consistently: ADR-0007 defines
  `gross_cap` as a constraint on the *requested* rebalance, and the post-band book *is* the
  request.
- **Drift is evaluated every rebalance** (each sleeve-period bar-close), not only when the
  target changes — a frozen target still drifts as prices move, so a held book is re-checked
  each cycle (once/day for a daily book; negligible cost).
- **Shut-venue legs are *masked*, not "below band."** An instrument whose venue is closed
  holds regardless of its drift — it can be far over band and still not trade. Its drifted
  `w_c` is nonetheless part of the realized book the gate evaluates, so the gate must
  *absorb* it: when a masked leg's drift breaches a cap, remediation can only use the
  **open** (tradeable) legs, and Trader **fails closed** (halt + alert) if the open legs
  cannot restore compliance. The "full trade-to-target is compliant by construction"
  terminus holds for band-suppression breaches (under-band *open* legs); it does **not**
  generally hold for a masked-leg breach, since the offending leg cannot be moved —
  fail-closed is the backstop there.
- **Gate the union; trade only the targeted (one rule).** The realized book the gate
  evaluates spans the **union** of Manifest-targeted instruments and all currently-held
  positions (reconciled `Cache`), so the gate always sees true exposure. The **trade set is
  the Manifest-targeted instruments only**: a held instrument with **no** Manifest entry is
  **quarantined** — never auto-traded, always alerted — while recognized sleeves keep
  rebalancing. A quarantined position is still real exposure, so the gate counts it exactly
  like a **masked leg** (remediate via tradeable legs, else fail closed). No opt-in
  trade-out path: retiring a sleeve quarantines its residual for deliberate, operator-driven
  wind-down.
- **NAV staleness is bounded, not eliminated.** `w_c` uses freshest-available marks; on a
  closed-venue day the shared `NAV_base` denominator is stale and a pure FX move can
  spuriously trip an EUR leg. Because the gate is authoritative, a spurious trip costs at
  most a small, often sub-band, trade. Documented, not engineered around for v1.
- **Two buffers compose intentionally** — the strategy's signal buffer
  (`trendStraddleBuffered`, baked in the bundle) and Trader's execution band are different
  layers. A fidelity diagnostic (realized tracking error vs the *unbuffered* target, plus
  turnover) is a test seam to confirm the floor does not go over-sticky.
- **Determinism:** the widen-toward-target order is deterministic, so identical inputs
  always yield the same minimal compliant trade set — auditable, matching RD's ethos.
