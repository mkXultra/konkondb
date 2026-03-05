"""Tests for core/transformation/__init__.py — Transformation Context facade (Step 9)."""

import time
from pathlib import Path

import pytest

from konkon.core.instance import init_project, last_build_path
from konkon.core.models import BuildError, QueryResult
from konkon.core.transformation import run_build, run_describe, run_query


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

def build(raw_data, context):
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

def build(raw_data, context):
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

def build(raw_data, context):
    raise BuildError("db connection failed")

def query(request):
    return ""
""")
        with pytest.raises(BuildError, match="db connection failed"):
            run_build(tmp_path)


class TestRunDescribe:
    """run_describe(project_root) — facade orchestration."""

    def test_returns_schema_dict(self, tmp_path: Path):
        """run_describe with valid plugin returns schema dict."""
        _setup_project(tmp_path, """\
def schema():
    return {"description": "test plugin", "params": {"q": {"type": "string"}}}

def build(raw_data, context):
    pass

def query(request):
    return ""
""")
        result = run_describe(tmp_path)
        assert result == {"description": "test plugin", "params": {"q": {"type": "string"}}}

    def test_cwd_restored_after_call(self, tmp_path: Path):
        """run_describe restores CWD even after successful call."""
        import os

        _setup_project(tmp_path, """\
def schema():
    return {"description": "test", "params": {}}

def build(raw_data, context):
    pass

def query(request):
    return ""
""")
        cwd_before = os.getcwd()
        run_describe(tmp_path)
        assert os.getcwd() == cwd_before

    def test_plugin_not_found_raises(self, tmp_path: Path):
        """run_describe with missing plugin raises FileNotFoundError."""
        _setup_project(tmp_path, "")
        (tmp_path / "konkon.py").unlink()
        with pytest.raises(FileNotFoundError):
            run_describe(tmp_path)


class TestRunQuery:
    """run_query(project_root, query_str) — facade orchestration."""

    def test_returns_string_result(self, tmp_path: Path):
        """run_query with plugin returning str returns the string."""
        _setup_project(tmp_path, """\
def schema():
    return {"description": "test", "params": {}}

def build(raw_data, context):
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

def build(raw_data, context):
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

def build(raw_data, context):
    pass

def query(request):
    return QueryResult(content=json.dumps(dict(request.params)))
""")
        result = run_query(tmp_path, "hello", params={"limit": "10"})
        assert isinstance(result, QueryResult)
        import json
        assert json.loads(result.content) == {"limit": "10"}


class TestIncrementalBuild:
    """run_build incremental vs full behavior."""

    def test_first_build_passes_all_records(self, tmp_path: Path):
        """First build (no last_build file) passes all records."""
        from konkon.core.ingestion import ingest

        _setup_project(tmp_path, """\
import json
from pathlib import Path

def schema():
    return {"description": "test", "params": {}}

def build(raw_data, context):
    records = list(raw_data)
    Path("build_count.txt").write_text(str(len(records)))

def query(request):
    return ""
""")
        ingest("one", None, tmp_path)
        ingest("two", None, tmp_path)
        run_build(tmp_path)
        assert (tmp_path / "build_count.txt").read_text() == "2"

    def test_incremental_build_filters_by_last_build(self, tmp_path: Path):
        """Second build only passes records modified after last build."""
        from konkon.core.ingestion import ingest

        _setup_project(tmp_path, """\
import json
from pathlib import Path

def schema():
    return {"description": "test", "params": {}}

def build(raw_data, context):
    records = list(raw_data)
    Path("build_count.txt").write_text(str(len(records)))

def query(request):
    return ""
""")
        ingest("one", None, tmp_path)
        run_build(tmp_path)
        assert (tmp_path / "build_count.txt").read_text() == "1"

        time.sleep(0.01)
        ingest("two", None, tmp_path)
        run_build(tmp_path)
        # Second build should only see the new record
        assert (tmp_path / "build_count.txt").read_text() == "1"

    def test_full_build_passes_all_records(self, tmp_path: Path):
        """--full passes all records even after previous build."""
        from konkon.core.ingestion import ingest

        _setup_project(tmp_path, """\
import json
from pathlib import Path

