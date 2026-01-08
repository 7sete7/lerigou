"""Engine de layout para posicionamento automático de nodes no canvas."""

from dataclasses import dataclass, field

from lerigou.canvas.models import CanvasColor, Node


@dataclass
class LayoutItem:
    """
    Item de layout que representa um node ou container.

    Pode ser um node individual ou um container (row, column, group).
    """

    width: int = 250
    height: int = 60
    node: Node | None = None
    children: list["LayoutItem"] = field(default_factory=list)
    layout_type: str = "node"  # "node", "row", "column", "group"
    label: str | None = None
    color: CanvasColor | None = None
    padding: int = 20
    spacing: int = 40


@dataclass
class LayoutResult:
    """Resultado do cálculo de layout com nodes posicionados."""

    nodes: list[Node]
    width: int
    height: int


class LayoutEngine:
    """
    Engine de layout para posicionamento automático de nodes.

    Suporta:
    - row(): Alinha items horizontalmente
    - column(): Alinha items verticalmente
    - group(): Encapsula items em um grupo visual
    """

    def __init__(self, default_node_width: int = 250, default_node_height: int = 60):
        self.default_node_width = default_node_width
        self.default_node_height = default_node_height
        self.default_spacing = 40
        self.default_padding = 20

    def node(
        self,
        text: str,
        width: int | None = None,
        height: int | None = None,
        color: CanvasColor | None = None,
        node_id: str | None = None,
    ) -> LayoutItem:
        """Cria um item de layout para um node de texto."""
        w = width or self.default_node_width
        h = height or self.default_node_height
        return LayoutItem(
            width=w,
            height=h,
            node=Node.text_node(
                text=text,
                width=w,
                height=h,
                color=color,
                node_id=node_id,
            ),
            layout_type="node",
        )

    def row(
        self,
        items: list[LayoutItem],
        spacing: int | None = None,
    ) -> LayoutItem:
        """
        Cria um container que alinha items horizontalmente.

        Args:
            items: Lista de LayoutItems para alinhar
            spacing: Espaçamento horizontal entre items
        """
        sp = spacing if spacing is not None else self.default_spacing
        return LayoutItem(
            children=items,
            layout_type="row",
            spacing=sp,
        )

    def column(
        self,
        items: list[LayoutItem],
        spacing: int | None = None,
    ) -> LayoutItem:
        """
        Cria um container que alinha items verticalmente.

        Args:
            items: Lista de LayoutItems para alinhar
            spacing: Espaçamento vertical entre items
        """
        sp = spacing if spacing is not None else self.default_spacing
        return LayoutItem(
            children=items,
            layout_type="column",
            spacing=sp,
        )

    def group(
        self,
        label: str,
        content: LayoutItem,
        color: CanvasColor | None = None,
        padding: int | None = None,
    ) -> LayoutItem:
        """
        Cria um grupo visual que encapsula outros items.

        Args:
            label: Rótulo do grupo
            content: LayoutItem contendo o conteúdo do grupo
            color: Cor do grupo
            padding: Padding interno do grupo
        """
        p = padding if padding is not None else self.default_padding
        return LayoutItem(
            children=[content],
            layout_type="group",
            label=label,
            color=color,
            padding=p,
        )

    def calculate_size(self, item: LayoutItem) -> tuple[int, int]:
        """
        Calcula o tamanho total de um item de layout.

        Returns:
            Tupla (width, height)
        """
        if item.layout_type == "node":
            return (item.width, item.height)

        if not item.children:
            return (0, 0)

        if item.layout_type == "row":
            total_width = 0
            max_height = 0
            for i, child in enumerate(item.children):
                w, h = self.calculate_size(child)
                total_width += w
                if i < len(item.children) - 1:
                    total_width += item.spacing
                max_height = max(max_height, h)
            return (total_width, max_height)

        if item.layout_type == "column":
            max_width = 0
            total_height = 0
            for i, child in enumerate(item.children):
                w, h = self.calculate_size(child)
                max_width = max(max_width, w)
                total_height += h
                if i < len(item.children) - 1:
                    total_height += item.spacing
            return (max_width, total_height)

        if item.layout_type == "group":
            if item.children:
                content_w, content_h = self.calculate_size(item.children[0])
                # Adiciona padding ao redor do conteúdo + espaço para o label
                return (
                    content_w + 2 * item.padding,
                    content_h + 2 * item.padding + 30,  # 30 para o label
                )
            return (0, 0)

        return (item.width, item.height)

    def calculate_positions(
        self,
        item: LayoutItem,
        start_x: int = 0,
        start_y: int = 0,
    ) -> LayoutResult:
        """
        Calcula as posições absolutas de todos os nodes.

        Args:
            item: Item de layout raiz
            start_x: Posição X inicial
            start_y: Posição Y inicial

        Returns:
            LayoutResult com nodes posicionados e dimensões totais
        """
        nodes: list[Node] = []

        if item.layout_type == "node" and item.node:
            # Node simples - posiciona diretamente
            item.node.x = start_x
            item.node.y = start_y
            return LayoutResult(
                nodes=[item.node],
                width=item.width,
                height=item.height,
            )

        if item.layout_type == "row":
            current_x = start_x
            max_height = 0
            for i, child in enumerate(item.children):
                child_w, child_h = self.calculate_size(child)
                # Centraliza verticalmente
                child_y = start_y + (self.calculate_size(item)[1] - child_h) // 2
                result = self.calculate_positions(child, current_x, child_y)
                nodes.extend(result.nodes)
                current_x += child_w + item.spacing
                max_height = max(max_height, child_h)
            total_width = current_x - item.spacing - start_x if item.children else 0
            return LayoutResult(nodes=nodes, width=total_width, height=max_height)

        if item.layout_type == "column":
            current_y = start_y
            max_width = 0
            for i, child in enumerate(item.children):
                child_w, child_h = self.calculate_size(child)
                result = self.calculate_positions(child, start_x, current_y)
                nodes.extend(result.nodes)
                current_y += child_h + item.spacing
                max_width = max(max_width, child_w)
            total_height = current_y - item.spacing - start_y if item.children else 0
            return LayoutResult(nodes=nodes, width=max_width, height=total_height)

        if item.layout_type == "group":
            group_w, group_h = self.calculate_size(item)
            # Cria o node do grupo (deve vir primeiro para ficar abaixo)
            group_node = Node.group_node(
                label=item.label or "",
                x=start_x,
                y=start_y,
                width=group_w,
                height=group_h,
                color=item.color,
            )
            nodes.append(group_node)

            # Posiciona o conteúdo dentro do grupo
            if item.children:
                content_x = start_x + item.padding
                content_y = start_y + item.padding + 30  # Espaço para o label
                result = self.calculate_positions(item.children[0], content_x, content_y)
                nodes.extend(result.nodes)

            return LayoutResult(nodes=nodes, width=group_w, height=group_h)

        return LayoutResult(nodes=[], width=0, height=0)


def auto_layout(
    items: list[LayoutItem], direction: str = "column", spacing: int = 40
) -> LayoutResult:
    """
    Função auxiliar para layout automático simples.

    Args:
        items: Lista de LayoutItems
        direction: "row" ou "column"
        spacing: Espaçamento entre items
    """
    engine = LayoutEngine()
    if direction == "row":
        container = engine.row(items, spacing)
    else:
        container = engine.column(items, spacing)
    return engine.calculate_positions(container)
