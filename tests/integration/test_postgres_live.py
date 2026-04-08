"""Live Postgres integration test using Testcontainers.

This test is skipped unless:
- the postgres test dependencies are installed
- Docker is available to Testcontainers
- KONKON_RUN_PG_LIVE=1 is set
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from click.testing import CliRunner

from konkon.cli import main


def _have_live_postgres_deps() -> bool:
    try:
        import psycopg  # noqa: F401
        from testcontainers.postgres import PostgresContainer  # noqa: F401
    except Exception:
        return False
    return True


def _postgres_dsn(container: object) -> str:
    raw_url = getattr(container, "get_connection_url", lambda: None)()
    if raw_url:
        return raw_url.replace("postgresql+psycopg2://", "postgresql://", 1)

    host = container.get_container_host_ip()
    port = container.get_exposed_port(5432)
    username = getattr(container, "username", None) or getattr(container, "user", None)
    password = getattr(container, "password", None)
    dbname = getattr(container, "dbname", None) or getattr(container, "db", None)
    if not all([host, port, username, password, dbname]):
        raise RuntimeError("Unable to construct a Postgres DSN from the container.")
    return f"postgresql://{username}:{password}@{host}:{port}/{dbname}"


def _write_plugin(root: Path) -> None:
    (root / "plugin.py").write_text(
        """\
def schema():
    return {"description": "live pg", "params": {}}

def build(raw_data, context):
    from pathlib import Path
    Path("context.txt").write_text(str(len(list(raw_data))))

def query(request):
    return ""
"""
    )


pytestmark = [
    pytest.mark.postgres_live,
    pytest.mark.skipif(
        not _have_live_postgres_deps(),
        reason="psycopg and testcontainers must be installed for live Postgres tests",
    ),
    pytest.mark.skipif(
        not os.environ.get("KONKON_RUN_PG_LIVE"),
        reason="set KONKON_RUN_PG_LIVE=1 to enable live Postgres tests",
    ),
]


def test_postgres_live_cli_workflow(tmp_path: Path) -> None:
    """Exercise setup-db, insert, raw reads, and build-state against real Postgres."""
    import psycopg
    from testcontainers.postgres import PostgresContainer

    runner = CliRunner()
    _write_plugin(tmp_path)
    config_path = tmp_path / "konkon.toml"
    config_path.write_text(
        "\n".join(
            [
                "raw_backend = 'postgres'",
                "plugin = 'plugin.py'",
                "schema = 'konkon_live'",
            ]
        )
        + "\n"
    )

    with PostgresContainer("postgres:16") as container:
        dsn = _postgres_dsn(container)

        setup_result = runner.invoke(
            main,
            ["--config", str(config_path), "--raw-dsn", dsn, "setup-db"],
        )
        assert setup_result.exit_code == 0, setup_result.output

        insert_result = runner.invoke(
            main,
            [
                "--config",
                str(config_path),
                "--raw-dsn",
                dsn,
                "insert",
                "-m",
                "source=it",
                "hello from live pg",
            ],
        )
        assert insert_result.exit_code == 0, insert_result.output
        record_id = insert_result.output.strip()

        list_result = runner.invoke(
            main,
            ["--config", str(config_path), "--raw-dsn", dsn, "raw", "list", "--format", "json"],
        )
        assert list_result.exit_code == 0, list_result.output
        listed = [json.loads(line) for line in list_result.output.splitlines() if line.strip()]
        assert any(item["id"] == record_id for item in listed)

        get_result = runner.invoke(
            main,
            [
                "--config",
                str(config_path),
                "--raw-dsn",
                dsn,
                "raw",
                "get",
                record_id,
                "--format",
                "json",
            ],
        )
        assert get_result.exit_code == 0, get_result.output
        fetched = json.loads(get_result.output)
        assert fetched["id"] == record_id
        assert fetched["content"] == "hello from live pg"

        build_result = runner.invoke(
            main,
            ["--config", str(config_path), "--raw-dsn", dsn, "build", "--full"],
        )
        assert build_result.exit_code == 0, build_result.output
        assert (tmp_path / "context.txt").read_text() == "1"

        with psycopg.connect(dsn) as connection:
            row = connection.execute(
                'SELECT build_state_key, last_build_at FROM "konkon_live"."build_state" '
                "WHERE build_state_key = %s",
                ("default",),
            ).fetchone()
        assert row is not None
        assert row[0] == "default"
        assert row[1] is not None
