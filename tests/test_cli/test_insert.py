"""Tests for cli/insert.py — konkon insert command (Step 7)."""

from pathlib import Path

from click.testing import CliRunner

from konkon.cli import main
from konkon.core.instance import KONKON_DIR


class TestInsertCommand:
    """konkon insert [TEXT] [-m KEY=VALUE] — CLI integration tests."""

    def _init_project(self, path: Path) -> None:
        """Helper: initialize a konkon project at path."""
        runner = CliRunner()
        runner.invoke(main, ["init", str(path)])

    def test_insert_text_arg_succeeds(self, tmp_path: Path):
        """konkon insert 'hello' → exit 0, outputs record ID."""
        self._init_project(tmp_path)
        runner = CliRunner()
        result = runner.invoke(
            main, ["-C", str(tmp_path), "insert", "hello"]
        )
        assert result.exit_code == 0
        assert result.output.strip()  # should output something (the ID)

    def test_insert_stdin(self, tmp_path: Path):
        """echo 'hello' | konkon insert → reads from stdin."""
        self._init_project(tmp_path)
        runner = CliRunner()
        result = runner.invoke(
            main, ["-C", str(tmp_path), "insert"], input="hello from stdin"
        )
        assert result.exit_code == 0
        assert result.output.strip()

    def test_insert_with_meta(self, tmp_path: Path):
        """konkon insert -m source=test -m lang=en 'hello' → passes metadata."""
        self._init_project(tmp_path)
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["-C", str(tmp_path), "insert",
             "-m", "source=test", "-m", "lang=en", "hello"],
        )
        assert result.exit_code == 0

    def test_insert_no_text_no_stdin_fails(self, tmp_path: Path):
        """konkon insert with no text and TTY stdin → exit 1."""
        self._init_project(tmp_path)
        runner = CliRunner()
        result = runner.invoke(
            main, ["-C", str(tmp_path), "insert"]
        )
        assert result.exit_code == 1

    def test_insert_no_project_fails(self, tmp_path: Path):
        """konkon insert in dir without .konkon/ → exit 1."""
        runner = CliRunner()
        result = runner.invoke(
            main, ["-C", str(tmp_path), "insert", "hello"]
        )
        assert result.exit_code == 1

    def test_insert_creates_raw_db(self, tmp_path: Path):
        """First insert lazily creates .konkon/raw.db."""
        self._init_project(tmp_path)
        assert not (tmp_path / KONKON_DIR / "raw.db").exists()
        runner = CliRunner()
        runner.invoke(main, ["-C", str(tmp_path), "insert", "hello"])
        assert (tmp_path / KONKON_DIR / "raw.db").exists()

    def test_insert_outputs_id(self, tmp_path: Path):
        """Output contains a UUID-like record ID."""
        self._init_project(tmp_path)
        runner = CliRunner()
        result = runner.invoke(
            main, ["-C", str(tmp_path), "insert", "hello"]
        )
        output = result.output.strip()
        # UUID v7 format: 8-4-4-4-12
        parts = output.split("-")
        assert len(parts) == 5
