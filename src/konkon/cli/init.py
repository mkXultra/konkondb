"""konkon init — Create a konkon project (system-level, no Bounded Context)."""

import sys
from pathlib import Path

import click

from konkon.core.instance import init_project


def register(group: click.Group) -> None:
    """Register the init command to the CLI group."""
    group.add_command(init)


@click.command(short_help="Create a konkon project")
@click.argument("directory", default=".", type=click.Path())
@click.option("--force", is_flag=True, help="Overwrite existing konkon.py")
def init(directory: str, force: bool) -> None:
    """Create a konkon project in the specified directory.

    Generates konkon.py template and .konkon/ directory.
    Raw DB is NOT created here — it is lazily initialized on first insert.
    """
    try:
        init_project(Path(directory).resolve(), force=force)
    except FileExistsError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    click.echo(f"Initialized konkon project in {Path(directory).resolve()}", err=True)
