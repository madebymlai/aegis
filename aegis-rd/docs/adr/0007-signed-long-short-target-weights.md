# Long/short via signed target weights, sized natively by VBT

Status: accepted (implementation pending)

The v1 portfolio contract was deliberately long-only: `convert_to_allocations` rejected
any `direction` but `longonly`, `_validate_target_weights` rejected negative weights, and
`PORTFOLIO_DIRECTIONS = {"longonly"}`. Long-only cannot act on negative views, profit from
declines, or hold a market-neutral book through a non-uptrend regime, so we admit
**signed** long/short allocations. Long-only becomes a special case, not a separate path.

A **Strategy** now emits a single **signed target-weight** frame — the sign is the
**Direction** (positive = long, negative = short), the magnitude is the intended share of
capital. VBT sizes those weights natively (`from_optimizer` → `from_orders`,
`size_type="targetpercent"`, `direction="both"`) and reads direction from the sign, so the
old **Allocation Policy** normalizer is **deleted**: there is nothing to "normalize" once
the strategy speaks final signed weights. What remains is a ~15-line fail-closed validator
that gates the frame against two run-level caps before simulation — it neither sizes nor
mutates weights.

Exposure is expressed as two knobs replacing the single `target_exposure_cap` (which was
capped at `≤ 1`, itself a long-only assumption): **`gross_cap`** = max `Σ|wᵢ|` per rebalance
(this *is* the VBT `leverage` ceiling; `> 1` means leverage) and **`net_cap`** = max `|Σwᵢ|`
(VBT has no equivalent, so the validator is the only place it is enforced; `net_cap ≈ 0` is
market-neutral). Every mode is a `(gross_cap, net_cap)` setting: long-only `(1, 1)`,
market-neutral `(2, ~0)`, directional L/S `(2, 2)`.

`PortfolioConfig.direction` is kept as a **run-level guard** (it is already wired into
`from_optimizer`): admit `both`/`shortonly` into `PORTFOLIO_DIRECTIONS`, drop the
"v1 is long-only" rejection, and have the validator assert sign-consistency
(`longonly ⇒ w ≥ 0`, `shortonly ⇒ w ≤ 0`, `both ⇒ any`) alongside the gross/net caps.

The architecture stays the documented VBT target-weight route
(`PFO.from_filled_allocations` → `Portfolio.from_optimizer`), which is **multi-day-hold by
construction** (a NaN row holds the prior book, a `0.0` row goes flat). The only genuinely
new simulator kwargs are `leverage=gross_cap` and `leverage_mode="eager"` — required because
a `targetpercent` book with `cash_sharing=True` and gross `> 1` silently fails to fill later
positions otherwise.

## Considered options

- **Policy builds the long/short book from a config flag** (strategy emits an unsigned
  ranking; policy goes long top-N / short bottom-N): rejected. "Which to short / how many"
  is strategy *alpha*; putting it in a generic policy violates the CONTEXT.md definition of
  the policy as a *normalizer* and the SRP boundary that keeps alpha in the Strategy.
- **Keep the policy as an active normalizer/sizer** that rescales strategy weights to a
  budget: rejected. VBT sizes `targetpercent` weights natively; mutating the strategy's
  chosen weights is unnecessary work and overrides strategy intent. The policy collapses to
  validation + pass-through.
- **Declare Direction on the `StrategyManifest`, or infer it purely from the weight signs**:
  rejected in favour of the run-level guard. Pure inference would *delete* an already-wired
  field and lose a real safety net — a sign-bug in a long-only-intended run
  (`[+.5,+.5] → [-.5,+.5]`) keeps gross `= 1`, net `= 0`, slips past both caps, and shorts
  silently; the `longonly ⇒ w ≥ 0` assert catches it. A manifest field duplicates direction
  in two places for metadata that is worthless while strategies are ephemeral.
- **Model short borrow / financing carry now** (negative `cash_earnings` or a
  `post_order_func`): deferred to a future version. VBT is a stateless machine that "doesn't
  track position duration," so carry is real work, not a flag; it is small for liquid ETFs
  and this is a *relative-scoring* system. `fees`/`slippage` already apply to short
  transactions; only the holding-period carry is omitted, recorded as
  `financing_carry: "not_modeled_v1"`. **Superseded by ADR-0008**: short borrow carry is now
  charged via a short-masked per-bar `cash_dividends` array on this same `from_optimizer`
  route, and `financing_carry` is now a structured diagnostics block. Margin interest remains
  deferred there by an architectural boundary (`from_orders` has no position-debt hook).
