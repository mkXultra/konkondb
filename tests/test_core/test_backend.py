"""Backend-common tests (json_backend_unified.md §10.2).

These tests run against both SQLite and JSON backends via the
parametrized `raw_db` fixture in conftest.py.
"""

import time
from datetime import datetime, timedelta, timezone

import pytest

from konkon.core.models import RawRecord


# ---- Insert ----


class TestBackendInsert:
    """Insert records — backend-agnostic assertions."""

    def test_insert_returns_raw_record(self, raw_db):
        record = raw_db.insert(content="hello")
        assert isinstance(record, RawRecord)

    def test_insert_generates_uuid_v7_id(self, raw_db):
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

    def test_insert_created_at_is_utc_aware(self, raw_db):
        record = raw_db.insert(content="hello")
        assert record.created_at.tzinfo is not None
        assert record.created_at.utcoffset() == timedelta(0)

    def test_insert_with_meta(self, raw_db):
        record = raw_db.insert(
            content="hello", meta={"source_uri": "file:///a.txt"}
        )
        assert record.meta == {"source_uri": "file:///a.txt"}
        assert record.source_uri == "file:///a.txt"

    def test_insert_without_meta(self, raw_db):
        record = raw_db.insert(content="hello")
        assert record.meta == {}


# ---- Insert: updated_at ----


class TestBackendInsertUpdatedAt:
    """Insert sets updated_at == created_at."""

    def test_insert_sets_updated_at(self, raw_db):
        record = raw_db.insert(content="hello")
        assert record.updated_at is not None
        assert record.updated_at == record.created_at

    def test_accessor_returns_updated_at(self, raw_db):
        raw_db.insert(content="hello")
        accessor = raw_db.accessor()
        record = list(accessor)[0]
        assert record.updated_at is not None
        assert record.updated_at == record.created_at


# ---- RawDataAccessor: __iter__ ----


class TestBackendAccessorIter:
    """RawDataAccessor.__iter__: ORDER BY created_at ASC, id ASC."""

    def test_empty_db(self, raw_db):
        accessor = raw_db.accessor()
        assert list(accessor) == []

    def test_returns_raw_records(self, raw_db):
        raw_db.insert(content="hello")
        accessor = raw_db.accessor()
        records = list(accessor)
        assert len(records) == 1
        assert isinstance(records[0], RawRecord)

    def test_ordering(self, raw_db):
        r1 = raw_db.insert(content="first")
        time.sleep(0.01)
        r2 = raw_db.insert(content="second")
        time.sleep(0.01)
        r3 = raw_db.insert(content="third")

        accessor = raw_db.accessor()
        records = list(accessor)
        assert [r.id for r in records] == [r1.id, r2.id, r3.id]

    def test_ordering_tiebreak_by_id(self, raw_db):
        """Same created_at should be tie-broken by id ASC (§13.1).

        Inserts multiple records in rapid succession. Even if they share
        the same microsecond timestamp, iteration must return them sorted
        by (created_at ASC, id ASC).
        """
        records_in = []
        for i in range(5):
            records_in.append(raw_db.insert(content=f"item-{i}"))

        accessor = raw_db.accessor()
        records_out = list(accessor)
        ids_out = [r.id for r in records_out]
        # Within the same created_at bucket, ids must be ascending
        for i in range(len(records_out) - 1):
            a, b = records_out[i], records_out[i + 1]
            assert (a.created_at, a.id) <= (b.created_at, b.id)

    def test_re_iterable(self, raw_db):
        raw_db.insert(content="hello")
        accessor = raw_db.accessor()
        first = list(accessor)
        second = list(accessor)
        assert first == second

    def test_meta_null_to_empty_dict(self, raw_db):
        """NULL/empty meta is surfaced as empty dict on RawRecord."""
        raw_db.insert(content="no meta")
        accessor = raw_db.accessor()
        record = list(accessor)[0]
        assert record.meta == {}


# ---- RawDataAccessor: __len__ ----


