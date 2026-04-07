"""
Java Parser - Análise de código Java usando tree-sitter.

Extrai classes, interfaces, métodos, campos, annotations, generics.
"""

from typing import Any, Dict, List, Optional

import structlog

try:
    import tree_sitter

    TREE_SITTER_AVAILABLE = True
except ImportError:
    TREE_SITTER_AVAILABLE = False
    tree_sitter = None

logger = structlog.get_logger()


class JavaParser:
    """Parser para código Java."""

    def __init__(self):
        """Inicializa o JavaParser."""
        self._parsed_cache: Dict[str, Dict] = {}
        self._parse_errors: set = set()
        self._parser = None
        self._language = None

        if TREE_SITTER_AVAILABLE:
            try:
                # Import da biblioteca tree-sitter-java
                import tree_sitter_java

                self._language = tree_sitter_java.language()
                self._parser = tree_sitter.Parser()
                self._parser.set_language(self._language)
            except Exception as e:
                logger.debug("java_parser_init_failed", error=str(e))
                # Tentar método alternativo
                try:
                    from tree_sitter_languages import get_language

                    self._language = get_language("java")
                    self._parser = tree_sitter.Parser()
                    self._parser.set_language(self._language)
                except Exception as e2:
                    logger.warning("java_parser_init_failed", error=str(e2))
                    self._language = None
                    self._parser = None
        else:
            self._language = None
            self._parser = None

    def parse(self, code: str, filename: str) -> Optional[Dict[str, Any]]:
        """
        Faz parsing de código Java.

        Args:
            code: Código fonte Java
            filename: Nome do arquivo

        Returns:
            Dict com classes, interfaces, métodos, campos, etc.
        """
        if not code or not code.strip():
            return self._empty_result()

        try:
            if self._parser and self._language:
                return self._parse_with_tree_sitter(code, filename)
            else:
                logger.warning(
                    "tree_sitter_not_available",
                    filename=filename,
                    message="Using regex-based fallback parser for Java",
                )
                return self._parse_with_regex(code, filename)

        except Exception as e:
            logger.error("java_parse_error", filename=filename, error=str(e))
            self._parse_errors.add(filename)
            return None

    def _empty_result(self) -> Dict[str, Any]:
        """Retorna resultado vazio padrão."""
        return {
            "classes": [],
            "interfaces": [],
            "enums": [],
            "methods": [],
            "fields": [],
            "annotations": [],
            "imports": [],
            "packages": None,
            "complexity": 1,
            "has_errors": False,
        }

    def _parse_with_tree_sitter(self, code: str, filename: str) -> Dict[str, Any]:
        """Parse usando tree-sitter."""
        tree = self._parser.parse(bytes(code, "utf8"))

        result = self._empty_result()
        result["imports"] = self._extract_imports_ts(code, tree)
        result["packages"] = self._extract_package_ts(code, tree)

        # Extrair classes, interfaces, enums, methods
        self._extract_declarations_ts(tree.root_node, code, result)

        # Calcular complexidade
        result["complexity"] = self._calculate_complexity_ts(tree)

        return result

    def _extract_package_ts(self, code: str, tree) -> Optional[str]:
        """Extrai nome do package."""
        query = self._language.query("(package_declaration (scoped_identifier_name) @name)")
        captures = query.captures(tree.root_node)

        for node, _ in captures:
            start = node.start_byte
            end = node.end_byte
            return code[start:end]

        return None

    def _extract_imports_ts(self, code: str, tree) -> List[Dict]:
        """Extrai imports."""
        imports = []
        query = self._language.query("(import_declaration (scoped_identifier_name) @name)")

        code.split("\n")
        for node, _ in query.captures(tree.root_node):
            start = node.start_byte
            end = node.end_byte
            import_name = code[start:end]
            lineno = code[:start].count("\n") + 1

            # Verificar se é static import
            line_start = max(0, start - 100)
            context = code[line_start:start]
            is_static = "static" in context

            imports.append({"name": import_name, "lineno": lineno, "is_static": is_static})

        return imports

    def _extract_declarations_ts(self, node, code: str, result: Dict):
        """Extrai declarações recursivamente."""
        if node.type == "class_declaration":
            class_info = self._extract_class_declaration(node, code)
            result["classes"].append(class_info)
            result["complexity"] += 1

        elif node.type == "interface_declaration":
            interface_info = self._extract_interface_declaration(node, code)
            result["interfaces"].append(interface_info)

        elif node.type == "enum_declaration":
            enum_info = self._extract_enum_declaration(node, code)
            result["enums"].append(enum_info)

        elif node.type == "method_declaration":
            method_info = self._extract_method_declaration(node, code)
            result["methods"].append(method_info)
            result["complexity"] += 1

        elif node.type == "field_declaration":
            field_info = self._extract_field_declaration(node, code)
            result["fields"].extend(field_info)

        elif node.type == "constructor_declaration":
            method_info = self._extract_constructor_declaration(node, code)
            result["methods"].append(method_info)
            result["complexity"] += 1

        # Recursão para filhos
        for child in node.children:
            self._extract_declarations_ts(child, code, result)

    def _extract_class_declaration(self, node, code: str) -> Dict:
        """Extrai informações de uma classe."""
        info = {
            "name": "",
            "lineno": 0,
            "extends": None,
            "implements": [],
            "annotations": [],
            "modifiers": [],
            "type_parameters": [],
            "fields_count": 0,
            "methods_count": 0,
        }

        # Nome
        name_node = node.child_by_field_name("name")
        if name_node:
            info["name"] = code[name_node.start_byte : name_node.end_byte]
            info["lineno"] = code[: name_node.start_byte].count("\n") + 1

        # Extends
        extends_node = node.child_by_field_name("superclass")
        if extends_node:
            info["extends"] = code[extends_node.start_byte : extends_node.end_byte]

        # Implements
        interfaces_node = node.child_by_field_name("super_interfaces")
        if interfaces_node:
            for child in interfaces_node.children:
                if child.type == "type_list":
                    for type_child in child.children:
                        if type_child.type == "type_identifier":
                            impl = code[type_child.start_byte : type_child.end_byte]
                            if impl and impl not in ["implements", ","]:
                                info["implements"].append(impl)

        # Modifiers e annotations
        for child in node.children:
            if child.type == "modifiers":
                for mod in child.children:
                    if mod.type == "annotation":
                        ann = self._extract_annotation(mod, code)
                        info["annotations"].append(ann)
                    elif mod.type in [
                        "public",
                        "private",
                        "protected",
                        "static",
                        "final",
                        "abstract",
                        "synchronized",
                        "volatile",
                        "transient",
                        "native",
                        "strictfp",
                    ]:
                        info["modifiers"].append(mod.type)

            elif child.type == "type_parameters":
                for param in child.children:
                    if param.type == "type_parameter":
                        name = code[param.start_byte : param.end_byte]
                        if name and name not in ["<", ">", ","]:
                            info["type_parameters"].append(name.strip("<>,"))

        # Contar fields e methods no body
        body_node = node.child_by_field_name("body")
        if body_node:
            info["fields_count"] = len(
                [n for n in body_node.children if n.type == "field_declaration"]
            )
            info["methods_count"] = len(
                [
                    n
                    for n in body_node.children
                    if n.type in ["method_declaration", "constructor_declaration"]
                ]
            )

        return info

    def _extract_interface_declaration(self, node, code: str) -> Dict:
        """Extrai informações de uma interface."""
        info = {
            "name": "",
            "lineno": 0,
            "extends": [],
            "annotations": [],
            "modifiers": [],
            "methods_count": 0,
        }

        # Nome
        name_node = node.child_by_field_name("name")
        if name_node:
            info["name"] = code[name_node.start_byte : name_node.end_byte]
            info["lineno"] = code[: name_node.start_byte].count("\n") + 1

        # Extends (interfaces podem estender outras)
        extends_node = node.child_by_field_name("extends")
        if extends_node:
            for child in extends_node.children:
                if child.type == "type_list":
                    for type_child in child.children:
                        if type_child.type == "type_identifier":
                            ext = code[type_child.start_byte : type_child.end_byte]
                            if ext and ext not in ["extends", ","]:
                                info["extends"].append(ext)

        # Modifiers e annotations
        for child in node.children:
            if child.type == "modifiers":
                for mod in child.children:
                    if mod.type == "annotation":
                        info["annotations"].append(self._extract_annotation(mod, code))
                    elif mod.type in ["public", "private", "protected", "static", "abstract"]:
                        info["modifiers"].append(mod.type)

        # Contar métodos
        body_node = node.child_by_field_name("body")
        if body_node:
            info["methods_count"] = len(
                [n for n in body_node.children if n.type == "method_declaration"]
            )

        return info

    def _extract_enum_declaration(self, node, code: str) -> Dict:
        """Extrai informações de um enum."""
        info = {
            "name": "",
            "lineno": 0,
            "constants": [],
            "implements": [],
            "annotations": [],
            "modifiers": [],
        }

        # Nome
        name_node = node.child_by_field_name("name")
        if name_node:
            info["name"] = code[name_node.start_byte : name_node.end_byte]
            info["lineno"] = code[: name_node.start_byte].count("\n") + 1

        # Implements (enums podem implementar interfaces)
        interfaces_node = node.child_by_field_name("super_interfaces")
        if interfaces_node:
            for child in interfaces_node.children:
                if child.type == "type_list":
                    for type_child in child.children:
                        if type_child.type == "type_identifier":
                            impl = code[type_child.start_byte : type_child.end_byte]
                            if impl and impl not in ["implements", ","]:
                                info["implements"].append(impl)

        # Constantes do enum
        for child in node.children:
            if child.type == "enum_constant":
                const_name = child.child_by_field_name("name")
                if const_name:
                    info["constants"].append(code[const_name.start_byte : const_name.end_byte])
            elif child.type == "modifiers":
                for mod in child.children:
                    if mod.type == "annotation":
                        info["annotations"].append(self._extract_annotation(mod, code))
                    elif mod.type in ["public", "private", "protected", "static", "final"]:
                        info["modifiers"].append(mod.type)

        return info

    def _extract_method_declaration(self, node, code: str) -> Dict:
        """Extrai informações de um método."""
        info = {
            "name": "",
            "lineno": 0,
            "return_type": None,
            "parameters": [],
            "annotations": [],
            "modifiers": [],
            "throws": [],
            "is_static": False,
            "is_abstract": False,
        }

        # Nome
        name_node = node.child_by_field_name("name")
        if name_node:
            info["name"] = code[name_node.start_byte : name_node.end_byte]
            info["lineno"] = code[: name_node.start_byte].count("\n") + 1

        # Return type
        return_node = node.child_by_field_name("type")
        if return_node:
            info["return_type"] = code[return_node.start_byte : return_node.end_byte]

        # Parâmetros
        params_node = node.child_by_field_name("parameters")
        if params_node:
            for child in params_node.children:
                if child.type == "formal_parameter":
                    param_info = self._extract_formal_parameter(child, code)
                    if param_info:
                        info["parameters"].append(param_info)
                elif child.type == "variable_arity_parameter":
                    # Varargs (String...)
                    param_info = self._extract_formal_parameter(child, code)
                    if param_info:
                        param_info["is_varargs"] = True
                        info["parameters"].append(param_info)

        # Modifiers e annotations
        for child in node.children:
            if child.type == "modifiers":
                for mod in child.children:
                    if mod.type == "annotation":
                        info["annotations"].append(self._extract_annotation(mod, code))
                    elif mod.type == "static":
                        info["is_static"] = True
                        info["modifiers"].append("static")
                    elif mod.type == "abstract":
                        info["is_abstract"] = True
                        info["modifiers"].append("abstract")
                    elif mod.type in [
                        "public",
                        "private",
                        "protected",
                        "final",
                        "synchronized",
                        "native",
                    ]:
                        info["modifiers"].append(mod.type)

        # Throws
        throws_node = node.child_by_field_name("throws")
        if throws_node:
            for child in throws_node.children:
                if child.type == "type_identifier":
                    info["throws"].append(code[child.start_byte : child.end_byte])

        return info

    def _extract_constructor_declaration(self, node, code: str) -> Dict:
        """Extrai informações de um construtor."""
        info = {
            "name": "<constructor>",
            "lineno": 0,
            "parameters": [],
            "annotations": [],
            "modifiers": [],
            "throws": [],
        }

        # Nome (constructor tem o mesmo nome da classe)
        name_node = node.child_by_field_name("name")
        if name_node:
            info["name"] = code[name_node.start_byte : name_node.end_byte]
            info["lineno"] = code[: name_node.start_byte].count("\n") + 1

        # Parâmetros
        params_node = node.child_by_field_name("parameters")
        if params_node:
            for child in params_node.children:
                if child.type == "formal_parameter":
                    param_info = self._extract_formal_parameter(child, code)
                    if param_info:
                        info["parameters"].append(param_info)

        # Modifiers e annotations
        for child in node.children:
            if child.type == "modifiers":
                for mod in child.children:
                    if mod.type == "annotation":
                        info["annotations"].append(self._extract_annotation(mod, code))
                    elif mod.type in ["public", "private", "protected"]:
                        info["modifiers"].append(mod.type)

        # Throws
        throws_node = node.child_by_field_name("throws")
        if throws_node:
            for child in throws_node.children:
                if child.type == "type_identifier":
                    info["throws"].append(code[child.start_byte : child.end_byte])

        return info

    def _extract_formal_parameter(self, node, code: str) -> Optional[Dict]:
        """Extrai informações de um parâmetro."""
        info = {"name": "", "type": None, "is_varargs": False}

        # Tipo
        type_node = node.child_by_field_name("type")
        if type_node:
            info["type"] = code[type_node.start_byte : type_node.end_byte]

        # Nome
        name_node = node.child_by_field_name("name")
        if name_node:
            info["name"] = code[name_node.start_byte : name_node.end_byte]

        # Se não tem nome, pode ser parâmetro sem nome em método abstrato
        if not info["name"]:
            return None

        return info

    def _extract_field_declaration(self, node, code: str) -> List[Dict]:
        """Extrai informações de campos (pode ter declaração múltipla)."""
        fields = []

        # Tipo
        type_node = node.child_by_field_name("type")
        field_type = None
        if type_node:
            field_type = code[type_node.start_byte : type_node.end_byte]

        # Declarators (pode ter: int a, b, c;)
        declarators_node = node.child_by_field_name("declarator")
        if declarators_node:
            info = {
                "name": code[declarators_node.start_byte : declarators_node.end_byte],
                "type": field_type,
                "lineno": code[: declarators_node.start_byte].count("\n") + 1,
            }
            fields.append(info)

        return fields

    def _extract_annotation(self, node, code: str) -> Dict:
        """Extrai informações de uma annotation."""
        info = {"name": "", "arguments": []}

        name_node = node.child_by_field_name("name")
        if name_node:
            info["name"] = code[name_node.start_byte : name_node.end_byte]

        # Argumentos da annotation: @Override(value="test")
        for child in node.children:
            if child.type == "annotation_argument_list":
                for arg in child.children:
                    if arg.type == "string_literal":
                        info["arguments"].append(code[arg.start_byte : arg.end_byte])

        return info

    def _calculate_complexity_ts(self, tree) -> int:
        """Calcula complexidade ciclomática."""
        complexity = 1  # Base

        # Contar estruturas de controle
        for node in tree.root_node.descendants_of_type(
            {
                "if_statement",
                "while_statement",
                "for_statement",
                "enhanced_for_statement",
                "do_statement",
                "catch_clause",
                "conditional_expression",
                "switch_expression",
            }
        ):
            complexity += 1

        return complexity

    def _parse_with_regex(self, code: str, filename: str) -> Dict[str, Any]:
        """Parse baseado em regex (fallback)."""
        import re

        result = self._empty_result()

        # Package
        package_match = re.search(r"package\s+([\w.]+);", code)
        if package_match:
            result["packages"] = package_match.group(1)

        # Imports
        for match in re.finditer(r"import\s+(static\s+)?([\w.]+);", code):
            result["imports"].append(
                {
                    "name": match.group(2),
                    "lineno": code[: match.start()].count("\n") + 1,
                    "is_static": match.group(1) is not None,
                }
            )

        # Classes - e extrair métodos dentro de cada classe
        for class_match in re.finditer(
            r"(?:@\w+(?:\([^)]*\))?\s*)*(?:public\s+)?(?:abstract\s+)?(?:final\s+)?class\s+(\w+)(?:\s*<[^>]+>)?\s*(?:extends\s+(\w+)(?:\s*<[^>]+>)?)?\s*(?:implements\s+([\w\s,]+))?\s*\{",
            code,
        ):
            class_name = class_match.group(1)
            extends = class_match.group(2)
            implements = class_match.group(3)

            class_start = class_match.end()
            class_end = self._find_matching_brace(code, class_start)

            methods_count = 0
            fields_count = 0

            if class_end:
                class_body = code[class_start:class_end]
                # Contar métodos na classe
                methods_count = len(
                    re.findall(
                        r"(?:public|private|protected)?\s*(?:static\s+)?(?:abstract\s+)?(?:synchronized\s+)?(?:final\s+)?(?:native\s+)?\S+\s+\w+\s*\([^)]*\)\s*(?:throws\s+[^{;]+)?\s*\{",
                        class_body,
                    )
                )
                # Contar campos
                fields_count = len(
                    re.findall(
                        r"(?:public|private|protected)?\s*(?:static\s+)?(?:final\s+)?\S+\s+\w+\s*=",
                        class_body,
                    )
                )

                # Extrair métodos individuais desta classe
                self._extract_methods_from_class_body(
                    class_body, code, class_start, result, class_name
                )

            result["classes"].append(
                {
                    "name": class_name,
                    "lineno": code[: class_match.start()].count("\n") + 1,
                    "extends": extends,
                    "implements": [i.strip() for i in implements.split(",")] if implements else [],
                    "annotations": [],
                    "modifiers": [],
                    "type_parameters": [],
                    "fields_count": fields_count,
                    "methods_count": methods_count,
                }
            )
            result["complexity"] += 1

        # Interfaces
        for match in re.finditer(
            r"(?:@\w+(?:\([^)]*\))?\s*)*(?:public\s+)?interface\s+(\w+)(?:\s*<[^>]+>)?\s*(?:extends\s+([\w\s,]+))?\s*\{",
            code,
        ):
            interface_name = match.group(1)
            extends = match.group(2)

            interface_start = match.end()
            interface_end = self._find_matching_brace(code, interface_start)

            methods_count = 0
            if interface_end:
                interface_body = code[interface_start:interface_end]
                methods_count = len(
                    re.findall(r"\w+\s*\([^)]*\)\s*(?:throws\s+[^{;]+)?\s*;", interface_body)
                )
                self._extract_methods_from_class_body(
                    interface_body, code, interface_start, result, interface_name
                )

            result["interfaces"].append(
                {
                    "name": interface_name,
                    "lineno": code[: match.start()].count("\n") + 1,
                    "extends": [e.strip() for e in extends.split(",")] if extends else [],
                    "annotations": [],
                    "modifiers": [],
                    "methods_count": methods_count,
                }
            )

        # Enums
        for match in re.finditer(
            r"(?:@\w+(?:\([^)]*\))?\s*)*(?:public\s+)?enum\s+(\w+)\s*(?:implements\s+([\w\s,]+))?\s*\{",
            code,
        ):
            enum_name = match.group(1)

            # Extrair constantes do enum
            constants = []
            enum_start = match.end()
            enum_end = self._find_matching_brace(code, enum_start)
            if enum_end:
                enum_body = code[enum_start:enum_end]
                # Extrair constantes do enum - padrão simples: CONST_NAME ou CONST_NAME(valor)
                for const_match in re.finditer(r"(\w+)(?:\s*\([^)]*\))?\s*(?:,|;)", enum_body):
                    const_name = const_match.group(1).strip()
                    if const_name and const_name not in ["implements", "{", "}"]:
                        constants.append(const_name)

            result["enums"].append(
                {
                    "name": enum_name,
                    "lineno": code[: match.start()].count("\n") + 1,
                    "constants": constants,
                    "implements": [],
                    "annotations": [],
                    "modifiers": [],
                }
            )

        # Calcular complexidade do código
        result["complexity"] += self._calculate_complexity_regex(code)

        return result

    def _extract_methods_from_class_body(
        self, class_body: str, full_code: str, class_start: int, result: Dict, class_name: str
    ):
        """Extrai métodos do corpo de uma classe/interface."""
        import re

        # Regex para métodos dentro da classe - mais permissivo
        # Captura métodos mesmo se a chave estiver na próxima linha
        for match in re.finditer(
            r"(?:@\w+(?:\([^)]*\))?\s*)*\s*(public|private|protected)?\s*(?:static\s+)?(?:abstract\s+)?(?:synchronized\s+)?(?:final\s+)?(?:native\s+)?(\S+(?:<[^>]+>)?)\s+(\w+)\s*\(([^)]*)\)(?:\s+throws\s+([\w\s.,]+))?\s*\{",
            class_body,
        ):
            visibility = match.group(1) or ""
            return_type = match.group(2)
            method_name = match.group(3)
            params = match.group(4) or ""
            throws = match.group(5)

            # Filtrar palavras-chave que não são nomes válidos de métodos
            if method_name in [
                "class",
                "interface",
                "enum",
                "implements",
                "extends",
                "new",
                "return",
                "if",
                "else",
                "for",
                "while",
                "switch",
                "case",
                "default",
                "try",
                "catch",
                "finally",
                "import",
                "package",
            ]:
                continue

            # Filtrar se o nome é um tipo/classe, não um método
            if method_name[0].isupper():
                continue

            # Calcular linha correta
            method_pos = class_start + match.start()
            lineno = full_code[:method_pos].count("\n") + 1

            # Processar parâmetros
            param_list = []
            if params.strip():
                for p in params.split(","):
                    p = p.strip()
                    if p and p not in ["..."]:
                        parts = p.split()
                        if len(parts) >= 2 and parts[0] not in ["final", "@"]:
                            param_list.append({"name": parts[-1], "type": parts[0]})
                        elif len(parts) == 1:
                            param_list.append({"name": parts[0], "type": None})

            result["methods"].append(
                {
                    "name": method_name,
                    "lineno": lineno,
                    "return_type": return_type if return_type != "void" else None,
                    "parameters": param_list,
                    "annotations": [],
                    "modifiers": [m for m in [visibility] if m],
                    "throws": [t.strip() for t in throws.split(",")] if throws else [],
                    "is_static": "static" in match.group(0),
                    "is_abstract": "abstract" in match.group(0),
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
        complexity += len(re.findall(r"\bwhile\s*\(", code))
        complexity += len(re.findall(r"\bdo\s*\{", code))
        complexity += len(re.findall(r"\bcatch\s*\(", code))
        complexity += len(re.findall(r"\?", code))
        complexity += len(re.findall(r"&&", code))
        complexity += len(re.findall(r"\|\|", code))
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

    def has_errors(self, filename: str) -> bool:
        """Verifica se arquivo tem erros de parsing."""
        return filename in self._parse_errors

    def get_stats(self) -> Dict[str, int]:
        """Retorna estatísticas do parser."""
        return {
            "parsed_files": len(self._parsed_cache),
            "files_with_errors": len(self._parse_errors),
        }
