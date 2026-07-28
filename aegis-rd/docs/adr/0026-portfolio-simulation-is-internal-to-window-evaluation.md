# Portfolio simulation is internal to Window Evaluation; ResolvedBook carries the run-constant book

Status: accepted

Amended 2026-07-22: continuous Candidate replay replaced Window Evaluation. The
portfolio engine and `ResolvedBook` remain one deep internal module, now named
`optimization/portfolio_simulation/`. Historical design language below describes the
module that existed when this decision was accepted.

Amended by [ADR-0028](0028-run-data-is-the-single-research-data-interface.md):
`ResolvedBook.resolve` consumes the one coherent `RunData` value, including its
shared `InstrumentResolution`, conversion, distributions, and size increments.

Window Evaluation is the deep module that turns one Candidate chunk over one split window
into a metric frame, yet before this work its single production call into the portfolio
simulation module crossed an 11-argument seam and its own construction took 9 fields. Five
of those arguments were run-constant book facts (`fees_by_symbol`, `instrument_bands`,
`futures_roots`, the portfolio config, `periods_per_year`) threaded field-by-field from the
pipeline execution stage through `execute_optimization` into the evaluator and onward into
the simulation — the same caller-owned-coordination shape ADR-0024 recorded as an actual
failure mode for `currency_conversion`/`distributions` before RunArrays killed it. The fee
series, band map, and futures roots were resolved in three separate steps and nothing made
an incoherent config/facts pairing unrepresentable. The simulation module was public
contract with exactly one production caller; its public status was carried almost entirely
by tests and diagnostic scripts. And the runner computed the Run's seam cost by reaching
into RunArrays to learn which frame's index is the governing market calendar — a fact the
evaluator already owned.

We decided: Window Evaluation is the one deep module for portfolio simulation, and the
run-constant book facts are one value.

- **`ResolvedBook`** (new glossary term) is a frozen value carrying the declared
  `PortfolioConfig` plus the per-instrument facts resolved from it: the FX-adjusted
  trade-fee series derived at construction, the instrument → DriftBand map (the same one
  the bundle carries), and the continuous-future roots. `ResolvedBook.resolve(config,
  currency_conversion)` owns all three resolutions — fee derivation (absorbing the public
  `fx_adjusted_fees` builder and the execution stage's private helper; a leg is non-base by
  its currency derived from the resolved Instrument, never a configured field), band
  resolution (delegating to the drift-bands authority, never copying it), and futures roots
  off the run's data config. Constructed once in the pipeline execution stage, it travels
  whole through `execute_optimization` into the evaluator. An incoherent config/facts
  pairing cannot exist as a value — the RunArrays argument applied one layer up.
  `periods_per_year` deliberately stays on `ReportConfig`: one home, read by both metrics
  and carry.
- **The absorb is a privacy change, not a textual merge.** Window Evaluation is the
  `optimization/portfolio_simulation/` subpackage; its `__init__` exports exactly
  `WindowEvaluator` and `ResolvedBook`, pinned by a facade-surface test (the market-data
  facade precedent). The simulation keeps its own submodule (`_simulation`) and single
  responsibility — VBT engine wiring, drift-band gating, short financing carry, margin
  interest, distributions, terminal liquidation, Exposure Validation wiring, the NoCash
  tripwire — private beside the staticized callback shim (`_callbacks`, co-located because
  the callback is loaded by filename and content-hashed into the staticization cache key).
- **The internal seam is a declared test convention.** The evaluator's interface emits
  metric frames; the Portfolio object the mechanics tests assert on (margin accrual, carry
  sign, distribution credits, band holds, gap-row holds, the NoCash tripwire, the
  Exposure Validation wiring test root ADR-0008 mandates) never crosses `evaluate`.
  Surfacing book internals through the metric channel would widen the real interface to
  accommodate tests, so those tests cross the internal seam deliberately — the underscore
  visible at every crossing import. `make_single_book_portfolio` is test support and lives in `tests/support`
  beside the factories (it has no production caller); metrics tests that only need a Portfolio use the `make_candidate_portfolio`
  support factory and never name the sim module.
- **Seam cost is a query on the evaluator.** `non_executable_rows(window_index)` answers
  one window's held-row count against the market calendar the evaluator already owns — the
  same calendar the simulation masks gap rows by. The runner contributes only the run's
  window structure (its sum over splits); which calendar governs is no longer its
  knowledge. The next-open executability rule keeps exactly one home, inside `_simulation`.

## Considered options

- **Keep the simulation module public with a narrowed seam**: rejected. The ResolvedBook
  value alone fixes the fact-threading, but the module layout would keep saying the wrong
  thing — a public seam with one production caller, carried by tests. The deletion test
  showed the seam survives only as the mechanics-test surface, which is precisely an
  internal seam.
- **Migrate the mechanics tests to `evaluate()` instead of declaring an internal seam**:
  rejected — observability, not inertia. `evaluate` returns metric frames; asserting
  margin accrual or carry sign through it would require smuggling book internals out as
  metric extractors, turning the registry into a test-observation channel.
- **A standalone public geometry module for the executability rule**: rejected — the
  runner would keep threading the market calendar, the exact fact-in-flight this ADR
  exists to kill.
- **Fold the resolved facts into `PortfolioConfig`**: rejected — mixes user-declared
  config with run-resolved facts, and Candidate Store identity hashes the declared config.
- **A whole-run seam-cost form (evaluator takes the splits)**: rejected — the evaluator is
  deliberately split-blind (the splitter hands it a bare `range_`); teaching it the Split
  shape couples it to run_splits for no gain.

## Consequences

- **Amends root ADR-0008 (Exposure Validation)**: research's one mandated wiring test
  through `simulate_portfolio_batch` now crosses Window Evaluation's internal simulation
  seam; the gate call site is `portfolio_simulation/_simulation.py`. The kernel-side surface
  is untouched. Root ADR-0008 carries an amendment note.
- **Extends ADR-0024's lesson one layer up**: one constructor, coherence by construction,
  threaded parameters die. ADR-0024 carries a back-reference.
- Diagnostic scripts (`floor_gate.py`, `leak_audit.py`) are out of the design by decision:
  operator tooling, not production surface; they import the internal module knowingly.
- Nothing crosses to live: `PortfolioConfig` never leaves RD (the Execution Bundle carries
  only the `LockedExecutionPlan` projection), so the bundle seam is untouched.
- Landed as three independently green steps (mint + narrow, the query, the subpackage
  move), each byte-identical against single-series goldens; Candidate Store identity
  unchanged throughout.
- The glossary gains **ResolvedBook**; it is the run-constant terms a Run's simulation
  trades every Candidate's book under — not the book of positions (that is the simulated
  portfolio).
