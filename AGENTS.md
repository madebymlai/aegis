# Issue tracker

  Use bd (beads) for issue tracking.

  - Run `bd prime` for workflow context and command guidance.
  - Use `bd ready`, `bd show <id>`, `bd update <id> --claim`, and `bd close <id>`.
  - Use `bd remember "insight"` for persistent project memory; do not create MEMORY.md files.
  - Use `bd dep add <blocked> --blocked-by <blocker>` for building dependecies trees across issues.
  - Do not use markdown TODO lists for task tracking.
  - `/to-prd` must create the PRD issue with `--type=epic`. Epics are containers — implement their children, not the epic itself.

# Triage labels

Two **category** roles:

 - `bug` — something is broken
 - `enhancement` — new feature or improvement

Five **state** roles:

 - `needs-triage` — maintainer needs to evaluate
 - `needs-info` — waiting on reporter
 - `ready-for-agent` — fully specified, AFK-ready (an agent can pick it up with no human context)
 - `ready-for-human` — needs human implementation
 - `wontfix` — will not be actioned

# Domain docs

Domain language and terminology defined in `CONTEXT.md` (or `CONTEXT-MAP.md`) the repo root.

# Coding Standards

see `CODING_STANDARDS.md` for coding standards - how to write code

# Workflow

Switch branches only when explicitly asked. Main flow: develop -> merge release to main

When reindexing the codebase-memort-mcp, use mode:full - the library is blazingly fast anyways.

Review findings are claims, not instructions. Before review-driven edits, freeze them into a closed docket and classify each as FIX or WONTFIX against the governing spec, documented standards, and changed lines. Address only FIX items; follow-up reviews may verify fixes and remediation regressions but must not expand into unchanged code.

<design-principles>
## Module Boundaries

- **Deep Modules** — Prefer modules with simple interfaces that hide substantial implementation; depth, not a thin pass-through, is what earns a module its interface.
- **Information Hiding** — A design decision (file format, schema, protocol, algorithm) lives in exactly one module; the same knowledge must not surface in modules that then have to change together.
- **Tell, Don't Ask** — Tell an object what to do and let it act on its own state, rather than querying its state and deciding on its behalf.

## Coupling

- **Law of Demeter** — Talk only to immediate collaborators: call methods on self, parameters, owned fields, or objects you created; never on objects returned by other calls.

## Module Design

- **SRP** — A module should have one, and only one, reason to change: responsible to one actor.
- **OCP** — Software entities should be open for extension but closed for modification.
- **LSP** — Objects of a supertype shall be replaceable with objects of a subtype without altering program correctness.
- **ISP** — No client should be forced to depend on methods it does not use; prefer many client-specific interfaces over one general-purpose interface.
- **DIP** — High-level modules should not depend on low-level modules; both should depend on abstractions, and abstractions should not depend on details.
- **Composition Over Inheritance** — Default to composition; use inheritance only when the subtype genuinely satisfies LSP and the hierarchy is closed to further extension.
- **Command-Query Separation** — Every method should either be a command that performs an action or a query that returns data, but never both.

## Meta

- **KISS** — Every system works best when simplicity is a key goal and unnecessary complexity is avoided.
- **YAGNI** — Do not introduce abstractions, parameters, or code paths that serve no current caller; if no concrete use case exercises it today, delete it. Wins for internal implementation.
- **Forward-First** — Design for the current and next contract version; never introduce backward-compatibility shims or legacy code paths that increase maintenance surface. Wins for contract surfaces.

## Domain Modeling

- **No Primitive Obsession** — Represent domain concepts as named types rather than raw strings, numbers, or booleans. A customer ID is not a string; a price is not a float.

## Robustness

- **Define Errors Out of Existence** — Design APIs so that routine edge cases are not errors at all (return empty, clamp, no-op) rather than pushing exceptions onto every caller.
</design-principles>
