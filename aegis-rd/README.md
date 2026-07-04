<p align="center">
  <img src="docs/assets/hero.png" alt="Aegis RD" width="830">
</p>

---

Aegis RD is a research operating system for turning market hypotheses into
reproducible evidence.

It gives every idea the same audit trail: source data, indicator construction,
strategy signals, split scoring, execution assumptions, costs, metrics, and
promotion evidence. The result is a research process you can rerun, inspect,
reject, or promote without relying on memory, notebooks, or hand-waved
assumptions.

Each valid run writes a local `manifest.json`. It records lifecycle status,
config evidence, environment and Git evidence, artifact hashes, schema versions,
and lineage. Failed runs stay inspectable. Split-based validation keeps
per-split artifacts separate from aggregate reports, and optimization writes
immutable candidate, leaderboard, and lock evidence.

## What it does

Each research loop follows one clear contract:

- **Load** market data from the shared Nautilus catalog by native `InstrumentId`,
  with explicit arrays, timeframe, timezone, missing-data, and quality behavior.
- **Build** indicator outputs with preserved parameter metadata.
- **Generate** strategy signals from reviewed components.
- **Split** run scoring into selection and held-out windows (optional), with
  native VBT splitter labels preserved as evidence.
- **Simulate** shared-cash portfolios with explicit entry budgets, costs,
  direction, metric scope, and benchmark assumptions. Fill timing is
  configurable (`portfolio.fill_timing`: `next_open`, `next_close`, or
  `same_close`; default `next_close`). Only `next_open` reads the Open array.
- **Rank** complete composed strategy candidates on a leaderboard, not isolated
  indicators.

## Commands

- **`aerd run <config>`** scores a strategy or research sweep over direct
  component references, then persists candidate rows and lock refs. A component's
  `param_space_callable` produces a native VBT parameter grid.
  `optimization.split` names the exact VBT `Splitter` method (for example
  `from_rolling` or `from_purged_kfold`). A later run can reuse a result by
  `lock_id`, or by `candidate_id` plus its source `run_id`.
- **`aerd show <topic>`** renders the authoring contracts and catalogs
  (`config-schema`, `components`, `splitters`, `indicator-schema`,
  `strategy-schema`) from the validating models, so the docs never drift from the
  code.
- **`aerd export <config>`** bakes a locked config into an **Execution Bundle**
  wheel for Aegis Trader.

Configs stay inert: YAML selects trusted IDs and parameters only. It cannot
import Python, execute formulas, point at arbitrary notebooks or scripts, or
reference generated run artifacts as reproducible inputs. Stale `lane`, `train`,
`model`, `label`, `labeler`, or `signals` fields are rejected before a run
directory is created.

## Market data contract

Runs load market data from Aegis Data's Nautilus `ParquetDataCatalog` through the
shared DataProvider port. A run config declares native Nautilus `InstrumentId`
strings:

```yaml
data:
  base_currency: USD
  instruments: [AAPL.NASDAQ, ESZ6.XCME]
  exchange: [EUR/USD.IDEALPRO]
  start: "2024-01-02"
  end: "2024-03-01"
  timeframe: 1D
  arrays: [Close]
```

`instruments` are tradeable columns. `exchange` IDs are data-only: requested from
the same catalog and port, but never exposed as tradeable columns. The forward
data schema has no `source`, `symbols`, or `provider` field.

Each run writes public `data.metadata` with the requested and observed native
IDs, canonical feature availability, per-instrument diagnostics, quality state,
timezone and index evidence, and provider-port provenance. Private `data.native`
preserves VectorBT-native state after public metadata succeeds, and stays
secret-scanned and fail-closed.

## Why it exists

Most strategy research fails for one of three reasons: the idea is weak, the
evidence is incomplete, or the experiment cannot be repeated. Aegis RD makes
those failures cheap and obvious.

The goal is not to make every idea look promising. The goal is to make the
research process strict enough that weak ideas are rejected early, and surviving
ideas carry an audit trail.

---

<p align="center">
  <a href="https://vectorbt.pro/">
    <img src="docs/assets/disclaimer.svg" alt="VectorBT PRO license required" width="830">
  </a>
</p>
