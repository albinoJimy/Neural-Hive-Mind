"""
Testes para CodebaseExplorer.

TDD: Testes escritos antes da implementação.
Espec: @.agent-os/specs/2026-03-17-gaps-05-scout-agents/
"""

import ast
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Import com skip automático se módulo não disponível
CodebaseExplorer = pytest.importorskip("src.exploration.codebase_explorer").CodebaseExplorer


class TestCodebaseExplorerInitialization:
    """Testes de inicialização do CodebaseExplorer."""

    def test_explorer_initialization(self):
        """Testa que o explorator é inicializado corretamente."""
        explorer = CodebaseExplorer(root_path="/test/path")

        assert explorer.root_path == Path("/test/path")

    def test_explorer_default_extensions(self):
        """Testa extensões padrão de arquivos."""
        explorer = CodebaseExplorer(root_path="/test/path")

        assert ".py" in explorer.file_extensions
        assert ".ts" in explorer.file_extensions
        assert ".yaml" in explorer.file_extensions


class TestParsePythonAST:
    """Testes do método parse_python_ast."""

    @pytest.fixture
    def explorer(self):
        return CodebaseExplorer(root_path="/test/path")

    def test_parse_python_valid_code(self, explorer):
        """Testa parsing de código Python válido."""
        code = """
def hello_world():
    '''Says hello'''
    print("Hello, world!")
"""
        tree = explorer.parse_python_ast(code, "test.py")

        assert tree is not None
        assert isinstance(tree, ast.Module)

    def test_parse_python_extract_functions(self, explorer):
        """Testa extração de nomes de funções."""
        code = """
def func_one():
    pass

class MyClass:
    def method_one(self):
        pass
"""
        tree = explorer.parse_python_ast(code, "test.py")

        functions = explorer.extract_functions(tree)
        function_names = [f["name"] for f in functions]

        assert "func_one" in function_names
        assert "method_one" in function_names

    def test_parse_python_extract_classes(self, explorer):
        """Testa extração de nomes de classes."""
        code = """
class UserService:
    pass

class OrderService:
    pass
"""
        tree = explorer.parse_python_ast(code, "test.py")

        classes = explorer.extract_classes(tree)
        class_names = [c["name"] for c in classes]

        assert "UserService" in class_names
        assert "OrderService" in class_names

    def test_parse_python_extract_decorators(self, explorer):
        """Testa extração de decorators."""
        code = """
@router.get("/users")
async def get_users():
    pass

@cache(ttl=300)
def expensive_operation():
    pass
"""
        tree = explorer.parse_python_ast(code, "test.py")

        functions = explorer.extract_functions(tree)
        decorators = []

        for f in functions:
            decorators.extend(f.get("decorators", []))

        # Verificar se decorator contém os elementos esperados
        decorator_str = " ".join(decorators)
        assert "router.get" in decorator_str
        assert "cache" in decorator_str

    def test_parse_python_invalid_syntax(self, explorer):
        """Testa handling de sintaxe inválida."""
        code = "def broken( This is { invalid Python"

        tree = explorer.parse_python_ast(code, "broken.py")

        assert tree is None
        assert explorer.has_errors("broken.py")


class TestExtractDependencies:
    """Testes do método extract_dependencies."""

    @pytest.fixture
    def explorer(self):
        return CodebaseExplorer(root_path="/test/path")

    def test_extract_imports_from_code(self, explorer):
        """Testa extração de imports."""
        code = """
import os
import sys
from fastapi import FastAPI
from datetime import datetime
from .utils import helper
"""
        tree = explorer.parse_python_ast(code, "test.py")

        imports = explorer.extract_imports(tree, "test.py")

        assert "os" in imports["stdlib"]
        assert "fastapi" in imports["external"] or "FastAPI" in imports["external"]
        assert "helper" in imports["local"]

    def test_extract_dependencies_categorizes_correctly(self, explorer):
        """Testa categorização correta de dependências."""
        code = """
import os
from fastapi import FastAPI
from .models import User
from ..utils import helper
"""
        tree = explorer.parse_python_ast(code, "test.py")

        imports = explorer.extract_imports(tree, "test.py")

        assert "os" in imports["stdlib"]
        assert "fastapi" in imports["external"] or "FastAPI" in imports["external"]
        assert "User" in imports["local"]
        assert "helper" in imports["local_relative"]


