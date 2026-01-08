"""Testes para o módulo canvas."""

import json

from lerigou.canvas.builder import CanvasBuilder
from lerigou.canvas.layout import LayoutEngine
from lerigou.canvas.models import Canvas, Edge, Node
from lerigou.canvas.renderer import render_canvas


def test_node_creation():
    """Testa a criação de nodes."""
    node = Node.text_node(
        text="Test Node",
        x=100,
        y=200,
        width=250,
        height=60,
        color="4",
    )

    assert node.type == "text"
    assert node.text == "Test Node"
    assert node.x == 100
    assert node.y == 200

    data = node.to_dict()
    assert data["type"] == "text"
    assert data["text"] == "Test Node"
    assert data["color"] == "4"


def test_edge_creation():
    """Testa a criação de edges."""
    edge = Edge.create(
        from_node="node1",
        to_node="node2",
        from_side="right",
        to_side="left",
        label="calls",
    )

    assert edge.from_node == "node1"
    assert edge.to_node == "node2"

    data = edge.to_dict()
    assert data["fromNode"] == "node1"
    assert data["toNode"] == "node2"
    assert data["label"] == "calls"


def test_canvas_creation():
    """Testa a criação de canvas."""
    canvas = Canvas()

    node1 = Node.text_node("Node 1", node_id="n1")
    node2 = Node.text_node("Node 2", node_id="n2")
    edge = Edge.create("n1", "n2")

    canvas.add_node(node1)
    canvas.add_node(node2)
    canvas.add_edge(edge)

    assert len(canvas.nodes) == 2
    assert len(canvas.edges) == 1

    data = canvas.to_dict()
    assert len(data["nodes"]) == 2
    assert len(data["edges"]) == 1


def test_layout_engine_row():
    """Testa o layout em linha."""
    engine = LayoutEngine()

    items = [
        engine.node("A"),
        engine.node("B"),
        engine.node("C"),
    ]

    row = engine.row(items)
    result = engine.calculate_positions(row)

    assert len(result.nodes) == 3
    # Verifica que os nodes estão em linha
    assert result.nodes[0].y == result.nodes[1].y == result.nodes[2].y


def test_layout_engine_column():
    """Testa o layout em coluna."""
    engine = LayoutEngine()

    items = [
        engine.node("A"),
        engine.node("B"),
        engine.node("C"),
    ]

    col = engine.column(items)
    result = engine.calculate_positions(col)

    assert len(result.nodes) == 3
    # Verifica que os nodes estão em coluna
    assert result.nodes[0].x == result.nodes[1].x == result.nodes[2].x


def test_layout_engine_group():
    """Testa o layout com grupo."""
    engine = LayoutEngine()

    content = engine.column(
        [
            engine.node("Child 1"),
            engine.node("Child 2"),
        ]
    )

    group = engine.group("My Group", content, color="6")
    result = engine.calculate_positions(group)

    # O primeiro node é o grupo
    assert result.nodes[0].type == "group"
    assert result.nodes[0].label == "My Group"
    assert len(result.nodes) == 3  # 1 grupo + 2 filhos


def test_canvas_builder():
    """Testa o CanvasBuilder."""
    builder = CanvasBuilder()

    builder.add_group(
        "TestGroup",
        lambda g: g.add_node("func1", "Function 1")
        .add_node("func2", "Function 2")
        .connect("func1", "func2"),
        color="6",
    )

    canvas = builder.build()

    assert len(canvas.nodes) >= 2
    assert len(canvas.edges) >= 1


def test_render_canvas():
    """Testa a renderização do canvas."""
    canvas = Canvas()
    canvas.add_node(Node.text_node("Test", node_id="test"))

    json_str = render_canvas(canvas)
    data = json.loads(json_str)

    assert "nodes" in data
    assert "edges" in data
    assert len(data["nodes"]) == 1
