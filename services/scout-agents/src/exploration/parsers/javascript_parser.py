"""
JavaScript Parser - Análise de código JavaScript.

Suporta ES6+ e CommonJS.
"""

import re
from typing import Any, Optional

import structlog

from .typescript_parser import TypeScriptParser

logger = structlog.get_logger()


class JavaScriptParser:
    """Parser para código JavaScript."""

    def __init__(self):
        """Inicializa o JavaScriptParser."""
        self._ts_parser = TypeScriptParser()
        self._parsed_cache: dict[str, dict] = {}
        self._parse_errors: set = set()

    def parse(self, code: str, filename: str) -> Optional[dict[str, Any]]:
        """
        Faz parsing de código JavaScript.

        Args:
            code: Código fonte JavaScript
            filename: Nome do arquivo

        Returns:
            Dict com classes, funções, imports, etc.
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
                "commonjs_imports": [],
                "decorators": [],
                "complexity": 1,
                "has_errors": False,
                "keys": [],
            }

        try:
            # Usar o parser TypeScript (JavaScript é um subconjunto)
            result = self._ts_parser.parse(code, filename)

            if result:
                # Adicionar detecção específica para JavaScript
                result["commonjs_imports"] = self._extract_commonjs_requires(code)

                # Detectar prototype-based inheritance
                result["prototype_chains"] = self._detect_prototype_chains(code)

                # Detectar classes extendidas (sintaxe JS)
                self._enhance_js_class_info(result, code)

                # Preservar has_errors do TypeScript parser
                if "has_errors" not in result:
                    result["has_errors"] = False
                return result
            else:
                return None

        except Exception as e:
            logger.error("javascript_parse_error", filename=filename, error=str(e))
            self._parse_errors.add(filename)
            return None

    def _extract_commonjs_requires(self, code: str) -> list[dict]:
        """Extrai imports CommonJS (require)."""
        imports = []

        # Pattern: require('module') ou require("./module")
        pattern = r"""
            (?:const|let|var)\s+
            (?:(?P<destruct>\{[^}]+\})|(?P<name>[A-Za-z_$][\w$]*))
            \s*=\s*
            require\(
                ['"](?P<source>[^'"]+)['"]
            \)
        """

        for match in re.finditer(pattern, code, re.VERBOSE):
            source = match.group("source")
            name = match.group("name") or match.group("destruct")

            imports.append({"source": source, "name": name, "type": "commonjs"})

        # Imports sem nome (bare require)
        bare_pattern = r"require\(['\"]([^'\"]+)['\"]\)"
        for match in re.finditer(bare_pattern, code):
            imports.append({"source": match.group(1), "name": None, "type": "commonjs"})

        return imports

    def _detect_prototype_chains(self, code: str) -> list[dict]:
        """Detecta herança baseada em prototype."""
        chains = []

        # Pattern: ClassName.prototype.methodName = function
        pattern = r"""
            ([A-Za-z_$][\w$]*)\s*\.\s*prototype\s*\.\s*
            ([A-Za-z_$][\w$]*)\s*=\s*(?:function\s+)?[A-Za-z_$]?
        """

        for match in re.finditer(pattern, code, re.VERBOSE):
            class_name = match.group(1)
            method_name = match.group(2)
            lineno = code[: match.start()].count("\n") + 1

            # Encontrar ou criar entrada para a classe
            existing = next((c for c in chains if c["class"] == class_name), None)
            if existing:
                existing["methods"].append(method_name)
                existing["method_count"] += 1
            else:
                chains.append(
                    {
                        "class": class_name,
                        "methods": [method_name],
                        "method_count": 1,
                        "lineno": lineno,
                    }
                )

        # Detectar Object.create para herança
        inherit_pattern = r"([A-Za-z_$][\w$]*)\s*\.\s*prototype\s*=\s*Object\.create\(([A-Za-z_$][\w$]*)\.prototype\)"
        for match in re.finditer(inherit_pattern, code):
            child = match.group(1)
            parent = match.group(2)
            chains.append(
                {
                    "class": child,
                    "inherits": parent,
                    "inheritance_type": "prototype",
                    "methods": [],
                    "method_count": 0,
                }
            )

        return chains

    def _enhance_js_class_info(self, result: dict, code: str):
        """Adiciona informações específicas de classes JavaScript."""
        # Adicionar métodos detectados via prototype
        prototype_methods = self._get_prototype_methods(code)
        for cls in result.get("classes", []):
            cls_name = cls["name"]
            if cls_name in prototype_methods:
                cls["prototype_methods"] = prototype_methods[cls_name]

    def _get_prototype_methods(self, code: str) -> dict[str, list[str]]:
        """Mapeia classes para seus métodos prototype."""
        methods = {}

        pattern = r"([A-Za-z_$][\w$]*)\.prototype\.([A-Za-z_$][\w$]*)\s*="
        for match in re.finditer(pattern, code):
            class_name = match.group(1)
            method_name = match.group(2)

            if class_name not in methods:
                methods[class_name] = []
            methods[class_name].append(method_name)

        return methods

    def has_errors(self, filename: str) -> bool:
        """Verifica se arquivo tem erros de parsing."""
        return filename in self._parse_errors

    def get_stats(self) -> dict[str, int]:
        """Retorna estatísticas do parser."""
        return {
            "parsed_files": len(self._parsed_cache),
            "files_with_errors": len(self._parse_errors),
        }
