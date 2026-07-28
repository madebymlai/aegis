# Run market-data preparation is one constructor: RunArrays carries both views, proven coherent

Status: superseded by [ADR-0028](0028-run-data-is-the-single-research-data-interface.md)

Status: accepted. ADR-0026 extends this lesson one layer up: the run-constant book
facts (fees, bands, futures roots) become one `ResolvedBook` value the same way.

A **Run** sweeps two views of one catalog pull: the signal series that drives **Indicators**, Strategy allocation, and **Splits**, and the P&L series (a future's `pnl_adjustment` mode) that prices the portfolio. Before this work the coordination between them was caller-owned and had already failed:

- **Preparation ran in two parallel, uncoordinated paths.** The orchestrator materialised a signal bundle and a P&L bundle separately, applying base-currency conversion to each on its own, and panelised *every* loaded Array for the P&L series although the portfolio consumes exactly two frames.
- **The view-definition rule was encoded twice.** "The declared `pnl_adjustment` series, else the signal series" lived once in the setup stage and again — dead on the pipeline path — in the runner's `_portfolio_prices`.
- **`SetupResult` had drifted from its ADR-0015 enumeration.** The documented five fields had grown to seven as the P&L frames leaked across the stage seam field-by-field.
- **Nothing proved the two views aligned.** Every downstream consumer slices both views positionally by the splitter's `range_` template, so a calendar or column divergence between them would corrupt window P&L silently.
- **The coordination had already failed in code.** On a dual-series Run, Window Evaluation handed the strategy's `simulate` the P&L-adjusted Close alongside indicator outputs precomputed on the signal Close — a mixed view no reading of the design intends, pinned by no test.

We decided: one deep module in the market-data package owns preparing the Arrays a Run sweeps. `prepare_run_arrays(data_result) -> RunArrays` is its entire public callable surface. The constructor materialises the signal view (a full **Bundle**, since Components may declare any Array) and the P&L view (exactly the two frames the portfolio contract consumes), applies the one base-currency conversion to both, defines the P&L view once, subsumes the usability gate, and proves cross-view alignment unconditionally. A misaligned or unusable pairing cannot exist as a value. As built:

- **`RunArrays` is an eager, inert, frozen value**: `signal` (the FX-converted Bundle), `pnl_close`/`pnl_open` (never `None`), plus the coherence facts `currency_conversion` (the one applied to both views) and `distributions` (cash events from the same loaded data). No methods, no lazy derivation — the dill-shipped sweep closures carry plain frames.
- **One working path, no fallbacks.** On a single-series Run the P&L fields are the signal frames *themselves* (the same objects). Downstream code never branches on the view's presence; both prior fallback encodings are deleted.
- **Alignment is an invariant, checked on every construction.** Each P&L frame must match the signal Close in index (values and order) and column set; divergence raises the typed `RunArrayAlignmentError` carrying the array name, row counts, first/last divergent timestamps, and the column-set difference. Fail-loud, never repair-by-reindex: the two series come from one catalog pull, so a mismatch is a wiring bug.
- **The value travels whole.** `SetupResult` returns to ADR-0015's field-admission discipline with four fields (`store_path`, `optimization_source`, `arrays`, `split_result`); the execution stage reads the value off it; `execute_optimization` and `WindowEvaluator` take `RunArrays` in place of six parameters and four fields respectively (the majority-consumer line of ADR-0015). The separately threaded `currency_conversion`/`distributions` parameters die; fee derivation reads the conversion off the value.
- **The mixed-view hand-off is fixed — a recorded behavior change, not drift.** Window Evaluation drives strategy allocation from the signal view (consistent with the indicators precomputed on it), prices the portfolio exclusively from the P&L view, and passes the full signal calendar as the market index. Single-series Runs are byte-identical (the same frame objects flow everywhere — the refactor oracle; goldens passed unpinned). Dual-series metrics move deliberately; the Window Evaluation regression test with distinguishable frames is the specification. No dual-series goldens existed to re-pin.

## Considered options

- **Place the module in the optimization package**: rejected. Its knowledge — panelisation, FX application, `pnl_adjustment` semantics — is market-data knowledge; optimization is merely its first consumer. The orchestrator now holds no market-data mechanics.
- **Keep the four frames on `SetupResult` and add the value alongside**: rejected (Forward-First). Every field of a typed hand-off is documented contract; carrying both the value and its unpacked copies re-creates the drift ADR-0015 was minted to stop.
- **Repair misalignment by reindexing the P&L view onto the signal calendar**: rejected. Reindexing would silently fabricate or drop P&L bars where the wiring is wrong; the divergence is evidence of an upstream bug and must surface as a typed error (house style: `AdjustmentModeEvidenceError`).
- **A lazy view-deriving value (properties over the loaded result)**: rejected. The sweep dill-ships its inputs to pathos workers; lazy derivation would ship the loader's native containers and re-derive per worker. Eager frames are the serialisation-honest shape (same reasoning as ADR-0020's eager Bundle).
- **Preserve dual-series behavior and fix the routing later**: rejected as a destination — but adopted as a landing step. The plumbing landed byte-identical first (the evaluator temporarily preserved the mixed routing), so any golden movement in the refactor step was a defect by construction; the routing flip then landed with its own regression net.

## Consequences

- **Amends ADR-0015**: `SetupResult`'s field enumeration is four, not five — `close`/`open_` (and the later-drifted `pnl_close`/`pnl_open`) are replaced by the single `arrays` product. The admission rule ("thread identities, recompute values") is unchanged; signal close/open are one lookup off the value at use sites. ADR-0015 carries a back-reference note.
- **Extends ADR-0020, replacing nothing**: the Bundle remains the single Component-facing Array interface; `RunArrays` composes above it. The Result→Bundle builder keeps its facade export and non-pipeline consumers.
- The `aegis_research.data` facade exports `RunArrays`, `prepare_run_arrays`, and `RunArrayAlignmentError`; the facade-surface test was re-pinned once.
- The constructor is the test surface: single-series identity, dual-series FX on both views, FX-equivalence across views, each alignment failure with its typed facts, the usability gate, and the carried coherence facts are all asserted through `prepare_run_arrays` alone. `tests/support` gains `make_run_arrays`.
- Dual-series Runs recorded before this ADR carry metrics computed from the mixed view; comparisons across the boundary must account for the fix. Single-series Runs are unaffected.
- The glossary is untouched: `RunArrays` and `prepare_run_arrays` compose already-minted nouns (Run, Array); "view" is deliberately not minted.
