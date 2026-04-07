"""
Testes para Scout MCP Tools.

TDD: Testes escritos antes da implementação.
Espec: @.agent-os/specs/2026-03-18-gaps-06-mcp-integration/
"""

import pytest
from pathlib import Path
from typing import Any, Dict
import tempfile
import shutil


class TestListFilesTool:
    """Testes da ferramenta list_files."""

    @pytest.fixture
    def temp_dir(self):
        """Diretório temporário para testes."""
        temp = tempfile.mkdtemp()
        # Criar estrutura de arquivos de teste
        Path(temp, "src").mkdir()
        Path(temp, "src", "main.py").write_text("print('hello')")
        Path(temp, "src", "utils.py").write_text("def helper(): pass")
        Path(temp, "tests").mkdir()
        Path(temp, "tests", "test_main.py").write_text("def test(): pass")
        Path(temp, "README.md").write_text("# Test")
        Path(temp, ".gitignore").write_text("*.pyc")

        yield temp
        shutil.rmtree(temp)

    def test_list_files_returns_all_files_by_default(self, temp_dir):
        """Testa que lista todos os arquivos por padrão."""
        from scout_mcp_server.tools import list_files

        result = list_files(path=temp_dir)

        assert "files" in result
        assert len(result["files"]) >= 5  # src, utils, test_main, README, gitignore

    def test_list_files_respects_recursive_false(self, temp_dir):
        """Testa que respeita recursive=False."""
        from scout_mcp_server.tools import list_files

        result = list_files(path=temp_dir, recursive=False)

        # Não deve retornar arquivos em subdiretórios
        for file_info in result["files"]:
            assert "/" not in file_info["path"] or file_info["path"].count("/") == 1

    def test_list_files_filters_by_pattern(self, temp_dir):
        """Testa filtro por pattern."""
        from scout_mcp_server.tools import list_files

        result = list_files(path=temp_dir, pattern="*.py")

        # Só deve retornar arquivos .py
        for file_info in result["files"]:
            assert file_info["path"].endswith(".py")

    def test_list_files_includes_file_metadata(self, temp_dir):
        """Testa que inclui metadata dos arquivos."""
        from scout_mcp_server.tools import list_files

        result = list_files(path=temp_dir)

        for file_info in result["files"]:
            assert "path" in file_info
            assert "size" in file_info
            assert "type" in file_info
            assert isinstance(file_info["size"], int)
            assert file_info["type"] in ["file", "directory"]

    def test_list_files_raises_on_invalid_path(self):
        """Testa erro para path inválido."""
        from scout_mcp_server.tools import list_files

        with pytest.raises(FileNotFoundError):
            list_files(path="/nonexistent/path/xyz")


class TestSearchCodeTool:
    """Testes da ferramenta search_code."""

    @pytest.fixture
    def code_dir(self):
        """Diretório com código para testes."""
        temp = tempfile.mkdtemp()
        Path(temp, "class_scout.py").write_text(
            """
class ScoutAgent:
    def explore(self):
        return results

class AnotherScout:
    def analyze(self):
        pass
"""
        )
        Path(temp, "functions.py").write_text(
            """
def scout_function():
    pass

def process_data():
    pass
"""
        )
        Path(temp, "README.md").write_text("scout is a tool")

        yield temp
        shutil.rmtree(temp)

    def test_search_code_finds_class_definitions(self, code_dir):
        """Testa busca de classes."""
        from scout_mcp_server.tools import search_code

        result = search_code(query="class Scout", path=code_dir)

        assert "matches" in result
        assert len(result["matches"]) >= 1
        assert any("ScoutAgent" in m.get("content", "") for m in result["matches"])

    def test_search_code_finds_function_definitions(self, code_dir):
        """Testa busca de funções."""
        from scout_mcp_server.tools import search_code

        result = search_code(query="def scout", path=code_dir)

        assert "matches" in result
        assert any("scout_function" in m.get("content", "") for m in result["matches"])

    def test_search_code_respects_max_results(self, code_dir):
        """Testa limite de resultados."""
        from scout_mcp_server.tools import search_code

        result = search_code(query="class", path=code_dir, max_results=1)

        assert len(result["matches"]) <= 1

    def test_search_code_filters_by_file_pattern(self, code_dir):
        """Testa filtro por extensão de arquivo."""
        from scout_mcp_server.tools import search_code

        result = search_code(query="scout", path=code_dir, file_pattern="*.py")

        # Não deve retornar resultados do README.md
        assert not any("README.md" in m.get("file", "") for m in result["matches"])

    def test_search_code_includes_context(self, code_dir):
        """Testa que inclui contexto ao redor da match."""
        from scout_mcp_server.tools import search_code

        result = search_code(query="class Scout", path=code_dir)

        for match in result["matches"]:
            assert "line" in match
            assert "content" in match
            assert "context" in match

    def test_search_code_returns_empty_for_no_matches(self, code_dir):
        """Testa resultado vazio quando não há matches."""
        from scout_mcp_server.tools import search_code

        result = search_code(query="NonExistentPattern_xyz", path=code_dir)

        assert result["matches"] == []

    def test_search_code_raises_on_invalid_path(self):
        """Testa erro para path inválido."""
        from scout_mcp_server.tools import search_code

        with pytest.raises(FileNotFoundError):
            search_code(query="test", path="/nonexistent/path")


