"""
Testes para Scout MCP Server.
"""
import sys
import pytest
import tempfile
import shutil
from pathlib import Path
import os

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from scout_server import (
    CodeScanner,
    ScanResult,
    get_scanner,
    _format_size,
)


# Diretório temporário global para testes assíncronos
_TEST_TEMP_DIR = None


def setup_temp_repo():
    """Cria repositório temporário para testes."""
    global _TEST_TEMP_DIR
    temp_dir = tempfile.mkdtemp()
    _TEST_TEMP_DIR = temp_dir

    repo_path = Path(temp_dir)

    # Criar estrutura de diretórios
    (repo_path / "src").mkdir(parents=True)
    (repo_path / "tests").mkdir()
    (repo_path / "docs").mkdir()

    # Criar arquivos Python
    (repo_path / "src" / "main.py").write_text("def main(): pass")
    (repo_path / "src" / "utils.py").write_text("def helper(): pass")
    (repo_path / "tests" / "test_main.py").write_text("def test_main(): pass")

    # Criar requirements.txt
    (repo_path / "requirements.txt").write_text("fastapi==0.100.0\nuvicorn==0.23.0")

    # Criar README.md
    (repo_path / "README.md").write_text("# Test Project")

    return temp_dir


def teardown_temp_repo():
    """Remove diretório temporário."""
    global _TEST_TEMP_DIR
    if _TEST_TEMP_DIR:
        shutil.rmtree(_TEST_TEMP_DIR)
        _TEST_TEMP_DIR = None


@pytest.fixture(scope="module")
def temp_repo_module():
    """Cria repositório temporário para testes (escopo módulo)."""
    temp_dir = setup_temp_repo()
    yield temp_dir
    teardown_temp_repo()


@pytest.fixture
def temp_repo():
    """Cria repositório temporário para testes síncronos."""
    temp_dir = tempfile.mkdtemp()
    repo_path = Path(temp_dir)

    # Criar estrutura mínima
    (repo_path / "src").mkdir(parents=True)
    (repo_path / "src" / "main.py").write_text("def main(): pass")
    (repo_path / "requirements.txt").write_text("fastapi==0.100.0\nuvicorn==0.23.0\n")

    yield temp_dir

    # Cleanup
    shutil.rmtree(temp_dir)


@pytest.fixture
def scanner():
    """Retorna instância do scanner."""
    return CodeScanner(base_path=tempfile.gettempdir())


class TestCodeScanner:
    """Testes para CodeScanner."""

    def test_init(self):
        """Testa inicialização do scanner."""
        scanner = CodeScanner(base_path="/test")
        assert scanner.base_path == Path("/test")

    def test_scan_directory(self, temp_repo):
        """Testa scan de diretório."""
        scanner = CodeScanner(base_path=temp_repo)

        result = scanner.scan_directory(path=".", max_depth=3)

        assert isinstance(result, ScanResult)
        assert result.total_files > 0
        assert result.total_dirs > 0
        assert "python" in result.languages
        assert result.languages["python"] >= 1  # pelo menos 1 arquivo .py

    def test_scan_directory_with_exclusion(self, temp_repo):
        """Testa scan com exclusão de diretórios."""
        scanner = CodeScanner(base_path=temp_repo)

        result = scanner.scan_directory(
            path=".",
            max_depth=5,
            exclude_dirs=["tests", "docs"]
        )

        # Arquivos em tests/ não devem ser contados
        assert result.total_files > 0

    def test_scan_directory_nonexistent(self):
        """Testa scan de diretório inexistente."""
        scanner = CodeScanner(base_path="/nonexistent")

        with pytest.raises(FileNotFoundError):
            scanner.scan_directory(path=".")

    def test_find_files(self, temp_repo):
        """Testa busca de arquivos por padrão."""
        scanner = CodeScanner(base_path=temp_repo)

        # Buscar arquivos Python
        files = scanner.find_files(path=".", pattern="*.py")

        assert len(files) >= 1
        assert any("main.py" in f for f in files)

    def test_find_files_recursive(self, temp_repo):
        """Testa busca recursiva."""
        scanner = CodeScanner(base_path=temp_repo)

        # Buscar recursivo
        files = scanner.find_files(path=".", pattern="**/*.py")

        assert len(files) >= 1

    def test_detect_dependencies_python(self, temp_repo):
        """Testa detecção de dependências Python."""
        scanner = CodeScanner(base_path=temp_repo)

        deps = scanner.detect_dependencies(path=".")

        assert "python" in deps
        assert "fastapi" in deps["python"]
        assert "uvicorn" in deps["python"]

    def test_detect_dependencies_no_deps(self, temp_repo):
        """Testa detecção quando não há dependências conhecidas."""
        # Remover requirements.txt
        req_file = Path(temp_repo) / "requirements.txt"
        if req_file.exists():
            req_file.unlink()

        scanner = CodeScanner(base_path=temp_repo)
        deps = scanner.detect_dependencies(path=".")

        # Deve retornar dict vazio ou sem Python
        assert "python" not in deps or len(deps.get("python", [])) == 0


