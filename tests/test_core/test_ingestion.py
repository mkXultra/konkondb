"""Tests for core/ingestion/__init__.py — Ingestion Context facade (Step 7)."""

from pathlib import Path

from konkon.core.ingestion import ingest
from konkon.core.instance import KONKON_DIR, init_project
from konkon.core.models import RawRecord


class TestIngest:
    """ingest(content, meta, project_root) — facade for data ingestion."""

    def test_returns_raw_record(self, tmp_path: Path):
        """ingest() returns a RawRecord."""
        init_project(tmp_path, force=False)
        record = ingest("hello", None, tmp_path)
        assert isinstance(record, RawRecord)

    def test_record_has_correct_content(self, tmp_path: Path):
        """Returned RawRecord has the content we passed in."""
        init_project(tmp_path, force=False)
        record = ingest("hello world", None, tmp_path)
        assert record.content == "hello world"

    def test_creates_raw_db_lazily(self, tmp_path: Path):
        """raw.db is created on first ingest, not by init."""
        init_project(tmp_path, force=False)
        assert not (tmp_path / KONKON_DIR / "raw.db").exists()
        ingest("hello", None, tmp_path)
        assert (tmp_path / KONKON_DIR / "raw.db").exists()

    def test_with_metadata(self, tmp_path: Path):
        """ingest() with meta dict stores it correctly."""
        init_project(tmp_path, force=False)
        record = ingest("hello", {"source": "test", "lang": "en"}, tmp_path)
        assert record.meta["source"] == "test"
        assert record.meta["lang"] == "en"

    def test_without_metadata(self, tmp_path: Path):
        """ingest() with meta=None works (empty meta)."""
        init_project(tmp_path, force=False)
        record = ingest("hello", None, tmp_path)
        assert record.meta == {}

    def test_record_has_id(self, tmp_path: Path):
        """Returned RawRecord has a UUID v7 id."""
        init_project(tmp_path, force=False)
        record = ingest("hello", None, tmp_path)
        assert record.id
        assert "-" in record.id  # UUID format
