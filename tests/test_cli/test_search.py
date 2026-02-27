"""Tests for cli/search.py — konkon search command (Step 10)."""

from pathlib import Path

from click.testing import CliRunner

from konkon.cli import main


def _init_project(runner: CliRunner, path: Path) -> None:
    """Helper: initialize a konkon project."""
    runner.invoke(main, ["init", str(path)])


def _write_plugin(path: Path, code: str) -> None:
    """Helper: overwrite konkon.py with custom plugin code."""
    (path / "konkon.py").write_text(code)


class TestSearchCommand:
    """konkon search QUERY — CLI integration tests."""

    def test_search_returns_result_on_stdout(self, tmp_path: Path):
        """konkon search 'hello' with valid plugin → exit 0, result on stdout."""
        runner = CliRunner()
        _init_project(runner, tmp_path)
        _write_plugin(tmp_path, """\
def build(raw_data):
    pass

def query(request):
    return "found: " + request.query
""")
        result = runner.invoke(main, ["-C", str(tmp_path), "search", "hello"])
        assert result.exit_code == 0
        assert "found: hello" in result.output

    def test_search_without_init_exit_1(self, tmp_path: Path):
        """konkon search without project init → exit 1."""
        runner = CliRunner()
        result = runner.invoke(main, ["-C", str(tmp_path), "search", "hello"])
        assert result.exit_code == 1

    def test_search_no_query_arg_exit_2(self, tmp_path: Path):
        """konkon search with no QUERY argument → exit 2 (click usage error)."""
        runner = CliRunner()
        _init_project(runner, tmp_path)
        result = runner.invoke(main, ["-C", str(tmp_path), "search"])
        assert result.exit_code == 2

    def test_search_query_result_outputs_content(self, tmp_path: Path):
        """Plugin returning QueryResult → content field printed to stdout."""
        runner = CliRunner()
        _init_project(runner, tmp_path)
        _write_plugin(tmp_path, """\
from konkon.core.models import QueryResult

def build(raw_data):
    pass

def query(request):
    return QueryResult(content="the answer", metadata={"score": 0.9})
""")
        result = runner.invoke(main, ["-C", str(tmp_path), "search", "test"])
        assert result.exit_code == 0
        assert "the answer" in result.output

    def test_search_query_error_exit_1(self, tmp_path: Path):
        """Plugin raising QueryError → exit 1 with error message."""
        runner = CliRunner()
        _init_project(runner, tmp_path)
        _write_plugin(tmp_path, """\
from konkon.core.models import QueryError

def build(raw_data):
    pass

def query(request):
    raise QueryError("index not found")
""")
        result = runner.invoke(main, ["-C", str(tmp_path), "search", "test"])
        assert result.exit_code == 1
        assert "index not found" in result.output
