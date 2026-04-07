"""
Testes para Optimizer MCP Server.
"""
import sys
import os
import pytest
import tempfile
import shutil
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from optimizer_server import (
    PythonAnalyzer,
    CodeOptimizer,
    Issue,
    Severity,
    FileMetrics,
    get_optimizer,
)


# Reset global state between tests
@pytest.fixture(autouse=True)
def reset_global_state():
    """Reseta estado global entre testes."""
    import optimizer_server

    optimizer_server._optimizer = None
    if "OPTIMIZER_BASE_PATH" in os.environ:
        del os.environ["OPTIMIZER_BASE_PATH"]
    yield
    # Cleanup after test
    optimizer_server._optimizer = None


@pytest.fixture
def temp_project():
    """Cria projeto Python temporário para testes."""
    temp_dir = tempfile.mkdtemp()
    project_path = Path(temp_dir)

    # Criar arquivos de teste
    (project_path / "module.py").write_text(
        '''
def simple_function():
    """Uma função simples."""
    return 42

def complex_function(x):
    """Uma função complexa."""
    if x > 0:
        for i in range(10):
            if i % 2 == 0:
                for j in range(5):
                    if x > j:
                        return x * i * j
    return 0

def long_function():
    """Uma função muito longa."""
    linha1 = 1
    linha2 = 2
    linha3 = 3
    linha4 = 4
    linha5 = 5
    linha6 = 6
    linha7 = 7
    linha8 = 8
    linha9 = 9
    linha10 = 10
    linha11 = 11
    linha12 = 12
    linha13 = 13
    linha14 = 14
    linha15 = 15
    linha16 = 16
    linha17 = 17
    linha18 = 18
    linha19 = 19
    linha20 = 20
    linha21 = 21
    linha22 = 22
    linha23 = 23
    linha24 = 24
    linha25 = 25
    linha26 = 26
    linha27 = 27
    linha28 = 28
    linha29 = 29
    linha30 = 30
    linha31 = 31
    linha32 = 32
    linha33 = 33
    linha34 = 34
    linha35 = 35
    linha36 = 36
    linha37 = 37
    linha38 = 38
    linha39 = 39
    linha40 = 40
    linha41 = 41
    linha42 = 42
    linha43 = 43
    linha44 = 44
    linha45 = 45
    linha46 = 46
    linha47 = 47
    linha48 = 48
    linha49 = 49
    linha50 = 50
    linha51 = 51
    return linha51

class BigClass:
    """Uma classe grande."""

    def method1(self):
        pass

    def method2(self):
        pass

    def method3(self):
        pass

    def method4(self):
        pass

    def method5(self):
        pass

    def method6(self):
        pass

    def method7(self):
        pass

    def method8(self):
        pass

    def method9(self):
        pass

    def method10(self):
        pass

    def method11(self):
        pass

    def method12(self):
        pass

    def method13(self):
        pass

    def method14(self):
        pass

    def method15(self):
        pass

    def method16(self):
        pass

    def method17(self):
        pass

    def method18(self):
        pass

    def method19(self):
        pass

    def method20(self):
        pass

    def method21(self):
        pass

    def method22(self):
        pass

    def method23(self):
        pass

    def method24(self):
        pass

    def method25(self):
        pass
'''
    )

    (project_path / "bare_except.py").write_text(
        '''
def risky_function():
    """Função com bare except."""
    try:
        result = 1 / 0
    except:
        result = 0
    return result
'''
    )

    yield temp_dir

    # Cleanup
    shutil.rmtree(temp_dir)


class TestPythonAnalyzer:
    """Testes para PythonAnalyzer."""

    def test_analyze_simple_file(self):
        """Testa análise de arquivo simples."""
        source = "def hello():\n    print('Hello, World!')\n"
        analyzer = PythonAnalyzer("/test.py", source)
        metrics = analyzer.analyze()

        assert metrics.total_lines == 3
        assert metrics.functions == 1
        assert metrics.classes == 0

    def test_analyze_with_class(self):
        """Testa análise com classe."""
        source = """
class MyClass:
    def method1(self):
        pass

    def method2(self):
        pass
"""
        analyzer = PythonAnalyzer("/test.py", source)
        metrics = analyzer.analyze()

        assert metrics.classes == 1
        assert metrics.functions == 2  # Métodos contados como funções

    def test_detects_long_function(self):
        """Testa detecção de função muito longa."""
        source = "def long_func():\n"
        for i in range(51):
            source += f"    x = {i}\n"

        analyzer = PythonAnalyzer("/test.py", source)
        analyzer.analyze()

        long_func_issues = [i for i in analyzer.issues if i.category == "function_length"]
        assert len(long_func_issues) == 1
        assert long_func_issues[0].severity == Severity.MEDIUM

    def test_detects_deep_nesting(self):
        """Testa detecção de nesting profundo."""
        source = """
def deep():
    for x in range(10):
        for y in range(10):
            for z in range(10):
                pass
"""
        analyzer = PythonAnalyzer("/test.py", source)
        analyzer.analyze()

        nesting_issues = [i for i in analyzer.issues if i.category == "nesting"]
        assert len(nesting_issues) > 0

    def test_detects_bare_except(self):
        """Testa detecção de bare except."""
        source = """
try:
    risky()
except:
    pass
"""
        analyzer = PythonAnalyzer("/test.py", source)
        analyzer.analyze()

        bare_issues = [i for i in analyzer.issues if i.category == "bare_except"]
        assert len(bare_issues) == 1
        assert bare_issues[0].severity == Severity.MEDIUM

    def test_calculates_complexity(self):
        """Testa cálculo de complexidade ciclomática."""
        source = """
def complex_func(x):
    if x > 0:
        for i in range(10):
            if i % 2 == 0:
                return i
    return 0
"""
        analyzer = PythonAnalyzer("/test.py", source)
        analyzer.analyze()

        # complex_func deve ter complexidade > 1 (devido a if + for + if)
        assert analyzer.complexity["complex_func"] > 1


