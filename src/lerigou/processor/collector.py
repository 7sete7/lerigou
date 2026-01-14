"""Coletor de código que segue chamadas de função e imports."""

import ast
from dataclasses import dataclass, field
from pathlib import Path

from lerigou.processor.models import APICall, CodeElement, Import


@dataclass
class CodeChunk:
    """Representa um pedaço de código coletado."""

    name: str
    code: str
    file_path: str
    line_start: int
    line_end: int
    chunk_type: str  # "function", "class", "method", "module", "component"
    language: str = "python"  # "python", "typescript", "javascript"
    docstring: str | None = None
    calls: list[str] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)
    api_calls: list[APICall] = field(default_factory=list)


SERVICE_KEYWORDS = ("service", "api", "client", "backend", "fetch", "http")


@dataclass
class CollectedCode:
    """Resultado da coleta de código."""

    entrypoint: str
    chunks: list[CodeChunk]
    all_imports: list[str]
    concatenated_code: str
    api_calls: list[APICall] = field(default_factory=list)
    frontend_component: str | None = None  # Nome do componente frontend de origem

    def to_prompt_context(self) -> str:
        """Gera o contexto de código para o prompt da IA."""
        sections = []

        # Separa chunks de backend
        backend_chunks = [c for c in self.chunks if c.language == "python"]

        # #region agent log
        import json as _json; open("/Users/leonardog/dev/lerigou/.cursor/debug.log", "a").write(_json.dumps({"hypothesisId": "D", "location": "collector.py:to_prompt_context:start", "message": "Building prompt context", "data": {"total_chunks": len(self.chunks), "backend_chunks": len(backend_chunks), "frontend_component": self.frontend_component, "api_calls_count": len(self.api_calls)}, "timestamp": __import__("time").time()}) + "\n")
        # #endregion

        # Se veio do frontend, mostra resumo das chamadas de API
        if self.frontend_component and self.api_calls:
            sections.append("## Frontend → Backend\n")
            sections.append(
                f"O componente `{self.frontend_component}` "
                "faz as seguintes chamadas de API:\n"
            )
            for api in self.api_calls:
                if api.matched_endpoint:
                    sections.append(f"- **{api.method} {api.path}** → `{api.matched_endpoint}`")
                else:
                    sections.append(f"- **{api.method} {api.path}** → (API externa)")
            sections.append("")

        # Backend: código completo para análise de fluxo
        if backend_chunks:
            sections.append("## Código Backend (analisar fluxo)\n")
            for chunk in backend_chunks:
                header = f"### {chunk.chunk_type.upper()}: {chunk.name}"
                if chunk.file_path:
                    header += f" (from {Path(chunk.file_path).name})"
                sections.append(header)
                sections.append(f"```python\n{chunk.code}\n```")
                if chunk.calls:
                    sections.append(f"Calls: {', '.join(chunk.calls)}")
                sections.append("")
        elif not self.frontend_component:
            # Fallback: mostra todos os chunks (código Python puro)
            sections.append(f"## Entrypoint: {self.entrypoint}\n")
            for chunk in self.chunks:
                header = f"### {chunk.chunk_type.upper()}: {chunk.name}"
                if chunk.file_path:
                    header += f" (from {Path(chunk.file_path).name})"
                sections.append(header)
                sections.append(f"```{chunk.language}\n{chunk.code}\n```")
                if chunk.calls:
                    sections.append(f"Calls: {', '.join(chunk.calls)}")
                sections.append("")

        result = "\n".join(sections)

        # #region agent log
        import json as _json; open("/Users/leonardog/dev/lerigou/.cursor/debug.log", "a").write(_json.dumps({"hypothesisId": "D", "location": "collector.py:to_prompt_context:end", "message": "Prompt context built", "data": {"result_length": len(result), "result_preview": result[:200] if result else "EMPTY"}, "timestamp": __import__("time").time()}) + "\n")
        # #endregion

        return result


