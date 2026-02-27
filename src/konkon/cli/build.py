"""konkon build — Run build() from konkon.py (Transformation Context)."""

import click


def register(group: click.Group) -> None:
    """Register the build command to the CLI group."""
    group.add_command(build)


@click.command(
    short_help="Transform Raw DB data via build() in konkon.py to produce AI-ready context [not implemented]"
)
def build() -> None:
    """Transform Raw DB data via build() in konkon.py to produce AI-ready context.

    Delegates to core/transformation.py (Transformation Context facade).
    """
    # TODO: Implement per 04_cli_design.md §4.3
    # - Delegate to core/transformation.run_build(project_root)
    raise NotImplementedError
