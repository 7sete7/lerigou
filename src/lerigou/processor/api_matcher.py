"""Matcher para conectar chamadas de API frontend aos endpoints do backend."""

from dataclasses import dataclass
from pathlib import Path

from lerigou.processor.models import APICall
from lerigou.processor.scanners.fastapi import EndpointInfo, FastAPIScanner


@dataclass
class MatchResult:
    """Resultado do matching de uma chamada de API."""

    api_call: APICall
    endpoint: EndpointInfo | None
    is_matched: bool
    backend_file: str | None = None
    backend_function: str | None = None
    backend_line: int | None = None

    @property
    def is_external(self) -> bool:
        """Retorna True se a chamada é para uma API externa."""
        return not self.is_matched


class EndpointMatcher:
    """
    Matcher que conecta chamadas de API do frontend aos endpoints do backend.

    Suporta:
    - FastAPI (Python)
    - Futuramente: Flask, Express, NestJS, etc.
    """

    def __init__(self, repo_path: Path):
        """
        Inicializa o matcher.

        Args:
            repo_path: Caminho raiz do repositório
        """
        self.repo_path = repo_path
        self._fastapi_scanner = FastAPIScanner()
        self._endpoints: dict[str, EndpointInfo] = {}
        self._scanned = False

    def scan(self) -> None:
        """Escaneia o repositório procurando endpoints."""
        if self._scanned:
            return

        # Escaneia FastAPI endpoints
        self._endpoints = self._fastapi_scanner.scan_repository(self.repo_path)
        self._scanned = True

    def match(self, api_call: APICall) -> MatchResult:
        """
        Tenta encontrar o endpoint correspondente a uma chamada de API.

        Args:
            api_call: Chamada de API a ser matchada

        Returns:
            MatchResult com informações do match
        """
        if not self._scanned:
            self.scan()

        # Normaliza o path
        path = self._normalize_path(api_call.path)

        # Busca o endpoint
        endpoint = self._match_with_alternatives(api_call.method, path)

        if endpoint:
            return MatchResult(
                api_call=api_call,
                endpoint=endpoint,
                is_matched=True,
                backend_file=endpoint.file_path,
                backend_function=endpoint.function_name,
                backend_line=endpoint.line_number,
            )

        return MatchResult(
            api_call=api_call,
            endpoint=None,
            is_matched=False,
        )

    def _match_with_alternatives(self, method: str, path: str) -> EndpointInfo | None:
        """Tenta encontrar endpoints considerando prefixos alternativos."""
        endpoint = self._fastapi_scanner.find_endpoint(method, path)
        if endpoint:
            return endpoint

        alt_path = self._add_public_interview_prefix(path)
        if alt_path != path:
            endpoint = self._fastapi_scanner.find_endpoint(method, alt_path)
        return endpoint

    def _add_public_interview_prefix(self, path: str) -> str:
        """Adiciona o prefixo /public/interview se fizer sentido."""
        if path.startswith("/api/v1/") and not path.startswith(
            "/api/v1/public/interview/"
        ):
            return path.replace("/api/v1/", "/api/v1/public/interview/", 1)
        return path

    def match_all(self, api_calls: list[APICall]) -> list[MatchResult]:
        """
        Faz o matching de múltiplas chamadas de API.

        Args:
            api_calls: Lista de chamadas de API

        Returns:
            Lista de MatchResults
        """
        return [self.match(call) for call in api_calls]

    def _normalize_path(self, path: str) -> str:
        """
        Normaliza um path de API.

        - Remove query strings
        - Converte placeholders template literals para path params
        """
        # Remove query string
        if "?" in path:
            path = path.split("?")[0]

        # Converte {variavel} (template literal) para manter consistência
        # O path já deve estar no formato correto, mas vamos garantir

        return path

    def get_all_endpoints(self) -> list[EndpointInfo]:
        """Retorna todos os endpoints encontrados."""
        if not self._scanned:
            self.scan()
        return list(self._endpoints.values())

    def get_endpoints_summary(self) -> dict[str, int]:
        """Retorna um resumo dos endpoints por método HTTP."""
        if not self._scanned:
            self.scan()

        summary: dict[str, int] = {}
        for endpoint in self._endpoints.values():
            method = endpoint.method
            summary[method] = summary.get(method, 0) + 1

        return summary
