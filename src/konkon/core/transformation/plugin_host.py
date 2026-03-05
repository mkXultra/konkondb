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
import inspect
import sys
from pathlib import Path
from types import ModuleType

# BuildError / KonkonError are in core.models which is a utility module
# (depends_on=[] is about *this module's* declared deps in tach, but
#  utility modules are importable by all — see tach.toml).
# However, plugin_host has depends_on=[] in tach, meaning it cannot
# import from any non-utility konkon module. core.models IS utility=true,
# so this import is allowed.
from konkon.core.models import BuildError, ConfigError, KonkonError, QueryError, QueryResult

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

    # Validate build() signature: exactly 2 required positional parameters,
    # no required keyword-only parameters (06_build_context.md §3.2)
    _validate_build_signature(module, path)

    return module


def _validate_build_signature(module: ModuleType, path: Path) -> None:
    """Validate that build() has exactly 2 required positional params."""
    sig = inspect.signature(module.build)
    required_positional = [
        p for p in sig.parameters.values()
        if p.kind in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        )
        and p.default is inspect.Parameter.empty
    ]
    required_keyword_only = [
        p for p in sig.parameters.values()
        if p.kind == inspect.Parameter.KEYWORD_ONLY
        and p.default is inspect.Parameter.empty
    ]

    if len(required_positional) != 2 or required_keyword_only:
        raise ConfigError(
            f"Contract violation: build() must have exactly 2 required positional parameters "
            f"(raw_data, context) and no required keyword-only parameters, "
            f"got {len(required_positional)} positional, "
            f"{len(required_keyword_only)} keyword-only. "
            f"Update your plugin: def build(raw_data, context): ..."
        )


def invoke_build(plugin: ModuleType, raw_data: object, context: object) -> None:
    """Call plugin.build(raw_data, context).

    KonkonError subclasses (e.g. BuildError) propagate unchanged.
    Other exceptions are wrapped as BuildError.
    """
    try:
        plugin.build(raw_data, context)
    except KonkonError:
        raise
    except Exception as exc:
        raise BuildError(str(exc)) from exc


def invoke_schema(plugin: ModuleType) -> dict:
    """Call plugin.schema() and return the schema dict.

    schema() errors are configuration-level (exit 3), so exceptions
    are wrapped as ValueError.  Uses ValueError (not a KonkonError subclass)
    because schema violations are config/contract errors; a dedicated
    ConfigError may replace this in the future.
    """
    try:
        result = plugin.schema()
    except Exception as exc:
        raise ValueError(f"schema() failed: {exc}") from exc
    if not isinstance(result, dict):
        raise ValueError(
            f"schema() must return dict, got {type(result).__name__}"
        )
    return result


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
