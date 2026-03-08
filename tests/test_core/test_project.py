"""Tests for core/instance.py — init_project and config utilities."""

import tomllib
from pathlib import Path

import pytest

from konkon.core.instance import (
    CONFIG_FILE,
    KONKON_DIR,
    PLUGIN_FILE,
    config_path,
    init_project,
    load_config,
    resolve_plugin_path,
    resolve_project,
    save_config,
)


class TestInitProject:
    """init_project(directory, force) — system-level project initialization."""

    def test_creates_konkon_dir(self, tmp_path: Path):
        """init_project creates .konkon/ directory."""
        init_project(tmp_path, force=False)
        assert (tmp_path / KONKON_DIR).is_dir()

    def test_creates_konkon_py(self, tmp_path: Path):
        """init_project creates konkon.py with plugin template."""
        init_project(tmp_path, force=False)
        plugin = tmp_path / PLUGIN_FILE
        assert plugin.is_file()
        content = plugin.read_text()
        assert "def schema(" in content
        assert "def build(" in content
        assert "def query(" in content

    def test_template_imports_types(self, tmp_path: Path):
        """konkon.py template imports from konkon.types."""
        init_project(tmp_path, force=False)
        content = (tmp_path / PLUGIN_FILE).read_text()
        assert "from konkon.types import" in content
        assert "RawDataAccessor" in content
        assert "QueryRequest" in content
        assert "QueryResult" in content

    def test_existing_konkon_py_raises_error(self, tmp_path: Path):
        """init_project raises FileExistsError when konkon.py already exists."""
        (tmp_path / PLUGIN_FILE).write_text("existing")
        with pytest.raises(FileExistsError):
            init_project(tmp_path, force=False)

    def test_force_overwrites_konkon_py(self, tmp_path: Path):
        """init_project with force=True overwrites existing konkon.py."""
        (tmp_path / PLUGIN_FILE).write_text("old content")
        init_project(tmp_path, force=True)
        content = (tmp_path / PLUGIN_FILE).read_text()
        assert "def build(" in content
        assert "old content" not in content

    def test_konkon_dir_idempotent(self, tmp_path: Path):
        """.konkon/ already exists — no error, directory preserved."""
        (tmp_path / KONKON_DIR).mkdir()
        (tmp_path / KONKON_DIR / "some_file").write_text("keep me")
        init_project(tmp_path, force=False)
        assert (tmp_path / KONKON_DIR / "some_file").read_text() == "keep me"

    def test_does_not_create_raw_db(self, tmp_path: Path):
        """Lazy init: raw.db must NOT be created during init."""
        init_project(tmp_path, force=False)
        assert not (tmp_path / KONKON_DIR / "raw.db").exists()

    def test_creates_directory_if_not_exists(self, tmp_path: Path):
        """DIRECTORY argument that doesn't exist yet is created."""
        target = tmp_path / "new_project"
        init_project(target, force=False)
        assert target.is_dir()
        assert (target / PLUGIN_FILE).is_file()
        assert (target / KONKON_DIR).is_dir()


