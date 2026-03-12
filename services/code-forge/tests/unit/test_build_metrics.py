"""
Unit tests para BuildMetricsCollector.

Testa a coleta, agregação e análise de métricas de performance de builds.
"""

import pytest
import tempfile
import os
import json
from pathlib import Path

from src.services.build_metrics import (
    BuildMetric,
    MetricStats,
    BuildMetricsCollector,
    MetricType,
    get_metrics_collector,
    success_checker,
)


class TestBuildMetric:
    """Testes para o dataclass BuildMetric."""

    def test_build_metric_creation(self):
        """Testa criação de uma métrica de build."""
        metric = BuildMetric(
            timestamp="2026-03-12T10:00:00",
            language="python",
            framework="fastapi",
            artifact_type="microservice",
            platform="linux/amd64",
            builder_type="docker",
            success=True,
            duration_seconds=120.5,
            size_bytes=1024000,
            cache_hit=True,
        )

        assert metric.language == "python"
        assert metric.duration_seconds == 120.5
        assert metric.cache_hit is True

    def test_build_metric_to_dict(self):
        """Testa conversão de métrica para dicionário."""
        metric = BuildMetric(
            timestamp="2026-03-12T10:00:00",
            language="python",
            framework=None,
            artifact_type="microservice",
            platform="linux/amd64",
            builder_type="docker",
            success=True,
            duration_seconds=120.5,
        )

        data = metric.to_dict()
        assert data["language"] == "python"
        assert data["framework"] is None
        assert data["duration_seconds"] == 120.5


class TestBuildMetricsCollector:
    """Testes para o coletor de métricas."""

    def test_collector_initialization(self):
        """Testa inicialização do coletor."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = os.path.join(tmpdir, "metrics.jsonl")
            collector = BuildMetricsCollector(storage_path=storage_path)
            collector.metrics.clear()

            assert len(collector.metrics) == 0
            assert collector.storage_path == storage_path

    def test_collector_load_existing_metrics(self):
        """Testa carregamento de métricas existentes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = os.path.join(tmpdir, "metrics.jsonl")

            # Criar arquivo com métricas existentes
            with open(storage_path, "w") as f:
                f.write(json.dumps({
                    "timestamp": "2026-03-12T10:00:00",
                    "language": "python",
                    "framework": "fastapi",
                    "artifact_type": "microservice",
                    "platform": "linux/amd64",
                    "builder_type": "docker",
                    "success": True,
                    "duration_seconds": 120.5,
                    "size_bytes": 1024000,
                    "cache_hit": False,
                    "multi_arch": False,
                    "platforms_count": 1,
                    "has_error": False,
                    "error_type": None,
                }) + "\n")

            collector = BuildMetricsCollector(storage_path=storage_path)

            assert len(collector.metrics) == 1
            assert collector.metrics[0].language == "python"

    def test_record_build_metric(self):
        """Testa registro de uma métrica de build."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = os.path.join(tmpdir, "metrics.jsonl")
            collector = BuildMetricsCollector(storage_path=storage_path)
            collector.metrics.clear()
            # Limpar métricas carregadas
            collector.metrics.clear()

            metric = collector.record_build(
                language="python",
                framework="fastapi",
                artifact_type="microservice",
                platform="linux/amd64",
                builder_type="docker",
                success=True,
                duration_seconds=120.5,
                size_bytes=1024000,
                cache_hit=True,
            )

            assert metric in collector.metrics
            assert len(collector.metrics) == 1
            assert metric.success is True

    def test_record_multi_arch_metric(self):
        """Testa registro de métrica multi-arch."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = os.path.join(tmpdir, "metrics.jsonl")
            collector = BuildMetricsCollector(storage_path=storage_path)
            collector.metrics.clear()

            metric = collector.record_build(
                language="python",
                framework=None,
                artifact_type="microservice",
                platform="linux/amd64",
                builder_type="kaniko",
                success=True,
                duration_seconds=300.0,
                platforms=["linux/amd64", "linux/arm64"],
            )

            assert metric.multi_arch is True
            assert metric.platforms_count == 2

    def test_record_failed_build_metric(self):
        """Testa registro de métrica de build falhado."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = os.path.join(tmpdir, "metrics.jsonl")
            collector = BuildMetricsCollector(storage_path=storage_path)
            collector.metrics.clear()

            metric = collector.record_build(
                language="nodejs",
                framework="express",
                artifact_type="microservice",
                platform="linux/amd64",
                builder_type="docker",
                success=False,
                duration_seconds=45.0,
                error_type="docker_daemon_not_found",
            )

            assert metric.success is False
            assert metric.has_error is True
            assert metric.error_type == "docker_daemon_not_found"

    def test_metric_persistence(self):
        """Testa persistência de métricas em arquivo."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = os.path.join(tmpdir, "metrics.jsonl")
            collector = BuildMetricsCollector(storage_path=storage_path)
            collector.metrics.clear()

            collector.record_build(
                language="python",
                framework="fastapi",
                artifact_type="microservice",
                platform="linux/amd64",
                builder_type="docker",
                success=True,
                duration_seconds=120.5,
            )

            # Verificar que arquivo foi criado
            assert os.path.exists(storage_path)

            # Criar novo coletor para carregar do arquivo
            new_collector = BuildMetricsCollector(storage_path=storage_path)
            assert len(new_collector.metrics) == 1
            assert new_collector.metrics[0].duration_seconds == 120.5


