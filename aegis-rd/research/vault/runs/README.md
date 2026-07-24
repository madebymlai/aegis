---
title: Runs
tags:
  - index
---

# Runs — strategy diaries

One diary note per day per strategy: `runs/<strategy>/<date>.md`, ISO-date filenames. Inside,
each run is a `### run_id` section (copy the run-folder name from the repo's `runs/`) recording
what was tested and how it went, and linking back to the [[research/README|paper]] or note that
seeded the idea. The headings are the single source of truth — searchable and
deep-linkable as `[[2026-06-10#run_id]]`. New day: use [[run-diary|the run-diary template]].

## What is a strategy — the run-diary gate

A behaviour from [[research/README|research/]] earns a run only when written as a falsifiable
rule answering five questions ([[what-is-a-strategy|full argument]]):

1. **State** — what makes action eligible *now*, not always?
2. **Action** — what is done, at what size?
3. **Exit** — how the position ends, on the good path and the bad?
4. **Payer** — who is on the other side and why they keep paying (the paper's economic rationale)?
5. **Failure** — the observation that kills the rule, **pre-registered before the data**.

Pre-register all five in the run's `### run_id` section before results exist — that is what makes
the keep/kill call honest.