class TestInitProjectPlugin:
    """init_project with plugin= argument."""

    def test_plugin_writes_config_only(self, tmp_path: Path):
        """--plugin src/my_plugin.py → config.toml only, no template generated."""
        init_project(tmp_path, plugin="src/my_plugin.py")
        assert not (tmp_path / "src" / "my_plugin.py").exists()
        assert not (tmp_path / PLUGIN_FILE).exists()
        cfg = load_config(tmp_path)
        assert cfg["plugin"] == "src/my_plugin.py"

    def test_plugin_writes_config_toml(self, tmp_path: Path):
        """--plugin writes plugin key to .konkon/config.toml."""
        init_project(tmp_path, plugin="src/my_plugin.py")
        cfg = load_config(tmp_path)
        assert cfg["plugin"] == "src/my_plugin.py"

    def test_plugin_preserves_existing_config_keys(self, tmp_path: Path):
        """--plugin merges into existing config.toml (load → merge → save)."""
        (tmp_path / KONKON_DIR).mkdir()
        (tmp_path / KONKON_DIR / CONFIG_FILE).write_text("log_level = 'debug'\n")
        init_project(tmp_path, plugin="custom.py")
        cfg = load_config(tmp_path)
        assert cfg["plugin"] == "custom.py"
        assert cfg["log_level"] == "debug"

    def test_plugin_force_ignored(self, tmp_path: Path):
        """--plugin with --force does not generate template; force is ignored."""
        (tmp_path / KONKON_DIR).mkdir()
        custom = tmp_path / "custom.py"
        custom.write_text("old")
        init_project(tmp_path, force=True, plugin="custom.py")
        # Template not generated — existing file untouched
        assert custom.read_text() == "old"
        cfg = load_config(tmp_path)
        assert cfg["plugin"] == "custom.py"

    def test_plugin_absolute_path_raises(self, tmp_path: Path):
        """Absolute path for plugin raises ValueError."""
        with pytest.raises(ValueError, match="relative path"):
            init_project(tmp_path, plugin="/absolute/path.py")

    def test_plugin_parent_traversal_raises(self, tmp_path: Path):
        """Path with .. raises ValueError."""
        with pytest.raises(ValueError, match="within the project"):
            init_project(tmp_path, plugin="../outside.py")

    def test_plugin_single_quote_raises(self, tmp_path: Path):
        """Path containing single quote raises ValueError."""
        with pytest.raises(ValueError, match="single quotes"):
            init_project(tmp_path, plugin="it's_plugin.py")

    def test_plugin_empty_string_raises(self, tmp_path: Path):
        """Empty string plugin raises ValueError."""
        with pytest.raises(ValueError, match="non-empty"):
            init_project(tmp_path, plugin="")

    def test_plugin_none_uses_default(self, tmp_path: Path):
        """plugin=None → same as no --plugin (creates konkon.py)."""
        init_project(tmp_path, plugin=None)
        assert (tmp_path / PLUGIN_FILE).is_file()
        assert not (tmp_path / KONKON_DIR / CONFIG_FILE).exists()


class TestLoadConfig:
    """load_config(project_root) — read .konkon/config.toml."""

    def test_missing_file_returns_empty_dict(self, tmp_path: Path):
        """No config.toml → empty dict."""
        (tmp_path / KONKON_DIR).mkdir()
        assert load_config(tmp_path) == {}

    def test_reads_valid_toml(self, tmp_path: Path):
        """Parses valid TOML and returns dict."""
        (tmp_path / KONKON_DIR).mkdir()
        (tmp_path / KONKON_DIR / CONFIG_FILE).write_text(
            "plugin = 'src/my_plugin.py'\n"
        )
        cfg = load_config(tmp_path)
        assert cfg == {"plugin": "src/my_plugin.py"}

    def test_preserves_unknown_keys(self, tmp_path: Path):
        """Unknown keys are preserved in returned dict."""
        (tmp_path / KONKON_DIR).mkdir()
        (tmp_path / KONKON_DIR / CONFIG_FILE).write_text(
            "plugin = 'p.py'\nfuture_key = 42\n"
        )
        cfg = load_config(tmp_path)
        assert cfg["future_key"] == 42

    def test_invalid_toml_raises(self, tmp_path: Path):
        """Invalid TOML → TOMLDecodeError."""
        (tmp_path / KONKON_DIR).mkdir()
        (tmp_path / KONKON_DIR / CONFIG_FILE).write_text("invalid [[[toml")
        with pytest.raises(tomllib.TOMLDecodeError):
            load_config(tmp_path)


