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
        assert version == 1

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
