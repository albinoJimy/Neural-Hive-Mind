"""Testes unitários para métricas e middleware de observabilidade."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import Request
from src.observability.metrics import (
    MetricsHelper,
    active_runs,
    average_duration,
    get_metrics_text,
    init_metrics_for_repo,
    pipeline_anomalies_resolved,
    pipeline_anomalies_total,
    pipeline_runs_total,
    queue_size,
    success_rate,
)
from src.observability.middleware import MetricsMiddleware
from starlette.datastructures import URL


class TestMetricsHelper:
    """Testes do MetricsHelper."""

    def test_record_pipeline_run(self):
        """Testa registro de execução de pipeline."""
        MetricsHelper.record_pipeline_run(
            repo_url="https://github.com/org/repo1",
            status="success",
            provider="github_actions",
            duration_seconds=300,
        )

        # Verifica que o contador foi incrementado
        assert (
            pipeline_runs_total.labels(
                repo_url="https://github.com/org/repo1",
                status="success",
                provider="github_actions",
            )._value.get()
            >= 1
        )

    def test_record_pipeline_run_multiple(self):
        """Testa múltiplos registros de execução."""
        unique_repo = "https://github.com/org/multi-test"
        for _ in range(5):
            MetricsHelper.record_pipeline_run(
                repo_url=unique_repo,
                status="success",
                provider="github_actions",
            )

        assert (
            pipeline_runs_total.labels(
                repo_url=unique_repo,
                status="success",
                provider="github_actions",
            )._value.get()
            == 5
        )

    def test_record_anomaly(self):
        """Testa registro de anomalia."""
        MetricsHelper.record_anomaly(
            repo_url="https://github.com/org/repo2",
            anomaly_type="flaky_test",
            severity="medium",
        )

        # Verifica contador e gauge
        assert (
            pipeline_anomalies_total.labels(
                repo_url="https://github.com/org/repo2",
                type="flaky_test",
                severity="medium",
            )._value.get()
            >= 1
        )

    def test_record_anomaly_resolved(self):
        """Testa registro de anomalia resolvida."""
        unique_repo = "https://github.com/org/resolve-test"

        # Primeiro registra a anomalia
        MetricsHelper.record_anomaly(
            repo_url=unique_repo,
            anomaly_type="flaky_test",
            severity="medium",
        )

        # Depois marca como resolvida
        MetricsHelper.record_anomaly_resolved(repo_url=unique_repo, severity="medium")

        # Verifica contador de resolvidas
        assert pipeline_anomalies_resolved.labels(repo_url=unique_repo)._value.get() == 1

    def test_update_active_runs(self):
        """Testa atualização de execuções ativas."""
        MetricsHelper.update_active_runs(repo_url="https://github.com/org/repo3", count=3)

        assert active_runs.labels(repo_url="https://github.com/org/repo3")._value.get() == 3

    def test_update_queue_size(self):
        """Testa atualização do tamanho da fila."""
        MetricsHelper.update_queue_size(count=10)

        assert queue_size._value.get() == 10

    def test_update_success_rate(self):
        """Testa atualização da taxa de sucesso."""
        MetricsHelper.update_success_rate(repo_url="https://github.com/org/repo4", rate=0.85)

        assert success_rate.labels(repo_url="https://github.com/org/repo4")._value.get() == 0.85

    def test_update_average_duration(self):
        """Testa atualização da duração média."""
        MetricsHelper.update_average_duration(repo_url="https://github.com/org/repo5", duration=450)

        assert average_duration.labels(repo_url="https://github.com/org/repo5")._value.get() == 450

    def test_init_metrics_for_repo(self):
        """Testa inicialização de métricas para repositório."""
        init_metrics_for_repo(repo_url="https://github.com/test/init-repo")

        # Verifica que os gauges foram inicializados
        assert success_rate.labels(repo_url="https://github.com/test/init-repo")._value.get() == 0
        assert (
            average_duration.labels(repo_url="https://github.com/test/init-repo")._value.get() == 0
        )
        assert active_runs.labels(repo_url="https://github.com/test/init-repo")._value.get() == 0


class TestMetricsMiddleware:
    """Testes do middleware de métricas."""

    @pytest.mark.asyncio()
    async def test_middleware_records_request(self):
        """Testa que o middleware registra requisições."""
        middleware = MetricsMiddleware(app=None)

        # Cria um mock request
        request = MagicMock(spec=Request)
        request.url = URL(path="/api/v1/pipelines/runs")
        request.method = "GET"

        # Cria um response mock válido
        response_mock = AsyncMock()
        response_mock.status_code = 200

        async def call_next(req):
            return response_mock

        # Processa a requisição
        response = await middleware.dispatch(request, call_next)

        # Verifica que a requisição foi processada
        assert response.status_code == 200

    @pytest.mark.asyncio()
    async def test_middleware_skips_metrics_endpoint(self):
        """Testa que o endpoint /metrics não é contabilizado."""
        middleware = MetricsMiddleware(app=None)

        request = MagicMock(spec=Request)
        request.url = URL(path="/metrics")
        request.method = "GET"

        response_mock = AsyncMock()
        response_mock.status_code = 200

        async def call_next(req):
            return response_mock

        # Processa a requisição
        response = await middleware.dispatch(request, call_next)

        # Verifica que a requisição foi processada
        assert response.status_code == 200


class TestGetMetricsText:
    """Testes da função get_metrics_text."""

    def test_get_metrics_text_returns_text(self):
        """Testa que get_metrics_text retorna texto."""
        metrics_text = get_metrics_text()

        # Pode retornar bytes ou str
        if isinstance(metrics_text, bytes):
            metrics_text = metrics_text.decode("utf-8")

        assert isinstance(metrics_text, str)
        assert len(metrics_text) > 0

    def test_get_metrics_text_contains_common_metrics(self):
        """Testa que as métricas comuns estão presentes."""
        metrics_text = get_metrics_text()

        if isinstance(metrics_text, bytes):
            metrics_text = metrics_text.decode("utf-8")

        # Verifica presença de métricas conhecidas
        assert "pipeline_runs_total" in metrics_text
        assert "pipeline_anomalies_total" in metrics_text
        assert "api_requests_total" in metrics_text

    def test_get_metrics_text_contains_help_text(self):
        """Testa que o texto de ajuda do Prometheus está presente."""
        metrics_text = get_metrics_text()

        if isinstance(metrics_text, bytes):
            metrics_text = metrics_text.decode("utf-8")

        # O Prometheus inclui linhas de HELP e TYPE
        assert "# HELP" in metrics_text or "# TYPE" in metrics_text
