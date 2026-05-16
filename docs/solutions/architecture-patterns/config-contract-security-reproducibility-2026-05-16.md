---
title: Schema-Versioned Experiment Config Contracts
date: 2026-05-16
category: architecture-patterns
module: research/aegis_research
problem_type: architecture_pattern
component: tooling
severity: medium
applies_when:
  - experiment configs control data loading, model training, reports, or artifacts
  - configs include passthrough kwargs into third-party libraries
  - run artifacts need reproducible and secret-safe provenance
related_components:
  - testing_framework
  - documentation
tags:
  - config-contracts
  - schema-validation
  - secret-redaction
  - reproducibility
  - vectorbt
---

# Schema-Versioned Experiment Config Contracts

## Context

The research scaffold originally loaded experiment YAML directly into frozen dataclasses. That made the YAML file look like the public contract, but most real validation lived downstream in data loading, labeling, portfolio construction, reporting, and VectorBT calls.

This created several risks:

- Unknown YAML fields failed as raw constructor errors instead of path-aware config issues.
- Invalid values could survive until after data downloads, model training, or artifact work.
- VectorBT-specific constraints were implicit and easy to violate.
- Provider passthrough kwargs and secrets were not modeled as a safe boundary.
- Run artifacts did not preserve enough authored/resolved config evidence for reliable reproduction.
- Config schema evolution had no explicit version gate.

Issue #7 resolved this by turning config loading into a schema-versioned, fail-fast contract boundary that produces a resolved envelope before experiment execution.

## Guidance

Treat experiment config loading as a public contract, not a dataclass unpacking convenience. The loader should validate raw authored input, reject malformed or unsafe values, and return a resolved envelope that downstream code can trust.

Use a project-owned validation error with machine-readable paths:

```python
@dataclass(frozen=True)
class ConfigValidationIssue:
    path: str
    message: str


class ConfigValidationError(ValueError):
    def __init__(self, issues: list[ConfigValidationIssue]) -> None:
        self.issues = tuple(issues)
        details = "; ".join(f"{issue.path}: {issue.message}" for issue in self.issues)
        super().__init__(f"Invalid experiment config: {details}")
```

Wrap the resolved dataclass with provenance and artifact-safe views:

```python
@dataclass(frozen=True)
class ResolvedExperimentConfig:
    config: ExperimentConfig
    raw_config_hash: str
    authored_config: dict[str, Any]
    source_path: str | None = None

    def redacted_authored_config(self) -> dict[str, Any]:
        return redact_config(self.authored_config)

    def redacted_resolved_config(self) -> dict[str, Any]:
        return redact_config(to_builtin(asdict(self.config)))

    def manifest(self) -> dict[str, Any]:
        return {
            "schema_version": self.config.schema_version,
            "raw_config_hash": self.raw_config_hash,
            "source_path": self.source_path,
        }
```

Resolve configs before side effects:

```python
def run_experiment(config: ResolvedExperimentConfig | ExperimentConfig | dict[str, Any]) -> dict[str, object]:
    resolved_config = resolve_experiment_config(config)
    config = resolved_config.config

    data = load_market_data(config.data)
    ...
```

Downstream code should accept `ResolvedExperimentConfig` or call `resolve_experiment_config` immediately. Avoid constructing `ExperimentConfig` directly from untrusted YAML.

Reject ambiguous authored input at the loader boundary:

- Duplicate YAML mapping keys fail before validation.
- Unknown fields fail outside explicit passthrough maps.
- Enum-like fields must use canonical values instead of mixed-case aliases.
- Numeric values must be finite and inside configured bounds.
- Report frequencies must be positive `Timedelta`-compatible strings.
- Experiment names must be path-safe filename components.

Keep passthrough boundaries explicit and source-aware. Provider, wrapper, and execution kwargs are valid only where they are actually consumed. Local sources such as `synthetic` and `csv` should reject ignored passthrough maps instead of accepting inert config.

Model secrets as environment references, not inline strings:

