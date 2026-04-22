"""
TypeScript Parser - Análise de código TypeScript.

Usa esprima para parsing de JavaScript/TypeScript.
Versão simplificada com regex patterns mais diretos.
"""

import re
from typing import Any, Optional

import structlog

try:
    import esprima

    ESPRIMA_AVAILABLE = True
except ImportError:
    ESPRIMA_AVAILABLE = False

logger = structlog.get_logger()


class TypeScriptParser:
    """Parser para código TypeScript."""

    def __init__(self):
        """Inicializa o TypeScriptParser."""
        self._parsed_cache: dict[str, dict] = {}
        self._parse_errors: set = set()

    def parse(self, code: str, filename: str) -> Optional[dict[str, Any]]:
        """
        Faz parsing de código TypeScript.

        Args:
            code: Código fonte TypeScript
            filename: Nome do arquivo

        Returns:
            Dict com classes, funções, interfaces, etc.
        """
        if not code or not code.strip():
            return {
                "classes": [],
                "functions": [],
                "interfaces": [],
                "enums": [],
                "type_aliases": [],
                "namespaces": [],
                "imports": [],
                "decorators": [],
                "complexity": 1,
                "has_errors": False,
                "keys": [],
            }

        try:
            # Usar esprima para parsing
            if ESPRIMA_AVAILABLE:
                return self._parse_with_esprima(code, filename)
            else:
                # Fallback para parsing baseado em regex
                logger.warning(
                    "esprima_not_available",
                    filename=filename,
                    message="Using regex-based fallback parser",
                )
                return self._parse_with_regex(code, filename)

        except Exception as e:
            logger.error("typescript_parse_error", filename=filename, error=str(e))
            self._parse_errors.add(filename)
            return None

    def _parse_with_esprima(self, code: str, filename: str) -> dict[str, Any]:
        """Parse usando esprima (JavaScript AST parser)."""
        try:
            tree = esprima.parseScript(code, options={"tolerant": True, "jsx": True})
            result = self._extract_from_esprima_tree(tree, code)
            result["has_errors"] = False
            return result
        except Exception:
            return self._parse_with_regex(code, filename)

    def _extract_from_esprima_tree(self, tree: dict, code: str) -> dict[str, Any]:
        """Extrai informações da AST do esprima."""
        result = {
            "classes": [],
            "functions": [],
            "interfaces": [],
            "enums": [],
            "type_aliases": [],
            "namespaces": [],
            "imports": [],
            "decorators": [],
            "complexity": 1,
            "keys": [],
        }

        def traverse(node):
            if not isinstance(node, dict):
                return

            node_type = node.get("type", "")

            if node_type == "ClassDeclaration":
                name = node.get("id", {}).get("name", "<anonymous>")
                result["classes"].append(
                    {
                        "name": name,
                        "lineno": node.get("loc", {}).get("start", {}).get("line"),
                        "decorators": [],
                        "methods_count": len(node.get("body", {}).get("body", [])),
                        "extends": None,
                        "docstring": None,
                    }
                )
                result["complexity"] += 1

            elif node_type in ("FunctionDeclaration", "FunctionExpression"):
                name = node.get("id", {}).get("name", "<anonymous>")
                result["functions"].append(
                    {
                        "name": name,
                        "lineno": node.get("loc", {}).get("start", {}).get("line"),
                        "decorators": [],
                        "args_count": len(node.get("params", [])),
                        "is_async": node.get("async", False),
                        "is_arrow": False,
                    }
                )
                result["complexity"] += 1

            elif node_type == "ArrowFunctionExpression":
                result["functions"].append(
                    {
                        "name": "<arrow>",
                        "lineno": node.get("loc", {}).get("start", {}).get("line"),
                        "decorators": [],
                        "args_count": len(node.get("params", [])),
                        "is_async": node.get("async", False),
                        "is_arrow": True,
                    }
                )

            elif node_type == "ImportDeclaration":
                source = node.get("source", {}).get("value", "")
                specifiers = node.get("specifiers", [])
                names = [s.get("local", {}).get("name", "") for s in specifiers]
                result["imports"].append({"source": source, "names": names})

            elif node_type in ("IfStatement", "WhileStatement", "ForStatement"):
                result["complexity"] += 1

            for key, value in node.items():
                if isinstance(value, dict):
                    traverse(value)
                elif isinstance(value, list):
                    for item in value:
                        if isinstance(item, dict):
                            traverse(item)

        traverse(tree)
        return result

    def _parse_with_regex(self, code: str, filename: str) -> dict[str, Any]:
        """Parse baseado em regex."""
        # Detectar erros de sintaxe óbvios
        if self._has_syntax_errors(code):
            return {
                "classes": [],
                "functions": [],
                "interfaces": [],
                "enums": [],
                "type_aliases": [],
                "namespaces": [],
                "imports": [],
                "decorators": [],
                "complexity": 1,
                "has_errors": True,
                "keys": [],
            }

        result = {
            "classes": self._extract_classes(code),
            "functions": self._extract_functions(code),
            "interfaces": self._extract_interfaces(code),
            "enums": self._extract_enums(code),
            "type_aliases": self._extract_type_aliases(code),
            "namespaces": self._extract_namespaces(code),
            "imports": self._extract_imports(code),
            "decorators": [],
            "complexity": self._calculate_complexity(code),
            "has_errors": False,
            "keys": [],
        }

        return result

    def _has_syntax_errors(self, code: str) -> bool:
        """Detecta erros de sintaxe óbvios."""
        # Verificar balanceamento básico
        if code.count("{") != code.count("}"):
            return True
        if code.count("(") != code.count(")"):
            return True

        # Detectar padrões que indicam erro
        if re.search(r"=>\s*function", code):
            return True

        # Detectar parêntese não fechado antes de abrir chaves em métodos/classe
        # Ex: constructor(name { - parêntese sem fechamento antes de abrir chaves
        # Mas não arrow functions ou template literals
        # Remover arrow functions primeiro
        code_without_arrows = re.sub(
            r"\w+\s*(?::\s*[^=]+)?\s*=\s*(?:async\s+)?(?:\([^)]*\)|\w+)\s*=>", "", code
        )

        # Remover template literals (podem conter qualquer caractere incluindo { e })
        code_without_templates = re.sub(r"`[^`]*`", "``", code_without_arrows)

        # Agora verificar por erros
        if re.search(r"(?:function|constructor)\s*\([^\)]*\{", code_without_templates):
            return True

        return False

    def _extract_classes(self, code: str) -> list[dict]:
        """Extrai classes."""
        classes = []

        # Padrão 1: Classes com decorators
        # Padrão 2: Classes sem decorators
        pattern = r"(@\w+(?:\([^)]*\))?\s*(?:\n\s*)*)*class\s+(\w+)(?:\s*<[^>{}]*(?:\{[^}]*\}[^>{}]*)*>)?\s*(?:extends\s+(\w+)(?:\s*<[^>]+>)?)?\s*\{"

        for match in re.finditer(pattern, code, re.MULTILINE):
            decorators_str = match.group(1) or ""
            name = match.group(2)
            extends = match.group(3)
            lineno = code[: match.start()].count("\n") + 1

            # Extrair decorators da string capturada
            decorators = []
            for dec_match in re.finditer(r"@(\w+)", decorators_str):
                decorators.append(f"@{dec_match.group(1)}")

            # Contar métodos
            class_start = match.end()
            class_end = self._find_matching_brace(code, class_start)
            methods_count = 0
            if class_end:
                class_body = code[class_start:class_end]
                methods_count = len(re.findall(r"\n\s*\w+\s*\(", class_body))

            classes.append(
                {
                    "name": name,
                    "lineno": lineno,
                    "decorators": decorators,
                    "methods_count": methods_count,
                    "extends": extends,
                    "docstring": None,
                }
            )

        return classes

    def _extract_functions(self, code: str) -> list[dict]:
        """Extrai funções."""
        functions = []

        # Funções declaradas: function name()
        for match in re.finditer(r"(?:async\s+)?function\s+(\w+)\s*\(([^)]*)\)", code):
            name = match.group(1)
            args_str = match.group(2) or ""
            args_count = len([a for a in args_str.split(",") if a.strip()])
            lineno = code[: match.start()].count("\n") + 1
            is_async = match.group(0).startswith("async")

            functions.append(
                {
                    "name": name,
                    "lineno": lineno,
                    "decorators": [],
                    "args_count": args_count,
                    "is_async": is_async,
                    "is_arrow": False,
                }
            )

        # Arrow functions: const name = (args): ReturnType => ...
        # Padrão que captura type annotations
        arrow_pattern = r"(?:const|let|var)\s+(\w+)\s*(?::\s*[^=]+)?\s*=\s*(?:async\s+)?\(([^)]*)\)(?:\s*:\s*[^=]+)?\s*=>"

        for match in re.finditer(arrow_pattern, code):
            name = match.group(1)
            args_str = match.group(2) or ""
            args_count = len([a for a in args_str.split(",") if a.strip()])
            lineno = code[: match.start()].count("\n") + 1

            # Verificar async
            before_match = code[max(0, match.start() - 30) : match.start()]
            is_async = "async" in before_match

            # Evitar duplicar
            if not any(f["name"] == name for f in functions):
                functions.append(
                    {
                        "name": name,
                        "lineno": lineno,
                        "decorators": [],
                        "args_count": args_count,
                        "is_async": is_async,
                        "is_arrow": True,
                    }
                )

        # Arrow functions com single param sem parênteses: const name = param =>
        # Ex: const double = x => x * 2;
        # Excluir se o param parece um tipo
        single_param_pattern = r"(?:const|let|var)\s+(\w+)\s*(?::\s*[^=]+)?\s*=\s*(\w+)\s*=>"

        for match in re.finditer(single_param_pattern, code):
            name = match.group(1)
            param = match.group(2)

            # Ignorar se o parâmetro é uma palavra-chave de tipo TypeScript
            if param in [
                "string",
                "number",
                "boolean",
                "void",
                "any",
                "never",
                "unknown",
                "null",
                "undefined",
                "object",
                "Promise",
                "Array",
                "Map",
                "Set",
                "Function",
                "Type",
            ]:
                continue

            lineno = code[: match.start()].count("\n") + 1

            # Evitar duplicar
            if not any(f["name"] == name for f in functions):
                functions.append(
                    {
                        "name": name,
                        "lineno": lineno,
                        "decorators": [],
                        "args_count": 1,
                        "is_async": False,
                        "is_arrow": True,
                    }
                )

        return functions

    def _extract_interfaces(self, code: str) -> list[dict]:
        """Extrai interfaces."""
        interfaces = []
        pattern = r"interface\s+(\w+)(?:\s*<[^>]+>)?(?:\s+extends\s+([^{]+))?\s*\{"

        for match in re.finditer(pattern, code):
            name = match.group(1)
            extends_str = match.group(2) or ""
            lineno = code[: match.start()].count("\n") + 1

            interfaces.append(
                {
                    "name": name,
                    "lineno": lineno,
                    "extends": [e.strip() for e in extends_str.split(",")] if extends_str else [],
                }
            )

        return interfaces

    def _extract_enums(self, code: str) -> list[dict]:
        """Extrai enums."""
        enums = []
        pattern = r"(?:const\s+)?enum\s+(\w+)\s*\{"

        for match in re.finditer(pattern, code):
            enums.append({"name": match.group(1), "lineno": code[: match.start()].count("\n") + 1})

        return enums

    def _extract_type_aliases(self, code: str) -> list[dict]:
        """Extrai type aliases."""
        aliases = []
        pattern = r"type\s+(\w+)\s*="

        for match in re.finditer(pattern, code):
            aliases.append(
                {"name": match.group(1), "lineno": code[: match.start()].count("\n") + 1}
            )

        return aliases

    def _extract_namespaces(self, code: str) -> list[dict]:
        """Extrai namespaces."""
        namespaces = []
        pattern = r"(?:export\s+)?namespace\s+(\w+(?:\.\w+)*)\s*\{"

        for match in re.finditer(pattern, code):
            namespaces.append(
                {"name": match.group(1), "lineno": code[: match.start()].count("\n") + 1}
            )

        return namespaces

    def _extract_imports(self, code: str) -> list[dict]:
        """Extrai imports."""
        imports = []

        # ES6 imports: import { ... } from '...'
        for match in re.finditer(
            r"import\s+(?:(\*)\s+as\s+(\w+)|\{([^}]+)\}|(\w+))\s+from\s+['\"]([^'\"]+)['\"]", code
        ):
            source = match.group(5)
            names = []
            if match.group(1):  # wildcard
                names.append(match.group(2))
            elif match.group(3):  # named
                names.extend([n.strip() for n in match.group(3).split(",")])
            elif match.group(4):  # default
                names.append(match.group(4))

            imports.append({"source": source, "names": names})

        # Bare imports: import '...'
        for match in re.finditer(r"import\s+['\"]([^'\"]+)['\"]", code):
            imports.append({"source": match.group(1), "names": []})

        return imports

    def _calculate_complexity(self, code: str) -> int:
        """Calcula complexidade ciclomática."""
        complexity = 1
        complexity += len(re.findall(r"\bif\s*\(", code))
        complexity += len(re.findall(r"\belse\s+if\s*\(", code))
        complexity += len(re.findall(r"\bfor\s*\(", code))
        complexity += len(re.findall(r"\bwhile\s*\(", code))
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
