"""Transformation Context facade (01_conceptual_architecture.md §1.2).

Public API for build and query operations. Called by CLI and Serving layers.
Internal implementation delegates to plugin_host.py.

Responsibilities:
- Load user plugin (konkon.py) and validate Plugin Contract
- Execute build: plugin.build(raw_data_accessor)
- Execute query: plugin.query(request) -> str | QueryResult
- Orchestrate data flow between Ingestion Context and User Plugin

Owns:
- Plugin Host (runtime), Plugin Contract enforcement

Does NOT know about:
- Context Store internals, Raw DB schema, protocol details

ACL boundaries:
- Receives RawDataAccessor from Ingestion Context (ACL #1)
- Enforces Plugin Contract with User Plugin (ACL #2)
- Returns QueryResult to callers / Serving Context (ACL #3)

References:
- 01_conceptual_architecture.md §1.2, §2.1, §3.2
- 02_interface_contracts.md §1 (Plugin Contract), §2.1 (Async/Sync)
- 04_cli_design.md §4.3 (build), §4.4 (search)
"""

# TODO: Implement
# - run_build(project_root: Path) -> None
#   - Load plugin via plugin_host.py
#   - Get RawDataAccessor from ingestion.py
#   - Invoke plugin.build(raw_data)
# - run_query(project_root: Path, query: str, params: dict | None) -> str | QueryResult
#   - Load plugin via plugin_host.py
#   - Create QueryRequest
#   - Invoke plugin.query(request)
#   - Return result
