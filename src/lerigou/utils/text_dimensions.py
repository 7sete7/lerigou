"""Utilitários para cálculo de dimensões de texto em nodes."""

import re

# Configurações de renderização (valores aproximados para Obsidian Canvas)
CHAR_WIDTH = 8  # Largura média de caractere em pixels
LINE_HEIGHT = 24  # Altura de uma linha normal
HEADER_LINE_HEIGHT = 32  # Altura de uma linha com ### header
CODE_LINE_HEIGHT = 22  # Altura de linha em code block
PADDING_HORIZONTAL = 24  # Padding horizontal do node
PADDING_VERTICAL = 20  # Padding vertical do node
MIN_WIDTH = 150
MIN_HEIGHT = 50
MAX_WIDTH = 500


def calculate_text_dimensions(
    text: str,
    min_width: int = MIN_WIDTH,
    max_width: int = MAX_WIDTH,
    min_height: int = MIN_HEIGHT,
) -> tuple[int, int]:
    """
    Calcula as dimensões necessárias para um texto em um node.

    Args:
        text: Texto com markdown
        min_width: Largura mínima
        max_width: Largura máxima
        min_height: Altura mínima

    Returns:
        Tupla (width, height) em pixels
    """
    if not text:
        return (min_width, min_height)

    lines = text.split("\n")
    total_height = PADDING_VERTICAL * 2
    max_line_width = 0

    for line in lines:
        line_width, line_height = _calculate_line_dimensions(line)
        max_line_width = max(max_line_width, line_width)
        total_height += line_height

    # Calcula largura final
    width = max_line_width + PADDING_HORIZONTAL * 2
    width = max(min_width, min(max_width, width))

    # Se o texto é muito largo, precisa de mais altura para wrap
    if max_line_width > max_width - PADDING_HORIZONTAL * 2:
        # Estima linhas extras por wrap
        wrap_factor = max_line_width / (max_width - PADDING_HORIZONTAL * 2)
        total_height = int(total_height * wrap_factor * 0.8)  # 0.8 para não exagerar

    height = max(min_height, total_height)

    return (width, height)


def _calculate_line_dimensions(line: str) -> tuple[int, int]:
    """
    Calcula dimensões de uma linha individual.

    Returns:
        Tupla (width, height) em pixels
    """
    # Remove formatação markdown para calcular largura visual
    clean_line = _strip_markdown(line)

    # Calcula largura base
    width = len(clean_line) * CHAR_WIDTH

    # Determina altura baseada no tipo de linha
    if line.startswith("###"):
        height = HEADER_LINE_HEIGHT + 4
        width = int(width * 1.1)  # Headers são um pouco maiores
    elif line.startswith("##"):
        height = HEADER_LINE_HEIGHT + 8
        width = int(width * 1.2)
    elif line.startswith("#"):
        height = HEADER_LINE_HEIGHT + 12
        width = int(width * 1.3)
    elif line.startswith("```") or line.startswith("`"):
        height = CODE_LINE_HEIGHT
        width = int(width * 0.9)  # Fonte monospace é mais estreita
    elif line.startswith("- ") or line.startswith("• "):
        height = LINE_HEIGHT
        width += 16  # Espaço para bullet
    elif line.strip() == "":
        height = LINE_HEIGHT // 2  # Linhas vazias são menores
    else:
        height = LINE_HEIGHT

    return (width, height)


def _strip_markdown(text: str) -> str:
    """Remove formatação markdown para obter texto visual."""
    # Remove headers
    text = re.sub(r"^#{1,6}\s*", "", text)

    # Remove bold/italic
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"__(.+?)__", r"\1", text)
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    text = re.sub(r"_(.+?)_", r"\1", text)

    # Remove code inline
    text = re.sub(r"`(.+?)`", r"\1", text)

    # Remove links
    text = re.sub(r"\[(.+?)\]\(.+?\)", r"\1", text)

    return text


def calculate_node_dimensions(
    text: str,
    node_type: str = "text",
    base_width: int = 250,
    base_height: int = 80,
) -> tuple[int, int]:
    """
    Calcula dimensões otimizadas para um node específico.

    Args:
        text: Conteúdo do node
        node_type: Tipo do node (afeta dimensões base)
        base_width: Largura base desejada
        base_height: Altura base mínima

    Returns:
        Tupla (width, height) em pixels
    """
    # Calcula dimensões do texto
    text_width, text_height = calculate_text_dimensions(
        text,
        min_width=base_width,
        max_width=max(base_width * 2, MAX_WIDTH),
        min_height=base_height,
    )

    # Ajustes por tipo de node
    if node_type == "group":
        # Grupos precisam de mais espaço para o label
        text_height += 30
    elif node_type == "decision":
        # Decisões podem ser um pouco mais largas
        text_width = max(text_width, 220)
    elif node_type in ("start", "end"):
        # Start/end podem ser mais compactos
        text_width = max(min(text_width, 250), 180)

    return (text_width, text_height)


def estimate_wrapped_height(text: str, available_width: int) -> int:
    """
    Estima a altura necessária considerando wrap de texto.

    Args:
        text: Texto a ser exibido
        available_width: Largura disponível para o texto

    Returns:
        Altura estimada em pixels
    """
    if not text:
        return MIN_HEIGHT

    lines = text.split("\n")
    total_height = PADDING_VERTICAL * 2

    content_width = available_width - PADDING_HORIZONTAL * 2

    for line in lines:
        clean_line = _strip_markdown(line)
        line_width = len(clean_line) * CHAR_WIDTH

        # Determina altura base da linha
        if line.startswith("#"):
            line_height = HEADER_LINE_HEIGHT
        else:
            line_height = LINE_HEIGHT

        # Calcula linhas extras por wrap
        if line_width > content_width and content_width > 0:
            wrapped_lines = (line_width // content_width) + 1
            total_height += line_height * wrapped_lines
        else:
            total_height += line_height

    return max(MIN_HEIGHT, total_height)
