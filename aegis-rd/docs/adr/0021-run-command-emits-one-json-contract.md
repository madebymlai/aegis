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
result shaping has one home; as amended on 2026-07-03, that home is the `run` command
handler itself. Future human-facing affordances (e.g. plot display) arrive as explicit
flags on top of the JSON contract, not as a second output mode.

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

**Amendment (2026-06-12).** The structured `show` subcommands (`components`,
`splitters`) drop their dual-mode toggle too: `write_success` emits the JSON envelope
unconditionally and has no mode parameter, `CommandResult.human_lines` and the
human-line formatters are deleted, and `--json` is removed from those parsers (failing
loudly, per Forward-First). The "plausibly a human at a terminal" carve-out proved not
worth a second output mode for data that is a JSON document either way — `aerd show
components | jq` serves the terminal reader. The carve-out now applies only to the
guide commands (`*-schema`), whose content is authored markdown, not data; ADR-0019
stands. In the same change `safe_path` is deleted outright: the generic JSON
sanitizer's `Path` branch emits real resolved absolute paths, so the scrub-vs-real
decision has one answer everywhere, including error `details`.

**Amendment (2026-07-03).** The run success-payload shape moves from the separate
`cli_support/run_output.py` module into `cli_commands/run.py` as a handler-local private
helper, and the separate module is deleted. The one-shape-owner invariant is unchanged:
the command handler owns the run result and now also owns its success projection, while
`cli_support/output.py` still owns the shared run-ref projection and the JSON envelope.
The pre-serialization unit seam is retired; the payload contract is tested only through
the emitted JSON by driving `cli.main(["run", ...])` with a stubbed sweep result and
capturing stdout. That seam also pins the ADR's real-path requirement against the
success-envelope serializer: success payload strings are preserved in full, so long
resolved artifact and Candidate Store paths are not clipped. Error messages and error
details keep their clipping behavior.

**Amendment (2026-07-23).** Every invocation creates a uniquely identified immutable Run.
`--rerun-mode`, `--parent-run-id`, and `--supersedes-run-id` are removed rather than accepted as
no-ops. The Manifest likewise drops mode, lineage, and the duplicate Run label; the resolved Run
Config remains the sole home of the configured name.

The same 2026-07-23 contract removes the `artifacts` block and strategy artifact path from Run
success output. The command returns only live references: Run lifecycle refs, Manifest path,
CandidateStore path, optimization accounting, and representative Candidate summaries. No
placeholder or renamed report projection replaces the deleted file.
