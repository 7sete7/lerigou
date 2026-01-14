"""CLI principal do lerigou."""

import typer
from rich.console import Console

from lerigou import __version__
from lerigou.commands import create_canvas

app = typer.Typer(
    name="lerigou",
    help="CLI multitarefa para análise e visualização de código",
    add_completion=False,
)

console = Console()


def version_callback(value: bool) -> None:
    """Mostra a versão e sai."""
    if value:
        console.print(f"[bold blue]lerigou[/bold blue] version {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        "-v",
        callback=version_callback,
        is_eager=True,
        help="Mostra a versão do lerigou",
    ),
) -> None:
    """lerigou - CLI multitarefa para análise e visualização de código."""
    pass


# Registra os comandos
app.command(name="create-canvas")(create_canvas.create_canvas)


if __name__ == "__main__":
    app()
