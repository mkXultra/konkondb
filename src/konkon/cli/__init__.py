"""CLI entry point for konkon.

Each command is defined in its own module under cli/.
This file only defines the top-level group and help command,
then registers subcommands from their respective modules.
"""

import sys

import click

from konkon.cli import (
    build,
    delete,
    describe,
    init,
    insert,
    migrate,
    raw,
    search,
    serve,
    setup_db,
    update,
)


@click.group(invoke_without_command=True, context_settings={"max_content_width": 120})
@click.option(
    "-C", "--project-dir",
    type=click.Path(exists=False),
    default=None,
    help="Project root directory (default: auto-detect from cwd).",
)
@click.option(
    "--config",
    "config_file",
    type=click.Path(exists=True, dir_okay=False),
    default=None,
    help="Stateless config TOML path.",
)
@click.option(
    "--raw-dsn",
    default=None,
    help="Explicit postgres DSN override.",
)
@click.pass_context
def main(
    ctx: click.Context,
    project_dir: str | None,
    config_file: str | None,
    raw_dsn: str | None,
) -> None:
    """konkon db — Store raw data, transform with plugins, and serve AI-ready context.

    \b
    Workflow: init → insert → build → search
    """
    if project_dir is not None and config_file is not None:
        raise click.UsageError(
            "'--config' and '--project-dir' cannot be used together."
        )
    ctx.ensure_object(dict)
    ctx.obj["project_dir"] = project_dir
    ctx.obj["config_file"] = config_file
    ctx.obj["raw_dsn"] = raw_dsn
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


# Register subcommands from their modules
init.register(main)
insert.register(main)
delete.register(main)
build.register(main)
search.register(main)
describe.register(main)
update.register(main)
migrate.register(main)
raw.register(main)
serve.register(main)
setup_db.register(main)
