"""Runtime and project resolution helpers.

Responsibilities:
- Resolve project roots and project-mode config
- Resolve stateless file/in-memory config into a normalized runtime config
- Provide project resource paths for local backends
- Resolve postgres credentials without persisting secrets
"""

from __future__ import annotations

import os
import re
import sys
import tomllib
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Literal, Mapping

from konkon.core.models import ConfigError

KONKON_DIR = ".konkon"
RAW_DB_NAME = "raw.db"
JSON_DB_NAME = "raw.json"
PLUGIN_FILE = "konkon.py"
LAST_BUILD_FILE = "last_build"
CONFIG_FILE = "config.toml"

DEFAULT_POSTGRES_SCHEMA = "public"
DEFAULT_POSTGRES_RAW_RECORDS_TABLE = "raw_records"
DEFAULT_POSTGRES_RAW_DELETIONS_TABLE = "raw_deletions"
DEFAULT_POSTGRES_BUILD_STATE_TABLE = "build_state"
DEFAULT_BUILD_STATE_KEY = "default"
DEFAULT_POSTGRES_DSN_ENV = "KONKON_RAW_DSN"

_VALID_BACKENDS = frozenset({"sqlite", "json", "postgres"})
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass(frozen=True)
class RuntimeConfig:
    """Normalized runtime config for both project and stateless modes."""

    mode: Literal["project", "stateless"]
    raw_backend: str
    backend_explicit: bool
    plugin_path: Path
    import_root: Path | None
    config_base: Path
    project_root: Path | None = None
    config_path: Path | None = None
    dsn_env: str | None = None
    schema: str = DEFAULT_POSTGRES_SCHEMA
    raw_records_table: str = DEFAULT_POSTGRES_RAW_RECORDS_TABLE
    raw_deletions_table: str = DEFAULT_POSTGRES_RAW_DELETIONS_TABLE
    build_state_table: str = DEFAULT_POSTGRES_BUILD_STATE_TABLE
    build_state_key: str = DEFAULT_BUILD_STATE_KEY


class PostgresConnectionManager:
    """Small adapter that yields postgres connections.

    A manager may wrap:
    - an explicit connection
    - an explicit psycopg pool
    - a connection opened from DSN by this manager
    """

    def __init__(
        self,
        *,
        connection: Any | None = None,
        pool: Any | None = None,
        owns_connection: bool = False,
        owns_pool: bool = False,
    ) -> None:
        self._connection = connection
        self._pool = pool
        self._owns_connection = owns_connection
        self._owns_pool = owns_pool

    @contextmanager
    def acquire(self) -> Iterator[Any]:
        """Yield a usable postgres connection."""
        if self._connection is not None:
            yield self._connection
            return
        if self._pool is None:
            raise ConfigError("Postgres connection manager is not configured.")
        with self._pool.connection() as connection:
            yield connection

    def close(self) -> None:
        """Close internally-owned resources."""
        if self._owns_connection and self._connection is not None:
            self._connection.close()
            self._connection = None
            self._owns_connection = False
        if self._owns_pool and self._pool is not None:
            self._pool.close()
            self._pool = None
            self._owns_pool = False

PLUGIN_TEMPLATE = '''\
"""konkon plugin."""

from konkon.types import BuildContext, RawDataAccessor, QueryRequest, QueryResult


def schema():
    """Declare the query interface."""
    return {
        "description": "My konkon plugin",
        "params": {},
        "result": {
            "description": "Query result",
        },
    }


def build(raw_data: RawDataAccessor, context: BuildContext) -> None:
    """Transform raw data into AI-ready context.

    Args:
        raw_data: Records to process.
            mode="full": all records. mode="incremental": changed since last build.
        context: Build metadata.
            context.mode: "full" or "incremental".
            context.deleted_records: records deleted since last build
                (empty for full builds). Remove these from your Context Store.
    """
    pass


def query(request: QueryRequest) -> str | QueryResult:
    """Handle a query request."""
    return ""
'''


def _load_toml_file(path: Path) -> dict[str, Any]:
    """Load a TOML file from an arbitrary path."""
    with open(path, "rb") as f:
        return tomllib.load(f)


def load_config(project_root: Path) -> dict[str, Any]:
    """Load .konkon/config.toml and return the raw dict.

    Returns empty dict if file does not exist.
    Raises TOMLDecodeError on parse failure.
    """
    cfg = config_path(project_root)
    if not cfg.exists():
        return {}
    return _load_toml_file(cfg)


