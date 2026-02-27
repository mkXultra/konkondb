"""konkon serve — Start API or MCP server (Serving Context)."""

import click


def register(group: click.Group) -> None:
    """Register the serve command to the CLI group."""
    group.add_command(serve)


@click.command(short_help="Start a REST API or MCP server [not implemented]")
def serve() -> None:
    """Start a REST API or MCP server.

    Delegates to serving/api.py or serving/mcp.py (Serving Context).
    """
    # TODO: Implement per 04_cli_design.md §4.5
    # - Parse --api / --mcp subcommand
    # - Delegate to serving/api.py or serving/mcp.py
    raise NotImplementedError