def schema():
    return {"description": "test", "params": {}}

def build(raw_data, context):
    records = list(raw_data)
    Path("build_count.txt").write_text(str(len(records)))

def query(request):
    return ""
""")
        ingest("one", None, tmp_path)
        run_build(tmp_path)

        time.sleep(0.01)
        ingest("two", None, tmp_path)
        run_build(tmp_path, full=True)
        assert (tmp_path / "build_count.txt").read_text() == "2"

    def test_build_creates_last_build_file(self, tmp_path: Path):
        """Successful build creates .konkon/last_build."""
        _setup_project(tmp_path, """\
def schema():
    return {"description": "test", "params": {}}

def build(raw_data, context):
    pass

def query(request):
    return ""
""")
        assert not last_build_path(tmp_path).exists()
        run_build(tmp_path)
        assert last_build_path(tmp_path).exists()

    def test_incremental_catches_updated_records(self, tmp_path: Path):
        """Incremental build catches records updated after last build."""
        from konkon.core.ingestion import ingest, update

        _setup_project(tmp_path, """\
import json
from pathlib import Path

def schema():
    return {"description": "test", "params": {}}

def build(raw_data, context):
    records = list(raw_data)
    Path("build_contents.json").write_text(
        json.dumps([r.content for r in records])
    )

def query(request):
    return ""
""")
        r1 = ingest("original", None, tmp_path)
        run_build(tmp_path)

        time.sleep(0.01)
        update(r1.id, content="modified", meta=None, project_root=tmp_path)
        run_build(tmp_path)

        import json as json_mod
        contents = json_mod.loads(
            (tmp_path / "build_contents.json").read_text()
        )
        assert contents == ["modified"]

    def test_checkpoint_uses_build_start_time(self, tmp_path: Path):
        """Records inserted DURING build() are picked up by the next build.

        Regression guard: if the checkpoint were the build *completion* time
        instead of the *start* time, a record ingested inside build() would
        have updated_at < completion and be permanently skipped.
        """
        from konkon.core.ingestion import ingest

        # The plugin ingests a new record *during* its own build() execution.
        # After build() returns, the framework records build_start as the
        # checkpoint.  The ingested record's updated_at is between
        # build_start and build_completion, so it MUST appear in the next
        # incremental build.
        _setup_project(tmp_path, """\
import time, json
from pathlib import Path
from konkon.core.ingestion import ingest as _ingest

def schema():
    return {"description": "test", "params": {}}

def build(raw_data, context):
    records = list(raw_data)
    Path("build_ids.json").write_text(
        json.dumps([r.content for r in records])
    )
    # Ingest a record while build is running
    _ingest("during-build", None, Path("."))
    time.sleep(0.02)  # ensure completion time is well after the ingest

def query(request):
    return ""
""")
        ingest("seed", None, tmp_path)
        run_build(tmp_path)  # first build: processes "seed", ingests "during-build"

        # Second incremental build MUST see "during-build"
        run_build(tmp_path)
        import json as json_mod
        contents = json_mod.loads(
            (tmp_path / "build_ids.json").read_text()
        )
        assert "during-build" in contents


class TestBuildContext:
    """run_build passes correct BuildContext to plugin."""

    def test_first_build_passes_full_mode(self, tmp_path: Path):
        """First build (no last_build) passes mode='full'."""
        _setup_project(tmp_path, """\
import json
from pathlib import Path

def schema():
    return {"description": "test", "params": {}}

def build(raw_data, context):
    Path("context_mode.txt").write_text(context.mode)

def query(request):
    return ""
""")
        run_build(tmp_path)
        assert (tmp_path / "context_mode.txt").read_text() == "full"

    def test_second_build_passes_incremental_mode(self, tmp_path: Path):
        """Second build passes mode='incremental'."""
        _setup_project(tmp_path, """\
import json
from pathlib import Path

def schema():
    return {"description": "test", "params": {}}

def build(raw_data, context):
    Path("context_mode.txt").write_text(context.mode)

def query(request):
    return ""
""")
        run_build(tmp_path)
        assert (tmp_path / "context_mode.txt").read_text() == "full"

        run_build(tmp_path)
        assert (tmp_path / "context_mode.txt").read_text() == "incremental"

    def test_full_flag_overrides_incremental(self, tmp_path: Path):
        """--full always passes mode='full'."""
        _setup_project(tmp_path, """\
