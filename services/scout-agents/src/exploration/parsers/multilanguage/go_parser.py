"""
Go AST Parser usando tree-sitter.

Suporta parsing de código Go com fallback regex.
"""
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class GoParser:
    """
    Parser para código Go usando tree-sitter.

    Extrai:
    - Packages
    - Imports
    - Structs
    - Interfaces
    - Functions
    - Methods (funções com receiver)
    - Goroutines
    - Channels
    - Defer statements
    """

    def __init__(self):
        self._ts_language = None
        self._ts_parser = None
        self._init_tree_sitter()

    def _init_tree_sitter(self):
        """Inicializa tree-sitter para Go."""
        try:
            import tree_sitter
            from tree_sitter_languages import get_language

            self._ts_language = get_language("go")
            self._ts_parser = tree_sitter.Parser()
            self._ts_parser.set_language(self._ts_language)
            logger.debug("go_parser_tree_sitter_loaded")
        except Exception as e:
            logger.warning(f"go_parser_init_failed: {str(e)}")
            self._ts_language = None
            self._ts_parser = None

    def parse(self, code: str, filename: str) -> Optional[Dict[str, Any]]:
        """
        Parse código Go e extrair informações.

        Args:
            code: Código fonte Go
            filename: Nome do arquivo (para extensão)

        Returns:
            Dicionário com structs, funções, métodos, etc.
        """
        if not code or not code.strip():
            return self._empty_result()

        # Tentar tree-sitter primeiro
        if self._ts_parser:
            try:
                return self._parse_with_tree_sitter(code, filename)
            except Exception as e:
                logger.warning(f"tree_sitter_parse_failed: {filename} - {str(e)}")

        # Fallback para regex
        return self._parse_with_regex(code, filename)

    def _empty_result(self) -> Dict[str, Any]:
        """Retorna estrutura vazia de resultado."""
        return {
            "packages": "",
            "imports": [],
            "structs": [],
            "interfaces": [],
            "functions": [],
            "methods": [],
            "goroutines": [],
            "channels": [],
            "defers": [],
            "complexity": 0,
        }

    def _parse_with_tree_sitter(self, code: str, filename: str) -> Dict[str, Any]:
        """Parse usando tree-sitter."""
        tree = self._ts_parser.parse(bytes(code, "utf8"))
        result = self._empty_result()

        # Extrair package
        self._extract_package(tree.root_node, code, result)

        # Extrair imports
        self._extract_imports(tree.root_node, code, result)

        # Extrair structs, interfaces, funções
        for node in tree.root_node.children:
            if node.type == "type_declaration":
                type_spec = node.children[0] if node.children else None
                if type_spec and type_spec.type == "type_spec":
                    self._extract_type_spec(type_spec, code, result)
            elif node.type == "function_declaration":
                func = self._extract_function_declaration(node, code)
                if func:
                    if func.get("receiver"):
                        result["methods"].append(func)
                    else:
                        result["functions"].append(func)

        # Detectar goroutines, channels, defer
        self._detect_concurrency_patterns(tree.root_node, code, result)

        # Calcular complexidade
        result["complexity"] = self._calculate_complexity_ts(tree)

        return result

    def _extract_package(self, root_node, code: str, result: Dict):
        """Extrai package."""
        for node in root_node.children:
            if node.type == "package_clause":
                for child in node.children:
                    if child.type == "package_identifier":
                        result["packages"] = code[child.start_byte : child.end_byte]

    def _extract_imports(self, root_node, code: str, result: Dict):
        """Extrai imports."""
        for node in root_node.children:
            if node.type == "import_declaration":
                import_path = node.child_by_field_name("path")
                if import_path:
                    # Remover aspas do import path
                    path = code[import_path.start_byte : import_path.end_byte].strip('"')
                    result["imports"].append(
                        {"name": path, "lineno": code[: import_path.start_byte].count("\n") + 1}
                    )
            elif node.type == "import_spec":
                import_path = node.child_by_field_name("path")
                if import_path:
                    path = code[import_path.start_byte : import_path.end_byte].strip('"')
                    result["imports"].append(
                        {"name": path, "lineno": code[: import_path.start_byte].count("\n") + 1}
                    )

    def _extract_type_spec(self, node, code: str, result: Dict):
        """Extrai type_spec (struct ou interface)."""
        name_node = node.child_by_field_name("name")
        if not name_node:
            return

        name = code[name_node.start_byte : name_node.end_byte]
        type_node = node.child_by_field_name("type")

        if not type_node:
            return

        if type_node.type == "struct_type":
            struct_info = {
                "name": name,
                "lineno": code[: name_node.start_byte].count("\n") + 1,
                "fields": [],
                "embedded": [],
            }
            # Extrair campos
            for field in type_node.children:
                if field.type == "field_declaration":
                    field_name = field.child_by_field_name("name")
                    field_type = field.child_by_field_name("type")
                    if field_name and field_type:
                        struct_info["fields"].append(
                            {
                                "name": code[field_name.start_byte : field_name.end_byte],
                                "type": code[field_type.start_byte : field_type.end_byte],
                            }
                        )
                    elif field_type:  # Embedded field
                        struct_info["embedded"].append(
                            code[field_type.start_byte : field_type.end_byte]
                        )
            result["structs"].append(struct_info)

        elif type_node.type == "interface_type":
            interface_info = {
                "name": name,
                "lineno": code[: name_node.start_byte].count("\n") + 1,
                "methods": [],
            }
            # Extrair métodos da interface
            for method in type_node.children:
                if method.type == "method_spec":
                    method_name = method.child_by_field_name("name")
                    if method_name:
                        interface_info["methods"].append(
                            code[method_name.start_byte : method_name.end_byte]
                        )
            result["interfaces"].append(interface_info)

    def _extract_function_declaration(self, node, code: str) -> Optional[Dict]:
        """Extrai informações de uma função."""
        info = {
            "name": "",
            "lineno": 0,
            "parameters": [],
            "return_type": "",
            "receiver": None,
            "is_variadic": False,
        }

        # Nome
        name_node = node.child_by_field_name("name")
        if name_node:
            info["name"] = code[name_node.start_byte : name_node.end_byte]
            info["lineno"] = code[: name_node.start_byte].count("\n") + 1

        # Receiver
        receiver_node = node.child_by_field_name("receiver")
        if receiver_node:
            for child in receiver_node.children:
                if child.type == "parameter_declaration":
                    param_name = child.child_by_field_name("name")
                    param_type = child.child_by_field_name("type")
                    if param_name and param_type:
                        info["receiver"] = {
                            "name": code[param_name.start_byte : param_name.end_byte],
                            "type": code[param_type.start_byte : param_type.end_byte],
                        }
                    elif param_type:
                        info["receiver"] = {
                            "name": "",
                            "type": code[param_type.start_byte : param_type.end_byte],
                        }

        # Parâmetros
        params_node = node.child_by_field_name("parameters")
        if params_node:
            for child in params_node.children:
                if child.type == "parameter_declaration":
                    param_name = child.child_by_field_name("name")
                    param_type = child.child_by_field_name("type")
                    if param_name and param_type:
                        info["parameters"].append(
                            {
                                "name": code[param_name.start_byte : param_name.end_byte],
                                "type": code[param_type.start_byte : param_type.end_byte],
                            }
                        )

        # Return type
        result_node = node.child_by_field_name("result")
        if result_node:
            info["return_type"] = code[result_node.start_byte : result_node.end_byte]

        return info

    def _detect_concurrency_patterns(self, root_node, code: str, result: Dict):
        """Detecta padrões de concorrência Go."""
        for node in root_node.descendants_of_type(
            {
                "go_statement",
                "send_statement",
                "receive_statement",
                "defer_statement",
                "channel_type",
                "make_statement",
            }
        ):
            if node.type == "go_statement":
                result["goroutines"].append({"lineno": code[: node.start_byte].count("\n") + 1})
            elif node.type == "defer_statement":
                result["defers"].append({"lineno": code[: node.start_byte].count("\n") + 1})
            elif node.type == "channel_type":
                result["channels"].append({"lineno": code[: node.start_byte].count("\n") + 1})

    def _calculate_complexity_ts(self, tree) -> int:
        """Calcula complexidade ciclomática via tree-sitter."""
        complexity = 1  # Base

        # Contar estruturas de controle
        for node in tree.root_node.descendants_of_type(
            {
                "if_statement",
                "for_statement",
                "range_statement",
                "switch_statement",
                "select_statement",
                "communication_case",
                "case_clause",
            }
        ):
            complexity += 1

        return complexity

    def _parse_with_regex(self, code: str, filename: str) -> Dict[str, Any]:
        """Parse baseado em regex (fallback)."""
        import re

        result = self._empty_result()

        # Package
        package_match = re.search(r"package\s+(\w+)", code)
        if package_match:
            result["packages"] = package_match.group(1)

        # Imports
        for match in re.finditer(r'import\s+"([^"]+)"', code):
            result["imports"].append(
                {"name": match.group(1), "lineno": code[: match.start()].count("\n") + 1}
            )
        # Imports com parenteses
        import_block = re.search(r"import\s*\((.*?)\)", code, re.DOTALL)
        if import_block:
            for match in re.finditer(r'"([^"]+)"', import_block.group(1)):
                result["imports"].append(
                    {
                        "name": match.group(1),
                        "lineno": code[: import_block.start() + match.start()].count("\n") + 1,
                    }
                )

        # Structs
        for struct_match in re.finditer(
            r"type\s+(\w+)\s+struct\s*\{([^}]*(?:\{[^}]*\}[^}]*)*)\}",
            code,
            re.MULTILINE | re.DOTALL,
        ):
            struct_name = struct_match.group(1)
            struct_body = struct_match.group(2)

            fields = []
            for field_match in re.finditer(r"(\w+)\s+(\S+(?:\s*\[\s*\]s*)?)", struct_body):
                field_name = field_match.group(1)
                field_type = field_match.group(2)
                if field_name not in ["type", "struct", ""]:
                    fields.append({"name": field_name, "type": field_type})

            result["structs"].append(
                {
                    "name": struct_name,
                    "lineno": code[: struct_match.start()].count("\n") + 1,
                    "fields": fields,
                    "embedded": [],
                }
            )

        # Interfaces
        for interface_match in re.finditer(
            r"type\s+(\w+)\s+interface\s*\{([^}]*(?:\{[^}]*\}[^}]*)*)\}",
            code,
            re.MULTILINE | re.DOTALL,
        ):
            interface_name = interface_match.group(1)
            interface_body = interface_match.group(2)

            methods = []
            for method_match in re.finditer(r"(\w+)\s*\(", interface_body):
                methods.append(method_match.group(1))

            result["interfaces"].append(
                {
                    "name": interface_name,
                    "lineno": code[: interface_match.start()].count("\n") + 1,
                    "methods": methods,
                }
            )

        # Métodos (com receiver) - processar primeiro para não confundir com funções
        for method_match in re.finditer(
            r"func\s*\(([^)]+)\)\s+(\w+)\s*\(([^)]*)\)(?:\s+(\S+))?(?:\s+\{)", code
        ):
            receiver = method_match.group(1)
            method_name = method_match.group(2)
            params = method_match.group(3) or ""
            return_type = method_match.group(4) or ""

            result["methods"].append(
                {
                    "name": method_name,
                    "lineno": code[: method_match.start()].count("\n") + 1,
                    "parameters": self._parse_go_params(params),
                    "return_type": return_type,
                    "receiver": self._parse_go_receiver(receiver),
                    "is_variadic": "..." in params,
                }
            )

        # Funções (sem receiver) - verificar que não começa com ( antes de func
        for func_match in re.finditer(r"func\s+(\w+)\s*\(([^)]*)\)(?:\s+(\S+))?\s*\{", code):
            # Verificar se não é um método verificando se há '(' imediatamente antes de 'func'
            match_start = func_match.start()
            if match_start > 0 and code[match_start - 1] == "(":
                continue  # É um método, skip

            func_name = func_match.group(1)
            params = func_match.group(2) or ""
            return_type = func_match.group(3) or ""

            result["functions"].append(
                {
                    "name": func_name,
                    "lineno": code[: func_match.start()].count("\n") + 1,
                    "parameters": self._parse_go_params(params),
                    "return_type": return_type,
                    "receiver": None,
                    "is_variadic": "..." in params,
                }
            )

        # Detectar goroutines
        for go_match in re.finditer(r"\bgo\s+\w+", code):
            result["goroutines"].append({"lineno": code[: go_match.start()].count("\n") + 1})
        for go_match in re.finditer(r"\bgo\s+func", code):
            result["goroutines"].append({"lineno": code[: go_match.start()].count("\n") + 1})

        # Detectar canais
        for chan_match in re.finditer(r"chan\s+\w+", code):
            result["channels"].append({"lineno": code[: chan_match.start()].count("\n") + 1})
        for make_match in re.finditer(r"make\s*\(\s*chan", code):
            result["channels"].append({"lineno": code[: make_match.start()].count("\n") + 1})

        # Detectar defer
        for defer_match in re.finditer(r"\bdefer\s+\w+", code):
            result["defers"].append({"lineno": code[: defer_match.start()].count("\n") + 1})

        # Calcular complexidade
        result["complexity"] += self._calculate_complexity_regex(code)

        return result

    def _parse_go_params(self, params_str: str) -> List[Dict]:
        """Parse parâmetros Go."""
        params = []
        if not params_str or params_str.strip() == "":
            return params

        for part in params_str.split(","):
            part = part.strip()
            if not part or part == "...":
                continue
            # Split por espaço para separar nome do tipo
            tokens = part.split()
            if len(tokens) >= 2:
                params.append({"name": tokens[0], "type": tokens[1]})
            elif len(tokens) == 1:
                params.append({"name": "", "type": tokens[0]})

        return params

    def _parse_go_receiver(self, receiver_str: str) -> Dict:
        """Parse receiver Go."""
        receiver_str = receiver_str.strip()
        # Formato: nome tipo ou *nome tipo
        parts = receiver_str.split()
        if len(parts) >= 2:
            return {"name": parts[0], "type": parts[1].lstrip("*")}
        elif len(parts) == 1:
            return {"name": "", "type": parts[0].lstrip("*")}
        return {}

    def _calculate_complexity_regex(self, code: str) -> int:
        """Calcula complexidade usando regex."""
        import re

        complexity = 1  # Base complexity
        complexity += len(re.findall(r"\bif\s+", code))
        complexity += len(re.findall(r"\belse\s+", code))
        complexity += len(re.findall(r"\bfor\s+", code))
        complexity += len(re.findall(r"\brange\s+", code))
        complexity += len(re.findall(r"\bswitch\s+", code))
        complexity += len(re.findall(r"\bselect\s+", code))
        complexity += len(re.findall(r"\bcase\s+", code))
        complexity += len(re.findall(r"\bdefault\s*:", code))
        complexity += len(re.findall(r"&&", code))
        complexity += len(re.findall(r"\|\|", code))
        return complexity
