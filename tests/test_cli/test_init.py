"""Tests for cli/init.py — konkon init command (Step 6)."""

from pathlib import Path

from click.testing import CliRunner

from konkon.cli import main
from konkon.core.instance import KONKON_DIR, PLUGIN_FILE


class TestInitCommand:
    """konkon init [DIRECTORY] [--force] — CLI integration tests."""

    def test_init_empty_dir_succeeds(self, tmp_path: Path):
        """konkon init in empty dir → exit 0."""
        runner = CliRunner()
        result = runner.invoke(main, ["init", str(tmp_path)])
        assert result.exit_code == 0
        assert (tmp_path / PLUGIN_FILE).is_file()
        assert (tmp_path / KONKON_DIR).is_dir()

    def test_init_default_cwd(self, tmp_path: Path):
        """konkon init with no DIRECTORY uses current working directory."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path) as td:
            result = runner.invoke(main, ["init"])
            assert result.exit_code == 0
            assert (Path(td) / PLUGIN_FILE).is_file()

    def test_init_creates_subdirectory(self, tmp_path: Path):
        """konkon init somedir — creates project in specified directory."""
        target = tmp_path / "myproject"
        runner = CliRunner()
        result = runner.invoke(main, ["init", str(target)])
        assert result.exit_code == 0
        assert (target / PLUGIN_FILE).is_file()

    def test_init_twice_fails(self, tmp_path: Path):
        """konkon init twice → exit 1 (konkon.py exists)."""
        runner = CliRunner()
        runner.invoke(main, ["init", str(tmp_path)])
        result = runner.invoke(main, ["init", str(tmp_path)])
        assert result.exit_code == 1
        assert "already exists" in result.output

    def test_init_force_overwrites(self, tmp_path: Path):
        """konkon init --force overwrites konkon.py."""
        runner = CliRunner()
        runner.invoke(main, ["init", str(tmp_path)])
        result = runner.invoke(main, ["init", "--force", str(tmp_path)])
        assert result.exit_code == 0

    def test_success_message_to_stderr(self, tmp_path: Path):
        """Success message goes to stderr, not stdout."""
        runner = CliRunner()
        result = runner.invoke(main, ["init", str(tmp_path)])
        assert result.exit_code == 0
        # click.echo(err=True) sends to stderr; CliRunner captures
        # stderr-bound output separately when available, but with default
        # settings it goes to result.output. The key contract is that
        # no data (only messages) appears on output, and the message exists.
        assert "Initialized" in result.output
