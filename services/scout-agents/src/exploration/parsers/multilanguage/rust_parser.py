"""
Rust AST Parser usando tree-sitter.

Suporta parsing de código Rust com fallback regex.
"""
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class RustParser:
    """
    Parser para código Rust usando tree-sitter.

    Extrai:
    - Structs
    - Enums
    - Traits
    - Impl blocks
    - Functions
    - Macros
    - Modules
    - Use declarations
    """

    def __init__(self):
        self._ts_language = None
        self._ts_parser = None
        self._init_tree_sitter()

    def _init_tree_sitter(self):
        """Inicializa tree-sitter para Rust."""
        try:
            import tree_sitter
            from tree_sitter_languages import get_language

            self._ts_language = get_language('rust')
            self._ts_parser = tree_sitter.Parser()
            self._ts_parser.set_language(self._ts_language)
            logger.debug("rust_parser_tree_sitter_loaded")
        except Exception as e:
            logger.warning(f"rust_parser_init_failed: {str(e)}")
            self._ts_language = None
            self._ts_parser = None

    def parse(self, code: str, filename: str) -> Optional[Dict[str, Any]]:
        """Parse código Rust e extrair informações."""
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
            'structs': [],
            'enums': [],
            'traits': [],
            'impls': [],
            'functions': [],
            'macros': [],
            'modules': '',
            'imports': [],  # use declarations
            'complexity': 0
        }

    def _parse_with_tree_sitter(self, code: str, filename: str) -> Dict[str, Any]:
        """Parse usando tree-sitter."""
        tree = self._ts_parser.parse(bytes(code, 'utf8'))
        result = self._empty_result()

        for node in tree.root_node.children:
            if node.type == 'struct_item':
                struct = self._extract_struct(node, code)
                if struct:
                    result['structs'].append(struct)
            elif node.type == 'enum_item':
                enum = self._extract_enum(node, code)
                if enum:
                    result['enums'].append(enum)
            elif node.type == 'trait_item':
                trait = self._extract_trait(node, code)
                if trait:
                    result['traits'].append(trait)
            elif node.type == 'impl_item':
                impl_block = self._extract_impl(node, code)
                if impl_block:
                    result['impls'].append(impl_block)
            elif node.type == 'function_item':
                func = self._extract_function(node, code)
                if func:
                    result['functions'].append(func)
            elif node.type == 'macro_invocation':
                result['macros'].append({
                    'lineno': code[:node.start_byte].count('\n') + 1
                })
            elif node.type == 'mod_item':
                name_node = node.child_by_field_name('name')
                if name_node:
                    result['modules'] = code[name_node.start_byte:name_node.end_byte]
            elif node.type == 'use_declaration':
                self._extract_use(node, code, result)

        result['complexity'] = self._calculate_complexity_ts(tree)
        return result

    def _extract_struct(self, node, code: str) -> Optional[Dict]:
        """Extrai struct."""
        name_node = node.child_by_field_name('name')
        if not name_node:
            return None

        return {
            'name': code[name_node.start_byte:name_node.end_byte],
            'lineno': code[:name_node.start_byte].count('\n') + 1,
            'fields': []
        }

    def _extract_enum(self, node, code: str) -> Optional[Dict]:
        """Extrai enum."""
        name_node = node.child_by_field_name('name')
        if not name_node:
            return None

        return {
            'name': code[name_node.start_byte:name_node.end_byte],
            'lineno': code[:name_node.start_byte].count('\n') + 1,
            'variants': []
        }

    def _extract_trait(self, node, code: str) -> Optional[Dict]:
        """Extrai trait."""
        name_node = node.child_by_field_name('name')
        if not name_node:
            return None

        return {
            'name': code[name_node.start_byte:name_node.end_byte],
            'lineno': code[:name_node.start_byte].count('\n') + 1,
            'methods': []
        }

    def _extract_impl(self, node, code: str) -> Optional[Dict]:
        """Extrai impl block."""
        type_node = node.child_by_field_name('type')
        trait_node = node.child_by_field_name('trait')

        impl_info = {
            'lineno': code[:node.start_byte].count('\n') + 1,
            'type': '',
            'trait': ''
        }

        if type_node:
            impl_info['type'] = code[type_node.start_byte:type_node.end_byte]
        if trait_node:
            impl_info['trait'] = code[trait_node.start_byte:trait_node.end_byte]

        return impl_info

    def _extract_function(self, node, code: str) -> Optional[Dict]:
        """Extrai função."""
        name_node = node.child_by_field_name('name')
        if not name_node:
            return None

        return {
            'name': code[name_node.start_byte:name_node.end_byte],
            'lineno': code[:name_node.start_byte].count('\n') + 1,
            'parameters': [],
            'return_type': '',
            'is_async': 'async' in code[node.start_byte:name_node.start_byte]
        }

    def _extract_use(self, node, code: str, result: Dict):
        """Extrai use declaration."""
        # Simplificado - apenas captura que existe import
        result['imports'].append({
            'lineno': code[:node.start_byte].count('\n') + 1
        })

    def _calculate_complexity_ts(self, tree) -> int:
        """Calcula complexidade."""
        complexity = 1
        for node in tree.root_node.descendants_of_type({
            'if_expression', 'while_expression', 'for_expression',
            'loop_expression', 'match_expression', 'match_arm',
            'if_let_expression', 'while_let_expression'
        }):
            complexity += 1
        return complexity

    def _parse_with_regex(self, code: str, filename: str) -> Dict[str, Any]:
        """Parse baseado em regex (fallback)."""
        import re

        result = self._empty_result()

        # Modules
        mod_match = re.search(r'mod\s+(\w+)', code)
        if mod_match:
            result['modules'] = mod_match.group(1)

        # Structs
        for struct_match in re.finditer(
            r'(?:pub\s+)?struct\s+(\w+)(?:\s*<[^>]*>)?\s*\{',
            code
        ):
            result['structs'].append({
                'name': struct_match.group(1),
                'lineno': code[:struct_match.start()].count('\n') + 1,
                'fields': []
            })

        # Enums
        for enum_match in re.finditer(
            r'(?:pub\s+)?enum\s+(\w+)(?:\s*<[^>]*>)?\s*\{',
            code
        ):
            result['enums'].append({
                'name': enum_match.group(1),
                'lineno': code[:enum_match.start()].count('\n') + 1,
                'variants': []
            })

        # Traits
        for trait_match in re.finditer(
            r'(?:pub\s+)?trait\s+(\w+)(?:\s*<[^>]*>)?\s*\{',
            code
        ):
            result['traits'].append({
                'name': trait_match.group(1),
                'lineno': code[:trait_match.start()].count('\n') + 1,
                'methods': []
            })

        # Impl blocks
        for impl_match in re.finditer(
            r'impl\s+(?:<[^>]*>)?(\w+)(?:\s*<[^>]*>)?\s*(?:for\s+(\w+))?\s*\{',
            code
        ):
            impl_info = {
                'lineno': code[:impl_match.start()].count('\n') + 1,
                'type': impl_match.group(1),
                'trait': ''
            }
            if impl_match.group(2):
                impl_info['type'] = impl_match.group(2)
                impl_info['trait'] = impl_match.group(1)
            result['impls'].append(impl_info)

        # Funções
        for func_match in re.finditer(
            r'(?:pub\s*)?(?:async\s*)?(?:unsafe\s*)?fn\s+(\w+)\s*\(',
            code
        ):
            func_name = func_match.group(1)
            result['functions'].append({
                'name': func_name,
                'lineno': code[:func_match.start()].count('\n') + 1,
                'parameters': [],
                'return_type': '',
                'is_async': 'async' in func_match.group(0)
            })

        # Macros
        for macro_match in re.finditer(r'(\w+)!', code):
            result['macros'].append({
                'lineno': code[:macro_match.start()].count('\n') + 1
            })

        # Attributes (#[])
        for attr_match in re.finditer(r'#\[\w+', code):
            result['macros'].append({
                'lineno': code[:attr_match.start()].count('\n') + 1
            })

        result['complexity'] = self._calculate_complexity_regex(code)
        return result

    def _calculate_complexity_regex(self, code: str) -> int:
        """Calcula complexidade via regex."""
        import re
        complexity = 1
        complexity += len(re.findall(r'\bif\s+', code))
        complexity += len(re.findall(r'\belse\s+', code))
        complexity += len(re.findall(r'\bmatch\s+', code))
        complexity += len(re.findall(r'\bloop\s*', code))
        complexity += len(re.findall(r'\bwhile\s+', code))
        complexity += len(re.findall(r'\bfor\s+', code))
        complexity += len(re.findall(r'&&', code))
        complexity += len(re.findall(r'\|\|', code))
        return complexity
