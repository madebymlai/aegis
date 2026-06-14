# Build the run Splitter once; the runner consumes it from RunSplitsResult

Status: accepted

The `vbt.Splitter` for a **Run** is built twice from one **Run Config**. `build_run_splits_result`
(`run_splits.py`) builds it, stores it on `RunSplitsResult.native_object`, and nobody reads it; the
optimization runner then rebuilds its own via `_build_splitter` (`runner.py`). The two constructions
disagree on their *input*: run_splits calls `method(index, **params)` with no `set_labels`, keeping
vbt's native set names (`set_0`/`set_1`, or `train`/`test`) and assigning the **Selection** /
**Held-out** roles **positionally** (set 0 = selection); the runner passes
`set_labels=["selection","held_out"]` and addresses sets **by role label** (`set_="selection"`). So
the Selection/Held-out role assignment lives in two implementations — positional and label — over one
config, with nothing enforcing they agree. They happen to agree today (both assume position 0 =
selection), but the agreement is unenforced: reorder one and the runner's selection sweep would score
the other set's rows with no signal.

The Splitter is now built **once**, in run_splits, with `set_labels=["selection","held_out"]`, and
roles are assigned **by name** (`set_indices["selection"]`) rather than positionally — so
positional/label drift is unrepresentable. `RunSplitsResult` exposes the built object as a required,
typed `splitter: vbt.Splitter` (replacing the untyped, unread `native_object`). The runner takes the
`RunSplitsResult` whole (`execute_optimization(..., split_result=...)`), reads `.splitter`, and its
`_build_splitter`, `SET_LABELS`, and second `optimization.split` read are deleted; the role-label
constants live solely in run_splits, which the runner imports. Imposing `selection`/`held_out` over
vbt's native labels is the deliberate act of writing domain language onto the framework's defaults:
`train`/`test` is banned by the **Split** glossary entry and actively misframes the set — nothing is
*trained* here; the Selection set feeds parameter scoring and **global ranking** (ADR-0002). The
preflight gate, which only ever read `.splits`, narrows to `build_preflight(splits=...)` so it no
longer depends on `RunSplitsResult` — letting `splitter` be honestly required.

The Splitter object never enters provenance or canonical hashing: only `.metadata`/`.splits` reach
**Evidence**, and `capture.py`'s `"splitter"` is a vbt *settings-section* name, not the object. So
the byte-identical `manifest.json` and split metadata are the regression oracle for the whole change.

## Considered options

- **Expose `native_object` as-is** (smallest diff): rejected — the stored object was built *without*
  `set_labels`, so its sets are named `set_0`/`train`, and `runner.apply(set_="selection")` would not
  resolve. It is not even a drop-in; the divergent input (role labels) has to be fixed at the single
  construction regardless.
- **Hide vbt behind a role-addressable interface** (a Protocol or `apply(close)` wrapper): rejected —
  the runner needs `vbt.Splitter.apply`'s full surface (the `range_` template, `mono_n_chunks`,
  `execute_kwargs`, the `parameterized` callable, `merge_func`, arbitrary params). A wrapper would
  re-forward all of it: a leaky adapter for a single implementation. No non-vbt splitter is
  envisioned, so the seam is justified by two *consumers* needing one consistent Split, not by
  adapter variance. We keep using `vbt.Splitter` concretely at the seam.
- **Rebuild in the runner from the role-labeled slices** (`vbt.Splitter.from_splits`): rejected —
  keeps two Splitter objects and adds a vbt-reconstruction question (does `from_splits` preserve the
  `range_` template the runner's two-phase `apply` relies on?) for no isolation we are not already
  giving up by carrying the object through the result.
- **Preserve the method-native set names in run_splits**: rejected — no consumer reads them (they are
  absent from Evidence; `_split_membership_metadata` and `_set_summary` already key by role), and
  preserving `train`/`test` would carry banned, misleading vocabulary (CONTEXT.md **Split**;
  ADR-0002) into the model.
- **Keep `splitter` optional on `RunSplitsResult`**: rejected — it is always present in production, so
  optionality only buys a `None` branch the runner can never legitimately reach. Making it required
  and narrowing preflight to the `.splits` it actually consumes is the honest model (define errors
  out of existence; ISP).

## Consequences

- Selection/Held-out role assignment exists in exactly one place — run_splits, name-based — and the
  runner derives nothing about roles. A seam test passes a recording splitter and asserts `.apply` is
  invoked `set_="selection"` then `set_="held_out"`, locking the single role home.
- `RunSplitsResult.native_object: Any | None` becomes `splitter: vbt.Splitter` (required, typed),
  extending ADR-0015's typed-stage-result pattern with a real framework type at the seam. The runner
  takes `RunSplitsResult` whole (it reads the splitter and roles), matching ADR-0015's
  majority/aggregator consumption rule.
- `runner._build_splitter`, `SET_LABELS`, and the runner's `optimization.split` read are deleted; the
  runner keeps `optimization` only for `search`/`seed`/`random_subset`/`execute`. The duplication
  dies structurally — the runner has no `getattr(vbt.Splitter, …)` left to drift.
- `build_preflight` narrows to `splits: Sequence[RunSplit]`; preflight no longer imports
  `RunSplitsResult`. `execution.py` passes `setup.split_result.splits` to preflight and
  `setup.split_result` to the runner.
- Tests: `test_run_splits` set-name assertions (`"set_0"`, `"train"`) become `"selection"` /
  `"held_out"` — the `"train"` change is a vocabulary fix; the preflight `_split_result` factory
  returns a `list[RunSplit]`.
- No Evidence or serialization change; `manifest.json` and split metadata are byte-identical — the
  regression oracle. ADR-0002 (the Selection set feeds global ranking) is the beneficiary and is
  honored; ADR-0001's stage seams are untouched; no ADR is reopened.
