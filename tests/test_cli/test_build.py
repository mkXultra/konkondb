"""Tests for cli/build.py — konkon build command (Step 9)."""

import sqlite3
import time
from pathlib import Path

from click.testing import CliRunner

from konkon.cli import main


def _init_project(runner: CliRunner, path: Path) -> None:
    """Helper: initialize a konkon project."""
    runner.invoke(main, ["init", str(path)])


def _write_plugin(path: Path, code: str) -> None:
    """Helper: overwrite konkon.py with custom plugin code."""
    (path / "konkon.py").write_text(code)


class TestBuildCommand:
    """konkon build — CLI integration tests."""

    def test_build_valid_plugin_exit_0(self, tmp_path: Path):
        """konkon build with valid no-op plugin → exit 0, no stdout."""
        runner = CliRunner()
        _init_project(runner, tmp_path)
        result = runner.invoke(main, ["-C", str(tmp_path), "build"])
        assert result.exit_code == 0
        assert result.output == ""

    def test_build_without_init_exit_1(self, tmp_path: Path):
        """konkon build without project init → exit 1."""
        runner = CliRunner()
        result = runner.invoke(main, ["-C", str(tmp_path), "build"])
        assert result.exit_code == 1

    def test_build_error_exit_1_with_message(self, tmp_path: Path):
        """konkon build with plugin that raises BuildError → exit 1, stderr message."""
        runner = CliRunner()
        _init_project(runner, tmp_path)
        _write_plugin(tmp_path, """\
from konkon.core.models import BuildError

def schema():
    return {"description": "test", "params": {}}

def build(raw_data):
    raise BuildError("vector store unreachable")

def query(request):
    return ""
""")
        result = runner.invoke(main, ["-C", str(tmp_path), "build"])
        assert result.exit_code == 1
        assert "vector store unreachable" in result.output

    def test_build_missing_contract_exit_1(self, tmp_path: Path):
        """konkon build with plugin missing build() → exit 1."""
        runner = CliRunner()
        _init_project(runner, tmp_path)
        _write_plugin(tmp_path, """\
def schema():
    return {"description": "test", "params": {}}

def query(request):
    return ""
""")
        result = runner.invoke(main, ["-C", str(tmp_path), "build"])
        assert result.exit_code == 1
        assert "build" in result.output

    def test_build_full_flag(self, tmp_path: Path):
        """konkon build --full passes all records even after prior build."""
        runner = CliRunner()
        _init_project(runner, tmp_path)
        _write_plugin(tmp_path, """\
from pathlib import Path

def schema():
    return {"description": "test", "params": {}}

def build(raw_data):
    Path("count.txt").write_text(str(len(list(raw_data))))

def query(request):
    return ""
""")
        runner.invoke(main, ["-C", str(tmp_path), "insert", "one"])
        runner.invoke(main, ["-C", str(tmp_path), "build"])
        assert (tmp_path / "count.txt").read_text() == "1"

        time.sleep(0.01)
        runner.invoke(main, ["-C", str(tmp_path), "insert", "two"])

        # Incremental: only new record
        runner.invoke(main, ["-C", str(tmp_path), "build"])
        assert (tmp_path / "count.txt").read_text() == "1"

        # Full: all records
        runner.invoke(main, ["-C", str(tmp_path), "build", "--full"])
        assert (tmp_path / "count.txt").read_text() == "2"

    def test_build_schema_mismatch_exit_3(self, tmp_path: Path):
        """Raw DB with unknown schema version → exit 3 (CONFIG_ERROR)."""
        runner = CliRunner()
        _init_project(runner, tmp_path)
        db_file = tmp_path / ".konkon" / "raw.db"
        conn = sqlite3.connect(str(db_file))
        conn.execute("PRAGMA user_version = 99")
        conn.close()

        result = runner.invoke(main, ["-C", str(tmp_path), "build"])
        assert result.exit_code == 3
        assert "schema version mismatch" in result.output
