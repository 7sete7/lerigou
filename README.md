# lerigou

CLI multitarefa para análise e visualização de código.

## Instalação

```bash
uv sync
```

## Uso

### create-canvas

Gera um JSON Canvas visual a partir de código Python usando análise AST:

```bash
# Analisar um arquivo
lerigou create-canvas ./src/main.py

# Analisar a partir de um entrypoint específico
lerigou create-canvas ./src/main.py --entrypoint main

# Especificar arquivo de saída
lerigou create-canvas ./src/main.py -o diagrama.canvas
```

### create-canvas-v2 (com IA)

Gera um JSON Canvas visual de **fluxo de execução** usando IA (OpenAI). 
O canvas mostra o código como um fluxograma linear, seguindo chamadas de função e branches:

```
Função A → chama B → valida → (sim) → processa → retorna
                          → (não) → erro
```

```bash
# Requer OPENAI_API_KEY configurada
export OPENAI_API_KEY="sua-chave-aqui"

# Analisar um arquivo com IA
lerigou create-canvas-v2 ./src/main.py -e main

# Usar modelo diferente
lerigou create-canvas-v2 ./src/main.py --model gpt-4o-mini

# Ver análise da IA no terminal
lerigou create-canvas-v2 ./src/main.py --show-analysis

# Apenas coletar código (sem chamar IA)
lerigou create-canvas-v2 ./src/main.py --dry-run
```

**Recursos do create-canvas-v2:**
- **Fluxo linear**: Visualiza a execução do código como um fluxograma
- **Setas direcionais**: Conecta todos os passos com edges/flechas
- **Tipos de passos**: Start, Process, Decision, Data, End, Error
- **Ramificações**: Mostra branches (if/else, try/except) com caminhos alternativos
- **Cores semânticas**: Verde (entrada/saída), Cyan (processamento), Amarelo (decisão), Vermelho (erro)
- **Formatos de dados**: Extrai e exibe estruturas de dados importantes

## Desenvolvimento

```bash
# Instalar dependências de desenvolvimento
uv sync --all-extras

# Rodar testes
uv run pytest

# Linting
uv run ruff check .

# Formatar código
uv run ruff format .
```
