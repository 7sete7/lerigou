"""Comando create-canvas para gerar JSON Canvas com análise de IA."""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from lerigou.ai.analyzer import AICodeAnalyzer
from lerigou.ai.canvas_adapter import AIToCanvasAdapter
from lerigou.canvas.models import Edge, Node
from lerigou.canvas.renderer import render_canvas, save_canvas
from lerigou.processor.collector import CodeCollector, CollectedCode
from lerigou.utils.text_dimensions import calculate_node_dimensions

console = Console()

# Extensões suportadas
SUPPORTED_EXTENSIONS = (
    ".py",
    ".pyw",
    ".pyi",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".mjs",
    ".cjs",
)


@dataclass
class FrontendAPICallSummary:
    method: str
    path: str
    matched_endpoint: str | None
    is_external: bool


@dataclass
class FrontendContext:
    component: str
    api_calls: list[FrontendAPICallSummary]


def _find_repo_root(start_path: Path) -> Path:
    """
    Encontra a raiz do repositório subindo a partir de um path.

    Prioriza .git (repositório real) sobre package.json (que pode estar em subpastas).
    """
    current = start_path.resolve()
    if current.is_file():
        current = current.parent

    # Primeiro, procura por .git (indica raiz real do repositório)
    git_root = None
    for parent in [current] + list(current.parents):
        if (parent / ".git").exists():
            git_root = parent
            break

    if git_root:
        return git_root

    # Se não encontrou .git, procura por outros indicadores
    # Prioriza pyproject.toml sobre package.json (para evitar parar em subpastas de monorepo)
    secondary_indicators = ["pyproject.toml", "Cargo.toml", "go.mod"]
    for parent in [current] + list(current.parents):
        for indicator in secondary_indicators:
            if (parent / indicator).exists():
                return parent

    # Por último, package.json (mas tenta encontrar o mais alto)
    pkg_root = None
    for parent in [current] + list(current.parents):
        if (parent / "package.json").exists():
            pkg_root = parent  # Continua procurando (queremos o mais alto)

    if pkg_root:
        return pkg_root

    # Fallback: retorna o diretório do arquivo
    return start_path.parent if start_path.is_file() else start_path


def create_canvas(
    file_path: Path = typer.Argument(
        ...,
        help="Caminho do arquivo a ser analisado (Python, TypeScript, JavaScript)",
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
    repo_root: Optional[Path] = typer.Option(
        None,
        "--repo-root",
        "-r",
        help="Raiz do repositório para buscar endpoints do backend (auto-detecta se não informado)",
    ),
) -> None:
    """
    Gera um JSON Canvas visual usando análise de IA.

    Este comando analisa o código seguindo todas as chamadas de função
    a partir do entrypoint, envia para a OpenAI para identificar o fluxo
    de execução, e gera um canvas visual estruturado.

    Suporta: Python (.py), TypeScript (.ts, .tsx), JavaScript (.js, .jsx)

    Para arquivos TypeScript/JavaScript, também detecta chamadas de API
    e conecta ao backend correspondente no repositório.

    Requer a variável de ambiente OPENAI_API_KEY ou --api-key.

    Exemplos:

        lerigou create-canvas ./src/main.py -e main

        lerigou create-canvas ./src/App.tsx -e UserList

        lerigou create-canvas ./src/service.py --show-analysis
    """
    # Valida o arquivo
    if not file_path.is_file():
        console.print(f"[red]Erro:[/red] '{file_path}' não é um arquivo válido")
        raise typer.Exit(1)

    # Valida a extensão
    if file_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        console.print(
            f"[red]Erro:[/red] Tipo de arquivo não suportado: {file_path.suffix}"
        )
        console.print(f"Tipos suportados: {', '.join(SUPPORTED_EXTENSIONS)}")
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

    # Determina a raiz do repositório
    if repo_root:
        # Tenta resolver o caminho especificado
        resolved = repo_root.resolve()
        if resolved.exists() and resolved.is_dir():
            base_path = resolved
        else:
            # Tenta resolver relativo ao diretório do arquivo
            relative_to_file = (file_path.parent / repo_root).resolve()
            if relative_to_file.exists() and relative_to_file.is_dir():
                base_path = relative_to_file
            else:
                # Fallback: usa _find_repo_root
                console.print(
                    f"[yellow]Aviso:[/yellow] Não foi possível resolver '{repo_root}', "
                    "usando detecção automática"
                )
                base_path = _find_repo_root(file_path)
    else:
        base_path = _find_repo_root(file_path)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        # Coleta o código
        task = progress.add_task("Coletando código...", total=None)

        collector = CodeCollector(base_path=base_path)

        try:
            collected = collector.collect_from_entrypoint(file_path, entrypoint)
        except Exception as e:
            progress.stop()
            console.print(f"[red]Erro ao coletar código:[/red] {e}")
            raise typer.Exit(1)

        progress.update(
            task, description=f"Coletados {len(collected.chunks)} chunks..."
        )

        # Dry run - mostra apenas o código coletado
        if dry_run:
            progress.stop()
            console.print()
            console.print(f"[dim]Repo root: {base_path}[/dim]")
            console.print()
            console.print(
                Panel(
                    collected.to_prompt_context()[:2000] + "...",
                    title="[bold blue]Código Coletado (preview)[/bold blue]",
                    border_style="blue",
                )
            )

            # Mostra API calls encontradas
            if collected.api_calls:
                console.print("\n[bold]API Calls detectadas:[/bold]")
                for api in collected.api_calls:
                    status = (
                        "[green]→ Backend[/green]"
                        if api.matched_endpoint
                        else "[yellow]→ External[/yellow]"
                    )
                    console.print(f"  {api.method:6} {api.path:40} {status}")
                    if api.matched_endpoint:
                        console.print(f"         [dim]{api.matched_endpoint}[/dim]")

            console.print(
                f"\n[dim]Total: {len(collected.chunks)} chunks, "
                f"~{len(collected.concatenated_code)} caracteres[/dim]"
            )
            return

        # Estima tokens
        analyzer = AICodeAnalyzer(model=model, api_key=api_key)
        estimated_tokens = analyzer.estimate_tokens(collected)

        progress.update(
            task, description=f"Analisando com IA (~{estimated_tokens} tokens)..."
        )

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

        # Preparar contexto frontend
        frontend_context = _build_frontend_context(collected)

        # Converte para canvas
        adapter = AIToCanvasAdapter()
        canvas = adapter.convert(analysis)
        if frontend_context:
            _augment_canvas_with_frontend(canvas, analysis, frontend_context)

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
            title="[bold blue]lerigou create-canvas[/bold blue]",
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
                (
                    data.description[:50] + "..."
                    if len(data.description) > 50
                    else data.description
                ),
                ", ".join(data.fields[:3]) + ("..." if len(data.fields) > 3 else ""),
            )

        console.print(table)


