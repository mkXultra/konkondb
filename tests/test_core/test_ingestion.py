"""Tests for core/ingestion/__init__.py — Ingestion Context facade.

Includes original facade tests and new backend selection tests
(json_backend_unified.md §10.4).
"""

import os
from pathlib import Path

import pytest

from konkon.core.ingestion import ingest, get_record, list_records
from konkon.core.instance import KONKON_DIR, init_project, save_config, load_config
from konkon.core.models import ConfigError, RawRecord


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


# ---- Backend selection tests (§10.4) ----


class TestBackendSelectionEnv:
    """Backend selection via KONKON_RAW_BACKEND env var."""

    def test_env_json_creates_json_file(self, tmp_path: Path, monkeypatch):
        """KONKON_RAW_BACKEND=json + ingest creates raw.json."""
        monkeypatch.setenv("KONKON_RAW_BACKEND", "json")
        init_project(tmp_path, force=False)
        ingest("hello", None, tmp_path)
        assert (tmp_path / KONKON_DIR / "raw.json").exists()
        assert not (tmp_path / KONKON_DIR / "raw.db").exists()

    def test_env_sqlite_creates_db_file(self, tmp_path: Path, monkeypatch):
        """KONKON_RAW_BACKEND=sqlite + ingest creates raw.db."""
        monkeypatch.setenv("KONKON_RAW_BACKEND", "sqlite")
        init_project(tmp_path, force=False)
        ingest("hello", None, tmp_path)
        assert (tmp_path / KONKON_DIR / "raw.db").exists()
        assert not (tmp_path / KONKON_DIR / "raw.json").exists()

    def test_env_overrides_config(self, tmp_path: Path, monkeypatch):
        """Environment variable takes priority over config.toml."""
        init_project(tmp_path, force=False, raw_backend="sqlite")
        monkeypatch.setenv("KONKON_RAW_BACKEND", "json")
        ingest("hello", None, tmp_path)
        assert (tmp_path / KONKON_DIR / "raw.json").exists()

    def test_env_unknown_backend_raises(self, tmp_path: Path, monkeypatch):
        """Unknown backend in env raises ConfigError."""
        monkeypatch.setenv("KONKON_RAW_BACKEND", "unknown")
        init_project(tmp_path, force=False)
        with pytest.raises(ConfigError, match="Unknown backend"):
            ingest("hello", None, tmp_path)


class TestBackendSelectionConfig:
    """Backend selection via config.toml."""

    def test_config_json_creates_json_file(self, tmp_path: Path):
        """raw_backend = 'json' in config.toml uses JSON backend."""
        init_project(tmp_path, force=False, raw_backend="json")
        ingest("hello", None, tmp_path)
        assert (tmp_path / KONKON_DIR / "raw.json").exists()

    def test_config_sqlite_creates_db_file(self, tmp_path: Path):
        """raw_backend = 'sqlite' in config.toml uses SQLite backend."""
        init_project(tmp_path, force=False, raw_backend="sqlite")
        ingest("hello", None, tmp_path)
        assert (tmp_path / KONKON_DIR / "raw.db").exists()

    def test_config_unknown_backend_raises(self, tmp_path: Path):
        """Unknown backend in config raises ConfigError."""
        init_project(tmp_path, force=False)
        existing = load_config(tmp_path)
        existing["raw_backend"] = "unknown"
        save_config(tmp_path, existing)
        with pytest.raises(ConfigError, match="Unknown backend"):
            ingest("hello", None, tmp_path)


class TestBackendAutoDetect:
    """Auto-detection when env/config are both unset."""

    def test_raw_json_only_selects_json(self, tmp_path: Path):
        """raw.json only → auto-detect selects json."""
        init_project(tmp_path, force=False)
        # Manually create raw.json
        json_path = tmp_path / KONKON_DIR / "raw.json"
        json_path.write_text('{"version": 2, "records": []}', encoding="utf-8")
        records = list_records(tmp_path)
        assert records == []  # works without error

    def test_raw_db_only_selects_sqlite(self, tmp_path: Path):
        """raw.db only → auto-detect selects sqlite."""
        init_project(tmp_path, force=False)
        ingest("hello", None, tmp_path)  # creates raw.db by default
        assert (tmp_path / KONKON_DIR / "raw.db").exists()
        record = get_record(tmp_path, "nonexistent")
        assert record is None  # works without error

    def test_neither_file_defaults_sqlite(self, tmp_path: Path):
        """No DB file → default to sqlite."""
        init_project(tmp_path, force=False)
        ingest("hello", None, tmp_path)
        assert (tmp_path / KONKON_DIR / "raw.db").exists()

    def test_both_files_raises(self, tmp_path: Path):
        """Both raw.db and raw.json exist → CONFIG_ERROR."""
        init_project(tmp_path, force=False)
        # Create both files
        (tmp_path / KONKON_DIR / "raw.db").write_bytes(b"")
        (tmp_path / KONKON_DIR / "raw.json").write_text("{}", encoding="utf-8")
        with pytest.raises(ConfigError, match="Both .konkon/raw.db and .konkon/raw.json"):
            ingest("hello", None, tmp_path)


class TestBackendConsistencyWarning:
    """Mismatch warnings between config and existing files."""

    def test_json_config_with_db_only_warns(self, tmp_path: Path, monkeypatch, capsys):
        """config='json' + raw.db only → stderr warning, raw.json created."""
        init_project(tmp_path, force=False)
        # Create raw.db
        (tmp_path / KONKON_DIR / "raw.db").write_bytes(b"placeholder")
        monkeypatch.setenv("KONKON_RAW_BACKEND", "json")
        ingest("hello", None, tmp_path)
        captured = capsys.readouterr()
        assert "WARN" in captured.err
        assert "raw.db exists but backend is 'json'" in captured.err
        assert (tmp_path / KONKON_DIR / "raw.json").exists()

    def test_sqlite_config_with_json_only_warns(self, tmp_path: Path, monkeypatch, capsys):
        """config='sqlite' + raw.json only → stderr warning, raw.db created."""
        init_project(tmp_path, force=False)
        (tmp_path / KONKON_DIR / "raw.json").write_text("{}", encoding="utf-8")
        monkeypatch.setenv("KONKON_RAW_BACKEND", "sqlite")
        ingest("hello", None, tmp_path)
        captured = capsys.readouterr()
        assert "WARN" in captured.err
        assert "raw.json exists but backend is 'sqlite'" in captured.err
        assert (tmp_path / KONKON_DIR / "raw.db").exists()


class TestInitRawBackendOption:
    """konkon init --raw-backend writes to config.toml."""

    def test_init_raw_backend_json(self, tmp_path: Path):
        init_project(tmp_path, force=False, raw_backend="json")
        config = load_config(tmp_path)
        assert config["raw_backend"] == "json"

    def test_init_raw_backend_sqlite(self, tmp_path: Path):
        init_project(tmp_path, force=False, raw_backend="sqlite")
        config = load_config(tmp_path)
        assert config["raw_backend"] == "sqlite"

    def test_init_no_raw_backend(self, tmp_path: Path):
        """Without --raw-backend, config.toml has no raw_backend key."""
        init_project(tmp_path, force=False)
        config = load_config(tmp_path)
        assert "raw_backend" not in config
