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

NOTE: This module MUST NOT import from konkon.core.ingestion or konkon.core.ingestion.raw_db.
It receives RawDataAccessor as a parameter (protocol-based dependency).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

# BuildError / KonkonError are in core.models which is a utility module
# (depends_on=[] is about *this module's* declared deps in tach, but
#  utility modules are importable by all — see tach.toml).
# However, plugin_host has depends_on=[] in tach, meaning it cannot
# import from any non-utility konkon module. core.models IS utility=true,
# so this import is allowed.
from konkon.core.models import BuildError, KonkonError, QueryError, QueryResult

_REQUIRED_FUNCTIONS = ("build", "query", "schema")


def load_plugin(path: Path) -> ModuleType:
    """Load a plugin module from *path* and validate the Plugin Contract.

    The plugin must define callable ``build()`` and ``query()`` functions.
    Raises ValueError if the contract is not satisfied.
    Raises FileNotFoundError if the file does not exist.
    """
    if not path.exists():
        raise FileNotFoundError(f"Plugin file not found: {path}")

    # Add plugin directory to sys.path so sibling modules (e.g. targets.py)
    # can be imported by the plugin.
    plugin_dir = str(path.parent.resolve())
    if plugin_dir not in sys.path:
        sys.path.insert(0, plugin_dir)

    spec = importlib.util.spec_from_file_location("konkon_plugin", str(path))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    # Validate Plugin Contract: build(), query(), schema() must exist and be callable
    missing = [
        fn for fn in _REQUIRED_FUNCTIONS
        if not callable(getattr(module, fn, None))
    ]
    if missing:
        raise ValueError(
            f"Plugin contract violation — {path.name} must define "
            f"'build()', 'query()', and 'schema()' functions. Missing: {', '.join(missing)}"
        )

    return module


def invoke_build(plugin: ModuleType, raw_data: object) -> None:
    """Call plugin.build(raw_data).

    KonkonError subclasses (e.g. BuildError) propagate unchanged.
    Other exceptions are wrapped as BuildError.
    """
    try:
        plugin.build(raw_data)
    except KonkonError:
        raise
    except Exception as exc:
        raise BuildError(str(exc)) from exc


def invoke_query(plugin: ModuleType, request: object) -> str | QueryResult:
    """Call plugin.query(request) and return the result.

    KonkonError subclasses (e.g. QueryError) propagate unchanged.
    Other exceptions are wrapped as QueryError.
    Returns str or QueryResult as-is from the plugin.
    """
    try:
        return plugin.query(request)
    except KonkonError:
        raise
    except Exception as exc:
        raise QueryError(str(exc)) from exc
