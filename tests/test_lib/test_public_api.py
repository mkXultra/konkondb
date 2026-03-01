"""Tests for konkon public API (Lib Entry) — import konkon."""

from pathlib import Path

import konkon


class TestPublicAPIExports:
    """All 7 Use Case functions are importable from konkon."""

    def test_init_available(self):
        assert callable(konkon.init)

    def test_insert_available(self):
        assert callable(konkon.insert)

    def test_update_available(self):
        assert callable(konkon.update)

    def test_build_available(self):
        assert callable(konkon.build)

    def test_search_available(self):
        assert callable(konkon.search)

    def test_raw_list_available(self):
        assert callable(konkon.raw_list)

    def test_raw_get_available(self):
        assert callable(konkon.raw_get)

    def test_all_exports(self):
        expected = {"build", "init", "insert", "raw_get", "raw_list", "search", "update"}
        assert set(konkon.__all__) == expected


class TestE2EWorkflow:
    """End-to-end workflow: init -> insert -> build -> search -> raw_list -> raw_get."""

    def test_full_workflow(self, tmp_path: Path):
        plugin_code = """\
from konkon.types import RawDataAccessor, QueryRequest, QueryResult

def schema():
    return {"description": "test", "params": {}}

def build(raw_data: RawDataAccessor) -> None:
    records = list(raw_data)
    # Write count to a file as a simple "context build"
    from pathlib import Path
    Path("context.txt").write_text(str(len(records)))

def query(request: QueryRequest) -> str | QueryResult:
    from pathlib import Path
    count = Path("context.txt").read_text() if Path("context.txt").exists() else "0"
    return f"count={count}, query={request.query}"
"""
        # 1. init
        konkon.init(tmp_path)
        assert (tmp_path / ".konkon").is_dir()

        # Write custom plugin
        (tmp_path / "konkon.py").write_text(plugin_code)

        # 2. insert
        r1 = konkon.insert("first document", None, tmp_path)
        assert r1.content == "first document"

        r2 = konkon.insert("second document", {"source_uri": "/doc.md"}, tmp_path)
        assert r2.source_uri == "/doc.md"

        # 3. build
        konkon.build(tmp_path)
        assert (tmp_path / "context.txt").read_text() == "2"

        # 4. search
        result = konkon.search(tmp_path, "hello")
        assert "count=2" in result
        assert "query=hello" in result

        # 5. raw_list
        records = konkon.raw_list(tmp_path)
        assert len(records) == 2

        # 6. raw_get
        found = konkon.raw_get(tmp_path, r1.id)
        assert found is not None
        assert found.content == "first document"

        # 7. update
        updated = konkon.update(r1.id, content="updated first", meta=None, project_root=tmp_path)
        assert updated.content == "updated first"
