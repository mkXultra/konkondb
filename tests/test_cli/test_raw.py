"""Tests for cli/raw.py — konkon raw list command."""

import json
import sqlite3
from pathlib import Path

from click.testing import CliRunner

from konkon.cli import main


def _init_project(runner: CliRunner, path: Path) -> None:
    """Helper: initialize a konkon project."""
    runner.invoke(main, ["init", str(path)])


def _insert_record(runner: CliRunner, path: Path, content: str) -> str:
    """Helper: insert a record and return its ID."""
    result = runner.invoke(main, ["-C", str(path), "insert", content])
    return result.output.strip()


class TestRawListCommand:
    """konkon raw list — CLI integration tests."""

    def test_list_empty_db_exit_0(self, tmp_path: Path):
        """Empty Raw DB → exit 0, no output."""
        runner = CliRunner()
        _init_project(runner, tmp_path)
        # Insert and delete is complex; just insert nothing.
        # But we need raw.db to exist — insert then test with limit 0
        _insert_record(runner, tmp_path, "seed")
        result = runner.invoke(
            main, ["-C", str(tmp_path), "raw", "list", "--limit", "0"]
        )
        assert result.exit_code == 0
        assert result.output == ""

    def test_list_text_format(self, tmp_path: Path):
        """Text format shows ID and truncated content."""
        runner = CliRunner()
        _init_project(runner, tmp_path)
        record_id = _insert_record(runner, tmp_path, "hello world")
        result = runner.invoke(
            main, ["-C", str(tmp_path), "raw", "list", "--format", "text"]
        )
        assert result.exit_code == 0
        assert record_id in result.output
        assert "hello world" in result.output
        # Header present
        assert "ID" in result.output

    def test_list_json_format(self, tmp_path: Path):
        """JSON format outputs full records as JSON Lines."""
        runner = CliRunner()
        _init_project(runner, tmp_path)
        record_id = _insert_record(runner, tmp_path, "json test content")
        result = runner.invoke(
            main, ["-C", str(tmp_path), "raw", "list", "--format", "json"]
        )
        assert result.exit_code == 0
        line = result.output.strip()
        obj = json.loads(line)
        assert obj["id"] == record_id
        assert obj["content"] == "json test content"
        assert "created_at" in obj
        assert "updated_at" in obj
        assert "meta" in obj

    def test_list_respects_limit(self, tmp_path: Path):
        """--limit N restricts the output to N records."""
        runner = CliRunner()
        _init_project(runner, tmp_path)
        for i in range(5):
            _insert_record(runner, tmp_path, f"record-{i}")
        result = runner.invoke(
            main, ["-C", str(tmp_path), "raw", "list", "--format", "json", "--limit", "2"]
        )
        assert result.exit_code == 0
        lines = [l for l in result.output.strip().split("\n") if l]
        assert len(lines) == 2

    def test_list_newest_first(self, tmp_path: Path):
        """Records are ordered newest first."""
        runner = CliRunner()
        _init_project(runner, tmp_path)
        _insert_record(runner, tmp_path, "first")
        _insert_record(runner, tmp_path, "second")
        result = runner.invoke(
            main, ["-C", str(tmp_path), "raw", "list", "--format", "json"]
        )
        assert result.exit_code == 0
        lines = result.output.strip().split("\n")
        first_obj = json.loads(lines[0])
        second_obj = json.loads(lines[1])
        assert first_obj["content"] == "second"
        assert second_obj["content"] == "first"

    def test_list_without_init_exit_3(self, tmp_path: Path):
        """konkon raw list without project init → exit 3 (CONFIG_ERROR)."""
        runner = CliRunner()
        result = runner.invoke(
            main, ["-C", str(tmp_path), "raw", "list"]
        )
        assert result.exit_code == 3

    def test_list_no_db_file_exit_0_empty(self, tmp_path: Path):
        """Project init'd but no insert (DB not created) → exit 0, no output, no raw.db."""
        runner = CliRunner()
        _init_project(runner, tmp_path)
        db_file = tmp_path / ".konkon" / "raw.db"
        assert not db_file.exists()

        result = runner.invoke(
            main, ["-C", str(tmp_path), "raw", "list", "--format", "json"]
        )
        assert result.exit_code == 0
        assert result.output == ""
        # Must NOT have created the DB
        assert not db_file.exists()

    def test_list_negative_limit_exit_2(self, tmp_path: Path):
        """konkon raw list --limit -1 → exit 2 (usage error)."""
        runner = CliRunner()
        _init_project(runner, tmp_path)
        result = runner.invoke(
            main, ["-C", str(tmp_path), "raw", "list", "--limit", "-1"]
        )
        assert result.exit_code == 2

    def test_list_schema_mismatch_exit_3(self, tmp_path: Path):
        """Raw DB with unknown schema version → exit 3 (CONFIG_ERROR)."""
        runner = CliRunner()
        _init_project(runner, tmp_path)
        # Create a DB file with a future schema version
        db_file = tmp_path / ".konkon" / "raw.db"
        conn = sqlite3.connect(str(db_file))
        conn.execute("PRAGMA user_version = 99")
        conn.close()

        result = runner.invoke(
            main, ["-C", str(tmp_path), "raw", "list"]
        )
        assert result.exit_code == 3
        assert "schema version mismatch" in result.output

    def test_list_truncates_long_content(self, tmp_path: Path):
        """Text format truncates content longer than 50 chars."""
        runner = CliRunner()
        _init_project(runner, tmp_path)
        long_content = "x" * 100
        _insert_record(runner, tmp_path, long_content)
        result = runner.invoke(
            main, ["-C", str(tmp_path), "raw", "list", "--format", "text"]
        )
        assert result.exit_code == 0
        # Should be truncated with "..."
        assert "..." in result.output
        # Full content should NOT appear
        assert long_content not in result.output

    def test_list_json_preserves_full_content(self, tmp_path: Path):
        """JSON format outputs full content without truncation."""
        runner = CliRunner()
        _init_project(runner, tmp_path)
        long_content = "x" * 100
        _insert_record(runner, tmp_path, long_content)
        result = runner.invoke(
            main, ["-C", str(tmp_path), "raw", "list", "--format", "json"]
        )
        assert result.exit_code == 0
        obj = json.loads(result.output.strip())
        assert obj["content"] == long_content
