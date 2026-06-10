# Carry a failed Run's terminal state across the failure seam

Status: accepted

When a **Run** fails, the CLI error report patches the Run's status and finish time by re-reading
the **Manifest** file from disk — despite the pipeline holding those facts in memory the whole time.
The seam between the pipeline and CLI — a bare raised exception plus a callback captured at start —
drops the terminal state. Worse, the disk re-read swallows read and parse errors, silently returning
stale refs so a failed Run can be reported as still `running` with no signal the report is wrong.

The pipeline now tells the CLI; the CLI formats what it is told. The callback fires twice: once at
Run creation with `running` refs, and again after the recorder persists the terminal status
(`failed`/`interrupted` with `finished_at`) just before the exception propagates. The CLI's disk
re-read is deleted along with its silent-stale failure mode. The refs projection — a six-field dict
of run id, run directory, manifest path, status, started-at, and finished-at — moves onto the run
recorder as a `run_refs()` method, so the projection lives with its data (tell-don't-ask).

Transport is the existing callback channel. Exception objects are not wrapped, re-typed, or
annotated — the CLI's exception-type → exit-code mapping and config-validation pass-through
survive verbatim. Durability is unchanged: the **Manifest** on disk is still current at raise time;
it is just no longer read back.

## Considered options

- **A refs-carrying pipeline exception** (annotate exceptions with Run refs): rejected — breaks the
  exception-type → exit-code mapping (e.g. `ConfigValidationError` → exit code 6) and the
  config-validation pass-through where no Run exists yet.
- **A result-object return on failure** (return `Ok`/`Err` variant): rejected — largest restructure
  for one caller; fights ADR-0015's precedent that terminal CLI-facing surfaces stay plain dicts
  while exceptions signal failure. The callback channel already exists and works.
- **Disk re-read as belt-and-braces fallback**: rejected — the same fact in two homes means one can
  silently go stale, which is the exact failure mode this change deletes. The in-memory hand-off is
  sufficient by ADR-0009's threat model (Runs are local and single-process).
- **A typed refs value object**: rejected — the six-field dict is a terminal CLI-facing surface, and
  house precedent (ADR-0015) keeps terminal surfaces as plain dicts.

## Landing

The change lands in three slices:

1. **aegis-rd-4rq.1** — The recorder gains `run_refs()`; the free refs-builder in the completion
   stage is deleted. Both call sites (orchestrator start event and completion success result) call
   the recorder method. Zero behavior change.
2. **aegis-rd-4rq.2** — The misnamed playbook failure-path test file is renamed; legacy-selector
   rejection tests (duplicated from the config-contract layer) are dropped.
3. **aegis-rd-4rq.3** — The callback fires twice (start + terminal); the CLI's disk re-read is
   deleted; the two identical failure clauses fold into one. The error-path JSON envelope is
   byte-identical before and after.

## Consequences

- The refs projection exists in exactly one place — `RunRecorder.run_refs()` — and every call site
  already holds the recorder, so no capability widens (ADR-0004's discipline: optimization stages
  do not see the recorder, is untouched).
- The orchestrator no longer imports anything from the completion stage except the stage call
  itself — the `build_run_refs` import is gone.
- ADR-0004 (terminal status persisted by recorder mark-methods before raise) stands.
- ADR-0009 (Runs are local and single-process, so in-memory hand-off is sufficient) is relied upon.
- ADR-0015 (terminal CLI-facing surfaces stay dicts) is followed — no typed refs object.
