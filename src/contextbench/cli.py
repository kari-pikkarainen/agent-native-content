"""Command-line interface for the Context IR benchmark."""

from typing import Annotated

import typer

from contextbench import __version__

app = typer.Typer(
    name="contextbench",
    help="Run reproducible context-compilation benchmark experiments.",
    no_args_is_help=True,
)


def version_callback(value: bool) -> None:
    """Print the package version and exit."""
    if value:
        typer.echo(__version__)
        raise typer.Exit


@app.callback()
def main(
    version: Annotated[
        bool | None,
        typer.Option(
            "--version",
            callback=version_callback,
            is_eager=True,
            help="Show the package version and exit.",
        ),
    ] = None,
) -> None:
    """Run reproducible context-compilation benchmark experiments."""
