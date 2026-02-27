"""Ingestion Context facade (01_conceptual_architecture.md §1.1).

Public API for data ingestion. Called by CLI and Serving layers.
Internal implementation delegates to raw_db.py.

Responsibilities:
- Insert a Document into Raw DB as a Raw Record
- Provide RawDataAccessor for Transformation Context (ACL #1)
- Lazy Raw DB initialization (create on first access)

Owns:
- Raw DB (SQLite), ingest metadata

Does NOT know about:
- AI, vectors, context, plugins, build, query

References:
- 01_conceptual_architecture.md §1.1, §2.1, §3.1
- 03_data_model.md (Raw DB schema)
- 04_cli_design.md §4.2 (insert)
"""

from konkon.core.models import JSONValue, RawRecord

# TODO: Implement
# - ingest(content: str, meta: dict[str, JSONValue] | None, project_root: Path) -> RawRecord
#   - Open/create Raw DB via core/instance.py (lazy init)
#   - Delegate to RawDB.insert()
#   - Return RawRecord
# - get_accessor(project_root: Path) -> RawDataAccessor
#   - Open Raw DB (must exist)
#   - Return RawDB.accessor()
