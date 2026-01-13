"""Analisador de código usando OpenAI."""

import json
import os

from openai import OpenAI

from lerigou.ai.models import AnalysisResult
from lerigou.ai.prompts import SYSTEM_PROMPT, build_analysis_prompt
from lerigou.processor.collector import CollectedCode


class AICodeAnalyzer:
    """
    Analisa código usando OpenAI para identificar domínios, assuntos e estruturas.

    Requer a variável de ambiente OPENAI_API_KEY configurada.
    """

    def __init__(
        self,
        model: str = "gpt-4o",
        api_key: str | None = None,
        temperature: float = 0.3,
    ):
        self.model = model
        self.temperature = temperature
        self._client: OpenAI | None = None
        self._api_key = api_key

    @property
    def client(self) -> OpenAI:
        """Retorna o cliente OpenAI, inicializando se necessário."""
        if self._client is None:
            api_key = self._api_key or os.environ.get("OPENAI_API_KEY")
            if not api_key:
                raise ValueError(
                    "OPENAI_API_KEY não configurada. "
                    "Configure via variável de ambiente ou parâmetro api_key."
                )
            self._client = OpenAI(api_key=api_key)
        return self._client

    def analyze(self, collected_code: CollectedCode) -> AnalysisResult:
        """
        Analisa o código coletado e retorna a estrutura identificada.

        Args:
            collected_code: Código coletado pelo CodeCollector

        Returns:
            AnalysisResult com domínios, assuntos e formatos de dados
        """
        # Gera o contexto de código para o prompt
        code_context = collected_code.to_prompt_context()

        # Constrói o prompt
        user_prompt = build_analysis_prompt(code_context, collected_code.entrypoint)

        # Chama a API
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=self.temperature,
            response_format={"type": "json_object"},
        )

        # Extrai o conteúdo
        content = response.choices[0].message.content
        if not content:
            raise ValueError("Resposta vazia da API OpenAI")

        # Parseia o JSON
        try:
            data = json.loads(content)
        except json.JSONDecodeError as e:
            raise ValueError(f"Resposta inválida da API: {e}") from e

        # Valida e retorna
        return AnalysisResult.model_validate(data)

    def analyze_with_retry(
        self,
        collected_code: CollectedCode,
        max_retries: int = 2,
    ) -> AnalysisResult:
        """
        Analisa o código com retry em caso de falha.

        Args:
            collected_code: Código coletado
            max_retries: Número máximo de tentativas

        Returns:
            AnalysisResult com a análise
        """
        last_error: Exception | None = None

        for attempt in range(max_retries + 1):
            try:
                return self.analyze(collected_code)
            except Exception as e:
                last_error = e
                if attempt < max_retries:
                    continue
                raise

        raise last_error or ValueError("Falha na análise")

    def estimate_tokens(self, collected_code: CollectedCode) -> int:
        """
        Estima o número de tokens do código coletado.

        Usa uma estimativa simples de ~4 caracteres por token.
        """
        code_context = collected_code.to_prompt_context()
        return len(code_context) // 4
