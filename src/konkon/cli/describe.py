"""konkon describe — Show plugin schema (query interface description)."""

import json
import sys
from pathlib import Path

import click

from konkon.application import describe as app_describe
from konkon.core.instance import resolve_project


def register(group: click.Group) -> None:
    """Register the describe command to the CLI group."""
    group.add_command(describe)


@click.command(short_help="Show plugin schema (query interface)")
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["text", "json"]),
    default=None,
    help="Output format (default: auto-detect from TTY).",
)
@click.option(
    "--plugin",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help="Path to a custom konkon.py plugin.",
)
@click.pass_context
def describe(ctx: click.Context, fmt: str | None, plugin: Path | None) -> None:
    """Show the plugin's query interface (schema).

    \b
    Calls schema() in konkon.py and displays:
    - description, params, result info (text mode)
    - raw schema dict (json mode)
    """
    try:
        project_dir = ctx.obj.get("project_dir") if ctx.obj else None
        start = Path(project_dir) if project_dir else None
        project_root = resolve_project(start)
    except FileNotFoundError as e:
        click.echo(str(e), err=True)
        sys.exit(3)

    try:
        schema = app_describe(project_root, plugin_override=plugin)
    except (FileNotFoundError, ValueError, SyntaxError, ImportError) as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(3)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    # Resolve format: explicit > TTY detection
    if fmt is None:
        fmt = "text" if sys.stdout.isatty() else "json"

    if fmt == "json":
        click.echo(json.dumps(schema, ensure_ascii=False, indent=2))
    else:
        _print_text(schema)


def _print_text(schema: dict) -> None:
    """Print schema in human-readable text format."""
    description = schema.get("description", "")
    if description:
        click.echo(f"Description: {description}")

    params = schema.get("params", {})
    if params:
        click.echo("")
        click.echo("Params:")
        for name, spec in params.items():
            typ = spec.get("type", "")
            desc = spec.get("description", "")
            parts = [f"  {name:<8} {typ:<8} {desc}"]
            extras = []
            if "enum" in spec:
                extras.append(f"enum: {', '.join(str(v) for v in spec['enum'])}")
            if "default" in spec:
                extras.append(f"default: {spec['default']}")
            if extras:
                parts.append(f" ({'; '.join(extras)})")
            click.echo("".join(parts))

    result = schema.get("result")
    if result:
        click.echo("")
        result_desc = result.get("description", "")
        if result_desc:
            click.echo(f"Result: {result_desc}")
