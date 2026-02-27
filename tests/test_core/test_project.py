"""Tests for core/instance.py — init_project (Step 6)."""

from pathlib import Path

import pytest

from konkon.core.instance import KONKON_DIR, PLUGIN_FILE, init_project


class TestInitProject:
    """init_project(directory, force) — system-level project initialization."""

    def test_creates_konkon_dir(self, tmp_path: Path):
        """init_project creates .konkon/ directory."""
        init_project(tmp_path, force=False)
        assert (tmp_path / KONKON_DIR).is_dir()

    def test_creates_konkon_py(self, tmp_path: Path):
        """init_project creates konkon.py with plugin template."""
        init_project(tmp_path, force=False)
        plugin = tmp_path / PLUGIN_FILE
        assert plugin.is_file()
        content = plugin.read_text()
        assert "def build(" in content
        assert "def query(" in content

    def test_template_imports_types(self, tmp_path: Path):
        """konkon.py template imports from konkon.types."""
        init_project(tmp_path, force=False)
        content = (tmp_path / PLUGIN_FILE).read_text()
        assert "from konkon.types import" in content
        assert "RawDataAccessor" in content
        assert "QueryRequest" in content
        assert "QueryResult" in content

    def test_existing_konkon_py_raises_error(self, tmp_path: Path):
        """init_project raises FileExistsError when konkon.py already exists."""
        (tmp_path / PLUGIN_FILE).write_text("existing")
        with pytest.raises(FileExistsError):
            init_project(tmp_path, force=False)

    def test_force_overwrites_konkon_py(self, tmp_path: Path):
        """init_project with force=True overwrites existing konkon.py."""
        (tmp_path / PLUGIN_FILE).write_text("old content")
        init_project(tmp_path, force=True)
        content = (tmp_path / PLUGIN_FILE).read_text()
        assert "def build(" in content
        assert "old content" not in content

    def test_konkon_dir_idempotent(self, tmp_path: Path):
        """.konkon/ already exists — no error, directory preserved."""
        (tmp_path / KONKON_DIR).mkdir()
        (tmp_path / KONKON_DIR / "some_file").write_text("keep me")
        init_project(tmp_path, force=False)
        assert (tmp_path / KONKON_DIR / "some_file").read_text() == "keep me"

    def test_does_not_create_raw_db(self, tmp_path: Path):
        """Lazy init: raw.db must NOT be created during init."""
        init_project(tmp_path, force=False)
        assert not (tmp_path / KONKON_DIR / "raw.db").exists()

    def test_creates_directory_if_not_exists(self, tmp_path: Path):
        """DIRECTORY argument that doesn't exist yet is created."""
        target = tmp_path / "new_project"
        init_project(target, force=False)
        assert target.is_dir()
        assert (target / PLUGIN_FILE).is_file()
        assert (target / KONKON_DIR).is_dir()
