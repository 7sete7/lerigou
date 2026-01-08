# lerigou

CLI multitarefa para análise e visualização de código.

## Instalação

```bash
uv sync
```

## Uso

### create-canvas

Gera um JSON Canvas visual a partir de código Python:

```bash
# Analisar um arquivo
lerigou create-canvas ./src/main.py

# Analisar a partir de um entrypoint específico
lerigou create-canvas ./src/main.py --entrypoint main

# Especificar arquivo de saída
lerigou create-canvas ./src/main.py -o diagrama.canvas
```

## Desenvolvimento

```bash
# Instalar dependências de desenvolvimento
uv sync --all-extras

# Rodar testes
uv run pytest

# Linting
uv run ruff check .
```
