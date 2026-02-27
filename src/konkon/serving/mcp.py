"""MCP Server Adapter — Serving Context (01_conceptual_architecture.md §1.3).

Responsibilities:
- Accept MCP tool calls via stdio/SSE (Protocol Request)
- Translate to QueryRequest (ACL #3)
- Delegate to core/plugin_host.py invoke_query()
- Render QueryResult as MCP tool response (Protocol Response)
- Stateless — no direct access to Raw DB or Context Store

References:
- 04_cli_design.md §4.5 (serve --mcp)
- 06_serving_adapters.md (TBD)

SDK: TBD (mcp official SDK / custom — see 05 §8)
"""

# TODO: Implement after 06_serving_adapters.md is finalized
