"""
C/C++ AST Parser usando tree-sitter.

Suporta parsing de código C/C++ com fallback regex.
"""

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class CppParser:
    """
    Parser para código C/C++ usando tree-sitter.

    Extrai:
    - Classes
    - Structs
    - Functions
    - Templates
    - Namespaces
    - Includes/Preprocessor directives
    - Macros
    """

    def __init__(self):
        self._ts_language = None
        self._ts_parser = None
        self._init_tree_sitter()

    def _init_tree_sitter(self):
        """Inicializa tree-sitter para C++."""
        try:
            import tree_sitter
            from tree_sitter_languages import get_language

            self._ts_language = get_language("cpp")
            self._ts_parser = tree_sitter.Parser()
            self._ts_parser.set_language(self._ts_language)
            logger.debug("cpp_parser_tree_sitter_loaded")
        except Exception as e:
            logger.warning(f"cpp_parser_init_failed: {str(e)}")
            self._ts_language = None
            self._ts_parser = None

    def parse(self, code: str, filename: str) -> Optional[Dict[str, Any]]:
        """Parse código C/C++ e extrair informações."""
        if not code or not code.strip():
            return self._empty_result()

        if self._ts_parser:
            try:
                return self._parse_with_tree_sitter(code, filename)
            except Exception as e:
                logger.warning(f"tree_sitter_parse_failed: {filename} - {str(e)}")

        return self._parse_with_regex(code, filename)

    def _empty_result(self) -> Dict[str, Any]:
        """Retorna estrutura vazia."""
        return {
            "classes": [],
            "structs": [],
            "functions": [],
            "namespaces": "",
            "imports": [],  # includes
            "macros": [],
            "templates": [],
            "complexity": 0,
        }

    def _parse_with_tree_sitter(self, code: str, filename: str) -> Dict[str, Any]:
        """Parse usando tree-sitter."""
        tree = self._ts_parser.parse(bytes(code, "utf8"))
        result = self._empty_result()

        for node in tree.root_node.children:
            if node.type == "namespace_definition":
                self._extract_namespace(node, code, result)
            elif node.type == "class_specifier":
                cls = self._extract_class(node, code)
                if cls:
                    result["classes"].append(cls)
            elif node.type == "struct_specifier":
                struct = self._extract_struct(node, code)
                if struct:
                    result["structs"].append(struct)
            elif node.type == "function_definition":
                func = self._extract_function(node, code)
                if func:
                    result["functions"].append(func)
            elif node.type == "preproc_include":
                self._extract_include(node, code, result)
            elif node.type == "preproc_def":
                self._extract_macro(node, code, result)
            elif node.type == "template_declaration":
                self._extract_template(node, code, result)

        result["complexity"] = self._calculate_complexity_ts(tree)
        return result

    def _extract_namespace(self, node, code: str, result: Dict):
        """Extrai namespace."""
        name_node = node.child_by_field_name("name")
        if name_node:
            name = code[name_node.start_byte : name_node.end_byte]
            if result["namespaces"]:
                result["namespaces"] += "::" + name
            else:
                result["namespaces"] = name

    def _extract_class(self, node, code: str) -> Optional[Dict]:
        """Extrai classe."""
        name_node = node.child_by_field_name("name")
        if not name_node:
            return None

        return {
            "name": code[name_node.start_byte : name_node.end_byte],
            "lineno": code[: name_node.start_byte].count("\n") + 1,
            "bases": [],
            "template_parameters": [],
        }

    def _extract_struct(self, node, code: str) -> Optional[Dict]:
        """Extrai struct."""
        name_node = node.child_by_field_name("name")
        if not name_node:
            return None

        return {
            "name": code[name_node.start_byte : name_node.end_byte],
            "lineno": code[: name_node.start_byte].count("\n") + 1,
        }

    def _extract_function(self, node, code: str) -> Optional[Dict]:
        """Extrai função."""
        name_node = node.child_by_field_name("declarator")
        if not name_node:
            return None

        # Encontrar o nome da função
        func_name = ""
        for child in name_node.children:
            if child.type == "identifier":
                func_name = code[child.start_byte : child.end_byte]
                break

        return {
            "name": func_name,
            "lineno": code[: node.start_byte].count("\n") + 1,
            "return_type": "",
            "parameters": [],
        }

    def _extract_include(self, node, code: str, result: Dict):
        """Extrai include."""
        path_node = node.child_by_field_name("path")
        if path_node:
            path = code[path_node.start_byte : path_node.end_byte].strip('<>"')
            result["imports"].append(
                {"name": path, "lineno": code[: node.start_byte].count("\n") + 1}
            )

    def _extract_macro(self, node, code: str, result: Dict):
        """Extrai macro define."""
        name_node = node.child_by_field_name("name")
        if name_node:
            result["macros"].append(
                {
                    "name": code[name_node.start_byte : name_node.end_byte],
                    "lineno": code[: node.start_byte].count("\n") + 1,
                }
            )

    def _extract_template(self, node, code: str, result: Dict):
        """Extrai template declaration."""
        result["templates"].append({"lineno": code[: node.start_byte].count("\n") + 1})

    def _calculate_complexity_ts(self, tree) -> int:
        """Calcula complexidade."""
        complexity = 1
        for node in tree.root_node.descendants_of_type(
            {
                "if_statement",
                "while_statement",
                "for_statement",
                "do_statement",
                "switch_statement",
                "case_statement",
                "conditional_expression",
                "catch_clause",
            }
        ):
            complexity += 1
        return complexity

    def _parse_with_regex(self, code: str, filename: str) -> Dict[str, Any]:
        """Parse baseado em regex (fallback)."""
        import re

        result = self._empty_result()

        # Namespaces
        for ns_match in re.finditer(r"namespace\s+(\w+)", code):
            name = ns_match.group(1)
            if result["namespaces"]:
                result["namespaces"] += "::" + name
            else:
                result["namespaces"] = name

        # Includes
        for inc_match in re.finditer(r'#include\s+[<"]([^>"]+)[>"]', code):
            result["imports"].append(
                {"name": inc_match.group(1), "lineno": code[: inc_match.start()].count("\n") + 1}
            )

        # Macros
        for macro_match in re.finditer(r"#define\s+(\w+)", code):
            result["macros"].append(
                {
                    "name": macro_match.group(1),
                    "lineno": code[: macro_match.start()].count("\n") + 1,
                }
            )

        # Classes
        for class_match in re.finditer(
            r"(?:template\s*<[^>]*>\s*)?class\s+(\w+)(?:\s*:\s*(?:public|protected|private)\s+\w+(?:<[^>]*>)?)?(?:\s*,\s*(?:public|protected|private)\s+\w+)*?\s*\{",
            code,
        ):
            class_name = class_match.group(1)
            result["classes"].append(
                {
                    "name": class_name,
                    "lineno": code[: class_match.start()].count("\n") + 1,
                    "bases": [],
                    "template_parameters": [],
                }
            )

        # Structs
        for struct_match in re.finditer(
            r"(?:template\s*<[^>]*>\s*)?struct\s+(\w+)(?:\s*:\s*(?:public|private|protected)\s+\w+(?:<[^>]*>)?)?(?:\s*,\s*(?:public|protected|private)\s+\w+)*?\s*\{",
            code,
        ):
            struct_name = struct_match.group(1)
            result["structs"].append(
                {"name": struct_name, "lineno": code[: struct_match.start()].count("\n") + 1}
            )

        # Funções
        for func_match in re.finditer(
            r"(?:template\s*<[^>]*>\s*)?(?:\w+(?:\s*\*|\s*&)?\s+)+(\w+)\s*\([^)]*\)\s*(?:const\s*)?(?:->\s*[^{]+)?\s*\{",
            code,
        ):
            func_name = func_match.group(1)
            # Filtrar keywords
            if func_name not in [
                "if",
                "else",
                "for",
                "while",
                "switch",
                "return",
                "class",
                "struct",
            ]:
                result["functions"].append(
                    {
                        "name": func_name,
                        "lineno": code[: func_match.start()].count("\n") + 1,
                        "return_type": "",
                        "parameters": [],
                    }
                )

        # Templates
        for template_match in re.finditer(r"template\s*<[^>]*>", code):
            result["templates"].append({"lineno": code[: template_match.start()].count("\n") + 1})

        result["complexity"] = self._calculate_complexity_regex(code)
        return result

    def _calculate_complexity_regex(self, code: str) -> int:
        """Calcula complexidade via regex."""
        import re

        complexity = 1
        complexity += len(re.findall(r"\bif\s*\(", code))
        complexity += len(re.findall(r"\bfor\s*\(", code))
        complexity += len(re.findall(r"\bwhile\s*\(", code))
        complexity += len(re.findall(r"\bdo\s*\{", code))
        complexity += len(re.findall(r"\bswitch\s*\(", code))
        complexity += len(re.findall(r"\bcase\s+", code))
        complexity += len(re.findall(r"\?", code))
        complexity += len(re.findall(r"&&", code))
        complexity += len(re.findall(r"\|\|", code))
        complexity += len(re.findall(r"\bcatch\s*\(", code))
        return complexity
