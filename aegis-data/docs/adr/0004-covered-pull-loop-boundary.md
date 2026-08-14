# Covered Pull loop boundary

Status: superseded by GH #96/#97/#101

The historical decision below described Aegis-owned coverage orchestration.
Research Bars now delegate gap calculation, request dispatch, and Catalog
write-back to Nautilus's DataEngine. Catalog absence is an empty answer.

## Context

ADR-0002 made coverage pure and frame-in, while ADR-0003 collapsed parquet I/O,
coverage queries, admission, and writes into `HistoricalStore`. The repository-level
ADR-0004 also says Pulls are additive: existing covered history is reused, and only
missing gaps are sourced from a provider.

The 2026-06-21 architecture review Candidate #2 framed a broader `CoverageFill`
extraction across yfinance and Databento. That framing is now superseded. Row-count
reporting was removed by the store collapse, yfinance native bars and FX History
share a real MERGE-only covered-history loop, and Databento continuous futures has
different rebuild semantics.

## Decision

`aegis_data.pull.pull(key, window, *, store, fetch)` owns the reusable covered Pull
loop for MERGE-only Covered History. The loop asks the store for gaps, narrows the
`CoveredWindow` to each gap, calls a `GapFetch` provider port with a `FetchWindow`,
asks `HistoricalStore.assert_admissible` to validate the returned frame, then writes
with `WriteMode.MERGE`.

`GapFetch` is provider-neutral and returns a store-ready `pd.DataFrame`. Provider
adapters own locator binding and private provider shape:

- `yfinance_native_adapter` binds one `YFinanceLocator` and returns store native-bar
  columns.
- `yfinance_fx_adapter` binds one `YFinanceLocator`, fetches provider `Close`, and
  returns the store FX `rate` column.

The public Pull verbs stay asset-specific. `pull_yfinance_native_bars` and
`pull_yfinance_fx_history` each build the right `CoveredWindow` and delegate to
`pull`. FX Pull remains a standalone public Pull; it is not folded into
`ensure_native_bar_coverage`. Ensure Coverage continues to own native-bar dispatch,
following the repository ADR-0004 line that callers declare refs and providers while
`aegis_data.coverage` chooses the Pull.

## Boundaries

Databento continuous futures is excluded. Its output can be retroactively
back-adjusted when a later leg is discovered, so one uncovered gap invalidates the
derived panel over the requested span. It writes with `WriteMode.REPLACE`, not MERGE.
Putting it behind `pull` would add a mode flag and a one-caller branch that hides the
important rebuild rule.

Raw Futures Leg caching is also excluded. It is provider source material, not
Covered History under an `InstrumentId`; fetch gaps are derived from the Fetch
Ledger introduced by ADR-0005. Its contract is `merge_leg`, `read_leg`, and
`leg_fetch_gaps`, not covered `write`.

## Consequences

- Native yfinance bars and yfinance FX History share one covered gap loop and one
  admission/write boundary.
- Provider-specific fetch details stay in small adapters rather than in the loop.
- Databento's REPLACE rebuild and raw-leg source-material cache remain explicit.
- No new domain term is introduced; this records the existing Pull boundary.
