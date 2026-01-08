"""Renderizador de Canvas para JSON."""

import json
from pathlib import Path

from lerigou.canvas.models import Canvas


def render_canvas(canvas: Canvas, pretty: bool = True) -> str:
    """
    Renderiza um Canvas para string JSON.

    Args:
        canvas: O Canvas a ser renderizado
        pretty: Se True, formata o JSON com indentação

    Returns:
        String JSON do canvas
    """
    data = canvas.to_dict()
    if pretty:
        return json.dumps(data, indent="\t", ensure_ascii=False)
    return json.dumps(data, ensure_ascii=False)


def save_canvas(canvas: Canvas, path: str | Path, pretty: bool = True) -> None:
    """
    Salva um Canvas em um arquivo .canvas.

    Args:
        canvas: O Canvas a ser salvo
        path: Caminho do arquivo (adiciona .canvas se não tiver)
        pretty: Se True, formata o JSON com indentação
    """
    path = Path(path)
    if path.suffix != ".canvas":
        path = path.with_suffix(".canvas")

    json_str = render_canvas(canvas, pretty)
    path.write_text(json_str, encoding="utf-8")


def load_canvas(path: str | Path) -> Canvas:
    """
    Carrega um Canvas de um arquivo .canvas.

    Args:
        path: Caminho do arquivo

    Returns:
        Canvas carregado
    """
    from lerigou.canvas.models import Edge, Node

    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8"))

    canvas = Canvas()

    # Carrega nodes
    for node_data in data.get("nodes", []):
        node = Node(
            id=node_data["id"],
            type=node_data["type"],
            x=node_data["x"],
            y=node_data["y"],
            width=node_data["width"],
            height=node_data["height"],
            color=node_data.get("color"),
            text=node_data.get("text"),
            file=node_data.get("file"),
            subpath=node_data.get("subpath"),
            url=node_data.get("url"),
            label=node_data.get("label"),
            background=node_data.get("background"),
            background_style=node_data.get("backgroundStyle"),
        )
        canvas.add_node(node)

    # Carrega edges
    for edge_data in data.get("edges", []):
        edge = Edge(
            id=edge_data["id"],
            from_node=edge_data["fromNode"],
            to_node=edge_data["toNode"],
            from_side=edge_data.get("fromSide"),
            to_side=edge_data.get("toSide"),
            from_end=edge_data.get("fromEnd"),
            to_end=edge_data.get("toEnd"),
            color=edge_data.get("color"),
            label=edge_data.get("label"),
        )
        canvas.add_edge(edge)

    return canvas
