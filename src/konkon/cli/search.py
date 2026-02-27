"""konkon search — Run query() from konkon.py (Transformation Context)."""

import sys
from pathlib import Path

import click

from konkon.core.instance import PLUGIN_FILE, resolve_project
from konkon.core.models import QueryResult
from konkon.core.transformation import run_query


def register(group: click.Group) -> None:
    """Register the search command to the CLI group."""
    group.add_command(search)


@click.command(short_help="Search context via query() in konkon.py")
@click.argument("query")
@click.pass_context
def search(ctx: click.Context, query: str) -> None:
    """Run query() in konkon.py and output results.

    Delegates to core/transformation (Transformation Context facade).
    """
    try:
        project_dir = ctx.obj.get("project_dir") if ctx.obj else None
        start = Path(project_dir) if project_dir else None
        project_root = resolve_project(start)
        result = run_query(
            project_root, query, plugin_path=project_root / PLUGIN_FILE
        )

        if isinstance(result, QueryResult):
            click.echo(result.content)
        else:
            click.echo(result)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
