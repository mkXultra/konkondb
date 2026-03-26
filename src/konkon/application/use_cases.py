"""Use Case functions — Application Layer (Thin Orchestrator).

Each function delegates to the appropriate Context Facade.
No business logic, no domain models, no persistence.

Design decisions (implementation_plan_app_layer.md):
- project_root is a function parameter (no state object)
- plugin spec is resolved via resolve_plugin_spec() (plugin_path + import_root)
- Exceptions propagate unchanged from Context Facades
"""

from pathlib import Path

from konkon.core import ingestion
from konkon.core.instance import init_project as _init_project
from konkon.core.instance import load_config, resolve_plugin_spec, save_config
from konkon.core.models import JSONValue, QueryResult, RawRecord
from konkon.core.transformation import run_build as _run_build
from konkon.core.transformation import run_describe as _run_describe
from konkon.core.transformation import run_query as _run_query


def init(
    directory: Path,
    *,
    force: bool = False,
    plugin: str | None = None,
    import_root: str | None = None,
    raw_backend: str | None = None,
) -> None:
    """Initialize a konkon project.

    Delegates to core.instance.init_project().
    """
    _init_project(
        directory, force=force, plugin=plugin,
        import_root=import_root, raw_backend=raw_backend,
    )


def insert(
    content: str,
    meta: dict[str, JSONValue] | None,
    project_root: Path,
) -> RawRecord:
    """Insert a document into Raw DB.

    Delegates to core.ingestion.ingest().
    """
    return ingestion.ingest(content, meta, project_root)


def update(
    record_id: str,
    *,
    content: str | None,
    meta: dict[str, JSONValue] | None,
    project_root: Path,
) -> RawRecord:
    """Update an existing Raw Record.

    Delegates to core.ingestion.update().
    """
    return ingestion.update(record_id, content, meta, project_root)


def delete(
    record_id: str,
    project_root: Path,
) -> None:
    """Delete a Raw Record and create a tombstone.

    Delegates to core.ingestion.delete().
    """
    ingestion.delete(record_id, project_root)


def build(
    project_root: Path,
    *,
    full: bool = False,
    plugin_override: Path | None = None,
) -> None:
    """Run build() from the user plugin.

    Resolves plugin_path and import_root via resolve_plugin_spec().
    When plugin_override is given, import_root is None (override uses
    its parent directory for sys.path).
    Delegates to core.transformation.run_build().
    """
    if plugin_override is not None:
        plugin_path = plugin_override
        import_root = None
    else:
        plugin_path, import_root = resolve_plugin_spec(project_root)
    _run_build(project_root, full=full, plugin_path=plugin_path,
               import_root=import_root)


def describe(
    project_root: Path,
    *,
    plugin_override: Path | None = None,
) -> dict:
    """Run schema() from the user plugin.

    Resolves plugin_path and import_root via resolve_plugin_spec().
    Delegates to core.transformation.run_describe().
    """
    if plugin_override is not None:
        plugin_path = plugin_override
        import_root = None
    else:
        plugin_path, import_root = resolve_plugin_spec(project_root)
    return _run_describe(project_root, plugin_path=plugin_path,
                         import_root=import_root)


def search(
    project_root: Path,
    query: str,
    *,
    params: dict[str, str] | None = None,
    plugin_override: Path | None = None,
) -> str | QueryResult:
    """Run query() from the user plugin.

    Resolves plugin_path and import_root via resolve_plugin_spec().
    Delegates to core.transformation.run_query().
    """
    if plugin_override is not None:
        plugin_path = plugin_override
        import_root = None
    else:
        plugin_path, import_root = resolve_plugin_spec(project_root)
    return _run_query(project_root, query, params=params,
                      plugin_path=plugin_path, import_root=import_root)


def raw_list(
    project_root: Path,
    *,
    limit: int = 20,
) -> list[RawRecord]:
    """List recent records from Raw DB.

    Delegates to core.ingestion.list_records().
    """
    return ingestion.list_records(project_root, limit=limit)


def raw_get(
    project_root: Path,
    record_id: str,
) -> RawRecord | None:
    """Get a single record by ID from Raw DB.

    Delegates to core.ingestion.get_record().
    """
    return ingestion.get_record(project_root, record_id)


def migrate(
    target_backend: str,
    project_root: Path,
    *,
    force: bool = False,
) -> tuple[int, str]:
    """Migrate Raw DB to a different backend.

    Orchestrates:
    1. Data migration (Ingestion Context)
    2. Config update (Instance)

    Returns (migrated_count, source_backend).
    """
    count, source_backend = ingestion.migrate(
        project_root, target_backend, force=force,
    )

    # Update config.toml with new backend
    config = load_config(project_root)
    config["raw_backend"] = target_backend
    save_config(project_root, config)

    return count, source_backend
