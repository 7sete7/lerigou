"""Comando create-canvas-v2 para gerar JSON Canvas com análise de IA."""

import os
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from lerigou.ai.analyzer import AICodeAnalyzer
from lerigou.ai.canvas_adapter import AIToCanvasAdapter
from lerigou.canvas.renderer import render_canvas, save_canvas
from lerigou.processor.collector import CodeCollector

console = Console()


def create_canvas_v2(
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
    model: str = typer.Option(
        "gpt-4o",
        "--model",
        "-m",
        help="Modelo OpenAI a usar (gpt-4o, gpt-4o-mini, gpt-4-turbo)",
    ),
    api_key: Optional[str] = typer.Option(
        None,
        "--api-key",
        envvar="OPENAI_API_KEY",
        help="Chave da API OpenAI (ou use OPENAI_API_KEY)",
    ),
    show_analysis: bool = typer.Option(
        False,
        "--show-analysis",
        help="Mostra a análise da IA no terminal",
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
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Apenas mostra o código coletado, sem chamar a IA",
    ),
) -> None:
    """
    Gera um JSON Canvas visual usando análise de IA.

    Este comando analisa o código seguindo todas as chamadas de função
    a partir do entrypoint, envia para a OpenAI para identificar domínios,
    assuntos e formatos de dados, e gera um canvas visual estruturado.

    Requer a variável de ambiente OPENAI_API_KEY ou --api-key.

    Exemplos:

        lerigou create-canvas-v2 ./src/main.py -e main

        lerigou create-canvas-v2 ./src/app.py --model gpt-4o-mini

        lerigou create-canvas-v2 ./src/service.py --show-analysis
    """
    # Valida o arquivo
    if not file_path.is_file():
        console.print(f"[red]Erro:[/red] '{file_path}' não é um arquivo válido")
        raise typer.Exit(1)

    # Valida a extensão
    if file_path.suffix not in (".py", ".pyw", ".pyi"):
        console.print("[red]Erro:[/red] Apenas arquivos Python são suportados")
        raise typer.Exit(1)

    # Valida API key
    if not dry_run and not api_key and not os.environ.get("OPENAI_API_KEY"):
        console.print(
            "[red]Erro:[/red] OPENAI_API_KEY não configurada.\n"
            "Configure via variável de ambiente ou use --api-key"
        )
        raise typer.Exit(1)

    # Define o arquivo de saída
    if output is None:
        suffix = "_ai" if not entrypoint else f"_{entrypoint.replace('.', '_')}_ai"
        output = file_path.with_stem(file_path.stem + suffix).with_suffix(".canvas")
    elif output.suffix != ".canvas":
        output = output.with_suffix(".canvas")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        # Coleta o código
        task = progress.add_task("Coletando código...", total=None)

        collector = CodeCollector(base_path=file_path.parent)

        try:
            collected = collector.collect_from_entrypoint(file_path, entrypoint)
        except Exception as e:
            progress.stop()
            console.print(f"[red]Erro ao coletar código:[/red] {e}")
            raise typer.Exit(1)

        progress.update(task, description=f"Coletados {len(collected.chunks)} chunks...")

        # Dry run - mostra apenas o código coletado
        if dry_run:
            progress.stop()
            console.print()
            console.print(
                Panel(
                    collected.to_prompt_context()[:2000] + "...",
                    title="[bold blue]Código Coletado (preview)[/bold blue]",
                    border_style="blue",
                )
            )
            console.print(
                f"\n[dim]Total: {len(collected.chunks)} chunks, "
                f"~{len(collected.concatenated_code)} caracteres[/dim]"
            )
            return

        # Estima tokens
        analyzer = AICodeAnalyzer(model=model, api_key=api_key)
        estimated_tokens = analyzer.estimate_tokens(collected)

        progress.update(task, description=f"Analisando com IA (~{estimated_tokens} tokens)...")

        # Analisa com IA
        try:
            analysis = analyzer.analyze_with_retry(collected, max_retries=2)
        except Exception as e:
            progress.stop()
            console.print(f"[red]Erro na análise de IA:[/red] {e}")
            raise typer.Exit(1)

        # Mostra análise se solicitado
        if show_analysis:
            progress.stop()
            _show_analysis_table(analysis)
            console.print()
            progress.start()

        progress.update(task, description="Gerando canvas...")

        # Converte para canvas
        adapter = AIToCanvasAdapter()
        canvas = adapter.convert(analysis)

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
    num_steps = len(analysis.main_flow.steps)
    num_connections = len(analysis.main_flow.connections)
    num_data_formats = len(analysis.data_formats)

    console.print()
    console.print(
        Panel(
            f"[green]✓[/green] Canvas de fluxo gerado com sucesso!\n\n"
            f"[bold]Arquivo:[/bold] {output}\n"
            f"[bold]Modelo:[/bold] {model}\n"
            f"[bold]Passos no fluxo:[/bold] {num_steps}\n"
            f"[bold]Conexões:[/bold] {num_connections}\n"
            f"[bold]Formatos de dados:[/bold] {num_data_formats}\n"
            f"[bold]Nodes no canvas:[/bold] {num_nodes}\n"
            f"[bold]Edges no canvas:[/bold] {num_edges}",
            title="[bold blue]lerigou create-canvas-v2[/bold blue]",
            border_style="blue",
        )
    )


def _show_analysis_table(analysis) -> None:
    """Mostra a análise em formato de tabela."""
    # Resumo
    console.print(
        Panel(
            analysis.summary,
            title="[bold]📋 Resumo[/bold]",
            border_style="cyan",
        )
    )

    # Fluxo principal
    if analysis.main_flow and analysis.main_flow.steps:
        table = Table(title=f"🔄 Fluxo: {analysis.main_flow.name}")
        table.add_column("#", style="dim")
        table.add_column("Passo", style="bold")
        table.add_column("Tipo")
        table.add_column("Função")

        for i, step in enumerate(analysis.main_flow.steps, 1):
            step_type_icons = {
                "start": "▶️ start",
                "process": "⚙️ process",
                "decision": "❓ decision",
                "data": "💾 data",
                "end": "🏁 end",
                "error": "❌ error",
            }
            table.add_row(
                str(i),
                step.name,
                step_type_icons.get(step.step_type, step.step_type),
                step.function or "-",
            )

        console.print(table)

        # Conexões
        if analysis.main_flow.connections:
            console.print(
                f"\n[dim]Conexões: {len(analysis.main_flow.connections)} flechas no fluxo[/dim]"
            )

    # Formatos de dados
    if analysis.data_formats:
        table = Table(title="📊 Formatos de Dados")
        table.add_column("Nome", style="bold")
        table.add_column("Descrição")
        table.add_column("Campos")

        for data in analysis.data_formats:
            table.add_row(
                data.name,
                data.description[:50] + "..." if len(data.description) > 50 else data.description,
                ", ".join(data.fields[:3]) + ("..." if len(data.fields) > 3 else ""),
            )

        console.print(table)
