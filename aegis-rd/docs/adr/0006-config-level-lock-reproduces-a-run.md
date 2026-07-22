# Collapse component locks into a single config-level Lock reference

Status: accepted (implementation queued behind ADR-0005 market-data work)

Locks were per-Component minted tokens (`lock_…`) kept in a dedicated `candidate_locks`
table and resolved one Component at a time. We replace them with a single top-level `lock:`
block in the Run Config, defined as `{run_id, candidate_id}` — which is exactly the
`candidates` primary key `(run_id, candidate_key)`, so a Lock needs no separate storage.
A locked Run reproduces one prior Candidate: every Component takes its parameters from that
Candidate and nothing is optimized.

`lock_id` is redefined as the transparent `(run_id, candidate_id)` pair, not an opaque hash
token. The two concerns a Run Config can express are now cleanly split: `params:` is
values-only (fix individual Component parameters), and the top-level `lock:` is the only
reference (reproduce a whole prior Candidate). Per-Component `lock_id`/`candidate_id`/`run_id`
fields are removed. When a locked config also carries `params:`, the lock wins and the run's
Evidence records the overridden values, so the Manifest never silently misrepresents what ran.

## Considered options

- **Typed `CandidateRow` at the store seam** (2026-05-29 review, candidate 5): rejected. The
  candidate row is a schema-versioned, hash-stable Evidence artifact — recorded into the
  Evidence ledger (ADR-0004) and persisted as `candidate_row_json`. Wrapping it violates
  ADR-0003/0005's "type the internal spine, keep the terminal artifact a dict" and risks
  moving Evidence hashes. Its spine (`EvaluatedCandidate`) is already typed.
- **Keep per-Component locks for partial freeze** (freeze one Component, optimize the rest —
  what `etf_vanguard_tune_lock_{mom,vol}.yaml` do today): rejected. That workflow is better
  served by per-Component `params:`, which already fixes a single Component's parameters
  while the rest optimize. Folding partial freeze into `params:` lets locks mean exactly one
  thing — whole-Candidate reproduction — and removes the per-Component reference surface.
- **Reject configs that set both `lock:` and `params:`** (today's per-Component rule):
  rejected in favour of lock-wins-plus-Evidence-record, so a lock can overlay an existing
  tuning config without silently dropping the author's values.

## Consequences

- Deletes the entire `candidate_locks` storage path and the lock-token minting/resolution
  machinery; the per-Component ref fields leave the config schema.
- **Partial freeze moves from per-Component locks to per-Component `params:`.** The two
  `etf_vanguard_tune_lock_{mom,vol}.yaml` samples migrate: the frozen Component's `lock_id:`
  is replaced by inline `params:` holding that Component's literal values (resolved once from
  the old lock). Old `lock_…` tokens stop resolving (Forward-First, no compat shim).
- `params:` carries no source provenance — it is literal values by definition. A frozen
  Component no longer records which Run/Candidate its values came from; that lineage lives
  only on a full `lock:`.
- Reproduction via `lock:` is faithful only when the locked config's data/portfolio match the
  original Run — the Lock pins parameters; the config still supplies data and portfolio.
- CONTEXT.md **Lock** entry redefined.

## Amendment (aegis-rd-6ie): human-friendly lock handle

The shipped `{run_id, candidate_id}` mapping is reproducible-by-machine but not
usable-by-human: the `candidate_id` is a content-hash with no `aerd show candidates`
command to discover it, and it forces two YAML fields plus an opaque hash. We amend the
`lock:` contract — **not** the storage model — to accept a single scalar:

```yaml
lock: 20260527T000603791760Z_etf_momentum          # -> best (default)
lock: 20260527T000603791760Z_etf_momentum:median   # non-best representative
```

- A scalar `run_id[:role]` defaults `role` to `best`; `role` is one of `best`/`median`/`worst`.
  A malformed or unknown role fails at config validation with a clear message. The `run_id`
  is literally the Run folder name, so the common case is copy-the-directory-name-and-paste.
- `role` resolves to a `candidate_key` through the existing `candidate_rankings` table
  (primary key `(run_id, role)`) — storage-free, exactly like the `candidates` primary key
  this ADR already leaned on. **No minted code, no new storage**: a code->hash map would undo
  the deletion this ADR made, so it is deliberately avoided.
- The precise forms still resolve: the `{run_id, candidate_id}` mapping, with `candidate_id`
  a `role` keyword **or** a raw `candidate_key` hash (hash = durable/exact; role = ergonomic).
- Lock provenance still records the resolved `candidate_key`, so locking by role keeps a full
  audit trail of the exact hash — and the lock-wins-plus-Evidence-record rule is unchanged.
- Post-run terminal output prints, per representative Candidate, the exact copy-paste
  `lock: <run_id>[:role]` string plus the `run_id` and candidate-store path, so the handle is
  discoverable without `--json` or raw SQL.

This makes the ADR's "no separate storage" principle hold *better*: the ergonomic handle is a
pure query over rankings the Run already persists.

**Amendment (2026-07-23).** `strategy_run.json` is deleted. CandidateStore is the durable authority
for Candidate rows, roles, activation, Candidate Keys, and Lock resolution; its provenance no
longer names a strategy artifact. The CLI still returns representative Candidate summaries and
copy-paste Lock handles directly from the completed in-memory result. Lock resolution and exact
Candidate reproduction therefore depend only on the authority this ADR established.

**Amendment (2026-07-23) — Run IDs outlive the directory layout.** A Lock handle continues to use
the Run ID recorded in Candidate Store; it is no longer described as a folder name. Flattening Run
storage to `<run-id>.json` changes neither Lock parsing nor Candidate lookup.
