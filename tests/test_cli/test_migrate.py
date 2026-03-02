"""Tests for cli/migrate.py — konkon migrate command.

CLI integration tests using CliRunner.
"""

import tomllib
from pathlib import Path

from click.testing import CliRunner

from konkon.cli import main


def _init_project(runner: CliRunner, path: Path, backend: str = "sqlite") -> None:
    """Helper: initialize a konkon project with given backend."""
    args = ["init", str(path), "--raw-backend", backend]
    runner.invoke(main, args)


def _insert_record(runner: CliRunner, path: Path, text: str) -> None:
    """Helper: insert a record."""
    runner.invoke(main, ["-C", str(path), "insert", text])


class TestMigrateCommand:
    """konkon migrate — CLI integration tests."""

    def test_migrate_cli_sqlite_to_json(self, tmp_path: Path):
        """konkon migrate --to json → exit 0, stderr messages."""
        runner = CliRunner()
        _init_project(runner, tmp_path, "sqlite")
        _insert_record(runner, tmp_path, "test-data")

        result = runner.invoke(
            main, ["-C", str(tmp_path), "migrate", "--to", "json"]
        )
        assert result.exit_code == 0
        assert "Migrated 1 records" in result.stderr
        assert "sqlite -> json" in result.stderr
        assert "Updated .konkon/config.toml" in result.stderr
        assert "Source file .konkon/raw.db preserved" in result.stderr

    def test_migrate_cli_json_to_sqlite(self, tmp_path: Path):
        """konkon migrate --to sqlite from json backend → exit 0."""
        runner = CliRunner()
        _init_project(runner, tmp_path, "json")
        _insert_record(runner, tmp_path, "json-data")

        result = runner.invoke(
            main, ["-C", str(tmp_path), "migrate", "--to", "sqlite"]
        )
        assert result.exit_code == 0
        assert "Migrated 1 records" in result.stderr
        assert "json -> sqlite" in result.stderr

    def test_migrate_cli_same_backend(self, tmp_path: Path):
        """Same backend → exit 3."""
        runner = CliRunner()
        _init_project(runner, tmp_path, "sqlite")
        _insert_record(runner, tmp_path, "seed")

        result = runner.invoke(
            main, ["-C", str(tmp_path), "migrate", "--to", "sqlite"]
        )
        assert result.exit_code == 3
        assert "Already using" in result.stderr

    def test_migrate_cli_no_to_option(self, tmp_path: Path):
        """--to not specified → exit 2."""
        runner = CliRunner()
        _init_project(runner, tmp_path)

        result = runner.invoke(
            main, ["-C", str(tmp_path), "migrate"]
        )
        assert result.exit_code == 2

    def test_migrate_cli_invalid_backend(self, tmp_path: Path):
        """--to invalid → exit 2 (click.Choice handles this)."""
        runner = CliRunner()
        _init_project(runner, tmp_path)

        result = runner.invoke(
            main, ["-C", str(tmp_path), "migrate", "--to", "invalid"]
        )
        assert result.exit_code == 2

    def test_migrate_cli_target_exists(self, tmp_path: Path):
        """Target file exists without --force → exit 1."""
        runner = CliRunner()
        _init_project(runner, tmp_path, "sqlite")
        _insert_record(runner, tmp_path, "data")

        # Create target file
        (tmp_path / ".konkon" / "raw.json").write_text("{}")

        result = runner.invoke(
            main, ["-C", str(tmp_path), "migrate", "--to", "json"]
        )
        assert result.exit_code == 1
        assert "already exists" in result.stderr
        assert "--force" in result.stderr

    def test_migrate_cli_target_exists_force(self, tmp_path: Path):
        """Target file exists with --force → exit 0, WARN on stderr."""
        runner = CliRunner()
        _init_project(runner, tmp_path, "sqlite")
        _insert_record(runner, tmp_path, "data")

        # Create target file
        (tmp_path / ".konkon" / "raw.json").write_text("{}")

        result = runner.invoke(
            main, ["-C", str(tmp_path), "migrate", "--to", "json", "--force"]
        )
        assert result.exit_code == 0
        assert "[WARN] Removing existing .konkon/raw.json" in result.stderr
        assert "Migrated 1 records" in result.stderr

    def test_migrate_cli_no_stdout(self, tmp_path: Path):
        """stdout is empty (all output goes to stderr)."""
        runner = CliRunner()
        _init_project(runner, tmp_path, "sqlite")
        _insert_record(runner, tmp_path, "data")

        result = runner.invoke(
            main, ["-C", str(tmp_path), "migrate", "--to", "json"]
        )
        assert result.exit_code == 0
        # In Click 8.3+, result.output mixes stdout+stderr,
        # result.stderr has stderr only. If no stdout, they are equal.
        assert result.output == result.stderr

    def test_migrate_cli_source_preserved(self, tmp_path: Path):
        """Source file is kept after migration."""
        runner = CliRunner()
        _init_project(runner, tmp_path, "sqlite")
        _insert_record(runner, tmp_path, "keep-me")

        result = runner.invoke(
            main, ["-C", str(tmp_path), "migrate", "--to", "json"]
        )
        assert result.exit_code == 0
        assert (tmp_path / ".konkon" / "raw.db").exists()

    def test_migrate_cli_config_updated(self, tmp_path: Path):
        """config.toml raw_backend is updated after migration."""
        runner = CliRunner()
        _init_project(runner, tmp_path, "sqlite")
        _insert_record(runner, tmp_path, "data")

        runner.invoke(
            main, ["-C", str(tmp_path), "migrate", "--to", "json"]
        )

        config_file = tmp_path / ".konkon" / "config.toml"
        with open(config_file, "rb") as f:
            config = tomllib.load(f)
        assert config["raw_backend"] == "json"

    def test_migrate_cli_format_accepted_but_ignored(self, tmp_path: Path):
        """--format is accepted but has no effect."""
        runner = CliRunner()
        _init_project(runner, tmp_path, "sqlite")
        _insert_record(runner, tmp_path, "data")

        result = runner.invoke(
            main, ["-C", str(tmp_path), "migrate", "--to", "json", "--format", "json"]
        )
        assert result.exit_code == 0
        assert "Migrated 1 records" in result.stderr
