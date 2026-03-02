"""konkon raw — Raw DB inspection commands (debug / operations)."""

import json
import sys
from pathlib import Path

import click

from konkon.application import raw_get, raw_list
from konkon.core.instance import resolve_project
from konkon.core.models import ConfigError


def register(group: click.Group) -> None:
    """Register the raw command group to the CLI group."""
    group.add_command(raw)


@click.group(short_help="Inspect Raw DB records (debug)")
@click.pass_context
def raw(ctx: click.Context) -> None:
    """Inspect and manage Raw DB records.

    \b
    Subcommands:
      list   List recent raw records
      get    Get a single raw record by ID
    """
    pass


@raw.command("list", short_help="List recent raw records")
@click.option(
    "--limit",
    type=click.IntRange(min=0),
    default=20,
    show_default=True,
    help="Maximum number of records to display.",
)
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["text", "json"]),
    default=None,
    help="Output format (default: auto-detect from TTY).",
)
@click.pass_context
def list_cmd(ctx: click.Context, limit: int, fmt: str | None) -> None:
    """List recent raw records (newest first).

    \b
    Text mode shows a truncated table; JSON mode outputs full records
    as JSON Lines (one JSON object per line).
    """
    try:
        project_dir = ctx.obj.get("project_dir") if ctx.obj else None
        start = Path(project_dir) if project_dir else None
        project_root = resolve_project(start)
    except FileNotFoundError as e:
        click.echo(str(e), err=True)
        sys.exit(3)

    try:
        records = raw_list(project_root, limit=limit)
    except ConfigError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(3)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    if not records:
        return

    # Resolve format: explicit > TTY detection
    if fmt is None:
        fmt = "text" if sys.stdout.isatty() else "json"

    if fmt == "json":
        for r in records:
            obj = {
                "id": r.id,
                "created_at": r.created_at.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z",
                "updated_at": (r.updated_at or r.created_at).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z",
                "content": r.content,
                "meta": dict(r.meta),
            }
            click.echo(json.dumps(obj, ensure_ascii=False))
    else:
        _print_table(records)


@raw.command("get", short_help="Get a single raw record by ID")
@click.argument("record_id", metavar="ID")
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["text", "json"]),
    default=None,
    help="Output format (default: auto-detect from TTY).",
)
@click.pass_context
def get_cmd(ctx: click.Context, record_id: str, fmt: str | None) -> None:
    """Get a single raw record by ID.

    \b
    Text mode shows the full record details;
    JSON mode outputs the record as a single JSON object.
    """
    try:
        project_dir = ctx.obj.get("project_dir") if ctx.obj else None
        start = Path(project_dir) if project_dir else None
        project_root = resolve_project(start)
    except FileNotFoundError as e:
        click.echo(str(e), err=True)
        sys.exit(3)

    try:
        record = raw_get(project_root, record_id)
    except ConfigError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(3)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    if record is None:
        click.echo(f"Error: Record not found: {record_id}", err=True)
        sys.exit(1)

    # Resolve format: explicit > TTY detection
    if fmt is None:
        fmt = "text" if sys.stdout.isatty() else "json"

    if fmt == "json":
        obj = {
            "id": record.id,
            "created_at": record.created_at.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z",
            "updated_at": (record.updated_at or record.created_at).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z",
            "content": record.content,
            "meta": dict(record.meta),
        }
        click.echo(json.dumps(obj, ensure_ascii=False))
    else:
        created = record.created_at.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"
        updated = (record.updated_at or record.created_at).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"
        meta_str = json.dumps(dict(record.meta), ensure_ascii=False) if record.meta else "{}"
        click.echo(f"ID:         {record.id}")
        click.echo(f"Created:    {created}")
        click.echo(f"Updated:    {updated}")
        click.echo(f"Content:    {record.content}")
        click.echo(f"Meta:       {meta_str}")


def _truncate(s: str, length: int = 50) -> str:
    """Truncate string to *length* chars, appending '...' if needed."""
    if len(s) <= length:
        return s
    return s[: length - 3] + "..."


def _print_table(records: list) -> None:
    """Print records as a human-readable table to stdout."""
    # Header
    id_w, ts_w, content_w = 36, 27, 50
    header = f"{'ID':<{id_w}}  {'CREATED_AT':<{ts_w}}  {'UPDATED_AT':<{ts_w}}  {'CONTENT'}"
    click.echo(header)
    click.echo("-" * len(header))

    for r in records:
        created = r.created_at.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"
        updated = (r.updated_at or r.created_at).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"
        content = _truncate(r.content, content_w)
        click.echo(f"{r.id:<{id_w}}  {created:<{ts_w}}  {updated:<{ts_w}}  {content}")