class TestCodeOptimizer:
    """Testes para CodeOptimizer."""

    def test_init(self):
        """Testa inicialização."""
        optimizer = CodeOptimizer(base_path="/test")
        assert optimizer.base_path == Path("/test")

    def test_analyze_file(self, temp_project):
        """Testa análise de arquivo."""
        optimizer = CodeOptimizer(base_path=temp_project)

        metrics, issues = optimizer.analyze_file("module.py")

        assert isinstance(metrics, FileMetrics)
        assert "module.py" in metrics.path
        assert metrics.total_lines > 0
        assert isinstance(issues, list)

    def test_analyze_nonexistent_file(self):
        """Testa análise de arquivo inexistente."""
        optimizer = CodeOptimizer(base_path="/tmp")

        with pytest.raises(FileNotFoundError):
            optimizer.analyze_file("nonexistent.py")

    def test_analyze_directory(self, temp_project):
        """Testa análise de diretório."""
        optimizer = CodeOptimizer(base_path=temp_project)

        result = optimizer.analyze_directory(path=".")

        assert "summary" in result
        assert result["summary"]["total_files"] >= 1
        assert "severity_breakdown" in result
        assert "category_breakdown" in result

    def test_generate_recommendations(self, temp_project):
        """Testa geração de recomendações."""
        optimizer = CodeOptimizer(base_path=temp_project)

        result = optimizer.analyze_directory(path=".")
        recommendations = optimizer.generate_recommendations(result)

        assert isinstance(recommendations, list)
        # Deve ter recomendações para pelo menos um problema
        # (o módulo de teste tem problemas de função longa e classe grande)


class TestMCPTools:
    """Testes para ferramentas MCP."""

    @pytest.mark.asyncio
    async def test_analyze_file_performance(self, temp_project):
        """Testa ferramenta analyze_file_performance."""
        from optimizer_server import analyze_file_performance

        import os

        os.environ["OPTIMIZER_BASE_PATH"] = temp_project

        result = await analyze_file_performance(file_path="module.py")

        assert "metrics" in result
        assert "issues" in result
        assert result["metrics"]["total_lines"] > 0

    @pytest.mark.asyncio
    async def test_analyze_directory_performance(self, temp_project):
        """Testa ferramenta analyze_directory_performance."""
        from optimizer_server import analyze_directory_performance

        os.environ["OPTIMIZER_BASE_PATH"] = temp_project

        result = await analyze_directory_performance(path=".")

        assert "summary" in result
        assert result["summary"]["total_files"] >= 1

    @pytest.mark.asyncio
    async def test_get_optimization_recommendations(self, temp_project):
        """Testa ferramenta get_optimization_recommendations."""
        from optimizer_server import get_optimization_recommendations

        os.environ["OPTIMIZER_BASE_PATH"] = temp_project

        result = await get_optimization_recommendations(path=".")

        assert "recommendations" in result
        assert isinstance(result["recommendations"], list)

    @pytest.mark.asyncio
    async def test_detect_code_smells(self, temp_project):
        """Testa ferramenta detect_code_smells."""
        from optimizer_server import detect_code_smells

        os.environ["OPTIMIZER_BASE_PATH"] = temp_project

        result = await detect_code_smells(path=".", severity="low")

        assert "by_category" in result
        assert isinstance(result["by_category"], dict)

    @pytest.mark.asyncio
    async def test_health_check(self):
        """Testa health check."""
        from optimizer_server import health_check

        result = await health_check()

        assert result["status"] == "healthy"
        assert result["server"] == "Optimizer MCP Server"


class TestIntegration:
    """Testes de integração."""

    @pytest.mark.asyncio
    async def test_full_analysis_workflow(self, temp_project):
        """Testa fluxo completo de análise."""
        import os

        os.environ["OPTIMIZER_BASE_PATH"] = temp_project

        from optimizer_server import (
            analyze_directory_performance,
            get_optimization_recommendations,
            detect_code_smells,
        )

        # 1. Analisar diretório
        analysis = await analyze_directory_performance(path=".")
        assert analysis["summary"]["total_files"] >= 1

        # 2. Obter recomendações
        recommendations = await get_optimization_recommendations(path=".")
        assert "recommendations" in recommendations

        # 3. Detectar code smells
        smells = await detect_code_smells(path=".", severity="low")
        assert "by_category" in smells