def save_config(project_root: Path, config: dict[str, Any]) -> None:
    """Write config dict to .konkon/config.toml.

    Preserves unknown keys whose values are TOML scalar types
    (str, bool, int, float). Non-scalar values (list, dict, datetime)
    and strings containing single quotes are skipped with a warning to stderr.

    String values are written as TOML literal strings (single quotes).
    Raises TypeError for values that are not valid TOML types at all,
    including non-finite floats (nan, inf).

    Note: ValueError is used for input validation errors (e.g. _validate_plugin_arg).
    A dedicated ConfigError may be introduced in a future version; for now ValueError
    covers config-related validation per design team consensus.
    """
    import datetime as _dt
    import math

    def _warn_skip(key: str, value: object, *, reason: str = "") -> None:
        detail = reason or (
            f"type '{type(value).__name__}' cannot be serialized "
            f"(only str/bool/int/float are preserved)"
        )
        print(
            f"[WARN] Skipping config key '{key}': {detail}. "
            f"Consider upgrading konkon.",
            file=sys.stderr,
        )

    lines: list[str] = []
    for key, value in config.items():
        if isinstance(value, bool):
            lines.append(f"{key} = {'true' if value else 'false'}")
        elif isinstance(value, str):
            if "'" in value:
                _warn_skip(
                    key, value,
                    reason="string contains single quote (cannot use TOML literal string)",
                )
                continue
            if "\n" in value or "\r" in value:
                _warn_skip(
                    key, value,
                    reason="string contains newline (cannot use TOML literal string)",
                )
                continue
            lines.append(f"{key} = '{value}'")
        elif isinstance(value, int):
            lines.append(f"{key} = {value}")
        elif isinstance(value, float):
            if not math.isfinite(value):
                raise TypeError(
                    f"Unsupported config value for key '{key}': "
                    f"non-finite float ({value})"
                )
            lines.append(f"{key} = {value}")
        elif isinstance(value, (list, dict)):
            _warn_skip(key, value)
            continue
        elif isinstance(value, (_dt.datetime, _dt.date, _dt.time)):
            _warn_skip(key, value)
            continue
        else:
            raise TypeError(
                f"Unsupported config value type for key '{key}': "
                f"{type(value).__name__}"
            )
    config_path(project_root).write_text("\n".join(lines) + "\n")


def config_path(project_root: Path) -> Path:
    """Return the path to config.toml under *project_root*/.konkon/."""
    return project_root / KONKON_DIR / CONFIG_FILE


def _validate_plugin_arg(plugin: str) -> None:
    """Validate plugin path argument for init_project.

    Raises ValueError for invalid paths.
    """
    if not plugin:
        raise ValueError("--plugin requires a non-empty path.")
    if Path(plugin).is_absolute():
        raise ValueError(
            f"--plugin must be a relative path (got '{plugin}')."
        )
    if "'" in plugin:
        raise ValueError(
            f"--plugin path must not contain single quotes (got '{plugin}')."
        )


def _validate_import_root_arg(import_root: str) -> None:
    """Validate import_root argument for init_project.

    Raises ValueError for invalid paths.
    """
    if not import_root:
        raise ValueError("--import-root requires a non-empty path.")
    if Path(import_root).is_absolute():
        raise ValueError(
            f"--import-root must be a relative path (got '{import_root}')."
        )
    if "'" in import_root:
        raise ValueError(
            f"--import-root path must not contain single quotes (got '{import_root}')."
        )


def init_project(
    directory: Path,
    *,
    force: bool = False,
    plugin: str | None = None,
    import_root: str | None = None,
    raw_backend: str | None = None,
) -> None:
    """Create a konkon project in *directory*.

    Creates .konkon/ (idempotent) and, unless *plugin* is given,
    generates a plugin template at ``directory/konkon.py``.
    Raises FileExistsError if the template file already exists and
    *force* is False.
    Does NOT create Raw DB (lazy init on first insert).

    If *plugin* is specified, writes ``plugin = '<path>'`` to
    ``.konkon/config.toml`` **only** — no template file is generated.
    The *force* flag is ignored in this case.

    If *raw_backend* is specified ('sqlite', 'json', or 'postgres'), writes it to
    .konkon/config.toml.
    """
    if plugin is not None:
        _validate_plugin_arg(plugin)
    if import_root is not None:
        _validate_import_root_arg(import_root)

    # Ensure the target directory exists so we can check import_root.
    # directory.mkdir is idempotent (exist_ok=True) and is the only
    # side effect before validation — .konkon/ and konkon.py are created later.
    directory.mkdir(parents=True, exist_ok=True)

    if import_root is not None:
        ir_path = directory / import_root
        if not ir_path.is_dir():
            raise ValueError(
                f"--import-root directory does not exist: {ir_path}"
            )

    if plugin is None:
        # Default: generate template at konkon.py
        plugin_path = directory / PLUGIN_FILE
        if plugin_path.exists() and not force:
            raise FileExistsError(
                f"{plugin_path} already exists. Use --force to overwrite."
            )

    (directory / KONKON_DIR).mkdir(exist_ok=True)

    if plugin is None:
        plugin_path.write_text(PLUGIN_TEMPLATE)

    needs_config = (
        plugin is not None
        or import_root is not None
        or raw_backend is not None
    )
    if needs_config:
        existing = load_config(directory)
        if plugin is not None:
            existing["plugin"] = plugin
        if import_root is not None:
            existing["import_root"] = import_root
        if raw_backend is not None:
            existing["raw_backend"] = raw_backend
        save_config(directory, existing)


