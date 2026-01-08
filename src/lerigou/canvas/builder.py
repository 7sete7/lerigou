"""Builder com API fluente para construção de Canvas."""

from typing import Callable

from lerigou.canvas.layout import LayoutEngine, LayoutItem
from lerigou.canvas.models import Canvas, CanvasColor, Edge, Node


class GroupBuilder:
    """Builder para construção de grupos no canvas."""

    def __init__(
        self, parent: "CanvasBuilder", label: str, color: CanvasColor | None = None
    ):
        self.parent = parent
        self.label = label
        self.color = color
        self.items: list[LayoutItem] = []
        self.connections: list[tuple[str, str, str | None]] = []  # (from, to, label)
        self._layout_engine = LayoutEngine()

    def add_node(
        self,
        node_id: str,
        text: str | None = None,
        width: int = 250,
        height: int = 60,
        color: CanvasColor | None = None,
    ) -> "GroupBuilder":
        """Adiciona um node ao grupo."""
        display_text = text or node_id
        item = self._layout_engine.node(
            text=display_text,
            width=width,
            height=height,
            color=color,
            node_id=node_id,
        )
        self.items.append(item)
        return self

    def connect(
        self,
        from_node: str,
        to_node: str,
        label: str | None = None,
    ) -> "GroupBuilder":
        """Conecta dois nodes dentro do grupo."""
        self.connections.append((from_node, to_node, label))
        return self

    def row(self, *node_ids: str) -> "GroupBuilder":
        """Organiza os próximos nodes em uma linha horizontal."""
        # Marca para o layout posterior
        return self

    def build_layout(self) -> LayoutItem:
        """Constrói o LayoutItem do grupo."""
        if not self.items:
            # Grupo vazio
            return self._layout_engine.group(
                label=self.label,
                content=LayoutItem(width=100, height=50),
                color=self.color,
            )

        # Por padrão, organiza em coluna
        content = self._layout_engine.column(self.items)
        return self._layout_engine.group(
            label=self.label,
            content=content,
            color=self.color,
        )


class CanvasBuilder:
    """
    Builder com API fluente para construção de Canvas.

    Exemplo:
        builder = CanvasBuilder()
        with builder.group("MyModule", color="6") as g:
            g.add_node("func1", "Função 1")
            g.add_node("func2", "Função 2")
            g.connect("func1", "func2")
        canvas = builder.build()
    """

    def __init__(self):
        self._layout_engine = LayoutEngine()
        self._items: list[LayoutItem] = []
        self._groups: list[GroupBuilder] = []
        self._standalone_nodes: dict[str, LayoutItem] = {}
        self._edges: list[Edge] = []
        self._node_id_map: dict[str, Node] = {}

    def add_node(
        self,
        node_id: str,
        text: str | None = None,
        width: int = 250,
        height: int = 60,
        color: CanvasColor | None = None,
    ) -> "CanvasBuilder":
        """Adiciona um node standalone ao canvas."""
        display_text = text or node_id
        item = self._layout_engine.node(
            text=display_text,
            width=width,
            height=height,
            color=color,
            node_id=node_id,
        )
        self._standalone_nodes[node_id] = item
        self._items.append(item)
        return self

    def add_group(
        self,
        label: str,
        builder_fn: Callable[[GroupBuilder], None],
        color: CanvasColor | None = None,
    ) -> "CanvasBuilder":
        """
        Adiciona um grupo ao canvas usando uma função builder.

        Args:
            label: Rótulo do grupo
            builder_fn: Função que recebe um GroupBuilder para definir o conteúdo
            color: Cor do grupo
        """
        group = GroupBuilder(self, label, color)
        builder_fn(group)
        self._groups.append(group)
        self._items.append(group.build_layout())
        return self

    def group(self, label: str, color: CanvasColor | None = None) -> GroupBuilder:
        """
        Cria um grupo para uso com context manager.

        Exemplo:
            with builder.group("MyGroup") as g:
                g.add_node("node1")
        """
        group = GroupBuilder(self, label, color)
        return group

    def connect(
        self,
        from_node: str,
        to_node: str,
        label: str | None = None,
        from_side: str | None = None,
        to_side: str | None = None,
        color: CanvasColor | None = None,
    ) -> "CanvasBuilder":
        """Conecta dois nodes."""
        edge = Edge.create(
            from_node=from_node,
            to_node=to_node,
            label=label,
            from_side=from_side,  # type: ignore
            to_side=to_side,  # type: ignore
            color=color,
        )
        self._edges.append(edge)
        return self

    def row(self, items: list[LayoutItem]) -> "CanvasBuilder":
        """Adiciona uma linha de items ao canvas."""
        row_item = self._layout_engine.row(items)
        self._items.append(row_item)
        return self

    def column(self, items: list[LayoutItem]) -> "CanvasBuilder":
        """Adiciona uma coluna de items ao canvas."""
        col_item = self._layout_engine.column(items)
        self._items.append(col_item)
        return self

    def build(self, start_x: int = 0, start_y: int = 0) -> Canvas:
        """
        Constrói o Canvas final com todos os nodes posicionados.

        Args:
            start_x: Posição X inicial
            start_y: Posição Y inicial
        """
        canvas = Canvas()

        # Organiza todos os items em coluna por padrão
        if self._items:
            root = self._layout_engine.column(self._items)
            result = self._layout_engine.calculate_positions(root, start_x, start_y)

            # Adiciona nodes (grupos primeiro, depois os nodes internos)
            for node in result.nodes:
                canvas.add_node(node)
                self._node_id_map[node.id] = node

        # Adiciona edges dos grupos
        for group in self._groups:
            for from_id, to_id, label in group.connections:
                edge = Edge.create(
                    from_node=from_id,
                    to_node=to_id,
                    label=label,
                    from_side="right",
                    to_side="left",
                )
                canvas.add_edge(edge)

        # Adiciona edges standalone
        for edge in self._edges:
            canvas.add_edge(edge)

        return canvas


