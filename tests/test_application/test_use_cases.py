"""Tests for application/use_cases.py — Application Layer Use Cases."""

from pathlib import Path

import pytest

import tomllib

from konkon.application import (
    build,
    init,
    insert,
    migrate,
    raw_get,
    raw_list,
    search,
    update,
)
from konkon.core.instance import init_project, load_config, save_config
from konkon.core.models import BuildError, ConfigError, QueryResult


def _setup_project(tmp_path: Path, plugin_code: str) -> Path:
    """Initialize a project and write a custom plugin."""
    init_project(tmp_path, force=False)
    (tmp_path / "konkon.py").write_text(plugin_code)
    return tmp_path


NOOP_PLUGIN = """\
def schema():
    return {"description": "test", "params": {}}

def build(raw_data, context):
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
        # --plugin only writes config, no template generated
        assert not (tmp_path / "plugins" / "my.py").exists()
        from konkon.core.instance import load_config
        cfg = load_config(tmp_path)
        assert cfg["plugin"] == "plugins/my.py"


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

def build(raw_data, context):
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

def build(raw_data, context):
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

def build(raw_data, context):
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

def build(raw_data, context):
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

def build(raw_data, context):
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

def build(raw_data, context):
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

def build(raw_data, context):
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

def build(raw_data, context):
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

def build(raw_data, context):
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

def build(raw_data, context):
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


class TestMigrate:
    """migrate() — orchestrates data migration + config update."""

    def test_migrate_updates_config(self, tmp_path: Path):
        """After migration, config.toml raw_backend is updated."""
        _setup_project(tmp_path, NOOP_PLUGIN)
        save_config(tmp_path, {"raw_backend": "sqlite"})
        insert("data", None, tmp_path)

        migrate("json", tmp_path)

        config = load_config(tmp_path)
        assert config["raw_backend"] == "json"

    def test_migrate_config_not_updated_on_failure(self, tmp_path: Path):
        """On migration failure, config remains unchanged."""
        _setup_project(tmp_path, NOOP_PLUGIN)
        save_config(tmp_path, {"raw_backend": "sqlite"})
        # Don't create the DB file — source doesn't exist

        with pytest.raises(ConfigError):
            migrate("json", tmp_path)

        config = load_config(tmp_path)
        assert config["raw_backend"] == "sqlite"

    def test_migrate_preserves_other_config(self, tmp_path: Path):
        """Migration preserves other config keys (e.g. plugin)."""
        _setup_project(tmp_path, NOOP_PLUGIN)
        save_config(tmp_path, {"raw_backend": "sqlite", "plugin": "konkon.py"})
        insert("data", None, tmp_path)

        migrate("json", tmp_path)

        config = load_config(tmp_path)
        assert config["raw_backend"] == "json"
        assert config["plugin"] == "konkon.py"


def _assert_records_match(before, after):
    """Assert two record lists are identical (sorted by id for stable comparison)."""
    assert len(before) == len(after)
    before_sorted = sorted(before, key=lambda r: r.id)
    after_sorted = sorted(after, key=lambda r: r.id)
    for b, a in zip(before_sorted, after_sorted):
        assert b.id == a.id
        assert b.created_at == a.created_at
        assert b.updated_at == a.updated_at
        assert b.content == a.content
        assert dict(b.meta) == dict(a.meta)


class TestMigrateRoundTrip:
    """Round-trip migration tests via Application Layer public API."""

    def test_roundtrip_sqlite_to_json(self, tmp_path: Path):
        """SQLite → JSON: raw_list() returns identical records."""
        _setup_project(tmp_path, NOOP_PLUGIN)
        save_config(tmp_path, {"raw_backend": "sqlite"})
        insert("alpha", {"tag": "a"}, tmp_path)
        insert("beta", {"tag": "b"}, tmp_path)
        insert("gamma", None, tmp_path)

        before = raw_list(tmp_path, limit=100)
        migrate("json", tmp_path)
        after = raw_list(tmp_path, limit=100)

        _assert_records_match(before, after)

    def test_roundtrip_json_to_sqlite(self, tmp_path: Path):
        """JSON → SQLite: raw_list() returns identical records."""
        _setup_project(tmp_path, NOOP_PLUGIN)
        save_config(tmp_path, {"raw_backend": "json"})
        insert("one", {"n": 1}, tmp_path)
        insert("two", {"n": 2}, tmp_path)

        before = raw_list(tmp_path, limit=100)
        migrate("sqlite", tmp_path)
        after = raw_list(tmp_path, limit=100)

        _assert_records_match(before, after)

    def test_roundtrip_escape_content(self, tmp_path: Path):
        """Content with escape characters survives SQLite → JSON migration."""
        _setup_project(tmp_path, NOOP_PLUGIN)
        save_config(tmp_path, {"raw_backend": "sqlite"})

        # Simulate `cat file | konkon insert` with tricky content
        tricky_contents = [
            "line1\nline2\nline3",                       # newlines
            "col1\tcol2\tcol3",                           # tabs
            "He said \"hello\" and 'goodbye'",            # quotes
            "path\\to\\file",                             # backslashes
            "emoji: \U0001f600 日本語テスト",               # unicode
            'json-like: {"key": [1, 2, 3]}',             # JSON special chars
            "back\\nslash-n vs real\nnewline",            # escaped vs real
            "null\x00byte",                               # NULL byte
            "",                                           # empty string
            "   leading and trailing spaces   ",          # whitespace
            'a' * 50_000,                                 # large content
        ]

        for content in tricky_contents:
            insert(content, None, tmp_path)

        before = raw_list(tmp_path, limit=100)
        migrate("json", tmp_path)
        after = raw_list(tmp_path, limit=100)

        _assert_records_match(before, after)
        # Also verify each record individually via raw_get
        for rec in before:
            got = raw_get(tmp_path, rec.id)
            assert got is not None
            assert got.content == rec.content

    def test_roundtrip_escape_meta(self, tmp_path: Path):
        """Meta with special characters survives JSON → SQLite migration."""
        _setup_project(tmp_path, NOOP_PLUGIN)
        save_config(tmp_path, {"raw_backend": "json"})

        tricky_metas = [
            {"path": "C:\\Users\\test\\file.txt"},
            {"desc": "line1\nline2"},
            {"quote": 'He said "hi"'},
            {"unicode": "\U0001f600\u00e9\u00fc"},
            {"nested": {"deep": {"list": [1, "two", None, True]}}},
            {"empty_str": "", "empty_list": [], "null_val": None},
            {"json_chars": '{"not": "parsed"}'},
            {"tabs": "a\tb\tc"},
        ]

        for meta in tricky_metas:
            insert("content", meta, tmp_path)

        before = raw_list(tmp_path, limit=100)
        migrate("sqlite", tmp_path)
        after = raw_list(tmp_path, limit=100)

        _assert_records_match(before, after)
        for rec in before:
            got = raw_get(tmp_path, rec.id)
            assert got is not None
            assert dict(got.meta) == dict(rec.meta)