def resolve_raw_backend(project_root: Path) -> tuple[str, bool]:
    """Resolve backend type and whether it was explicitly set.

    Priority: env > config > auto-detect > 'sqlite' fallback.
    """
    env = os.environ.get("KONKON_RAW_BACKEND")
    if env is not None:
        return env.lower(), True
    config = load_config(project_root)
    if "raw_backend" in config:
        return str(config["raw_backend"]).lower(), True
    db_exists = raw_db_path(project_root).exists()
    json_exists = json_db_path(project_root).exists()
    if db_exists and json_exists:
        raise ConfigError(
            "Both .konkon/raw.db and .konkon/raw.json exist. "
            "Set 'raw_backend' in .konkon/config.toml to specify "
            "which backend to use."
        )
    if json_exists and not db_exists:
        return "json", False
    return "sqlite", False


def resolve_project(start: Path | None = None) -> Path:
    """Walk up from *start* to find the project root.

    Project root marker (either satisfies):
    - .konkon/ directory exists, OR
    - konkon.py file exists (backward compatibility)

    Raises FileNotFoundError if neither is found up to the filesystem root.
    Per 04_cli_conventions.md §2.4.
    """
    current = (start or Path.cwd()).resolve()
    while True:
        if (current / KONKON_DIR).is_dir() or (current / PLUGIN_FILE).exists():
            return current
        parent = current.parent
        if parent == current:
            raise FileNotFoundError(
                "Error: konkon project not found (no .konkon/ directory or konkon.py). "
                "Run 'konkon init' to create a project, "
                "or use '--project-dir' to specify the project root."
            )
        current = parent


def resolve_plugin_path(
    project_root: Path,
    *,
    cli_plugin: Path | None = None,
    require_plugin: bool = True,
) -> Path:
    # Priority 1: CLI argument (already absolute)
    if cli_plugin is not None:
        resolved = cli_plugin
    else:
        # Priority 2: Environment variable (CWD-based)
        env_value = os.environ.get("KONKON_PLUGIN")
        if env_value is not None:
            resolved = Path(env_value).resolve()
        else:
            # Priority 3: config.toml (project-root-based)
            config = load_config(project_root)
            plugin_value = config.get("plugin")
            if plugin_value is not None:
                if not isinstance(plugin_value, str):
                    raise ValueError(
                        f"Invalid config: 'plugin' must be a string "
                        f"in .konkon/config.toml (got {type(plugin_value).__name__})"
                    )
                resolved = project_root / plugin_value
            else:
                # Priority 4: Fallback
                resolved = project_root / PLUGIN_FILE
    if require_plugin and not resolved.exists():
        raise FileNotFoundError(
            f"Plugin file not found: {resolved}"
        )
    return resolved


def _resolve_import_root(project_root: Path) -> Path | None:
    """Read import_root from config.toml and resolve to absolute Path.

    Returns None if not configured.
    Raises ConfigError if the configured value is invalid.
    """
    config = load_config(project_root)
    value = config.get("import_root")
    if value is None:
        return None
    if not isinstance(value, str):
        raise ConfigError(
            f"Invalid config: 'import_root' must be a string "
            f"in .konkon/config.toml (got {type(value).__name__})"
        )
    # Validate against the same rules as init-time (absolute path)
    if Path(value).is_absolute():
        raise ConfigError(
            f"Invalid config: 'import_root' must be a relative path "
            f"in .konkon/config.toml (got '{value}')."
        )
    resolved = project_root / value
    if not resolved.is_dir():
        raise ConfigError(
            f"import_root directory does not exist: {resolved}"
        )
    return resolved


