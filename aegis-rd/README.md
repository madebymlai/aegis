<p align="center">
  <img src="docs/assets/hero.png" alt="Aegis RD" width="830">
</p>

---

Aegis RD is a research operating system for turning market hypotheses into reproducible evidence.

It gives every idea the same audit trail: source data, indicator construction, strategy signals, split scoring, execution assumptions, costs, metrics, and promotion evidence. The result is a research process that can be rerun, inspected, rejected, or promoted without relying on memory, notebooks, or hand-waved assumptions.

Each valid run writes a local `manifest.json` that records lifecycle status, config evidence, environment and Git evidence, artifact hashes, schema versions, and lineage. Failed runs remain inspectable, and split-based validation keeps per-split artifacts separate from aggregate reports. Component-native optimization writes immutable candidate, leaderboard, and lock evidence.

## What It Does

Aegis RD gives each research loop a clear contract:

- Load market data from the shared Nautilus catalog by native `InstrumentId`, with explicit arrays, timeframe, timezone, missing-data, and quality behavior.
- Build indicator outputs with preserved parameter metadata.
- Generate strategy signals from reviewed components.
- Optionally split run scoring into selection and held-out windows with native VBT splitter labels preserved as evidence.
- Simulate shared-cash portfolios with explicit entry budgets, costs, fill timing (`portfolio.fill_timing`: `next_open` / `next_close` / `same_close`, default `next_close` — only `next_open` reads the Open array), direction, metric scope, and benchmark assumptions.
- Produce leaderboards that rank complete composed strategy candidates, not isolated indicators.

## Research Command

- `aerd run <config>` runs strategy/research evidence over direct component strategy/indicator refs. Component `param_space_callable` definitions produce native VBT parameter grids, `optimization.split` names the exact VBT `Splitter` method such as `from_rolling` or `from_purged_kfold`, and completed runs persist candidate rows plus lock refs for later `lock_id` or `candidate_id` plus source `run_id` execution.

Configs stay inert: YAML selects trusted IDs and parameters only. It cannot import Python, execute formulas, point at arbitrary notebooks/scripts, or reference generated run artifacts as reproducible inputs. Stale lane, train, model, label, labeler, or signals fields are rejected before a run directory is created.

## Market Data Contract

Market data is loaded from Aegis Data's Nautilus `ParquetDataCatalog` through the shared DataProvider port. Run configs declare native Nautilus `InstrumentId` strings:

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

`instruments` are tradeable columns. `exchange` IDs are data-only, requested from the same catalog/port but never exposed as tradeable columns. There is no `source`, `symbols`, or `provider` field in the forward data schema.

Each run writes public `data.metadata` with requested and observed native IDs, canonical feature availability, per-instrument diagnostics, quality state, timezone and index evidence, and provider-port provenance. Private `data.native` preserves VectorBT-native state after public metadata succeeds and remains secret-scanned and fail-closed.

## Why It Exists

Most strategy research fails because the idea is weak, the evidence is incomplete, or the experiment cannot be repeated. Aegis RD is designed to make those failures cheap and obvious.

The goal is not to make every idea look promising. The goal is to make the research process strict enough that weak ideas are rejected early and surviving ideas carry an audit trail.

---

<p align="center">
  <a href="https://vectorbt.pro/">
    <img src="docs/assets/disclaimer.svg" alt="VectorBT PRO license required" width="830">
  </a>
</p>
