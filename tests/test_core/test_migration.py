"""Tests for core/ingestion/migration.py — Raw DB backend migration.

Covers:
- SQLite → JSON and JSON → SQLite migration
- Field preservation (id, created_at, updated_at, content, meta)
- Order preservation
- Edge cases (empty DB, empty meta, nested meta, large content)
- Validation errors (same backend, source not found, target exists)
"""

import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from konkon.core.ingestion import migrate
from konkon.core.ingestion.json_db import JsonDB
from konkon.core.ingestion.raw_db import RawDB
from konkon.core.instance import init_project, save_config
from konkon.core.models import ConfigError, RawRecord


def assert_records_equal(
    source_records: list[RawRecord],
    target_records: list[RawRecord],
) -> None:
    """Assert all fields match between source and target records."""
    assert len(source_records) == len(target_records)
    for s, t in zip(source_records, target_records):
        assert s.id == t.id
        assert s.created_at == t.created_at
        assert s.updated_at == t.updated_at
        assert s.content == t.content
        assert dict(s.meta) == dict(t.meta)


def _setup_sqlite_project(tmp_path: Path) -> Path:
    """Initialize a project with sqlite backend and insert test data."""
    init_project(tmp_path)
    save_config(tmp_path, {"raw_backend": "sqlite"})
    return tmp_path


def _setup_json_project(tmp_path: Path) -> Path:
    """Initialize a project with json backend and insert test data."""
    init_project(tmp_path)
    save_config(tmp_path, {"raw_backend": "json"})
    return tmp_path


def _insert_records(db_path: Path, backend: str, records_data: list[dict]) -> list[RawRecord]:
    """Insert records into the given backend and return them."""
    if backend == "sqlite":
        db = RawDB(db_path)
    else:
        db = JsonDB(db_path)
    results = []
    for data in records_data:
        r = db.insert(data["content"], data.get("meta"))
        results.append(r)
        time.sleep(0.001)  # Ensure distinct timestamps
    db.close()
    return results


class TestMigrateSqliteToJson:
    """SQLite → JSON migration."""

    def test_migrate_sqlite_to_json(self, tmp_path: Path):
        """SQLite → JSON. All fields preserved."""
        project = _setup_sqlite_project(tmp_path)
        records = _insert_records(
            tmp_path / ".konkon" / "raw.db", "sqlite",
            [
                {"content": "hello", "meta": {"key": "value"}},
                {"content": "world", "meta": {"num": 42}},
            ],
        )

        count, source = migrate(project, "json", force=False)

        assert count == 2
        assert source == "sqlite"

        # Read back from JSON
        json_db = JsonDB(tmp_path / ".konkon" / "raw.json")
        target_records = list(json_db.accessor())
        json_db.close()

        assert_records_equal(records, target_records)


class TestMigrateJsonToSqlite:
    """JSON → SQLite migration."""

    def test_migrate_json_to_sqlite(self, tmp_path: Path):
        """JSON → SQLite. All fields preserved."""
        project = _setup_json_project(tmp_path)
        records = _insert_records(
            tmp_path / ".konkon" / "raw.json", "json",
            [
                {"content": "foo", "meta": {"a": "b"}},
                {"content": "bar", "meta": {"c": "d"}},
            ],
        )

        count, source = migrate(project, "sqlite", force=False)

        assert count == 2
        assert source == "json"

        # Read back from SQLite
        sqlite_db = RawDB(tmp_path / ".konkon" / "raw.db")
        target_records = list(sqlite_db.accessor())
        sqlite_db.close()

        assert_records_equal(records, target_records)


class TestFieldPreservation:
    """Detailed field preservation tests."""

    def test_migrate_preserves_id(self, tmp_path: Path):
        """Migrated records have identical IDs."""
        project = _setup_sqlite_project(tmp_path)
        records = _insert_records(
            tmp_path / ".konkon" / "raw.db", "sqlite",
            [{"content": "test"}],
        )

        migrate(project, "json")

        json_db = JsonDB(tmp_path / ".konkon" / "raw.json")
        target = list(json_db.accessor())
        json_db.close()

        assert target[0].id == records[0].id

    def test_migrate_preserves_timestamps(self, tmp_path: Path):
        """created_at and updated_at are fully preserved."""
        project = _setup_sqlite_project(tmp_path)
        db = RawDB(tmp_path / ".konkon" / "raw.db")
        original = db.insert("test", None)
        # Update to make updated_at differ from created_at
        time.sleep(0.01)
        updated = db.update(original.id, content="updated")
        db.close()

        migrate(project, "json")

        json_db = JsonDB(tmp_path / ".konkon" / "raw.json")
        target = list(json_db.accessor())
        json_db.close()

        assert target[0].created_at == updated.created_at
        assert target[0].updated_at == updated.updated_at
        assert target[0].created_at != target[0].updated_at

    def test_migrate_preserves_order(self, tmp_path: Path):
        """Migrated records maintain (created_at, id) ASC order."""
        project = _setup_sqlite_project(tmp_path)
        records = _insert_records(
            tmp_path / ".konkon" / "raw.db", "sqlite",
            [{"content": f"item-{i}"} for i in range(5)],
        )

        migrate(project, "json")

        json_db = JsonDB(tmp_path / ".konkon" / "raw.json")
        target = list(json_db.accessor())
        json_db.close()

        for i in range(len(target) - 1):
            assert (target[i].created_at, target[i].id) <= (target[i + 1].created_at, target[i + 1].id)


