"""Adapter para converter análise de IA em Canvas de fluxo."""

from lerigou.ai.models import AnalysisResult, CodeFlow, DataFormat, FlowStep
from lerigou.canvas.models import Canvas, Edge, Node
from lerigou.utils.text_dimensions import calculate_node_dimensions

# Cores por tipo de passo
STEP_COLORS = {
    "start": "4",  # Verde - entrada
    "process": "5",  # Cyan - processamento
    "decision": "3",  # Amarelo - decisão
    "data": "6",  # Roxo - dados
    "end": "4",  # Verde - saída
    "error": "1",  # Vermelho - erro
}

# Larguras base por tipo de passo
STEP_BASE_WIDTHS = {
    "start": 220,
    "process": 280,
    "decision": 250,
    "data": 280,
    "end": 220,
    "error": 220,
}

# Alturas mínimas por tipo de passo
STEP_MIN_HEIGHTS = {
    "start": 60,
    "process": 80,
    "decision": 70,
    "data": 80,
    "end": 60,
    "error": 60,
}


class AIToCanvasAdapter:
    """
    Converte o resultado da análise de IA em um Canvas de fluxo visual.

    Layout do canvas:
    - Fluxo linear de cima para baixo
    - Ramificações horizontais para decisões
    - Setas (edges) conectando todos os passos
    - Seção de dados separada à direita
    """

    def __init__(
        self,
        node_width: int = 250,
        node_height: int = 80,
        h_spacing: int = 110,
        v_spacing: int = 90,
        data_section_x: int = 900,
    ):
        self.node_width = node_width
        self.node_height = node_height
        self.h_spacing = h_spacing
        self.v_spacing = v_spacing
        self.data_section_x = data_section_x
        self._node_positions: dict[str, tuple[int, int]] = {}  # step_id -> (x, y)
        self._step_node_ids: dict[str, str] = {}  # step_id -> node_id

    def convert(self, analysis: AnalysisResult) -> Canvas:
        """
        Converte o resultado da análise em Canvas de fluxo.

        Args:
            analysis: Resultado da análise de IA

        Returns:
            Canvas com o fluxograma visual
        """
        self._node_positions.clear()
        self._step_node_ids.clear()
        canvas = Canvas()

        # Adiciona resumo no topo
        summary_node = self._create_summary_node(analysis.summary)
        canvas.add_node(summary_node)

        # Processa o fluxo principal
        flow_nodes, flow_edges = self._process_flow(analysis.main_flow, start_y=100)
        for node in flow_nodes:
            canvas.add_node(node)
        for edge in flow_edges:
            canvas.add_edge(edge)

        # Processa sub-fluxos
        sub_start_y = 100
        for i, sub_flow in enumerate(analysis.sub_flows):
            sub_nodes, sub_edges = self._process_flow(
                sub_flow, start_x=self.data_section_x + 400, start_y=sub_start_y
            )
            for node in sub_nodes:
                canvas.add_node(node)
            for edge in sub_edges:
                canvas.add_edge(edge)
            if sub_nodes:
                sub_start_y = max(n.y + n.height for n in sub_nodes) + self.v_spacing * 2

        # Cria seção de dados
        if analysis.data_formats:
            data_nodes = self._create_data_section(analysis.data_formats)
            for node in data_nodes:
                canvas.add_node(node)

        return canvas

    def _create_summary_node(self, summary: str) -> Node:
        """Cria o node de resumo."""
        text = f"## 📋 Fluxo de Execução\n\n{summary}"
        width, height = calculate_node_dimensions(
            text,
            node_type="text",
            base_width=self.node_width * 3,
            base_height=80,
        )
        return Node.text_node(
            text=text,
            x=0,
            y=0,
            width=width,
            height=height,
            node_id="summary",
        )

    def _process_flow(
        self, flow: CodeFlow, start_x: int = 0, start_y: int = 0
    ) -> tuple[list[Node], list[Edge]]:
        """
        Processa um fluxo e gera nodes e edges.

        Returns:
            Tupla (lista de nodes, lista de edges)
        """
        nodes: list[Node] = []
        edges: list[Edge] = []

        if not flow.steps:
            return nodes, edges

        # Calcula posições dos passos
        positions = self._calculate_positions(flow, start_x, start_y)

        # Cria nodes para cada passo
        for step in flow.steps:
            pos = positions.get(step.id, (start_x, start_y))
            node = self._create_step_node(step, pos[0], pos[1])
            nodes.append(node)
            self._step_node_ids[step.id] = node.id
            self._node_positions[step.id] = (node.x, node.y)

        # Cria edges para conexões
        for conn in flow.connections:
            from_id = self._step_node_ids.get(conn.from_step)
            to_id = self._step_node_ids.get(conn.to_step)

            if from_id and to_id:
                from_pos = self._node_positions.get(conn.from_step, (0, 0))
                to_pos = self._node_positions.get(conn.to_step, (0, 0))

                # Determina lados da conexão baseado nas posições
                from_side, to_side = self._determine_sides(from_pos, to_pos)

                edge = Edge.create(
                    from_node=from_id,
                    to_node=to_id,
                    from_side=from_side,
                    to_side=to_side,
                    label=conn.label,
                    color="1" if conn.is_error else None,
                )
                edges.append(edge)

        return nodes, edges

    def _calculate_positions(
        self, flow: CodeFlow, start_x: int, start_y: int
    ) -> dict[str, tuple[int, int]]:
        """
        Calcula as posições de cada passo no fluxo.

        Usa um algoritmo de layout vertical com ramificações horizontais.
        """
        positions: dict[str, tuple[int, int]] = {}
        visited: set[str] = set()

        # Encontra o passo inicial
        start_steps = [s for s in flow.steps if s.step_type == "start"]
        if not start_steps:
            start_steps = flow.steps[:1] if flow.steps else []

        # Constrói grafo de conexões
        next_steps: dict[str, list[tuple[str, str | None]]] = {}  # step_id -> [(next_id, label)]
        for conn in flow.connections:
            if conn.from_step not in next_steps:
                next_steps[conn.from_step] = []
            next_steps[conn.from_step].append((conn.to_step, conn.label))

        # Layout usando BFS
        current_y = start_y
        current_x = start_x + self.node_width  # Centraliza

        for start in start_steps:
            if start.id in visited:
                continue

            queue = [(start.id, current_x, current_y, 0)]  # (step_id, x, y, branch_level)

            while queue:
                step_id, x, y, branch = queue.pop(0)

                if step_id in visited:
                    continue

                visited.add(step_id)

                # Encontra o step
                step = next((s for s in flow.steps if s.id == step_id), None)
                if not step:
                    continue

                # Posiciona o step
                step_w = STEP_BASE_WIDTHS.get(step.step_type, self.node_width)
                step_h = STEP_MIN_HEIGHTS.get(step.step_type, self.node_height)
                positions[step_id] = (x, y)

                # Processa próximos passos
                nexts = next_steps.get(step_id, [])

                if len(nexts) == 1:
                    # Fluxo linear - continua para baixo
                    next_id, _ = nexts[0]
                    if next_id not in visited:
                        queue.append((next_id, x, y + step_h + self.v_spacing, branch))

                elif len(nexts) == 2:
                    # Ramificação - um para cada lado
                    for i, (next_id, label) in enumerate(nexts):
                        if next_id not in visited:
                            if i == 0:
                                # Caminho principal (sim) - continua para baixo
                                queue.append((next_id, x, y + step_h + self.v_spacing, branch))
                            else:
                                # Caminho alternativo (não) - vai para o lado
                                queue.append(
                                    (
                                        next_id,
                                        x + step_w + self.h_spacing,
                                        y + step_h + self.v_spacing,
                                        branch + 1,
                                    )
                                )

                elif len(nexts) > 2:
                    # Múltiplas ramificações
                    for i, (next_id, label) in enumerate(nexts):
                        if next_id not in visited:
                            offset = (i - len(nexts) // 2) * (step_w + self.h_spacing)
                            queue.append(
                                (next_id, x + offset, y + step_h + self.v_spacing, branch + i)
                            )

                current_y = max(current_y, y + step_h + self.v_spacing)

        # Posiciona steps não conectados
        for step in flow.steps:
            if step.id not in positions:
                positions[step.id] = (current_x + self.node_width * 2, current_y)
                current_y += self.node_height + self.v_spacing

        return positions

    def _create_step_node(self, step: FlowStep, x: int, y: int) -> Node:
        """Cria um node para um passo do fluxo."""
        step_type = step.step_type or "process"
        color = STEP_COLORS.get(step_type, "5")
        base_width = STEP_BASE_WIDTHS.get(step_type, self.node_width)
        min_height = STEP_MIN_HEIGHTS.get(step_type, self.node_height)

        # Monta o texto do node
        lines = []

        # Ícone por tipo
        icons = {
            "start": "▶️",
            "process": "⚙️",
            "decision": "❓",
            "data": "💾",
            "end": "🏁",
            "error": "❌",
        }
        icon = icons.get(step_type, "•")

        lines.append(f"{icon} **{step.name}**")

        if step.description and step.description != step.name:
            # Não trunca a descrição, deixa o cálculo de dimensão lidar
            lines.append(f"_{step.description}_")

        if step.function:
            lines.append(f"`{step.function}()`")

        if step.inputs:
            inputs_text = ", ".join(step.inputs[:4])
            lines.append(f"⬅️ {inputs_text}")

        if step.outputs:
            outputs_text = ", ".join(step.outputs[:4])
            lines.append(f"➡️ {outputs_text}")

        text = "\n".join(lines)

        # Calcula dimensões baseado no conteúdo real
        width, height = calculate_node_dimensions(
            text,
            node_type=step_type,
            base_width=base_width,
            base_height=min_height,
        )

        return Node.text_node(
            text=text,
            x=x,
            y=y,
            width=width,
            height=height,
            color=color,
            node_id=f"step_{step.id}",
        )

    def _determine_sides(
        self, from_pos: tuple[int, int], to_pos: tuple[int, int]
    ) -> tuple[str, str]:
        """Determina os lados de conexão baseado nas posições."""
        from_x, from_y = from_pos
        to_x, to_y = to_pos

        # Calcula diferença
        dx = to_x - from_x
        dy = to_y - from_y

        # Determina direção predominante
        if abs(dy) > abs(dx):
            # Movimento vertical predominante
            if dy > 0:
                return "bottom", "top"
            else:
                return "top", "bottom"
        else:
            # Movimento horizontal predominante
            if dx > 0:
                return "right", "left"
            else:
                return "left", "right"

    def _create_data_section(self, data_formats: list[DataFormat]) -> list[Node]:
        """Cria a seção de formatos de dados."""
        nodes: list[Node] = []

        # Título da seção
        title_node = Node.text_node(
            text="## 📊 Formatos de Dados",
            x=self.data_section_x,
            y=0,
            width=300,
            height=50,
            color="4",
            node_id="data_section_title",
        )
        nodes.append(title_node)

        current_y = 70

        for data_format in data_formats:
            node = self._create_data_format_node(data_format, current_y)
            nodes.append(node)
            current_y += node.height + 20

        return nodes

    def _create_data_format_node(self, data_format: DataFormat, y: int) -> Node:
        """Cria um node de formato de dados."""
        lines = [f"### {data_format.name}", "", data_format.description]

        if data_format.fields:
            lines.append("")
            for field in data_format.fields[:6]:
                lines.append(f"• {field}")
            if len(data_format.fields) > 6:
                lines.append(f"• ... (+{len(data_format.fields) - 6} campos)")

        text = "\n".join(lines)
        width, height = calculate_node_dimensions(
            text,
            node_type="data",
            base_width=320,
            base_height=80,
        )

        return Node.text_node(
            text=text,
            x=self.data_section_x,
            y=y,
            width=width,
            height=height,
            color="4",
            node_id=f"data_{data_format.name.lower().replace(' ', '_')}",
        )
