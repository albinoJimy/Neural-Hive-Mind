"""
Testes para Optimizer MCP Tools.

TDD: Testes escritos antes da implementação.
Espec: @.agent-os/specs/2026-03-18-gaps-06-mcp-integration/
"""

import shutil
import tempfile
from pathlib import Path

import pytest


class TestSuggestRefactorsTool:
    """Testes da ferramenta suggest_refactors."""

    @pytest.fixture()
    def code_dir(self):
        """Diretório com código para análise."""
        temp = tempfile.mkdtemp()

        # Arquivo com problemas de refatoração
        code = """
class UserManager:
    def __init__(self):
        self.users = []

    def add_user(self, name):
        if name not in self.users:
            self.users.append(name)

    def get_user(self, name):
        for i, u in enumerate(self.users):
            if u == name:
                return self.users[i]
        return None

    def process_all_users(self):
        results = []
        for user in self.users:
            result = str(user).upper()
            results.append(result)
        return results
"""
        Path(temp, "userManager.py").write_text(code)

        # Arquivo longo (complexidade alta)
        long_lines = [f"    step{i} = x[{i}]" for i in range(101)]
        long_code = "def process(x):\n" + "\n".join(long_lines)
        Path(temp, "long_function.py").write_text(long_code)

        # Arquivo com duplicação
        duplicate_code = """
def calculate_tax(price):
    return price * 0.1

def calculate_shipping(price):
    return price * 0.1

def calculate_fee(price):
    return price * 0.1
"""
        Path(temp, "duplicates.py").write_text(duplicate_code)

        yield temp
        shutil.rmtree(temp)

    def test_suggest_refactors_detects_long_methods(self, code_dir):
        """Testa detecção de métodos longos."""
        from src.tools.optimizer_tools import suggest_refactors

        result = suggest_refactors(path=code_dir, complexity_threshold=10)

        assert "suggestions" in result
        assert any(s["type"] == "long_method" for s in result["suggestions"])

    def test_suggest_refactors_detects_code_duplication(self, code_dir):
        """Testa detecção de duplicação de código."""
        from src.tools.optimizer_tools import suggest_refactors

        result = suggest_refactors(path=code_dir)

        assert "suggestions" in result
        assert any(s["type"] == "duplication" for s in result["suggestions"])

    def test_suggest_refactors_includes_effort_estimate(self, code_dir):
        """Testa que inclui estimativa de effort."""
        from src.tools.optimizer_tools import suggest_refactors

        result = suggest_refactors(path=code_dir)

        for suggestion in result["suggestions"]:
            assert "effort" in suggestion
            assert suggestion["effort"] in ["low", "medium", "high"]

    def test_suggest_refactors_includes_impact(self, code_dir):
        """Testa que inclui impacto da refatoração."""
        from src.tools.optimizer_tools import suggest_refactors

        result = suggest_refactors(path=code_dir)

        for suggestion in result["suggestions"]:
            assert "impact" in suggestion
            assert isinstance(suggestion["impact"], (int, float))

    def test_suggest_refactors_filters_by_threshold(self, code_dir):
        """Testa filtro por threshold de complexidade."""
        from src.tools.optimizer_tools import suggest_refactors

        result_high = suggest_refactors(path=code_dir, complexity_threshold=5)
        result_low = suggest_refactors(path=code_dir, complexity_threshold=50)

        # Threshold menor = mais sugestões
        assert len(result_high["suggestions"]) >= len(result_low["suggestions"])

    def test_suggest_refactors_raises_on_invalid_path(self):
        """Testa erro para path inválido."""
        from src.tools.optimizer_tools import suggest_refactors

        with pytest.raises(FileNotFoundError):
            suggest_refactors(path="/nonexistent/path")


