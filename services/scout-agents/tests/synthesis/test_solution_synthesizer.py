"""
Testes para SolutionSynthesizer.

TDD: Testes escritos antes da implementação.
Espec: GAPS-05 Scout Agents
"""

import pytest
from unittest.mock import Mock, MagicMock
from typing import Dict, List

# Import com skip automático se módulo não disponível
SolutionSynthesizer = pytest.importorskip("src.synthesis.solution_synthesizer").SolutionSynthesizer


class TestSolutionSynthesizerInitialization:
    """Testes de inicialização do SolutionSynthesizer."""

    def test_synthesizer_initialization(self):
        """Testa que o synthesizer é inicializado corretamente."""
        synthesizer = SolutionSynthesizer()

        assert synthesizer is not None
        assert hasattr(synthesizer, "synthesis_strategies")

    def test_synthesizer_with_custom_strategies(self):
        """Testa configuração com estratégias customizadas."""
        custom_strategies = {"merge": lambda x: x}
        synthesizer = SolutionSynthesizer(strategies=custom_strategies)

        assert synthesizer.synthesis_strategies == custom_strategies


class TestSynthesizeSingleSource:
    """Testes de síntese de fonte única."""

    @pytest.fixture
    def synthesizer(self):
        return SolutionSynthesizer()

    def test_synthesize_codebase_analysis(self, synthesizer):
        """Testa síntese de análise de codebase."""
        source_data = {
            "source": "codebase_explorer",
            "patterns": [{"name": "repository", "count": 5, "confidence": 0.85}],
            "dependencies": {
                "files": ["service.py", "repo.py"],
                "edges": [["service.py", "repo.py"]],
            },
            "complexity": {"average": 3.2, "max": 8},
        }

        result = synthesizer.synthesize(source_data)

        assert "summary" in result
        assert "recommendations" in result
        assert "repository" in result["summary"].lower()

    def test_synthesize_pattern_discovery(self, synthesizer):
        """Testa síntese de descoberta de padrões."""
        source_data = {
            "source": "pattern_discovery",
            "patterns_found": [
                {"name": "service", "occurrences": 3},
                {"name": "repository", "occurrences": 5},
            ],
            "suggestions": [{"pattern": "factory", "confidence": 0.7}],
        }

        result = synthesizer.synthesize(source_data)

        assert result["patterns_count"] == 2
        assert "factory" in str(result["suggestions"])


class TestSynthesizeMultipleSources:
    """Testes de síntese de múltiplas fontes."""

    @pytest.fixture
    def synthesizer(self):
        return SolutionSynthesizer()

    def test_merge_codebase_and_pattern_results(self, synthesizer):
        """Testa merge de resultados de codebase e pattern discovery."""
        sources = [
            {"source": "codebase_explorer", "files_analyzed": 10, "functions": 45, "classes": 12},
            {
                "source": "pattern_discovery",
                "patterns": [{"name": "repository", "count": 4}, {"name": "service", "count": 3}],
            },
        ]

        result = synthesizer.synthesize_multiple(sources)

        assert "codebase_explorer" in result["sources"]
        assert "pattern_discovery" in result["sources"]
        assert result["total_sources"] == 2

    def test_deduplicate_patterns_from_multiple_sources(self, synthesizer):
        """Testa deduplicação de padrões de fontes diferentes."""
        sources = [
            {
                "source": "codebase_explorer",
                "patterns": [{"name": "repository", "locations": ["repo1.py", "repo2.py"]}],
            },
            {
                "source": "pattern_discovery",
                "patterns": [
                    {"name": "repository", "locations": ["repo1.py", "repo2.py", "repo3.py"]}
                ],
            },
        ]

        result = synthesizer.synthesize_multiple(sources)

        # Deve ter apenas uma entrada de repository com todas as locations
        repository_entries = [p for p in result.get("patterns", []) if p["name"] == "repository"]
        assert len(repository_entries) == 1
        assert len(repository_entries[0]["locations"]) == 3

    def test_calculate_aggregated_confidence(self, synthesizer):
        """Testa cálculo de confiança agregada."""
        sources = [
            {
                "source": "scout_a",
                "confidence": 0.8,
                "patterns": [{"name": "service", "confidence": 0.9}],
            },
            {
                "source": "scout_b",
                "confidence": 0.6,
                "patterns": [{"name": "service", "confidence": 0.7}],
            },
        ]

        result = synthesizer.synthesize_multiple(sources)

        service_pattern = next(
            (p for p in result.get("patterns", []) if p["name"] == "service"), None
        )
        assert service_pattern is not None
        # Média das confianças: (0.9 + 0.7) / 2 = 0.8
        assert abs(service_pattern["confidence"] - 0.8) < 0.05


class TestGenerateRecommendations:
    """Testes de geração de recomendações."""

    @pytest.fixture
    def synthesizer(self):
        return SolutionSynthesizer()

    def test_recommend_refactoring_based_on_complexity(self, synthesizer):
        """Testa recomendação de refatoração baseada em complexidade."""
        data = {
            "complexity_metrics": {
                "average": 7.5,
                "high_complexity_files": [
                    {"file": "service.py", "complexity": 15},
                    {"file": "controller.py", "complexity": 12},
                ],
            }
        }

        recommendations = synthesizer.generate_recommendations(data)

        assert any("refactor" in r["action"].lower() for r in recommendations)
        assert any("service.py" in str(r) for r in recommendations)

    def test_recommend_pattern_application(self, synthesizer):
        """Testa recomendação de aplicação de padrão."""
        data = {
            "patterns_found": [{"name": "service", "count": 5}],
            "missing_patterns": [{"name": "factory", "suggested_locations": ["responses.py"]}],
        }

        recommendations = synthesizer.generate_recommendations(data)

        assert any("factory" in str(r).lower() for r in recommendations)

    def test_prioritize_recommendations_by_impact(self, synthesizer):
        """Testa priorização de recomendações por impacto."""
        data = {
            "issues": [
                {"severity": "high", "description": "Circular dependency detected"},
                {"severity": "low", "description": "Missing docstring"},
                {"severity": "medium", "description": "High complexity function"},
            ]
        }

        recommendations = synthesizer.generate_recommendations(data)

        # High severity deve vir primeiro
        assert recommendations[0]["severity"] == "high"
        assert recommendations[-1]["severity"] == "low"


