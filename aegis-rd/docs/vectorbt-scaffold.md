# VectorBT PRO Research Scaffold

Aegis RD turns registered Strategy and Indicator Components into reproducible
Candidate evidence. Each Candidate is simulated once over one continuous Development
Period. Observation Blocks measure the resulting Portfolio without resetting positions,
cash, costs, or drawdown state.

## Flow

```text
Historical Store
-> registered Components
-> materialized Candidate grid
-> common Warmup
-> continuous portfolio replay
-> Observation-Block Metrics and mean ranks
-> best / median / worst Candidate evidence
```

The implementation seams are:

- `optimization/candidate_paths.py`: materializes Candidate parameters and common Warmup.
- `optimization/continuous_replay.py`: builds each Candidate's single causal Portfolio.
- `optimization/portfolio_simulation/`: owns the internal VBT simulation engine and
  `ResolvedBook`.
- `optimization/observation_blocks.py`: applies analysis-only bounds to unchanged
  Portfolios and ranks admissible Candidates.
- `optimization/continuous_evidence.py`: publishes the exact selection inputs and ranks.

## Current Run Config

Run configs are strict schema-versioned YAML. Unknown and retired fields fail; there are
no compatibility shims for Split, Held-out, terminal-liquidation, or optimizer-engine
configuration. Run configs require explicit config paths.

`data.arrays` names the required Historical Store Arrays. YAML never imports Python,
accepts arbitrary notebook paths, last-run refs, or selects executable source code.
Loaded VectorBT data exposes its available Arrays through `Data.features`.
`OHLCV` is defined by the schema's `DATA_ARRAY_SHORTCUTS` catalog.

```yaml
schema_version: 11
name: momentum_run
output_dir: runs

data:
  path: data/catalog
  base_currency: EUR
  instruments: [SYN.XNAS]
  arrays: [OHLCV]
  start: 2020-01-01
  end: 2025-01-01
  timeframe: 1D

portfolio:
  direction: longonly
  fill_timing: next_close

strategy:
  id: example.momentum

indicators:
  - id: example.momentum_score

ranking:
  metric: sharpe_ratio
  min_trades: 5

report:
  freq: 1D
  year_freq: 252D

optimization:
  search: grid
  observation_block_bars: 252
```

Components own fixed parameters and optional `param_space()` callables containing
`vbt.Param` values. Random sampling additionally requires `random_subset` and `seed`.
The Run Config does not accept raw VBT execution or chunking kwargs.
There is one indicator entry per component id. Playbook and source-selector forms are no
longer a supported `aerd run` authoring surface. `candidate_grid` is unknown to the
forward schema.

Component locks use persisted candidate rows from the Candidate Store; they do not copy
parameters from transient output.

## Allocation And Replay Contract

A Strategy emits signed target weights: sign supplies Direction and magnitude supplies
the intended share of capital. The sleeve contract is unit-gross; leverage belongs to the
book allocator, not the Strategy or Run Config.

Production fills are causal:

- `next_close`: a target decided on bar `t` fills at bar `t+1` Close.
- `next_open`: a target decided on bar `t` fills at bar `t+1` Open and requires Open data.

The Portfolio is not liquidated merely because the Development Period or an Observation
Block ends. Positions remain marked and portfolio state remains continuous through the
last available row.

## Observation-Block Ranking

`optimization.observation_block_bars` creates fixed labeled half-open ranges after the
common Warmup. Internally Aegis uses `vbt.Splitter.from_splits` only to apply these bounds;
it never uses a block to construct, truncate, or reset a Portfolio.

The configured Metric is ranked within each block after Invalid and Degenerate Candidates
are excluded. Selection uses mean within-block rank, with materialized Candidate position
as the deterministic equal-score tie-break. Complete-period Metrics are descriptive
Evidence and do not replace the authoritative block-rank matrix.

Return and drawdown extractors read the uninterrupted full-path streams before reducing
an Observation Block. This preserves the real first return and inherited high-water mark;
bounded native VBT calls would rebase those values and change the estimand.

## Evidence

Successful Runs record the materialized Candidate grid, Warmup drivers, continuous replay
contract, Observation Block bounds, Metric extractor contract versions, admissibility
verdicts, exact rank matrix, representative Candidates, config identity, and artifact
hashes. Candidate keys therefore move when an identity-bearing execution or Metric
contract changes.

Run locally with:

```text
aerd run <config>
```

Use `aerd show config-schema` for the generated field-level contract.

| Error category | Exit code |
|---|---:|
| `execution_failure` | 10 |
