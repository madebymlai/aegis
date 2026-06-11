# The run command emits one JSON contract — no human mode, real paths

Status: accepted

`aerd run` emits the structured JSON envelope always, on success and on failure: the
`--json` flag is removed from its parser (passing it fails loudly as an unrecognized
argument — no accepted-and-ignored shim, per Forward-First), and the human rendering of
run results (`held_out_summary_lines`, `reproduce_lock_lines`, and their helpers) is
deleted rather than relocated. The `show`/guide commands keep their dual-mode toggle for
*success* output — their consumer is plausibly a human at a terminal; a run's consumer
is a script or an agent, and run output had already grown two diverging shape-owners
(the handler's hand-built payload and the dead, divergent `run_success_payload`). The
result shaping moves to one home, `cli_support/run_output.py`, with a single public
entry; future human-facing affordances (e.g. plot display) arrive as explicit flags on
top of the JSON contract, not as a second output mode.

**There is no output mode in the dispatcher.** `write_error` emits the JSON envelope
unconditionally for every command, which removes the only reason `json_requested` (a raw
`"--json" in argv` re-scan, needed because errors can fire before argparse finishes)
ever existed: it is deleted, `_main` computes and threads no `json_mode`, and handlers
own their output entirely. The `show`/guide `--json` becomes an ordinary parsed argument
(`default=False`, read off the namespace inside the handler) instead of a
`SUPPRESS`-registered marker whose real value came from the argv scan. A command-name
check in `_main` (errors-JSON for run only) was rejected as the same side path in new
clothes.

Three contract details are part of the decision:

- **Run identity has one projection, shared by both envelopes.** The six-field `run`
  block (`id`, `status`, `run_dir`, `manifest_path`, `started_at`, `finished_at`) was
  hand-built on the success path and built by `safe_run_refs` on the error path — two
  encodings kept equal by convention. One projection in `cli_support/output.py` now
  serves both; `safe_run_refs` is deleted.
- **Paths are real.** `safe_path`'s rewriting (cwd-relative, `~`, `<tmp>`, and the
  information-destroying `<path>` fallback) is retired from run output **and** from
  `ConfigSelectionEvidence` — the Manifest's config-selection Evidence records the
  resolved absolute config path. This finishes what ADR-0009 started: under the
  local-single-machine threat model there is nothing to scrub, and a local tool that
  hides the location of its own run directory works against its user. No schema bump:
  same key, same type; existing Runs are unaffected.
- **Lock handles are payload data, not formatting.** Each entry in
  `payload["candidates"]` carries a ready-to-paste `"lock"` handle. The composer
  `lock_handle(run_id, role)` lives in `configuration/schema.py` beside
  `Lock._coerce_handle`, so the `run_id[:role]` grammar (bare = `best`) is read and
  written by one module instead of being re-derived by every JSON consumer — the only
  knowledge the deleted human lines carried.

Rejected: keeping `--json` as a no-op (compat shim against Forward-First); making only
the success path JSON-always (the contract would split by status exactly where scripts
parse hardest); scrubbing paths in Evidence while emitting real ones in the CLI (the
retired threat model would survive in one layer). Amends the human-mode expectation for
`run` and for every command's *error* output; ADR-0019's guide-command human success
mode is untouched.