- **Intraday flat-overnight to avoid carry entirely**: rejected. It is incompatible with the
  target-weight architecture — flattening every night requires `from_signals` event signals,
  which *cannot express target percentages* (maintainer-confirmed), so it would discard the
  `gross_cap`/`net_cap` exposure control this ADR is built on. It is also a different class
  of strategy (day-trading) than the carried, regime-robust market-neutral book that
  motivated the change.

## Consequences

- Deletes `portfolio_policy/policy.py` (`convert_to_allocations`) and its tests. The four
  declared output shapes collapse to **one**: signed `target_weights`. `active`/`scores`/
  `ranks` leave the contract (a strategy wanting a simple ternary book emits `target_weights`
  in `{-c, 0, +c}`).
- Config schema bumps **6 → 7**. `target_exposure_cap` → `gross_cap` + `net_cap`; validation
  becomes `gross_cap > 0` (the `≤ 1` ceiling is gone) and `0 ≤ net_cap ≤ gross_cap`.
  `PORTFOLIO_DIRECTIONS = {"longonly", "shortonly", "both"}`. The default `PortfolioConfig`
  `(gross_cap=1.0, net_cap=1.0, direction="longonly")` reproduces today's long-only behavior
  byte-for-byte.
- `portfolios.py`: passes `leverage=gross_cap`, `leverage_mode="eager"`; adds a
  **requested ≈ realized** allocation assertion (the existing diagnostics already capture both
  frames) to catch the known `cash_sharing` + multi-asset leverage mis-fill, which would
  otherwise corrupt metrics by silently under-trading or drifting net-long. Diagnostics:
  relabel the conflict markers `not_applicable_from_orders` (the real reason is the factory,
  not the direction — the long-only version got this subtly wrong), drop `direction_scope`,
  add `financing_carry: "not_modeled_v1"`.
- The ranking / candidate-validity layer (`ranking.py`) is **unchanged** — it scores metric
  values and counts long+short trades, both direction-agnostic.
- Forward-First: old on-disk configs using `target_exposure_cap` stop validating under v7;
  no compatibility shim. **Lock** is unaffected — it overrides *Component* params, not the
  portfolio block, and reproduction builds a fresh v7 config.
- CONTEXT.md updated: **Strategy** and **Allocation Policy** redefined; **Direction**,
  **Gross Exposure**, **Net Exposure** added.

## Amendment (2026-06-09): gross_cap is enforced at the gate, not by the engine

This ADR set `leverage=gross_cap`, making the cap enforced **twice**: once fail-closed at the
**Allocation Policy** gate (it rejects any requested book with `Σ|wᵢ| > gross_cap` before
simulation) and again inside VBT as a buying-power ceiling. For a compliant book the second
enforcer is pure redundancy; it can only bite in transient states (equity shrank, prices
drifted the realized book above cap, a losing short needs cash to close), and its bite mode is
to **silently under-fill the rebalance** — perversely blocking the very order that returns the
book to compliance. The `requested ≈ realized` assertion this ADR added (and the NoCash guard
that succeeded it in ADR-0011 / aegis-rd-ce4.1) existed *solely* to detect corruption the
second enforcer created.

We therefore make the **gate the sole enforcer** of `gross_cap` and give the engine surplus
buying power: `leverage = k × gross_cap` (k ≥ 2), large enough that no compliant rebalance ever
hits the ceiling — `gross_cap` is unbounded above by config, so the headroom is tied to it
rather than a flat constant, and `np.inf` is avoided (free cash pinned at 0 gives a `0 × ∞`
division-by-zero; the VBT maintainer prescribes a generous *finite* leverage). `leverage_mode`
stays `"eager"`.

This changes no economics for scored evidence: surplus buying power only affects whether a
marginal order *fills*, not the resulting accounting. `from_orders` executes a bar's orders at
one price and marks `pf.value` at bar close, so a within-bar transition spike between two
compliant books never enters the close-to-close value series the **Metrics** are computed on;
and margin interest is unmodeled (ADR-0008), so extra borrowing power carries no cost. In drift
states the simulator may transiently borrow above cap to transition between two compliant
books — strictly more honest than today's alternative of holding a silently under-filled,
already-above-cap book and scoring it. `gross_cap` was always a constraint on the *requested*
rebalance (CONTEXT.md: `Σ|wᵢ|` per rebalance), never on realized exposure, which already drifts
above cap between rebalances regardless.

The downstream guard collapses accordingly: with no zero-buying-power states, every `NoCash`
rejection is a bug, so the tolerance-graded benign-vs-genuine classifier becomes an exact
`if any(NoCash): raise` tripwire (see the ADR-0011 amendment). Tracked as a `discovered-from`
follow-up to aegis-rd-ce4.1.
