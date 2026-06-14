# Hand research candidates to live trading as an Execution Bundle wheel

Status: accepted (implementation pending; `aegis-runtime` not yet carved out)

Aegis RD must hand a validated strategy to Aegis Trader for live execution. We
resolve the handoff as an **Execution Bundle** — a versioned uv wheel that
`aerd export` builds from a **Lock**, baking the resolved Candidate's parameters
and packaging the strategy plus its wired indicators, executed in Trader through a
new shared **`aegis-runtime`** package — rather than the Nuitka-compiled, self-
contained binary the originating issue (#40) proposed. The wheel owns the full
deterministic transform: Trader supplies native-currency prices and FX series, and
the bundle converts to base currency, runs indicators → strategy → **Allocation
Policy**, and returns a signed target-weight frame, reaching no **Candidate Store**
at runtime.

## Considered options

- **Nuitka-compiled standalone bundle** (the issue's proposal): rejected. Nuitka
  buys three things — a dependency-free binary, source/IP hiding, and speed — and
  inside one monorepo with one owner all three evaporate. VBT PRO (private,
  licensed, Numba-heavy) cannot be compiled into a standalone binary anyway;
  Trader shares the same VBT PRO license, so there is no dependency or licensing
  boundary; there is no third party to hide source from; and a once-per-rebalance,
  numpy-vectorized compute gains ~nothing from compiling the thin Python glue. A
  uv **wheel** delivers the "single drop-in package" ergonomics that actually
  motivated the request, without the build tax (a C toolchain, per-OS/arch/Python
  `.so` artifacts, harder tracebacks).
- **Wheel depends on `aegis-rd` as a library**: rejected. It drags the whole
  research apparatus (optimizer, Candidate Store, preflight, ranking, run
  pipeline) onto the live box, contradicting "executable without the full source
  tree" and permanently coupling research to execution.
- **Vendor a runtime copy into each wheel**: rejected. Duplicates runtime code
  across every bundle with no single place to fix runtime bugs.
- **Resolve a Lock live against a shared Candidate Store** (no bundle): rejected.
  Live Trader would read RD's private research store (chmod 600) at runtime;
  baking params at export time is precisely what decouples execution from it.
- **Export unprovenanced inline-concrete configs**: rejected. `aerd export`
  requires the config to carry a **Lock** so every live book is auditable back to
  scored research **Evidence**; configs with an unresolved `param_space` sweep or
  with hand-pinned params and no candidate lineage are refused.

## Consequences

- **New shared package `aegis-runtime`.** The locked execution path — component
  loading, the `force_locked` / `n_candidates=1` orchestration, currency
  conversion (`currency.py`), the Allocation Policy gate, and the
  `MarketDataBundle` types — is extracted from `aegis-rd` so research and every
  Execution Bundle share one runtime. It lives as a **top-level package**
  (`aegis-runtime/`, sibling of `aegis-rd`/`aegis-trader`) with its own
  distribution; `aegis-rd` and every Execution Bundle *depend on* it (a path /
  workspace source) and it is never shipped inside the `aegis-rd` distribution —
  doing so would reintroduce the rejected "wheel depends on aegis-rd" coupling.
  This is real work beyond adding an export command — issue #40 covers both,
  sequenced internally as: carve out `aegis-runtime` first, then build `aerd
  export` on top of it.
- **No new single-candidate execution signature.** The existing batched
  `run(inputs, *, n_candidates, **param_lists)` at `n_candidates=1` with locked
  params is the live path; baking the Lock drops `param_space` entirely.
- **Trader stays dumb about currency.** It hands raw native-currency prices and FX
  series; the wheel assembles/aligns FX and converts with the same `currency.py`,
  so live conversion is byte-identical to research.
- **VBT PRO remains a runtime dependency of Aegis Trader** (kept deliberately).
- **Bundle identity is content-addressed.** A wheel is named
  `aegis-exec-{strategy_id}-{candidate_key[:8]}` (e.g.
  `aegis-exec-demeter-carry-a1b2c3d4`), versioned at the strategy component's
  semver, with the full `run_id`, `role`, and `candidate_key` recorded in the
  bundle manifest. The 8-char hash prefix lengthens git-style on collision.
  Because the candidate hash is in the package *name*, two candidates of the same
  strategy are distinct packages that install side by side. Each wheel registers
  an `aegis.execution_bundles` entry point (`{strategy_id}@{run_id}[:role]` →
  the bundle facade) so Trader discovers installed bundles instead of importing
  them by name.
- **Bundle entrypoint and data contract.** Each wheel exposes an
  `ExecutionBundle` with `compute_weights(prices: MarketDataBundle, *, fx_series)
  -> signed target-weight frame` and a `DataContract` advertising `symbols`,
  `required_arrays`, `base_currency`, `required_fx_currencies`, `timeframe`, and
  `lookback_bars`. Trader hands raw native-currency prices plus FX rate series;
  the wheel aligns the FX (`assemble_fx_rates`) and converts. `compute_weights`
  fails closed on a symbol/array/FX-currency mismatch, a window shorter than
  `lookback_bars`, a non-finite latest row, or an Allocation Policy breach.
- **Components declare lookback.** A new pure `lookback(**params) -> int`
  component entrypoint (alongside `run`/`param_space`) returns the warmup bars a
  component consumes; the bundle bakes `lookback_bars = max` across the strategy
  and its wired indicators. `aerd export` rejects, fail-closed, any bundled
  component that does not declare it.
- **Exported bundles land in `bundles/` at the monorepo root**, overridable with
  `aerd export --out <dir>`. Neutral ground owned by neither context — not buried
  in `aegis-rd`, and *not* inside the `aegis-runtime` library that the wheels
  depend on (a dependency must not contain its dependents). `aerd export` prints
  the written path and the `uv add` line. Bundles are regenerable from the Lock,
  so they are gitignored by default (commit them only if a tracked record of what
  has shipped to live is wanted).

## Amendment (2026-06-14): the bundle is a pure transform; exposure caps move to Aegis Trader

The bundle no longer applies the **Allocation Policy**. The contract above baked the gate
into `compute_weights` to make each wheel a *distributable safe atom* — intrinsically
compliant regardless of caller (the "Aegis Trader operator installs a bundle" stories of
`aegis-rd-qcj`). Aegis is a single-operator personal project with exactly one bundle
consumer — Aegis Trader's overlay, which always validates — and no distribution. With no
untrusted caller, the self-gate guards a consumer that does not exist.

`compute_weights` therefore becomes a **pure `data → signed weights` transform**, keeping
only its I/O-contract guards (fail closed on symbol/array/FX-currency mismatch, a window
shorter than `lookback_bars`, and a non-finite latest row). **Exposure caps (per-sleeve and
book) move to the Aegis Trader Book Config** (operator config), and the single shared
`aegis-runtime` Allocation Policy validator is invoked by the overlay — at **book scope**
(the mandatory realized-book compliance invariant; Aegis Trader ADR-0002) and at **sleeve
scope** (fail-closed attribution). No cap field is added to the `DataContract`; the only
change to this contract is the bundle dropping the gate.

The wheel still records the candidate's research-validated caps in its `BundleManifest` as
**provenance** (they are part of the baked candidate config). The overlay asserts each
Manifest cap **≤** the sleeve's research-validated cap and refuses to run a sleeve *hotter*
than it was scored — a "don't trade beyond your evidence" guard, enforced in Trader and
sourced from provenance, not baked into the wheel as enforcement.

`aegis-runtime` still contains the Allocation Policy validator (shared by research and the
overlay); only its invocation inside `compute_weights` is removed. The book-scope gate of
ADR-0002 is the **rebalancer's** realized-book invariant, distinct from this per-sleeve
validator though it reuses the same function.
