"""konkon raw — Raw DB inspection commands (debug / operations)."""

import json
import sys
from pathlib import Path

import click

from konkon.core.ingestion import list_records
from konkon.core.instance import resolve_project


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
        records = list_records(project_root, limit=limit)
    except RuntimeError as e:
        # Schema version mismatch etc. — configuration error
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