class TestSaveConfig:
    """save_config(project_root, config) — write .konkon/config.toml."""

    def test_writes_string_value(self, tmp_path: Path):
        """String value is written as TOML literal string."""
        (tmp_path / KONKON_DIR).mkdir()
        save_config(tmp_path, {"plugin": "src/p.py"})
        raw = (tmp_path / KONKON_DIR / CONFIG_FILE).read_text()
        assert "plugin = 'src/p.py'" in raw
        # Verify round-trip
        cfg = load_config(tmp_path)
        assert cfg["plugin"] == "src/p.py"

    def test_writes_bool_value(self, tmp_path: Path):
        """Bool values are serialized correctly."""
        (tmp_path / KONKON_DIR).mkdir()
        save_config(tmp_path, {"verbose": True, "quiet": False})
        cfg = load_config(tmp_path)
        assert cfg["verbose"] is True
        assert cfg["quiet"] is False

    def test_writes_int_value(self, tmp_path: Path):
        """Int values are serialized correctly."""
        (tmp_path / KONKON_DIR).mkdir()
        save_config(tmp_path, {"count": 42})
        cfg = load_config(tmp_path)
        assert cfg["count"] == 42

    def test_writes_float_value(self, tmp_path: Path):
        """Float values are serialized correctly."""
        (tmp_path / KONKON_DIR).mkdir()
        save_config(tmp_path, {"ratio": 3.14})
        cfg = load_config(tmp_path)
        assert cfg["ratio"] == 3.14

    def test_preserves_existing_scalar_keys(self, tmp_path: Path):
        """load → merge → save preserves existing scalar keys."""
        (tmp_path / KONKON_DIR).mkdir()
        save_config(tmp_path, {"existing": "keep", "plugin": "old.py"})
        existing = load_config(tmp_path)
        existing["plugin"] = "new.py"
        save_config(tmp_path, existing)
        cfg = load_config(tmp_path)
        assert cfg["existing"] == "keep"
        assert cfg["plugin"] == "new.py"

    def test_skips_list_with_warning(self, tmp_path: Path, capsys):
        """List values are skipped with warning to stderr."""
        (tmp_path / KONKON_DIR).mkdir()
        save_config(tmp_path, {"tags": [1, 2], "plugin": "p.py"})
        cfg = load_config(tmp_path)
        assert "tags" not in cfg
        assert cfg["plugin"] == "p.py"
        captured = capsys.readouterr()
        assert "Skipping" in captured.err
        assert "tags" in captured.err

    def test_skips_dict_with_warning(self, tmp_path: Path, capsys):
        """Dict values are skipped with warning to stderr."""
        (tmp_path / KONKON_DIR).mkdir()
        save_config(tmp_path, {"nested": {"a": 1}, "plugin": "p.py"})
        cfg = load_config(tmp_path)
        assert "nested" not in cfg
        captured = capsys.readouterr()
        assert "Skipping" in captured.err

    def test_raises_typeerror_for_none(self, tmp_path: Path):
        """None value raises TypeError."""
        (tmp_path / KONKON_DIR).mkdir()
        with pytest.raises(TypeError):
            save_config(tmp_path, {"bad": None})

    def test_bool_before_int(self, tmp_path: Path):
        """Bool is not confused with int (bool is subclass of int in Python)."""
        (tmp_path / KONKON_DIR).mkdir()
        save_config(tmp_path, {"flag": True, "count": 1})
        cfg = load_config(tmp_path)
        assert cfg["flag"] is True  # not 1
        assert cfg["count"] == 1

    def test_skips_datetime_with_warning(self, tmp_path: Path, capsys):
        """Datetime values are skipped with warning to stderr."""
        from datetime import datetime

        (tmp_path / KONKON_DIR).mkdir()
        save_config(tmp_path, {"ts": datetime(2024, 1, 1), "plugin": "p.py"})
        cfg = load_config(tmp_path)
        assert "ts" not in cfg
        assert cfg["plugin"] == "p.py"
        captured = capsys.readouterr()
        assert "Skipping" in captured.err

    def test_skips_date_with_warning(self, tmp_path: Path, capsys):
        """Date values are skipped with warning to stderr."""
        from datetime import date

        (tmp_path / KONKON_DIR).mkdir()
        save_config(tmp_path, {"d": date(2024, 1, 1), "plugin": "p.py"})
        cfg = load_config(tmp_path)
        assert "d" not in cfg
        captured = capsys.readouterr()
        assert "Skipping" in captured.err

    def test_raises_typeerror_for_nan(self, tmp_path: Path):
        """float('nan') raises TypeError (non-finite)."""
        (tmp_path / KONKON_DIR).mkdir()
        with pytest.raises(TypeError, match="non-finite"):
            save_config(tmp_path, {"bad": float("nan")})

    def test_raises_typeerror_for_inf(self, tmp_path: Path):
        """float('inf') raises TypeError (non-finite)."""
        (tmp_path / KONKON_DIR).mkdir()
        with pytest.raises(TypeError, match="non-finite"):
            save_config(tmp_path, {"bad": float("inf")})

    def test_skips_single_quote_string_with_warning(self, tmp_path: Path, capsys):
        """String containing single quote is skipped with warning."""
        (tmp_path / KONKON_DIR).mkdir()
        save_config(tmp_path, {"key": "it's broken", "ok": "fine"})
        cfg = load_config(tmp_path)
        assert "key" not in cfg
        assert cfg["ok"] == "fine"
        captured = capsys.readouterr()
        assert "Skipping" in captured.err
        assert "single quote" in captured.err

    def test_skips_newline_string_with_warning(self, tmp_path: Path, capsys):
        """String containing newline is skipped with warning."""
        (tmp_path / KONKON_DIR).mkdir()
        save_config(tmp_path, {"key": "line1\nline2", "ok": "fine"})
        cfg = load_config(tmp_path)
        assert "key" not in cfg
        assert cfg["ok"] == "fine"
        captured = capsys.readouterr()
        assert "Skipping" in captured.err
        assert "newline" in captured.err

    def test_skips_carriage_return_string_with_warning(self, tmp_path: Path, capsys):
        """String containing carriage return is skipped with warning."""
        (tmp_path / KONKON_DIR).mkdir()
        save_config(tmp_path, {"key": "line1\rline2", "ok": "fine"})
        cfg = load_config(tmp_path)
        assert "key" not in cfg
        assert cfg["ok"] == "fine"
        captured = capsys.readouterr()
        assert "Skipping" in captured.err
        assert "newline" in captured.err


