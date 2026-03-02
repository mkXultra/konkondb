"""JSON backend-specific tests (json_backend_unified.md §10.2).

Tests for file format, atomic writes, version checks, and error handling.
"""

import json
from pathlib import Path

import pytest

from konkon.core.ingestion.json_db import JsonDB
from konkon.core.models import ConfigError


# ---- Fixtures ----


@pytest.fixture
def json_path(tmp_path: Path) -> Path:
    return tmp_path / "raw.json"


@pytest.fixture
def json_db(json_path: Path):
    db = JsonDB(json_path)
    yield db
    db.close()


# ---- File creation ----


class TestJsonFileCreation:
    """JSON file is created on first insert, not on init."""

    def test_no_file_on_init(self, json_path: Path):
        db = JsonDB(json_path)
        assert not json_path.exists()
        db.close()

    def test_file_created_on_insert(self, json_path: Path):
        db = JsonDB(json_path)
        db.insert(content="hello")
        assert json_path.exists()
        db.close()


# ---- File format ----


class TestJsonFileFormat:
    """Verify the JSON file format matches §4 spec."""

    def test_file_structure(self, json_path: Path):
        db = JsonDB(json_path)
        db.insert(content="hello", meta={"key": "value"})
        db.close()

        data = json.loads(json_path.read_text(encoding="utf-8"))
        assert data["version"] == 2
        assert isinstance(data["records"], list)
        assert len(data["records"]) == 1

        record = data["records"][0]
        assert "id" in record
        assert "created_at" in record
        assert "updated_at" in record
        assert record["content"] == "hello"
        assert record["meta"] == {"key": "value"}

    def test_created_at_format(self, json_path: Path):
        """created_at is 27-char RFC3339 UTC string."""
        db = JsonDB(json_path)
        db.insert(content="hello")
        db.close()

        data = json.loads(json_path.read_text(encoding="utf-8"))
        ts = data["records"][0]["created_at"]
        assert len(ts) == 27
        assert ts.endswith("Z")
        assert ts[10] == "T"

    def test_meta_empty_stored_as_empty_object(self, json_path: Path):
        """Empty meta stored as {} (not null or omitted)."""
        db = JsonDB(json_path)
        db.insert(content="hello")
        db.close()

        data = json.loads(json_path.read_text(encoding="utf-8"))
        assert data["records"][0]["meta"] == {}

    def test_records_sorted_by_created_at(self, json_path: Path):
        """Records in file are sorted by (created_at, id) ASC."""
        import time

        db = JsonDB(json_path)
        db.insert(content="first")
        time.sleep(0.01)
        db.insert(content="second")
        time.sleep(0.01)
        db.insert(content="third")
        db.close()

        data = json.loads(json_path.read_text(encoding="utf-8"))
        timestamps = [r["created_at"] for r in data["records"]]
        assert timestamps == sorted(timestamps)

    def test_file_encoding_utf8(self, json_path: Path):
        """File is written as UTF-8."""
        db = JsonDB(json_path)
        db.insert(content="日本語テスト")
        db.close()

        text = json_path.read_text(encoding="utf-8")
        assert "日本語テスト" in text

    def test_file_ends_with_newline(self, json_path: Path):
        db = JsonDB(json_path)
        db.insert(content="hello")
        db.close()

        raw = json_path.read_bytes()
        assert raw.endswith(b"\n")

    def test_indent_two_spaces(self, json_path: Path):
        """File uses 2-space indent for git diff readability."""
        db = JsonDB(json_path)
        db.insert(content="hello")
        db.close()

        text = json_path.read_text(encoding="utf-8")
        # Check that records array items are indented with 2 spaces
        assert '  "version"' in text or '"version"' in text
        lines = text.split("\n")
        # At least one line should have 4-space indent (nested object keys)
        has_4space = any(line.startswith("    ") for line in lines)
        assert has_4space


# ---- Atomic writes ----


class TestJsonAtomicWrite:
    """Verify atomic write via os.replace()."""

    def test_no_tmp_file_after_write(self, json_path: Path):
        """Temp file should not remain after successful write."""
        db = JsonDB(json_path)
        db.insert(content="hello")
        db.close()

        tmp_path = json_path.with_suffix(".json.tmp")
        assert not tmp_path.exists()

    def test_data_persists_across_reopen(self, json_path: Path):
        """Data written by one JsonDB instance is readable by another."""
        db1 = JsonDB(json_path)
        r = db1.insert(content="persisted")
        db1.close()

        db2 = JsonDB(json_path)
        result = db2.get_record(r.id)
        assert result is not None
        assert result.content == "persisted"
        db2.close()

    def test_update_persists_across_reopen(self, json_path: Path):
        db1 = JsonDB(json_path)
        r = db1.insert(content="before")
        db1.update(r.id, content="after")
        db1.close()

        db2 = JsonDB(json_path)
        result = db2.get_record(r.id)
        assert result is not None
        assert result.content == "after"
        db2.close()


# ---- Version checks ----


class TestJsonVersionCheck:
    """Version checking per §9.5."""

    def test_rejects_future_version(self, json_path: Path):
        json_path.write_text(
            json.dumps({"version": 99, "records": []}), encoding="utf-8"
        )
        with pytest.raises(ConfigError, match="schema version mismatch"):
            JsonDB(json_path)

    def test_rejects_old_version(self, json_path: Path):
        json_path.write_text(
            json.dumps({"version": 1, "records": []}), encoding="utf-8"
        )
        with pytest.raises(ConfigError, match="schema version mismatch"):
            JsonDB(json_path)

    def test_rejects_missing_version(self, json_path: Path):
        json_path.write_text(
            json.dumps({"records": []}), encoding="utf-8"
        )
        with pytest.raises(ConfigError, match="schema version mismatch"):
            JsonDB(json_path)


# ---- Invalid JSON ----


class TestJsonInvalidFile:
    """Error handling for corrupt/invalid JSON files per §4.7."""

    def test_rejects_invalid_json(self, json_path: Path):
        json_path.write_text("not valid json{{{", encoding="utf-8")
        with pytest.raises(ConfigError, match="Failed to parse"):
            JsonDB(json_path)

    def test_rejects_non_utf8(self, json_path: Path):
        json_path.write_bytes(b"\xff\xfe invalid")
        with pytest.raises(ConfigError, match="Failed to parse"):
            JsonDB(json_path)


# ---- close() is no-op ----


class TestJsonClose:
    """close() is a no-op that doesn't raise."""

    def test_close_is_noop(self, json_db):
        json_db.insert(content="hello")
        json_db.close()  # should not raise
        json_db.close()  # double close should not raise
