"""konkon init — Create a konkon project (system-level, no Bounded Context)."""

import sys
import tomllib
from pathlib import Path

import click

from konkon.application import init as app_init

_VALID_BACKENDS = ("sqlite", "json")


def register(group: click.Group) -> None:
    """Register the init command to the CLI group."""
    group.add_command(init)


@click.command(short_help="Create a konkon project")
@click.argument("directory", default=".", type=click.Path())
@click.option("--force", is_flag=True, help="Overwrite existing konkon.py template")
@click.option(
    "--plugin",
    default=None,
    help="Register plugin path in config (relative to DIRECTORY). No template is generated.",
)
@click.option(
    "--raw-backend",
    default=None,
    help="Raw DB backend ('sqlite' or 'json') [default: sqlite]",
)
def init(directory: str, force: bool, plugin: str | None, raw_backend: str | None) -> None:
    """Create a konkon project in the specified directory.

    Creates .konkon/ directory and a konkon.py plugin template.
    With --plugin, only writes the plugin path to config — no template is generated.
    Raw DB is NOT created here — it is lazily initialized on first insert.
    """
    if raw_backend is not None and raw_backend not in _VALID_BACKENDS:
        click.echo(
            f"Error: Invalid value for '--raw-backend': "
            f"'{raw_backend}' is not one of {', '.join(repr(b) for b in _VALID_BACKENDS)}.",
            err=True,
        )
        sys.exit(2)
    try:
        app_init(
            Path(directory).resolve(),
            force=force,
            plugin=plugin,
            raw_backend=raw_backend,
        )
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
