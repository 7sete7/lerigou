"""Adapter para converter CodeElements em estrutura de Canvas."""

from lerigou.canvas.layout import LayoutEngine, LayoutItem
from lerigou.canvas.models import Canvas, Edge
from lerigou.processor.models import CodeElement, CodeGraph, ElementType

# Mapeamento de cores semânticas
COLORS = {
    ElementType.MODULE: "2",  # Laranja
    ElementType.CLASS: "6",  # Roxo
    ElementType.FUNCTION: "5",  # Cyan
    ElementType.METHOD: "5",  # Cyan
    ElementType.VARIABLE: "4",  # Verde
    "input": "4",  # Verde
    "output": "1",  # Vermelho
    "call": None,  # Sem cor especial
}


class CodeToCanvasAdapter:
    """
    Adapter que converte CodeElements em Canvas.

    Estratégia de layout:
    - Módulos e Classes são representados como Groups
    - Funções e Métodos são representados como Text nodes
    - Chamadas de função são representadas como Edges
    - Layout hierárquico (vertical por padrão)
    """

    def __init__(
        self,
        node_width: int = 280,
        node_height: int = 80,
        spacing: int = 40,
        group_padding: int = 25,
        include_docstrings: bool = True,
        include_params: bool = True,
        max_depth: int = 10,
    ):
        self.node_width = node_width
        self.node_height = node_height
        self.spacing = spacing
        self.group_padding = group_padding
        self.include_docstrings = include_docstrings
        self.include_params = include_params
        self.max_depth = max_depth
        self._layout = LayoutEngine(node_width, node_height)
        self._node_map: dict[str, str] = {}  # qualified_name -> node_id

    def convert(self, root: CodeElement) -> Canvas:
        """
        Converte um CodeElement raiz em Canvas.

        Args:
            root: Elemento raiz (geralmente um módulo)

        Returns:
            Canvas com a representação visual
        """
        self._node_map.clear()

        # Cria o grafo de código
        graph = CodeGraph(root=root)
        graph.build_indices()

        # Cria o layout do elemento raiz
        layout_item = self._create_layout_item(root, depth=0)

        # Calcula posições
        result = self._layout.calculate_positions(layout_item)

        # Cria o canvas
        canvas = Canvas()
        for node in result.nodes:
            canvas.add_node(node)

        # Adiciona edges para chamadas
        self._add_call_edges(canvas, graph)

        return canvas

    def convert_from_entrypoint(
        self,
        root: CodeElement,
        entrypoint: str,
    ) -> Canvas:
        """
        Converte a partir de um entrypoint específico.

        Filtra para mostrar apenas elementos relacionados ao entrypoint.

        Args:
            root: Elemento raiz
            entrypoint: Nome do entrypoint (ex: "main" ou "MyClass.process")

        Returns:
            Canvas filtrado
        """
        # Encontra o elemento do entrypoint
        target = root.find_element(entrypoint.split(".")[-1])

        if target is None:
            # Se não encontrou, tenta buscar pelo nome qualificado
            for child in root.children:
                if entrypoint in child.get_qualified_name():
                    target = child
                    break

        if target is None:
            # Fallback: converte o root completo
            return self.convert(root)

        # Cria um grafo focado no entrypoint
        graph = CodeGraph(root=root)
        graph.build_indices()

        # Coleta elementos relacionados ao entrypoint
        related_elements = self._collect_related_elements(target, graph)

        # Cria o canvas apenas com elementos relacionados
        return self._convert_filtered(root, related_elements, graph)

    def _create_layout_item(
        self,
        element: CodeElement,
        depth: int = 0,
    ) -> LayoutItem:
        """Cria um LayoutItem para um CodeElement."""
        if depth > self.max_depth:
            return self._create_node_item(element)

        if element.element_type == ElementType.MODULE:
            return self._create_module_layout(element, depth)
        elif element.element_type == ElementType.CLASS:
            return self._create_class_layout(element, depth)
        else:
            return self._create_node_item(element)

    def _create_module_layout(
        self,
        module: CodeElement,
        depth: int,
    ) -> LayoutItem:
        """Cria layout para um módulo."""
        children_items = []

        # Agrupa por tipo
        classes = [c for c in module.children if c.element_type == ElementType.CLASS]
        functions = [
            c
            for c in module.children
            if c.element_type in (ElementType.FUNCTION, ElementType.METHOD)
        ]
        variables = [c for c in module.children if c.element_type == ElementType.VARIABLE]

        # Cria items para classes
        for cls in classes:
            item = self._create_layout_item(cls, depth + 1)
            children_items.append(item)

        # Cria row de funções
        if functions:
            func_items = [self._create_node_item(f) for f in functions]
            # Se muitas funções, organiza em coluna
            if len(func_items) > 3:
                children_items.append(self._layout.column(func_items))
            else:
                children_items.append(self._layout.row(func_items))

        # Cria row de variáveis (se poucas)
        if variables and len(variables) <= 5:
            var_items = [self._create_node_item(v) for v in variables]
            children_items.append(self._layout.row(var_items))

        if not children_items:
            # Módulo vazio
            return self._create_node_item(module)

        content = self._layout.column(children_items)
        return self._layout.group(
            label=f"📦 {module.name}",
            content=content,
            color=COLORS[ElementType.MODULE],
            padding=self.group_padding,
        )

    def _create_class_layout(
        self,
        cls: CodeElement,
        depth: int,
    ) -> LayoutItem:
        """Cria layout para uma classe."""
        method_items = []

        # Ordena métodos: __init__ primeiro, depois públicos, depois privados
        methods = [
            c for c in cls.children if c.element_type in (ElementType.FUNCTION, ElementType.METHOD)
        ]

        def method_sort_key(m: CodeElement) -> tuple[int, str]:
            if m.name == "__init__":
                return (0, m.name)
            elif m.name.startswith("_"):
                return (2, m.name)
            else:
                return (1, m.name)

        methods.sort(key=method_sort_key)

        for method in methods:
            item = self._create_node_item(method)
            method_items.append(item)

        if not method_items:
            # Classe sem métodos
            return self._create_node_item(cls)

        # Organiza métodos em coluna dentro do grupo
        content = self._layout.column(method_items, spacing=20)

        # Monta o label com herança
        label = f"🏛️ {cls.name}"
        if cls.base_classes:
            label += f" ({', '.join(cls.base_classes)})"

        return self._layout.group(
            label=label,
            content=content,
            color=COLORS[ElementType.CLASS],
            padding=self.group_padding,
        )

    def _create_node_item(self, element: CodeElement) -> LayoutItem:
        """Cria um LayoutItem de node para um elemento."""
        qualified_name = element.get_qualified_name()
        node_id = self._generate_node_id(qualified_name)
        self._node_map[qualified_name] = node_id

        # Gera o texto do node
        text = self._generate_node_text(element)

        # Determina a altura baseada no conteúdo
        line_count = text.count("\n") + 1
        height = max(self.node_height, line_count * 20 + 20)

        # Determina a cor
        color = COLORS.get(element.element_type)

        return self._layout.node(
            text=text,
            width=self.node_width,
            height=height,
            color=color,
            node_id=node_id,
        )

    def _generate_node_text(self, element: CodeElement) -> str:
        """Gera o texto para um node."""
        lines = []

        # Nome do elemento
        if element.element_type in (ElementType.FUNCTION, ElementType.METHOD):
            prefix = "async " if element.is_async else ""
            lines.append(f"### {prefix}{element.name}")

            # Parâmetros
            if self.include_params and element.parameters:
                params = []
                for p in element.parameters[:4]:  # Limita a 4 params
                    if p.name == "self":
                        continue
                    param_str = p.name
                    if p.type_hint:
                        param_str += f": {p.type_hint}"
                    params.append(param_str)
                if params:
                    lines.append(f"({', '.join(params)})")

            # Return type
            if element.return_type:
                lines.append(f"→ {element.return_type}")

        elif element.element_type == ElementType.CLASS:
            lines.append(f"### {element.name}")
            if element.base_classes:
                lines.append(f"extends {', '.join(element.base_classes)}")

        elif element.element_type == ElementType.VARIABLE:
            lines.append(f"**{element.name}**")

        else:
            lines.append(f"### {element.name}")

        # Docstring (primeira linha apenas)
        if self.include_docstrings and element.docstring:
            first_line = element.docstring.strip().split("\n")[0][:50]
            lines.append(f"\n_{first_line}_")

        return "\n".join(lines)

    def _generate_node_id(self, qualified_name: str) -> str:
        """Gera um ID único para um node."""
        # Remove caracteres especiais
        clean_name = qualified_name.replace(".", "_").replace("<", "").replace(">", "")
        return clean_name[:16] or "node"

    def _add_call_edges(self, canvas: Canvas, graph: CodeGraph) -> None:
        """Adiciona edges para chamadas de função."""
        for caller_name, callees in graph.call_graph.items():
            caller_id = self._node_map.get(caller_name)
            if not caller_id:
                continue

            for callee_name in callees:
                # Tenta encontrar o callee no mapa
                callee_id = None

                # Busca exata
                if callee_name in self._node_map:
                    callee_id = self._node_map[callee_name]
                else:
                    # Busca parcial (apenas o nome da função)
                    simple_name = callee_name.split(".")[-1]
                    for qname, nid in self._node_map.items():
                        if qname.endswith(f".{simple_name}") or qname == simple_name:
                            callee_id = nid
                            break

                if callee_id and caller_id != callee_id:
                    edge = Edge.create(
                        from_node=caller_id,
                        to_node=callee_id,
                        from_side="right",
                        to_side="left",
                    )
                    canvas.add_edge(edge)

    def _collect_related_elements(
        self,
        target: CodeElement,
        graph: CodeGraph,
        visited: set[str] | None = None,
    ) -> set[str]:
        """Coleta elementos relacionados a um target (callees e callers)."""
        if visited is None:
            visited = set()

        qualified_name = target.get_qualified_name()
        if qualified_name in visited:
            return visited

        visited.add(qualified_name)

        # Adiciona callees
        for callee in graph.get_callees(qualified_name):
            if callee in graph.elements:
                element = graph.elements[callee]
                self._collect_related_elements(element, graph, visited)

        # Adiciona callers (um nível apenas)
        for caller in graph.get_callers(qualified_name):
            visited.add(caller)

        return visited

    def _convert_filtered(
        self,
        root: CodeElement,
        related_names: set[str],
        graph: CodeGraph,
    ) -> Canvas:
        """Converte apenas os elementos filtrados."""
        # Cria uma versão filtrada do elemento
        filtered_root = self._filter_element(root, related_names)

        if filtered_root is None:
            return Canvas()

        # Converte normalmente
        return self.convert(filtered_root)

    def _filter_element(
        self,
        element: CodeElement,
        related_names: set[str],
    ) -> CodeElement | None:
        """Filtra um elemento mantendo apenas os relacionados."""
        qualified_name = element.get_qualified_name()

        # Verifica se o elemento ou algum filho é relevante
        is_relevant = qualified_name in related_names

        # Filtra filhos
        filtered_children = []
        for child in element.children:
            filtered_child = self._filter_element(child, related_names)
            if filtered_child:
                filtered_children.append(filtered_child)
                is_relevant = True

        if not is_relevant:
            return None

        # Cria cópia do elemento com filhos filtrados
        filtered = CodeElement(
            name=element.name,
            element_type=element.element_type,
            source_file=element.source_file,
            line_number=element.line_number,
            end_line_number=element.end_line_number,
            docstring=element.docstring,
            parameters=element.parameters,
            return_type=element.return_type,
            is_async=element.is_async,
            is_generator=element.is_generator,
            decorators=element.decorators,
            base_classes=element.base_classes,
            calls=element.calls,
            imports=element.imports,
            inputs=element.inputs,
            outputs=element.outputs,
        )

        for child in filtered_children:
            filtered.add_child(child)

        return filtered
