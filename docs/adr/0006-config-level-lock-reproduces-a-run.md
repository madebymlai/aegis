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