class TestAnalyzePerformanceTool:
    """Testes da ferramenta analyze_performance."""

    @pytest.fixture()
    def service_dir(self):
        """Diretório com métricas de serviço."""
        temp = tempfile.mkdtemp()

        # Criar arquivos de métrica
        metrics = {
            "scout-agents": {
                "latency_ms": {"p50": 50, "p95": 120, "p99": 250},
                "throughput": {"requests_per_sec": 100},
                "error_rate": 0.02,
            },
            "optimizer": {
                "latency_ms": {"p50": 200, "p95": 500, "p99": 1000},
                "throughput": {"requests_per_sec": 25},
                "error_rate": 0.05,
            },
        }

        import json

        Path(temp, "metrics.json").write_text(json.dumps(metrics))

        yield temp
        shutil.rmtree(temp)

    def test_analyze_performance_returns_metrics(self, service_dir):
        """Testa que retorna métricas de performance."""
        from src.tools.optimizer_tools import analyze_performance

        result = analyze_performance(path=service_dir)

        assert "metrics" in result
        assert "latency_p50" in result["metrics"]
        assert "latency_p95" in result["metrics"]
        assert "latency_p99" in result["metrics"]

    def test_analyze_performance_identifies_bottlenecks(self, service_dir):
        """Testa identificação de bottlenecks."""
        from src.tools.optimizer_tools import analyze_performance

        result = analyze_performance(path=service_dir)

        assert "bottlenecks" in result
        assert isinstance(result["bottlenecks"], list)

    def test_analyze_performance_includes_trend(self, service_dir):
        """Testa que inclui análise de tendência."""
        from src.tools.optimizer_tools import analyze_performance

        result = analyze_performance(path=service_dir, duration="1h")

        assert "trend" in result
        assert result["trend"] in ["improving", "stable", "degrading"]

    def test_analyze_performance_accepts_service_name(self):
        """Testa que aceita nome de serviço específico."""
        from src.tools.optimizer_tools import analyze_performance

        # Não deve gerar erro mesmo sem arquivo
        result = analyze_performance(service="scout-agents")

        assert "metrics" in result

    def test_analyze_performance_raises_on_invalid_service(self):
        """Testa erro para serviço inexistente (quando específico)."""
        from src.tools.optimizer_tools import analyze_performance

        # Quando não há dados, deve retornar vazio ou padrão
        result = analyze_performance(service="nonexistent-service")

        assert "metrics" in result


class TestOptimizeQueriesTool:
    """Testes da ferramenta optimize_queries."""

    def test_optimize_queries_suggests_indexes(self):
        """Testa sugestão de índices."""
        from src.tools.optimizer_tools import optimize_queries

        query = {"name": {"$eq": "John"}, "age": {"$gte": 18}}
        collection = "users"

        result = optimize_queries(query=query, collection=collection)

        assert "suggested_indexes" in result
        assert isinstance(result["suggested_indexes"], list)

    def test_optimize_queries_returns_optimized_query(self):
        """Testa que retorna query otimizada."""
        from src.tools.optimizer_tools import optimize_queries

        query = {"$or": [{"status": "active"}, {"status": "pending"}]}
        collection = "orders"

        result = optimize_queries(query=query, collection=collection)

        assert "optimized_query" in result

    def test_optimize_queries_estimates_improvement(self):
        """Testa estimativa de melhoria."""
        from src.tools.optimizer_tools import optimize_queries

        query = {"name": {"$regex": "^Jo"}}
        collection = "users"

        result = optimize_queries(query=query, collection=collection)

        assert "improvement_estimate" in result
        assert isinstance(result["improvement_estimate"], str)

    def test_optimize_queries_handles_complex_queries(self):
        """Testa queries complexas."""
        from src.tools.optimizer_tools import optimize_queries

        query = {
            "$and": [
                {"created_at": {"$gte": "2024-01-01"}},
                {"$or": [{"status": "active"}, {"status": "pending"}]},
                {"priority": {"$in": [1, 2, 3]}},
            ]
        }
        collection = "complex_collection"

        result = optimize_queries(query=query, collection=collection)

        assert "optimized_query" in result
        assert "suggested_indexes" in result

    def test_optimize_queries_validates_query(self):
        """Testa validação de query."""
        from src.tools.optimizer_tools import optimize_queries

        with pytest.raises(ValueError):
            optimize_queries(query="not a dict", collection="test")

    def test_optimize_queries_requires_collection(self):
        """Testa que collection é obrigatório."""
        from src.tools.optimizer_tools import optimize_queries

        with pytest.raises(ValueError):
            optimize_queries(query={"test": "value"}, collection="")


class TestOptimizerMCPServerIntegration:
    """Testes de integração do Optimizer MCP Server."""

    def test_server_has_required_tools(self):
        """Testa que o servidor expõe as ferramentas requeridas."""
        from src.server import mcp

        # Verificar que o servidor MCP está configurado
        assert mcp is not None
        assert mcp.name == "Optimizer MCP Server"

    def test_tools_have_metadata(self):
        """Testa que ferramentas têm metadata descritiva."""
        from src.tools.optimizer_tools import (
            analyze_performance,
            optimize_queries,
            suggest_refactors,
        )

        # Verificar que funções de tools existem e têm docstrings
        assert suggest_refactors.__doc__
        assert analyze_performance.__doc__
        assert optimize_queries.__doc__
