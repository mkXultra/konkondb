"""konkon setup-db — Bootstrap postgres schema and tables."""

import sys

import click

from konkon.application import setup_db as app_setup_db
from konkon.cli.common import runtime_session
from konkon.core.models import ConfigError


def register(group: click.Group) -> None:
    """Register the setup-db command to the CLI group."""
    group.add_command(setup_db)


@click.command("setup-db", short_help="Create postgres schema/tables for konkon")
@click.pass_context
def setup_db(ctx: click.Context) -> None:
    """Create the schema and tables required by the postgres backend."""
    try:
        with runtime_session(ctx, needs_connection=True, require_plugin=False) as (runtime, manager):
            app_setup_db(runtime=runtime, connection_manager=manager)
        click.echo("[INFO] Postgres schema/bootstrap completed.", err=True)
    except ConfigError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(3)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
