"""Prompts para análise de código com IA."""

SYSTEM_PROMPT = """Você é um arquiteto de software especialista em análise de fluxo de código.
Sua tarefa é analisar código-fonte e extrair o FLUXO DE EXECUÇÃO LINEAR, identificando:
1. Cada passo de execução em sequência
2. Chamadas de função e o que cada uma faz
3. Ramificações condicionais (if/else, match, try/except)
4. Fluxo de dados (entrada → processamento → saída)

Você deve retornar sua análise em formato JSON estruturado que represente um FLUXOGRAMA do código."""


def build_analysis_prompt(code_context: str, entrypoint: str) -> str:
    """Constrói o prompt de análise para a IA."""
    return f"""# Tarefa: Análise de Fluxo de Código

Analise o código Python abaixo e extraia o FLUXO DE EXECUÇÃO LINEAR, como um fluxograma.

## Código a Analisar

Entrypoint: `{entrypoint}`

{code_context}

---

## Instruções de Análise

### 1. Identificar o Fluxo Principal
Siga a execução do código a partir do entrypoint, passo a passo:
- Cada chamada de função é um passo
- Cada operação significativa é um passo
- Cada decisão (if/else) cria uma ramificação

### 2. Tipos de Passos

Cada passo deve ter um `step_type`:
- `"start"`: Início do fluxo (entrada de dados, request recebido)
- `"process"`: Processamento/transformação de dados
- `"decision"`: Ponto de decisão (if/else, validação)
- `"data"`: Operação com dados (leitura/escrita BD, API call)
- `"end"`: Fim do fluxo (retorno, resposta)
- `"error"`: Tratamento de erro

### 3. Conexões e Flechas

IMPORTANTE: Crie conexões (`connections`) entre TODOS os passos para formar o fluxo:
- Cada passo deve ter pelo menos uma conexão de entrada OU saída
- Use `label` para descrever a transição quando relevante
- Para erros, use `is_error: true`

### 4. Ramificações (Branches)

Para cada if/else ou decisão, crie uma entrada em `branches`:
- `condition`: A pergunta/condição (ex: "Usuário existe?")
- `true_branch`: ID do passo se verdadeiro
- `false_branch`: ID do passo se falso
- `label_true`/`label_false`: Labels das setas (ex: "Sim"/"Não")

---

## Exemplo de Fluxo

Para um código como:
```python
def process_order(order_id):
    order = get_order(order_id)
    if not order:
        raise OrderNotFound()
    
    if validate_order(order):
        result = calculate_total(order)
        save_order(order)
        return result
    else:
        return {{"error": "invalid"}}
```

O fluxo seria:
```json
{{
  "main_flow": {{
    "name": "Processar Pedido",
    "description": "Fluxo de processamento de um pedido",
    "steps": [
      {{"id": "start", "name": "Receber order_id", "step_type": "start", "inputs": ["order_id"]}},
      {{"id": "get_order", "name": "Buscar pedido", "step_type": "data", "function": "get_order"}},
      {{"id": "check_exists", "name": "Pedido existe?", "step_type": "decision"}},
      {{"id": "error_not_found", "name": "Erro: Não encontrado", "step_type": "error"}},
      {{"id": "validate", "name": "Validar pedido", "step_type": "process", "function": "validate_order"}},
      {{"id": "check_valid", "name": "Pedido válido?", "step_type": "decision"}},
      {{"id": "calculate", "name": "Calcular total", "step_type": "process", "function": "calculate_total"}},
      {{"id": "save", "name": "Salvar pedido", "step_type": "data", "function": "save_order"}},
      {{"id": "return_success", "name": "Retornar resultado", "step_type": "end", "outputs": ["result"]}},
      {{"id": "return_error", "name": "Retornar erro", "step_type": "end", "outputs": ["error"]}}
    ],
    "connections": [
      {{"from_step": "start", "to_step": "get_order"}},
      {{"from_step": "get_order", "to_step": "check_exists"}},
      {{"from_step": "check_exists", "to_step": "error_not_found", "label": "Não", "is_error": true}},
      {{"from_step": "check_exists", "to_step": "validate", "label": "Sim"}},
      {{"from_step": "validate", "to_step": "check_valid"}},
      {{"from_step": "check_valid", "to_step": "calculate", "label": "Sim"}},
      {{"from_step": "check_valid", "to_step": "return_error", "label": "Não"}},
      {{"from_step": "calculate", "to_step": "save"}},
      {{"from_step": "save", "to_step": "return_success"}}
    ],
    "branches": [
      {{"condition": "Pedido existe?", "true_branch": "validate", "false_branch": "error_not_found", "label_true": "Sim", "label_false": "Não"}},
      {{"condition": "Pedido válido?", "true_branch": "calculate", "false_branch": "return_error", "label_true": "Sim", "label_false": "Não"}}
    ]
  }}
}}
```

---

## Formato de Resposta

Retorne APENAS o JSON válido, sem texto adicional:

```json
{{
  "summary": "Resumo do fluxo em 1-2 frases",
  "main_flow": {{
    "name": "Nome do fluxo principal",
    "description": "O que este fluxo faz",
    "steps": [
      {{
        "id": "step_id_unico",
        "name": "Nome curto da ação",
        "description": "O que faz",
        "function": "nome_da_funcao",
        "step_type": "process|start|end|decision|data|error",
        "inputs": ["dados de entrada"],
        "outputs": ["dados de saída"]
      }}
    ],
    "connections": [
      {{
        "from_step": "step_origem",
        "to_step": "step_destino",
        "label": "descrição opcional",
        "is_error": false
      }}
    ],
    "branches": [
      {{
        "condition": "Condição?",
        "true_branch": "step_se_sim",
        "false_branch": "step_se_nao",
        "label_true": "Sim",
        "label_false": "Não"
      }}
    ]
  }},
  "sub_flows": [],
  "data_formats": [
    {{
      "name": "NomeDoFormato",
      "description": "O que representa",
      "fields": ["campo1", "campo2"],
      "used_in": ["step1", "step2"]
    }}
  ],
  "entry_points": ["main"]
}}
```

Analise o código fornecido e retorne o JSON estruturado representando o FLUXO DE EXECUÇÃO."""


def build_refinement_prompt(initial_result: str, feedback: str) -> str:
    """Constrói um prompt para refinamento da análise."""
    return f"""Refine a análise anterior com base no feedback:

## Análise Anterior
{initial_result}

## Feedback
{feedback}

Retorne o JSON atualizado com as correções/melhorias solicitadas."""