from pathlib import Path

def schema():
    return {"description": "test", "params": {}}

def build(raw_data, context):
    Path("context_mode.txt").write_text(context.mode)

def query(request):
    return ""
""")
        run_build(tmp_path)
        run_build(tmp_path, full=True)
        assert (tmp_path / "context_mode.txt").read_text() == "full"

    def test_incremental_build_includes_deleted_records(self, tmp_path: Path):
        """Incremental build passes deleted records in context."""
        from konkon.core.ingestion import ingest

        _setup_project(tmp_path, """\
import json
from pathlib import Path

def schema():
    return {"description": "test", "params": {}}

def build(raw_data, context):
    Path("deleted_ids.json").write_text(
        json.dumps([d.id for d in context.deleted_records])
    )

def query(request):
    return ""
""")
        r1 = ingest("first", {"key": "val"}, tmp_path)
        run_build(tmp_path)

        # Delete after first build
        from konkon.core.ingestion import delete
        time.sleep(0.01)
        delete(r1.id, tmp_path)

        run_build(tmp_path)

        import json as json_mod
        deleted_ids = json_mod.loads(
            (tmp_path / "deleted_ids.json").read_text()
        )
        assert r1.id in deleted_ids

    def test_full_build_has_empty_deleted_records(self, tmp_path: Path):
        """Full build always has empty deleted_records."""
        from konkon.core.ingestion import ingest

        _setup_project(tmp_path, """\
import json
from pathlib import Path

def schema():
    return {"description": "test", "params": {}}

def build(raw_data, context):
    Path("deleted_count.txt").write_text(str(len(context.deleted_records)))

def query(request):
    return ""
""")
        r1 = ingest("first", None, tmp_path)
        run_build(tmp_path)

        from konkon.core.ingestion import delete
        time.sleep(0.01)
        delete(r1.id, tmp_path)

        run_build(tmp_path, full=True)
        assert (tmp_path / "deleted_count.txt").read_text() == "0"


class TestTombstonePurge:
    """Tombstone purge after successful build."""

    def test_tombstones_purged_after_successful_build(self, tmp_path: Path):
        """Tombstones are purged after a successful build."""
        from datetime import timezone
        from konkon.core.ingestion import delete, get_deleted_records_since, ingest

        _setup_project(tmp_path, """\
def schema():
    return {"description": "test", "params": {}}

def build(raw_data, context):
    pass

def query(request):
    return ""
""")
        r1 = ingest("first", None, tmp_path)
        run_build(tmp_path)

        time.sleep(0.01)
        delete(r1.id, tmp_path)

        # Tombstone exists before build
        from datetime import datetime
        early = datetime(2000, 1, 1, tzinfo=timezone.utc)
        assert len(get_deleted_records_since(tmp_path, early)) == 1

        run_build(tmp_path)

        # Tombstone purged after successful build
        assert len(get_deleted_records_since(tmp_path, early)) == 0

    def test_tombstones_not_purged_on_build_failure(self, tmp_path: Path):
        """Tombstones survive when build() fails."""
        from datetime import datetime, timezone
        from konkon.core.ingestion import delete, get_deleted_records_since, ingest

        # Start with a succeeding plugin so we can do the first build
        _setup_project(tmp_path, """\
def schema():
    return {"description": "test", "params": {}}

def build(raw_data, context):
    pass

def query(request):
    return ""
""")
        r1 = ingest("first", None, tmp_path)
        run_build(tmp_path)

        time.sleep(0.01)
        delete(r1.id, tmp_path)

        # Now switch to failing plugin
        (tmp_path / "konkon.py").write_text("""\
from konkon.core.models import BuildError

def schema():
    return {"description": "test", "params": {}}

def build(raw_data, context):
    raise BuildError("fail on purpose")

def query(request):
    return ""
""")
        with pytest.raises(BuildError):
            run_build(tmp_path)

        # Tombstone should still exist
        early = datetime(2000, 1, 1, tzinfo=timezone.utc)
        assert len(get_deleted_records_since(tmp_path, early)) == 1
