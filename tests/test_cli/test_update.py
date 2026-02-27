"""Tests for cli/update.py — konkon update command."""

from pathlib import Path

from click.testing import CliRunner

from konkon.cli import main


def _init_project(runner: CliRunner, path: Path) -> None:
    """Helper: initialize a konkon project."""
    runner.invoke(main, ["init", str(path)])


def _insert_record(runner: CliRunner, path: Path, content: str) -> str:
    """Helper: insert a record and return its ID."""
    result = runner.invoke(main, ["-C", str(path), "insert", content])
    # The insert command outputs "Ingested: <id>"
    return result.output.strip()


class TestUpdateCommand:
    """konkon update ID — CLI integration tests."""

    def test_update_content(self, tmp_path: Path):
        """konkon update ID --content 'new' → exit 0."""
        runner = CliRunner()
        _init_project(runner, tmp_path)
        record_id = _insert_record(runner, tmp_path, "original")
        result = runner.invoke(
            main, ["-C", str(tmp_path), "update", record_id, "--content", "new"]
        )
        assert result.exit_code == 0
        assert record_id in result.output

    def test_update_meta(self, tmp_path: Path):
        """konkon update ID -m key=value → exit 0."""
        runner = CliRunner()
        _init_project(runner, tmp_path)
        record_id = _insert_record(runner, tmp_path, "hello")
        result = runner.invoke(
            main, ["-C", str(tmp_path), "update", record_id, "-m", "tag=new"]
        )
        assert result.exit_code == 0

    def test_update_no_changes_exit_2(self, tmp_path: Path):
        """konkon update ID with no --content or --meta → exit 2."""
        runner = CliRunner()
        _init_project(runner, tmp_path)
        record_id = _insert_record(runner, tmp_path, "hello")
        result = runner.invoke(
            main, ["-C", str(tmp_path), "update", record_id]
        )
        assert result.exit_code == 2

    def test_update_nonexistent_exit_1(self, tmp_path: Path):
        """konkon update with non-existent ID → exit 1."""
        runner = CliRunner()
        _init_project(runner, tmp_path)
        # Need at least one insert so raw.db exists
        _insert_record(runner, tmp_path, "hello")
        result = runner.invoke(
            main,
            ["-C", str(tmp_path), "update", "nonexistent-id", "--content", "x"],
        )
        assert result.exit_code == 1

    def test_update_without_init_exit_1(self, tmp_path: Path):
        """konkon update without project init → exit 1."""
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["-C", str(tmp_path), "update", "some-id", "--content", "x"],
        )
        assert result.exit_code == 1
