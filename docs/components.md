# Components

Components are reviewed Python percent-cell files under `research/components/{indicators,strategies}/`. Forward `run` configs name component IDs directly:

```yaml
strategy:
  id: demo.cross

indicators:
  - id: demo.ma
```

Each entry may carry `params`, `lock_id`, or `candidate_id`. `candidate_id` pins must also include the source `run_id`; `lock_id` and `candidate_id` are mutually exclusive. Source selectors and indicator `ids` batching are removed so each lockable component slot is explicit.

YAML never imports Python, names modules, embeds formulas, or points at arbitrary files. Discovery reads only literal `COMPONENT_MANIFEST` and `COMPONENT_CALLABLE` metadata without executing the component file. Callable code loads only after validation selects a known ID under the fixed component root.

Component manifests declare:

- `input_names`: exact VBT raw-data features the component reads, such as `Close` or `High`.
- Indicator `output_names`: named outputs available to strategies.
- Strategy `consumes_outputs`: named indicator outputs required by the strategy.
- Strategy `output_name`: singular allocation-native output the callable returns; must be one of `{active, scores, ranks, target_weights}` (the registered `STRATEGY_ALLOCATION_OUTPUTS`).
- `param_names`: lockable/optimizable parameter names.
- `defaults`: fixed values for one-candidate execution.
- `param_space_callable`: optional callable returning a mapping of parameter names to `vbt.Param` axes.

Indicator callables receive a market-data bundle and request declared raw features through `data.feature("FeatureName")`. Strategy callables receive an inputs object with `inputs.data`, `inputs.indicators`, and `inputs.metadata`; they emit exactly one declared allocation-native frame named by the manifest's `output_name`.

Selection convention: non-NaN cells = selected this rebalance row; NaN = excluded. Top-N filtering is owned by the component — the component chooses what to NaN out before returning. The portfolio policy layer owns conversion of the declared shape to a validated allocations frame: it applies the executable mask, normalizes against `portfolio.target_exposure_cap`, and writes the terminal-liquidation row. The runtime then hands the frame to `vbt.PFO.from_filled_allocations` and `vbt.Portfolio.from_optimizer`. Components do not own portfolios, official metrics, or arbitrary VBT kwargs — those are config-owned and policy-owned.

Legacy `entries`/`exits` and `signal_outputs` declarations are no longer accepted; configs and components that name them fail registry validation. See `docs/vectorbt-scaffold.md` for the portfolio substrate and `docs/brainstorms/2026-05-22-portfolio-target-allocation-pfo-contract-requirements.md` / `docs/plans/2026-05-22-003-feat-portfolio-target-allocation-pfo-contract-plan.md` for the contract history.

Runs with no unlocked axes still execute through the native optimization path as one candidate. Runs with unlocked component params compose all indicator and strategy axes into one VBT-native grid. Completed runs write component promotion records under `strategy_run.json` `promotions`; use a promotion record `token` as a later component `lock_id`. Use a leaderboard row `candidate_key` as `candidate_id` plus that leaderboard's `run_id` to pin a specific non-best candidate row. Promotion locks resolve persisted component params into constants before execution.

Local component files are ignored by git by default except placeholder READMEs. Ignored files are not secret management; do not store credentials in local research code. Public component examples live under `docs/examples/components/`.