class TestConfigPath:
    """config_path(project_root) — return path to config.toml."""

    def test_returns_correct_path(self, tmp_path: Path):
        assert config_path(tmp_path) == tmp_path / KONKON_DIR / CONFIG_FILE


class TestResolvePluginPath:
    """resolve_plugin_path — 4-level priority resolution."""

    def test_cli_arg_wins(self, tmp_path: Path):
        """Priority 1: CLI --plugin argument."""
        plugin = tmp_path / "cli_plugin.py"
        plugin.write_text("# plugin")
        result = resolve_plugin_path(tmp_path, cli_plugin=plugin)
        assert result == plugin

    def test_env_wins_over_config(self, tmp_path: Path, monkeypatch):
        """Priority 2: KONKON_PLUGIN env > config.toml."""
        (tmp_path / KONKON_DIR).mkdir()
        env_plugin = tmp_path / "env_plugin.py"
        env_plugin.write_text("# plugin")
        save_config(tmp_path, {"plugin": "config_plugin.py"})
        (tmp_path / "config_plugin.py").write_text("# config")
        monkeypatch.setenv("KONKON_PLUGIN", str(env_plugin))
        result = resolve_plugin_path(tmp_path)
        assert result == env_plugin

    def test_config_wins_over_fallback(self, tmp_path: Path, monkeypatch):
        """Priority 3: config.toml > fallback konkon.py."""
        monkeypatch.delenv("KONKON_PLUGIN", raising=False)
        (tmp_path / KONKON_DIR).mkdir()
        (tmp_path / "custom.py").write_text("# custom")
        (tmp_path / PLUGIN_FILE).write_text("# default")
        save_config(tmp_path, {"plugin": "custom.py"})
        result = resolve_plugin_path(tmp_path)
        assert result == tmp_path / "custom.py"

    def test_fallback_to_konkon_py(self, tmp_path: Path, monkeypatch):
        """Priority 4: fallback to konkon.py when nothing else is set."""
        monkeypatch.delenv("KONKON_PLUGIN", raising=False)
        (tmp_path / KONKON_DIR).mkdir()
        (tmp_path / PLUGIN_FILE).write_text("# default")
        result = resolve_plugin_path(tmp_path)
        assert result == tmp_path / PLUGIN_FILE

    def test_config_relative_resolved_against_project_root(
        self, tmp_path: Path, monkeypatch
    ):
        """config.toml path is resolved relative to project root."""
        monkeypatch.delenv("KONKON_PLUGIN", raising=False)
        (tmp_path / KONKON_DIR).mkdir()
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "p.py").write_text("# plugin")
        save_config(tmp_path, {"plugin": "src/p.py"})
        result = resolve_plugin_path(tmp_path)
        assert result == tmp_path / "src" / "p.py"

    def test_env_relative_resolved_against_cwd(self, tmp_path: Path, monkeypatch):
        """KONKON_PLUGIN relative path is resolved against CWD."""
        monkeypatch.delenv("KONKON_PLUGIN", raising=False)
        (tmp_path / KONKON_DIR).mkdir()
        plugin = tmp_path / "env_rel.py"
        plugin.write_text("# plugin")
        monkeypatch.setenv("KONKON_PLUGIN", "env_rel.py")
        monkeypatch.chdir(tmp_path)
        result = resolve_plugin_path(tmp_path)
        assert result == plugin.resolve()

    def test_nonexistent_path_raises(self, tmp_path: Path, monkeypatch):
        """Resolved path that doesn't exist raises FileNotFoundError."""
        monkeypatch.delenv("KONKON_PLUGIN", raising=False)
        (tmp_path / KONKON_DIR).mkdir()
        # No konkon.py or config → fallback to nonexistent konkon.py
        with pytest.raises(FileNotFoundError):
            resolve_plugin_path(tmp_path)

    def test_config_plugin_non_string_raises(self, tmp_path: Path, monkeypatch):
        """config.toml plugin value that is not str raises ValueError."""
        monkeypatch.delenv("KONKON_PLUGIN", raising=False)
        (tmp_path / KONKON_DIR).mkdir()
        # Write integer value manually
        (tmp_path / KONKON_DIR / CONFIG_FILE).write_text("plugin = 42\n")
        with pytest.raises(ValueError, match="must be a string"):
            resolve_plugin_path(tmp_path)


class TestResolveProjectWithKonkonDir:
    """resolve_project now also detects .konkon/ directory."""

    def test_finds_by_konkon_dir(self, tmp_path: Path):
        """Project with .konkon/ but no konkon.py is found."""
        (tmp_path / KONKON_DIR).mkdir()
        result = resolve_project(tmp_path)
        assert result == tmp_path

    def test_finds_by_konkon_py(self, tmp_path: Path):
        """Backward compat: project with konkon.py is still found."""
        (tmp_path / PLUGIN_FILE).write_text("# plugin")
        result = resolve_project(tmp_path)
        assert result == tmp_path

    def test_neither_raises(self, tmp_path: Path):
        """No .konkon/ or konkon.py → FileNotFoundError."""
        child = tmp_path / "deep" / "nested"
        child.mkdir(parents=True)
        with pytest.raises(FileNotFoundError, match="konkon project not found"):
            resolve_project(child)
