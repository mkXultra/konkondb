"""Postgres-specific backend/state tests."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from konkon.core.ingestion.postgres_db import PostgresDB, setup_postgres_db
from konkon.core.instance import load_runtime_config
from konkon.core.models import ConfigError
from konkon.core.state.postgres_state import PostgresBuildStateStore
from tests.postgres_fakes import FakePostgresConnection


def _runtime(tmp_path: Path, *, build_state_key: str = "default"):
    plugin = tmp_path / "plugin.py"
    plugin.write_text("def schema(): return {}\ndef build(raw_data, context): pass\ndef query(request): return ''\n")
    return load_runtime_config(
        {
            "raw_backend": "postgres",
            "plugin": str(plugin.resolve()),
            "schema": "konkon",
            "build_state_key": build_state_key,
        }
    )


class _ConnectionManager:
    def __init__(self, connection):
        self._connection = connection

    def acquire(self):
        class _Ctx:
            def __init__(self, connection):
                self._connection = connection

            def __enter__(self):
                return self._connection

            def __exit__(self, exc_type, exc, tb):
                return False

        return _Ctx(self._connection)


class TestPostgresSetup:
    def test_setup_db_creates_schema_tables_and_commits(self, tmp_path: Path):
        runtime = _runtime(tmp_path)
        connection = FakePostgresConnection(schema="konkon")
        connection.schema_exists = False

        setup_postgres_db(connection, runtime)

        assert connection.schema_exists is True
        assert {"raw_records", "raw_deletions", "build_state"} <= connection.available_tables
        assert connection.commit_count == 1

    def test_backend_requires_existing_setup(self, tmp_path: Path):
        runtime = _runtime(tmp_path)
        connection = FakePostgresConnection(schema="konkon")

        with pytest.raises(ConfigError, match="Run 'konkon setup-db' first"):
            PostgresDB(connection, runtime)


class TestPostgresRawBackend:
    def test_crud_and_tombstones(self, tmp_path: Path):
        runtime = _runtime(tmp_path)
        connection = FakePostgresConnection(schema="konkon")
        connection.available_tables.update({"raw_records", "raw_deletions"})
        db = PostgresDB(connection, runtime)

        first = db.insert("first", {"source": "a"})
        second = db.insert("second", {"source": "b"})
        listed = db.list_records(10)
        assert [record.content for record in listed] == ["second", "first"]

        updated = db.update(first.id, content="first-updated")
        assert updated.content == "first-updated"
        fetched = db.get_record(first.id)
        assert fetched is not None
        assert fetched.content == "first-updated"

        db.delete(second.id)
        deleted = db.get_deleted_records_since(datetime(1970, 1, 1, tzinfo=timezone.utc))
        assert [item.id for item in deleted] == [second.id]
        assert connection.commit_count >= 4


class TestPostgresBuildState:
    def test_build_state_is_scoped_by_key(self, tmp_path: Path):
        runtime_a = _runtime(tmp_path, build_state_key="dataset-a")
        runtime_b = _runtime(tmp_path, build_state_key="dataset-b")
        connection = FakePostgresConnection(schema="konkon")
        connection.available_tables.update({"raw_records", "raw_deletions", "build_state"})
        manager = _ConnectionManager(connection)
        store_a = PostgresBuildStateStore(runtime_a, connection_manager=manager)
        store_b = PostgresBuildStateStore(runtime_b, connection_manager=manager)
        started = datetime.now(timezone.utc)
        completed = started + timedelta(seconds=5)

        store_a.write_success(build_started_at=started, completed_at=completed)
        snapshot_a = store_a.read()
        snapshot_b = store_b.read()

        assert snapshot_a.build_state_key == "dataset-a"
        assert snapshot_a.last_checkpoint == started
        assert snapshot_a.last_tombstone_at == started
        assert snapshot_b.last_checkpoint is None
