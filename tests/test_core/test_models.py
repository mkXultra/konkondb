"""Tests for core data models (02_interface_contracts.md)."""

from datetime import datetime, timezone

import pytest


class TestRawRecord:
    """RawRecord: frozen dataclass with meta-based properties."""

    def test_basic_creation(self):
        from konkon.types import RawRecord

        now = datetime.now(timezone.utc)
        record = RawRecord(id="r1", created_at=now, content="hello")
        assert record.id == "r1"
        assert record.created_at == now
        assert record.content == "hello"
        assert record.meta == {}

    def test_frozen(self):
        from konkon.types import RawRecord

        now = datetime.now(timezone.utc)
        record = RawRecord(id="r1", created_at=now, content="hello")
        with pytest.raises(AttributeError):
            record.id = "r2"  # type: ignore[misc]

    def test_source_uri_property(self):
        from konkon.types import RawRecord

        now = datetime.now(timezone.utc)
        record = RawRecord(
            id="r1", created_at=now, content="hello",
            meta={"source_uri": "file:///tmp/a.txt"},
        )
        assert record.source_uri == "file:///tmp/a.txt"

    def test_source_uri_none_when_missing(self):
        from konkon.types import RawRecord

        now = datetime.now(timezone.utc)
        record = RawRecord(id="r1", created_at=now, content="hello")
        assert record.source_uri is None

    def test_source_uri_none_when_non_string(self):
        from konkon.types import RawRecord

        now = datetime.now(timezone.utc)
        record = RawRecord(
            id="r1", created_at=now, content="hello",
            meta={"source_uri": 123},
        )
        assert record.source_uri is None

    def test_content_type_property(self):
        from konkon.types import RawRecord

        now = datetime.now(timezone.utc)
        record = RawRecord(
            id="r1", created_at=now, content="hello",
            meta={"content_type": "text/plain"},
        )
        assert record.content_type == "text/plain"

    def test_content_type_none_when_missing(self):
        from konkon.types import RawRecord

        now = datetime.now(timezone.utc)
        record = RawRecord(id="r1", created_at=now, content="hello")
        assert record.content_type is None


class TestQueryRequest:
    """QueryRequest: frozen dataclass with query + params."""

    def test_basic_creation(self):
        from konkon.types import QueryRequest

        req = QueryRequest(query="find something")
        assert req.query == "find something"
        assert req.params == {}

    def test_with_params(self):
        from konkon.types import QueryRequest

        req = QueryRequest(query="search", params={"limit": 10})
        assert req.params["limit"] == 10

    def test_frozen(self):
        from konkon.types import QueryRequest

        req = QueryRequest(query="test")
        with pytest.raises(AttributeError):
            req.query = "other"  # type: ignore[misc]


class TestQueryResult:
    """QueryResult: frozen dataclass with content + metadata."""

    def test_basic_creation(self):
        from konkon.types import QueryResult

        result = QueryResult(content="answer")
        assert result.content == "answer"
        assert result.metadata == {}

    def test_with_metadata(self):
        from konkon.types import QueryResult

        result = QueryResult(content="answer", metadata={"score": 0.95})
        assert result.metadata["score"] == 0.95


class TestDeletedRecord:
    """DeletedRecord: frozen dataclass with id + meta."""

    def test_basic_creation(self):
        from konkon.types import DeletedRecord

        rec = DeletedRecord(id="d1", meta={"source_uri": "file:///a.txt"})
        assert rec.id == "d1"
        assert rec.meta == {"source_uri": "file:///a.txt"}

    def test_frozen(self):
        from konkon.types import DeletedRecord

        rec = DeletedRecord(id="d1", meta={})
        with pytest.raises(AttributeError):
            rec.id = "d2"  # type: ignore[misc]

    def test_empty_meta(self):
        from konkon.types import DeletedRecord

        rec = DeletedRecord(id="d1", meta={})
        assert rec.meta == {}


class TestBuildContext:
    """BuildContext: frozen dataclass with mode + deleted_records."""

    def test_full_mode(self):
        from konkon.types import BuildContext

        ctx = BuildContext(mode="full")
        assert ctx.mode == "full"
        assert ctx.deleted_records == ()

    def test_incremental_mode_with_deleted(self):
        from konkon.types import BuildContext, DeletedRecord

        deleted = [DeletedRecord(id="d1", meta={"key": "val"})]
        ctx = BuildContext(mode="incremental", deleted_records=deleted)
        assert ctx.mode == "incremental"
        assert len(ctx.deleted_records) == 1
        assert ctx.deleted_records[0].id == "d1"

    def test_frozen(self):
        from konkon.types import BuildContext

        ctx = BuildContext(mode="full")
        with pytest.raises(AttributeError):
            ctx.mode = "incremental"  # type: ignore[misc]


class TestExceptions:
    """Exception hierarchy: KonkonError > BuildError, QueryError."""

    def test_konkon_error_is_exception(self):
        from konkon.types import KonkonError

        assert issubclass(KonkonError, Exception)

    def test_build_error_inherits(self):
        from konkon.types import BuildError, KonkonError

        assert issubclass(BuildError, KonkonError)
        with pytest.raises(KonkonError):
            raise BuildError("build failed")

    def test_query_error_inherits(self):
        from konkon.types import KonkonError, QueryError

        assert issubclass(QueryError, KonkonError)
        with pytest.raises(KonkonError):
            raise QueryError("query failed")
