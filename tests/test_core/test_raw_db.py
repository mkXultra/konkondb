"""Tests for Raw DB (03_data_model.md)."""

import json
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from konkon.core.ingestion.raw_db import RawDB


# ---- Fixtures ----


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "raw.db"


@pytest.fixture
def raw_db(db_path: Path):
    db = RawDB(db_path)
    yield db
    db.close()


# ---- DB Initialization ----


class TestRawDBInit:
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
                "INSERT INTO raw_records (id, created_at, content, meta) "
                "VALUES ('id1', '2026-01-01T00:00:00.000000Z', X'DEAD', NULL)"
            )
        conn.close()

    def test_check_empty_id_rejected(self, db_path: Path):
        """CHECK (id <> '') rejects empty string id."""
        db = RawDB(db_path)
        db.close()
        conn = sqlite3.connect(str(db_path))
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO raw_records (id, created_at, content, meta) "
                "VALUES ('', '2026-01-01T00:00:00.000000Z', 'x', NULL)"
            )
        conn.close()

    def test_check_invalid_meta_rejected(self, db_path: Path):
        """CHECK rejects non-object JSON in meta."""
        db = RawDB(db_path)
        db.close()
        conn = sqlite3.connect(str(db_path))
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO raw_records (id, created_at, content, meta) "
                """VALUES ('id1', '2026-01-01T00:00:00.000000Z', 'x', '"string"')"""
            )
        conn.close()

    def test_check_created_at_length_rejected(self, db_path: Path):
        """CHECK (length(created_at) = 27) rejects wrong-length timestamps."""
        db = RawDB(db_path)
        db.close()
        conn = sqlite3.connect(str(db_path))
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO raw_records (id, created_at, content, meta) "
                "VALUES ('id1', '2026-01-01T00:00:00Z', 'x', NULL)"
            )
        conn.close()


# ---- Insert ----


class TestRawDBInsert:
    """Insert records into raw_records."""

    def test_insert_returns_raw_record(self, raw_db: RawDB):
        from konkon.core.models import RawRecord

        record = raw_db.insert(content="hello")
        assert isinstance(record, RawRecord)

    def test_insert_generates_uuid_v7_id(self, raw_db: RawDB):
        record = raw_db.insert(content="hello")
        parts = record.id.split("-")
        assert len(parts) == 5
        assert len(parts[0]) == 8
        assert len(parts[1]) == 4
        assert len(parts[2]) == 4
        assert len(parts[3]) == 4
        assert len(parts[4]) == 12
        assert parts[2][0] == "7"  # version 7
        assert parts[3][0] in "89ab"  # variant

    def test_insert_created_at_is_utc_aware(self, raw_db: RawDB):
        record = raw_db.insert(content="hello")
        assert record.created_at.tzinfo is not None
        assert record.created_at.utcoffset() == timedelta(0)

    def test_insert_with_meta(self, raw_db: RawDB):
        record = raw_db.insert(
            content="hello", meta={"source_uri": "file:///a.txt"}
        )
        assert record.meta == {"source_uri": "file:///a.txt"}
        assert record.source_uri == "file:///a.txt"

    def test_insert_without_meta(self, raw_db: RawDB):
        record = raw_db.insert(content="hello")
        assert record.meta == {}

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


# ---- RawDataAccessor: __iter__ ----


class TestRawDataAccessorIter:
    """RawDataAccessor.__iter__: ORDER BY created_at ASC, id ASC."""

    def test_empty_db(self, raw_db: RawDB):
        accessor = raw_db.accessor()
        assert list(accessor) == []

    def test_returns_raw_records(self, raw_db: RawDB):
        from konkon.core.models import RawRecord

        raw_db.insert(content="hello")
        accessor = raw_db.accessor()
        records = list(accessor)
        assert len(records) == 1
        assert isinstance(records[0], RawRecord)

    def test_ordering(self, raw_db: RawDB):
        r1 = raw_db.insert(content="first")
        time.sleep(0.01)
        r2 = raw_db.insert(content="second")
        time.sleep(0.01)
        r3 = raw_db.insert(content="third")

        accessor = raw_db.accessor()
        records = list(accessor)
        assert [r.id for r in records] == [r1.id, r2.id, r3.id]

    def test_re_iterable(self, raw_db: RawDB):
        raw_db.insert(content="hello")
        accessor = raw_db.accessor()
        first = list(accessor)
        second = list(accessor)
        assert first == second

    def test_meta_null_to_empty_dict(self, raw_db: RawDB):
        """NULL meta in DB is surfaced as empty dict on RawRecord."""
        raw_db.insert(content="no meta")
        accessor = raw_db.accessor()
        record = list(accessor)[0]
        assert record.meta == {}


