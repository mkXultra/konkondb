"""Tests for CLI framework (Step 4) and konkon help (Step 5)."""

from click.testing import CliRunner

from konkon.cli import main


class TestCLIFramework:
    """Step 4: Click group entry point."""

    def test_main_no_args_shows_help(self):
        runner = CliRunner()
        result = runner.invoke(main, [])
        assert result.exit_code == 0
        assert "konkon db" in result.output

    def test_main_help_flag(self):
        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "konkon db" in result.output


class TestHelpCommand:
    """Step 5: konkon help [COMMAND] (04_cli_design.md §4.0)."""

    def test_help_no_args_shows_commands(self):
        """konkon help — shows all commands overview."""
        runner = CliRunner()
        result = runner.invoke(main, ["help"])
        assert result.exit_code == 0
        assert "help" in result.output

    def test_help_is_equivalent_to_dash_dash_help(self):
        """konkon help output should match konkon --help."""
        runner = CliRunner()
        help_result = runner.invoke(main, ["help"])
        flag_result = runner.invoke(main, ["--help"])
        assert help_result.exit_code == 0
        assert help_result.output == flag_result.output

    def test_help_specific_command(self):
        """konkon help <command> — shows detailed help for that command."""
        runner = CliRunner()
        result = runner.invoke(main, ["help", "help"])
        assert result.exit_code == 0
        assert "COMMAND" in result.output

    def test_help_unknown_command_exit_2(self):
        """konkon help <unknown> — exit code 2."""
        runner = CliRunner()
        result = runner.invoke(main, ["help", "nonexistent"])
        assert result.exit_code == 2

    def test_help_output_to_stdout(self):
        """Help text goes to stdout (pipe-friendly)."""
        runner = CliRunner()
        result = runner.invoke(main, ["help"])
        assert result.exit_code == 0
        assert len(result.output) > 0
