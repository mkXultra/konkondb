"""konkon init — Create a konkon project (system-level, no Bounded Context)."""

from pathlib import Path

import click


def register(group: click.Group) -> None:
    """Register the init command to the CLI group."""
    group.add_command(init)


@click.command(short_help="Create a konkon project in the current directory [not implemented]")
@click.argument("directory", default=".", type=click.Path())
@click.option("--force", is_flag=True, help="Overwrite existing konkon.py")
def init(directory: str, force: bool) -> None:
    """Create a konkon project in the specified directory.

    Generates konkon.py template and .konkon/ directory.
    Raw DB is NOT created here — it is lazily initialized on first insert.
    """
    # TODO: Implement per 04_cli_design.md §4.1
    # - Delegate to core/project.init_project(directory, force)
    raise NotImplementedError