class TestMCPTools:
    """Testes para ferramentas MCP."""

    def test_format_size(self):
        """Testa formatação de tamanho."""
        assert _format_size(100) == "100.0B"
        assert _format_size(2048) == "2.0KB"
        assert _format_size(1024 * 1024) == "1.0MB"
        assert _format_size(1024 * 1024 * 1024) == "1.0GB"

    @pytest.mark.asyncio
    async def test_health_check(self):
        """Testa health check."""
        from scout_server import health_check

        result = await health_check()

        assert result["status"] == "healthy"
        assert result["server"] == "Scout MCP Server"

    @pytest.mark.asyncio
    async def test_scan_directory_tool(self, temp_repo_module):
        """Testa ferramenta scan_directory via MCP."""
        from scout_server import scan_directory

        # Configurar base path
        os.environ["SCOUT_BASE_PATH"] = temp_repo_module

        result = await scan_directory(path=".", max_depth=3)

        assert "total_files" in result
        assert "languages" in result
        assert result["total_files"] > 0

    @pytest.mark.asyncio
    async def test_find_files_tool(self, temp_repo_module):
        """Testa ferramenta find_files via MCP."""
        from scout_server import find_files

        os.environ["SCOUT_BASE_PATH"] = temp_repo_module

        result = await find_files(path=".", pattern="*.py")

        assert "files" in result
        assert result["count"] > 0
        assert len(result["files"]) > 0

    @pytest.mark.asyncio
    async def test_detect_dependencies_tool(self, temp_repo_module):
        """Testa ferramenta detect_dependencies via MCP."""
        from scout_server import detect_dependencies

        os.environ["SCOUT_BASE_PATH"] = temp_repo_module

        result = await detect_dependencies(path=".")

        assert "dependencies" in result
        assert "summary" in result

    @pytest.mark.asyncio
    async def test_analyze_project_structure_tool(self, temp_repo_module):
        """Testa ferramenta analyze_project_structure via MCP."""
        from scout_server import analyze_project_structure

        os.environ["SCOUT_BASE_PATH"] = temp_repo_module

        result = await analyze_project_structure(path=".")

        assert "scan" in result
        assert "dependencies" in result
        assert "common_files" in result
        assert "recommendations" in result

    @pytest.mark.asyncio
    async def test_get_file_info_tool(self, temp_repo_module):
        """Testa ferramenta get_file_info via MCP."""
        from scout_server import get_file_info

        os.environ["SCOUT_BASE_PATH"] = temp_repo_module

        result = await get_file_info(path="README.md")

        assert "name" in result
        assert result["name"] == "README.md"
        assert result["language"] == "markdown"
        assert "size_bytes" in result

        # Teste arquivo inexistente
        result_missing = await get_file_info(path="nonexistent.txt")
        assert "error" in result_missing


class TestIntegration:
    """Testes de integração."""

    @pytest.mark.asyncio
    async def test_full_scan_workflow(self, temp_repo_module):
        """Testa fluxo completo de scan."""
        os.environ["SCOUT_BASE_PATH"] = temp_repo_module

        from scout_server import (
            scan_directory,
            find_files,
            detect_dependencies,
            analyze_project_structure,
        )

        # 1. Scan inicial
        scan_result = await scan_directory(path=".", max_depth=3)
        assert scan_result["total_files"] > 0

        # 2. Encontrar arquivos específicos
        py_files = await find_files(path=".", pattern="*.py")
        assert py_files["count"] > 0

        # 3. Detectar dependências
        deps = await detect_dependencies(path=".")
        assert "dependencies" in deps

        # 4. Análise completa
        analysis = await analyze_project_structure(path=".")
        assert "scan" in analysis
        assert "recommendations" in analysis
