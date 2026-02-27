"""konkon build — Run build() from konkon.py (Transformation Context)."""

import sys
from pathlib import Path

import click

from konkon.core.instance import PLUGIN_FILE, resolve_project
from konkon.core.transformation import run_build


def register(group: click.Group) -> None:
    """Register the build command to the CLI group."""
    group.add_command(build)


@click.command(short_help="Transform Raw DB data via build() in konkon.py")
@click.option(
    "--full",
    is_flag=True,
    default=False,
    help="Full rebuild (default: incremental since last build).",
)
@click.pass_context
def build(ctx: click.Context, full: bool) -> None:
    """Transform Raw DB data via build() in konkon.py to produce AI-ready context.

    By default, runs an incremental build (only records modified since the last
    build). Use --full to rebuild from all records.

    Delegates to core/transformation (Transformation Context facade).
    """
    try:
        project_dir = ctx.obj.get("project_dir") if ctx.obj else None
        start = Path(project_dir) if project_dir else None
        project_root = resolve_project(start)
        run_build(
            project_root, full=full, plugin_path=project_root / PLUGIN_FILE
        )
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