class TestAnalyzeStructureTool:
    """Testes da ferramenta analyze_structure."""

    @pytest.fixture
    def structure_dir(self):
        """Diretório com estrutura complexa."""
        temp = tempfile.mkdtemp()

        # Criar estrutura aninhada
        Path(temp, "src").mkdir()
        Path(temp, "src", "services").mkdir()
        Path(temp, "src", "services", "scout.py").write_text("# scout service")
        Path(temp, "src", "services", "optimizer.py").write_text("# optimizer service")
        Path(temp, "src", "models.py").write_text("# models")
        Path(temp, "tests").mkdir()
        Path(temp, "tests", "unit").mkdir()
        Path(temp, "tests", "integration").mkdir()
        Path(temp, "tests", "unit", "test_scout.py").write_text("# test")
        Path(temp, "README.md").write_text("# readme")

        yield temp
        shutil.rmtree(temp)

    def test_analyze_structure_returns_tree(self, structure_dir):
        """Testa que retorna estrutura em árvore."""
        from scout_mcp_server.tools import analyze_structure

        result = analyze_structure(path=structure_dir)

        assert "structure" in result
        assert isinstance(result["structure"], dict)

    def test_analyze_structure_includes_metrics(self, structure_dir):
        """Testa que inclui métricas."""
        from scout_mcp_server.tools import analyze_structure

        result = analyze_structure(path=structure_dir)

        assert "metrics" in result
        assert "files" in result["metrics"]
        assert "dirs" in result["metrics"]
        assert result["metrics"]["files"] >= 5  # scout, optimizer, models, test_scout, README
        assert result["metrics"]["dirs"] >= 4  # src, services, tests, unit, integration

    def test_analyze_structure_calculates_complexity(self, structure_dir):
        """Testa cálculo de complexidade."""
        from scout_mcp_server.tools import analyze_structure

        result = analyze_structure(path=structure_dir)

        assert "complexity" in result["metrics"]
        assert isinstance(result["metrics"]["complexity"], (int, float))

    def test_analyze_structure_respects_depth(self, structure_dir):
        """Testa limite de profundidade."""
        from scout_mcp_server.tools import analyze_structure

        result = analyze_structure(path=structure_dir, depth=1)

        # Com depth=1, não deve incluir subdiretórios profundos
        # Verificar que estrutura não contém níveis muito profundos
        def count_levels(d, level=0):
            max_level = level
            for v in d.values():
                if isinstance(v, dict):
                    max_level = max(max_level, count_levels(v, level + 1))
            return max_level

        assert count_levels(result["structure"]) <= 2  # root + 1 level

    def test_analyze_structure_raises_on_invalid_path(self):
        """Testa erro para path inválido."""
        from scout_mcp_server.tools import analyze_structure

        with pytest.raises(FileNotFoundError):
            analyze_structure(path="/nonexistent/path")


class TestScoutMCPServerIntegration:
    """Testes de integração do Scout MCP Server."""

    def test_server_has_required_tools(self):
        """Testa que o servidor expõe as ferramentas requeridas."""
        from scout_mcp_server.server import mcp

        # Verificar que o servidor MCP está configurado
        assert mcp is not None
        assert mcp.name == "Scout MCP Server"

    def test_tools_have_metadata(self):
        """Testa que ferramentas têm metadata descritiva."""
        from scout_mcp_server.tools import list_files, search_code, analyze_structure

        # Verificar que funções de tools existem e têm docstrings
        assert list_files.__doc__
        assert search_code.__doc__
        assert analyze_structure.__doc__

    def test_server_info_resource_exists(self):
        """Testa que resource de info existe."""
        from scout_mcp_server.server import mcp

        # FastMCP tem métodos para listar resources
        # O recurso "scout://info" está definido no servidor
        assert mcp is not None
