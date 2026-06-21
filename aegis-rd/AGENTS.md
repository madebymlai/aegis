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