class TestBackendAccessorLen:
    """RawDataAccessor.__len__."""

    def test_empty(self, raw_db):
        accessor = raw_db.accessor()
        assert len(accessor) == 0

    def test_count(self, raw_db):
        raw_db.insert(content="a")
        raw_db.insert(content="b")
        raw_db.insert(content="c")
        accessor = raw_db.accessor()
        assert len(accessor) == 3


# ---- RawDataAccessor: since() ----


class TestBackendAccessorSince:
    """RawDataAccessor.since(): exclusive filter on created_at."""

    def test_since_excludes_exact_timestamp(self, raw_db):
        r1 = raw_db.insert(content="first")
        time.sleep(0.01)
        r2 = raw_db.insert(content="second")

        accessor = raw_db.accessor()
        filtered = accessor.since(r1.created_at)
        records = list(filtered)
        ids = [r.id for r in records]
        assert r1.id not in ids
        assert r2.id in ids

    def test_since_len(self, raw_db):
        r1 = raw_db.insert(content="first")
        time.sleep(0.01)
        raw_db.insert(content="second")
        time.sleep(0.01)
        raw_db.insert(content="third")

        accessor = raw_db.accessor()
        filtered = accessor.since(r1.created_at)
        assert len(filtered) == 2

    def test_since_empty_result(self, raw_db):
        raw_db.insert(content="only")
        accessor = raw_db.accessor()
        future = datetime(2099, 1, 1, tzinfo=timezone.utc)
        filtered = accessor.since(future)
        assert list(filtered) == []
        assert len(filtered) == 0

    def test_since_preserves_ordering(self, raw_db):
        r1 = raw_db.insert(content="first")
        time.sleep(0.01)
        r2 = raw_db.insert(content="second")
        time.sleep(0.01)
        r3 = raw_db.insert(content="third")

        accessor = raw_db.accessor()
        filtered = accessor.since(r1.created_at)
        records = list(filtered)
        assert [r.id for r in records] == [r2.id, r3.id]

    def test_since_chained(self, raw_db):
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

    def test_since_rejects_naive_datetime(self, raw_db):
        accessor = raw_db.accessor()
        naive = datetime(2026, 1, 1)
        with pytest.raises(ValueError):
            accessor.since(naive)

    def test_since_rejects_non_utc_datetime(self, raw_db):
        accessor = raw_db.accessor()
        jst = timezone(timedelta(hours=9))
        non_utc = datetime(2026, 1, 1, tzinfo=jst)
        with pytest.raises(ValueError):
            accessor.since(non_utc)


# ---- Update ----


class TestBackendUpdate:
    """Backend.update() — modify content and/or meta."""

    def test_update_content(self, raw_db):
        record = raw_db.insert(content="original")
        updated = raw_db.update(record.id, content="modified")
        assert updated.content == "modified"
        assert updated.id == record.id
        assert updated.created_at == record.created_at

    def test_update_meta(self, raw_db):
        record = raw_db.insert(content="hello", meta={"key": "old"})
        updated = raw_db.update(record.id, meta={"key": "new"})
        assert updated.meta == {"key": "new"}
        assert updated.content == "hello"

    def test_update_both(self, raw_db):
        record = raw_db.insert(content="old", meta={"a": "1"})
        updated = raw_db.update(record.id, content="new", meta={"b": "2"})
        assert updated.content == "new"
        assert updated.meta == {"b": "2"}

    def test_update_sets_updated_at(self, raw_db):
        record = raw_db.insert(content="original")
        time.sleep(0.01)
        updated = raw_db.update(record.id, content="modified")
        assert updated.updated_at is not None
        assert updated.updated_at > record.created_at

    def test_update_preserves_created_at(self, raw_db):
        record = raw_db.insert(content="original")
        time.sleep(0.01)
        updated = raw_db.update(record.id, content="modified")
        assert updated.created_at == record.created_at

    def test_update_nonexistent_raises(self, raw_db):
        with pytest.raises(KeyError, match="record not found"):
            raw_db.update("nonexistent-id", content="x")

    def test_update_no_args_raises(self, raw_db):
        record = raw_db.insert(content="hello")
        with pytest.raises(ValueError, match="at least one"):
            raw_db.update(record.id)


