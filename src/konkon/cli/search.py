"""konkon search — Run query() from konkon.py (Transformation Context)."""

import click


def register(group: click.Group) -> None:
    """Register the search command to the CLI group."""
    group.add_command(search)


@click.command(short_help="Run query() in konkon.py and output results [not implemented]")
@click.argument("query")
def search(query: str) -> None:
    """Run query() in konkon.py and output results.

    Delegates to core/transformation.py (Transformation Context facade).
    """
    # TODO: Implement per 04_cli_design.md §4.4
    # - Delegate to core/transformation.run_query(project_root, query)
    raise NotImplementedError
