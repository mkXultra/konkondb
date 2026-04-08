"""Tests for runtime config and postgres credential resolution."""

from pathlib import Path

import pytest

from konkon.core.instance import (
    DEFAULT_POSTGRES_DSN_ENV,
    load_runtime_config,
    load_runtime_config_file,
    resolve_postgres_dsn,
)
from konkon.core.models import ConfigError


class TestStatelessRuntimeConfig:
    def test_file_config_resolves_relative_paths(self, tmp_path: Path):
        plugin_dir = tmp_path / "plugins"
        import_root = tmp_path / "src"
        plugin_dir.mkdir()
        import_root.mkdir()
        plugin_path = plugin_dir / "plugin.py"
        plugin_path.write_text("def schema(): return {}\ndef build(raw_data, context): pass\ndef query(request): return ''\n")
        config_path = tmp_path / "konkon.toml"
        config_path.write_text(
            "\n".join(
                [
                    "raw_backend = 'postgres'",
                    "plugin = 'plugins/plugin.py'",
                    "import_root = 'src'",
                    "schema = 'konkon'",
                    "build_state_key = 'dataset-a'",
                ]
            )
            + "\n"
        )

        runtime = load_runtime_config_file(config_path)

        assert runtime.mode == "stateless"
        assert runtime.raw_backend == "postgres"
        assert runtime.plugin_path == plugin_path.resolve()
        assert runtime.import_root == import_root.resolve()
        assert runtime.config_base == tmp_path.resolve()
        assert runtime.build_state_key == "dataset-a"

    def test_file_config_rejects_config_base(self, tmp_path: Path):
        plugin_path = tmp_path / "plugin.py"
        plugin_path.write_text("def schema(): return {}\ndef build(raw_data, context): pass\ndef query(request): return ''\n")
        config_path = tmp_path / "konkon.toml"
        config_path.write_text(
            "\n".join(
                [
                    "raw_backend = 'postgres'",
                    "plugin = 'plugin.py'",
                    "config_base = '/app'",
                ]
            )
            + "\n"
        )

        with pytest.raises(ConfigError, match="config_base"):
            load_runtime_config_file(config_path)

    def test_in_memory_config_requires_config_base_for_relative_plugin(self, tmp_path: Path):
        with pytest.raises(ConfigError, match="config_base"):
            load_runtime_config(
                {
                    "raw_backend": "postgres",
                    "plugin": "relative/plugin.py",
                }
            )

    def test_in_memory_config_uses_config_base(self, tmp_path: Path):
        plugin_dir = tmp_path / "plugins"
        plugin_dir.mkdir()
        plugin_path = plugin_dir / "plugin.py"
        plugin_path.write_text("def schema(): return {}\ndef build(raw_data, context): pass\ndef query(request): return ''\n")

        runtime = load_runtime_config(
            {
                "raw_backend": "postgres",
                "config_base": str(tmp_path),
                "plugin": "plugins/plugin.py",
                "schema": "konkon",
            }
        )

        assert runtime.plugin_path == plugin_path.resolve()
        assert runtime.config_base == tmp_path.resolve()


class TestPostgresDsnResolution:
    def test_explicit_dsn_wins(self, tmp_path: Path, monkeypatch):
        plugin = tmp_path / "plugin.py"
        plugin.write_text("def schema(): return {}\ndef build(raw_data, context): pass\ndef query(request): return ''\n")
        runtime = load_runtime_config(
            {
                "raw_backend": "postgres",
                "config_base": str(tmp_path),
                "plugin": str(plugin.resolve()),
            }
        )
        monkeypatch.setenv(DEFAULT_POSTGRES_DSN_ENV, "postgresql://default")

        resolved = resolve_postgres_dsn(runtime, dsn="postgresql://explicit")

        assert resolved == "postgresql://explicit"

    def test_named_env_wins_over_default_env(self, tmp_path: Path, monkeypatch):
        plugin = tmp_path / "plugin.py"
        plugin.write_text("def schema(): return {}\ndef build(raw_data, context): pass\ndef query(request): return ''\n")
        runtime = load_runtime_config(
            {
                "raw_backend": "postgres",
                "plugin": str(plugin.resolve()),
                "dsn_env": "MY_RUNTIME_DSN",
            }
        )
        monkeypatch.setenv("MY_RUNTIME_DSN", "postgresql://named")
        monkeypatch.setenv(DEFAULT_POSTGRES_DSN_ENV, "postgresql://default")

        assert resolve_postgres_dsn(runtime) == "postgresql://named"

    def test_default_env_is_fallback(self, tmp_path: Path, monkeypatch):
        plugin = tmp_path / "plugin.py"
        plugin.write_text("def schema(): return {}\ndef build(raw_data, context): pass\ndef query(request): return ''\n")
        runtime = load_runtime_config(
            {
                "raw_backend": "postgres",
                "plugin": str(plugin.resolve()),
            }
        )
        monkeypatch.setenv(DEFAULT_POSTGRES_DSN_ENV, "postgresql://default")

        assert resolve_postgres_dsn(runtime) == "postgresql://default"
