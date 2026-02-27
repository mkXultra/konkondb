"""Tests for cli/build.py — konkon build command (Step 9)."""

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
def query(request):
    return ""
""")
        result = runner.invoke(main, ["-C", str(tmp_path), "build"])
        assert result.exit_code == 1
        assert "build" in result.output
