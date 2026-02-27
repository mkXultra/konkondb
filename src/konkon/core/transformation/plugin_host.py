"""Plugin Host — Transformation Context (01_conceptual_architecture.md §1.2).

Responsibilities:
- Load user plugin (konkon.py) and validate Plugin Contract (build + query)
- Invoke build(raw_data) with a RawDataAccessor from Ingestion Context
- Invoke query(request) and return str | QueryResult
- Handle sync/async plugin functions (inspect.iscoroutinefunction)
- Catch and classify exceptions (KonkonError vs unexpected)

References:
- 02_interface_contracts.md §1 (Plugin Contract)
- 02_interface_contracts.md §2.1 (Async/Sync support)

ACL boundaries:
- Receives RawDataAccessor from Ingestion Context (ACL #1, read-only)
- Exposes Plugin Contract to User Plugin Logic (ACL #2)
- Returns QueryResult to Serving Context (ACL #3)
"""

# TODO: Implement per 02_interface_contracts.md
# - load_plugin(path: Path) -> module
#   - Validate build() and query() exist
#   - Detect sync/async
# - invoke_build(plugin, raw_data: RawDataAccessor) -> None
#   - Catch KonkonError (clean message) vs unexpected (full traceback)
# - invoke_query(plugin, request: QueryRequest) -> str | QueryResult
#   - Catch KonkonError vs unexpected
#   - For server mode: wrap sync query() in asyncio.to_thread()