class TestMetricsAggregation:
    """Testes para agregação de métricas."""

    def test_get_stats_by_language(self):
        """Testa cálculo de estatísticas agrupadas por linguagem."""
        collector = BuildMetricsCollector()
        collector.metrics.clear()  # Começar vazio

        # Registrar builds de diferentes linguagens
        for duration in [100, 120, 140]:
            collector.record_build(
                language="python",
                framework=None,
                artifact_type="microservice",
                platform="linux/amd64",
                builder_type="docker",
                success=True,
                duration_seconds=duration,
            )

        for duration in [50, 60, 70]:
            collector.record_build(
                language="nodejs",
                framework=None,
                artifact_type="microservice",
                platform="linux/amd64",
                builder_type="docker",
                success=True,
                duration_seconds=duration,
            )

        stats = collector.get_stats(
            metric_type=MetricType.DURATION,
            group_by="language"
        )

        assert "python" in stats
        assert "nodejs" in stats
        assert stats["python"].mean == 120.0
        assert stats["nodejs"].mean == 60.0

    def test_get_stats_filtered(self):
        """Testa cálculo de estatísticas com filtros."""
        collector = BuildMetricsCollector()
        collector.metrics.clear()  # Começar vazio

        # Registrar builds mistos
        for i in range(5):
            collector.record_build(
                language="python" if i < 3 else "nodejs",
                framework=None,
                artifact_type="microservice",
                platform="linux/amd64",
                builder_type="docker",
                success=True,
                duration_seconds=100 + i * 10,
            )

        stats = collector.get_stats(
            metric_type=MetricType.DURATION,
            filter_by={"language": "python"}
        )

        # Python tem 3 builds: 100, 110, 120
        assert stats["all"].count == 3
        assert stats["all"].mean == 110.0

    def test_cache_hit_stats(self):
        """Testa cálculo de estatísticas de cache hit."""
        collector = BuildMetricsCollector()
        collector.metrics.clear()  # Começar vazio

        # 5 builds com cache, 5 sem cache
        for i in range(10):
            collector.record_build(
                language="python",
                framework=None,
                artifact_type="microservice",
                platform="linux/amd64",
                builder_type="docker",
                success=True,
                duration_seconds=100,
                cache_hit=i < 5,
            )

        stats = collector.get_stats(
            metric_type=MetricType.CACHE_HIT,
            group_by="language"
        )

        assert stats["python"].mean == 0.5  # 50% cache hit

    def test_success_rate_stats(self):
        """Testa cálculo de taxa de sucesso."""
        collector = BuildMetricsCollector()
        collector.metrics.clear()  # Começar vazio

        # 7 sucessos, 3 falhas
        for i in range(10):
            collector.record_build(
                language="python",
                framework=None,
                artifact_type="microservice",
                platform="linux/amd64",
                builder_type="docker",
                success=i < 7,
                duration_seconds=100,
            )

        stats = collector.get_stats(
            metric_type=MetricType.SUCCESS_RATE,
            group_by="language"
        )

        assert stats["python"].mean == 0.7  # 70% sucesso