class CodeCollector:
    """
    Coleta código seguindo chamadas de função a partir de um entrypoint.

    Traversa o código seguindo:
    - Chamadas de função diretas
    - Imports locais (do mesmo projeto)
    - Métodos de classes instanciadas
    - Chamadas de API (conectando frontend ao backend)
    """

    def __init__(self, base_path: Path | None = None, follow_api_calls: bool = True):
        self.base_path = base_path or Path.cwd()
        self.follow_api_calls = follow_api_calls
        self._collected: dict[str, CodeChunk] = {}
        self._visited: set[str] = set()
        self._file_cache: dict[str, str] = {}
        self._ast_cache: dict[str, ast.Module] = {}
        self._import_map: dict[str, Path] = {}
        self._api_calls: list[APICall] = []
        self._endpoint_matcher = None

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
        self._api_calls.clear()

        # Detecta a linguagem do arquivo
        language = self._detect_language(file_path)

        if language in ("typescript", "javascript"):
            self._collect_typescript(file_path, entrypoint)
        else:
            # Python (comportamento original)
            source = self._read_file(file_path)
            tree = self._parse_file(file_path, source)
            self._collect_imports(tree, file_path)

            if entrypoint:
                self._collect_entrypoint(tree, file_path, source, entrypoint)
            else:
                self._collect_module(tree, file_path, source)

        # Ordena chunks por ordem de dependência
        chunks = self._order_chunks()

        # Detecta se veio do frontend
        frontend_component = None
        if language in ("typescript", "javascript"):
            frontend_component = entrypoint or file_path.stem

        # Gera código concatenado (apenas backend para análise)
        backend_chunks = [c for c in chunks if c.language == "python"]
        concatenated = "\n\n".join(
            f"# {c.chunk_type}: {c.name}\n{c.code}" for c in backend_chunks
        )

        # Coleta todos os imports únicos
        all_imports = list(set(imp for c in chunks for imp in c.imports))

        return CollectedCode(
            entrypoint=entrypoint or file_path.stem,
            chunks=chunks,
            all_imports=all_imports,
            concatenated_code=concatenated,
            api_calls=self._api_calls,
            frontend_component=frontend_component,
        )

    def _detect_language(self, file_path: Path) -> str:
        """Detecta a linguagem de um arquivo baseado na extensão."""
        suffix = file_path.suffix.lower()
        if suffix in (".ts", ".tsx"):
            return "typescript"
        if suffix in (".js", ".jsx", ".mjs", ".cjs"):
            return "javascript"
        return "python"

    def _collect_typescript(self, file_path: Path, entrypoint: str | None = None) -> None:
        """
        Coleta chamadas de API de um arquivo TypeScript/JavaScript.

        NÃO coleta o código frontend completo - apenas identifica quais endpoints são chamados
        e segue para coletar o código backend correspondente.
        """
        from lerigou.processor.parser import get_parser_for_file
        # #region agent log
        import json as _json; open("/Users/leonardog/dev/lerigou/.cursor/debug.log", "a").write(_json.dumps({"hypothesisId": "A", "location": "collector.py:_collect_typescript:start", "message": "Starting TS collection", "data": {"file": str(file_path), "entrypoint": entrypoint}, "timestamp": __import__("time").time()}) + "\n")
        # #endregion

        parser = get_parser_for_file(file_path)
        if not parser:
            # #region agent log
            import json as _json; open("/Users/leonardog/dev/lerigou/.cursor/debug.log", "a").write(_json.dumps({"hypothesisId": "A", "location": "collector.py:_collect_typescript:no_parser", "message": "No parser found", "data": {}, "timestamp": __import__("time").time()}) + "\n")
            # #endregion
            return

        try:
            element = parser.parse_file(file_path)
        except Exception as e:
            # #region agent log
            import json as _json; open("/Users/leonardog/dev/lerigou/.cursor/debug.log", "a").write(_json.dumps({"hypothesisId": "A", "location": "collector.py:_collect_typescript:parse_error", "message": "Parse error", "data": {"error": str(e)}, "timestamp": __import__("time").time()}) + "\n")
            # #endregion
            return

        # Coleta API calls do componente/função especificado ou de todo o módulo
        found = None
        if entrypoint:
            found = element.find_element(entrypoint)
            if found:
                all_api_calls = found.get_all_api_calls()
            else:
                all_api_calls = element.get_all_api_calls()
        else:
            all_api_calls = element.get_all_api_calls()

        component_element = found or element

        # #region agent log
        import json as _json; open("/Users/leonardog/dev/lerigou/.cursor/debug.log", "a").write(_json.dumps({"hypothesisId": "A", "location": "collector.py:_collect_typescript:direct_api_calls", "message": "Direct API calls found", "data": {"count": len(all_api_calls), "calls": [{"method": c.method, "path": c.path} for c in all_api_calls]}, "timestamp": __import__("time").time()}) + "\n")
        # #endregion

        service_imports = self._filter_service_imports(element.imports)
        service_usage = self._find_used_service_functions(component_element, service_imports)
        # #region agent log
        import json as _json; open("/Users/leonardog/dev/lerigou/.cursor/debug.log", "a").write(_json.dumps({"hypothesisId": "A", "location": "collector.py:_collect_typescript:service_usage", "message": "Service import usage", "data": {"imports": len(service_imports), "used_modules": {module: sorted(list(funcs)) for module, funcs in service_usage.items()}}, "timestamp": __import__("time").time()}) + "\n")
        # #endregion

        if service_usage:
            service_api_calls = self._collect_service_api_calls(
                file_path, service_imports, service_usage
            )
            if service_api_calls:
                all_api_calls.extend(service_api_calls)

        # Processa as chamadas de API e segue para o backend
        if self.follow_api_calls and all_api_calls:
            self._process_api_calls(all_api_calls)

        # NÃO coleta o código frontend - apenas cria um chunk de resumo
        # O código frontend não é necessário para análise de fluxo

    def _filter_service_imports(self, imports: list[Import]) -> list[Import]:
        """Retorna apenas imports que parecem arquivos de serviço."""
        return [
            imp
            for imp in imports
            if imp.module
            and any(kw in imp.module.lower() for kw in SERVICE_KEYWORDS)
        ]

    def _get_import_alias_map(self, imp: Import) -> dict[str, str]:
        """Constroi um mapa local -> importado para um import statement."""
        alias_map: dict[str, str] = {}
        for spec in imp.specifiers:
            local = spec.get("local")
            imported = spec.get("imported")
            if local and imported:
                alias_map[local] = imported

        # Fallback para imports simples (sem specifiers)
        if not alias_map:
            for name in imp.names:
                alias_map[name] = name

        return alias_map

    def _resolve_service_function_name(
        self, call, alias_map: dict[str, str], local_name: str
    ) -> str:
        """Retorna o nome real da função do serviço considerando alias."""
        imported = alias_map.get(local_name)
        if not imported or imported in ("*", "default"):
            return call.name
        return imported

    def _find_used_service_functions(
        self, element: CodeElement, service_imports: list[Import]
    ) -> dict[str, set[str]]:
        """Identifica quais funções de cada módulo de serviço estão sendo chamadas."""
        usage: dict[str, set[str]] = {}
        if not service_imports:
            return usage

        calls = element.get_all_calls()
        for imp in service_imports:
            alias_map = self._get_import_alias_map(imp)
            if not alias_map:
                continue

            used_names: set[str] = set()
            for call in calls:
                if call.target and call.target in alias_map:
                    resolved = self._resolve_service_function_name(
                        call, alias_map, call.target
                    )
                    used_names.add(resolved)
                elif not call.target and call.name in alias_map:
                    resolved = self._resolve_service_function_name(
                        call, alias_map, call.name
                    )
                    used_names.add(resolved)

            if used_names:
                usage[imp.module] = used_names

        return usage

    def _collect_service_api_calls(
        self,
        file_path: Path,
        service_imports: list[Import],
        usage_map: dict[str, set[str]],
    ) -> list[APICall]:
        """Coleta as chamadas de API dos módulos de serviço usados."""
        from lerigou.processor.parser import get_parser_for_file

        collected: list[APICall] = []
        processed_modules: set[str] = set()
        for imp in service_imports:
            module = imp.module
            if not module or module not in usage_map:
                continue

            functions = usage_map[module]
            if not functions:
                continue

            service_path = self._resolve_ts_import(module, file_path)
            if not service_path or not service_path.exists():
                # #region agent log
                import json as _json; open("/Users/leonardog/dev/lerigou/.cursor/debug.log", "a").write(_json.dumps({"hypothesisId": "A", "location": "collector.py:_collect_service_api_calls:not_found", "message": "Service file not found", "data": {"module": module, "resolved": str(service_path) if service_path else None}, "timestamp": __import__("time").time()}) + "\n")
                # #endregion
                continue

            if module in processed_modules:
                continue

            processed_modules.add(module)
            # #region agent log
            import json as _json; open("/Users/leonardog/dev/lerigou/.cursor/debug.log", "a").write(_json.dumps({"hypothesisId": "A", "location": "collector.py:_collect_service_api_calls:parsing", "message": "Parsing service file", "data": {"path": str(service_path), "functions": list(functions)}, "timestamp": __import__("time").time()}) + "\n")
            # #endregion

            service_parser = get_parser_for_file(service_path)
            if not service_parser:
                continue

            try:
                service_element = service_parser.parse_file(service_path)
                for func_name in functions:
                    target = service_element.find_element(func_name)
                    if not target:
                        # #region agent log
                        import json as _json; open("/Users/leonardog/dev/lerigou/.cursor/debug.log", "a").write(_json.dumps({"hypothesisId": "A", "location": "collector.py:_collect_service_api_calls:not_found_function", "message": "Function not found in service", "data": {"path": str(service_path), "function": func_name}, "timestamp": __import__("time").time()}) + "\n")
                        # #endregion
                        continue

                    for api_call in target.get_all_api_calls():
                        if api_call not in collected:
                            collected.append(api_call)

                # #region agent log
                import json as _json; open("/Users/leonardog/dev/lerigou/.cursor/debug.log", "a").write(_json.dumps({"hypothesisId": "A", "location": "collector.py:_collect_service_api_calls:found", "message": "Found API calls in service", "data": {"path": str(service_path), "count": len(collected), "calls": [{"method": c.method, "path": c.path} for c in collected]} , "timestamp": __import__("time").time()}) + "\n")
                # #endregion
            except Exception as e:
                # #region agent log
                import json as _json; open("/Users/leonardog/dev/lerigou/.cursor/debug.log", "a").write(_json.dumps({"hypothesisId": "A", "location": "collector.py:_collect_service_api_calls:error", "message": "Error parsing service", "data": {"path": str(service_path), "error": str(e)}, "timestamp": __import__("time").time()}) + "\n")
                # #endregion
                continue

        return collected

    def _resolve_ts_import(self, module: str, from_file: Path) -> Path | None:
        """
        Resolve um import TypeScript para um caminho de arquivo.
        
        Suporta:
        - Caminhos relativos: ./service, ../utils/api
        - Alias @/: @/services/backendService -> src/services/backendService
        """
        if not module:
            return None

        # Tenta encontrar o diretório base do projeto frontend
        frontend_src = None
        current = from_file.parent
        while current != current.parent:
            if (current / "src").is_dir():
                frontend_src = current / "src"
                break
            if (current / "tsconfig.json").exists() or (current / "package.json").exists():
                if (current / "src").is_dir():
                    frontend_src = current / "src"
                break
            current = current.parent

        # Resolve alias @/ para src/
        if module.startswith("@/"):
            if frontend_src:
                relative_path = module[2:]  # Remove @/
                base_path = frontend_src / relative_path
            else:
                return None
        elif module.startswith("./") or module.startswith("../"):
            # Caminho relativo
            base_path = from_file.parent / module
        else:
            # Módulo npm, ignorar
            return None

        # Tenta diferentes extensões
        extensions = [".ts", ".tsx", ".js", ".jsx", "/index.ts", "/index.tsx", "/index.js"]
        for ext in extensions:
            candidate = Path(str(base_path) + ext)
            if candidate.exists():
                return candidate

        # Tenta o caminho exato (caso já tenha extensão)
        if base_path.exists() and base_path.is_file():
            return base_path

        return None

    def _add_element_chunk(self, element, file_path: Path, source: str, language: str) -> None:
        """Adiciona um CodeElement como um CodeChunk."""
        from lerigou.processor.models import CodeElement

        if not isinstance(element, CodeElement):
            return

        full_key = f"{file_path}:{element.name}"
        if full_key in self._visited:
            return
        self._visited.add(full_key)

        # Extrai o código
        lines = source.splitlines()
        start = max(0, element.line_number - 1)
        end = element.end_line_number or element.line_number
        code = "\n".join(lines[start:end])

        # Converte chamadas para lista de strings
        calls = [f"{c.target}.{c.name}" if c.target else c.name for c in element.calls]

        # Converte imports
        imports = [imp.module for imp in element.imports]

        chunk = CodeChunk(
            name=element.name,
            code=code,
            file_path=str(file_path),
            line_start=element.line_number,
            line_end=element.end_line_number or element.line_number,
            chunk_type=element.element_type.value,
            language=language,
            docstring=element.docstring,
            calls=calls,
            imports=imports,
            api_calls=list(element.api_calls),
        )

        self._collected[full_key] = chunk

        # Adiciona API calls à lista global
        for api_call in element.api_calls:
            if api_call not in self._api_calls:
                self._api_calls.append(api_call)

    def _process_api_calls(self, api_calls: list[APICall]) -> None:
        """Processa chamadas de API e segue para o backend se encontrado."""
        # #region agent log
        import json as _json; open("/Users/leonardog/dev/lerigou/.cursor/debug.log", "a").write(_json.dumps({"hypothesisId": "B", "location": "collector.py:_process_api_calls:start", "message": "Processing API calls", "data": {"count": len(api_calls), "base_path": str(self.base_path)}, "timestamp": __import__("time").time()}) + "\n")
        # #endregion

        if not self._endpoint_matcher:
            from lerigou.processor.api_matcher import EndpointMatcher

            self._endpoint_matcher = EndpointMatcher(self.base_path)

        for api_call in api_calls:
            result = self._endpoint_matcher.match(api_call)

            # #region agent log
            import json as _json; open("/Users/leonardog/dev/lerigou/.cursor/debug.log", "a").write(_json.dumps({"hypothesisId": "B", "location": "collector.py:_process_api_calls:match", "message": "Match result", "data": {"method": api_call.method, "path": api_call.path, "is_matched": result.is_matched, "backend_file": result.backend_file, "backend_function": result.backend_function}, "timestamp": __import__("time").time()}) + "\n")
            # #endregion

            if result.is_matched and result.backend_file:
                # Atualiza a API call com informações do match
                api_call.is_external = False
                api_call.matched_endpoint = f"{result.backend_function}@{result.backend_file}"

                # Coleta o código do backend
                backend_path = Path(result.backend_file)
                if backend_path.exists():
                    self._collect_backend_endpoint(
                        backend_path, result.backend_function, result.backend_line
                    )
            else:
                api_call.is_external = True

            # Adiciona à lista de API calls
            if api_call not in self._api_calls:
                self._api_calls.append(api_call)

    def _collect_backend_endpoint(
        self, file_path: Path, function_name: str, line_number: int
    ) -> None:
        """Coleta o código de um endpoint do backend."""
        # #region agent log
        import json as _json; open("/Users/leonardog/dev/lerigou/.cursor/debug.log", "a").write(_json.dumps({"hypothesisId": "C", "location": "collector.py:_collect_backend_endpoint:start", "message": "Collecting backend endpoint", "data": {"file": str(file_path), "function": function_name, "line": line_number}, "timestamp": __import__("time").time()}) + "\n")
        # #endregion

        full_key = f"{file_path}:{function_name}"
        if full_key in self._visited:
            # #region agent log
            import json as _json; open("/Users/leonardog/dev/lerigou/.cursor/debug.log", "a").write(_json.dumps({"hypothesisId": "C", "location": "collector.py:_collect_backend_endpoint:already_visited", "message": "Already visited", "data": {"key": full_key}, "timestamp": __import__("time").time()}) + "\n")
            # #endregion
            return

        source = self._read_file(file_path)
        tree = self._parse_file(file_path, source)

        # Encontra a função do endpoint
        found = False
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name == function_name:
                    found = True
                    self._collect_function(node, file_path, source)

        # #region agent log
        import json as _json; open("/Users/leonardog/dev/lerigou/.cursor/debug.log", "a").write(_json.dumps({"hypothesisId": "C", "location": "collector.py:_collect_backend_endpoint:end", "message": "Backend collection done", "data": {"found": found, "collected_count": len(self._collected)}, "timestamp": __import__("time").time()}) + "\n")
        # #endregion

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
