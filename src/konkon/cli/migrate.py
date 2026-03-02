"""konkon migrate — Migrate Raw DB between backends."""

import sys
import tomllib
from pathlib import Path

import click

from konkon.application import migrate as app_migrate
from konkon.core.instance import resolve_project
from konkon.core.models import ConfigError


def register(group: click.Group) -> None:
    """Register the migrate command to the CLI group."""
    group.add_command(migrate)


@click.command(short_help="Migrate Raw DB to a different backend")
@click.option(
    "--to",
    "target_backend",
    required=True,
    type=click.Choice(["sqlite", "json"], case_sensitive=False),
    help="Target backend to migrate to.",
)
@click.option(
    "--force",
    is_flag=True,
    default=False,
    help="Overwrite existing target file.",
)
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["text", "json"]),
    default=None,
    hidden=True,
    help="Accepted for consistency but ignored.",
)
@click.pass_context
def migrate(ctx: click.Context, target_backend: str, force: bool, fmt: str | None) -> None:
    """Migrate all Raw DB records to a different backend.

    Copies all records preserving id, timestamps, content, and metadata.
    The source file is kept after migration.

    \b
    Examples:
      konkon migrate --to json
      konkon migrate --to sqlite --force
    """
    try:
        project_dir = ctx.obj.get("project_dir") if ctx.obj else None
        start = Path(project_dir) if project_dir else None
        project_root = resolve_project(start)

        count, source_backend = app_migrate(
            target_backend, project_root, force=force,
        )

        # All output to stderr (no data output)
        src_name = "raw.db" if source_backend == "sqlite" else "raw.json"
        click.echo(
            f"[INFO] Migrated {count} records: "
            f"{source_backend} -> {target_backend}",
            err=True,
        )
        click.echo(
            f"[INFO] Updated .konkon/config.toml: "
            f"raw_backend = '{target_backend}'",
            err=True,
        )
        click.echo(
            f"[INFO] Source file .konkon/{src_name} preserved",
            err=True,
        )

    except FileNotFoundError as e:
        click.echo(str(e), err=True)
        sys.exit(3)
    except FileExistsError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except (ConfigError, tomllib.TOMLDecodeError) as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(3)
    except click.UsageError:
        raise  # click handles exit 2
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
