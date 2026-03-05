"""Tests for cli/describe.py — konkon describe command."""

import json
from pathlib import Path

from click.testing import CliRunner

from konkon.cli import main


def _init_project(runner: CliRunner, path: Path) -> None:
    """Helper: initialize a konkon project."""
    runner.invoke(main, ["init", str(path)])


def _write_plugin(path: Path, code: str) -> None:
    """Helper: overwrite konkon.py with custom plugin code."""
    (path / "konkon.py").write_text(code)


VALID_PLUGIN = """\
def schema():
    return {
        "description": "Test plugin description",
        "params": {
            "view": {
                "type": "string",
                "description": "View type",
                "enum": ["a", "b"],
                "default": "a",
            },
            "q": {
                "type": "string",
                "description": "Search query",
            },
        },
        "result": {
            "description": "Markdown context",
        },
    }

def build(raw_data, context):
    pass

def query(request):
    return ""
"""


class TestDescribeCommand:
    """konkon describe — CLI integration tests."""

    def test_describe_json_format(self, tmp_path: Path):
        """konkon describe --format json → exit 0, valid JSON."""
        runner = CliRunner()
        _init_project(runner, tmp_path)
        _write_plugin(tmp_path, VALID_PLUGIN)
        result = runner.invoke(main, ["-C", str(tmp_path), "describe", "--format", "json"])
        assert result.exit_code == 0
        schema = json.loads(result.output)
        assert schema["description"] == "Test plugin description"
        assert "view" in schema["params"]
        assert "q" in schema["params"]

    def test_describe_text_format(self, tmp_path: Path):
        """konkon describe --format text → exit 0, human-readable output."""
        runner = CliRunner()
        _init_project(runner, tmp_path)
        _write_plugin(tmp_path, VALID_PLUGIN)
        result = runner.invoke(main, ["-C", str(tmp_path), "describe", "--format", "text"])
        assert result.exit_code == 0
        assert "Description: Test plugin description" in result.output
        assert "Params:" in result.output
        assert "view" in result.output
        assert "enum: a, b" in result.output
        assert "default: a" in result.output
        assert "Result: Markdown context" in result.output

    def test_describe_without_init_exit_3(self, tmp_path: Path):
        """konkon describe without project init → exit 3."""
        runner = CliRunner()
        result = runner.invoke(main, ["-C", str(tmp_path), "describe"])
        assert result.exit_code == 3

    def test_describe_schema_error_exit_3(self, tmp_path: Path):
        """Plugin schema() raising error → exit 3."""
        runner = CliRunner()
        _init_project(runner, tmp_path)
        _write_plugin(tmp_path, """\
def schema():
    raise RuntimeError("broken schema")

def build(raw_data, context):
    pass

def query(request):
    return ""
""")
        result = runner.invoke(main, ["-C", str(tmp_path), "describe", "--format", "json"])
        assert result.exit_code == 3
        assert "schema() failed" in result.output

    def test_describe_default_format_json_when_not_tty(self, tmp_path: Path):
        """Without explicit --format, non-TTY defaults to json."""
        runner = CliRunner()
        _init_project(runner, tmp_path)
        _write_plugin(tmp_path, VALID_PLUGIN)
        # CliRunner is not a TTY, so default should be json
        result = runner.invoke(main, ["-C", str(tmp_path), "describe"])
        assert result.exit_code == 0
        schema = json.loads(result.output)
        assert "description" in schema

    def test_describe_minimal_schema(self, tmp_path: Path):
        """Plugin with minimal schema (no params, no result) → works."""
        runner = CliRunner()
        _init_project(runner, tmp_path)
        _write_plugin(tmp_path, """\
def schema():
    return {"description": "Minimal", "params": {}}

def build(raw_data, context):
    pass

def query(request):
    return ""
""")
        result = runner.invoke(main, ["-C", str(tmp_path), "describe", "--format", "text"])
        assert result.exit_code == 0
        assert "Description: Minimal" in result.output

    def test_describe_non_dict_schema_exit_3(self, tmp_path: Path):
        """Plugin schema() returning non-dict → exit 3."""
        runner = CliRunner()
        _init_project(runner, tmp_path)
        _write_plugin(tmp_path, """\
def schema():
    return "not a dict"

def build(raw_data, context):
    pass

def query(request):
    return ""
""")
        result = runner.invoke(main, ["-C", str(tmp_path), "describe"])
        assert result.exit_code == 3
        assert "must return dict" in result.output

    def test_describe_syntax_error_exit_3(self, tmp_path: Path):
        """Plugin with SyntaxError → exit 3 (config error)."""
        runner = CliRunner()
        _init_project(runner, tmp_path)
        _write_plugin(tmp_path, "def schema( BROKEN SYNTAX")
        result = runner.invoke(main, ["-C", str(tmp_path), "describe"])
        assert result.exit_code == 3

    def test_describe_with_plugin_option(self, tmp_path: Path):
        """konkon describe --plugin path → reads specified plugin."""
        runner = CliRunner()
        _init_project(runner, tmp_path)
        # Write a custom plugin at a non-default path
        custom = tmp_path / "custom_plugin.py"
        custom.write_text("""\
def schema():
    return {"description": "Custom plugin", "params": {}}

def build(raw_data, context):
    pass

def query(request):
    return ""
""")
        result = runner.invoke(
            main, ["-C", str(tmp_path), "describe", "--plugin", str(custom), "--format", "json"]
        )
        assert result.exit_code == 0
        schema = json.loads(result.output)
        assert schema["description"] == "Custom plugin"
