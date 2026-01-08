"""Analisador de código Python usando AST."""

import ast
from pathlib import Path

from lerigou.processor.models import (
    CodeElement,
    ElementType,
    FunctionCall,
    Import,
    Parameter,
)
from lerigou.processor.parser import CodeParser


class PythonAnalyzer(CodeParser):
    """
    Analisador de código Python usando o módulo ast.

    Extrai:
    - Funções e métodos (com parâmetros e return types)
    - Classes e seus métodos
    - Imports
    - Chamadas de função (call graph)
    - Docstrings
    """

    def supports_extension(self, extension: str) -> bool:
        return extension.lower() in (".py", ".pyw", ".pyi")

    def parse_file(self, file_path: Path) -> CodeElement:
        """Parseia um arquivo Python."""
        source = file_path.read_text(encoding="utf-8")
        return self.parse_source(source, str(file_path))

    def parse_source(self, source: str, file_name: str = "<string>") -> CodeElement:
        """Parseia código fonte Python."""
        tree = ast.parse(source, filename=file_name)
        return self._analyze_module(tree, file_name)

    def _analyze_module(self, tree: ast.Module, file_name: str) -> CodeElement:
        """Analisa um módulo Python."""
        module_name = Path(file_name).stem

        module = CodeElement(
            name=module_name,
            element_type=ElementType.MODULE,
            source_file=file_name,
            line_number=1,
            docstring=ast.get_docstring(tree),
        )

        for node in tree.body:
            if isinstance(node, ast.Import):
                module.imports.extend(self._analyze_import(node))
            elif isinstance(node, ast.ImportFrom):
                module.imports.append(self._analyze_import_from(node))
            elif isinstance(node, ast.FunctionDef):
                module.add_child(self._analyze_function(node, file_name))
            elif isinstance(node, ast.AsyncFunctionDef):
                module.add_child(self._analyze_function(node, file_name, is_async=True))
            elif isinstance(node, ast.ClassDef):
                module.add_child(self._analyze_class(node, file_name))
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        var = CodeElement(
                            name=target.id,
                            element_type=ElementType.VARIABLE,
                            source_file=file_name,
                            line_number=node.lineno,
                        )
                        module.add_child(var)

        return module

    def _analyze_function(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        file_name: str,
        is_async: bool = False,
        is_method: bool = False,
    ) -> CodeElement:
        """Analisa uma função ou método."""
        element_type = ElementType.METHOD if is_method else ElementType.FUNCTION

        func = CodeElement(
            name=node.name,
            element_type=element_type,
            source_file=file_name,
            line_number=node.lineno,
            end_line_number=node.end_lineno or node.lineno,
            docstring=ast.get_docstring(node),
            is_async=is_async or isinstance(node, ast.AsyncFunctionDef),
            decorators=[self._get_decorator_name(d) for d in node.decorator_list],
            parameters=self._analyze_parameters(node.args),
            return_type=self._get_annotation(node.returns),
        )

        # Analisa o corpo para encontrar chamadas
        func.calls = self._find_calls(node)

        # Detecta se é um generator
        for child in ast.walk(node):
            if isinstance(child, (ast.Yield, ast.YieldFrom)):
                func.is_generator = True
                break

        # Analisa inputs (parâmetros) e outputs (return)
        func.inputs = [p.name for p in func.parameters if p.name != "self"]
        if func.return_type:
            func.outputs = [func.return_type]

        return func

    def _analyze_class(self, node: ast.ClassDef, file_name: str) -> CodeElement:
        """Analisa uma classe."""
        cls = CodeElement(
            name=node.name,
            element_type=ElementType.CLASS,
            source_file=file_name,
            line_number=node.lineno,
            end_line_number=node.end_lineno or node.lineno,
            docstring=ast.get_docstring(node),
            decorators=[self._get_decorator_name(d) for d in node.decorator_list],
            base_classes=[self._get_base_class_name(b) for b in node.bases],
        )

        for child_node in node.body:
            if isinstance(child_node, ast.FunctionDef):
                cls.add_child(
                    self._analyze_function(child_node, file_name, is_method=True)
                )
            elif isinstance(child_node, ast.AsyncFunctionDef):
                cls.add_child(
                    self._analyze_function(
                        child_node, file_name, is_async=True, is_method=True
                    )
                )
            elif isinstance(child_node, ast.ClassDef):
                # Classe aninhada
                cls.add_child(self._analyze_class(child_node, file_name))
            elif isinstance(child_node, ast.Assign):
                # Atributo de classe
                for target in child_node.targets:
                    if isinstance(target, ast.Name):
                        var = CodeElement(
                            name=target.id,
                            element_type=ElementType.VARIABLE,
                            source_file=file_name,
                            line_number=child_node.lineno,
                        )
                        cls.add_child(var)

        return cls

    def _analyze_parameters(self, args: ast.arguments) -> list[Parameter]:
        """Analisa parâmetros de função."""
        params = []

        # Parâmetros posicionais
        defaults_offset = len(args.args) - len(args.defaults)
        for i, arg in enumerate(args.args):
            default = None
            if i >= defaults_offset:
                default_node = args.defaults[i - defaults_offset]
                default = self._get_literal_value(default_node)

            params.append(
                Parameter(
                    name=arg.arg,
                    type_hint=self._get_annotation(arg.annotation),
                    default_value=default,
                )
            )

        # *args
        if args.vararg:
            params.append(
                Parameter(
                    name=args.vararg.arg,
                    type_hint=self._get_annotation(args.vararg.annotation),
                    is_args=True,
                )
            )

        # Keyword-only args
        kw_defaults_dict = {
            i: args.kw_defaults[i]
            for i in range(len(args.kw_defaults))
            if args.kw_defaults[i] is not None
        }
        for i, arg in enumerate(args.kwonlyargs):
            default = None
            if i in kw_defaults_dict:
                default = self._get_literal_value(kw_defaults_dict[i])
            params.append(
                Parameter(
                    name=arg.arg,
                    type_hint=self._get_annotation(arg.annotation),
                    default_value=default,
                )
            )

        # **kwargs
        if args.kwarg:
            params.append(
                Parameter(
                    name=args.kwarg.arg,
                    type_hint=self._get_annotation(args.kwarg.annotation),
                    is_kwargs=True,
                )
            )

        return params

    def _analyze_import(self, node: ast.Import) -> list[Import]:
        """Analisa um import simples."""
        imports = []
        for alias in node.names:
            imports.append(
                Import(
                    module=alias.name,
                    alias=alias.asname,
                    is_from=False,
                    line_number=node.lineno,
                )
            )
        return imports

    def _analyze_import_from(self, node: ast.ImportFrom) -> Import:
        """Analisa um from import."""
        module = node.module or ""
        names = [alias.name for alias in node.names]
        return Import(
            module=module,
            names=names,
            is_from=True,
            line_number=node.lineno,
        )

    def _find_calls(self, node: ast.AST) -> list[FunctionCall]:
        """Encontra todas as chamadas de função em um nó."""
        calls = []

        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                call = self._analyze_call(child)
                if call:
                    calls.append(call)

        return calls

    def _analyze_call(self, node: ast.Call) -> FunctionCall | None:
        """Analisa uma chamada de função."""
        func = node.func

        if isinstance(func, ast.Name):
            # Chamada simples: func()
            return FunctionCall(
                name=func.id,
                line_number=node.lineno,
            )
        elif isinstance(func, ast.Attribute):
            # Chamada de método: obj.method()
            target = self._get_attribute_chain(func.value)
            return FunctionCall(
                name=func.attr,
                target=target,
                line_number=node.lineno,
            )

        return None

    def _get_attribute_chain(self, node: ast.AST) -> str:
        """Obtém a cadeia de atributos (ex: a.b.c)."""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            parent = self._get_attribute_chain(node.value)
            return f"{parent}.{node.attr}"
        elif isinstance(node, ast.Call):
            # Chamada encadeada: func().method()
            inner = self._analyze_call(node)
            if inner:
                if inner.target:
                    return f"{inner.target}.{inner.name}()"
                return f"{inner.name}()"
        return "<expr>"

    def _get_decorator_name(self, node: ast.AST) -> str:
        """Obtém o nome de um decorator."""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return self._get_attribute_chain(node)
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                return func.id
            elif isinstance(func, ast.Attribute):
                return self._get_attribute_chain(func)
        return "<decorator>"

    def _get_base_class_name(self, node: ast.AST) -> str:
        """Obtém o nome de uma classe base."""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return self._get_attribute_chain(node)
        elif isinstance(node, ast.Subscript):
            # Generic: List[T]
            base = self._get_base_class_name(node.value)
            return f"{base}[...]"
        return "<base>"

    def _get_annotation(self, node: ast.AST | None) -> str | None:
        """Obtém a anotação de tipo como string."""
        if node is None:
            return None

        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Constant):
            return repr(node.value)
        elif isinstance(node, ast.Attribute):
            return self._get_attribute_chain(node)
        elif isinstance(node, ast.Subscript):
            base = self._get_annotation(node.value)
            slice_val = self._get_annotation(node.slice)
            return f"{base}[{slice_val}]"
        elif isinstance(node, ast.Tuple):
            elts = [self._get_annotation(e) for e in node.elts]
            return ", ".join(e or "?" for e in elts)
        elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
            # Union type: X | Y
            left = self._get_annotation(node.left)
            right = self._get_annotation(node.right)
            return f"{left} | {right}"

        return None

    def _get_literal_value(self, node: ast.AST | None) -> str | None:
        """Obtém o valor literal de um nó."""
        if node is None:
            return None

        if isinstance(node, ast.Constant):
            return repr(node.value)
        elif isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.List):
            return "[...]"
        elif isinstance(node, ast.Dict):
            return "{...}"
        elif isinstance(node, ast.Tuple):
            return "(...)"

        return "..."
