"""konkon search — Run query() from konkon.py (Transformation Context)."""

import sys
from pathlib import Path

import click

from konkon.application import search as app_search
from konkon.core.instance import resolve_project
from konkon.core.models import QueryResult


def register(group: click.Group) -> None:
    """Register the search command to the CLI group."""
    group.add_command(search)


def _parse_param(
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


@click.command(short_help="Search context via query() in konkon.py")
@click.argument("query")
@click.option(
    "-p",
    "--param",
    "params",
    multiple=True,
    callback=_parse_param,
    expose_value=True,
    help="Plugin parameter as KEY=VALUE (repeatable).",
)
@click.pass_context
def search(ctx: click.Context, query: str, params: dict[str, str]) -> None:
    """Run query() in konkon.py and output results.

    Delegates to Application Layer Use Case.
    """
    try:
        project_dir = ctx.obj.get("project_dir") if ctx.obj else None
        start = Path(project_dir) if project_dir else None
        project_root = resolve_project(start)
        result = app_search(
            project_root,
            query,
            params=params or None,
        )

        if isinstance(result, QueryResult):
            click.echo(result.content)
        else:
            click.echo(result)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
