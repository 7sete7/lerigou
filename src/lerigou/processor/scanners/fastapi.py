"""Scanner para encontrar endpoints FastAPI em um repositório."""

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class EndpointInfo:
    """Informações sobre um endpoint FastAPI."""

    path: str  # /users/{user_id}
    method: str  # GET, POST, etc.
    function_name: str  # Nome da função handler
    file_path: str  # Caminho do arquivo
    line_number: int  # Linha onde está definido
    router_prefix: str = ""  # Prefixo do router (ex: /api/v1)
    decorators: list[str] = field(default_factory=list)
    docstring: str | None = None

    @property
    def full_path(self) -> str:
        """Retorna o path completo incluindo prefixo do router."""
        prefix = self.router_prefix.rstrip("/")
        path = self.path if self.path.startswith("/") else f"/{self.path}"
        return f"{prefix}{path}"

    def matches_path(self, request_path: str) -> bool:
        """Verifica se o endpoint corresponde a um path de requisição."""
        # Normaliza os paths
        endpoint_path = self.full_path.strip("/")
        request_path = request_path.strip("/")
        
        endpoint_norm = self._normalize_placeholder_path(endpoint_path)
        request_norm = self._normalize_placeholder_path(request_path)
        if endpoint_norm == request_norm:
            return True

        # Converte path parameters para regex
        # /users/{user_id} -> /users/[^/]+
        pattern = re.sub(r"\{[^}]+\}", r"[^/]+", endpoint_path)
        pattern = f"^{pattern}$"

        # Tenta match direto
        if re.match(pattern, request_path):
            return True

        # Tenta removendo prefixos comuns de API do request
        for prefix in ["api/", "api/v1/", "api/v2/"]:
            if request_path.startswith(prefix):
                clean_path = request_path[len(prefix) :]
                clean_endpoint = endpoint_path
                # Remove o mesmo prefixo do endpoint se existir
                if clean_endpoint.startswith(prefix):
                    clean_endpoint = clean_endpoint[len(prefix) :]
                clean_pattern = re.sub(r"\{[^}]+\}", r"[^/]+", clean_endpoint)
                clean_pattern = f"^{clean_pattern}$"
                if re.match(clean_pattern, clean_path):
                    return True

        return False

    def _normalize_placeholder_path(self, path: str) -> str:
        """Substitui placeholders {param} por um valor genérico para comparar."""
        return re.sub(r"\{[^}]+\}", "{param}", path)


