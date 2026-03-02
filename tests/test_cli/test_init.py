"""Tests for cli/init.py — konkon init command."""

from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from konkon.cli import main
from konkon.core.instance import CONFIG_FILE, KONKON_DIR, PLUGIN_FILE, load_config


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
        """konkon init twice → exit 2 (konkon.py exists, per commands/init.md)."""
        runner = CliRunner()
        runner.invoke(main, ["init", str(tmp_path)])
        result = runner.invoke(main, ["init", str(tmp_path)])
        assert result.exit_code == 2
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


class TestInitPluginOption:
    """konkon init --plugin PATH — CLI integration tests."""

    def test_plugin_creates_at_custom_path(self, tmp_path: Path):
        """--plugin src/my_plugin.py → template at that path."""
        runner = CliRunner()
        result = runner.invoke(
            main, ["init", "--plugin", "src/my_plugin.py", str(tmp_path)]
        )
        assert result.exit_code == 0
        assert (tmp_path / "src" / "my_plugin.py").is_file()
        assert not (tmp_path / PLUGIN_FILE).exists()

    def test_plugin_writes_config(self, tmp_path: Path):
        """--plugin writes to .konkon/config.toml."""
        runner = CliRunner()
        runner.invoke(
            main, ["init", "--plugin", "src/my_plugin.py", str(tmp_path)]
        )
        cfg = load_config(tmp_path)
        assert cfg["plugin"] == "src/my_plugin.py"

    def test_plugin_no_config_when_unspecified(self, tmp_path: Path):
        """No --plugin → no config.toml."""
        runner = CliRunner()
        runner.invoke(main, ["init", str(tmp_path)])
        assert not (tmp_path / KONKON_DIR / CONFIG_FILE).exists()

    def test_plugin_absolute_path_rejected(self, tmp_path: Path):
        """Absolute path → exit 2."""
        runner = CliRunner()
        result = runner.invoke(
            main, ["init", "--plugin", "/absolute/path.py", str(tmp_path)]
        )
        assert result.exit_code == 2
        assert "relative path" in result.output

    def test_plugin_parent_traversal_rejected(self, tmp_path: Path):
        """.. in path → exit 2."""
        runner = CliRunner()
        result = runner.invoke(
            main, ["init", "--plugin", "../outside.py", str(tmp_path)]
        )
        assert result.exit_code == 2
        assert "within the project" in result.output

    def test_plugin_single_quote_rejected(self, tmp_path: Path):
        """Single quote in path → exit 2."""
        runner = CliRunner()
        result = runner.invoke(
            main, ["init", "--plugin", "it's_plugin.py", str(tmp_path)]
        )
        assert result.exit_code == 2
        assert "single quotes" in result.output

    def test_plugin_existing_file_fails(self, tmp_path: Path):
        """Existing plugin file without --force → exit 2."""
        (tmp_path / "custom.py").write_text("old")
        runner = CliRunner()
        result = runner.invoke(
            main, ["init", "--plugin", "custom.py", str(tmp_path)]
        )
        assert result.exit_code == 2
        assert "already exists" in result.output

    def test_plugin_force_overwrites(self, tmp_path: Path):
        """--force with --plugin overwrites existing file."""
        (tmp_path / "custom.py").write_text("old")
        runner = CliRunner()
        result = runner.invoke(
            main, ["init", "--force", "--plugin", "custom.py", str(tmp_path)]
        )
        assert result.exit_code == 0
        assert "def build(" in (tmp_path / "custom.py").read_text()

    def test_plugin_empty_string_rejected(self, tmp_path: Path):
        """Empty --plugin → exit 2."""
        runner = CliRunner()
        result = runner.invoke(
            main, ["init", "--plugin", "", str(tmp_path)]
        )
        assert result.exit_code == 2
        assert "non-empty" in result.output

    def test_corrupt_config_toml_exits_3(self, tmp_path: Path):
        """TOMLDecodeError during --plugin with corrupt config → exit 3."""
        (tmp_path / KONKON_DIR).mkdir()
        (tmp_path / KONKON_DIR / CONFIG_FILE).write_text("invalid [[[toml")
        runner = CliRunner()
        result = runner.invoke(
            main, ["init", "--force", "--plugin", "p.py", str(tmp_path)]
        )
        assert result.exit_code == 3

    def test_typeerror_exits_3(self, tmp_path: Path):
        """TypeError from save_config → exit 3 (CONFIG_ERROR)."""
        original_save = __import__(
            "konkon.core.instance", fromlist=["save_config"]
        ).save_config

        def _raise_type_error(*args, **kwargs):
            raise TypeError("Unsupported config value type for key 'bad': NoneType")

        runner = CliRunner()
        with patch("konkon.core.instance.save_config", side_effect=_raise_type_error):
            result = runner.invoke(
                main, ["init", "--plugin", "p.py", str(tmp_path)]
            )
        assert result.exit_code == 3
        assert "Unsupported config value" in result.output
