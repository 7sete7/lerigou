"""Modelos de dados para representação intermediária de código."""

from dataclasses import dataclass, field
from enum import Enum


class ElementType(str, Enum):
    """Tipos de elementos de código."""

    MODULE = "module"
    CLASS = "class"
    FUNCTION = "function"
    METHOD = "method"
    VARIABLE = "variable"
    IMPORT = "import"
    CALL = "call"


@dataclass
class Parameter:
    """Representa um parâmetro de função/método."""

    name: str
    type_hint: str | None = None
    default_value: str | None = None
    is_args: bool = False  # *args
    is_kwargs: bool = False  # **kwargs


@dataclass
class FunctionCall:
    """Representa uma chamada de função."""

    name: str
    target: str | None = None  # Para method calls: obj.method()
    arguments: list[str] = field(default_factory=list)
    line_number: int = 0


@dataclass
class Import:
    """Representa um import."""

    module: str
    names: list[str] = field(default_factory=list)  # from X import Y, Z
    alias: str | None = None
    is_from: bool = False  # from X import Y vs import X
    line_number: int = 0


@dataclass
class CodeElement:
    """
    Representa um elemento de código (módulo, classe, função, etc).

    Esta é a representação intermediária usada para gerar o canvas.
    """

    name: str
    element_type: ElementType
    source_file: str = ""
    line_number: int = 0
    end_line_number: int = 0

    # Documentação
    docstring: str | None = None

    # Para funções/métodos
    parameters: list[Parameter] = field(default_factory=list)
    return_type: str | None = None
    is_async: bool = False
    is_generator: bool = False
    decorators: list[str] = field(default_factory=list)

    # Para classes
    base_classes: list[str] = field(default_factory=list)

    # Dependências e chamadas
    calls: list[FunctionCall] = field(default_factory=list)
    imports: list[Import] = field(default_factory=list)

    # Dados de fluxo
    inputs: list[str] = field(default_factory=list)  # Dados que entram
    outputs: list[str] = field(default_factory=list)  # Dados que saem

    # Hierarquia
    children: list["CodeElement"] = field(default_factory=list)
    parent: "CodeElement | None" = None

    def add_child(self, child: "CodeElement") -> "CodeElement":
        """Adiciona um elemento filho."""
        child.parent = self
        self.children.append(child)
        return self

    def get_qualified_name(self) -> str:
        """Retorna o nome qualificado do elemento (ex: MyClass.my_method)."""
        if self.parent and self.parent.element_type != ElementType.MODULE:
            return f"{self.parent.get_qualified_name()}.{self.name}"
        return self.name

    def get_functions(self) -> list["CodeElement"]:
        """Retorna todas as funções/métodos deste elemento."""
        result = []
        for child in self.children:
            if child.element_type in (ElementType.FUNCTION, ElementType.METHOD):
                result.append(child)
            result.extend(child.get_functions())
        return result

    def get_classes(self) -> list["CodeElement"]:
        """Retorna todas as classes deste elemento."""
        result = []
        for child in self.children:
            if child.element_type == ElementType.CLASS:
                result.append(child)
            result.extend(child.get_classes())
        return result

    def find_element(self, name: str) -> "CodeElement | None":
        """Busca um elemento pelo nome."""
        if self.name == name:
            return self
        for child in self.children:
            found = child.find_element(name)
            if found:
                return found
        return None

    def get_all_calls(self) -> list[FunctionCall]:
        """Retorna todas as chamadas de função deste elemento e filhos."""
        result = list(self.calls)
        for child in self.children:
            result.extend(child.get_all_calls())
        return result

    def to_markdown(self, include_params: bool = True) -> str:
        """Gera uma representação Markdown do elemento."""
        lines = []

        # Título
        type_emoji = {
            ElementType.MODULE: "📦",
            ElementType.CLASS: "🏛️",
            ElementType.FUNCTION: "⚙️",
            ElementType.METHOD: "🔧",
            ElementType.VARIABLE: "📊",
        }
        emoji = type_emoji.get(self.element_type, "")
        lines.append(f"### {emoji} {self.name}")

        # Decorators
        if self.decorators:
            for dec in self.decorators:
                lines.append(f"`@{dec}`")

        # Signature para funções/métodos
        if self.element_type in (ElementType.FUNCTION, ElementType.METHOD) and include_params:
            params = []
            for p in self.parameters:
                param_str = p.name
                if p.type_hint:
                    param_str += f": {p.type_hint}"
                if p.default_value:
                    param_str += f" = {p.default_value}"
                if p.is_args:
                    param_str = f"*{param_str}"
                if p.is_kwargs:
                    param_str = f"**{param_str}"
                params.append(param_str)

            sig = f"({', '.join(params)})"
            if self.return_type:
                sig += f" -> {self.return_type}"
            lines.append(f"```python\n{sig}\n```")

        # Base classes para classes
        if self.element_type == ElementType.CLASS and self.base_classes:
            lines.append(f"Herda de: {', '.join(self.base_classes)}")

        # Docstring
        if self.docstring:
            # Primeira linha da docstring
            first_line = self.docstring.strip().split("\n")[0]
            lines.append(f"\n{first_line}")

        return "\n".join(lines)


@dataclass
class CodeGraph:
    """
    Grafo de código representando relações entre elementos.
    """

    root: CodeElement
    # Mapa de nome qualificado -> elemento
    elements: dict[str, CodeElement] = field(default_factory=dict)
    # Mapa de chamadas: caller -> list[callee]
    call_graph: dict[str, list[str]] = field(default_factory=dict)

    def build_indices(self) -> None:
        """Constrói os índices de elementos e call graph."""
        self._index_element(self.root)
        self._build_call_graph(self.root)

    def _index_element(self, element: CodeElement) -> None:
        """Indexa um elemento e seus filhos."""
        qualified_name = element.get_qualified_name()
        self.elements[qualified_name] = element
        for child in element.children:
            self._index_element(child)

    def _build_call_graph(self, element: CodeElement) -> None:
        """Constrói o grafo de chamadas."""
        qualified_name = element.get_qualified_name()
        calls = []
        for call in element.calls:
            if call.target:
                calls.append(f"{call.target}.{call.name}")
            else:
                calls.append(call.name)
        if calls:
            self.call_graph[qualified_name] = calls

        for child in element.children:
            self._build_call_graph(child)

    def get_callers(self, element_name: str) -> list[str]:
        """Retorna os elementos que chamam o elemento especificado."""
        callers = []
        for caller, callees in self.call_graph.items():
            if element_name in callees:
                callers.append(caller)
        return callers

    def get_callees(self, element_name: str) -> list[str]:
        """Retorna os elementos chamados pelo elemento especificado."""
        return self.call_graph.get(element_name, [])