class FlowBuilder:
    """
    Builder especializado para criar fluxos de dados/processos.

    Facilita a criação de diagramas sequenciais com conexões automáticas.
    """

    def __init__(self):
        self._layout_engine = LayoutEngine()
        self._steps: list[tuple[str, str, CanvasColor | None]] = []  # (id, text, color)
        self._branches: dict[str, list[tuple[str, str, CanvasColor | None]]] = {}

    def step(
        self,
        step_id: str,
        text: str | None = None,
        color: CanvasColor | None = None,
    ) -> "FlowBuilder":
        """Adiciona um passo ao fluxo."""
        self._steps.append((step_id, text or step_id, color))
        return self

    def branch(
        self,
        from_step: str,
        branch_id: str,
        text: str | None = None,
        color: CanvasColor | None = None,
    ) -> "FlowBuilder":
        """Adiciona uma ramificação a partir de um passo."""
        if from_step not in self._branches:
            self._branches[from_step] = []
        self._branches[from_step].append((branch_id, text or branch_id, color))
        return self

    def build(self, direction: str = "row") -> Canvas:
        """
        Constrói o Canvas do fluxo.

        Args:
            direction: "row" para horizontal, "column" para vertical
        """
        canvas = Canvas()
        items: list[LayoutItem] = []

        # Cria nodes para cada passo
        for step_id, text, color in self._steps:
            item = self._layout_engine.node(
                text=text,
                color=color,
                node_id=step_id,
            )
            items.append(item)

        # Posiciona
        if direction == "row":
            container = self._layout_engine.row(items)
        else:
            container = self._layout_engine.column(items)

        result = self._layout_engine.calculate_positions(container)

        for node in result.nodes:
            canvas.add_node(node)

        # Cria edges sequenciais
        for i in range(len(self._steps) - 1):
            from_id = self._steps[i][0]
            to_id = self._steps[i + 1][0]
            from_side = "right" if direction == "row" else "bottom"
            to_side = "left" if direction == "row" else "top"
            edge = Edge.create(
                from_node=from_id,
                to_node=to_id,
                from_side=from_side,  # type: ignore
                to_side=to_side,  # type: ignore
            )
            canvas.add_edge(edge)

        return canvas
