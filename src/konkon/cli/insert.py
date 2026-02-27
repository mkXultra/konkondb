"""konkon insert — Append text data to Raw DB (Ingestion Context)."""

import click


def register(group: click.Group) -> None:
    """Register the insert command to the CLI group."""
    group.add_command(insert)


@click.command(short_help="Append text data to the Raw DB [not implemented]")
@click.argument("text", required=False, default=None)
@click.option("-m", "--meta", multiple=True, help="Metadata as KEY=VALUE")
def insert(text: str | None, meta: tuple[str, ...]) -> None:
    """Append text data to the Raw DB.

    TEXT can be provided as argument or via stdin.
    Delegates to core/ingestion.py (Ingestion Context facade).
    """
    # TODO: Implement per 04_cli_design.md §4.2
    # - Read TEXT from argument or stdin
    # - Parse --meta KEY=VALUE pairs
    # - Delegate to core/ingestion.ingest(content, meta, project_root)
    raise NotImplementedError
