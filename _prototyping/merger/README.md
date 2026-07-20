# Cash-merger convergence prototype

This directory contains all cash-merger experimental work. It is deliberately outside
`aegis-rd`, `aegis-trader`, and their normal test suites.

`legacy_aegis_rd/` retains the earlier retired Aegis RD component/config attempt and its
generated runs; its old checks are under `_prototyping/tests/legacy_aegis_rd` and are evidence,
not an active suite. `shadow/` is the forward evidence collector for the surviving market-implied
`q70` control. The control is **not promoted alpha**: the gate remains closed until the prospective ledger has
at least 100 resolved events and 10 adverse resolutions.

There is one active strategy implementation: `CashMergerSelector.select(...)`. Prospective
collection and historical replay call that same interface. EdgarTools supplies SEC filings in
both modes; Aegis's standard catalog-backed IBKR path supplies market data. The prototype has no
secondary market-data provider and no provider-specific strategy logic.

## Prospective run

Copy `shadow.example.yaml` to a local config, add only IBKR-qualified InstrumentIds, and run
from the repository root:

```bash
aegis-rd/.venv/bin/python -m _prototyping.merger.run_shadow \
  --config /path/to/local-shadow.yaml \
  --bootstrap-start 2025-07-01
```

Each run:

1. replays SEC filings from `--bootstrap-start` when its state is empty, then resumes after
   the latest covered filing date (the current partial filing day is collected by the next run);
2. resolves every configured InstrumentId to its SEC CIK through EdgarTools;
3. fetches and locally caches company filings and complete submissions through EdgarTools;
4. rejects filings outside the configured CIK universe before creating an event;
5. appends content-addressed event observations without rewriting history;
6. fetches the latest public FRED `DTB3` cash rate with an immutable offline cache;
7. prices active configured targets through Aegis's catalog-backed IBKR path;
8. computes the market-implied completion baseline once, passes immutable deal cases through the
   selected completion engine, and records market and model probabilities side by side;
9. applies monthly whole-share sizing outside the engine, models IBKR Pro Tiered U.S.
   equity commissions, reserves IBKR's 3-bps AutoFX cost on deployed USD notional, and
   reports terminal exits; and
10. writes immutable evidence under the runtime state directory.

The configured InstrumentIds are authoritative. A filing cannot create a tradeable instrument,
and the prototype does not guess a venue, submit an order, or alter a production schema. EdgarTools
owns SEC access, ticker/CIK reference data, fair-access throttling, and its standard `~/.edgar`
cache; the prototype owns merger extraction, lifecycle state, and evidence.

`CashMergerSelector.select(...)` is the public selection interface. A completion engine implements
one `forecast(cases)` method and cannot replace the selector's market-implied probability, hard
tradability filters, break-loss caps, whole-share sizing, or execution-cost accounting. The default
engine is the no-alpha `market-implied-q70` benchmark. Any challenger must carry an immutable model
artifact identity and training cutoff for the forecast batch, plus a causal feature timestamp for
every deal. Injected challengers remain shadow-only while the market baseline controls positions;
qualified-challenger authority must be granted explicitly after out-of-sample evidence exists.

## Historical replay

Replay the configured cohort one calendar month at a time with the same event parser, selector,
cost model and whole-share sizing used by the prospective runner:

```bash
aegis-rd/.venv/bin/python -m _prototyping.merger.run_history \
  --config /path/to/local-shadow.yaml \
  --start 2025-07-01 \
  --end 2026-07-01 \
  --source-state-dir ~/.cache/aegis/cash-merger-shadow
```

The replay reconstructs filings through EdgarTools using SEC acceptance timestamps and loads
every mark through the Aegis catalog. Missing catalog intervals are lazily requested from IBKR.
Bars already stored in the catalog remain replayable after a target delists.
`--source-state-dir` copies only immutable event observations into the dedicated replay ledger;
this preserves the event-time CIK and listing identity without asking a current ticker map to
resolve a delisted target. Replay decisions and prospective evidence remain isolated.

IBKR does not provide historical data for securities which are no longer trading. Consequently,
this runner deliberately reports unavailable market history for an uncached delisted target. It
does not omit the event, guess a price, or fall back to another provider. The replay becomes
survivorship-free prospectively as Aegis persists each observed target's bars before delisting;
it is not a complete pre-collection historical alpha test.

The execution estimate assumes IBKR Pro Tiered pricing for U.S. equities: `$0.0035` per share,
with a `$0.35` order minimum and a `1%` trade-value cap, plus a `0.03%` AutoFX adjustment on USD
notional funded from EUR. The FX estimate is a portfolio-formation reserve, not a per-name charge;
USD sale proceeds are intended to remain available for later U.S. trades. Exchange, clearing and
regulatory pass-through fees and eventual USD-to-EUR repatriation are not yet included.

## Behavior checks

The checks intentionally remain outside normal Pytest discovery:

```bash
aegis-rd/.venv/bin/python -m pytest _prototyping/tests/shadow -q
```