def _build_frontend_context(collected: CollectedCode) -> FrontendContext | None:
    """Cria um contexto descritivo sobre o frontend e APIs detectadas."""
    component = collected.frontend_component
    if not component:
        return None

    api_summaries = [
        FrontendAPICallSummary(
            method=call.method,
            path=call.path,
            matched_endpoint=call.matched_endpoint,
            is_external=call.is_external or call.matched_endpoint is None,
        )
        for call in collected.api_calls
    ]

    if not api_summaries:
        return None

    return FrontendContext(component=component, api_calls=api_summaries)


def _format_frontend_api_text(api_calls: list[FrontendAPICallSummary]) -> str:
    """Formata o texto que descreve as chamadas de API do frontend."""
    if not api_calls:
        return ""

    lines = ["### 🔌 Chamadas de API detectadas", ""]
    limit = 8
    for call in api_calls[:limit]:
        status = "Backend" if call.matched_endpoint else "API externa"
        target = call.matched_endpoint or "externa"
        lines.append(f"- **{call.method}** {call.path} → {status} ({target})")

    if len(api_calls) > limit:
        lines.append(f"- ... (+{len(api_calls) - limit} chamadas restantes)")

    return "\n".join(lines)


def _augment_canvas_with_frontend(
    canvas, analysis, frontend_context: FrontendContext
) -> None:
    """Adiciona nodes do frontend e conecta ao fluxo backend."""
    summary_node = canvas.get_node_by_id("summary")
    if summary_node and summary_node.text:
        extra = (
            f"### 🌐 Frontend detectado: {frontend_context.component}\n"
            f"- Entrada identificada com {len(frontend_context.api_calls)} APIs mapeadas"
        )
        summary_node.text = f"{summary_node.text}\n\n{extra}"

    base_y = summary_node.y + summary_node.height + 40 if summary_node else 60
    component_text = (
        f"## 🧭 {frontend_context.component}\n"
        "Componente/página React responsável por iniciar o fluxo abaixo."
    )
    width, height = calculate_node_dimensions(
        component_text, node_type="text", base_width=340, base_height=100
    )
    component_node = Node.text_node(
        text=component_text,
        x=0,
        y=base_y,
        width=width,
        height=height,
        color="2",
        node_id="frontend_component",
    )
    canvas.add_node(component_node)

    api_text = _format_frontend_api_text(frontend_context.api_calls)
    if api_text:
        api_y = component_node.y + component_node.height + 30
        api_width, api_height = calculate_node_dimensions(
            api_text, node_type="text", base_width=360, base_height=120
        )
        api_node = Node.text_node(
            text=api_text,
            x=0,
            y=api_y,
            width=api_width,
            height=api_height,
            color="5",
            node_id="frontend_api_calls",
        )
        canvas.add_node(api_node)
        canvas.add_edge(
            Edge.create(
                from_node=component_node.id,
                to_node=api_node.id,
                label="Chamadas mapeadas",
            )
        )

    start_step_id = next(
        (step.id for step in analysis.main_flow.steps if step.step_type == "start"),
        None,
    )
    if not start_step_id and analysis.main_flow.steps:
        start_step_id = analysis.main_flow.steps[0].id

    first_node_id = f"step_{start_step_id}" if start_step_id else None
    if first_node_id and canvas.get_node_by_id(first_node_id):
        canvas.add_edge(
            Edge.create(
                from_node=component_node.id,
                to_node=first_node_id,
                label="Dispara fluxo backend",
            )
        )