class TestPerformanceComparison:
    """Testes para comparação de performance."""

    def test_compare_performance_by_language(self):
        """Testa comparação de performance entre linguagens."""
        collector = BuildMetricsCollector()
        collector.metrics.clear()  # Começar vazio

        collector.record_build(
            language="python", framework="fastapi",
            artifact_type="microservice", platform="linux/amd64",
            builder_type="docker", success=True, duration_seconds=150,
        )
        collector.record_build(
            language="python", framework="flask",
            artifact_type="microservice", platform="linux/amd64",
            builder_type="docker", success=True, duration_seconds=130,
        )
        collector.record_build(
            language="go", framework="gin",
            artifact_type="microservice", platform="linux/amd64",
            builder_type="docker", success=True, duration_seconds=80,
        )

        comparison = collector.compare_performance(
            metric_type=MetricType.DURATION,
            dimension="language"
        )

        # Go deve ser mais rápido
        assert comparison["go"]["mean"] < comparison["python"]["mean"]

    def test_compare_performance_by_builder(self):
        """Testa comparação de performance entre builders."""
        collector = BuildMetricsCollector()
        collector.metrics.clear()  # Começar vazio

        for _ in range(3):
            collector.record_build(
                language="python",
                framework=None,
                artifact_type="microservice",
                platform="linux/amd64",
                builder_type="docker",
                success=True,
                duration_seconds=100,
            )
        for _ in range(3):
            collector.record_build(
                language="python",
                framework=None,
                artifact_type="microservice",
                platform="linux/amd64",
                builder_type="kaniko",
                success=True,
                duration_seconds=140,
            )

        comparison = collector.compare_performance(
            metric_type=MetricType.DURATION,
            dimension="builder_type"
        )

        # Docker deve ser mais rápido que Kaniko (local)
        assert comparison["docker"]["mean"] < comparison["kaniko"]["mean"]


class TestPerformanceReport:
    """Testes para relatório de performance."""

    def test_performance_report_structure(self):
        """Testa estrutura do relatório de performance."""
        collector = BuildMetricsCollector()
        collector.metrics.clear()  # Começar vazio para teste consistente

        # Adicionar alguns builds
        for i in range(10):
            collector.record_build(
                language="python",
                framework="fastapi",
                artifact_type="microservice",
                platform="linux/amd64",
                builder_type="docker",
                success=i < 8,  # 8 sucessos, 2 falhas
                duration_seconds=100 + i * 5,
                cache_hit=i % 2 == 0,  # 50% cache
            )

        report = collector.get_performance_report()

        # Verificar estrutura
        assert "summary" in report
        assert "duration_by_language" in report
        assert "cache_hit_rate_by_language" in report
        assert "multi_arch_impact" in report
        assert "generated_at" in report

        # Verificar valores
        assert report["summary"]["total_builds"] == 10
        assert report["summary"]["successful_builds"] == 8
        assert report["summary"]["success_rate"] == 0.8

    def test_multi_arch_impact_calculation(self):
        """Testa cálculo de overhead de multi-arch."""
        collector = BuildMetricsCollector()
        collector.metrics.clear()  # Começar vazio para teste consistente

        # Builds single-arch
        for duration in [100, 110, 120]:
            collector.record_build(
                language="python",
                framework=None,
                artifact_type="microservice",
                platform="linux/amd64",
                builder_type="docker",
                success=True,
                duration_seconds=duration,
            )

        # Builds multi-arch (significativamente mais lentos)
        for duration in [250, 270, 290]:
            collector.record_build(
                language="python",
                framework=None,
                artifact_type="microservice",
                platform="linux/amd64",
                builder_type="kaniko",
                success=True,
                duration_seconds=duration,
                platforms=["linux/amd64", "linux/arm64"],
            )

        report = collector.get_performance_report()

        impact = report["multi_arch_impact"]
        assert impact["single_arch_count"] == 3
        assert impact["multi_arch_count"] == 3
        # Multi-arch deve ser >100% mais lento
        assert impact["multi_arch_overhead_percent"] > 100


class TestSlowestBuilds:
    """Testes para identificação de builds mais lentos."""

    def test_get_slowest_builds(self):
        """Testa recuperação dos builds mais lentos."""
        collector = BuildMetricsCollector()
        collector.metrics.clear()  # Começar vazio para teste consistente

        # Criar builds com durações variadas
        durations = [50, 100, 150, 200, 250, 300]
        for i, duration in enumerate(durations):
            collector.record_build(
                language="python",
                framework=f"framework{i}",
                artifact_type="microservice",
                platform="linux/amd64",
                builder_type="docker",
                success=True,
                duration_seconds=duration,
            )

        slowest = collector.get_slowest_builds(n=3)

        assert len(slowest) == 3
        # Os 3 mais lentos devem ser 300, 250, 200
        assert slowest[0]["duration_seconds"] == 300
        assert slowest[1]["duration_seconds"] == 250
        assert slowest[2]["duration_seconds"] == 200


