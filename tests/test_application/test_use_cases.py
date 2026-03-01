"""Tests for application/use_cases.py — Application Layer Use Cases."""

from pathlib import Path

import pytest

from konkon.application import (
    build,
    init,
    insert,
    raw_get,
    raw_list,
    search,
    update,
)
from konkon.core.instance import init_project, save_config
from konkon.core.models import BuildError, QueryResult


def _setup_project(tmp_path: Path, plugin_code: str) -> Path:
    """Initialize a project and write a custom plugin."""
    init_project(tmp_path, force=False)
    (tmp_path / "konkon.py").write_text(plugin_code)
    return tmp_path


NOOP_PLUGIN = """\
def schema():
    return {"description": "test", "params": {}}

def build(raw_data):
    pass

def query(request):
    return ""
"""


class TestInit:
    """init() — delegates to core.instance.init_project()."""

    def test_creates_project(self, tmp_path: Path):
        target = tmp_path / "myproject"
        init(target)
        assert (target / ".konkon").is_dir()
        assert (target / "konkon.py").exists()

    def test_force_overwrites(self, tmp_path: Path):
        init(tmp_path)
        init(tmp_path, force=True)
        assert (tmp_path / "konkon.py").exists()

    def test_raises_file_exists_error(self, tmp_path: Path):
        init(tmp_path)
        with pytest.raises(FileExistsError):
            init(tmp_path, force=False)

    def test_plugin_option(self, tmp_path: Path):
        init(tmp_path, plugin="plugins/my.py")
        assert (tmp_path / "plugins" / "my.py").exists()


class TestInsert:
    """insert() — delegates to core.ingestion.ingest()."""

    def test_returns_raw_record(self, tmp_path: Path):
        _setup_project(tmp_path, NOOP_PLUGIN)
        record = insert("hello", None, tmp_path)
        assert record.content == "hello"
        assert record.id

    def test_with_meta(self, tmp_path: Path):
        _setup_project(tmp_path, NOOP_PLUGIN)
        record = insert("data", {"source_uri": "/test.md"}, tmp_path)
        assert record.source_uri == "/test.md"


class TestUpdate:
    """update() — delegates to core.ingestion.update()."""

    def test_updates_content(self, tmp_path: Path):
        _setup_project(tmp_path, NOOP_PLUGIN)
        r = insert("original", None, tmp_path)
        updated = update(r.id, content="modified", meta=None, project_root=tmp_path)
        assert updated.content == "modified"

    def test_raises_key_error_for_missing(self, tmp_path: Path):
        _setup_project(tmp_path, NOOP_PLUGIN)
        insert("seed", None, tmp_path)
        with pytest.raises(KeyError):
            update("nonexistent-id", content="x", meta=None, project_root=tmp_path)


class TestBuild:
    """build() — delegates to core.transformation.run_build()."""

    def test_succeeds_with_valid_plugin(self, tmp_path: Path):
        _setup_project(tmp_path, NOOP_PLUGIN)
        result = build(tmp_path)
        assert result is None

    def test_uses_resolve_plugin_path_from_config(self, tmp_path: Path):
        """build() uses resolve_plugin_path() — config.toml plugin is respected."""
        init_project(tmp_path)
        # Write plugin at custom path
        custom_dir = tmp_path / "plugins"
        custom_dir.mkdir()
        (custom_dir / "custom.py").write_text("""\
import json
from pathlib import Path

def schema():
    return {"description": "test", "params": {}}

def build(raw_data):
    Path("build_marker.txt").write_text("custom-plugin-used")

def query(request):
    return ""
""")
        # Set config.toml to point to custom plugin
        save_config(tmp_path, {"plugin": "plugins/custom.py"})

        build(tmp_path)
        # Plugin runs in its own directory (plugins/), so marker is there
        assert (custom_dir / "build_marker.txt").read_text() == "custom-plugin-used"

    def test_plugin_override_takes_priority(self, tmp_path: Path):
        """plugin_override argument takes priority over config.toml."""
        init_project(tmp_path)
        # Set config.toml to point to a config plugin
        config_dir = tmp_path / "plugins"
        config_dir.mkdir()
        (config_dir / "config.py").write_text("""\
from pathlib import Path

def schema():
    return {"description": "test", "params": {}}

def build(raw_data):
    Path("config_marker.txt").write_text("config-plugin-used")

def query(request):
    return ""
""")
        save_config(tmp_path, {"plugin": "plugins/config.py"})

        # Write override plugin
        override_path = tmp_path / "override.py"
        override_path.write_text("""\
from pathlib import Path

def schema():
    return {"description": "test", "params": {}}

def build(raw_data):
    Path("override_marker.txt").write_text("override-used")

def query(request):
    return ""
""")

        build(tmp_path, plugin_override=override_path)
        # Override plugin ran (in its own directory = tmp_path)
        assert (tmp_path / "override_marker.txt").read_text() == "override-used"
        # Config plugin did NOT run
        assert not (config_dir / "config_marker.txt").exists()

    def test_build_error_propagates(self, tmp_path: Path):
        """BuildError from plugin propagates unchanged."""
        _setup_project(tmp_path, """\
from konkon.core.models import BuildError

def schema():
    return {"description": "test", "params": {}}

def build(raw_data):
    raise BuildError("build failed")

def query(request):
    return ""
""")
        with pytest.raises(BuildError, match="build failed"):
            build(tmp_path)


