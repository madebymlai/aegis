# The catalog lazy fill is unconditional and shared by research and live

Status: superseded in part by GH #96/#101

Research and live still share provider-backed warming, but research now drives
Nautilus's DataEngine directly. Absence no longer raises a Coverage Gap.

## Context

The r8b epic exists to stop research and live from sourcing market data through
different code. Today they still do: Aegis RD reads the catalog through
`CatalogBackedDataPort` with `provider=None` hard-wired (`catalog.py`), so a
`Coverage Gap` can only fail loud — research never fills. The live node, meanwhile,
warms its Nautilus Cache through `Strategy.request_bars`. Different fill behaviour
per context is the exact divergence the epic removes.

The tempting safety valve is to **gate** the fill per context — wire the IBKR
provider only when credentials or an env flag are present — so a wide research
"reader" sweep can never become a writer swarm. But that re-creates divergence:
**live can never gate the fill.** A gated miss in live is a cold-start lookback
gap — the precise failure the boot-time warmup exists to close. If RD gates and
live does not, the two paths drift apart again.

## Decision

The DataProvider-port lazy fill is **unconditional and ungated** for every reader
of the catalog. RD follows live: a miss fills and persists additively, never
silently truncates. What is **single-sourced** is the catalog, the `EXTERNAL`
BarType identity (ADR-0007), the additive-monotonic merge, and the IBKR adapter
family — **not** a single function. The *invocation* differs by necessity:

- **RD** (no node) fills synchronously through `CatalogBackedDataPort` wrapping the
  standalone `HistoricInteractiveBrokersClient` (`asyncio.run` hidden inside the
  port), persisting via `catalog.write_data`.
- **The live node** warms through Nautilus's *native* catalog seam —
  `TradingNodeConfig(catalogs=[DataCatalogConfig(path=catalog_root)])` plus a single
  startup `request_bars(start=lookback, end=now, update_catalog=True)` per
  instrument: served from the catalog where covered, topped up from IBKR for the
  tail, and persisted. The startup `request_bars` itself **stays** — a configured
  catalog is not auto-loaded into the cache, and `subscribe_bars` is real-time only,
  so history must be requested explicitly (Nautilus's request-then-subscribe
  workflow). What changes is that with `catalogs=` wired the *same* call now serves
  history from the catalog instead of pulling the whole window from IBKR (KISS/DIP).
  **Confirmed by prototype** — the
  DataEngine splits one call: `get_missing_intervals_for_request` yields the gap, the
  catalog serves the covered span, the client fetches only the missing tail as grouped
  subrequests, and `update_catalog=True` persists that tail (the catalog-served
  subresponse is forced no-write, so no double-write). Source: `nautilus_trader`
  v1.228.0 `data/engine.pyx::_handle_date_range_request`.

Both use Nautilus's official IBKR adapter and write byte-identical bars, so the two
contexts cannot diverge on *data* even though they invoke differently. Identity
resolution is the adapter's (`SymbologyMethod.IB_SIMPLIFIED` + `load_ids` of native
InstrumentIds); no bespoke resolver (root ADR-0005).

- `warmup_cache_on_start` defaults to **`True`** for the same reason: "no
  cold-start gap" is a *property* of the live node, not an opt-in. The backtest —
  which loads bars directly and has no cold start — is the one caller that
  explicitly opts out.
- The writer-swarm concern that motivated gating is handled **structurally**, not
  by a knob. IBKR permits a single session, so fills are inherently serialized; the
  `Warm Then Sweep` rule (one serial run/warming pass populates first, then
  concurrent readers run over the immutable Catalog) means the wide sweep never
  misses, so it never writes. No write-coordination or locking infra (YAGNI).

## Considered and rejected

- **Gate the fill by credential presence or an env flag.** Rejected: it
  re-introduces the RD↔live divergence the epic removes, and it makes the live
  cold-start gap reachable whenever the gate is off. Its only real benefit —
  preventing concurrent writers — is already given for free by the single IBKR
  session plus `Warm Then Sweep`.

## Consequences

- A *research* backtest may open an IBKR connection and write to the catalog on a
  miss. Surprising at first glance, deliberate here: research "behaves like live."
- The concurrent RD sweep is read-only in practice only because it runs warm;
  safety rests on `Warm Then Sweep` + the single IBKR session, not on locks. A
  future reader must not add a "reader mode" that disables the fill — that is the
  divergence this ADR forbids.
