"""konkon search — Run query() from konkon.py (Transformation Context)."""

import sys

import click

from konkon.application import search as app_search
from konkon.cli.common import runtime_session
from konkon.core.models import ConfigError, QueryResult


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
        with runtime_session(ctx, needs_connection=False) as (runtime, _manager):
            result = app_search(
                None,
                query,
                params=params or None,
                runtime=runtime,
            )

        if isinstance(result, QueryResult):
            click.echo(result.content)
        else:
            click.echo(result)
    except FileNotFoundError as e:
        click.echo(str(e), err=True)
        sys.exit(1)
    except ConfigError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(3)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
