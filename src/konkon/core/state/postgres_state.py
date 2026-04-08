"""Postgres-backed build state store."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from konkon.core.ingestion.backend import validate_utc
from konkon.core.ingestion.postgres_db import (
    assert_postgres_setup,
    normalize_timestamp,
    qualified_table_name,
)
from konkon.core.instance import RuntimeConfig
from konkon.core.state.base import BuildStateSnapshot


class PostgresBuildStateStore:
    """Build checkpoint storage in postgres."""

    def __init__(
        self,
        runtime: RuntimeConfig,
        *,
        connection_manager: Any,
    ) -> None:
        self._runtime = runtime
        self._connection_manager = connection_manager
        self._state_ref = qualified_table_name(
            runtime.schema,
            runtime.build_state_table,
        )

    def read(self) -> BuildStateSnapshot:
        with self._connection_manager.acquire() as connection:
            assert_postgres_setup(
                connection,
                self._runtime,
                require_build_state=True,
            )
            row = connection.execute(
                f"""
                SELECT
                    build_state_key,
                    last_checkpoint,
                    last_build_at,
                    last_tombstone_at,
                    metadata::text
                FROM {self._state_ref}
                WHERE build_state_key = %s
                """,
                (self._runtime.build_state_key,),
            ).fetchone()
        if row is None:
            return BuildStateSnapshot(build_state_key=self._runtime.build_state_key)
        build_state_key, last_checkpoint, last_build_at, last_tombstone_at, metadata_text = row
        return BuildStateSnapshot(
            build_state_key=build_state_key,
            last_checkpoint=normalize_timestamp(last_checkpoint),
            last_build_at=normalize_timestamp(last_build_at),
            last_tombstone_at=normalize_timestamp(last_tombstone_at),
            metadata=json.loads(metadata_text) if metadata_text else {},
        )

    def write_success(
        self,
        *,
        build_started_at: datetime,
        completed_at: datetime,
    ) -> None:
        validate_utc(build_started_at)
        validate_utc(completed_at)
        with self._connection_manager.acquire() as connection:
            assert_postgres_setup(
                connection,
                self._runtime,
                require_build_state=True,
            )
            connection.execute(
                f"""
                INSERT INTO {self._state_ref}
                    (
                        build_state_key,
                        last_checkpoint,
                        last_build_at,
                        last_tombstone_at,
                        metadata,
                        updated_at
                    )
                VALUES (%s, %s, %s, %s, %s::jsonb, %s)
                ON CONFLICT (build_state_key) DO UPDATE SET
                    last_checkpoint = EXCLUDED.last_checkpoint,
                    last_build_at = EXCLUDED.last_build_at,
                    last_tombstone_at = EXCLUDED.last_tombstone_at,
                    metadata = EXCLUDED.metadata,
                    updated_at = EXCLUDED.updated_at
                """,
                (
                    self._runtime.build_state_key,
                    build_started_at,
                    completed_at,
                    build_started_at,
                    "{}",
                    completed_at,
                ),
            )
            connection.commit()
