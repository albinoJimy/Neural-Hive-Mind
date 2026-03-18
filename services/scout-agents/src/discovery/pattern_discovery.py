"""
PatternDiscovery - Identificação de padrões de design no código.

Responsável por:
- Identificar padrões de design (Repository, Service, Factory, Singleton, etc.)
- Analisar estrutura de classes e métodos
- Calcular frequência e confiança de padrões
- Sugerir aplicação de padrões onde apropriado
"""

import ast
import re
from collections import defaultdict, Counter
from typing import Dict, List, Any, Optional, Set
import structlog

logger = structlog.get_logger()


class PatternDiscovery:
    """Descoberta de padrões de design em código Python."""

    # Padrões pré-configurados com suas características
    KNOWN_PATTERNS = {
        'repository': {
            'keywords': ['repository', 'repo', 'dao'],
            'common_methods': ['find', 'save', 'delete', 'update', 'get', 'list', 'create', 'remove'],
            'naming_suffix': ['Repository', 'Repo', 'DAO']
        },
        'service': {
            'keywords': ['service', 'handler', 'manager'],
            'common_methods': ['create', 'update', 'delete', 'get', 'process', 'handle'],
            'naming_suffix': ['Service', 'Handler', 'Manager']
        },
        'factory': {
            'keywords': ['factory', 'builder', 'creator'],
            'common_methods': ['create', 'make', 'build', 'from_'],
            'naming_suffix': ['Factory', 'Builder', 'Creator']
        },
        'singleton': {
            'keywords': ['instance', 'singleton'],
            'indicators': ['_instance', '__new__', '_lock'],
            'naming_suffix': ['Manager', 'Connection', 'Instance']
        },
        'decorator': {
            'keywords': ['decorator', 'wrapper'],
            'indicators': ['wrapper', '@wraps', 'functools'],
            'structure': ['inner_function', 'wrapper_function']
        }
    }

    def __init__(self):
        """Inicializa o PatternDiscovery."""
        self.patterns_db = dict(self.KNOWN_PATTERNS)
        self._code_samples: Dict[str, str] = {}
        self._analyzed_patterns: Dict[str, List[Dict]] = defaultdict(list)

    def get_known_patterns(self) -> List[str]:
        """Retorna lista de padrões conhecidos."""
        return list(self.patterns_db.keys())

    def identify_patterns(
        self,
        code: str,
        filename: str = "<unknown>"
    ) -> List[Dict[str, Any]]:
        """
        Identifica padrões de design em um código.

        Args:
            code: Código fonte Python
            filename: Nome do arquivo (para contexto)

        Returns:
            Lista de padrões encontrados com confiança
        """
        patterns_found = []

        try:
            tree = ast.parse(code)
        except SyntaxError:
            logger.warning("syntax_error_in_pattern_discovery", filename=filename)
            return patterns_found

        # Analisar cada classe
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                class_patterns = self._analyze_class_for_patterns(node, code, filename)
                patterns_found.extend(class_patterns)

        # Analisar decorators
        decorator_patterns = self._analyze_decorators(code, filename)
        patterns_found.extend(decorator_patterns)

        return patterns_found

    def _analyze_class_for_patterns(
        self,
        class_node: ast.ClassDef,
        code: str,
        filename: str
    ) -> List[Dict[str, Any]]:
        """Analisa uma classe para identificar padrões."""
        patterns = []

        for pattern_name, pattern_config in self.patterns_db.items():
            confidence = self._calculate_pattern_confidence(class_node, pattern_name, pattern_config)

            if confidence >= 0.5:
                patterns.append({
                    'name': pattern_name,
                    'class_name': class_node.name,
                    'filename': filename,
                    'confidence': round(confidence, 2),
                    'methods': [n.name for n in class_node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
                })

        return patterns

    def _calculate_pattern_confidence(
        self,
        class_node: ast.ClassDef,
        pattern_name: str,
        pattern_config: Dict
    ) -> float:
        """Calcula confiança de que a classe implementa o padrão."""
        confidence = 0.0

        # 1. Verificar nome da classe
        class_name_lower = class_node.name.lower()
        for suffix in pattern_config.get('naming_suffix', []):
            if class_node.name.endswith(suffix) or suffix.lower() in class_name_lower:
                confidence += 0.3
                break

        # 2. Verificar keywords no nome
        for keyword in pattern_config.get('keywords', []):
            if keyword in class_name_lower:
                confidence += 0.2
                break

        # 3. Verificar métodos comuns
        methods = [n.name for n in class_node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        common_methods = pattern_config.get('common_methods', [])

        method_matches = 0
        for method in methods:
            for common in common_methods:
                if common in method.lower():
                    method_matches += 1
                    break

        if common_methods:
            method_ratio = min(method_matches / len(common_methods), 1.0)
            confidence += method_ratio * 0.5

        # 4. Verificar indicadores especiais
        for indicator in pattern_config.get('indicators', []):
            # Verificar em atributos da classe
            for node in class_node.body:
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name) and indicator in target.id:
                            confidence += 0.2

        # 5. Verificar __new__ para singleton
        if pattern_name == 'singleton':
            has_new = any(n.name == '__new__' for n in class_node.body if isinstance(n, ast.FunctionDef))
            if has_new:
                confidence += 0.3

        return min(confidence, 1.0)

    def _analyze_decorators(self, code: str, filename: str) -> List[Dict[str, Any]]:
        """Analisa código para identificar padrões decorator."""
        patterns = []

        # Verificar presença de wrapper + inner function
        if 'def wrapper' in code and 'def ' in code:
            # Verificar estrutura típica de decorator
            tree = ast.parse(code)

            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    # Verificar se retorna uma função interna
                    for child in ast.walk(node):
                        if isinstance(child, ast.FunctionDef) and child.name == 'wrapper':
                            patterns.append({
                                'name': 'decorator',
                                'function_name': node.name,
                                'filename': filename,
                                'confidence': 0.85
                            })
                            break

        return patterns

    def analyze_pattern_frequency(
        self,
        files: Dict[str, str],
        pattern_name: str
    ) -> Dict[str, Any]:
        """
        Analisa frequência de um padrão em múltiplos arquivos.

        Args:
            files: Dict {filename: code}
            pattern_name: Nome do padrão para buscar

        Returns:
            Dict com count, locations, e average_confidence
        """
        occurrences = []
        total_confidence = 0.0

        for filename, code in files.items():
            patterns = self.identify_patterns(code, filename)
            matching = [p for p in patterns if p['name'] == pattern_name]

            if matching:
                occurrences.append(filename)
                total_confidence += max(p['confidence'] for p in matching)

        return {
            'pattern': pattern_name,
            'count': len(occurrences),
            'locations': occurrences,
            'average_confidence': round(total_confidence / len(occurrences), 2) if occurrences else 0.0
        }

    def calculate_pattern_confidence(
        self,
        files: Dict[str, str],
        pattern_name: str
    ) -> float:
        """
        Calcula confiança agregada de um padrão no código.

        Args:
            files: Dict {filename: code}
            pattern_name: Nome do padrão

        Returns:
            Float de 0.0 a 1.0 representando confiança
        """
        if not files:
            return 0.0

        frequency = self.analyze_pattern_frequency(files, pattern_name)
        file_ratio = frequency['count'] / len(files)

        # Combinação: razão de arquivos + confiança média
        confidence = (file_ratio * 0.6) + (frequency['average_confidence'] * 0.4)

        return round(confidence, 2)

    def suggest_patterns(
        self,
        code: str,
        filename: str = "<unknown>"
    ) -> List[Dict[str, Any]]:
        """
        Sugere padrões que poderiam ser aplicados ao código.

        Args:
            code: Código fonte
            filename: Nome do arquivo

        Returns:
            Lista de sugestões com padrão e razão
        """
        suggestions = []

        try:
            tree = ast.parse(code)
        except SyntaxError:
            return suggestions

        # Analisar cada classe
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                class_suggestions = self._suggest_for_class(node, filename)
                suggestions.extend(class_suggestions)

        # Analisar funções soltas
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and not self._is_nested_function(tree, node):
                func_suggestions = self._suggest_for_function(node, filename)
                suggestions.extend(func_suggestions)

        return suggestions

    def _suggest_for_class(self, class_node: ast.ClassDef, filename: str) -> List[Dict[str, Any]]:
        """Sugere padrões para uma classe."""
        suggestions = []
        methods = [n.name for n in class_node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]

        # Se tem muitos métodos de dados mas não parece Repository
        data_methods = ['get', 'save', 'delete', 'find', 'query', 'insert', 'update', 'db']
        has_data_access = any(any(keyword in m.lower() for keyword in data_methods) for m in methods)

        class_name_lower = class_node.name.lower()
        if has_data_access and not any(s in class_name_lower for s in ['repo', 'service', 'dao']):
            suggestions.append({
                'pattern': 'Repository',
                'class': class_node.name,
                'reason': 'Classe com métodos de acesso a dados pode beneficiar do padrão Repository',
                'confidence': 0.7
            })

        # Se tem muitas variações de create/build
        create_methods = [m for m in methods if 'create' in m.lower() or 'make' in m.lower() or 'build' in m.lower()]
        if len(create_methods) >= 3 and 'factory' not in class_name_lower:
            suggestions.append({
                'pattern': 'Factory',
                'class': class_node.name,
                'reason': f'{len(create_methods)} métodos de criação identificados; considere o padrão Factory',
                'confidence': 0.65
            })

        return suggestions

    def _suggest_for_function(self, func_node: ast.FunctionDef, filename: str) -> List[Dict[str, Any]]:
        """Sugere padrões para uma função."""
        suggestions = []

        # Função com muitos ifs retornando dicts semelhantes
        # pode sugerir Factory
        if func_node.body:
            return_stmts = list(ast.walk(func_node))
            dict_returns = [n for n in return_stmts if isinstance(n, ast.Return) and isinstance(n.value, ast.Dict)]

            if len(dict_returns) >= 3:
                suggestions.append({
                    'pattern': 'Factory',
                    'function': func_node.name,
                    'reason': 'Função com múltiplas construções de dict similares; considere padrão Factory',
                    'confidence': 0.6
                })

        return suggestions

    def _is_nested_function(self, tree: ast.Module, func_node: ast.FunctionDef) -> bool:
        """Verifica se a função está aninhada em outra."""
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                for child in ast.walk(node):
                    if child is func_node and node is not func_node:
                        return True
        return False

    def add_code_sample(self, filename: str, code: str) -> None:
        """Adiciona amostra de código para análise."""
        self._code_samples[filename] = code

    def extract_class_structure(
        self,
        code: str,
        filename: str = "<unknown>"
    ) -> Dict[str, Any]:
        """
        Extrai estrutura de classes do código.

        Args:
            code: Código fonte
            filename: Nome do arquivo

        Returns:
            Dict com nome, métodos, atributos, decorators
        """
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return {'name': None, 'methods': [], 'attributes': [], 'decorators': []}

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                methods = []
                attributes = []
                decorators = []

                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        method_decorators = [f"@{self._get_decorator_name(d)}" for d in item.decorator_list]
                        methods.append({
                            'name': item.name,
                            'decorators': method_decorators,
                            'args': [a.arg for a in item.args.args if a.arg],
                            'is_async': isinstance(item, ast.AsyncFunctionDef)
                        })

                    elif isinstance(item, ast.Assign):
                        for target in item.targets:
                            if isinstance(target, ast.Name):
                                attributes.append(target.id)

                return {
                    'name': node.name,
                    'methods': methods,
                    'attributes': attributes,
                    'decorators': decorators,
                    'bases': [self._get_name(base) for base in node.bases]
                }

        return {'name': None, 'methods': [], 'attributes': [], 'decorators': []}

    def _get_decorator_name(self, decorator: ast.AST) -> str:
        """Extrai nome de decorator."""
        if isinstance(decorator, ast.Name):
            return decorator.id
        elif isinstance(decorator, ast.Call):
            if isinstance(decorator.func, ast.Name):
                return decorator.func.id
            elif isinstance(decorator.func, ast.Attribute):
                return decorator.func.attr
        elif isinstance(decorator, ast.Attribute):
            return decorator.attr
        return '<decorator>'

    def _get_name(self, node: ast.AST) -> str:
        """Extrai nome de um nó AST."""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return node.attr
        return str(type(node).__name__)

    def detect_class_dependencies(
        self,
        class_name: str
    ) -> List[str]:
        """
        Detecta dependências de uma classe analisando código armazenado.

        Args:
            class_name: Nome da classe

        Returns:
            Lista de classes/dependências encontradas
        """
        dependencies = []

        for filename, code in self._code_samples.items():
            try:
                tree = ast.parse(code)
            except SyntaxError:
                continue

            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef) and node.name == class_name:
                    # Verificar __init__ para injeções
                    for item in node.body:
                        if isinstance(item, ast.FunctionDef) and item.name == '__init__':
                            for arg in item.args.args:
                                if arg.arg and arg.arg != 'self':
                                    dependencies.append(arg.arg)

                    # Verificar atributos de classe
                    for item in node.body:
                        if isinstance(item, ast.Assign):
                            for target in item.targets:
                                if isinstance(target, ast.Name) and 'repo' in target.id.lower():
                                    dependencies.append(target.id)

        return dependencies

    def generate_pattern_report(
        self,
        files: Dict[str, str]
    ) -> Dict[str, Any]:
        """
        Gera relatório de padrões encontrados nos arquivos.

        Args:
            files: Dict {filename: code}

        Returns:
            Dict com resumo de padrões encontrados
        """
        all_patterns = defaultdict(list)
        total_files = len(files)

        for filename, code in files.items():
            patterns = self.identify_patterns(code, filename)
            for pattern in patterns:
                all_patterns[pattern['name']].append({
                    'filename': filename,
                    'class_name': pattern.get('class_name', pattern.get('function_name', 'N/A')),
                    'confidence': pattern['confidence']
                })

        # Resumir por padrão
        pattern_summary = []
        for pattern_name, occurrences in all_patterns.items():
            avg_confidence = sum(o['confidence'] for o in occurrences) / len(occurrences)
            pattern_summary.append({
                'pattern': pattern_name,
                'occurrences': len(occurrences),
                'average_confidence': round(avg_confidence, 2),
                'locations': [o['filename'] for o in occurrences]
            })

        # Ordenar por ocorrências
        pattern_summary.sort(key=lambda x: x['occurrences'], reverse=True)

        return {
            'total_files': total_files,
            'patterns_found': len(all_patterns),
            'pattern_summary': pattern_summary,
            'raw_patterns': dict(all_patterns)
        }

    def export_pattern_graph(
        self,
        files: Dict[str, str]
    ) -> Dict[str, Any]:
        """
        Exporta grafo de padrões para visualização.

        Args:
            files: Dict {filename: code}

        Returns:
            Dict com nodes e edges para grafo
        """
        nodes = []
        edges = []
        pattern_id = 0

        for filename, code in files.items():
            patterns = self.identify_patterns(code, filename)

            for pattern in patterns:
                node_id = f"pattern_{pattern_id}"
                label = f"{pattern['name']}\\n{pattern.get('class_name', '')}"
                nodes.append({
                    'id': node_id,
                    'label': label,
                    'pattern': pattern['name'],
                    'filename': filename,
                    'confidence': pattern['confidence']
                })

                pattern_id += 1

        return {
            'nodes': nodes,
            'edges': edges,
            'total_patterns': pattern_id
        }
