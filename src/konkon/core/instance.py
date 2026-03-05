"""Project resolution — System-level (no Bounded Context).

Responsibilities:
- Resolve project root (find .konkon/ directory)
- Provide paths to project resources (.konkon/raw.db, konkon.py)
- Lazy Raw DB initialization (create on first insert, not on init)

References:
- commands/init.md (init creates .konkon/ but NOT the DB)
- commands/insert.md (insert lazily creates DB)

Used by:
- cli/init.py — create .konkon/ and konkon.py template
- cli/insert.py — open/create Raw DB, delegate to core/raw_db.py
- cli/build.py — open Raw DB (read), delegate to core/plugin_host.py
- cli/search.py — delegate to core/plugin_host.py
- serving/api.py — same as cli but via HTTP
- serving/mcp.py — same as cli but via MCP
"""

import os
import sys
import tomllib
from pathlib import Path
from typing import Any

KONKON_DIR = ".konkon"
RAW_DB_NAME = "raw.db"
JSON_DB_NAME = "raw.json"
PLUGIN_FILE = "konkon.py"
LAST_BUILD_FILE = "last_build"
CONFIG_FILE = "config.toml"

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


def load_config(project_root: Path) -> dict[str, Any]:
    """Load .konkon/config.toml and return the raw dict.

    Returns empty dict if file does not exist.
    Raises TOMLDecodeError on parse failure.
    """
    cfg = config_path(project_root)
    if not cfg.exists():
        return {}
    with open(cfg, "rb") as f:
        return tomllib.load(f)


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
    if ".." in Path(plugin).parts:
        raise ValueError(
            f"--plugin path must be within the project directory (got '{plugin}')."
        )
    if "'" in plugin:
        raise ValueError(
            f"--plugin path must not contain single quotes (got '{plugin}')."
        )


def init_project(
    directory: Path,
    *,
    force: bool = False,
    plugin: str | None = None,
    raw_backend: str | None = None,
) -> None:
    """Create a konkon project in *directory*.

    Creates .konkon/ (idempotent) and plugin template.
    Raises FileExistsError if plugin file already exists and force is False.
    Does NOT create Raw DB (lazy init on first insert).

    If plugin is specified, generates template at directory/plugin
    and writes plugin path to .konkon/config.toml.

    If raw_backend is specified ('sqlite' or 'json'), writes it to
    .konkon/config.toml.
    """
    if plugin is not None:
        _validate_plugin_arg(plugin)

    directory.mkdir(parents=True, exist_ok=True)

    if plugin is not None:
        plugin_path = directory / plugin
    else:
        plugin_path = directory / PLUGIN_FILE

    if plugin_path.exists() and not force:
        raise FileExistsError(f"{plugin_path} already exists. Use --force to overwrite.")

    # H2: Prevent symlink-based path traversal — check BEFORE creating directories
    # so that a rejected path doesn't leave side-effects (e.g. dirs created outside project).
    resolved_dir = directory.resolve()
    if plugin is not None:
        # Resolve the plugin path relative to the resolved directory to detect symlinks.
        # For existing symlinked parents, resolve() follows them; for non-existent paths,
        # resolve the existing prefix and append the remaining parts.
        resolved_plugin = (resolved_dir / plugin).resolve()
        if not str(resolved_plugin).startswith(str(resolved_dir) + os.sep):
            raise ValueError(
                f"--plugin path resolves outside the project directory "
                f"(resolved to '{resolved_plugin}')."
            )

    (directory / KONKON_DIR).mkdir(exist_ok=True)
    plugin_path.parent.mkdir(parents=True, exist_ok=True)
    plugin_path.write_text(PLUGIN_TEMPLATE)

    needs_config = plugin is not None or raw_backend is not None
    if needs_config:
        existing = load_config(directory)
        if plugin is not None:
            existing["plugin"] = plugin
        if raw_backend is not None:
            existing["raw_backend"] = raw_backend
        save_config(directory, existing)


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
) -> Path:
    """Resolve the plugin file path.

    Priority: CLI arg > KONKON_PLUGIN env > config.toml > fallback (konkon.py).

    Raises:
        FileNotFoundError: resolved path does not exist.
        ValueError: config.toml 'plugin' value is not a string.

    NOTE: 設計書 v5 では ConfigError を規定しているが、現時点では独自例外クラスの
    導入を見送り ValueError で代用している。将来 build/search/serve の配線時に
    ConfigError を導入する可能性がある。
    """
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

    if not resolved.exists():
        raise FileNotFoundError(
            f"Plugin file not found: {resolved}"
        )
    return resolved


def raw_db_path(project_root: Path) -> Path:
    """Return the path to the Raw DB file under *project_root*/.konkon/."""
    return project_root / KONKON_DIR / RAW_DB_NAME


def json_db_path(project_root: Path) -> Path:
    """Return the path to the JSON DB file under *project_root*/.konkon/."""
    return project_root / KONKON_DIR / JSON_DB_NAME


def last_build_path(project_root: Path) -> Path:
    """Return the path to the last_build timestamp file."""
    return project_root / KONKON_DIR / LAST_BUILD_FILE