class FastAPIScanner:
    """
    Scanner para encontrar endpoints FastAPI em um repositório.

    Detecta:
    - @app.get("/path"), @app.post("/path"), etc.
    - @router.get("/path"), @router.post("/path"), etc.
    - APIRouter(prefix="/api")
    - Include router statements
    """

    HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options", "trace"}

    def __init__(self):
        self._endpoints: dict[str, EndpointInfo] = {}
        self._router_prefixes: dict[str, str] = {}  # router_name -> prefix
        self._file_routers: dict[str, list[str]] = {}  # file -> router names

    def scan_repository(self, repo_path: Path) -> dict[str, EndpointInfo]:
        """
        Escaneia um repositório procurando endpoints FastAPI.

        Args:
            repo_path: Caminho raiz do repositório

        Returns:
            Dicionário de path -> EndpointInfo
        """
        self._endpoints = {}
        self._router_prefixes = {}

        # Encontra todos os arquivos Python
        python_files = list(repo_path.rglob("*.py"))

        # Primeira passada: encontra definições de routers e seus prefixos
        for file_path in python_files:
            self._scan_router_definitions(file_path)

        # Segunda passada: encontra endpoints
        for file_path in python_files:
            self._scan_endpoints(file_path)

        return self._endpoints

    def _scan_router_definitions(self, file_path: Path) -> None:
        """Escaneia um arquivo procurando definições de APIRouter."""
        try:
            source = file_path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(file_path))
        except (SyntaxError, UnicodeDecodeError):
            return

        for node in ast.walk(tree):
            # Procura por: router = APIRouter(prefix="/api")
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and isinstance(node.value, ast.Call):
                        if self._is_api_router_call(node.value):
                            prefix = self._extract_prefix_from_router(node.value)
                            self._router_prefixes[target.id] = prefix

            # Procura por: app.include_router(router, prefix="/api")
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
                call = node.value
                if self._is_include_router_call(call):
                    router_name, prefix = self._extract_include_router_info(call)
                    if router_name:
                        existing = self._router_prefixes.get(router_name, "")
                        self._router_prefixes[router_name] = prefix + existing

    def _scan_endpoints(self, file_path: Path) -> None:
        """Escaneia um arquivo procurando decorators de endpoint."""
        try:
            source = file_path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(file_path))
        except (SyntaxError, UnicodeDecodeError):
            return

        # Encontra os nomes de routers usados neste arquivo
        local_routers = self._find_local_routers(tree)

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for decorator in node.decorator_list:
                    endpoint = self._parse_endpoint_decorator(
                        decorator, node, str(file_path), local_routers
                    )
                    if endpoint:
                        key = f"{endpoint.method}:{endpoint.full_path}"
                        self._endpoints[key] = endpoint

    def _find_local_routers(self, tree: ast.Module) -> dict[str, str]:
        """Encontra routers definidos localmente no arquivo."""
        local_routers: dict[str, str] = {}

        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and isinstance(node.value, ast.Call):
                        if self._is_api_router_call(node.value):
                            prefix = self._extract_prefix_from_router(node.value)
                            local_routers[target.id] = prefix

        return local_routers

    def _is_api_router_call(self, call: ast.Call) -> bool:
        """Verifica se é uma chamada APIRouter()."""
        if isinstance(call.func, ast.Name):
            return call.func.id == "APIRouter"
        if isinstance(call.func, ast.Attribute):
            return call.func.attr == "APIRouter"
        return False

    def _is_include_router_call(self, call: ast.Call) -> bool:
        """Verifica se é uma chamada include_router()."""
        if isinstance(call.func, ast.Attribute):
            return call.func.attr == "include_router"
        return False

    def _extract_prefix_from_router(self, call: ast.Call) -> str:
        """Extrai o prefixo de uma chamada APIRouter()."""
        # Procura por prefix="..." nos kwargs
        for keyword in call.keywords:
            if keyword.arg == "prefix" and isinstance(keyword.value, ast.Constant):
                return str(keyword.value.value)
        return ""

    def _extract_include_router_info(self, call: ast.Call) -> tuple[str | None, str]:
        """Extrai informações de include_router()."""
        router_name = None
        prefix = ""

        # Primeiro argumento é o router
        if call.args and isinstance(call.args[0], ast.Name):
            router_name = call.args[0].id

        # Procura por prefix nos kwargs
        for keyword in call.keywords:
            if keyword.arg == "prefix" and isinstance(keyword.value, ast.Constant):
                prefix = str(keyword.value.value)

        return router_name, prefix

    def _parse_endpoint_decorator(
        self,
        decorator: ast.expr,
        func: ast.FunctionDef | ast.AsyncFunctionDef,
        file_path: str,
        local_routers: dict[str, str],
    ) -> EndpointInfo | None:
        """Parseia um decorator de endpoint."""
        if not isinstance(decorator, ast.Call):
            return None

        # @app.get("/path") ou @router.get("/path")
        if isinstance(decorator.func, ast.Attribute):
            method = decorator.func.attr.lower()
            if method not in self.HTTP_METHODS:
                return None

            # Identifica o objeto (app ou router)
            obj_name = None
            if isinstance(decorator.func.value, ast.Name):
                obj_name = decorator.func.value.id

            # Extrai o path do primeiro argumento
            path = "/"
            if decorator.args and isinstance(decorator.args[0], ast.Constant):
                path = str(decorator.args[0].value)

            # Determina o prefixo do router
            router_prefix = ""
            if obj_name:
                # Primeiro tenta routers locais, depois globais
                router_prefix = local_routers.get(obj_name, "")
                if not router_prefix:
                    router_prefix = self._router_prefixes.get(obj_name, "")

            return EndpointInfo(
                path=path,
                method=method.upper(),
                function_name=func.name,
                file_path=file_path,
                line_number=func.lineno,
                router_prefix=router_prefix,
                docstring=ast.get_docstring(func),
            )

        return None

    def find_endpoint(self, method: str, path: str) -> EndpointInfo | None:
        """
        Encontra um endpoint que corresponde ao método e path.

        Args:
            method: Método HTTP (GET, POST, etc.)
            path: Path da requisição (/api/users/123)

        Returns:
            EndpointInfo se encontrado, None caso contrário
        """
        method = method.upper()

        # Tenta match exato primeiro
        key = f"{method}:{path}"
        if key in self._endpoints:
            return self._endpoints[key]

        # Tenta match com path parameters
        for endpoint in self._endpoints.values():
            if endpoint.method == method and endpoint.matches_path(path):
                return endpoint

        return None

    def get_all_endpoints(self) -> list[EndpointInfo]:
        """Retorna todos os endpoints encontrados."""
        return list(self._endpoints.values())