def resolve_plugin_spec(
    project_root: Path,
    *,
    cli_plugin: Path | None = None,
    require_plugin: bool = True,
) -> tuple[Path, Path | None]:
    """Resolve plugin path and import_root together.

    Returns (plugin_path, import_root) tuple.

    When the plugin is resolved via CLI arg or env var (override),
    import_root is None — the override plugin uses its parent directory
    for sys.path (current behaviour).  import_root from config.toml is
    only used when the plugin itself comes from config/fallback.
    """
    # Priority 1 & 2: CLI / env override → import_root = None
    if cli_plugin is not None:
        plugin_path = resolve_plugin_path(project_root, cli_plugin=cli_plugin, require_plugin=require_plugin)
        return plugin_path, None

    env_value = os.environ.get("KONKON_PLUGIN")
    if env_value is not None:
        plugin_path = resolve_plugin_path(project_root, require_plugin=require_plugin)
        return plugin_path, None

    # Priority 3 & 4: config / fallback → also resolve import_root
    plugin_path = resolve_plugin_path(project_root, require_plugin=require_plugin)
    import_root = _resolve_import_root(project_root)
    return plugin_path, import_root


def raw_db_path(project_root: Path) -> Path:
    """Return the path to the Raw DB file under *project_root*/.konkon/."""
    return project_root / KONKON_DIR / RAW_DB_NAME


def json_db_path(project_root: Path) -> Path:
    """Return the path to the JSON DB file under *project_root*/.konkon/."""
    return project_root / KONKON_DIR / JSON_DB_NAME


def last_build_path(project_root: Path) -> Path:
    """Return the path to the last_build timestamp file."""
    return project_root / KONKON_DIR / LAST_BUILD_FILE


def _require_string(
    config: Mapping[str, Any],
    key: str,
    *,
    source: str,
    allow_empty: bool = False,
) -> str:
    value = config.get(key)
    if not isinstance(value, str):
        raise ConfigError(
            f"Invalid {source}: '{key}' must be a string "
            f"(got {type(value).__name__ if value is not None else 'NoneType'})."
        )
    if not allow_empty and value == "":
        raise ConfigError(f"Invalid {source}: '{key}' must not be empty.")
    return value


def _optional_string(
    config: Mapping[str, Any],
    key: str,
    *,
    source: str,
    allow_empty: bool = False,
) -> str | None:
    value = config.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ConfigError(
            f"Invalid {source}: '{key}' must be a string "
            f"(got {type(value).__name__})."
        )
    if not allow_empty and value == "":
        raise ConfigError(f"Invalid {source}: '{key}' must not be empty.")
    return value


def _normalize_backend(value: str, *, source: str) -> str:
    backend = value.lower()
    if backend not in _VALID_BACKENDS:
        allowed = ", ".join(sorted(repr(item) for item in _VALID_BACKENDS))
        raise ConfigError(
            f"Unknown backend: {backend!r}. Use one of {allowed} "
            f"({source})."
        )
    return backend


def _normalize_identifier(value: str, *, key: str, source: str) -> str:
    if not _IDENTIFIER_RE.match(value):
        raise ConfigError(
            f"Invalid {source}: '{key}' must be a simple SQL identifier "
            f"(got {value!r})."
        )
    return value


def _resolve_file_or_absolute_path(
    raw_path: str,
    *,
    base: Path | None,
    source: str,
    key: str,
) -> Path:
    candidate = Path(raw_path)
    if candidate.is_absolute():
        return candidate.resolve()
    if base is None:
        raise ConfigError(
            f"Invalid {source}: relative '{key}' requires 'config_base'."
        )
    return (base / candidate).resolve()


def _resolve_import_root_from_path(
    raw_path: str | None,
    *,
    base: Path | None,
    source: str,
) -> Path | None:
    if raw_path is None:
        return None
    resolved = _resolve_file_or_absolute_path(
        raw_path,
        base=base,
        source=source,
        key="import_root",
    )
    if not resolved.is_dir():
        raise ConfigError(f"import_root directory does not exist: {resolved}")
    return resolved


def _resolve_plugin_from_path(
    raw_path: str,
    *,
    base: Path | None,
    source: str,
) -> Path:
    resolved = _resolve_file_or_absolute_path(
        raw_path,
        base=base,
        source=source,
        key="plugin",
    )
    if not resolved.exists():
        raise FileNotFoundError(f"Plugin file not found: {resolved}")
    return resolved


