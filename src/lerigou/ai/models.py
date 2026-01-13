"""Modelos de dados para análise de código com IA."""

from pydantic import BaseModel, Field


class DataFormat(BaseModel):
    """Representa um formato de dados importante no código."""

    name: str = Field(description="Nome do formato de dados (ex: UserDTO, PaymentRequest)")
    description: str = Field(description="Breve descrição do que representa")
    fields: list[str] = Field(default_factory=list, description="Campos principais do formato")
    used_in: list[str] = Field(default_factory=list, description="Funções/métodos onde é usado")


class FlowStep(BaseModel):
    """Representa um passo no fluxo de execução."""

    id: str = Field(description="ID único do passo (ex: step_1, validate_input)")
    name: str = Field(description="Nome curto da ação (ex: 'Validar entrada')")
    description: str = Field(description="O que este passo faz")
    function: str | None = Field(default=None, description="Nome da função que executa este passo")
    step_type: str = Field(
        default="process",
        description="Tipo: 'start', 'process', 'decision', 'data', 'end', 'error'",
    )
    inputs: list[str] = Field(default_factory=list, description="Dados de entrada")
    outputs: list[str] = Field(default_factory=list, description="Dados de saída")


class FlowBranch(BaseModel):
    """Representa uma ramificação condicional no fluxo."""

    condition: str = Field(description="Condição da ramificação (ex: 'usuário válido?')")
    true_branch: str = Field(description="ID do passo se condição for verdadeira")
    false_branch: str = Field(description="ID do passo se condição for falsa")
    label_true: str = Field(default="Sim", description="Label do caminho verdadeiro")
    label_false: str = Field(default="Não", description="Label do caminho falso")


class FlowConnection(BaseModel):
    """Representa uma conexão entre passos do fluxo."""

    from_step: str = Field(description="ID do passo de origem")
    to_step: str = Field(description="ID do passo de destino")
    label: str | None = Field(default=None, description="Label opcional da conexão")
    is_error: bool = Field(default=False, description="Se é um fluxo de erro")


class CodeFlow(BaseModel):
    """Representa o fluxo completo de execução do código."""

    name: str = Field(description="Nome do fluxo")
    description: str = Field(description="Descrição do que o fluxo faz")
    steps: list[FlowStep] = Field(default_factory=list, description="Passos do fluxo")
    connections: list[FlowConnection] = Field(
        default_factory=list, description="Conexões entre passos"
    )
    branches: list[FlowBranch] = Field(
        default_factory=list, description="Ramificações condicionais"
    )


class AnalysisResult(BaseModel):
    """Resultado da análise de código pela IA."""

    summary: str = Field(description="Resumo geral do código analisado")
    main_flow: CodeFlow = Field(description="Fluxo principal de execução")
    sub_flows: list[CodeFlow] = Field(default_factory=list, description="Sub-fluxos auxiliares")
    data_formats: list[DataFormat] = Field(
        default_factory=list, description="Formatos de dados importantes"
    )
    entry_points: list[str] = Field(
        default_factory=list, description="Pontos de entrada identificados"
    )