class TestEdgeCases:
    """Edge case tests."""

    def test_migrate_empty_db(self, tmp_path: Path):
        """0 records migrate. Normal exit, count=0."""
        project = _setup_sqlite_project(tmp_path)
        # Create empty SQLite DB
        db = RawDB(tmp_path / ".konkon" / "raw.db")
        db.close()

        count, source = migrate(project, "json")

        assert count == 0
        assert source == "sqlite"

    def test_migrate_meta_empty(self, tmp_path: Path):
        """Record with empty meta {} migrates correctly."""
        project = _setup_sqlite_project(tmp_path)
        _insert_records(
            tmp_path / ".konkon" / "raw.db", "sqlite",
            [{"content": "no-meta"}],
        )

        migrate(project, "json")

        json_db = JsonDB(tmp_path / ".konkon" / "raw.json")
        target = list(json_db.accessor())
        json_db.close()

        assert dict(target[0].meta) == {}

    def test_migrate_meta_nested(self, tmp_path: Path):
        """Nested meta JSON is preserved."""
        project = _setup_sqlite_project(tmp_path)
        nested_meta = {"tags": ["a", "b"], "nested": {"deep": True, "list": [1, 2, 3]}}
        _insert_records(
            tmp_path / ".konkon" / "raw.db", "sqlite",
            [{"content": "nested", "meta": nested_meta}],
        )

        migrate(project, "json")

        json_db = JsonDB(tmp_path / ".konkon" / "raw.json")
        target = list(json_db.accessor())
        json_db.close()

        assert dict(target[0].meta) == nested_meta

    def test_migrate_large_content(self, tmp_path: Path):
        """Large content string is fully preserved."""
        project = _setup_sqlite_project(tmp_path)
        large_content = "x" * 100_000
        _insert_records(
            tmp_path / ".konkon" / "raw.db", "sqlite",
            [{"content": large_content}],
        )

        migrate(project, "json")

        json_db = JsonDB(tmp_path / ".konkon" / "raw.json")
        target = list(json_db.accessor())
        json_db.close()

        assert target[0].content == large_content


class TestValidation:
    """Validation and error handling tests."""

    def test_migrate_same_backend_error(self, tmp_path: Path):
        """Same backend → ConfigError."""
        project = _setup_sqlite_project(tmp_path)
        db = RawDB(tmp_path / ".konkon" / "raw.db")
        db.close()

        with pytest.raises(ConfigError, match="Already using"):
            migrate(project, "sqlite")

    def test_migrate_source_not_found(self, tmp_path: Path):
        """Source DB file missing → ConfigError."""
        project = _setup_sqlite_project(tmp_path)
        # Don't create the actual DB file

        with pytest.raises(ConfigError, match="does not exist"):
            migrate(project, "json")

    def test_migrate_target_exists_no_force(self, tmp_path: Path):
        """Target file exists without --force → FileExistsError."""
        project = _setup_sqlite_project(tmp_path)
        db = RawDB(tmp_path / ".konkon" / "raw.db")
        db.insert("test")
        db.close()

        # Create target file
        (tmp_path / ".konkon" / "raw.json").write_text("{}")

        with pytest.raises(FileExistsError, match="already exists"):
            migrate(project, "json", force=False)

    def test_migrate_target_exists_force(self, tmp_path: Path):
        """Target file exists with --force → success (overwrite)."""
        project = _setup_sqlite_project(tmp_path)
        db = RawDB(tmp_path / ".konkon" / "raw.db")
        db.insert("test")
        db.close()

        # Create target file
        (tmp_path / ".konkon" / "raw.json").write_text("{}")

        count, source = migrate(project, "json", force=True)
        assert count == 1
        assert source == "sqlite"

    def test_migrate_force_emits_warn(self, tmp_path: Path, capsys):
        """--force emits WARN to stderr when removing existing target."""
        project = _setup_sqlite_project(tmp_path)
        db = RawDB(tmp_path / ".konkon" / "raw.db")
        db.insert("test")
        db.close()

        # Create target file
        (tmp_path / ".konkon" / "raw.json").write_text("{}")

        migrate(project, "json", force=True)

        captured = capsys.readouterr()
        assert "[WARN] Removing existing .konkon/raw.json" in captured.err

    def test_migrate_source_file_preserved(self, tmp_path: Path):
        """Source file is NOT deleted after migration."""
        project = _setup_sqlite_project(tmp_path)
        db = RawDB(tmp_path / ".konkon" / "raw.db")
        db.insert("preserve-me")
        db.close()

        migrate(project, "json")

        assert (tmp_path / ".konkon" / "raw.db").exists()
