"""Tests for core/transformation/__init__.py — Transformation Context facade (Step 9)."""

from pathlib import Path

import pytest

from konkon.core.instance import init_project
from konkon.core.models import BuildError, QueryResult
from konkon.core.transformation import run_build, run_query


def _setup_project(tmp_path: Path, plugin_code: str) -> Path:
    """Initialize a project and write a custom plugin."""
    init_project(tmp_path, force=False)
    (tmp_path / "konkon.py").write_text(plugin_code)
    return tmp_path


class TestRunBuild:
    """run_build(project_root) — facade orchestration."""

    def test_succeeds_with_valid_plugin(self, tmp_path: Path):
        """run_build with a valid no-op plugin succeeds (returns None)."""
        _setup_project(tmp_path, """\
def schema():
    return {"description": "test", "params": {}}

def build(raw_data):
    pass

def query(request):
    return ""
""")
        result = run_build(tmp_path)
        assert result is None

    def test_plugin_receives_raw_data(self, tmp_path: Path):
        """Plugin build() receives a RawDataAccessor with inserted data."""
        from konkon.core.ingestion import ingest

        _setup_project(tmp_path, """\
import json
from pathlib import Path

def schema():
    return {"description": "test", "params": {}}

def build(raw_data):
    records = list(raw_data)
    Path("build_result.json").write_text(
        json.dumps([r.content for r in records])
    )

def query(request):
    return ""
""")
        ingest("record-one", None, tmp_path)
        ingest("record-two", None, tmp_path)

        run_build(tmp_path)

        result_file = tmp_path / "build_result.json"
        assert result_file.exists()
        import json
        contents = json.loads(result_file.read_text())
        assert contents == ["record-one", "record-two"]

    def test_build_error_propagates(self, tmp_path: Path):
        """BuildError from plugin propagates through facade."""
        _setup_project(tmp_path, """\
from konkon.core.models import BuildError

def schema():
    return {"description": "test", "params": {}}

def build(raw_data):
    raise BuildError("db connection failed")

def query(request):
    return ""
""")
        with pytest.raises(BuildError, match="db connection failed"):
            run_build(tmp_path)


class TestRunQuery:
    """run_query(project_root, query_str) — facade orchestration."""

    def test_returns_string_result(self, tmp_path: Path):
        """run_query with plugin returning str returns the string."""
        _setup_project(tmp_path, """\
def schema():
    return {"description": "test", "params": {}}

def build(raw_data):
    pass

def query(request):
    return "result for: " + request.query
""")
        result = run_query(tmp_path, "hello")
        assert result == "result for: hello"

    def test_returns_query_result(self, tmp_path: Path):
        """run_query with plugin returning QueryResult returns it."""
        _setup_project(tmp_path, """\
from konkon.core.models import QueryResult

def schema():
    return {"description": "test", "params": {}}

def build(raw_data):
    pass

def query(request):
    return QueryResult(content="answer")
""")
        result = run_query(tmp_path, "test")
        assert isinstance(result, QueryResult)
        assert result.content == "answer"

    def test_passes_params_to_query_request(self, tmp_path: Path):
        """run_query with params passes them in QueryRequest."""
        _setup_project(tmp_path, """\
import json
from konkon.core.models import QueryResult

def schema():
    return {"description": "test", "params": {"limit": {"type": "integer"}}}

def build(raw_data):
    pass

def query(request):
    return QueryResult(content=json.dumps(dict(request.params)))
""")
        result = run_query(tmp_path, "hello", params={"limit": "10"})
        assert isinstance(result, QueryResult)
        import json
        assert json.loads(result.content) == {"limit": "10"}
