<p align="center">
  <img src="docs/assets/hero.png" alt="Aegis RD" width="830">
</p>

---

Aegis RD is a research operating system for turning market hypotheses into
reproducible evidence.

It gives every idea the same audit trail: source data, indicator construction,
strategy allocations, continuous replay, execution assumptions, costs, metrics, and
promotion evidence. The result is a research process you can rerun, inspect,
reject, or promote without relying on memory, notebooks, or hand-waved
assumptions.

Each valid run writes one local `<run-id>.json` Manifest under its configured
Run root. It records lifecycle status plus config, environment, Git, data, and
optimization Evidence. Failed runs stay inspectable. Optimization replays each
Candidate once, observes fixed chronological blocks without resetting portfolio
state, and publishes representative Candidates to the shared Candidate Store.

## What it does

Each research loop follows one clear contract:

- **Load** one coherent `RunData` value from the shared Nautilus catalog by native
  `InstrumentId`, with explicit Arrays, timeframe, and missing-index policy.
- **Build** indicator outputs with preserved parameter metadata.
- **Generate** strategy signals from reviewed components.
- **Replay** each fixed Candidate continuously after a common derived warmup.
- **Observe** fixed chronological blocks on the unchanged full Portfolio and
  rank Candidates by their mean within-block rank.
- **Simulate** shared-cash portfolios with explicit entry budgets, costs,
  direction, metric scope, and benchmark assumptions. Fill timing is
  configurable (`portfolio.fill_timing`: `next_open`, `next_close`, or
  `same_close`; default `next_close`). Only `next_open` reads the Open array.
- **Rank** complete composed strategy candidates on a leaderboard, not isolated
  indicators.

## Commands

- **`aerd run <config>`** scores a strategy or research sweep over direct
  component references, then persists candidate rows and lock refs. A component's
  `param_space_callable` produces a native VBT parameter grid, while
  `optimization.observation_block_bars` fixes the observational regime length.
  A later run can reuse a result by
  `lock_id`, or by `candidate_id` plus its source `run_id`.
- **`aerd show <topic>`** renders the authoring contracts and catalogs
  (`config-schema`, `components`, `indicator-schema`,
  `strategy-schema`) from the validating models, so the docs never drift from the
  code.
- **`aerd export <config>`** bakes a locked config into an **Execution Bundle**
  wheel for Aegis Trader.

Configs stay inert: YAML selects trusted IDs and parameters only. It cannot
import Python, execute formulas, point at arbitrary notebooks or scripts, or
reference generated Run files as reproducible inputs. Stale `lane`, `train`,
`model`, `label`, `labeler`, or `signals` fields are rejected before a run
Manifest is created.

## Market data contract

Runs call one deep `load_run_data` operation over Aegis Data's Nautilus
`ParquetDataCatalog` port. It resolves tradeables, materialises continuous
futures, loads custom Arrays, applies base-currency conversion, validates the
result, and returns one coherent `RunData` value. A run config declares native
Nautilus `InstrumentId` strings:

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

`RunData` carries the kernel `MarketDataBundle` consumed by Components, the one
`InstrumentResolution` used by simulation and export, currency and distribution
facts, catalog size increments, and structural load Evidence. Successful values
are valid by construction. Environmental failures carry Evidence that is
persisted before the Run is marked failed; there is no configurable degradation
or partially usable success state.

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
