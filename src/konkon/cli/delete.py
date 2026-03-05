"""konkon delete — Delete a Raw Record (Ingestion Context)."""

import sys
from pathlib import Path

import click

from konkon.application import delete as app_delete
from konkon.core.instance import resolve_project
from konkon.core.models import ConfigError


def _is_tty() -> bool:
    """Check if both stdin and stderr are TTY (for confirmation prompt)."""
    return sys.stdin.isatty() and sys.stderr.isatty()


def register(group: click.Group) -> None:
    """Register the delete command to the CLI group."""
    group.add_command(delete_cmd)


@click.command("delete", short_help="Delete a Raw Record by ID")
@click.argument("record_id")
@click.option(
    "--force", "-f",
    is_flag=True,
    default=False,
    help="Skip confirmation prompt.",
)
@click.pass_context
def delete_cmd(
    ctx: click.Context,
    record_id: str,
    force: bool,
) -> None:
    """Delete a Raw Record by ID.

    Physically deletes the record from Raw DB and creates a tombstone
    for the next build. Run 'konkon build' after deleting to update
    the Context Store.

    \b
    Example:
      konkon delete 019516a0-3b40-7f8a-b12c-4e5f6a7b8c9d
      konkon delete --force 019516a0-3b40-7f8a-b12c-4e5f6a7b8c9d
    """
    try:
        project_dir = ctx.obj.get("project_dir") if ctx.obj else None
        start = Path(project_dir) if project_dir else None
        project_root = resolve_project(start)
    except (FileNotFoundError, ConfigError) as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(3)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    # Confirmation prompt (delete.md §振る舞い step 3)
    if not force:
        if _is_tty():
            click.echo(
                f"Delete record {record_id}? [y/N] ",
                err=True,
                nl=False,
            )
            try:
                answer = input().strip().lower()
            except EOFError:
                sys.exit(0)
            if answer not in ("y", "yes"):
                sys.exit(0)
        # Non-TTY without --force: stdin or stderr is not TTY
        # Per spec: "stdin または stderr が TTY でない場合は --force が暗黙的に適用される"
        # So we proceed without prompting.

    try:
        app_delete(record_id, project_root)
        click.echo(record_id)
        click.echo(
            "[INFO] Record deleted. Run 'konkon build' to update Context Store.",
            err=True,
        )
    except KeyError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except ConfigError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(3)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