def _postgres_config_from_mapping(
    config: Mapping[str, Any],
    *,
    source: str,
) -> dict[str, str | None]:
    dsn_env = _optional_string(config, "dsn_env", source=source)
    schema = _optional_string(config, "schema", source=source) or DEFAULT_POSTGRES_SCHEMA
    records_table = (
        _optional_string(config, "raw_records_table", source=source)
        or DEFAULT_POSTGRES_RAW_RECORDS_TABLE
    )
    deletions_table = (
        _optional_string(config, "raw_deletions_table", source=source)
        or DEFAULT_POSTGRES_RAW_DELETIONS_TABLE
    )
    build_state_table = (
        _optional_string(config, "build_state_table", source=source)
        or DEFAULT_POSTGRES_BUILD_STATE_TABLE
    )
    build_state_key = (
        _optional_string(config, "build_state_key", source=source)
        or DEFAULT_BUILD_STATE_KEY
    )
    return {
        "dsn_env": dsn_env,
        "schema": _normalize_identifier(schema, key="schema", source=source),
        "raw_records_table": _normalize_identifier(
            records_table, key="raw_records_table", source=source,
        ),
        "raw_deletions_table": _normalize_identifier(
            deletions_table, key="raw_deletions_table", source=source,
        ),
        "build_state_table": _normalize_identifier(
            build_state_table, key="build_state_table", source=source,
        ),
        "build_state_key": build_state_key,
    }


def load_project_runtime(project_root: Path, *, require_plugin: bool = True) -> RuntimeConfig:
    """Resolve project-mode runtime config from a project root."""
    backend, explicit = resolve_raw_backend(project_root)
    backend = _normalize_backend(backend, source=".konkon/config.toml or KONKON_RAW_BACKEND")
    plugin_path, import_root = resolve_plugin_spec(project_root, require_plugin=require_plugin)
    config = load_config(project_root)
    postgres = _postgres_config_from_mapping(
        config,
        source=".konkon/config.toml",
    )
    return RuntimeConfig(
        mode="project",
        project_root=project_root,
        config_path=config_path(project_root),
        config_base=project_root,
        raw_backend=backend,
        backend_explicit=explicit,
        plugin_path=plugin_path,
        import_root=import_root,
        dsn_env=postgres["dsn_env"],
        schema=str(postgres["schema"]),
        raw_records_table=str(postgres["raw_records_table"]),
        raw_deletions_table=str(postgres["raw_deletions_table"]),
        build_state_table=str(postgres["build_state_table"]),
        build_state_key=str(postgres["build_state_key"]),
    )


def load_runtime_config_file(path: Path, *, require_plugin: bool = True) -> RuntimeConfig:
    """Resolve stateless runtime config from a TOML file."""
    config = _load_toml_file(path)
    if "config_base" in config:
        raise ConfigError(
            "Invalid stateless config: 'config_base' is only allowed "
            "for in-memory config."
        )
    source = str(path)
    raw_backend = _normalize_backend(
        _require_string(config, "raw_backend", source=source),
        source=source,
    )
    base = path.parent.resolve()
    if require_plugin:
        plugin_path = _resolve_plugin_from_path(
            _require_string(config, "plugin", source=source),
            base=base,
            source=source,
        )
    else:
        raw_plugin = config.get("plugin")
        if raw_plugin is not None:
            plugin_path = _resolve_file_or_absolute_path(
                str(raw_plugin),
                base=base,
                source=source,
                key="plugin",
            )
        else:
            plugin_path = (base / PLUGIN_FILE)
    import_root = _resolve_import_root_from_path(
        _optional_string(config, "import_root", source=source),
        base=base,
        source=source,
    )
    postgres = _postgres_config_from_mapping(config, source=source)
    return RuntimeConfig(
        mode="stateless",
        raw_backend=raw_backend,
        backend_explicit=True,
        plugin_path=plugin_path,
        import_root=import_root,
        config_base=base,
        config_path=path.resolve(),
        dsn_env=postgres["dsn_env"],
        schema=str(postgres["schema"]),
        raw_records_table=str(postgres["raw_records_table"]),
        raw_deletions_table=str(postgres["raw_deletions_table"]),
        build_state_table=str(postgres["build_state_table"]),
        build_state_key=str(postgres["build_state_key"]),
    )