# ---- RawDataAccessor: __len__ ----


class TestRawDataAccessorLen:
    """RawDataAccessor.__len__."""

    def test_empty(self, raw_db: RawDB):
        accessor = raw_db.accessor()
        assert len(accessor) == 0

    def test_count(self, raw_db: RawDB):
        raw_db.insert(content="a")
        raw_db.insert(content="b")
        raw_db.insert(content="c")
        accessor = raw_db.accessor()
        assert len(accessor) == 3


# ---- RawDataAccessor: since() ----


class TestRawDataAccessorSince:
    """RawDataAccessor.since(): exclusive filter on created_at."""

    def test_since_excludes_exact_timestamp(self, raw_db: RawDB):
        r1 = raw_db.insert(content="first")
        time.sleep(0.01)
        r2 = raw_db.insert(content="second")

        accessor = raw_db.accessor()
        filtered = accessor.since(r1.created_at)
        records = list(filtered)
        ids = [r.id for r in records]
        assert r1.id not in ids
        assert r2.id in ids

    def test_since_len(self, raw_db: RawDB):
        r1 = raw_db.insert(content="first")
        time.sleep(0.01)
        raw_db.insert(content="second")
        time.sleep(0.01)
        raw_db.insert(content="third")

        accessor = raw_db.accessor()
        filtered = accessor.since(r1.created_at)
        assert len(filtered) == 2

    def test_since_empty_result(self, raw_db: RawDB):
        raw_db.insert(content="only")
        accessor = raw_db.accessor()
        future = datetime(2099, 1, 1, tzinfo=timezone.utc)
        filtered = accessor.since(future)
        assert list(filtered) == []
        assert len(filtered) == 0

    def test_since_preserves_ordering(self, raw_db: RawDB):
        r1 = raw_db.insert(content="first")
        time.sleep(0.01)
        r2 = raw_db.insert(content="second")
        time.sleep(0.01)
        r3 = raw_db.insert(content="third")

        accessor = raw_db.accessor()
        filtered = accessor.since(r1.created_at)
        records = list(filtered)
        assert [r.id for r in records] == [r2.id, r3.id]

    def test_since_chained(self, raw_db: RawDB):
        """since() returns a full accessor supporting further since()."""
        r1 = raw_db.insert(content="first")
        time.sleep(0.01)
        r2 = raw_db.insert(content="second")
        time.sleep(0.01)
        r3 = raw_db.insert(content="third")

        accessor = raw_db.accessor()
        filtered = accessor.since(r1.created_at).since(r2.created_at)
        records = list(filtered)
        assert len(records) == 1
        assert records[0].id == r3.id

    def test_since_rejects_naive_datetime(self, raw_db: RawDB):
        accessor = raw_db.accessor()
        naive = datetime(2026, 1, 1)
        with pytest.raises(ValueError):
            accessor.since(naive)

    def test_since_rejects_non_utc_datetime(self, raw_db: RawDB):
        accessor = raw_db.accessor()
        jst = timezone(timedelta(hours=9))
        non_utc = datetime(2026, 1, 1, tzinfo=jst)
        with pytest.raises(ValueError):
            accessor.since(non_utc)


# ---- Insert: updated_at ----


class TestRawDBInsertUpdatedAt:
    """Insert sets updated_at == created_at."""

    def test_insert_sets_updated_at(self, raw_db: RawDB):
        record = raw_db.insert(content="hello")
        assert record.updated_at is not None
        assert record.updated_at == record.created_at

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

    def test_accessor_returns_updated_at(self, raw_db: RawDB):
        raw_db.insert(content="hello")
        accessor = raw_db.accessor()
        record = list(accessor)[0]
        assert record.updated_at is not None
        assert record.updated_at == record.created_at


# ---- Update ----