class TestBuildDependencyGraph:
    """Testes do método build_dependency_graph."""

    @pytest.fixture
    def explorer(self):
        return CodebaseExplorer(root_path="/test/path")

    def test_build_graph_from_multiple_files(self, explorer):
        """Testa construção de grafo com múltiplos arquivos."""
        files = {
            "service_a.py": {
                "imports": {"external": ["FastAPI"], "local": ["models"]},
                "classes": ["UserService"],
            },
            "service_b.py": {"imports": {"local": ["service_a"]}, "classes": ["OrderService"]},
            "models.py": {"imports": {"external": ["pydantic"]}, "classes": ["User"]},
        }

        graph = explorer.build_dependency_graph(files)

        # service_b depende de service_a
        assert "service_b.py" in graph["edges"]
        assert "service_a.py" in graph["edges"]["service_b.py"]

        # service_a depende de models
        assert "service_a.py" in graph["edges"]
        assert "models.py" in graph["edges"]["service_a.py"]

    def test_build_graph_detects_circular_dependencies(self, explorer):
        """Testa detecção de dependências circulares."""
        files = {
            "a.py": {"imports": {"local": ["b"]}, "classes": []},
            "b.py": {"imports": {"local": ["c"]}, "classes": []},
            "c.py": {"imports": {"local": ["a"]}, "classes": []},
        }

        graph = explorer.build_dependency_graph(files)

        assert "circular" in graph
        assert len(graph["circular"]) > 0


class TestExploreDirectory:
    """Testes do método explore_directory."""

    @pytest.fixture
    def explorer(self):
        return CodebaseExplorer(root_path="/test/path")

    @patch("builtins.open", create=True)
    @patch("pathlib.Path.glob")
    def test_explore_finds_python_files(self, mock_glob, mock_open, explorer):
        """Testa descoberta de arquivos Python."""
        # Criar arquivos mock que retornam conteúdo diferente
        mock_service = MagicMock()
        mock_service.is_file.return_value = True
        mock_service.read_text.return_value = "def test(): pass"
        mock_service.__str__ = lambda self: "/test/path/service.py"

        mock_models = MagicMock()
        mock_models.is_file.return_value = True
        mock_models.read_text.return_value = "class Model: pass"
        mock_models.__str__ = lambda self: "/test/path/models.py"

        # Configurar mock para retornar apenas para .py
        # Para .ts e .yaml retorna lista vazia
        def glob_side_effect(pattern):
            if "*.py" in pattern:
                return [mock_service, mock_models]
            return []  # Para .ts e .yaml

        mock_glob.side_effect = glob_side_effect

        results = explorer.explore_directory()

        # Deve encontrar apenas 2 arquivos Python
        assert len(results["files_found"]) == 2
        assert "/test/path/service.py" in results["files_found"]
        assert "/test/path/models.py" in results["files_found"]

    @patch("pathlib.Path.glob")
    def test_explore_parses_found_files(self, mock_glob, explorer):
        """Testa parsing dos arquivos encontrados."""
        mock_file = MagicMock()
        mock_file.read_text.return_value = "def test(): pass"
        mock_file.is_file.return_value = True
        mock_glob.return_value = [mock_file]

        results = explorer.explore_directory()

        assert "parsed_data" in results


class TestCalculateComplexity:
    """Testes do método calculate_complexity."""

    @pytest.fixture
    def explorer(self):
        return CodebaseExplorer(root_path="/test/path")

    def test_calculate_complexity_simple_function(self, explorer):
        """Testa cálculo de complexidade ciclomática simples."""
        code = """
def simple_function(x):
    if x > 0:
        return x
    else:
        return -x
"""
        tree = explorer.parse_python_ast(code, "test.py")

        complexity = explorer.calculate_complexity(tree)

        # Base = 1, if = +1, else é parte do if não adiciona
        assert complexity == 2  # 1 (base) + 1 (if branch)

    def test_calculate_complexity_complex_function(self, explorer):
        """Testa cálculo de complexidade alta."""
        code = """
def complex_function(x):
    if x > 0:
        if x < 10:
            return x
        elif x < 20:
            return x * 2
    else:
        return -x
"""
        tree = explorer.parse_python_ast(code, "test.py")

        complexity = explorer.calculate_complexity(tree)

        assert complexity > 3
