"""konkon update — Update an existing Raw Record (Ingestion Context)."""

import sys
from pathlib import Path

import click

from konkon.application import update as app_update
from konkon.core.instance import resolve_project


def _parse_meta(
    _ctx: click.Context, _param: click.Parameter, value: tuple[str, ...]
) -> dict[str, str]:
    """Parse KEY=VALUE pairs into a dict."""
    result: dict[str, str] = {}
    for item in value:
        if "=" not in item:
            raise click.BadParameter(f"expected KEY=VALUE, got {item!r}")
        key, val = item.split("=", 1)
        result[key] = val
    return result


def register(group: click.Group) -> None:
    """Register the update command to the CLI group."""
    group.add_command(update_cmd)


@click.command("update", short_help="Update an existing Raw Record")
@click.argument("record_id")
@click.option(
    "--content",
    type=str,
    default=None,
    help="New content for the record.",
)
@click.option(
    "-m",
    "--meta",
    "meta",
    multiple=True,
    callback=_parse_meta,
    expose_value=True,
    help="Metadata as KEY=VALUE (repeatable).",
)
@click.pass_context
def update_cmd(
    ctx: click.Context,
    record_id: str,
    content: str | None,
    meta: dict[str, str],
) -> None:
    """Update content and/or meta of an existing Raw Record by ID.

    At least one of --content or --meta must be provided.

    \b
    Example:
      konkon update 019516a0-3b40-... --content "new text"
      konkon update 019516a0-3b40-... -m source_uri=/path/to/new.md
    """
    if content is None and not meta:
        click.echo("Error: at least one of --content or --meta is required.", err=True)
        sys.exit(2)

    try:
        project_dir = ctx.obj.get("project_dir") if ctx.obj else None
        start = Path(project_dir) if project_dir else None
        project_root = resolve_project(start)
        record = app_update(
            record_id,
            content=content,
            meta=meta or None,
            project_root=project_root,
        )
        click.echo(record.id)
    except KeyError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
