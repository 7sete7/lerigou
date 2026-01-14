"""Analisador de código TypeScript/JavaScript usando Node.js e @babel/parser."""

import json
import subprocess
from pathlib import Path

from lerigou.processor.models import (
    APICall,
    CodeElement,
    ElementType,
    FunctionCall,
    Import,
    Parameter,
)
from lerigou.processor.parser import CodeParser


class TypeScriptAnalyzer(CodeParser):
    """
    Analisador de código TypeScript/JavaScript.

    Usa um script Node.js com @babel/parser para extrair:
    - Funções e arrow functions
    - Componentes React (function components)
    - Classes
    - Imports/exports
    - Chamadas de função
    - Chamadas de API (fetch, axios, etc.)
    """

    def __init__(self):
        # Encontra o diretório do script
        self._script_dir = self._find_script_dir()

    def _find_script_dir(self) -> Path:
        """Encontra o diretório onde o script parse-ts.js está."""
        # Tenta encontrar na raiz do projeto (onde package.json está)
        current = Path(__file__).resolve()

        # Sobe a árvore procurando por package.json
        for parent in [current] + list(current.parents):
            if (parent / "package.json").exists() and (
                parent / "scripts" / "parse-ts.js"
            ).exists():
                return parent

        # Fallback: diretório de trabalho atual
        cwd = Path.cwd()
        if (cwd / "scripts" / "parse-ts.js").exists():
            return cwd

        raise FileNotFoundError(
            "Não foi possível encontrar scripts/parse-ts.js. "
            "Execute 'npm install' no diretório raiz do projeto."
        )

    def supports_extension(self, extension: str) -> bool:
        return extension.lower() in (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")

    def parse_file(self, file_path: Path) -> CodeElement:
        """Parseia um arquivo TypeScript/JavaScript."""
        script_path = self._script_dir / "scripts" / "parse-ts.js"

        try:
            result = subprocess.run(
                ["node", str(script_path), str(file_path)],
                capture_output=True,
                text=True,
                cwd=str(self._script_dir),
                timeout=30,
            )

            if result.returncode != 0:
                error_msg = result.stderr or result.stdout
                raise RuntimeError(f"Erro ao parsear TypeScript: {error_msg}")

            data = json.loads(result.stdout)

            if "error" in data:
                raise RuntimeError(f"Erro no parser: {data['error']}")

            return self._convert_to_code_element(data, str(file_path))

        except subprocess.TimeoutExpired:
            raise RuntimeError(f"Timeout ao parsear {file_path}")
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Erro ao decodificar JSON do parser: {e}")
        except FileNotFoundError:
            raise RuntimeError(
                "Node.js não encontrado. Certifique-se de que Node.js está instalado."
            )

    def parse_source(self, source: str, file_name: str = "<string>") -> CodeElement:
        """Parseia código fonte TypeScript/JavaScript."""
        # Cria arquivo temporário para o source
        import tempfile

        suffix = ".tsx" if "jsx" in source.lower() or "<" in source else ".ts"

        with tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False) as f:
            f.write(source)
            temp_path = Path(f.name)

        try:
            result = self.parse_file(temp_path)
            result.source_file = file_name
            return result
        finally:
            temp_path.unlink()

    def _convert_to_code_element(self, data: dict, file_path: str) -> CodeElement:
        """Converte o JSON do parser para CodeElement."""
        element_type = self._map_element_type(data.get("element_type", "module"))

        element = CodeElement(
            name=data.get("name", "unknown"),
            element_type=element_type,
            source_file=file_path,
            line_number=data.get("line_number", 0),
            end_line_number=data.get("end_line_number", 0),
            docstring=data.get("docstring"),
            return_type=data.get("return_type"),
            is_async=data.get("is_async", False),
            is_generator=data.get("is_generator", False),
            decorators=data.get("decorators", []),
            base_classes=data.get("base_classes", []),
        )

        # Converte parâmetros
        for param in data.get("parameters", []):
            element.parameters.append(
                Parameter(
                    name=param.get("name", "param"),
                    type_hint=param.get("type_hint"),
                    default_value=param.get("default_value"),
                    is_args=param.get("is_args", False),
                    is_kwargs=param.get("is_kwargs", False),
                )
            )

        # Converte imports
        for imp in data.get("imports", []):
            specifiers = []
            for spec in imp.get("specifiers", []):
                local = spec.get("local")
                imported = spec.get("imported")
                if local and imported:
                    specifiers.append({"local": local, "imported": imported})
            element.imports.append(
                Import(
                    module=imp.get("module", ""),
                    names=imp.get("names", []),
                    alias=imp.get("alias"),
                    is_from=imp.get("is_from", True),
                    line_number=imp.get("line_number", 0),
                    specifiers=specifiers,
                )
            )

        # Converte chamadas de função
        for call in data.get("calls", []):
            element.calls.append(
                FunctionCall(
                    name=call.get("name", ""),
                    target=call.get("target"),
                    arguments=call.get("arguments", []),
                    line_number=call.get("line_number", 0),
                )
            )

        # Converte chamadas de API
        for api_call in data.get("api_calls", []):
            element.api_calls.append(
                APICall(
                    method=api_call.get("method", "GET"),
                    path=api_call.get("path", ""),
                    client=api_call.get("client", "fetch"),
                    line_number=api_call.get("line_number", 0),
                    is_external=api_call.get("is_external", False),
                    matched_endpoint=api_call.get("matched_endpoint"),
                )
            )

        # Converte filhos recursivamente
        for child_data in data.get("children", []):
            child = self._convert_to_code_element(child_data, file_path)
            element.add_child(child)

        return element

    def _map_element_type(self, type_str: str) -> ElementType:
        """Mapeia string de tipo para ElementType."""
        mapping = {
            "module": ElementType.MODULE,
            "class": ElementType.CLASS,
            "function": ElementType.FUNCTION,
            "method": ElementType.METHOD,
            "variable": ElementType.VARIABLE,
            "component": ElementType.COMPONENT,
        }
        return mapping.get(type_str, ElementType.FUNCTION)
