# The rebalancer gates the realized post-band book

Status: accepted (as built; refines the rebalance step of ADR-0001)

Aegis Trader suppresses rebalance churn with a **drift band**: a leg trades only when its
realized weight has drifted from target by more than the band. The band means under-band
legs are *deliberately held* at their current weight `w_c`, so the book Trader actually
requests after band resolution — `{traded legs → resolved target} ∪ {held legs → w_c}` —
is **not** the all-at-target book. Therefore the **rebalancer** gates that **planned
realized post-band book** against the book's gross/net/per-name caps, not the raw target
book. The gate is **authoritative for the rebalance request**; the band is subordinate and
may only suppress churn within the gate's compliance envelope.

This book gate is **not** a second wheel-local **Allocation Policy**. Root ADR-0008
supersedes ADR-0001's 2026-06-14 removal of bundle-side validation: the Execution Bundle
is still a pure transform, but it passes each **sleeve** allocation through the shared
`aegis-runtime` validator using the limits locked with that bundle. The **Book Config**
separately supplies the realized-book limits, and provenance prevents it from running a
sleeve hotter than its locked research evidence. The Rebalancer gates that realized
**book** through the same validator; it owns projection and remediation but no gross/net
inequality, tolerance, or error vocabulary.

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
  intended weights with no single leg tripping. The configured aggregate L1
  target-versus-realized drift threshold forces a full cleanup even when every leg is
  in-band; it only ever *adds* trades and remains subordinate to the gate.
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
- **A min-cost-set solver for the gate override**: rejected for v1. Trader applies a fixed
  sequence of deterministic remediations in weight space before sizing. Any residual
  planned-book breach halts with no orders; no optimizer is required.
- **Trade-to-edge by default** (move a tripped leg only to the band rim): rejected as the
  default. Edge-parking leaves legs at the rim so they re-trip next cycle and raises
  tracking error; trade-to-target is the default, with partial movement carried only when
  the locked per-instrument `DriftBand.destination_fraction` says so.

## Consequences

- **Rebalance pipeline:** `targets → allocate/net by InstrumentId → clamp target gross →
  resolve per-instrument bands → optional aggregate-L1 full cleanup → repair realized
  per-name breaches → clamp projected gross → gate the planned book → size/round → filter
  stale instruments → emit`. A planned-book breach returns no orders and halts the
  strategy.
- **Band lives in weight space**, per instrument, as a pair `(band_up, band_down)`
  defaulting symmetric to the book band; `w_c = position_notional_base / NAV_base`. Trip
  when `(w_c − w_t) > band_up` (trim) or `(w_t − w_c) > band_down` (add). Overrides are
  locked per instrument in the Execution Bundle and scaled by the owning sleeve's applied
  allocation. The tail sets `band_up` tight and `band_down` loose.
- **Trade-to-target by default**; a locked band may select a partial destination.
- **Between-rebalance drift is still accepted**, now consistently: ADR-0007 defines
  `gross_cap` as a constraint on the *requested* rebalance, and the post-band book *is* the
  request.
- **Drift is evaluated every rebalance** (each sleeve-period bar-close), not only when the
  target changes — a frozen target still drifts as prices move, so a held book is re-checked
  each cycle (once/day for a daily book; negligible cost).
- **Shut-venue legs are *masked*, not "below band."** An instrument whose venue is closed
  holds regardless of its drift — it can be far over band and still not trade. Its drifted
  `w_c` is part of the planned post-band projection. Freshness filtering occurs after that
  request is validated and simply suppresses orders for unavailable venues; Trader does
  not run a second exposure policy over sizing or availability outcomes.
- **Gate the realized book; trade only the targeted (one rule).** The realized book the gate
  evaluates spans the Manifest-targeted instruments and their reconciled `Cache` positions, so
  the gate always sees true exposure for the book Trader runs. The **trade set is the
  Manifest-targeted instruments only**.
  - **Amended 2026-06-15 (aegis-rd-bwb.1): quarantine removed.** The original rule also
    folded *held instruments with no Manifest entry* into the gate union — quarantined (never
    auto-traded, always alerted), counted exactly like a masked leg. That is dropped: v1
    assumes the Commingled Book holds only sleeve-covered instruments (see ADR-0001, amended),
    so an unrecognized holding is **out of scope**, not gated. The gate union is therefore over
    Manifest-targeted instruments and their realized positions only; there is no
    quarantine trade-out path. Reinstating quarantine (e.g. for operator-driven sleeve
    retirement) is a future decision.
- **NAV staleness is bounded, not eliminated.** `w_c` uses freshest-available marks; on a
  closed-venue day the shared `NAV_base` denominator is stale and a pure FX move can
  spuriously trip an EUR leg. Because the planned-book gate is authoritative, that can
  trigger a corrective request. Documented, not engineered around for v1.
- **Two buffers compose intentionally** — the strategy's signal buffer
  (`trendStraddleBuffered`, baked in the bundle) and Trader's execution band are different
  layers. A fidelity diagnostic (realized tracking error vs the *unbuffered* target, plus
  turnover) is a test seam to confirm the floor does not go over-sticky.
- **Determinism:** band resolution, full-cleanup selection, per-name repair, gross clamp,
  and planned-book validation are deterministic. No minimal-trade-set claim is made.

## Amendment (2026-07-10): remove the post-sizing defensive gate

The 2026-07-09 implementation added a second exposure gate after sizing, rounding, and
freshness filtering. It required `SizedOrder.projected_delta`, reconstructed a second book
from provider-agnostic quantities, and revalidated a held book even when no sleeve made a
rebalance decision. That layer is removed.

The planned post-band book is the single Trader exposure scope. `size_deltas` again returns
plain `OrderIntent` values, and a no-decision period performs no exposure validation.
Rounding, missing sizing data, and venue availability are execution outcomes rather than a
second book policy. Monitoring an already-held book is a separate risk-monitoring concern.

Strategy still materializes every order before submitting any, so a missing instrument
cannot cause partial submission. The venue-produced `Quantity` is accepted directly; it is
not compared against a separately derived float projection.
