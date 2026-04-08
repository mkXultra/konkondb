"""Build state abstraction."""

from __future__ import annotations

from konkon.core.instance import RuntimeConfig, last_build_path
from konkon.core.models import ConfigError
from konkon.core.state.base import BuildStateSnapshot, BuildStateStore


from konkon.core.state.local_state import LocalBuildStateStore
from konkon.core.state.postgres_state import PostgresBuildStateStore


def create_build_state_store(
    runtime: RuntimeConfig,
    *,
    connection_manager: object | None = None,
) -> BuildStateStore:
    """Create the correct build state store for a runtime."""
    if runtime.raw_backend == "postgres":
        if connection_manager is None:
            raise ConfigError(
                "Postgres build state requires an active connection manager."
            )
        return PostgresBuildStateStore(
            runtime,
            connection_manager=connection_manager,
        )
    if runtime.project_root is None:
        raise ConfigError(
            "Stateless mode currently requires the postgres backend."
        )
    return LocalBuildStateStore(
        last_build_path(runtime.project_root),
        build_state_key=runtime.build_state_key,
    )