class TestSynthesisConflictResolution:
    """Testes de resolução de conflitos em síntese."""

    @pytest.fixture
    def synthesizer(self):
        return SolutionSynthesizer()

    def test_resolve_conflicting_pattern_names(self, synthesizer):
        """Testa resolução de nomes de padrões conflitantes."""
        sources = [
            {"source": "scout_a", "patterns": [{"name": "Repository", "confidence": 0.8}]},
            {"source": "scout_b", "patterns": [{"name": "repository", "confidence": 0.7}]},
        ]

        result = synthesizer.synthesize_multiple(sources)

        # Deve normalizar para lowercase
        repository_entries = [
            p for p in result.get("patterns", []) if p["name"].lower() == "repository"
        ]
        assert len(repository_entries) == 1

    def test_merge_conflicting_dependencies(self, synthesizer):
        """Testa merge de dependências conflitantes."""
        sources = [
            {"source": "static_analysis", "dependencies": {"service.py": ["repo.py", "utils.py"]}},
            {"source": "runtime_analysis", "dependencies": {"service.py": ["repo.py", "cache.py"]}},
        ]

        result = synthesizer.synthesize_multiple(sources)

        # Deve unir as dependências
        service_deps = result.get("dependencies", {}).get("service.py", [])
        assert "repo.py" in service_deps
        assert "utils.py" in service_deps or "cache.py" in service_deps


class TestGenerateActionableInsights:
    """Testes de geração de insights acionáveis."""

    @pytest.fixture
    def synthesizer(self):
        return SolutionSynthesizer()

    def test_generate_refactoring_steps(self, synthesizer):
        """Testa geração de passos de refatoração."""
        data = {
            "issue": "High complexity in service.py",
            "suggestion": "Extract Factory pattern",
            "affected_files": ["service.py", "models.py"],
        }

        insights = synthesizer.generate_actionable_insights(data)

        assert "steps" in insights
        assert len(insights["steps"]) > 0
        assert all("action" in step for step in insights["steps"])

    def test_estimate_effort_for_recommendations(self, synthesizer):
        """Testa estimativa de esforço para recomendações."""
        data = {
            "recommendations": [
                {"type": "simple", "description": "Add docstring"},
                {"type": "complex", "description": "Extract service layer"},
                {"type": "medium", "description": "Add factory pattern"},
            ]
        }

        insights = synthesizer.generate_actionable_insights(data)

        assert "effort" in insights
        # Simple deve ter esforço menor que complex
        simple_effort = next(
            r["effort"] for r in insights["recommendations"] if r["type"] == "simple"
        )
        complex_effort = next(
            r["effort"] for r in insights["recommendations"] if r["type"] == "complex"
        )
        assert simple_effort < complex_effort


class TestSynthesisOutputFormats:
    """Testes de formatos de saída da síntese."""

    @pytest.fixture
    def synthesizer(self):
        return SolutionSynthesizer()

    def test_output_as_dict(self, synthesizer):
        """Testa saída como dicionário."""
        data = {"test": "data"}
        result = synthesizer.synthesize(data, format="dict")

        assert isinstance(result, dict)

    def test_output_as_markdown_report(self, synthesizer):
        """Testa geração de relatório Markdown."""
        data = {
            "patterns": [{"name": "repository", "count": 5}],
            "recommendations": [{"action": "Extract factory", "priority": "high"}],
        }

        report = synthesizer.synthesize(data, format="markdown")

        assert isinstance(report, str)
        assert "# Scout Analysis Report" in report or "## Patterns Found" in report

    def test_output_as_json(self, synthesizer):
        """Testa saída como JSON string."""
        data = {"test": "data"}
        result = synthesizer.synthesize(data, format="json")

        assert isinstance(result, str)
        # JSON válido deve ter { e " ou '
        assert "{" in result and ('"' in result or "'" in result)
        # Verificar que é válido tentando fazer parse
        import json

        parsed = json.loads(result)
        assert "sources" in parsed


class TestSynthesisQualityMetrics:
    """Testes de métricas de qualidade da síntese."""

    @pytest.fixture
    def synthesizer(self):
        return SolutionSynthesizer()

    def test_calculate_synthesis_coverage(self, synthesizer):
        """Testa cálculo de cobertura da síntese."""
        sources = [
            {"source": "codebase", "files": 10},
            {"source": "patterns", "patterns": 5},
            {"source": "dependencies", "edges": 8},
        ]

        metrics = synthesizer.calculate_quality_metrics(sources)

        assert "coverage" in metrics
        assert 0 <= metrics["coverage"] <= 1

    def test_calculate_confidence_distribution(self, synthesizer):
        """Testa distribuição de confiança."""
        sources = [
            {
                "source": "scout_a",
                "findings": [{"confidence": 0.9}, {"confidence": 0.7}, {"confidence": 0.5}],
            }
        ]

        metrics = synthesizer.calculate_quality_metrics(sources)

        assert "confidence_distribution" in metrics
        assert "high" in metrics["confidence_distribution"]
        assert "medium" in metrics["confidence_distribution"]
        assert "low" in metrics["confidence_distribution"]
