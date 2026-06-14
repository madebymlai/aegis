# tokf

🗜️ means this output was compressed by tokf.
Run `tokf raw last` to see the full uncompressed output of the last command.

# Principles

- **SRP** — A module should have one, and only one, reason to change: responsible to one actor.
- **OCP** — Software entities should be open for extension but closed for modification.
- **LSP** — Objects of a supertype shall be replaceable with objects of a subtype without altering program correctness.
- **ISP** — No client should be forced to depend on methods it does not use; prefer many client-specific interfaces over one general-purpose interface.
- **DIP** — High-level modules should not depend on low-level modules — both should depend on abstractions; abstractions should not depend on details.
- **Composition Over Inheritance** — Default to composition; use inheritance only when the subtype genuinely satisfies LSP and the hierarchy is closed to further extension.
- **Command-Query Separation** — Every method should either be a command that performs an action or a query that returns data, but never both.
- **KISS** — Every system works best when simplicity is a key goal and unnecessary complexity is avoided.
- **YAGNI** — Do not introduce abstractions, parameters, or code paths that serve no current caller. If no concrete use case exercises it today, delete it.
- **Forward-First** — Design for the current and next contract version; never introduce backward-compatibility shims or legacy code paths that increase maintenance surface.
- **No Primitive Obsession** — Represent domain concepts as named types rather than raw strings, numbers, or booleans. A customer ID is not a string; a price is not a float.

# Agent skills

## Issue tracker

Use bd (beads) for issue tracking.

- Run `bd prime` for workflow context and command guidance.
- Use `bd ready`, `bd show <id>`, `bd update <id> --claim`, and `bd close <id>`.
- Use `bd remember "insight"` for persistent project memory; do not create MEMORY.md files.
- Do not use markdown TODO lists for task tracking.
- The issue PRD of `/to-prd` must be made with `type=epic`.

## Triage labels

Two **category** roles:

- `bug` — something is broken
- `enhancement` — new feature or improvement

Five **state** roles:

- `needs-triage` — maintainer needs to evaluate
- `needs-info` — waiting on reporter
- `ready-for-agent` — fully specified, AFK-ready (an agent can pick it up with no human context)
- `ready-for-human` — needs human implementation
- `wontfix` — will not be actioned

## Domain docs

Domain language and terminology defined in `CONTEXT.md` at the repo root.

## Documented Solutions

`docs/solutions/` contains documented solutions to past problems and practices (bugs, best practices, workflow patterns), organized by category with YAML frontmatter (`module`, `tags`, `problem_type`). Relevant when implementing, debugging, or making decisions in documented areas.

# Workflow

**Documentation**:
[Documentation Sitemap](https://vectorbt.pro/pvt_16ebf9ef/llms.txt)

- Use VectorBT PRO MCP tools before web docs.
- Use `vectorbtpro_search` for broad docs/API searches.
- Use `vectorbtpro_find` for object mentions, docs examples, and Discord support context.
- For API objects, call `vectorbtpro_resolve_refnames` first.
- After resolving, call `vectorbtpro_get_attrs` for available methods/properties.
- After resolving, call `vectorbtpro_get_source` for implementation details.
- Use `vectorbtpro_get_page` for known docs or private docs URLs.
- Use `vectorbtpro_get_message`, `vectorbtpro_get_message_block`, or `vectorbtpro_get_message_thread` for Discord links.
- Use `vectorbtpro_run_code` only for small, safe VectorBT PRO experiments.
- Use direct `vectorbtpro_*` tool calls instead of MCP subprocesses.
- Fall back to the sitemap or web docs only when MCP tools are insufficient or unavailable.
