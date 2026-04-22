"""
C# AST Parser usando tree-sitter.

Suporta parsing de código C# com fallback regex.
"""

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


class CSharpParser:
    """
    Parser para código C# usando tree-sitter.

    Extrai:
    - Classes (incluindo records)
    - Interfaces
    - Enums
    - Methods (async, static, abstract)
    - Properties
    - Fields
    - Namespaces
    - Using directives
    - Attributes
    - Generics
    """

    def __init__(self):
        self._ts_language = None
        self._ts_parser = None
        self._init_tree_sitter()

    def _init_tree_sitter(self):
        """Inicializa tree-sitter para C#."""
        try:
            import tree_sitter
            from tree_sitter_languages import get_language

            self._ts_language = get_language("c_sharp")
            self._ts_parser = tree_sitter.Parser()
            self._ts_parser.set_language(self._ts_language)
            logger.debug("csharp_parser_tree_sitter_loaded")
        except Exception as e:
            logger.warning(f"csharp_parser_init_failed: {e!s}")
            self._ts_language = None
            self._ts_parser = None

    def parse(self, code: str, filename: str) -> Optional[dict[str, Any]]:
        """
        Parse código C# e extrair informações.

        Args:
            code: Código fonte C#
            filename: Nome do arquivo (para extensão)

        Returns:
            Dicionário com classes, métodos, propriedades, etc.
        """
        if not code or not code.strip():
            return self._empty_result()

        # Tentar tree-sitter primeiro
        if self._ts_parser:
            try:
                return self._parse_with_tree_sitter(code, filename)
            except Exception as e:
                logger.warning(f"tree_sitter_parse_failed: {filename} - {e!s}")

        # Fallback para regex
        return self._parse_with_regex(code, filename)

    def _empty_result(self) -> dict[str, Any]:
        """Retorna estrutura vazia de resultado."""
        return {
            "classes": [],
            "interfaces": [],
            "enums": [],
            "methods": [],
            "properties": [],
            "fields": [],
            "namespaces": "",
            "imports": [],  # using directives
            "attributes": [],
            "complexity": 0,
        }

    def _parse_with_tree_sitter(self, code: str, filename: str) -> dict[str, Any]:
        """Parse usando tree-sitter."""
        tree = self._ts_parser.parse(bytes(code, "utf8"))
        result = self._empty_result()

        # Extrair namespace
        self._extract_namespace(tree.root_node, code, result)

        # Extrair using directives
        self._extract_usings(tree.root_node, code, result)

        # Extrair classes, interfaces, enums
        for node in tree.root_node.children:
            if node.type == "class_declaration":
                cls = self._extract_class_declaration(node, code)
                if cls:
                    result["classes"].append(cls)
            elif node.type == "interface_declaration":
                interface = self._extract_interface_declaration(node, code)
                if interface:
                    result["interfaces"].append(interface)
            elif node.type == "enum_declaration":
                enum = self._extract_enum_declaration(node, code)
                if enum:
                    result["enums"].append(enum)
            elif node.type == "record_declaration":
                # Records são tratados como classes
                cls = self._extract_record_declaration(node, code)
                if cls:
                    result["classes"].append(cls)

        # Calcular complexidade
        result["complexity"] = self._calculate_complexity_ts(tree)

        return result

    def _extract_namespace(self, root_node, code: str, result: dict):
        """Extrai namespace."""
        for node in root_node.children:
            if node.type == "namespace_declaration":
                name_node = node.child_by_field_name("name")
                if name_node:
                    result["namespaces"] = code[name_node.start_byte : name_node.end_byte]

    def _extract_usings(self, root_node, code: str, result: dict):
        """Extrai using directives."""
        for node in root_node.children:
            if node.type == "using_directive":
                name_node = node.child_by_field_name("name")
                if name_node:
                    using_text = code[name_node.start_byte : name_node.end_byte]
                    result["imports"].append(
                        {
                            "name": using_text,
                            "lineno": code[: name_node.start_byte].count("\n") + 1,
                            "is_static": "static" in code[node.start_byte : name_node.start_byte],
                        }
                    )

    def _extract_class_declaration(self, node, code: str) -> Optional[dict]:
        """Extrai informações de uma classe."""
        info = {
            "name": "",
            "lineno": 0,
            "bases": [],
            "implements": [],
            "attributes": [],
            "modifiers": [],
            "type_parameters": [],
            "methods_count": 0,
        }

        # Nome
        name_node = node.child_by_field_name("name")
        if name_node:
            info["name"] = code[name_node.start_byte : name_node.end_byte]
            info["lineno"] = code[: name_node.start_byte].count("\n") + 1

        # Base class (herança)
        bases_node = node.child_by_field_name("base_list")
        if bases_node:
            for child in bases_node.children:
                if child.type == "identifier":
                    base = code[child.start_byte : child.end_byte]
                    if base and base not in [":", ",", "class", "interface"]:
                        info["bases"].append(base)

        # Type parameters (generics)
        type_params_node = node.child_by_field_name("type_parameters")
        if type_params_node:
            for child in type_params_node.children:
                if child.type == "type_parameter":
                    param = code[child.start_byte : child.end_byte]
                    if param:
                        info["type_parameters"].append(param)

        # Modifiers e attributes
        for child in node.children:
            if child.type == "modifiers":
                for mod in child.children:
                    if mod.type == "attribute":
                        info["attributes"].append(self._extract_attribute(mod, code))
                    elif mod.type in [
                        "public",
                        "private",
                        "protected",
                        "internal",
                        "static",
                        "abstract",
                        "sealed",
                        "partial",
                    ]:
                        info["modifiers"].append(mod.type)

        # Contar métodos e propriedades
        body_node = node.child_by_field_name("body")
        if body_node:
            info["methods_count"] = len(
                [
                    n
                    for n in body_node.children
                    if n.type in ["method_declaration", "constructor_declaration"]
                ]
            )

        return info

    def _extract_record_declaration(self, node, code: str) -> Optional[dict]:
        """Extrai informações de um record."""
        info = {
            "name": "",
            "lineno": 0,
            "bases": [],
            "attributes": [],
            "modifiers": [],
            "is_record": True,
            "methods_count": 0,
        }

        # Nome
        name_node = node.child_by_field_name("name")
        if name_node:
            info["name"] = code[name_node.start_byte : name_node.end_byte]
            info["lineno"] = code[: name_node.start_byte].count("\n") + 1

        # Base class/record
        bases_node = node.child_by_field_name("base_list")
        if bases_node:
            for child in bases_node.children:
                if child.type == "identifier":
                    base = code[child.start_byte : child.end_byte]
                    if base and base not in [":", ","]:
                        info["bases"].append(base)

        # Modifiers e attributes
        for child in node.children:
            if child.type == "modifiers":
                for mod in child.children:
                    if mod.type == "attribute":
                        info["attributes"].append(self._extract_attribute(mod, code))
                    elif mod.type in [
                        "public",
                        "private",
                        "protected",
                        "internal",
                        "static",
                        "abstract",
                        "sealed",
                    ]:
                        info["modifiers"].append(mod.type)

        return info

    def _extract_interface_declaration(self, node, code: str) -> Optional[dict]:
        """Extrai informações de uma interface."""
        info = {
            "name": "",
            "lineno": 0,
            "bases": [],
            "attributes": [],
            "modifiers": [],
            "type_parameters": [],
            "methods_count": 0,
        }

        # Nome
        name_node = node.child_by_field_name("name")
        if name_node:
            info["name"] = code[name_node.start_byte : name_node.end_byte]
            info["lineno"] = code[: name_node.start_byte].count("\n") + 1

        # Base interfaces
        bases_node = node.child_by_field_name("base_list")
        if bases_node:
            for child in bases_node.children:
                if child.type == "identifier":
                    base = code[child.start_byte : child.end_byte]
                    if base and base not in [":", ","]:
                        info["bases"].append(base)

        # Type parameters
        type_params_node = node.child_by_field_name("type_parameters")
        if type_params_node:
            for child in type_params_node.children:
                if child.type == "type_parameter":
                    param = code[child.start_byte : child.end_byte]
                    if param:
                        info["type_parameters"].append(param)

        # Modifiers e attributes
        for child in node.children:
            if child.type == "modifiers":
                for mod in child.children:
                    if mod.type == "attribute":
                        info["attributes"].append(self._extract_attribute(mod, code))
                    elif mod.type in ["public", "private", "protected", "internal"]:
                        info["modifiers"].append(mod.type)

        # Contar métodos
        body_node = node.child_by_field_name("body")
        if body_node:
            info["methods_count"] = len(
                [n for n in body_node.children if n.type == "method_declaration"]
            )

        return info

    def _extract_enum_declaration(self, node, code: str) -> Optional[dict]:
        """Extrai informações de um enum."""
        info = {
            "name": "",
            "lineno": 0,
            "values": [],
            "bases": [],
            "attributes": [],
            "modifiers": [],
        }

        # Nome
        name_node = node.child_by_field_name("name")
        if name_node:
            info["name"] = code[name_node.start_byte : name_node.end_byte]
            info["lineno"] = code[: name_node.start_byte].count("\n") + 1

        # Base type (enum : byte, etc.)
        bases_node = node.child_by_field_name("base_list")
        if bases_node:
            for child in bases_node.children:
                if child.type == "identifier":
                    base = code[child.start_byte : child.end_byte]
                    if base and base not in [":", ","]:
                        info["bases"].append(base)

        # Enum values
        for child in node.children:
            if child.type == "enum_member_declaration":
                name = child.child_by_field_name("name")
                if name:
                    info["values"].append(code[name.start_byte : name.end_byte])
            elif child.type == "modifiers":
                for mod in child.children:
                    if mod.type == "attribute":
                        info["attributes"].append(self._extract_attribute(mod, code))
                    elif mod.type in ["public", "private", "internal"]:
                        info["modifiers"].append(mod.type)

        return info

    def _extract_method_declaration(self, node, code: str) -> Optional[dict]:
        """Extrai informações de um método."""
        info = {
            "name": "",
            "lineno": 0,
            "return_type": "",
            "parameters": [],
            "attributes": [],
            "modifiers": [],
            "type_parameters": [],
            "body": None,
            "is_async": False,
            "is_static": False,
            "is_abstract": False,
            "is_override": False,
            "is_virtual": False,
        }

        # Nome
        name_node = node.child_by_field_name("name")
        if name_node:
            info["name"] = code[name_node.start_byte : name_node.end_byte]
            info["lineno"] = code[: name_node.start_byte].count("\n") + 1

        # Return type
        type_node = node.child_by_field_name("type")
        if type_node:
            info["return_type"] = code[type_node.start_byte : type_node.end_byte]
            # Check for async return type (Task, Task<T>, ValueTask, ValueTask<T>)
            if "Task" in info["return_type"] or "ValueTask" in info["return_type"]:
                info["is_async"] = True

        # Parâmetros
        params_node = node.child_by_field_name("parameters")
        if params_node:
            for child in params_node.children:
                if child.type == "parameter":
                    param_name = child.child_by_field_name("name")
                    param_type = child.child_by_field_name("type")
                    if param_name:
                        param_info = {"name": code[param_name.start_byte : param_name.end_byte]}
                        if param_type:
                            param_info["type"] = code[param_type.start_byte : param_type.end_byte]
                        info["parameters"].append(param_info)

        # Type parameters
        type_params_node = node.child_by_field_name("type_parameters")
        if type_params_node:
            for child in type_params_node.children:
                if child.type == "type_parameter":
                    param = code[child.start_byte : child.end_byte]
                    if param:
                        info["type_parameters"].append(param)

        # Modifiers e attributes
        for child in node.children:
            if child.type == "modifiers":
                for mod in child.children:
                    if mod.type == "attribute":
                        info["attributes"].append(self._extract_attribute(mod, code))
                    elif mod.type == "async":
                        info["is_async"] = True
                        info["modifiers"].append(mod.type)
                    elif mod.type == "static":
                        info["is_static"] = True
                        info["modifiers"].append(mod.type)
                    elif mod.type == "abstract":
                        info["is_abstract"] = True
                        info["modifiers"].append(mod.type)
                    elif mod.type == "override":
                        info["is_override"] = True
                        info["modifiers"].append(mod.type)
                    elif mod.type == "virtual":
                        info["is_virtual"] = True
                        info["modifiers"].append(mod.type)
                    elif mod.type in [
                        "public",
                        "private",
                        "protected",
                        "internal",
                        "sealed",
                        "extern",
                        "unsafe",
                    ]:
                        info["modifiers"].append(mod.type)

        return info

    def _extract_attribute(self, node, code: str) -> str:
        """Extrai attribute como string."""
        return code[node.start_byte : node.end_byte].strip()

    def _calculate_complexity_ts(self, tree) -> int:
        """Calcula complexidade ciclomática via tree-sitter."""
        complexity = 1  # Base

        # Contar estruturas de controle
        for node in tree.root_node.descendants_of_type(
            {
                "if_statement",
                "while_statement",
                "for_statement",
                "foreach_statement",
                "do_statement",
                "catch_clause",
                "conditional_expression",
                "switch_expression",
                "switch_statement",
            }
        ):
            complexity += 1

        return complexity

    def _parse_with_regex(self, code: str, filename: str) -> dict[str, Any]:
        """Parse baseado em regex (fallback)."""
        import re

        result = self._empty_result()

        # Namespace
        namespace_match = re.search(r"namespace\s+([\w.]+)", code)
        if namespace_match:
            result["namespaces"] = namespace_match.group(1)

        # Usings
        for match in re.finditer(r"using\s+(static\s+)?([\w.]+);", code):
            result["imports"].append(
                {
                    "name": match.group(2),
                    "lineno": code[: match.start()].count("\n") + 1,
                    "is_static": match.group(1) is not None,
                }
            )

        # Classes - incluindo records
        for class_match in re.finditer(
            r"(?:\[(?:\w+(?:\([^)]*\))?\s*)*\]\s*)*\s*"
            r"(public|private|protected|internal)?\s*"
            r"(?:static\s+)?(?:abstract\s+)?(?:sealed\s+)?(?:partial\s+)?"
            r"(class|record)\s+(\w+)(?:\s*<[^>]+>)?"
            r"(?:\s*:\s*([\w\s,<>]+))?\s*\{",
            code,
        ):
            visibility = class_match.group(1) or ""
            class_type = class_match.group(2)
            class_name = class_match.group(3)
            bases = class_match.group(4)

            class_start = class_match.end()
            class_end = self._find_matching_brace(code, class_start)

            methods_count = 0

            if class_end:
                class_body = code[class_start:class_end]

                # Contar métodos na classe
                methods_count = len(
                    re.findall(
                        r"(?:public|private|protected|internal)?\s*"
                        r"(?:static\s+)?(?:async\s+)?(?:abstract\s+)?(?:override\s+)?(?:virtual\s+)?"
                        r"(?:new\s+)?(?:extern\s+)?(?:unsafe\s+)?"
                        r"(?:[\w<>?,\s]+)\s+\w+\s*\([^)]*\)\s*(?:where\s+[^{]+)?\s*\{",
                        class_body,
                    )
                )

                # Contar propriedades
                len(re.findall(r"\{[^}]*\{[^}]*get[^}]*\}[^}]*\}", class_body)) + len(
                    re.findall(
                        r"(?:public|private|protected|internal)?\s*(?:static\s+)?"
                        r"(?:override\s+)?(?:virtual\s+)?"
                        r"(?:required\s+)?"
                        r"[\w<>?,\s]+\s+\w+\s*\{[^}]*get[^}]*\}",
                        class_body,
                    )
                )

                # Extrair métodos individuais
                self._extract_methods_from_class_body(
                    class_body, code, class_start, result, class_name
                )

            result["classes"].append(
                {
                    "name": class_name,
                    "lineno": code[: class_match.start()].count("\n") + 1,
                    "bases": [b.strip() for b in bases.split(",")] if bases else [],
                    "attributes": [],
                    "modifiers": [visibility, class_type] if visibility else [class_type],
                    "type_parameters": [],
                    "methods_count": methods_count,
                    "is_record": class_type == "record",
                }
            )

        # Interfaces
        for interface_match in re.finditer(
            r"(?:\[(?:\w+(?:\([^)]*\))?\s*)*\]\s*)*\s*"
            r"(public|private|protected|internal)?\s*"
            r"interface\s+(\w+)(?:\s*<[^>]+>)?"
            r"(?:\s*:\s*([\w\s,<>]+))?\s*\{",
            code,
        ):
            interface_name = interface_match.group(2)
            bases = interface_match.group(3)

            interface_start = interface_match.end()
            interface_end = self._find_matching_brace(code, interface_start)

            methods_count = 0
            if interface_end:
                interface_body = code[interface_start:interface_end]
                methods_count = len(
                    re.findall(r"\w+\s*\([^)]*\)\s*(?:where\s+[^{;]+)?\s*[;{]", interface_body)
                )

            result["interfaces"].append(
                {
                    "name": interface_name,
                    "lineno": code[: interface_match.start()].count("\n") + 1,
                    "bases": [b.strip() for b in bases.split(",")] if bases else [],
                    "attributes": [],
                    "modifiers": [],
                    "type_parameters": [],
                    "methods_count": methods_count,
                }
            )

        # Enums
        for enum_match in re.finditer(
            r"(?:\[(?:\w+(?:\([^)]*\))?\s*)*\]\s*)*\s*"
            r"(?:public|private|protected|internal)?\s*"
            r"enum\s+(\w+)(?:\s*:\s*(\w+))?\s*\{",
            code,
        ):
            enum_name = enum_match.group(1)
            enum_base = enum_match.group(2)

            # Extrair valores do enum
            enum_start = enum_match.end()
            enum_end = self._find_matching_brace(code, enum_start)
            enum_values = []
            if enum_end:
                enum_body = code[enum_start:enum_end]
                for const_match in re.finditer(r"(\w+)(?:\s*=\s*[^,}]+)?", enum_body):
                    const_name = const_match.group(1).strip()
                    if const_name and const_name not in ["{", "}", ","]:
                        enum_values.append(const_name)

            result["enums"].append(
                {
                    "name": enum_name,
                    "lineno": code[: enum_match.start()].count("\n") + 1,
                    "values": enum_values,
                    "bases": [enum_base] if enum_base else [],
                    "attributes": [],
                    "modifiers": [],
                }
            )

        # Calcular complexidade do código
        result["complexity"] += self._calculate_complexity_regex(code)

        return result

    def _extract_methods_from_class_body(
        self, class_body: str, full_code: str, class_start: int, result: dict, class_name: str
    ):
        """Extrai métodos do corpo de uma classe/interface."""
        import re

        # Regex para métodos dentro da classe - mais permissivo
        # Grupos: 1=visibility, 2=return_type, 3=method_name, 4=params, 5=where (opcional)
        for match in re.finditer(
            r"(?:\[(?:\w+(?:\([^)]*\))?\s*)*\]\s*)*\s*"
            r"(public|private|protected|internal)?\s*"
            r"(?:static\s+)?(?:async\s+)?(?:abstract\s+)?(?:override\s+)?(?:virtual\s+)?"
            r"(?:new\s+)?(?:extern\s+)?(?:unsafe\s+)?"
            r"(\S+(?:<[^>]+>)?)\s+(\w+)\s*\(([^)]*)\)"
            r"(?:\s+where\s+([\w\s,<>]+))?"
            r"\s*\{",
            class_body,
        ):
            visibility = match.group(1) or ""
            return_type = match.group(2)
            method_name = match.group(3)
            params = match.group(4) or ""
            match.group(5) if len(match.groups()) >= 5 else None

            # Filtrar palavras-chave que não são nomes válidos de métodos
            if method_name in [
                "class",
                "interface",
                "enum",
                "struct",
                "record",
                "get",
                "set",
                "init",
                "add",
                "remove",
            ]:
                continue

            # Filtrar se o nome começa com maiúscula e não tem parênteses (provavelmente propriedade)
            if method_name[0].isupper() and return_type in ["get", "set", "init"]:
                continue

            # Calcular linha correta
            method_pos = class_start + match.start()
            lineno = full_code[:method_pos].count("\n") + 1

            # Determinar se é async
            is_async = (
                "async" in match.group(0) or "Task" in return_type or "ValueTask" in return_type
            )
            is_static = "static" in match.group(0)
            is_abstract = "abstract" in match.group(0)
            is_override = "override" in match.group(0)
            is_virtual = "virtual" in match.group(0)

            # Processar parâmetros
            param_list = []
            if params.strip():
                for p in params.split(","):
                    p = p.strip()
                    if p and p not in ["..."]:
                        parts = p.split()
                        if len(parts) >= 2 and parts[0] not in ["ref", "out", "in", "params"]:
                            param_list.append({"name": parts[-1], "type": parts[0]})
                        elif len(parts) == 1:
                            param_list.append({"name": parts[0], "type": None})

            result["methods"].append(
                {
                    "name": method_name,
                    "lineno": lineno,
                    "return_type": return_type if return_type != "void" else None,
                    "parameters": param_list,
                    "attributes": [],
                    "modifiers": [m for m in [visibility] if m],
                    "type_parameters": [],
                    "is_async": is_async,
                    "is_static": is_static,
                    "is_abstract": is_abstract,
                    "is_override": is_override,
                    "is_virtual": is_virtual,
                    "class_name": class_name,
                }
            )
            result["complexity"] += 1

    def _calculate_complexity_regex(self, code: str) -> int:
        """Calcula complexidade usando regex."""
        import re

        complexity = 0
        complexity += len(re.findall(r"\bif\s*\(", code))
        complexity += len(re.findall(r"\belse\s+if\s*\(", code))
        complexity += len(re.findall(r"\bfor\s*\(", code))
        complexity += len(re.findall(r"\bforeach\s*\(", code))
        complexity += len(re.findall(r"\bwhile\s*\(", code))
        complexity += len(re.findall(r"\bdo\s*\{", code))
        complexity += len(re.findall(r"\bcatch\s*\(", code))
        complexity += len(re.findall(r"\?", code))
        complexity += len(re.findall(r"&&", code))
        complexity += len(re.findall(r"\|\|", code))
        complexity += len(re.findall(r"\bswitch\s*\(", code))
        return complexity

    def _find_matching_brace(self, code: str, start: int) -> Optional[int]:
        """Encontra a closing brace."""
        brace_count = 1
        i = start
        while i < len(code) and brace_count > 0:
            if code[i] == "{":
                brace_count += 1
            elif code[i] == "}":
                brace_count -= 1
            i += 1
        return i if brace_count == 0 else None
