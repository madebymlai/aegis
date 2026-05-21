# Playbooks

Playbooks are repo-controlled Jupytext-compatible Python percent-cell files under `research/playbooks/{indicators,strategies}/`. `aerd run` selects them by stable ID from `PLAYBOOK_MANIFEST`, not by path:

```yaml
strategy:
  source: playbook
  id: ma_strategy_explore

indicators:
  - source: playbook
    ids: [ma_explore]
  - source: component
    ids: all

ranking:
  metric: total_return
  direction: desc
  secondary_metrics: [sharpe_ratio]
```

Each playbook ID represents one research idea/family. Playbooks own sweep grids and candidate axes; components are fixed-param promoted implementations. Run configs select source blocks only: `ids: all` expands to every discovered playbook for that source, and `ids: [...]` selects explicit stable IDs. Playbooks receive runner-provided inputs through the same logical data contract as components, and run configs still declare `data.arrays` for those inputs. Playbooks do not receive run-config params; put VectorBT-native parameter grids in the playbook itself. Run playbooks must use `result_schema: "playbook_sweep_result.v1"` and contract marker `"aegis.playbook_sweep.v1"`. Indicator playbooks emit candidate-indexed output surfaces; strategy playbooks first return a strategy candidate axis, then materialize requested entry/exit signal batches. Candidate metadata must include a `params` mapping containing the swept parameter values needed to reproduce or promote that candidate, for example `{"window": 20, "wtype": "simple", "threshold": 0.01}`. Every non-empty param value must appear in `candidate_id`; use `candidate_id_from_params` to derive IDs from the same params dictionary rather than duplicating values in literals. The playbook registry rejects literal `candidate_id` values when `params` is non-empty, for both indicator and strategy sweep playbooks. Use `params: {}` when the candidate varies by named logic rather than tunable params. Aegis computes portfolio metrics centrally. Playbook-provided metrics are not accepted as leaderboard metrics.

Indicator playbook candidates become rankable only when a strategy playbook consumes their named surfaces and emits executable signals. Each indicator output is a DataFrame with a `candidate_id` level and a `symbol` level. Strategies read source-scoped surfaces from keys like `inputs.indicators["playbook:ma_explore"]["outputs"]["ma"]`. Aegis fails the run if a selected indicator playbook axis is not consumed by the strategy, because an unused indicator should not appear next to ranked strategy metrics.

Leaderboards rank complete composed strategy candidates, not raw indicators. A row is the combination of strategy source/candidate/params, consumed indicator source/candidate/params, portfolio config, and Aegis central VBT metrics:

```json
{
  "composed_candidate_id": "strategy:playbook:ma_cross:fast-0.01+indicators:[playbook:ma_explore:ma-20]",
  "strategy_source": "playbook",
  "strategy_id": "ma_cross",
  "strategy_candidate_id": "fast-0.01",
  "strategy_params": {"threshold": 0.01},
  "indicator_candidates": [
    {
      "source": "playbook",
      "id": "ma_explore",
      "candidate_id": "ma-20",
      "params": {"window": 20},
      "outputs": ["ma"]
    }
  ],
  "strategy_candidate_ref": "strategy:playbook:ma_cross:fast-0.01",
  "indicator_candidate_refs": ["indicator:playbook:ma_explore:ma-20"],
  "chunk_ref": "batch-000000",
  "metric_ref": "strategy:playbook:ma_cross:fast-0.01+indicators:[playbook:ma_explore:ma-20]",
  "metric_source": "central_portfolio",
  "metrics": {
    "total_return": 12.5,
    "sharpe_ratio": 1.4
  }
}
```

Full completed-run evidence is normalized under `strategy_run.json` `catalogs`: source records, indicator candidates, strategy candidates, composed candidates, chunks, and metric payloads are keyed by refs. Leaderboard rows stay compact and readable but include refs so agents can resolve full provenance without reconstructing hidden batch dimensions.

Candidate-grid policy is configured under `candidate_grid`. `candidate_grid.batch_size` bounds how many complete composed strategy candidates Aegis asks a strategy materializer to return per chunk; `candidate_grid.max_candidates` and `candidate_grid.max_estimated_cells` fail closed before scoring when a selected grid is too large:

```yaml
candidate_grid:
  batch_size: 1000
  max_candidates: 100000
  max_estimated_cells: 50000000
```

Completed strategy sweeps require every planned candidate chunk to score and produce the requested ranking metric. Preflight rejections and chunk failures write diagnostic evidence to the manifest, including planned counts, chunk indexes, candidate IDs, stage, error type, and message, but they do not publish completed `strategy_run.json` leaderboard evidence.

Run configs can optionally add top-level split scoring. The selected strategy candidate set is unchanged: fixed component runs are one-candidate sets, and playbook sweeps are composed strategy x indicator candidate sets. Aegis builds VBT split sets from the source index, scores candidates only on each split's selection set, evaluates the selected candidate on the held-out set with fresh portfolio state, and writes one final split-based leaderboard plus `split_metrics` and `split_diagnostics` in `strategy_run.json`.

```yaml
split:
  method: from_rolling
  params:
    length: 252
    offset: 252
    split: 0.8
    set_labels: [selection, held_out]
  max_splits: 100
```

`split.method` must be an exact `vbt.Splitter` constructor method. Use `aerd show splitters from_rolling --json` or another discovered method to inspect signature-derived params and defaults. Compatible methods such as `from_rolling` and `from_purged_kfold` share the same scoring path when VBT returns exactly two non-overlapping sets per split. The first set is used for selection, the second set is used for held-out scoring, and native VBT set labels are preserved in evidence. The final split leaderboard is distinct from the full-period historical leaderboard: it is ranked by held-out split metrics and includes selected split coverage. Do not treat these run split sets as ML train-lane support; label/model training remains legacy and separate from playbook strategy scoring.

Use purposeful percent cells in playbook files: a broad overview cell that states the research idea and source data, imports/definitions as needed, a literal metadata cell, and a `# %% main ...` cell containing the callable. The callable docstring should explain the indicator or strategy approach being explored.

In `PLAYBOOK_MANIFEST`, `family` is the registry bucket and must match the active directory: `indicators` or `strategies`. Indicator playbooks also declare `indicator_family`, which describes the idea being explored, such as `moving_average`; it is not the registry bucket. Labels are not a playbook family; train labels are fixed reviewed label components selected by top-level `labeler: {id: ...}`.

Run artifacts are immutable evidence under the configured run root. Playbook-backed rows remain source-labeled as playbook evidence; manual promotion into `research/components/` is still a reviewed source-code step, not an automatic command that mutates component files. To promote a composed winner, copy the winning indicator source/candidate/params into a fixed indicator component, copy the winning strategy source/candidate/params into a fixed strategy component, and rerun with those component refs to verify the promoted implementation.

Configs cannot provide arbitrary source paths, imports, inline Python, formulas, generated run state, last-run refs, or leaderboard-row refs as reproducible run inputs.

Public playbook examples live under `docs/examples/playbooks/`.
