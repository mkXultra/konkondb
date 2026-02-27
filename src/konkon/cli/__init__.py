"""CLI entry point for konkon."""

import sys

import click


@click.group(invoke_without_command=True, context_settings={"max_content_width": 120})
@click.pass_context
def main(ctx: click.Context) -> None:
    """konkon db — Store raw data, transform with plugins, and serve AI-ready context.

    \b
    Workflow: init → insert → build → search
    """
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@main.command(short_help="Show detailed help for a command (e.g. konkon help search) [ready]")
@click.argument("command", required=False, default=None)
@click.pass_context
def help(ctx: click.Context, command: str | None) -> None:
    """Show detailed help for a command.

    \b
    Example: konkon help search
    """
    parent = ctx.parent
    assert parent is not None

    if command is None:
        click.echo(parent.get_help())
        return

    cmd = main.get_command(ctx, command)
    if cmd is None:
        click.echo(f"Error: Unknown command '{command}'.", err=True)
        sys.exit(2)

    sub_ctx = click.Context(cmd, info_name=command, parent=parent)
    click.echo(cmd.get_help(sub_ctx))


@main.command(short_help="Create a konkon project in the current directory [not implemented]")
def init() -> None:
    """Create a konkon project in the current directory."""
    click.echo("Error: 'init' is not yet implemented.", err=True)
    sys.exit(1)


@main.command(short_help="Append text data to the Raw DB [not implemented]")
def insert() -> None:
    """Append text data to the Raw DB."""
    click.echo("Error: 'insert' is not yet implemented.", err=True)
    sys.exit(1)


@main.command(
    short_help="Transform Raw DB data via build() in konkon.py to produce AI-ready context [not implemented]"
)
def build() -> None:
    """Transform Raw DB data via build() in konkon.py to produce AI-ready context."""
    click.echo("Error: 'build' is not yet implemented.", err=True)
    sys.exit(1)


@main.command(short_help="Run query() in konkon.py and output results [not implemented]")
def search() -> None:
    """Run query() in konkon.py and output results."""
    click.echo("Error: 'search' is not yet implemented.", err=True)
    sys.exit(1)


@main.command(short_help="Start a REST API or MCP server [not implemented]")
def serve() -> None:
    """Start a REST API or MCP server."""
    click.echo("Error: 'serve' is not yet implemented.", err=True)
    sys.exit(1)
