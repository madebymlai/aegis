# Short financing carry charged via short-masked per-bar cash dividends

Status: accepted

ADR-0007 admitted signed long/short books but deferred the time-based cost of holding a
short, recording `financing_carry: "not_modeled_v1"` in the portfolio diagnostics. A short
seller borrows the security and pays a borrow fee for every period the short is held, partly
offset by a rebate on the short-sale proceeds; that net carry is real and falls hardest on
the heaviest, longest-held shorts. We now charge it, superseding ADR-0007's deferral
paragraph.

We model **short borrow carry only** — `borrow − rebate`, charged on short legs — as a
per-bar `cash_dividends` array on the existing `from_optimizer` → `from_orders` path, the
same factory and the same simulation route ADR-0007 settled on. For each bar and symbol the
array holds `(net_rate / periods_per_year) × close`, **masked to the short legs** (ffilled
signed allocation `< 0`); long legs are `0`. VBT multiplies a per-share `cash_dividends`
value by the live position before adding it to that bar's cash earnings, so the `× position`
semantics give the three properties we need **for free**: the carry rides the drifted short
notional (not a stale entry notional), it is charged only while the short is open, and a
positive per-share value is a **cost on a short / credit on a long** — which is exactly why
the long legs must be masked to zero, or longs would be paid to hold. `periods_per_year`
comes from the same `freq` / `year_freq` the metric layer uses to annualize Sharpe (252 for
the daily defaults), so carry and the performance metrics share one calendar.

The rates are two flat annual scalars on `PortfolioConfig`: `short_borrow_rate` (default
**0.005** = 0.5%/yr) and `short_rebate_rate` (default **0.0**), each validated `≥ 0`. Per
-symbol (hard-to-borrow) and time-varying rates are YAGNI for the liquid-ETF universe this
system targets. The **non-zero borrow default means carry is ON by default**; a researcher
sets `0.0` to opt back into a frictionless book.

The diagnostics `financing_carry` string becomes a structured block
`{mechanism: "cash_dividends_short_borrow_v2", short_borrow_rate, short_rebate_rate,
periods_per_year, margin_interest: "not_modeled", margin_interest_reason: "<reason>"}`, and
the `portfolio_diagnostics` schema bumps `v3 → v4`. The config schema bumps `7 → 8`
(sequenced after ADR-0007's `6 → 7`), Forward-First, no compatibility shim.

## Considered options

- **Model carry now via `cash_dividends`** (this decision): chosen. The maintainer sanctions
  it — *"cash_dividends works if your fees depend on position size"* — and it keeps carry on
  the existing order-based route with no new simulation engine. The `× live position`
  semantics solve drifted notional, only-while-open charging, and the per-leg cost sign
  without bespoke state tracking.
- **Also model margin interest now** (`int_rate × borrowed_cash`): rejected as out of scope,
  by an architectural boundary VBT itself draws. Margin interest needs
  `vbt.pf_nb.get_debt_nb(c)`, which is **unavailable on `from_orders`**; charging it would
  require `from_signals` or `from_order_func` — a different factory than ADR-0007's
  target-weight route. It is recorded as `margin_interest: "not_modeled"` with that reason.
  The consequence is honest and bounded: a **levered net-long** book under-charges carry,
  while the hedged/market-neutral book that motivated ADR-0007 (gross ≈ 2, net ≈ 0, longs
  funded by short proceeds ⇒ debt ≈ 0) has margin interest ≈ 0 and is fully charged by short
  borrow alone.
- **A `post_segment_func`/`from_order_func` callback that charges both costs precisely**:
  rejected for now. It abandons the `targetpercent` target-weight expression ADR-0007 is
  built on and adds a stateful simulation surface for a cost that is small for liquid ETFs in
  a relative-scoring system. The masked-`cash_dividends` path captures the dominant term
  (short borrow) on the route we already run.

## Consequences

- `PortfolioConfig` gains `short_borrow_rate` (0.005) and `short_rebate_rate` (0.0); config
  schema bumps **7 → 8**. The portfolio validator asserts each rate `≥ 0`. The two fields are
  whitelisted automatically because the portfolio block's allowed keys derive from
  `PortfolioConfig.__dataclass_fields__`.
- `portfolios.py` builds the short-masked `cash_dividends` array and passes it to
  `from_optimizer` on both the single-group and per-candidate paths. The effective net rate
  is floored at zero, so a rebate above the borrow does not pay the book to hold a short. The
  array is computed once per simulation from the (ffilled) signed allocations.
- `ReportConfig` gains a `periods_per_year` property (`year_freq / freq`, rounded) so the
  carry annualization and the Sharpe annualization read one calendar. The optimization runner
  threads `report.periods_per_year` into the batch simulation.
- **ADR-0007 guarantee preserved byte-for-byte.** A long-only book has no short legs, so the
  masked `cash_dividends` is all-zero and the simulation is identical whether carry is on at
  the default or explicitly off — verified end-to-end through the CLI.
- Carry only bites where there is cash to charge it against. A fully cash-deployed book (gross
  exactly at the leverage ceiling) leaves no free cash, and VBT suppresses the carry deduction
  rather than driving the balance negative; the realistic market-neutral book (gross below the
  ceiling, long funded by short proceeds) has the free cash and is charged in full.
- Diagnostics: `financing_carry` becomes the structured block above; `portfolio_diagnostics`
  schema bumps **v3 → v4**.
- CONTEXT.md adds the **Financing Carry** term (concept only — the `cash_dividends` mechanism
  is an implementation detail and stays out of the glossary).