```yaml
data:
  source: binance
  symbols: ["BTCUSDT"]
  start: "2020-01-01"
  end: "2020-02-01"
  timeframe: "1D"
  provider_kwargs:
    api_key:
      env: BINANCE_API_KEY
```

Reject inline credentials in passthrough maps both by key name and secret-like value. Also redact resolved secrets from remote provider errors without chaining the original provider exception, because exception causes and tracebacks can leak the original secret-bearing message.

Persist config provenance artifacts on successful runs:

```text
runs/<timestamp>_<name>/
  config.yaml           # redacted resolved config with defaults
  config_authored.yaml  # redacted authored input
  config_manifest.json  # schema version, source path, raw config hash
```

Store `source_path` only when local path disclosure is acceptable. If paths may reveal usernames or private directory structure, persist a relative path or omit it.

Make third-party library assumptions explicit in the config contract. For VectorBT-based experiments, validate `Portfolio.from_signals`-compatible size types, allowed portfolio directions, `labels.kind: trendlb` requiring `labels.mode: binary`, and report frequency assumptions before calling VectorBT.

## Why This Matters

Automation needs config failures before side effects. A bad YAML file should fail before downloading market data, training a model, writing a run directory, or calling VectorBT.

Reproducibility needs stable authored and resolved evidence. For file-based loads, the raw config hash ties a run back to the raw config text as loaded; for in-memory configs, it hashes the normalized YAML representation. The resolved config captures defaults. The authored config preserves user intent.

Security needs secrets outside durable artifacts and tracebacks. Environment references let runs use credentials without storing credentials in YAML, reports, manifests, pushed artifacts, or provider error chains.

Schema versioning keeps config evolution intentional. A version gate prevents old or future config files from being interpreted under the wrong assumptions.

Path-aware validation also helps agents and scripts repair configs. They can patch `data.provider_kwargs.api_key` or `portfolio.size_type` directly instead of reverse-engineering raw constructor failures or downstream VectorBT errors.

## When to Apply

- Config files control data access, model training, backtests, reports, or artifact paths.
- Configs may be run by automation without a human watching every downstream failure.
- Configs include passthrough kwargs into third-party libraries.
- Configs may reference credentials, private URLs, provider tokens, or API keys.
- Runs need to be reproducible, auditable, or comparable over time.
- Third-party library semantics are easy to misuse unless constrained at the scaffold boundary.
- The config schema is expected to evolve.

## Examples

Before, a config could intentionally mix multiple contract failures: unsafe names, invalid shapes, inline secrets, target portfolio sizing, and non-finite report gates.

```yaml
name: ../escape
data:
  source: SYNTHETIC
  symbols: SYN
  provider_kwargs:
    api_key: plain-secret
portfolio:
  size_type: targetpercent
report:
  min_oos_sharpe: .nan
```

After, the authored config is explicit, canonical, and safe to serialize:

```yaml
schema_version: 1
name: baseline_research
output_dir: runs
data:
  source: binance
  symbols: ["BTCUSDT"]
  start: "2020-01-01"
  end: "2020-02-01"
  timeframe: "1D"
  provider_kwargs:
    api_key:
      env: BINANCE_API_KEY
portfolio:
  size_type: valuepercent
  direction: longonly
report:
  freq: "1D"
  year_freq: "252D"
```

Key regression tests for this pattern should assert:

- Unknown fields include the config path in `ConfigValidationError`.
- Duplicate YAML keys fail before dataclass construction.
- Inline passthrough secrets fail, including credential-bearing URLs under benign keys.
- Env secret refs resolve at runtime and are redacted from provider errors, `__cause__`, `__context__`, and formatted tracebacks.
- Non-finite numbers, mixed-case enums, path-unsafe experiment names, and ignored passthrough maps fail at validation.
- Invalid configs do not create run directories, write artifacts, download data, train models, or call VectorBT.

## Related

- GitHub issue #7: Review experiment config schema and validation
- GitHub issue #6: Review VectorBT PRO data provider and OHLCV contracts
- GitHub issue #8: Review experiment orchestration and artifact provenance
- GitHub issue #10: Review report metrics and survival verdict contract
- GitHub issue #13: Review baseline experiment methodology configs
