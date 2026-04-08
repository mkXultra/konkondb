"""CLI tests for stateless mode and postgres setup."""

from pathlib import Path

from click.testing import CliRunner

from konkon.cli import main
from konkon.core.instance import PostgresConnectionManager
from tests.postgres_fakes import FakePostgresConnection


class TestStatelessCli:
    def test_config_and_project_dir_are_mutually_exclusive(self, tmp_path: Path):
        runner = CliRunner()
        config_path = tmp_path / "konkon.toml"
        config_path.write_text("")

        result = runner.invoke(
            main,
            ["-C", str(tmp_path), "--config", str(config_path), "describe"],
        )

        assert result.exit_code == 2
        assert "cannot be used together" in result.output

    def test_describe_supports_stateless_config(self, tmp_path: Path):
        runner = CliRunner()
        plugin_dir = tmp_path / "plugins"
        plugin_dir.mkdir()
        plugin_path = plugin_dir / "plugin.py"
        plugin_path.write_text("""\
def schema():
    return {"description": "stateless plugin", "params": {}}

def build(raw_data, context):
    pass

def query(request):
    return ""
""")
        config_path = tmp_path / "konkon.toml"
        config_path.write_text(
            "\n".join(
                [
                    "raw_backend = 'postgres'",
                    "plugin = 'plugins/plugin.py'",
                    "schema = 'konkon'",
                ]
            )
            + "\n"
        )

        result = runner.invoke(
            main,
            ["--config", str(config_path), "describe", "--format", "json"],
        )

        assert result.exit_code == 0
        assert "stateless plugin" in result.output

    def test_setup_db_uses_stateless_config(self, tmp_path: Path, monkeypatch):
        runner = CliRunner()
        plugin_path = tmp_path / "plugin.py"
        plugin_path.write_text("""\
def schema():
    return {"description": "plugin", "params": {}}

def build(raw_data, context):
    pass

def query(request):
    return ""
""")
        config_path = tmp_path / "konkon.toml"
        config_path.write_text(
            "\n".join(
                [
                    "raw_backend = 'postgres'",
                    "plugin = 'plugin.py'",
                    "schema = 'konkon'",
                ]
            )
            + "\n"
        )
        connection = FakePostgresConnection(schema="konkon")
        connection.schema_exists = False
        monkeypatch.setattr(
            "konkon.cli.common.create_postgres_connection_manager",
            lambda runtime, dsn=None: PostgresConnectionManager(connection=connection),
        )

        result = runner.invoke(
            main,
            ["--config", str(config_path), "setup-db"],
        )

        assert result.exit_code == 0
        assert {"raw_records", "raw_deletions", "build_state"} <= connection.available_tables