class TestSearch:
    """search() — delegates to core.transformation.run_query()."""

    def test_returns_string(self, tmp_path: Path):
        _setup_project(tmp_path, """\
def schema():
    return {"description": "test", "params": {}}

def build(raw_data):
    pass

def query(request):
    return "answer: " + request.query
""")
        result = search(tmp_path, "hello")
        assert result == "answer: hello"

    def test_returns_query_result(self, tmp_path: Path):
        _setup_project(tmp_path, """\
from konkon.core.models import QueryResult

def schema():
    return {"description": "test", "params": {}}

def build(raw_data):
    pass

def query(request):
    return QueryResult(content="structured")
""")
        result = search(tmp_path, "test")
        assert isinstance(result, QueryResult)
        assert result.content == "structured"

    def test_uses_resolve_plugin_path_from_config(self, tmp_path: Path):
        """search() uses resolve_plugin_path() — config.toml plugin is respected."""
        init_project(tmp_path)
        custom_dir = tmp_path / "plugins"
        custom_dir.mkdir()
        (custom_dir / "custom.py").write_text("""\
def schema():
    return {"description": "test", "params": {}}

def build(raw_data):
    pass

def query(request):
    return "custom-plugin-query"
""")
        save_config(tmp_path, {"plugin": "plugins/custom.py"})

        result = search(tmp_path, "test")
        assert result == "custom-plugin-query"

    def test_plugin_override_takes_priority(self, tmp_path: Path):
        """plugin_override argument takes priority over config.toml."""
        init_project(tmp_path)
        # Set config.toml to point to a config plugin
        config_dir = tmp_path / "plugins"
        config_dir.mkdir()
        (config_dir / "config.py").write_text("""\
def schema():
    return {"description": "test", "params": {}}

def build(raw_data):
    pass

def query(request):
    return "config-plugin-result"
""")
        save_config(tmp_path, {"plugin": "plugins/config.py"})

        # Write override plugin
        override_path = tmp_path / "override.py"
        override_path.write_text("""\
def schema():
    return {"description": "test", "params": {}}

def build(raw_data):
    pass

def query(request):
    return "override-result"
""")

        result = search(tmp_path, "test", plugin_override=override_path)
        assert result == "override-result"

    def test_passes_params(self, tmp_path: Path):
        _setup_project(tmp_path, """\
import json

def schema():
    return {"description": "test", "params": {"limit": {"type": "integer"}}}

def build(raw_data):
    pass

def query(request):
    return json.dumps(dict(request.params))
""")
        import json
        result = search(tmp_path, "test", params={"limit": "5"})
        assert json.loads(result) == {"limit": "5"}


class TestRawList:
    """raw_list() — delegates to core.ingestion.list_records()."""

    def test_returns_empty_when_no_db(self, tmp_path: Path):
        _setup_project(tmp_path, NOOP_PLUGIN)
        assert raw_list(tmp_path) == []

    def test_returns_records(self, tmp_path: Path):
        _setup_project(tmp_path, NOOP_PLUGIN)
        insert("one", None, tmp_path)
        insert("two", None, tmp_path)
        records = raw_list(tmp_path)
        assert len(records) == 2

    def test_respects_limit(self, tmp_path: Path):
        _setup_project(tmp_path, NOOP_PLUGIN)
        for i in range(5):
            insert(f"record-{i}", None, tmp_path)
        records = raw_list(tmp_path, limit=3)
        assert len(records) == 3


class TestRawGet:
    """raw_get() — delegates to core.ingestion.get_record()."""

    def test_returns_none_when_no_db(self, tmp_path: Path):
        _setup_project(tmp_path, NOOP_PLUGIN)
        assert raw_get(tmp_path, "nonexistent") is None

    def test_returns_record(self, tmp_path: Path):
        _setup_project(tmp_path, NOOP_PLUGIN)
        r = insert("hello", None, tmp_path)
        found = raw_get(tmp_path, r.id)
        assert found is not None
        assert found.content == "hello"

    def test_returns_none_for_missing_id(self, tmp_path: Path):
        _setup_project(tmp_path, NOOP_PLUGIN)
        insert("seed", None, tmp_path)
        assert raw_get(tmp_path, "nonexistent-id") is None
