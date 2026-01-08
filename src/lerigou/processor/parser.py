"""Interface abstrata para parsers de código."""

from abc import ABC, abstractmethod
from pathlib import Path

from lerigou.processor.models import CodeElement


class CodeParser(ABC):
    """Interface abstrata para parsers de código."""

    @abstractmethod
    def parse_file(self, file_path: Path) -> CodeElement:
        """
        Parseia um arquivo e retorna o elemento raiz.

        Args:
            file_path: Caminho do arquivo

        Returns:
            CodeElement representando o módulo
        """
        pass

    @abstractmethod
    def parse_source(self, source: str, file_name: str = "<string>") -> CodeElement:
        """
        Parseia código fonte e retorna o elemento raiz.

        Args:
            source: Código fonte
            file_name: Nome do arquivo (para referência)

        Returns:
            CodeElement representando o módulo
        """
        pass

    @abstractmethod
    def supports_extension(self, extension: str) -> bool:
        """Verifica se o parser suporta a extensão de arquivo."""
        pass


def get_parser_for_file(file_path: Path) -> CodeParser | None:
    """
    Retorna o parser apropriado para um arquivo.

    Args:
        file_path: Caminho do arquivo

    Returns:
        Parser apropriado ou None se não suportado
    """
    from lerigou.processor.analyzers.python import PythonAnalyzer

    suffix = file_path.suffix.lower()

    # Python
    if suffix in (".py", ".pyw", ".pyi"):
        return PythonAnalyzer()

    # Extensível para outras linguagens no futuro
    return None
