"""REST API Adapter — Serving Context (01_conceptual_architecture.md §1.3).

Responsibilities:
- Accept HTTP requests (Protocol Request)
- Translate to QueryRequest (ACL #3)
- Delegate to core/plugin_host.py invoke_query()
- Render QueryResult as Protocol Response (JSON)
- Stateless — no direct access to Raw DB or Context Store

References:
- commands/serve-api.md
- 06_serving_adapters.md (TBD)

Framework: TBD (FastAPI / Starlette / http.server — see 05 §7)
"""

# TODO: Implement after 06_serving_adapters.md is finalized
