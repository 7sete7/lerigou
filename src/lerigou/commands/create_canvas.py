"""Comando create-canvas para gerar JSON Canvas a partir de código."""

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from lerigou.canvas.renderer import render_canvas, save_canvas
from lerigou.processor.adapter import CodeToCanvasAdapter
from lerigou.processor.parser import get_parser_for_file

console = Console()


def create_canvas(
    file_path: Path = typer.Argument(
        ...,
        help="Caminho do arquivo Python a ser analisado",
        exists=True,
        readable=True,
    ),
    entrypoint: Optional[str] = typer.Option(
        None,
        "--entrypoint",
        "-e",
        help="Nome da função/classe de entrada (ex: main, MyClass.process)",
    ),
    output: Optional[Path] = typer.Option(
        None,
        "--output",
        "-o",
        help="Caminho do arquivo de saída (.canvas)",
    ),
    no_docstrings: bool = typer.Option(
        False,
        "--no-docstrings",
        help="Não incluir docstrings nos nodes",
    ),
    no_params: bool = typer.Option(
        False,
        "--no-params",
        help="Não incluir parâmetros nas funções",
    ),
    compact: bool = typer.Option(
        False,
        "--compact",
        "-c",
        help="Gera JSON compacto (sem indentação)",
    ),
    stdout: bool = typer.Option(
        False,
        "--stdout",
        help="Imprime o JSON no stdout ao invés de salvar",
    ),
) -> None:
    """
    Gera um JSON Canvas visual a partir de código Python.

    Analisa a estrutura do código (funções, classes, chamadas) e gera
    um arquivo .canvas compatível com Obsidian e outras ferramentas.

    Exemplos:

        lerigou create-canvas ./src/main.py

        lerigou create-canvas ./src/main.py --entrypoint main

        lerigou create-canvas ./src/app.py -o diagrama.canvas
    """
    # Valida o arquivo
    if not file_path.is_file():
        console.print(f"[red]Erro:[/red] '{file_path}' não é um arquivo válido")
        raise typer.Exit(1)

    # Obtém o parser apropriado
    parser = get_parser_for_file(file_path)
    if parser is None:
        console.print(f"[red]Erro:[/red] Tipo de arquivo não suportado: {file_path.suffix}")
        console.print("Tipos suportados: .py, .pyw, .pyi")
        raise typer.Exit(1)

    # Define o arquivo de saída
    if output is None:
        output = file_path.with_suffix(".canvas")
    elif output.suffix != ".canvas":
        output = output.with_suffix(".canvas")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        # Parseia o código
        task = progress.add_task("Analisando código...", total=None)

        try:
            code_element = parser.parse_file(file_path)
        except SyntaxError as e:
            progress.stop()
            console.print(f"[red]Erro de sintaxe:[/red] {e}")
            raise typer.Exit(1)
        except Exception as e:
            progress.stop()
            console.print(f"[red]Erro ao analisar:[/red] {e}")
            raise typer.Exit(1)

        progress.update(task, description="Gerando canvas...")

        # Cria o adapter
        adapter = CodeToCanvasAdapter(
            include_docstrings=not no_docstrings,
            include_params=not no_params,
        )

        # Converte para canvas
        if entrypoint:
            canvas = adapter.convert_from_entrypoint(code_element, entrypoint)
        else:
            canvas = adapter.convert(code_element)

        progress.update(task, description="Salvando...")

        # Gera o JSON
        if stdout:
            progress.stop()
            json_output = render_canvas(canvas, pretty=not compact)
            console.print(json_output)
            return

        # Salva o arquivo
        save_canvas(canvas, output, pretty=not compact)

    # Estatísticas
    num_nodes = len(canvas.nodes)
    num_edges = len(canvas.edges)
    num_groups = sum(1 for n in canvas.nodes if n.type == "group")

    console.print()
    console.print(
        Panel(
            f"[green]✓[/green] Canvas gerado com sucesso!\n\n"
            f"[bold]Arquivo:[/bold] {output}\n"
            f"[bold]Nodes:[/bold] {num_nodes} ({num_groups} grupos)\n"
            f"[bold]Edges:[/bold] {num_edges}",
            title="[bold blue]lerigou create-canvas[/bold blue]",
            border_style="blue",
        )
    )

    if entrypoint:
        console.print(f"[dim]Filtrado a partir de: {entrypoint}[/dim]")
