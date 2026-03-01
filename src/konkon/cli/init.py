"""konkon init — Create a konkon project (system-level, no Bounded Context)."""

import sys
import tomllib
from pathlib import Path

import click

from konkon.application import init as app_init


def register(group: click.Group) -> None:
    """Register the init command to the CLI group."""
    group.add_command(init)


@click.command(short_help="Create a konkon project")
@click.argument("directory", default=".", type=click.Path())
@click.option("--force", is_flag=True, help="Overwrite existing plugin file")
@click.option(
    "--plugin",
    default=None,
    help="Plugin template path (relative to DIRECTORY).",
)
def init(directory: str, force: bool, plugin: str | None) -> None:
    """Create a konkon project in the specified directory.

    Generates plugin template and .konkon/ directory.
    Raw DB is NOT created here — it is lazily initialized on first insert.
    """
    try:
        app_init(Path(directory).resolve(), force=force, plugin=plugin)
    except tomllib.TOMLDecodeError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(3)
    except TypeError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(3)
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(2)
    except FileExistsError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(2)
    click.echo(f"Initialized konkon project in {Path(directory).resolve()}", err=True)
