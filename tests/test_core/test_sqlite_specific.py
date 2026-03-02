"""SQLite-specific tests (json_backend_unified.md §10.2).

Tests for DDL, PRAGMAs, CHECK constraints, migrations, and
SQLite storage format details.
"""

import json
import sqlite3
from pathlib import Path

import pytest

from konkon.core.ingestion.raw_db import RawDB
from konkon.core.models import ConfigError


# ---- Fixtures ----


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "raw.db"


@pytest.fixture
def sqlite_db(db_path: Path):
    db = RawDB(db_path)
    yield db
    db.close()


# ---- DB Initialization ----


class TestSqliteInit:
    """DB initialization: table, pragmas, index, schema version."""

    def test_creates_db_file(self, db_path: Path):
        db = RawDB(db_path)
        db.close()
        assert db_path.exists()

    def test_creates_raw_records_table(self, db_path: Path):
        db = RawDB(db_path)
        db.close()
        conn = sqlite3.connect(str(db_path))
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='raw_records'"
        ).fetchone()
        conn.close()
        assert row is not None

    def test_sets_wal_journal_mode(self, db_path: Path):
        db = RawDB(db_path)
        db.close()
        conn = sqlite3.connect(str(db_path))
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        conn.close()
        assert mode == "wal"

    def test_sets_user_version(self, db_path: Path):
        db = RawDB(db_path)
        db.close()
        conn = sqlite3.connect(str(db_path))
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        conn.close()
        assert version == 2

    def test_creates_index(self, db_path: Path):
        db = RawDB(db_path)
        db.close()
        conn = sqlite3.connect(str(db_path))
        row = conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='index' AND name='idx_raw_records_created_at_id'"
        ).fetchone()
        conn.close()
        assert row is not None

    def test_idempotent_init(self, db_path: Path):
        db1 = RawDB(db_path)
        db1.close()
        db2 = RawDB(db_path)  # must not raise
        db2.close()

    def test_strict_table(self, db_path: Path):
        """STRICT mode rejects BLOB in TEXT column."""
        db = RawDB(db_path)
        db.close()
        conn = sqlite3.connect(str(db_path))
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO raw_records (id, created_at, updated_at, content, meta) "
                "VALUES ('id1', '2026-01-01T00:00:00.000000Z', "
                "'2026-01-01T00:00:00.000000Z', X'DEAD', NULL)"
            )
        conn.close()

    def test_check_empty_id_rejected(self, db_path: Path):
        """CHECK (id <> '') rejects empty string id."""
        db = RawDB(db_path)
        db.close()
        conn = sqlite3.connect(str(db_path))
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO raw_records (id, created_at, updated_at, content, meta) "
                "VALUES ('', '2026-01-01T00:00:00.000000Z', "
                "'2026-01-01T00:00:00.000000Z', 'x', NULL)"
            )
        conn.close()

    def test_check_invalid_meta_rejected(self, db_path: Path):
        """CHECK rejects non-object JSON in meta."""
        db = RawDB(db_path)
        db.close()
        conn = sqlite3.connect(str(db_path))
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO raw_records (id, created_at, updated_at, content, meta) "
                "VALUES ('id1', '2026-01-01T00:00:00.000000Z', "
                """'2026-01-01T00:00:00.000000Z', 'x', '"string"')"""
            )
        conn.close()

    def test_check_created_at_length_rejected(self, db_path: Path):
        """CHECK (length(created_at) = 27) rejects wrong-length timestamps."""
        db = RawDB(db_path)
        db.close()
        conn = sqlite3.connect(str(db_path))
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO raw_records (id, created_at, updated_at, content, meta) "
                "VALUES ('id1', '2026-01-01T00:00:00Z', "
                "'2026-01-01T00:00:00.000000Z', 'x', NULL)"
            )
        conn.close()


# ---- SQLite storage format assertions ----


