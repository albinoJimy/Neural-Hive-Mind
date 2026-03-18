"""
CodebaseExplorer - Análise estática de código para Scout Agents.

Responsável por:
- Parsing de arquivos Python usando AST
- Extração de dependências (imports)
- Construção de grafo de dependências
- Cálculo de complexidade ciclomática
"""

import ast
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Set
import structlog

logger = structlog.get_logger()


class CodebaseExplorer:
    """Explorador de codebase para análise estática."""

    def __init__(
        self,
        root_path: str,
        file_extensions: Optional[List[str]] = None
    ):
        """
        Inicializa o CodebaseExplorer.

        Args:
            root_path: Caminho raiz do codebase
            file_extensions: Extensões para analisar (default: .py, .ts, .yaml)
        """
        self.root_path = Path(root_path)
        self.file_extensions = file_extensions or ['.py', '.ts', '.yaml']

        # Cache de arquivos analisados
        self._parsed_files: Dict[str, Dict] = {}
        self._parse_errors: Set[str] = set()

        # Métricas agregadas
        self.metrics = {
            'files_analyzed': 0,
            'total_functions': 0,
            'total_classes': 0,
            'total_imports': 0
        }

    def parse_python_ast(
        self,
        code: str,
        filename: str
    ) -> Optional[ast.Module]:
        """
        Faz parsing de código Python para AST.

        Args:
            code: Código fonte Python
            filename: Nome do arquivo (para erros)

        Returns:
            AST Module ou None em caso de erro
        """
        try:
            tree = ast.parse(code)
            self._parsed_files[filename] = {
                'parsed_at': datetime.utcnow(),
                'has_errors': False
            }
            return tree
        except SyntaxError as e:
            logger.warning(
                "python_syntax_error",
                filename=filename,
                error=str(e)
            )
            self._parse_errors.add(filename)
            if filename in self._parsed_files:
                self._parsed_files[filename]['has_errors'] = True
            return None
        except Exception as e:
            logger.error(
                "parse_error",
                filename=filename,
                error=str(e)
            )
            return None

    def extract_functions(
        self,
        tree: ast.Module
    ) -> List[Dict[str, Any]]:
        """
        Extrai informações de funções da AST.

        Args:
            tree: AST Module

        Returns:
            Lista de dicts com info das funções
        """
        functions = []

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                func_info = {
                    'name': node.name,
                    'lineno': node.lineno,
                    'decorators': self._extract_decorators(node),
                    'args_count': len(node.args.args),
                    'is_async': False,
                    'docstring': ast.get_docstring(node)
                }
                functions.append(func_info)
            elif isinstance(node, ast.AsyncFunctionDef):
                func_info = {
                    'name': node.name,
                    'lineno': node.lineno,
                    'decorators': self._extract_decorators(node),
                    'args_count': len(node.args.args),
                    'is_async': True,
                    'docstring': ast.get_docstring(node)
                }
                functions.append(func_info)

        self.metrics['total_functions'] += len(functions)
        return functions

    def extract_classes(
        self,
        tree: ast.Module
    ) -> List[Dict[str, Any]]:
        """
        Extrai informações de classes da AST.

        Args:
            tree: AST Module

        Returns:
            Lista de dicts com info das classes
        """
        classes = []

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                class_info = {
                    'name': node.name,
                    'lineno': node.lineno,
                    'decorators': self._extract_decorators(node),
                    'methods_count': len([
                        n for n in node.body
                        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                    ]),
                    'docstring': ast.get_docstring(node)
                }
                classes.append(class_info)

        self.metrics['total_classes'] += len(classes)
        return classes

    def _extract_decorators(
        self,
        node: ast.AST
    ) -> List[str]:
        """Extrai decorators de um nó AST como strings."""
        decorators = []

        for decorator in getattr(node, 'decorator_list', []):
            try:
                # Tenta converter para string
                if isinstance(decorator, ast.Name):
                    decorators.append(f"@{decorator.id}")
                elif isinstance(decorator, ast.Call):
                    func_name = self._get_call_name(decorator)
                    if func_name:
                        decorators.append(f"@{func_name}")
                elif isinstance(decorator, ast.Attribute):
                    decorators.append(f"@{decorator.attr}")
            except Exception:
                decorators.append("@<decorator>")

        return decorators

    def _get_call_name(self, node: ast.Call) -> Optional[str]:
        """Extrai nome de uma chamada de função."""
        if isinstance(node.func, ast.Name):
            return node.func.id
        elif isinstance(node.func, ast.Attribute):
            # Extrai o valor recursivamente para lidar com atributos aninhados
            value = self._extract_attribute_value(node.func)
            return f"{value}.{node.func.attr}"
        return None

    def _extract_attribute_value(self, node: ast.Attribute) -> str:
        """Extrai o valor de um atributo recursivamente."""
        if isinstance(node.value, ast.Name):
            return node.value.id
        elif isinstance(node.value, ast.Attribute):
            return f"{self._extract_attribute_value(node.value)}.{node.value.attr}"
        else:
            return str(node.value)

    def extract_imports(
        self,
        tree: ast.Module,
        filename: str
    ) -> Dict[str, List[str]]:
        """
        Extrai imports de um AST categorizados por tipo.

        Args:
            tree: AST Module
            filename: Nome do arquivo (para imports relativos)

        Returns:
            Dict com categorias: stdlib, external, local, local_relative
        """
        imports = {
            'stdlib': set(),
            'external': set(),
            'local': set(),
            'local_relative': set()
        }

        # Módulos da stdlib Python 3.10 mais comuns
        stdlib_modules = {
            'os', 'sys', 'json', 're', 'datetime', 'pathlib', 'typing',
            'collections', 'itertools', 'functools', 'asyncio', 'logging',
            'math', 'random', 'hashlib', 'base64', 'time', 'uuid'
        }

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    module_name = alias.name.split('.')[0]

                    if module_name in stdlib_modules:
                        imports['stdlib'].add(module_name)
                    else:
                        imports['external'].add(module_name)

                    self.metrics['total_imports'] += 1

            elif isinstance(node, ast.ImportFrom):
                module = node.module or ''
                level = node.level or 0

                for alias in node.names:
                    import_name = alias.name

                    if level == 1:  # Import relativo simples (.) -> local
                        imports['local'].add(import_name)
                    elif level > 1:  # Import relativo com nível (.., ...) -> local_relative
                        imports['local_relative'].add(import_name)  # Apenas o nome, sem pontos
                    elif module.startswith('.'):
                        imports['local_relative'].add(import_name)
                    elif module in stdlib_modules:
                        imports['stdlib'].add(module)
                    else:
                        # Import de módulo externo: o módulo vai para external, o nome importado vai para local
                        imports['external'].add(module)
                        # Só adicionamos ao local se não for um nome do próprio módulo (ex: FastAPI do fastapi)
                        # Verifica se o nome importado é diferente do nome do módulo
                        if import_name.lower() != module.lower():
                            imports['local'].add(import_name)

        # Converter sets para lists
        return {k: list(v) for k, v in imports.items()}

    def build_dependency_graph(
        self,
        files_data: Dict[str, Dict]
    ) -> Dict[str, Any]:
        """
        Constrói grafo de dependências entre arquivos.

        Args:
            files_data: Dict com dados dos arquivos {filename: {imports, classes}}

        Returns:
            Dict com grafo (nodes, edges, circular)
        """
        graph = {
            'nodes': list(files_data.keys()),
            'edges': defaultdict(set),
            'circular': []
        }

        # Construir arestas baseada em imports locais
        for filename, data in files_data.items():
            local_imports = (
                data.get('imports', {}).get('local', []) +
                data.get('imports', {}).get('local_relative', [])
            )

            for imp in local_imports:
                # Tentar resolver o nome do arquivo
                target_file = self._resolve_import_filename(imp, filename, files_data.keys())

                if target_file and target_file != filename:
                    graph['edges'][filename].add(target_file)

        # Detectar dependências circulares
        visited = set()
        temp_path = []

        def detect_cycle(node, path):
            if node in path:
                cycle_start = path.index(node)
                cycle = path[cycle_start:] + [node]
                graph['circular'].append(cycle)
                return

            if node in visited:
                return

            visited.add(node)
            path.append(node)

            for neighbor in graph['edges'].get(node, []):
                detect_cycle(neighbor, path.copy())

            path.pop()

        for node in graph['nodes']:
            detect_cycle(node, [])

        return dict(graph)

    def _resolve_import_filename(
        self,
        import_name: str,
        source_file: str,
        available_files: List[str]
    ) -> Optional[str]:
        """
        Resolve nome de import para nome de arquivo.

        Args:
            import_name: Nome do import (ex: utils, .models)
            source_file: Arquivo de origem
            available_files: Lista de arquivos disponíveis

        Returns:
            Nome do arquivo ou None
        """
        source_dir = Path(source_file).parent

        # Import relativo simples
        if import_name.startswith('.') and import_name.count('.') == 1:
            target = source_dir / f"{import_name[1:]}.py"
            if str(target) in available_files or str(target.with_suffix('')) in available_files:
                return str(target)

        # Import relativo com nível
        if import_name.startswith('..'):
            levels = import_name.count('..')
            target_dir = source_dir
            for _ in range(levels):
                target_dir = target_dir.parent
            remaining = import_name.replace('../', '').replace('.', '')
            target = target_dir / f"{remaining}.py"
            if str(target) in available_files or str(target.with_suffix('')) in available_files:
                return str(target)

        # Import local sem ponto
        for filename in available_files:
            if filename.endswith(f"{import_name}.py"):
                return filename
            if filename.replace('/', '.').endswith(f"{import_name}.py"):
                return filename

        return None

    def calculate_complexity(
        self,
        tree: ast.Module
    ) -> int:
        """
        Calcula complexidade ciclomática de McCabe.

        Args:
            tree: AST Module

        Returns:
            Valor de complexidade
        """
        complexity = 1  # Base complexity

        for node in ast.walk(tree):
            if isinstance(node, (ast.If, ast.While, ast.For)):
                complexity += 1
            elif isinstance(node, ast.ExceptHandler):
                complexity += 1
            elif isinstance(node, ast.With):
                complexity += 1
            elif isinstance(node, ast.BoolOp):
                # Operadores and/or contam como múltiplos caminhos
                complexity += len(node.values) - 1

        return complexity

    def has_errors(self, filename: str) -> bool:
        """
        Verifica se arquivo tem erros de parsing.

        Args:
            filename: Nome do arquivo

        Returns:
            True se tem erros
        """
        return filename in self._parse_errors

    def explore_directory(self, max_files: int = 100) -> Dict[str, Any]:
        """
        Explora diretório recursivamente analisando arquivos.

        Args:
            max_files: Máximo de arquivos para analisar

        Returns:
            Dict com dados agregados da exploração
        """
        results = {
            'files_found': [],
            'parsed_data': {},
            'summary': {
                'total_files': 0,
                'parsed_success': 0,
                'parsed_errors': 0,
                'total_functions': 0,
                'total_classes': 0,
                'total_imports': 0
            }
        }

        root = Path(self.root_path)

        # Encontrar arquivos
        for ext in self.file_extensions:
            pattern = f"**/*{ext}"
            for filepath in root.glob(pattern):
                if len(results['files_found']) >= max_files:
                    break

                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        code = f.read()

                    if ext == '.py':
                        tree = self.parse_python_ast(code, str(filepath))
                        if tree:
                            functions = self.extract_functions(tree)
                            classes = self.extract_classes(tree)
                            imports = self.extract_imports(tree, str(filepath))

                            results['parsed_data'][str(filepath)] = {
                                'functions': functions,
                                'classes': classes,
                                'imports': imports,
                                'complexity': self.calculate_complexity(tree)
                            }
                            results['summary']['parsed_success'] += 1
                        else:
                            results['summary']['parsed_errors'] += 1
                    else:
                        # Para não-Python, apenas registrar
                        results['parsed_data'][str(filepath)] = {
                            'type': ext,
                            'size': len(code)
                        }
                        results['summary']['parsed_success'] += 1

                    results['files_found'].append(str(filepath))
                    results['summary']['total_files'] += 1

                except Exception as e:
                    logger.error(
                        "file_read_failed",
                        filepath=str(filepath),
                        error=str(e)
                    )

        # Atualizar métricas agregadas
        results['summary']['total_functions'] = self.metrics['total_functions']
        results['summary']['total_classes'] = self.metrics['total_classes']
        results['summary']['total_imports'] = self.metrics['total_imports']

        return results

    def get_stats(self) -> Dict[str, Any]:
        """Retorna estatísticas da exploração."""
        return {
            **self.metrics,
            'parsed_files': len(self._parsed_files),
            'files_with_errors': len(self._parse_errors)
        }