def load_runtime_config(config: Mapping[str, Any]) -> RuntimeConfig:
    """Resolve stateless runtime config from an in-memory mapping."""
    source = "in-memory config"
    raw_backend = _normalize_backend(
        _require_string(config, "raw_backend", source=source),
        source=source,
    )
    raw_base = config.get("config_base")
    base: Path | None
    if raw_base is None:
        base = None
    elif isinstance(raw_base, (str, Path)):
        base = Path(raw_base).resolve()
    else:
        raise ConfigError(
            f"Invalid {source}: 'config_base' must be a string or Path "
            f"(got {type(raw_base).__name__})."
        )

    raw_plugin = config.get("plugin")
    if not isinstance(raw_plugin, (str, Path)):
        raise ConfigError(
            f"Invalid {source}: 'plugin' must be a string or Path "
            f"(got {type(raw_plugin).__name__ if raw_plugin is not None else 'NoneType'})."
        )
    plugin_path = _resolve_plugin_from_path(
        str(raw_plugin),
        base=base,
        source=source,
    )

    raw_import_root = config.get("import_root")
    if raw_import_root is not None and not isinstance(raw_import_root, (str, Path)):
        raise ConfigError(
            f"Invalid {source}: 'import_root' must be a string or Path "
            f"(got {type(raw_import_root).__name__})."
        )
    import_root = _resolve_import_root_from_path(
        str(raw_import_root) if raw_import_root is not None else None,
        base=base,
        source=source,
    )
    postgres = _postgres_config_from_mapping(config, source=source)
    return RuntimeConfig(
        mode="stateless",
        raw_backend=raw_backend,
        backend_explicit=True,
        plugin_path=plugin_path,
        import_root=import_root,
        config_base=base or plugin_path.parent,
        dsn_env=postgres["dsn_env"],
        schema=str(postgres["schema"]),
        raw_records_table=str(postgres["raw_records_table"]),
        raw_deletions_table=str(postgres["raw_deletions_table"]),
        build_state_table=str(postgres["build_state_table"]),
        build_state_key=str(postgres["build_state_key"]),
    )


def resolve_runtime(
    *,
    project_dir: Path | None = None,
    config_file: Path | None = None,
    require_plugin: bool = True,
) -> RuntimeConfig:
    if project_dir is not None and config_file is not None:
        raise ConfigError(
            "'--config' and '--project-dir' cannot be used together."
        )
    if config_file is not None:
        return load_runtime_config_file(config_file.resolve(), require_plugin=require_plugin)
    start = project_dir.resolve() if project_dir is not None else None
    project_root = resolve_project(start)
    return load_project_runtime(project_root, require_plugin=require_plugin)


def _import_psycopg() -> Any:
    """Import psycopg lazily so sqlite/json usage does not require it."""
    try:
        import psycopg  # type: ignore
    except ModuleNotFoundError as exc:
        raise ConfigError(
            "Postgres backend requires the 'psycopg' package to be installed."
        ) from exc
    return psycopg


def resolve_postgres_dsn(
    runtime: RuntimeConfig,
    *,
    dsn: str | None = None,
) -> str:
    """Resolve a postgres DSN from explicit input or environment."""
    if dsn:
        return dsn
    if runtime.dsn_env:
        from_named_env = os.environ.get(runtime.dsn_env)
        if from_named_env:
            return from_named_env
    default_env = os.environ.get(DEFAULT_POSTGRES_DSN_ENV)
    if default_env:
        return default_env
    env_sources = [runtime.dsn_env] if runtime.dsn_env else []
    env_sources.append(DEFAULT_POSTGRES_DSN_ENV)
    joined = ", ".join(repr(item) for item in env_sources)
    raise ConfigError(
        "Postgres backend requires credentials. "
        f"Provide --raw-dsn / dsn, or set one of: {joined}."
    )


def create_postgres_connection_manager(
    runtime: RuntimeConfig,
    *,
    connection: Any | None = None,
    pool: Any | None = None,
    dsn: str | None = None,
) -> PostgresConnectionManager | None:
    """Create a postgres connection manager for a runtime when needed."""
    if runtime.raw_backend != "postgres":
        return None
    if connection is not None and pool is not None:
        raise ValueError("Specify either 'connection' or 'pool', not both.")
    if connection is not None:
        return PostgresConnectionManager(connection=connection)
    if pool is not None:
        return PostgresConnectionManager(pool=pool)
    resolved_dsn = resolve_postgres_dsn(runtime, dsn=dsn)
    psycopg = _import_psycopg()
    opened = psycopg.connect(resolved_dsn)
    return PostgresConnectionManager(connection=opened, owns_connection=True)
