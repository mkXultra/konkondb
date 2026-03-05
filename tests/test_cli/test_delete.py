"""Tests for cli/delete.py — konkon delete command."""

import sqlite3
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from konkon.cli import main


def _init_project(runner: CliRunner, path: Path) -> None:
    """Helper: initialize a konkon project."""
    runner.invoke(main, ["init", str(path)])


def _insert_record(runner: CliRunner, path: Path, content: str) -> str:
    """Helper: insert a record and return its ID."""
    result = runner.invoke(main, ["-C", str(path), "insert", content])
    return result.output.strip()


class TestDeleteCommand:
    """konkon delete ID — CLI integration tests."""

    def test_delete_with_force(self, tmp_path: Path):
        """konkon delete --force ID → exit 0, outputs ID."""
        runner = CliRunner()
        _init_project(runner, tmp_path)
        record_id = _insert_record(runner, tmp_path, "hello")
        result = runner.invoke(
            main, ["-C", str(tmp_path), "delete", "--force", record_id]
        )
        assert result.exit_code == 0
        assert record_id in result.output

    def test_delete_nonexistent_exit_1(self, tmp_path: Path):
        """konkon delete --force with non-existent ID → exit 1."""
        runner = CliRunner()
        _init_project(runner, tmp_path)
        _insert_record(runner, tmp_path, "hello")
        result = runner.invoke(
            main, ["-C", str(tmp_path), "delete", "--force", "nonexistent-id"]
        )
        assert result.exit_code == 1

    def test_delete_without_init_exit_3(self, tmp_path: Path):
        """konkon delete without project init → exit 3 (CONFIG_ERROR)."""
        runner = CliRunner()
        result = runner.invoke(
            main, ["-C", str(tmp_path), "delete", "--force", "some-id"]
        )
        assert result.exit_code == 3

    def test_delete_schema_mismatch_exit_3(self, tmp_path: Path):
        """Raw DB with unknown schema version → exit 3 (CONFIG_ERROR)."""
        runner = CliRunner()
        _init_project(runner, tmp_path)
        _insert_record(runner, tmp_path, "hello")
        db_file = tmp_path / ".konkon" / "raw.db"
        conn = sqlite3.connect(str(db_file))
        conn.execute("PRAGMA user_version = 99")
        conn.close()

        result = runner.invoke(
            main,
            ["-C", str(tmp_path), "delete", "--force", "some-id"],
        )
        assert result.exit_code == 3
        assert "schema version mismatch" in result.output

    def test_delete_record_is_gone_after_delete(self, tmp_path: Path):
        """Record should not appear in raw list after deletion."""
        runner = CliRunner()
        _init_project(runner, tmp_path)
        record_id = _insert_record(runner, tmp_path, "to delete")
        runner.invoke(
            main, ["-C", str(tmp_path), "delete", "--force", record_id]
        )
        result = runner.invoke(
            main, ["-C", str(tmp_path), "raw", "get", record_id]
        )
        assert "not found" in result.output.lower() or result.exit_code != 0

    def test_delete_info_message_on_stderr(self, tmp_path: Path, capsys):
        """Successful delete prints info message to stderr."""
        runner = CliRunner()
        _init_project(runner, tmp_path)
        record_id = _insert_record(runner, tmp_path, "hello")
        result = runner.invoke(
            main, ["-C", str(tmp_path), "delete", "--force", record_id]
        )
        assert result.exit_code == 0
        # With Click's CliRunner, stderr output is mixed into result.output
        assert "[INFO]" in result.output
        assert "konkon build" in result.output


class TestDeleteConfirmation:
    """Confirmation prompt behavior (delete.md §振る舞い step 3)."""

    def test_confirm_yes(self, tmp_path: Path):
        """User answers 'y' → delete proceeds."""
        runner = CliRunner()
        _init_project(runner, tmp_path)
        record_id = _insert_record(runner, tmp_path, "hello")

        with patch("konkon.cli.delete._is_tty", return_value=True):
            result = runner.invoke(
                main,
                ["-C", str(tmp_path), "delete", record_id],
                input="y\n",
            )
        assert result.exit_code == 0
        assert record_id in result.output

    def test_confirm_no(self, tmp_path: Path):
        """User answers 'N' → cancel with exit 0."""
        runner = CliRunner()
        _init_project(runner, tmp_path)
        record_id = _insert_record(runner, tmp_path, "hello")

        with patch("konkon.cli.delete._is_tty", return_value=True):
            result = runner.invoke(
                main,
                ["-C", str(tmp_path), "delete", record_id],
                input="N\n",
            )
        assert result.exit_code == 0
        # The ID appears in the prompt but should NOT appear as a standalone
        # output line (which means delete did not execute)
        assert "[INFO]" not in result.output

    def test_confirm_empty_input_cancels(self, tmp_path: Path):
        """Empty input → cancel with exit 0."""
        runner = CliRunner()
        _init_project(runner, tmp_path)
        record_id = _insert_record(runner, tmp_path, "hello")

        with patch("konkon.cli.delete._is_tty", return_value=True):
            result = runner.invoke(
                main,
                ["-C", str(tmp_path), "delete", record_id],
                input="\n",
            )
        assert result.exit_code == 0
        assert "[INFO]" not in result.output

    def test_confirm_eof_cancels(self, tmp_path: Path):
        """EOF (Ctrl+D) → cancel with exit 0."""
        runner = CliRunner()
        _init_project(runner, tmp_path)
        record_id = _insert_record(runner, tmp_path, "hello")

        with patch("konkon.cli.delete._is_tty", return_value=True):
            # Empty input (no newline) simulates EOF
            result = runner.invoke(
                main,
                ["-C", str(tmp_path), "delete", record_id],
                input="",
            )
        assert result.exit_code == 0
        assert "[INFO]" not in result.output

    def test_non_tty_without_force_proceeds(self, tmp_path: Path):
        """Non-TTY without --force → implicit force (proceeds)."""
        runner = CliRunner()
        _init_project(runner, tmp_path)
        record_id = _insert_record(runner, tmp_path, "hello")

        with patch("konkon.cli.delete._is_tty", return_value=False):
            result = runner.invoke(
                main,
                ["-C", str(tmp_path), "delete", record_id],
            )
        assert result.exit_code == 0
        assert record_id in result.output

    def test_force_flag_short(self, tmp_path: Path):
        """-f short flag works."""
        runner = CliRunner()
        _init_project(runner, tmp_path)
        record_id = _insert_record(runner, tmp_path, "hello")
        result = runner.invoke(
            main, ["-C", str(tmp_path), "delete", "-f", record_id]
        )
        assert result.exit_code == 0
        assert record_id in result.output
