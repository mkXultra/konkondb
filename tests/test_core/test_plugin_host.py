"""Tests for core/transformation/plugin_host.py (Step 9)."""

from pathlib import Path
from types import ModuleType

import pytest

from konkon.core.models import BuildError, QueryError, QueryResult
from konkon.core.transformation.plugin_host import invoke_build, invoke_query, load_plugin


def _write_plugin(path: Path, code: str) -> Path:
    """Write a konkon.py plugin file and return its path."""
    plugin = path / "konkon.py"
    plugin.write_text(code)
    return plugin


class TestLoadPlugin:
    """load_plugin(path) — dynamic module loading + contract validation."""

    def test_loads_valid_plugin(self, tmp_path: Path):
        """Valid plugin with build() and query() loads successfully."""
        plugin_path = _write_plugin(tmp_path, """\
def schema():
    return {"description": "test", "params": {}}

def build(raw_data):
    pass

def query(request):
    return ""
""")
        module = load_plugin(plugin_path)
        assert isinstance(module, ModuleType)
        assert callable(module.build)
        assert callable(module.query)

    def test_raises_if_build_missing(self, tmp_path: Path):
        """Plugin missing build() raises error."""
        plugin_path = _write_plugin(tmp_path, """\
def schema():
    return {"description": "test", "params": {}}

def query(request):
    return ""
""")
        with pytest.raises(ValueError, match="build"):
            load_plugin(plugin_path)

    def test_raises_if_query_missing(self, tmp_path: Path):
        """Plugin missing query() raises error."""
        plugin_path = _write_plugin(tmp_path, """\
def schema():
    return {"description": "test", "params": {}}

def build(raw_data):
    pass
""")
        with pytest.raises(ValueError, match="query"):
            load_plugin(plugin_path)

    def test_raises_if_file_not_found(self, tmp_path: Path):
        """Non-existent plugin file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            load_plugin(tmp_path / "nonexistent.py")

    def test_raises_if_build_not_callable(self, tmp_path: Path):
        """build defined as non-callable raises error."""
        plugin_path = _write_plugin(tmp_path, """\
def schema():
    return {"description": "test", "params": {}}

build = 42

def query(request):
    return ""
""")
        with pytest.raises(ValueError, match="build"):
            load_plugin(plugin_path)


class TestInvokeBuild:
    """invoke_build(plugin, raw_data) — call plugin.build() with accessor."""

    def test_calls_build_with_accessor(self, tmp_path: Path):
        """invoke_build passes the accessor to plugin.build()."""
        plugin_path = _write_plugin(tmp_path, """\
received = None

def schema():
    return {"description": "test", "params": {}}

def build(raw_data):
    global received
    received = raw_data

def query(request):
    return ""
""")
        module = load_plugin(plugin_path)
        sentinel = object()
        invoke_build(module, sentinel)
        assert module.received is sentinel

    def test_build_error_propagates(self, tmp_path: Path):
        """BuildError from plugin.build() propagates unchanged."""
        plugin_path = _write_plugin(tmp_path, """\
from konkon.core.models import BuildError

def schema():
    return {"description": "test", "params": {}}

def build(raw_data):
    raise BuildError("vector DB down")

def query(request):
    return ""
""")
        module = load_plugin(plugin_path)
        with pytest.raises(BuildError, match="vector DB down"):
            invoke_build(module, None)

    def test_unexpected_exception_wrapped(self, tmp_path: Path):
        """Non-KonkonError from plugin.build() is wrapped as BuildError."""
        plugin_path = _write_plugin(tmp_path, """\
def schema():
    return {"description": "test", "params": {}}

def build(raw_data):
    raise KeyError("missing_key")

def query(request):
    return ""
""")
        module = load_plugin(plugin_path)
        with pytest.raises(BuildError, match="missing_key"):
            invoke_build(module, None)


class TestInvokeQuery:
    """invoke_query(plugin, request) — call plugin.query() with request."""

    def test_returns_string_result(self, tmp_path: Path):
        """invoke_query returns a string result from plugin.query()."""
        plugin_path = _write_plugin(tmp_path, """\
def schema():
    return {"description": "test", "params": {}}

def build(raw_data):
    pass

def query(request):
    return "found: " + request.query
""")
        from konkon.core.models import QueryRequest
        module = load_plugin(plugin_path)
        result = invoke_query(module, QueryRequest(query="hello"))
        assert result == "found: hello"

    def test_returns_query_result(self, tmp_path: Path):
        """invoke_query returns a QueryResult from plugin.query()."""
        plugin_path = _write_plugin(tmp_path, """\
from konkon.core.models import QueryResult

def schema():
    return {"description": "test", "params": {}}

def build(raw_data):
    pass

def query(request):
    return QueryResult(content="answer", metadata={"score": 0.9})
""")
        from konkon.core.models import QueryRequest
        module = load_plugin(plugin_path)
        result = invoke_query(module, QueryRequest(query="test"))
        assert isinstance(result, QueryResult)
        assert result.content == "answer"

    def test_query_error_propagates(self, tmp_path: Path):
        """QueryError from plugin.query() propagates unchanged."""
        plugin_path = _write_plugin(tmp_path, """\
from konkon.core.models import QueryError

def schema():
    return {"description": "test", "params": {}}

def build(raw_data):
    pass

def query(request):
    raise QueryError("search failed")
""")
        from konkon.core.models import QueryRequest
        module = load_plugin(plugin_path)
        with pytest.raises(QueryError, match="search failed"):
            invoke_query(module, QueryRequest(query="test"))

    def test_unexpected_exception_wrapped(self, tmp_path: Path):
        """Non-KonkonError from plugin.query() is wrapped as QueryError."""
        plugin_path = _write_plugin(tmp_path, """\
def schema():
    return {"description": "test", "params": {}}

def build(raw_data):
    pass

def query(request):
    raise RuntimeError("boom")
""")
        from konkon.core.models import QueryRequest
        module = load_plugin(plugin_path)
        with pytest.raises(QueryError, match="boom"):
            invoke_query(module, QueryRequest(query="test"))
