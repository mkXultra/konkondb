"""konkon build — Run build() from konkon.py (Transformation Context)."""

import sys

import click

from konkon.application import build as app_build
from konkon.cli.common import runtime_session
from konkon.core.models import ConfigError


def register(group: click.Group) -> None:
    """Register the build command to the CLI group."""
    group.add_command(build)


@click.command(short_help="Transform Raw DB data via build() in konkon.py")
@click.option(
    "--full",
    is_flag=True,
    default=False,
    help="Full rebuild (default: incremental since last build).",
)
@click.pass_context
def build(ctx: click.Context, full: bool) -> None:
    """Transform Raw DB data via build() in konkon.py to produce AI-ready context.

    By default, runs an incremental build (only records modified since the last
    build). Use --full to rebuild from all records.

    Delegates to Application Layer Use Case.
    """
    try:
        with runtime_session(ctx, needs_connection=True) as (runtime, manager):
            app_build(
                full=full,
                runtime=runtime,
                connection_manager=manager,
            )
    except FileNotFoundError as e:
        click.echo(str(e), err=True)
        sys.exit(1)
    except ConfigError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(3)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
