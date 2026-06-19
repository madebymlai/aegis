<p align="center">
  <img src="docs/assets/hero.png" alt="Aegis RD" width="830">
</p>

---

Aegis RD is a research operating system for turning market hypotheses into reproducible evidence.

It gives every idea the same audit trail: source data, indicator construction, strategy signals, split scoring, execution assumptions, costs, metrics, and promotion evidence. The result is a research process that can be rerun, inspected, rejected, or promoted without relying on memory, notebooks, or hand-waved assumptions.

Each valid run writes a local `manifest.json` that records lifecycle status, config evidence, environment and Git evidence, artifact hashes, schema versions, and lineage. Failed runs remain inspectable, and split-based validation keeps per-split artifacts separate from aggregate reports. Component-native optimization writes immutable candidate, leaderboard, and lock evidence.

## What It Does

Aegis RD gives each research loop a clear contract:

- Load market data through a native VectorBT `Data` contract with explicit provider, symbol, feature, timeframe, timezone, missing-data, and quality behavior.
- Build indicator outputs with preserved parameter metadata.
- Generate strategy signals from reviewed components.
- Optionally split run scoring into selection and held-out windows with native VBT splitter labels preserved as evidence.
- Simulate shared-cash portfolios with explicit entry budgets, costs, fill timing (`portfolio.fill_timing`: `next_open` / `next_close` / `same_close`, default `next_close` — only `next_open` reads the Open array), direction, metric scope, and benchmark assumptions.
- Produce leaderboards that rank complete composed strategy candidates, not isolated indicators.

## Research Command

- `aerd run <config>` runs strategy/research evidence over direct component strategy/indicator refs. Component `param_space_callable` definitions produce native VBT parameter grids, `optimization.split` names the exact VBT `Splitter` method such as `from_rolling` or `from_purged_kfold`, and completed runs persist candidate rows plus lock refs for later `lock_id` or `candidate_id` plus source `run_id` execution.

Configs stay inert: YAML selects trusted IDs and parameters only. It cannot import Python, execute formulas, point at arbitrary notebooks/scripts, or reference generated run artifacts as reproducible inputs. Stale lane, train, model, label, labeler, or signals fields are rejected before a run directory is created.

## Market Data Contract

Market data is loaded as native VectorBT `Data` for every supported source: `synthetic`, `csv`, `yf`, `binance`, and `ccxt`. Run configs declare `data.arrays` as a list of exact VectorBT feature names, with `OHLCV` expanding to `Open`, `High`, `Low`, `Close`, and `Volume`. Beyond that shortcut, available arrays are source-specific VBT `Data.features`, not a global Aegis list. Downstream stages consume timestamp-by-symbol panels; single-symbol runs are still one-column panels, not squeezed Series.

Each run writes public `data.metadata` with safe provider metadata, requested and observed symbols, canonical feature availability, per-symbol diagnostics, quality state, timezone and index evidence, and omitted metadata fields. Private `data.native` preserves VectorBT-native state after public metadata succeeds and remains secret-scanned and fail-closed.

Strategy runs require Open and Close data so bar-aligned entry/exit signals can be scored with next-open execution. Portfolio configs must declare `portfolio.entry_budget`, which is split across executable same-bar entries in one shared cash pool. Shorting, `portfolio.direction: both`, equal-weight rebalancing, ranked allocation, and target-weight sizing are out of scope for the v1 signal contract.

Non-standard local columns must be normalized before ingestion or inside a source adapter; run configs do not provide feature mapping. Market-data symbols are not normalized: configs must use the provider's exact symbol format, such as `BTC-USD` for Yahoo Finance, `BTCUSDT` for Binance, or `BTC/USDT` for CCXT. This is intentional; hidden alias mapping would make evidence ambiguous.

### Historical Store configs

`data.source: store` reads cache-backed Covered History through `aegis-data` and may gap-fill through exactly one block-level `provider`. Required FX history uses the same provider; there is no `fx_provider`.

Listed instruments keep `ticker` only as the provider locator and must declare the canonical `ListedRef` FIGI explicitly:

```yaml
data:
  source: store
  provider: yfinance
  start: "2024-01-02"
  end: "2024-03-01"
  timeframe: 1D
  arrays: [Close]
  symbols:
    - ticker: SPY
      ccy: USD
      figi: BBG000BDTBL9
```

Futures store configs use block-level Databento request semantics. The symbol authoring surface is the `FuturesRef.root`; RD columns/display names derive from that root, and per-symbol `ticker`, `locator`, `label`, and `dataset` are rejected:

```yaml
data:
  source: store
  provider: databento
  dataset: GLBX.MDP3
  start: "2024-01-02"
  end: "2024-03-01"
  timeframe: 1D
  arrays: [Close]
  symbols:
    - root: ES
      ccy: USD
      roll_rule: calendar
      adjustment: unadjusted
```

## Why It Exists

Most strategy research fails because the idea is weak, the evidence is incomplete, or the experiment cannot be repeated. Aegis RD is designed to make those failures cheap and obvious.

The goal is not to make every idea look promising. The goal is to make the research process strict enough that weak ideas are rejected early and surviving ideas carry an audit trail.

---

<p align="center">
  <a href="https://vectorbt.pro/">
    <img src="docs/assets/disclaimer.svg" alt="VectorBT PRO license required" width="830">
  </a>
</p>
