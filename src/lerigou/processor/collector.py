"""Coletor de código que segue chamadas de função e imports."""

import ast
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class CodeChunk:
    """Representa um pedaço de código coletado."""

    name: str
    code: str
    file_path: str
    line_start: int
    line_end: int
    chunk_type: str  # "function", "class", "method", "module"
    docstring: str | None = None
    calls: list[str] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)


@dataclass
class CollectedCode:
    """Resultado da coleta de código."""

    entrypoint: str
    chunks: list[CodeChunk]
    all_imports: list[str]
    concatenated_code: str

    def to_prompt_context(self) -> str:
        """Gera o contexto de código para o prompt da IA."""
        sections = []

        sections.append(f"## Entrypoint: {self.entrypoint}\n")

        for chunk in self.chunks:
            header = f"### {chunk.chunk_type.upper()}: {chunk.name}"
            if chunk.file_path:
                header += f" (from {Path(chunk.file_path).name})"
            sections.append(header)
            sections.append(f"```python\n{chunk.code}\n```")
            if chunk.calls:
                sections.append(f"Calls: {', '.join(chunk.calls)}")
            sections.append("")

        return "\n".join(sections)


class CodeCollector:
    """
    Coleta código seguindo chamadas de função a partir de um entrypoint.

    Traversa o código seguindo:
    - Chamadas de função diretas
    - Imports locais (do mesmo projeto)
    - Métodos de classes instanciadas
    """

    def __init__(self, base_path: Path | None = None):
        self.base_path = base_path or Path.cwd()
        self._collected: dict[str, CodeChunk] = {}
        self._visited: set[str] = set()
        self._file_cache: dict[str, str] = {}
        self._ast_cache: dict[str, ast.Module] = {}
        self._import_map: dict[str, Path] = {}

    def collect_from_entrypoint(
        self,
        file_path: Path,
        entrypoint: str | None = None,
    ) -> CollectedCode:
        """
        Coleta todo o código relevante a partir de um entrypoint.

        Args:
            file_path: Caminho do arquivo principal
            entrypoint: Nome da função/classe de entrada (opcional)

        Returns:
            CollectedCode com todos os chunks coletados
        """
        self._collected.clear()
        self._visited.clear()
        self._file_cache.clear()
        self._ast_cache.clear()
        self._import_map.clear()

        # Carrega o arquivo principal
        source = self._read_file(file_path)
        tree = self._parse_file(file_path, source)

        # Coleta imports do arquivo
        self._collect_imports(tree, file_path)

        if entrypoint:
            # Busca o entrypoint específico
            self._collect_entrypoint(tree, file_path, source, entrypoint)
        else:
            # Coleta todas as funções/classes do módulo
            self._collect_module(tree, file_path, source)

        # Ordena chunks por ordem de dependência
        chunks = self._order_chunks()

        # Gera código concatenado
        concatenated = "\n\n".join(f"# {c.chunk_type}: {c.name}\n{c.code}" for c in chunks)

        # Coleta todos os imports únicos
        all_imports = list(set(imp for c in chunks for imp in c.imports))

        return CollectedCode(
            entrypoint=entrypoint or file_path.stem,
            chunks=chunks,
            all_imports=all_imports,
            concatenated_code=concatenated,
        )

    def _read_file(self, file_path: Path) -> str:
        """Lê e cacheia o conteúdo de um arquivo."""
        key = str(file_path)
        if key not in self._file_cache:
            self._file_cache[key] = file_path.read_text(encoding="utf-8")
        return self._file_cache[key]

    def _parse_file(self, file_path: Path, source: str) -> ast.Module:
        """Parseia e cacheia a AST de um arquivo."""
        key = str(file_path)
        if key not in self._ast_cache:
            self._ast_cache[key] = ast.parse(source, filename=str(file_path))
        return self._ast_cache[key]

    def _collect_imports(self, tree: ast.Module, file_path: Path) -> None:
        """Coleta e mapeia imports locais."""
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self._try_resolve_import(alias.name, file_path)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    self._try_resolve_import(node.module, file_path)
                    for alias in node.names:
                        full_name = f"{node.module}.{alias.name}"
                        self._try_resolve_import(full_name, file_path)

    def _try_resolve_import(self, module_name: str, from_file: Path) -> None:
        """Tenta resolver um import para um arquivo local."""
        parts = module_name.split(".")

        # Tenta encontrar o arquivo no mesmo diretório ou subdiretórios
        base_dir = from_file.parent

        # Tenta como arquivo direto
        for i in range(len(parts), 0, -1):
            partial = "/".join(parts[:i])
            candidate = base_dir / f"{partial}.py"
            if candidate.exists():
                self._import_map[module_name] = candidate
                return

            # Tenta como pacote
            candidate = base_dir / partial / "__init__.py"
            if candidate.exists():
                self._import_map[module_name] = candidate.parent
                return

        # Tenta a partir do base_path
        for i in range(len(parts), 0, -1):
            partial = "/".join(parts[:i])
            candidate = self.base_path / f"{partial}.py"
            if candidate.exists():
                self._import_map[module_name] = candidate
                return

    def _collect_entrypoint(
        self,
        tree: ast.Module,
        file_path: Path,
        source: str,
        entrypoint: str,
    ) -> None:
        """Coleta a partir de um entrypoint específico."""
        # Busca a função/classe
        parts = entrypoint.split(".")

        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name == parts[0]:
                self._collect_function(node, file_path, source)
            elif isinstance(node, ast.AsyncFunctionDef) and node.name == parts[0]:
                self._collect_function(node, file_path, source)
            elif isinstance(node, ast.ClassDef) and node.name == parts[0]:
                if len(parts) > 1:
                    # Busca método específico
                    for item in node.body:
                        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            if item.name == parts[1]:
                                self._collect_function(
                                    item, file_path, source, class_name=node.name
                                )
                else:
                    self._collect_class(node, file_path, source)

    def _collect_module(
        self,
        tree: ast.Module,
        file_path: Path,
        source: str,
    ) -> None:
        """Coleta todas as funções e classes de um módulo."""
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._collect_function(node, file_path, source)
            elif isinstance(node, ast.ClassDef):
                self._collect_class(node, file_path, source)

    def _collect_function(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        file_path: Path,
        source: str,
        class_name: str | None = None,
    ) -> None:
        """Coleta uma função e suas dependências."""
        qualified_name = f"{class_name}.{node.name}" if class_name else node.name
        full_key = f"{file_path}:{qualified_name}"

        if full_key in self._visited:
            return
        self._visited.add(full_key)

        # Extrai o código da função
        lines = source.splitlines()
        code = "\n".join(lines[node.lineno - 1 : node.end_lineno or node.lineno])

        # Encontra chamadas de função
        calls = self._find_calls(node)
        imports = self._find_imports_used(node, file_path)

        chunk = CodeChunk(
            name=qualified_name,
            code=code,
            file_path=str(file_path),
            line_start=node.lineno,
            line_end=node.end_lineno or node.lineno,
            chunk_type="method" if class_name else "function",
            docstring=ast.get_docstring(node),
            calls=calls,
            imports=imports,
        )

        self._collected[full_key] = chunk

        # Segue as chamadas para funções locais
        self._follow_calls(calls, file_path)

    def _collect_class(
        self,
        node: ast.ClassDef,
        file_path: Path,
        source: str,
    ) -> None:
        """Coleta uma classe e seus métodos."""
        full_key = f"{file_path}:{node.name}"

        if full_key in self._visited:
            return
        self._visited.add(full_key)

        # Extrai o código da classe
        lines = source.splitlines()
        code = "\n".join(lines[node.lineno - 1 : node.end_lineno or node.lineno])

        # Encontra chamadas de função
        calls = self._find_calls(node)
        imports = self._find_imports_used(node, file_path)

        chunk = CodeChunk(
            name=node.name,
            code=code,
            file_path=str(file_path),
            line_start=node.lineno,
            line_end=node.end_lineno or node.lineno,
            chunk_type="class",
            docstring=ast.get_docstring(node),
            calls=calls,
            imports=imports,
        )

        self._collected[full_key] = chunk

        # Segue as chamadas para funções locais
        self._follow_calls(calls, file_path)

    def _find_calls(self, node: ast.AST) -> list[str]:
        """Encontra todas as chamadas de função em um nó."""
        calls = []
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                call_name = self._get_call_name(child)
                if call_name:
                    calls.append(call_name)
        return list(set(calls))

    def _get_call_name(self, node: ast.Call) -> str | None:
        """Extrai o nome de uma chamada de função."""
        if isinstance(node.func, ast.Name):
            return node.func.id
        elif isinstance(node.func, ast.Attribute):
            parts = []
            current = node.func
            while isinstance(current, ast.Attribute):
                parts.append(current.attr)
                current = current.value
            if isinstance(current, ast.Name):
                parts.append(current.id)
            return ".".join(reversed(parts))
        return None

    def _find_imports_used(self, node: ast.AST, file_path: Path) -> list[str]:
        """Encontra imports usados em um nó."""
        imports = []
        tree = self._ast_cache.get(str(file_path))
        if not tree:
            return imports

        # Coleta nomes usados no nó
        used_names = set()
        for child in ast.walk(node):
            if isinstance(child, ast.Name):
                used_names.add(child.id)

        # Verifica quais imports correspondem
        for tree_node in tree.body:
            if isinstance(tree_node, ast.Import):
                for alias in tree_node.names:
                    name = alias.asname or alias.name.split(".")[0]
                    if name in used_names:
                        imports.append(alias.name)
            elif isinstance(tree_node, ast.ImportFrom):
                for alias in tree_node.names:
                    name = alias.asname or alias.name
                    if name in used_names:
                        module = tree_node.module or ""
                        imports.append(f"{module}.{alias.name}" if module else alias.name)

        return imports

    def _follow_calls(self, calls: list[str], current_file: Path) -> None:
        """Segue chamadas de função para outros arquivos/funções."""
        for call in calls:
            # Verifica se é um import local
            parts = call.split(".")

            # Busca no arquivo atual primeiro
            source = self._file_cache.get(str(current_file))
            tree = self._ast_cache.get(str(current_file))

            if tree and source:
                for node in tree.body:
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        if node.name == parts[0]:
                            self._collect_function(node, current_file, source)
                    elif isinstance(node, ast.ClassDef):
                        if node.name == parts[0]:
                            self._collect_class(node, current_file, source)

            # Tenta seguir imports
            for import_name, import_path in self._import_map.items():
                if parts[0] in import_name or import_name.endswith(f".{parts[0]}"):
                    if isinstance(import_path, Path) and import_path.is_file():
                        try:
                            imp_source = self._read_file(import_path)
                            imp_tree = self._parse_file(import_path, imp_source)
                            self._collect_imports(imp_tree, import_path)

                            for node in imp_tree.body:
                                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                                    if node.name == parts[-1]:
                                        self._collect_function(node, import_path, imp_source)
                                elif isinstance(node, ast.ClassDef):
                                    if node.name == parts[-1]:
                                        self._collect_class(node, import_path, imp_source)
                        except Exception:
                            pass

    def _order_chunks(self) -> list[CodeChunk]:
        """Ordena chunks por dependência (chamadores primeiro)."""
        # Por simplicidade, ordena por tipo e nome
        chunks = list(self._collected.values())

        def sort_key(c: CodeChunk) -> tuple[int, str]:
            type_order = {"function": 0, "class": 1, "method": 2}
            return (type_order.get(c.chunk_type, 3), c.name)

        chunks.sort(key=sort_key)
        return chunks
