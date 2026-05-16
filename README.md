<p align="center">
  <img src="docs/assets/hero.png" alt="Aegis RD" width="830">
</p>

---

Aegis RD is a research operating system for turning market hypotheses into reproducible evidence.

It gives every idea the same audit trail: source data, feature construction, labels, splits, model behavior, signal rules, execution assumptions, costs, reports, and the final decision about whether the idea survived. The result is a research process that can be rerun, inspected, rejected, or promoted without relying on memory, notebooks, or hand-waved assumptions.

Each valid experiment run writes a local `manifest.json` that records lifecycle status, config evidence, environment and Git evidence, artifact hashes, schema versions, and lineage. Failed runs remain inspectable, and walk-forward validation keeps per-split artifacts separate from aggregate reports.

## What It Does

Aegis RD gives each research loop a clear contract:

- Load market data with explicit provider, symbol, timeframe, timezone, missing-data, and cache behavior.
- Build indicator matrices with preserved parameter metadata.
- Generate labels and model targets without hiding look-ahead, sparse-event, or trend-regime semantics.
- Split data with validation windows that make leakage and embargo assumptions visible.
- Train models with explicit target, class, probability, calibration, and artifact metadata.
- Convert probabilities into signals with documented threshold, timing, cleaning, and conflict rules.
- Simulate portfolios with stated sizing, costs, execution timing, direction, cash, and benchmark assumptions.
- Produce reports that separate per-split evidence, aggregate summaries, survival gates, and uncertainty.

## Why It Exists

Most strategy research fails because the idea is weak, the evidence is incomplete, or the experiment cannot be repeated. Aegis RD is designed to make those failures cheap and obvious.

The goal is not to make every idea look promising. The goal is to make the research process strict enough that weak ideas are rejected early and surviving ideas carry an audit trail.

---

<p align="center">
  <a href="https://vectorbt.pro/">
    <img src="docs/assets/disclaimer.svg" alt="VectorBT PRO license required" width="830">
  </a>
</p>
