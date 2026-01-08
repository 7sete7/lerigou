"""Modelos de dados para JSON Canvas seguindo a spec 1.0."""

import uuid
from dataclasses import dataclass, field
from typing import Literal

NodeType = Literal["text", "file", "link", "group"]
Side = Literal["top", "right", "bottom", "left"]
EndShape = Literal["none", "arrow"]
BackgroundStyle = Literal["cover", "ratio", "repeat"]

# Cores preset do JSON Canvas spec
CanvasColor = Literal["1", "2", "3", "4", "5", "6"] | str  # 1-6 ou hex (#RRGGBB)


def generate_id() -> str:
    """Gera um ID único para nodes e edges."""
    return uuid.uuid4().hex[:16]


@dataclass
class Node:
    """
    Representa um node no canvas.

    Tipos:
    - text: Node com texto em Markdown
    - file: Referência a um arquivo
    - link: Referência a uma URL
    - group: Container visual para outros nodes
    """

    id: str
    type: NodeType
    x: int
    y: int
    width: int
    height: int
    # Opcional para todos os tipos
    color: CanvasColor | None = None
    # Para type="text"
    text: str | None = None
    # Para type="file"
    file: str | None = None
    subpath: str | None = None
    # Para type="link"
    url: str | None = None
    # Para type="group"
    label: str | None = None
    background: str | None = None
    background_style: BackgroundStyle | None = None

    @classmethod
    def text_node(
        cls,
        text: str,
        x: int = 0,
        y: int = 0,
        width: int = 250,
        height: int = 60,
        color: CanvasColor | None = None,
        node_id: str | None = None,
    ) -> "Node":
        """Cria um node de texto."""
        return cls(
            id=node_id or generate_id(),
            type="text",
            x=x,
            y=y,
            width=width,
            height=height,
            color=color,
            text=text,
        )

    @classmethod
    def group_node(
        cls,
        label: str,
        x: int = 0,
        y: int = 0,
        width: int = 400,
        height: int = 300,
        color: CanvasColor | None = None,
        node_id: str | None = None,
    ) -> "Node":
        """Cria um node de grupo."""
        return cls(
            id=node_id or generate_id(),
            type="group",
            x=x,
            y=y,
            width=width,
            height=height,
            color=color,
            label=label,
        )

    @classmethod
    def file_node(
        cls,
        file_path: str,
        x: int = 0,
        y: int = 0,
        width: int = 250,
        height: int = 60,
        subpath: str | None = None,
        color: CanvasColor | None = None,
        node_id: str | None = None,
    ) -> "Node":
        """Cria um node de arquivo."""
        return cls(
            id=node_id or generate_id(),
            type="file",
            x=x,
            y=y,
            width=width,
            height=height,
            color=color,
            file=file_path,
            subpath=subpath,
        )

    @classmethod
    def link_node(
        cls,
        url: str,
        x: int = 0,
        y: int = 0,
        width: int = 250,
        height: int = 60,
        color: CanvasColor | None = None,
        node_id: str | None = None,
    ) -> "Node":
        """Cria um node de link."""
        return cls(
            id=node_id or generate_id(),
            type="link",
            x=x,
            y=y,
            width=width,
            height=height,
            color=color,
            url=url,
        )

    def to_dict(self) -> dict:
        """Converte o node para dicionário compatível com JSON Canvas."""
        result: dict = {
            "id": self.id,
            "type": self.type,
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
        }

        # Adiciona campos opcionais apenas se definidos
        if self.color is not None:
            result["color"] = self.color

        if self.type == "text" and self.text is not None:
            result["text"] = self.text
        elif self.type == "file":
            if self.file is not None:
                result["file"] = self.file
            if self.subpath is not None:
                result["subpath"] = self.subpath
        elif self.type == "link" and self.url is not None:
            result["url"] = self.url
        elif self.type == "group":
            if self.label is not None:
                result["label"] = self.label
            if self.background is not None:
                result["background"] = self.background
            if self.background_style is not None:
                result["backgroundStyle"] = self.background_style

        return result


@dataclass
class Edge:
    """
    Representa uma conexão (edge) entre dois nodes.

    As edges conectam um node de origem (fromNode) a um node de destino (toNode).
    """

    id: str
    from_node: str
    to_node: str
    from_side: Side | None = None
    to_side: Side | None = None
    from_end: EndShape | None = None  # Default: "none"
    to_end: EndShape | None = None  # Default: "arrow"
    color: CanvasColor | None = None
    label: str | None = None

    @classmethod
    def create(
        cls,
        from_node: str,
        to_node: str,
        from_side: Side | None = None,
        to_side: Side | None = None,
        label: str | None = None,
        color: CanvasColor | None = None,
        edge_id: str | None = None,
    ) -> "Edge":
        """Cria uma edge entre dois nodes."""
        return cls(
            id=edge_id or generate_id(),
            from_node=from_node,
            to_node=to_node,
            from_side=from_side,
            to_side=to_side,
            label=label,
            color=color,
        )

    def to_dict(self) -> dict:
        """Converte a edge para dicionário compatível com JSON Canvas."""
        result: dict = {
            "id": self.id,
            "fromNode": self.from_node,
            "toNode": self.to_node,
        }

        if self.from_side is not None:
            result["fromSide"] = self.from_side
        if self.to_side is not None:
            result["toSide"] = self.to_side
        if self.from_end is not None:
            result["fromEnd"] = self.from_end
        if self.to_end is not None:
            result["toEnd"] = self.to_end
        if self.color is not None:
            result["color"] = self.color
        if self.label is not None:
            result["label"] = self.label

        return result


@dataclass
class Canvas:
    """
    Representa um JSON Canvas completo.

    Contém uma lista de nodes e edges que formam o diagrama.
    Nodes são ordenados por z-index (primeiro = abaixo, último = acima).
    """

    nodes: list[Node] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)

    def add_node(self, node: Node) -> "Canvas":
        """Adiciona um node ao canvas."""
        self.nodes.append(node)
        return self

    def add_edge(self, edge: Edge) -> "Canvas":
        """Adiciona uma edge ao canvas."""
        self.edges.append(edge)
        return self

    def get_node_by_id(self, node_id: str) -> Node | None:
        """Busca um node pelo ID."""
        for node in self.nodes:
            if node.id == node_id:
                return node
        return None

    def to_dict(self) -> dict:
        """Converte o canvas para dicionário compatível com JSON Canvas."""
        return {
            "nodes": [node.to_dict() for node in self.nodes],
            "edges": [edge.to_dict() for edge in self.edges],
        }