class TestSqliteStorageFormat:
    """Verify SQLite-specific storage format details."""

    def test_insert_persists_to_db(self, db_path: Path):
        db = RawDB(db_path)
        record = db.insert(content="persisted")
        db.close()

        conn = sqlite3.connect(str(db_path))
        row = conn.execute(
            "SELECT id, content FROM raw_records WHERE id = ?", (record.id,)
        ).fetchone()
        conn.close()
        assert row is not None
        assert row[1] == "persisted"

    def test_insert_created_at_format_in_db(self, db_path: Path):
        """created_at stored as 27-char RFC3339 UTC string ending with Z."""
        db = RawDB(db_path)
        record = db.insert(content="hello")
        db.close()

        conn = sqlite3.connect(str(db_path))
        row = conn.execute(
            "SELECT created_at FROM raw_records WHERE id = ?", (record.id,)
        ).fetchone()
        conn.close()
        ts = row[0]
        assert len(ts) == 27
        assert ts.endswith("Z")
        assert ts[4] == "-"
        assert ts[7] == "-"
        assert ts[10] == "T"
        assert ts[13] == ":"
        assert ts[16] == ":"
        assert ts[19] == "."

    def test_insert_meta_stored_as_json(self, db_path: Path):
        db = RawDB(db_path)
        db.insert(content="hello", meta={"key": "value"})
        db.close()

        conn = sqlite3.connect(str(db_path))
        row = conn.execute("SELECT meta FROM raw_records").fetchone()
        conn.close()
        assert json.loads(row[0]) == {"key": "value"}

    def test_insert_none_meta_stored_as_null(self, db_path: Path):
        """meta=None (default) is stored as NULL."""
        db = RawDB(db_path)
        db.insert(content="hello")
        db.close()

        conn = sqlite3.connect(str(db_path))
        row = conn.execute("SELECT meta FROM raw_records").fetchone()
        conn.close()
        assert row[0] is None

    def test_insert_empty_meta_stored_as_null(self, db_path: Path):
        """meta={} is normalized to NULL (03_data_model.md section 11.3)."""
        db = RawDB(db_path)
        db.insert(content="hello", meta={})
        db.close()

        conn = sqlite3.connect(str(db_path))
        row = conn.execute("SELECT meta FROM raw_records").fetchone()
        conn.close()
        assert row[0] is None

    def test_insert_updated_at_in_db(self, db_path: Path):
        """updated_at stored with same format as created_at."""
        db = RawDB(db_path)
        record = db.insert(content="hello")
        db.close()

        conn = sqlite3.connect(str(db_path))
        row = conn.execute(
            "SELECT updated_at FROM raw_records WHERE id = ?", (record.id,)
        ).fetchone()
        conn.close()
        ts = row[0]
        assert len(ts) == 27
        assert ts.endswith("Z")

    def test_update_persists(self, db_path: Path):
        db = RawDB(db_path)
        record = db.insert(content="before")
        db.update(record.id, content="after")
        db.close()

        conn = sqlite3.connect(str(db_path))
        row = conn.execute(
            "SELECT content FROM raw_records WHERE id = ?", (record.id,)
        ).fetchone()
        conn.close()
        assert row[0] == "after"


# ---- Migration v1 → v2 ----


class TestMigrationV1ToV2:
    """Schema migration from version 1 (no updated_at) to version 2."""

    def _create_v1_db(self, db_path: Path) -> None:
        """Create a v1 schema database directly."""
        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS raw_records (
                id          TEXT PRIMARY KEY COLLATE BINARY,
                created_at  TEXT NOT NULL,
                content     TEXT NOT NULL,
                meta        TEXT,
                CHECK (id <> ''),
                CHECK (meta IS NULL OR (json_valid(meta) AND json_type(meta) = 'object')),
                CHECK (length(created_at) = 27),
                CHECK (substr(created_at, 5, 1)  = '-'),
                CHECK (substr(created_at, 8, 1)  = '-'),
                CHECK (substr(created_at, 11, 1) = 'T'),
                CHECK (substr(created_at, 14, 1) = ':'),
                CHECK (substr(created_at, 17, 1) = ':'),
                CHECK (substr(created_at, 20, 1) = '.'),
                CHECK (substr(created_at, 27, 1) = 'Z')
            ) STRICT;
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_raw_records_created_at_id
                ON raw_records (created_at ASC, id ASC);
        """)
        conn.execute("PRAGMA user_version = 1")
        # Insert a test record
        conn.execute(
            "INSERT INTO raw_records (id, created_at, content, meta) "
            "VALUES (?, ?, ?, ?)",
            ("test-id", "2026-01-01T00:00:00.000000Z", "hello", None),
        )
        conn.commit()
        conn.close()

    def test_migration_preserves_data(self, db_path: Path):
        self._create_v1_db(db_path)
        db = RawDB(db_path)  # triggers migration
        accessor = db.accessor()
        records = list(accessor)
        assert len(records) == 1
        assert records[0].content == "hello"
        assert records[0].id == "test-id"
        db.close()

    def test_migration_sets_updated_at_from_created_at(self, db_path: Path):
        self._create_v1_db(db_path)
        db = RawDB(db_path)
        accessor = db.accessor()
        record = list(accessor)[0]
        assert record.updated_at == record.created_at
        db.close()

    def test_migration_bumps_version(self, db_path: Path):
        self._create_v1_db(db_path)
        db = RawDB(db_path)
        db.close()
        conn = sqlite3.connect(str(db_path))
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        conn.close()
        assert version == 2


# ---- Unknown schema version ----


class TestUnknownSchemaVersion:
    """RawDB rejects databases with unknown (future) schema versions."""

    def test_rejects_future_version(self, db_path: Path):
        """user_version > _CURRENT_VERSION raises ConfigError."""
        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA user_version = 99")
        conn.close()

        with pytest.raises(ConfigError, match="schema version mismatch"):
            RawDB(db_path)