# ---- RawDataAccessor: modified_since() ----


class TestBackendAccessorModifiedSince:
    """modified_since() filters by updated_at for incremental builds."""

    def test_catches_updated_records(self, raw_db):
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

    def test_catches_new_inserts(self, raw_db):
        """modified_since catches records inserted after the timestamp."""
        r1 = raw_db.insert(content="first")
        checkpoint = r1.created_at

        time.sleep(0.01)
        r2 = raw_db.insert(content="second")

        accessor = raw_db.accessor().modified_since(checkpoint)
        records = list(accessor)
        assert len(records) == 1
        assert records[0].id == r2.id

    def test_modified_since_len(self, raw_db):
        r1 = raw_db.insert(content="first")
        checkpoint = r1.created_at

        time.sleep(0.01)
        raw_db.insert(content="second")
        raw_db.update(r1.id, content="first-v2")

        accessor = raw_db.accessor().modified_since(checkpoint)
        assert len(accessor) == 2

    def test_modified_since_rejects_naive(self, raw_db):
        accessor = raw_db.accessor()
        with pytest.raises(ValueError):
            accessor.modified_since(datetime(2026, 1, 1))


# ---- get_record ----


class TestBackendGetRecord:
    """Backend.get_record(record_id) — retrieve a single record by ID."""

    def test_get_existing_record(self, raw_db):
        record = raw_db.insert(content="hello")
        result = raw_db.get_record(record.id)
        assert result is not None
        assert result.id == record.id
        assert result.content == "hello"

    def test_get_nonexistent_record(self, raw_db):
        result = raw_db.get_record("nonexistent-id")
        assert result is None

    def test_get_record_with_meta(self, raw_db):
        record = raw_db.insert(content="hello", meta={"key": "value"})
        result = raw_db.get_record(record.id)
        assert result is not None
        assert result.meta == {"key": "value"}

    def test_get_record_returns_updated_at(self, raw_db):
        record = raw_db.insert(content="hello")
        time.sleep(0.01)
        raw_db.update(record.id, content="updated")
        result = raw_db.get_record(record.id)
        assert result is not None
        assert result.content == "updated"
        assert result.updated_at > result.created_at


# ---- list_records ----


class TestBackendListRecords:
    """Backend.list_records(limit) — return recent records newest first."""

    def test_empty_db(self, raw_db):
        assert raw_db.list_records(10) == []

    def test_returns_records_newest_first(self, raw_db):
        r1 = raw_db.insert(content="first")
        time.sleep(0.01)
        r2 = raw_db.insert(content="second")
        time.sleep(0.01)
        r3 = raw_db.insert(content="third")

        records = raw_db.list_records(10)
        assert [r.id for r in records] == [r3.id, r2.id, r1.id]

    def test_respects_limit(self, raw_db):
        for i in range(5):
            raw_db.insert(content=f"record-{i}")
            time.sleep(0.01)

        records = raw_db.list_records(3)
        assert len(records) == 3

    def test_limit_larger_than_count(self, raw_db):
        raw_db.insert(content="only")
        records = raw_db.list_records(100)
        assert len(records) == 1


# ---- Delete ----