class TestErrorSummary:
    """Testes para resumo de erros."""

    def test_error_summary(self):
        """Testa geração de resumo de erros."""
        collector = BuildMetricsCollector()
        collector.metrics.clear()  # Começar vazio para teste consistente

        # Builds bem-sucedidos
        for _ in range(5):
            collector.record_build(
                language="python",
                framework=None,
                artifact_type="microservice",
                platform="linux/amd64",
                builder_type="docker",
                success=True,
                duration_seconds=100,
            )

        # Builds falhados
        collector.record_build(
            language="python",
            framework=None,
            artifact_type="microservice",
            platform="linux/amd64",
            builder_type="docker",
            success=False,
            duration_seconds=50,
            error_type="docker_daemon_not_found",
        )
        collector.record_build(
            language="python",
            framework=None,
            artifact_type="microservice",
            platform="linux/amd64",
            builder_type="docker",
            success=False,
            duration_seconds=60,
            error_type="out_of_memory",
        )

        summary = collector.get_error_summary()

        assert summary["total_errors"] == 2
        assert "docker_daemon_not_found" in summary["error_types"]
        assert "out_of_memory" in summary["error_types"]
        assert summary["error_types"]["docker_daemon_not_found"] == 1


class TestMetricsExport:
    """Testes para exportação de métricas."""

    def test_export_metrics_json(self):
        """Testa exportação de métricas em formato JSON."""
        with tempfile.TemporaryDirectory() as tmpdir:
            collector = BuildMetricsCollector()
            collector.metrics.clear()  # Começar vazio para teste consistente

            collector.record_build(
                language="python",
                framework="fastapi",
                artifact_type="microservice",
                platform="linux/amd64",
                builder_type="docker",
                success=True,
                duration_seconds=120.5,
            )

            output_path = os.path.join(tmpdir, "metrics.json")
            collector.export_metrics(output_path, format="json")

            assert os.path.exists(output_path)

            with open(output_path, "r") as f:
                data = json.load(f)
                assert len(data) == 1
                assert data[0]["language"] == "python"

    def test_export_metrics_csv(self):
        """Testa exportação de métricas em formato CSV."""
        with tempfile.TemporaryDirectory() as tmpdir:
            collector = BuildMetricsCollector()
            collector.metrics.clear()  # Começar vazio para teste consistente

            collector.record_build(
                language="python",
                framework="fastapi",
                artifact_type="microservice",
                platform="linux/amd64",
                builder_type="docker",
                success=True,
                duration_seconds=120.5,
            )

            output_path = os.path.join(tmpdir, "metrics.csv")
            collector.export_metrics(output_path, format="csv")

            assert os.path.exists(output_path)

            with open(output_path, "r") as f:
                content = f.read()
                assert "python" in content
                assert "120.5" in content


class TestGlobalCollector:
    """Testes para o coletor global."""

    def test_get_metrics_collector_singleton(self):
        """Testa que get_metrics_collector retorna singleton."""
        collector1 = get_metrics_collector()
        collector2 = get_metrics_collector()

        assert collector1 is collector2


class TestSuccessChecker:
    """Testes para a função success_checker."""

    def test_success_checker_with_successful_metric(self):
        """Testa success_checker com métrica de sucesso."""
        metric = BuildMetric(
            timestamp="2026-03-12T10:00:00",
            language="python",
            framework=None,
            artifact_type="microservice",
            platform="linux/amd64",
            builder_type="docker",
            success=True,
            duration_seconds=100,
            has_error=False,
        )

        assert success_checker(metric) is True

    def test_success_checker_with_failed_metric(self):
        """Testa success_checker com métrica de falha."""
        metric = BuildMetric(
            timestamp="2026-03-12T10:00:00",
            language="python",
            framework=None,
            artifact_type="microservice",
            platform="linux/amd64",
            builder_type="docker",
            success=False,
            duration_seconds=50,
            has_error=True,
        )

        assert success_checker(metric) is False
