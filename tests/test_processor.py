"""Testes para o módulo processor."""

from lerigou.processor.adapter import CodeToCanvasAdapter
from lerigou.processor.analyzers.python import PythonAnalyzer
from lerigou.processor.models import CodeElement, ElementType, Parameter


def test_code_element_creation():
    """Testa a criação de CodeElement."""
    element = CodeElement(
        name="my_function",
        element_type=ElementType.FUNCTION,
        source_file="test.py",
        line_number=10,
        parameters=[
            Parameter(name="x", type_hint="int"),
            Parameter(name="y", type_hint="str", default_value="'default'"),
        ],
        return_type="bool",
    )

    assert element.name == "my_function"
    assert element.element_type == ElementType.FUNCTION
    assert len(element.parameters) == 2


def test_python_analyzer_simple():
    """Testa o analisador Python com código simples."""
    source = '''
def hello(name: str) -> str:
    """Say hello."""
    return f"Hello, {name}!"

def main():
    print(hello("World"))
'''

    analyzer = PythonAnalyzer()
    module = analyzer.parse_source(source, "test.py")

    assert module.element_type == ElementType.MODULE
    assert len(module.children) == 2

    hello_func = module.children[0]
    assert hello_func.name == "hello"
    assert hello_func.docstring == "Say hello."
    assert len(hello_func.parameters) == 1
    assert hello_func.return_type == "str"


def test_python_analyzer_class():
    """Testa o analisador Python com classes."""
    source = '''
class Calculator:
    """A simple calculator."""
    
    def __init__(self, value: int = 0):
        self.value = value
    
    def add(self, n: int) -> int:
        """Add n to value."""
        self.value += n
        return self.value
    
    def reset(self) -> None:
        self.value = 0
'''

    analyzer = PythonAnalyzer()
    module = analyzer.parse_source(source, "calc.py")

    assert len(module.children) == 1

    calc_class = module.children[0]
    assert calc_class.element_type == ElementType.CLASS
    assert calc_class.name == "Calculator"
    assert len(calc_class.children) == 3  # __init__, add, reset


def test_python_analyzer_calls():
    """Testa a detecção de chamadas de função."""
    source = """
def helper():
    pass

def main():
    helper()
    print("test")
"""

    analyzer = PythonAnalyzer()
    module = analyzer.parse_source(source, "test.py")

    main_func = module.children[1]
    assert main_func.name == "main"

    call_names = [c.name for c in main_func.calls]
    assert "helper" in call_names
    assert "print" in call_names


def test_code_to_canvas_adapter():
    """Testa o adapter de código para canvas."""
    source = '''
class Service:
    def process(self, data: str) -> dict:
        """Process the data."""
        result = self.validate(data)
        return {"status": "ok", "result": result}
    
    def validate(self, data: str) -> bool:
        return len(data) > 0
'''

    analyzer = PythonAnalyzer()
    module = analyzer.parse_source(source, "service.py")

    adapter = CodeToCanvasAdapter()
    canvas = adapter.convert(module)

    assert len(canvas.nodes) >= 3  # module group + class group + methods

    # Verifica que há um grupo para a classe
    groups = [n for n in canvas.nodes if n.type == "group"]
    assert any("Service" in (g.label or "") for g in groups)


def test_code_element_qualified_name():
    """Testa o nome qualificado de elementos."""
    module = CodeElement(
        name="mymodule",
        element_type=ElementType.MODULE,
    )

    cls = CodeElement(
        name="MyClass",
        element_type=ElementType.CLASS,
    )
    module.add_child(cls)

    method = CodeElement(
        name="my_method",
        element_type=ElementType.METHOD,
    )
    cls.add_child(method)

    assert method.get_qualified_name() == "MyClass.my_method"
