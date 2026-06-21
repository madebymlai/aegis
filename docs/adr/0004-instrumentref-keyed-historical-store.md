# Make historical data `InstrumentRef`-keyed, additive, and read-only for Trader

Status: accepted (design; implementation pending). Builds on ADR-0003's
asset-agnostic **InstrumentRef** identity and applies it to the shared
`aegis-data` historical-data layer.

Aegis RD and Aegis Trader need to share historical market data without letting
provider tickers, RD `DataConfig`, or RD's cache-fill behavior cross context
boundaries. We make the `aegis-data` **Historical Store** an OS-global store
keyed by the same **InstrumentRef** identity that crosses the research/live
boundary, while treating provider tickers as provider locators only. Aegis RD
may **Ensure Coverage** by pulling missing gaps into the store; a Trader **Store
Read** is provider-free and fail-closed if the requested bars or FX history are
absent or incomplete.

## Considered options

- **Key the store by provider ticker**: rejected. Tickers are provider-shaped
  locators (`IHYU.L`, Bloomberg symbols, Databento symbols), not durable
  instrument identity. Storing by ticker would make Aegis Trader inherit RD's
  provider choice and would duplicate history when the same instrument is
  sourced through a different provider.
- **Use one shared fetch-on-miss surface for RD and Trader**: rejected. Pulling
  gaps is useful for research, but unsafe for Trader backtests: a missing range
  could silently become a live provider pull and make the result depend on
  today's provider state.
- **Migrate CSV and synthetic sources into the shared store**: rejected for now.
  They remain useful as RD-local fixtures or test conveniences, but the shared
  Historical Store represents reusable market history sourced from remote
  historical providers.
- **Store only continuous adjusted futures history**: rejected. Raw dated futures
  legs are provider source material; continuous histories are derived from them
  by roll rule and adjustment method.

## Consequences

- **Store identity is `InstrumentRef` plus data semantics.** Listed instruments
  store under `ListedRef`; continuous futures store under `FuturesRef`; provider
  locators are adapter inputs only. Listed adjustment policy and futures
  roll/adjustment choices are explicit data semantics, not hidden provider
  defaults.
- **Ensure Coverage and Store Read are separate store semantics.** Aegis RD
  `source: store` uses Ensure Coverage: read existing covered history, pull only
  missing gaps through the configured Gap-Fill Provider, admit them into the
  store, then return the covered range. Store Read never calls providers and
  fails closed unless the requested window has covered history.
- **Ensure Coverage owns the asset-class Pull dispatch.** The
  `(InstrumentRef, Gap-Fill Provider) -> Pull` matrix lives in one `aegis-data`
  module (`aegis_data.coverage`), not in callers. A caller declares the refs, the
  block-level Gap-Fill Provider, and the per-ref Provider Locators; Ensure Coverage
  decides which Pull runs (yfinance for `ListedRef`, Databento for `FuturesRef`) and
  fails closed on an unsupported pair. Aegis RD's `source: store` adapter therefore
  builds the Data Request and gap-fill intent but never branches on ref type or
  provider, and a new Pull provider is a one-module change in `aegis-data`.
- **RD `source: store` opts into the Historical Store path.** Non-store RD
  sources keep RD's existing provider/source resolution. Only the store path
  crosses into Aegis Data, and it does so through a neutral **Data Request**
  rather than RD `DataConfig` or `SymbolSpec`.
- **RD `source: store` declares a provider.** The provider is required so a
  cache miss has deterministic fill behavior, but it is a Gap-Fill Provider only:
  it is declared once for the whole data block, and provider locators are fetch
  inputs that never become store identity.
- **FX History uses the same provider.** Store-mode RD configs do not declare a
  separate `fx_provider`; required FX History is ensured through the same
  block-level Gap-Fill Provider.
- **Databento futures declare a per-symbol dataset.** Amended by
  `aegis-rd/docs/adr/0023-per-symbol-futures-dataset.md`: each futures
  `SymbolSpec` carries the Databento feed/universe that becomes its
  `FuturesRef.dataset`; there is no block-level dataset default.
- **RD `source: store` requires explicit refs.** Every symbol in the store path
  declares its canonical `InstrumentRef` before any gap-fill pull can run.
  Listed store symbols keep `ticker` as their provider locator; there is no
  legacy alias for listed store config.
- **Futures store symbols use root as the RD symbol name.** A futures store
  config does not author a separate ticker, locator, or label for continuous
  futures. The `FuturesRef.root` supplies RD's column/display name; duplicate
  roots in one data block fail closed.
- **Pulls are additive.** Existing covered history is reused; only gaps in the
  requested instrument calendar/timeframe coverage are fetched. Data with gaps or
  missing required arrays is not covered history.
- **Native bars and FX history are stored separately.** Instrument bars stay in
  native quote currency; base-currency conversion remains a runtime/bundle
  concern. FX history is stored separately so it can be reused independently by
  research and Trader backtests.
- **Provider scope is deliberately narrow.** Initial Pull providers are yfinance
  for listed instruments and Databento for futures through NautilusTrader's
  Databento port. The CLI selects providers explicitly (`--yfinance`,
  `--databento`) while preserving the same store semantics.
- **Trader cannot fetch historical data.** Aegis Trader reads the Historical
  Store for the **InstrumentRef** values baked into each **Execution Bundle**;
  it has no provider/source surface in the backtest path.
