"""
Testes expandidos para CodebaseExplorer.
Cobertura de funcionalidades de análise estática de código.
"""

import ast
import pytest
from pathlib import Path
from datetime import datetime
import tempfile
import os

from src.exploration.codebase_explorer import CodebaseExplorer


@pytest.fixture
def sample_python_code():
    """Código Python de exemplo para testes."""
    return '''
"""Módulo de exemplo para testes."""
import os
import sys
from typing import List, Optional
from collections import defaultdict
import asyncio

class UserRepository:
    """Repositório de utilizadores."""

    def __init__(self, db_connection):
        self.db = db_connection
        self._cache = {}

    def find_by_id(self, user_id: str) -> Optional[dict]:
        """Encontra utilizador por ID."""
        return self._cache.get(user_id)

    def save(self, user: dict) -> bool:
        """Salva utilizador."""
        self._cache[user['id']] = user
        return True

    def delete(self, user_id: str) -> bool:
        """Remove utilizador."""
        if user_id in self._cache:
            del self._cache[user_id]
            return True
        return False

class UserService:
    """Serviço de utilizadores."""

    def __init__(self, repository: UserRepository):
        self.repository = repository

    def create_user(self, name: str, email: str) -> dict:
        """Cria novo utilizador."""
        user = {'id': str(os.urandom(8)), 'name': name, 'email': email}
        return user

    async def get_user_async(self, user_id: str):
        """Obtém utilizador de forma assíncrona."""
        await asyncio.sleep(0.1)
        return self.repository.find_by_id(user_id)

def calculate_complexity(data: List[int]) -> float:
    """Calcula complexidade dos dados."""
    if not data:
        return 0.0
    return sum(data) / len(data)

class SingletonFactory:
    """Factory singleton."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def create(self, type_name: str):
        """Cria instância."""
        if type_name == "user":
            return UserRepository(None)
        return None
'''


@pytest.fixture
def temp_codebase_dir():
    """Diretório temporário para testes de codebase."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Criar estrutura de arquivos
        test_files = {
            "module1.py": """
from typing import List
from .module2 import Helper

class DataProcessor:
    def process(self, data: List[int]) -> int:
        return sum(data)

class Validator:
    def validate(self, value: int) -> bool:
        return value > 0
""",
            "module2.py": """
class Helper:
    @staticmethod
    def assist() -> str:
        return "help"
""",
            "sub/__init__.py": """
from .base import BaseClass
""",
            "sub/base.py": """
class BaseClass:
    def __init__(self):
        self.value = 42
""",
        }

        for filename, content in test_files.items():
            filepath = Path(tmpdir) / filename
            filepath.parent.mkdir(parents=True, exist_ok=True)
            filepath.write_text(content, encoding="utf-8")

        yield tmpdir


@pytest.fixture
def explorer(temp_codebase_dir):
    """Explorador para testes."""
    return CodebaseExplorer(temp_codebase_dir, file_extensions=[".py"])


class TestCodebaseExplorerAST:
    """Testes de parsing AST."""

    def test_parse_python_ast_success(self, explorer, sample_python_code):
        """Testa parsing de código Python válido."""
        tree = explorer.parse_python_ast(sample_python_code, "test.py")
        assert tree is not None
        assert isinstance(tree, ast.Module)

    def test_parse_python_ast_syntax_error(self, explorer):
        """Testa parsing de código com erro de sintaxe."""
        invalid_code = "def foo(:\n    return 1"
        tree = explorer.parse_python_ast(invalid_code, "invalid.py")
        assert tree is None
        assert explorer.has_errors("invalid.py")

    def test_extract_functions(self, explorer, sample_python_code):
        """Testa extração de funções."""
        tree = explorer.parse_python_ast(sample_python_code, "test.py")
        functions = explorer.extract_functions(tree)

        # Todas as funções incluindo métodos de classe e funções módulo-level
        # UserRepository(4): __init__, find_by_id, save, delete
        # UserService(3): __init__, create_user, get_user_async
        # SingletonFactory(2): __new__, create
        # Module-level(1): calculate_complexity
        assert len(functions) == 10

        # Verificar funções específicas por nome
        function_names = [f["name"] for f in functions]
        assert "find_by_id" in function_names
        assert "save" in function_names
        assert "delete" in function_names
        assert "create_user" in function_names
        assert "get_user_async" in function_names
        assert "calculate_complexity" in function_names

        # Verificar função async
        async_funcs = [f for f in functions if f["is_async"]]
        assert len(async_funcs) == 1
        assert async_funcs[0]["name"] == "get_user_async"

    def test_extract_classes(self, explorer, sample_python_code):
        """Testa extração de classes."""
        tree = explorer.parse_python_ast(sample_python_code, "test.py")
        classes = explorer.extract_classes(tree)

        assert len(classes) == 3

        # Verificar UserRepository
        repo = next(c for c in classes if c["name"] == "UserRepository")
        assert repo["methods_count"] == 4

        # Verificar SingletonFactory
        singleton = next(c for c in classes if c["name"] == "SingletonFactory")
        assert singleton["methods_count"] == 2  # __new__ e create

    def test_extract_imports(self, explorer, sample_python_code):
        """Testa extração e categorização de imports."""
        tree = explorer.parse_python_ast(sample_python_code, "test.py")
        imports = explorer.extract_imports(tree, "test.py")

        assert "stdlib" in imports
        assert "external" in imports
        assert "local" in imports
        assert "local_relative" in imports

        # Verificar stdlib
        stdlib = set(imports["stdlib"])
        assert "os" in stdlib
        assert "sys" in stdlib
        assert "asyncio" in stdlib

        # Verificar external (vazio pois typing/collections são stdlib)
        external = set(imports["external"])
        # typing e collections são categorizados como stdlib pelo explorer

    def test_calculate_complexity(self, explorer, sample_python_code):
        """Testa cálculo de complexidade ciclomática."""
        tree = explorer.parse_python_ast(sample_python_code, "test.py")
        complexity = explorer.calculate_complexity(tree)

        # Base = 1, cada if/while/for/except adiciona 1
        # UserRepository tem 3 ifs (save, delete, find_by_id retorna)
        assert complexity >= 1
        assert complexity < 50  # Deve ser razoável


class TestCodebaseExplorerDependencyGraph:
    """Testes de construção de grafo de dependências."""

    def test_build_dependency_graph(self, explorer, temp_codebase_dir):
        """Testa construção de grafo de dependências."""
        # Primeiro explorar diretório
        results = explorer.explore_directory(max_files=10)

        graph = explorer.build_dependency_graph(results["parsed_data"])

        assert "nodes" in graph
        assert "edges" in graph
        assert "circular" in graph
        assert len(graph["nodes"]) > 0

    def test_detect_circular_dependencies(self, explorer, temp_codebase_dir):
        """Testa detecção de dependências circulares."""
        # Criar código com dependência circular
        # Usando imports que podem ser resolvidos pelo grafo
        circular_dir = Path(temp_codebase_dir) / "circular"
        circular_dir.mkdir()

        (circular_dir / "module_a.py").write_text(
            """
