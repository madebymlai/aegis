# Hand research candidates to live trading as an Execution Bundle wheel

Status: accepted (as built; amended below)

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

## Amendment (2026-06-19): bundle names are deterministic — fixed 8-char prefix, fail-closed on collision

The content-addressed name above lengthened the 8-char `candidate_key` prefix *git-style on
collision*, so the name a Candidate received depended on what else already sat in the target
directory and on the order bundles were exported. That fights this ADR's own stance that
bundles are **regenerable from the Lock** and gitignored: re-exporting the same Locks in a
different order into a populated `bundles/` could shift a *referenced* wheel name
(`…deadbeef` ↔ `…deadbeef2`), silently breaking the Book Config sleeve that names it.

A content-addressed, regenerable artifact must have a name that is a **pure function of its
content**. The prefix is therefore **fixed at 8 chars** and never lengthens. `aerd export`
**fails closed** if a wheel owned by a *different* `candidate_key` already occupies that
8-char name in the target directory — the same fail-closed posture as instrument resolution,
`lookback()`, and exposure validation — rather than silently mutating the name. (At 8 hex
chars in a single-operator project a genuine collision is ~1e-6 even across hundreds of
bundles; if it ever fires, the operator re-exports to a clean `--out` dir.) The full
`run_id`, `role`, and `candidate_key` stay in the manifest as before, so identity is never
lost — only the *display prefix* is now fixed.

Consequence: a bundle's package name, distribution name, and every module path baked into it
are computable from the Candidate alone, with **no read of the output directory**. This is
what lets `aerd export` split along its axis of change into a deterministic,
directory-agnostic **assembly** core (Lock → typed `DataContract` / `BundleManifest` /
`LockedExecutionPlan` plus component sources) and a thin **wheel materializer** that only
fails closed on a real name collision and serializes the wheel — wheel-format knowledge
(serialization, dist-info, RECORD, zip) localized to one module.

## Amendment (2026-06-19): the wheel is data plus a constant loader; aegis-runtime owns bundle (de)serialization

The original contract built the bundle facade by **generating Python** — `aerd export`
`repr`'d the contract/manifest/plan into the wheel's `__init__.py`, which reconstructed the
typed objects at import (`DataContract(**CONTRACT)` …). That smears the serialization of
`aegis-runtime`'s own types across three places (export's `repr`-codegen, the
`bundle_manifest.json` writer, and the runtime's construction), serializes the same data
twice (Python literals *and* json), and ships *generated logic* inside every wheel.

A bundle's typed payload is `aegis-runtime` vocabulary, so its serialization is
**`aegis-runtime`'s single responsibility**. `aegis-runtime` gains a `bundle_loader`
surface: a dump/load pair for the `DataContract` / `BundleManifest` / `LockedExecutionPlan`
trio and `load_installed_bundle(package) -> ExecutionBundle`. The `DataContract`'s
`instrument_ids` are Nautilus `InstrumentId`s, encoded as their `{symbol}.{venue}` value
strings and **decoded fail-closed** via `InstrumentId.from_str` — consistent with the
codebase's fail-closed, canonical-representation posture — while continuous-future roots
travel as bare root symbols in `futures` (ADR-0007).

A wheel therefore ships **only data plus a constant loader**: the copied component sources,
one `bundle_manifest.json`, and a byte-identical `__init__.py` shim that calls
`load_installed_bundle(__package__)`. No generated code. The wheel becomes fully
inspectable, the json is the single serialization, and the future Trader overlay reads the
same `bundle_loader` to recover a bundle's provenance (the caps it must check, ADR-0001
amendment 2026-06-14).

Consequence for `aerd export`: with serialization owned upstream and names deterministic,
the command splits cleanly into a pure `assemble_bundle(...) -> BundleArtifact` core (the
typed payload plus component source text, no filesystem) and a thin
`write_wheel(artifact, out_dir)` materializer (fail-closed clobber guard, then lay out files
and zip). `BundleArtifact` and the split are implementation detail — not domain glossary;
"Execution Bundle" remains the wheel.

## Amendment (2026-07-03): bundle output returns to the shared Exposure Validation gate

Root ADR-0008 supersedes the **no bundle-side gate** part of the 2026-06-14 amendment.
`compute_weights` remains a pure `data -> signed weights` transform: it does not remediate,
resize, or mutate an allocation. Before returning, however, it passes those weights and the
limits in its `LockedExecutionPlan` to the one kernel-owned Exposure Validation module.
Research uses that same module at Candidate scope, and Trader uses it again on the realized
post-band plan and the executable post-round projection. The three scopes therefore share
one inequality, tolerance, Direction vocabulary, and typed error hierarchy rather than
maintaining nominally identical policies.

The ownership split remains intact. The locked plan carries the sleeve limits validated by
research; Trader's Book Config carries operator-selected realized-book limits; the startup
provenance check prevents those book limits from exceeding the bundle's research evidence.
Only the claim that validation occurs exclusively in the overlay is withdrawn.