class TestBackendDelete:
    """Backend.delete() — physical delete + tombstone creation."""

    def test_delete_removes_record(self, raw_db):
        record = raw_db.insert(content="hello")
        raw_db.delete(record.id)
        assert raw_db.get_record(record.id) is None

    def test_delete_nonexistent_raises(self, raw_db):
        with pytest.raises(KeyError, match="record not found"):
            raw_db.delete("nonexistent-id")

    def test_delete_creates_tombstone(self, raw_db):
        record = raw_db.insert(content="hello", meta={"key": "val"})
        checkpoint = datetime(2000, 1, 1, tzinfo=timezone.utc)
        raw_db.delete(record.id)
        deleted = raw_db.get_deleted_records_since(checkpoint)
        assert len(deleted) == 1
        assert deleted[0].id == record.id
        assert deleted[0].meta == {"key": "val"}

    def test_delete_null_meta_coalesced(self, raw_db):
        """COALESCE(meta, '{}') ensures NULL meta becomes empty dict."""
        record = raw_db.insert(content="no meta")
        checkpoint = datetime(2000, 1, 1, tzinfo=timezone.utc)
        raw_db.delete(record.id)
        deleted = raw_db.get_deleted_records_since(checkpoint)
        assert len(deleted) == 1
        assert deleted[0].meta == {}

    def test_delete_reduces_accessor_count(self, raw_db):
        r1 = raw_db.insert(content="first")
        raw_db.insert(content="second")
        raw_db.delete(r1.id)
        assert len(raw_db.accessor()) == 1


# ---- get_deleted_records_since ----


class TestBackendGetDeletedRecordsSince:
    """Backend.get_deleted_records_since() — tombstone retrieval."""

    def test_empty_when_no_deletions(self, raw_db):
        raw_db.insert(content="hello")
        checkpoint = datetime(2000, 1, 1, tzinfo=timezone.utc)
        assert raw_db.get_deleted_records_since(checkpoint) == []

    def test_filters_by_timestamp(self, raw_db):
        r1 = raw_db.insert(content="first")
        time.sleep(0.01)
        checkpoint = datetime.now(timezone.utc)
        time.sleep(0.01)
        r2 = raw_db.insert(content="second")

        raw_db.delete(r1.id)
        time.sleep(0.01)
        raw_db.delete(r2.id)

        # Both deleted after checkpoint
        deleted = raw_db.get_deleted_records_since(checkpoint)
        ids = [d.id for d in deleted]
        assert r1.id in ids
        assert r2.id in ids

    def test_excludes_before_timestamp(self, raw_db):
        r1 = raw_db.insert(content="first")
        raw_db.delete(r1.id)
        time.sleep(0.01)

        checkpoint = datetime.now(timezone.utc)
        time.sleep(0.01)

        r2 = raw_db.insert(content="second")
        raw_db.delete(r2.id)

        deleted = raw_db.get_deleted_records_since(checkpoint)
        assert len(deleted) == 1
        assert deleted[0].id == r2.id


# ---- purge_tombstones ----


class TestBackendPurgeTombstones:
    """Backend.purge_tombstones() — tombstone cleanup."""

    def test_purge_removes_old_tombstones(self, raw_db):
        r1 = raw_db.insert(content="first")
        raw_db.delete(r1.id)
        time.sleep(0.01)

        cutoff = datetime.now(timezone.utc)
        time.sleep(0.01)

        r2 = raw_db.insert(content="second")
        raw_db.delete(r2.id)

        purged = raw_db.purge_tombstones(cutoff)
        assert purged == 1

        # Only r2's tombstone should remain
        early = datetime(2000, 1, 1, tzinfo=timezone.utc)
        remaining = raw_db.get_deleted_records_since(early)
        assert len(remaining) == 1
        assert remaining[0].id == r2.id

    def test_purge_returns_zero_when_empty(self, raw_db):
        cutoff = datetime.now(timezone.utc)
        assert raw_db.purge_tombstones(cutoff) == 0

    def test_purge_all(self, raw_db):
        r1 = raw_db.insert(content="first")
        raw_db.delete(r1.id)
        time.sleep(0.01)

        future = datetime(2099, 1, 1, tzinfo=timezone.utc)
        purged = raw_db.purge_tombstones(future)
        assert purged == 1

        early = datetime(2000, 1, 1, tzinfo=timezone.utc)
        assert raw_db.get_deleted_records_since(early) == []