class TestRawDBUpdate:
    """RawDB.update() — modify content and/or meta."""

    def test_update_content(self, raw_db: RawDB):
        record = raw_db.insert(content="original")
        updated = raw_db.update(record.id, content="modified")
        assert updated.content == "modified"
        assert updated.id == record.id
        assert updated.created_at == record.created_at

    def test_update_meta(self, raw_db: RawDB):
        record = raw_db.insert(content="hello", meta={"key": "old"})
        updated = raw_db.update(record.id, meta={"key": "new"})
        assert updated.meta == {"key": "new"}
        assert updated.content == "hello"

    def test_update_both(self, raw_db: RawDB):
        record = raw_db.insert(content="old", meta={"a": "1"})
        updated = raw_db.update(record.id, content="new", meta={"b": "2"})
        assert updated.content == "new"
        assert updated.meta == {"b": "2"}

    def test_update_sets_updated_at(self, raw_db: RawDB):
        record = raw_db.insert(content="original")
        time.sleep(0.01)
        updated = raw_db.update(record.id, content="modified")
        assert updated.updated_at is not None
        assert updated.updated_at > record.created_at

    def test_update_preserves_created_at(self, raw_db: RawDB):
        record = raw_db.insert(content="original")
        time.sleep(0.01)
        updated = raw_db.update(record.id, content="modified")
        assert updated.created_at == record.created_at

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

    def test_update_nonexistent_raises(self, raw_db: RawDB):
        with pytest.raises(KeyError, match="record not found"):
            raw_db.update("nonexistent-id", content="x")

    def test_update_no_args_raises(self, raw_db: RawDB):
        record = raw_db.insert(content="hello")
        with pytest.raises(ValueError, match="at least one"):
            raw_db.update(record.id)


# ---- RawDataAccessor: modified_since() ----


class TestRawDataAccessorModifiedSince:
    """modified_since() filters by updated_at for incremental builds."""

    def test_catches_updated_records(self, raw_db: RawDB):
        """modified_since catches records updated after the timestamp."""
        r1 = raw_db.insert(content="first")
        r2 = raw_db.insert(content="second")
        checkpoint = r2.created_at

        time.sleep(0.01)
        raw_db.update(r1.id, content="first-v2")

        accessor = raw_db.accessor().modified_since(checkpoint)
        records = list(accessor)
        ids = [r.id for r in records]
        assert r1.id in ids
        assert r2.id not in ids

    def test_catches_new_inserts(self, raw_db: RawDB):
        """modified_since catches records inserted after the timestamp."""
        r1 = raw_db.insert(content="first")
        checkpoint = r1.created_at

        time.sleep(0.01)
        r2 = raw_db.insert(content="second")

        accessor = raw_db.accessor().modified_since(checkpoint)
        records = list(accessor)
        assert len(records) == 1
        assert records[0].id == r2.id

    def test_modified_since_len(self, raw_db: RawDB):
        r1 = raw_db.insert(content="first")
        checkpoint = r1.created_at

        time.sleep(0.01)
        raw_db.insert(content="second")
        raw_db.update(r1.id, content="first-v2")

        accessor = raw_db.accessor().modified_since(checkpoint)
        assert len(accessor) == 2

    def test_modified_since_rejects_naive(self, raw_db: RawDB):
        accessor = raw_db.accessor()
        with pytest.raises(ValueError):
            accessor.modified_since(datetime(2026, 1, 1))


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
        """user_version > _CURRENT_VERSION raises RuntimeError."""
        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA user_version = 99")
        conn.close()

        with pytest.raises(RuntimeError, match="schema version mismatch"):
            RawDB(db_path)


# ---- list_records ----


class TestRawDBListRecords:
    """RawDB.list_records(limit) — return recent records newest first."""

    def test_empty_db(self, raw_db: RawDB):
        assert raw_db.list_records(10) == []

    def test_returns_records_newest_first(self, raw_db: RawDB):
        r1 = raw_db.insert(content="first")
        time.sleep(0.01)
        r2 = raw_db.insert(content="second")
        time.sleep(0.01)
        r3 = raw_db.insert(content="third")

        records = raw_db.list_records(10)
        assert [r.id for r in records] == [r3.id, r2.id, r1.id]

    def test_respects_limit(self, raw_db: RawDB):
        for i in range(5):
            raw_db.insert(content=f"record-{i}")
            time.sleep(0.01)

        records = raw_db.list_records(3)
        assert len(records) == 3

    def test_limit_larger_than_count(self, raw_db: RawDB):
        raw_db.insert(content="only")
        records = raw_db.list_records(100)
        assert len(records) == 1
