"""Tests for core/transformation/__init__.py — Transformation Context facade (Step 9)."""

import time
from pathlib import Path

import pytest

from konkon.core.instance import init_project, last_build_path
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

def build(raw_data):
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

def build(raw_data):
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

def build(raw_data):
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

def build(raw_data):
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

def build(raw_data):
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

def build(raw_data):
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
