"""konkon insert — Append text data to Raw DB (Ingestion Context)."""

import sys
from pathlib import Path

import click

from konkon.core import ingestion
from konkon.core.instance import resolve_project


def register(group: click.Group) -> None:
    """Register the insert command to the CLI group."""
    group.add_command(insert)


def _parse_meta(pairs: tuple[str, ...]) -> dict[str, str] | None:
    """Parse KEY=VALUE pairs into a dict. Returns None if empty."""
    if not pairs:
        return None
    result: dict[str, str] = {}
    for pair in pairs:
        key, _, value = pair.partition("=")
        if not key:
            raise click.BadParameter(f"Invalid meta format: {pair!r}")
        result[key] = value
    return result


@click.command(short_help="Append text data to the Raw DB")
@click.argument("text", required=False, default=None)
@click.option("-m", "--meta", multiple=True, help="Metadata as KEY=VALUE")
@click.pass_context
def insert(ctx: click.Context, text: str | None, meta: tuple[str, ...]) -> None:
    """Append text data to the Raw DB.

    TEXT can be provided as argument or via stdin.
    Delegates to core/ingestion (Ingestion Context facade).
    """
    try:
        # Resolve content: argument or stdin
        if text is not None:
            content = text
        elif not sys.stdin.isatty():
            content = sys.stdin.read()
            if not content:
                click.echo("Error: No text provided. Pass TEXT argument or pipe via stdin.", err=True)
                sys.exit(1)
        else:
            click.echo("Error: No text provided. Pass TEXT argument or pipe via stdin.", err=True)
            sys.exit(1)

        # Resolve project root
        project_dir = ctx.obj.get("project_dir") if ctx.obj else None
        start = Path(project_dir) if project_dir else None
        project_root = resolve_project(start)

        # Parse metadata
        meta_dict = _parse_meta(meta)

        # Delegate to facade
        record = ingestion.ingest(content, meta_dict, project_root)
        click.echo(record.id)
    except FileNotFoundError as e:
        click.echo(str(e), err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
