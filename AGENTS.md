# tokf

🗜️ means this output was compressed by tokf.
Run `tokf raw last` to see the full uncompressed output of the last command.

# Principles

- **SRP** — A module should have one, and only one, reason to change: responsible to one actor.
- **OCP** — Software entities should be open for extension but closed for modification.
- **LSP** — Objects of a supertype shall be replaceable with objects of a subtype without altering program correctness.
- **ISP** — No client should be forced to depend on methods it does not use; prefer many client-specific interfaces over one general-purpose interface.
- **DIP** — High-level modules should not depend on low-level modules — both should depend on abstractions; abstractions should not depend on details.
- **KISS** — Every system works best when simplicity is a key goal and unnecessary complexity is avoided.
- **DRY** — Every piece of knowledge must have a single, unambiguous, authoritative representation within a system.
- **Forward-First** — Design for the current and next contract version; never introduce backward-compatibility shims or legacy code paths that increase maintenance surface.
- **No Defensive Garbage** — Trust established preconditions and module contracts; let violated invariants surface as immediate failures instead of masking them with silent fallbacks.
- **Tell, Don't Ask** — Rather than querying an object's state and acting on it, tell the object what to do and let it use its own state to decide how.
- **Fail Fast** — Detect and report errors at the earliest possible point, at the interface where the fault originates, rather than allowing bad state to propagate.
- **No Silent Error Swallowing** — Never catch an exception and discard it without logging, re-raising, or making the failure visible; every error must produce an observable signal.
- **Explicit Error Types** — Represent each distinct failure mode as a named, typed value in the return signature rather than relying on generic exceptions or sentinel values.

## Documented Solutions

`docs/solutions/` contains documented solutions to past problems and practices (bugs, best practices, workflow patterns), organized by category with YAML frontmatter (`module`, `tags`, `problem_type`). Relevant when implementing, debugging, or making decisions in documented areas.

## Workflow
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
