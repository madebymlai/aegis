# Components

Components are reviewed Python percent-cell files under `research/components/{indicators,strategies}/`. Forward `run` configs name component IDs directly:

```yaml
strategy:
  id: demo.cross

indicators:
  - id: demo.ma
```

Each entry carries `id` plus optional values-only `params` that fix declared parameters. Per-component `lock_id`/`candidate_id` references are removed (ADR-0006): the only reference surface is the top-level `lock:` block — `lock: <run_id>[:<best|median|worst>]` or `lock: {run_id: ..., candidate_id: <candidate_key>}` — which reproduces one whole prior Candidate. Source selectors and indicator `ids` batching are removed so each component slot is explicit.

YAML never imports Python, names modules, embeds formulas, or points at arbitrary files. Discovery reads only the literal `COMPONENT_MANIFEST`, the required module-level `run` entry point, and the optional module-level `param_space` entry point without executing the component file. Callable code loads only after validation selects a known ID under the fixed component root.

Component manifests declare domain facts only:

- `id` and `version`: the stable selection ID and the component's own version string (both required).
- `input_names`: exact VBT raw-data features the component reads, such as `Close` or `High`.
- Indicator `output_names`: named outputs available to strategies.
- Strategy `consumes_outputs`: named indicator outputs required by the strategy.
- Strategy `output_name`: singular allocation-native output the callable returns; must be one of `{active, scores, ranks, target_weights}` (the registered `STRATEGY_ALLOCATION_OUTPUTS`).
- `param_names`: lockable/optimizable parameter names.
- `defaults`: fixed values for one-candidate execution (keys must be declared in `param_names`).

A component has a searchable parameter space iff it defines `def param_space()`, which returns a mapping of parameter names to `vbt.Param` axes. Indicator callables receive a market-data bundle and request declared raw features through `data.feature("FeatureName")`. Strategy callables receive an inputs object with `inputs.data`, `inputs.indicators`, `inputs.n_symbols`, and `inputs.metadata`; they emit exactly one declared allocation-native output named by the manifest's `output_name`. The optimization path invokes `run` with the batched signature: an indicator's `(data, *, n_candidates, **param_lists)` returns a mapping of output name to candidate-major `(rows, n_candidates * n_symbols)` array, and a strategy's `(inputs, *, n_candidates, **param_lists)` reads candidate-major indicator arrays plus `inputs.n_symbols` and returns one allocation array with the same layout.

Selection convention: non-NaN cells = selected this rebalance row; NaN = excluded. Top-N filtering is owned by the component — the component chooses what to NaN out before returning. The portfolio policy layer owns conversion of the declared shape to a validated allocations frame: it applies the executable mask, gates gross exposure against `portfolio.gross_cap` (with `portfolio.net_cap` and the required `portfolio.direction`), and writes the terminal-liquidation row. The runtime then hands the frame to `vbt.PFO.from_filled_allocations` and `vbt.Portfolio.from_optimizer`. Components do not own portfolios, official metrics, or arbitrary VBT kwargs — those are config-owned and policy-owned.

Legacy `entries`/`exits` and `signal_outputs` declarations are no longer accepted; configs and components that name them fail registry validation. See `docs/vectorbt-scaffold.md` for the portfolio substrate and `docs/brainstorms/2026-05-22-portfolio-target-allocation-pfo-contract-requirements.md` / `docs/plans/2026-05-22-003-feat-portfolio-target-allocation-pfo-contract-plan.md` for the contract history.

Runs with no unlocked axes still execute through the native optimization path as one candidate. Runs with unlocked component params compose all indicator and strategy axes into one VBT-native grid. Completed runs persist Candidates keyed by `(run_id, candidate_key)`; a later config's top-level `lock:` references one by raw `candidate_key` or by representative role (`best`, `median`, `worst`) resolved through that run's candidate rankings. A locked run resolves every component's persisted params into constants before execution; if the locked config also carries `params:`, the lock wins and the overridden values are recorded in Evidence.

Local component files are ignored by git by default except placeholder READMEs. Ignored files are not secret management; do not store credentials in local research code. Public component examples live under `docs/examples/components/`.