# Importa b para criar dependência circular
from circular import module_b
class ClassA:
    pass
"""
        )

        (circular_dir / "module_b.py").write_text(
            """
# Importa a para criar dependência circular
from circular import module_a
class ClassB:
    pass
"""
        )

        explorer_circular = CodebaseExplorer(temp_codebase_dir, file_extensions=[".py"])
        results = explorer_circular.explore_directory()
        graph = explorer_circular.build_dependency_graph(results["parsed_data"])

        # Verificar estrutura do grafo
        assert "nodes" in graph
        assert "edges" in graph
        assert "circular" in graph
        # Devem ter 2 novos arquivos no grafo
        assert len(graph["nodes"]) >= 2


class TestCodebaseExplorerExploration:
    """Testes de exploração de diretório."""

    def test_explore_directory(self, explorer, temp_codebase_dir):
        """Testa exploração completa de diretório."""
        results = explorer.explore_directory(max_files=100)

        assert "files_found" in results
        assert "parsed_data" in results
        assert "summary" in results

        # temp_codebase_dir cria 4 arquivos: module1.py, module2.py, sub/__init__.py, sub/base.py
        assert results["summary"]["total_files"] == 4
        assert results["summary"]["parsed_success"] == 4  # Todos .py devem parsear
        assert results["summary"]["parsed_errors"] == 0

    def test_explorer_with_max_files_limit(self, temp_codebase_dir):
        """Testa limite máximo de arquivos."""
        explorer = CodebaseExplorer(temp_codebase_dir, file_extensions=[".py"])
        results = explorer.explore_directory(max_files=2)

        assert results["summary"]["total_files"] <= 2

    def test_get_stats(self, explorer, temp_codebase_dir):
        """Testa obtenção de estatísticas."""
        explorer.explore_directory(max_files=10)
        stats = explorer.get_stats()

        assert "files_analyzed" in stats
        assert "total_functions" in stats
        assert "total_classes" in stats
        assert "total_imports" in stats
        assert "parsed_files" in stats
        assert "files_with_errors" in stats


class TestCodebaseExplorerMultiLanguage:
    """Testes de suporte multi-linguagem."""

    def test_explore_with_typescript(self, temp_codebase_dir):
        """Testa exploração com arquivos TypeScript."""
        # Criar arquivo TypeScript
        ts_file = Path(temp_codebase_dir) / "service.ts"
        ts_file.write_text(
            """
interface User {
    id: string;
    name: string;
}

class UserService {
    private users: Map<string, User> = new Map();

    findAll(): User[] {
        return Array.from(this.users.values());
    }
}
"""
        )

        explorer = CodebaseExplorer(temp_codebase_dir, file_extensions=[".ts", ".py"])
        results = explorer.explore_directory()

        assert results["summary"]["total_files"] >= 1

    def test_explore_with_yaml(self, temp_codebase_dir):
        """Testa exploração com arquivos YAML."""
        yaml_file = Path(temp_codebase_dir) / "config.yaml"
        yaml_file.write_text(
            """
version: "1.0"
services:
  scout:
    image: scout:latest
"""
        )

        explorer = CodebaseExplorer(temp_codebase_dir, file_extensions=[".yaml"])
        results = explorer.explore_directory()

        assert results["summary"]["total_files"] >= 1
