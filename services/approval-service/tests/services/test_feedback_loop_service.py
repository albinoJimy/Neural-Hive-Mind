"""
Tests for FeedbackLoopService.
"""

import pytest

from src.services.feedback_loop_service import (
    DeploymentMetrics,
    FeedbackSignal,
    FeedbackSource,
    FeedbackLoopService,
    MetricType,
    get_feedback_loop_service,
)


class TestDeploymentMetrics:
    """Testes para DeploymentMetrics."""

    def test_creation(self):
        """Testa criação de DeploymentMetrics."""
        metrics = DeploymentMetrics(
            deployment_id="dep-123",
            plan_id="plan-456",
            workflow_id="wf-789",
            service_url="http://service.example.com",
        )

        assert metrics.deployment_id == "dep-123"
        assert metrics.plan_id == "plan-456"
        assert metrics.service_url == "http://service.example.com"
        assert metrics.restart_count == 0
        assert metrics.crash_count == 0

    def test_to_dict(self):
        """Testa conversão para dict."""
        metrics = DeploymentMetrics(
            deployment_id="dep-123",
            plan_id="plan-456",
            workflow_id="wf-789",
            service_url="http://service.example.com",
        )

        # Simular métricas
        metrics.response_time_ms = 150.0
        metrics.error_rate = 0.001

        data = metrics.to_dict()

        assert data["deployment_id"] == "dep-123"
        assert data["performance"]["response_time_ms"] == 150.0
        assert data["performance"]["error_rate"] == 0.001


class TestFeedbackSignal:
    """Testes para FeedbackSignal."""

    def test_creation(self):
        """Testa criação de FeedbackSignal."""
        signal = FeedbackSignal(
            signal_type="quality_issue",
            source=FeedbackSource.AUTOMATED,
            plan_id="plan-456",
            workflow_id="wf-789",
            data={"issue": "low_test_coverage"},
            priority="high",
        )

        assert signal.signal_type == "quality_issue"
        assert signal.source == FeedbackSource.AUTOMATED
        assert signal.plan_id == "plan-456"
        assert signal.priority == "high"
        assert signal.processed is False

    def test_to_dict(self):
        """Testa conversão para dict."""
        signal = FeedbackSignal(
            signal_type="quality_issue",
            source=FeedbackSource.USER,
            plan_id="plan-456",
            workflow_id="wf-789",
            data={"rating": 3},
        )

        data = signal.to_dict()

        assert data["signal_type"] == "quality_issue"
        assert data["source"] == "user"
        assert data["plan_id"] == "plan-456"
        assert "timestamp" in data


class TestFeedbackLoopService:
    """Testes para FeedbackLoopService."""

    @pytest.fixture
    def service(self):
        """Fixture para serviço."""
        return FeedbackLoopService()

    def test_initialization(self, service):
        """Testa inicialização padrão."""
        assert service.enable_auto_collection is True
        assert service.collection_interval_hours == 24
        assert service.feedback_queue_size == 1000
        assert len(service.metrics) == 0
        assert len(service.feedback_signals) == 0

    @pytest.mark.asyncio
    async def test_collect_deployment_metrics(self, service):
        """Testa coleta de métricas de deployment."""
        metrics = await service.collect_deployment_metrics(
            deployment_id="dep-123",
            plan_id="plan-456",
            workflow_id="wf-789",
            service_url="http://service.example.com",
        )

        assert metrics.deployment_id == "dep-123"
        assert metrics.plan_id == "plan-456"
        assert metrics.response_time_ms is not None
        assert metrics.error_rate is not None
        assert metrics.uptime_pct is not None

        # Verificar que foi armazenado
        assert "dep-123" in service.metrics

    @pytest.mark.asyncio
    async def test_generate_specialist_feedback(self, service):
        """Testa geração de feedback de especialista."""
        # Primeiro coletar métricas
        await service.collect_deployment_metrics(
            deployment_id="dep-123",
            plan_id="plan-456",
            workflow_id="wf-789",
            service_url="http://service.example.com",
        )

        # Gerar feedback
        signal = await service.generate_specialist_feedback(
            deployment_id="dep-123",
            feedback_data={"rating": 4, "comment": "Good deployment"},
        )

        assert signal is not None
        assert signal.signal_type == "specialist_feedback"
        assert signal.source == FeedbackSource.SPECIALIST
        assert signal.data["rating"] == 4
        assert signal.priority == "normal"

    @pytest.mark.asyncio
    async def test_generate_ml_training_data(self, service):
        """Testa geração de dados de treinamento ML."""
        # Coletar métricas para alguns deployments
        for i in range(5):
            await service.collect_deployment_metrics(
                deployment_id=f"dep-{i}",
                plan_id="plan-456",
                workflow_id=f"wf-{i}",
                service_url=f"http://service-{i}.example.com",
            )

        # Gerar dados de treinamento
        training_data = await service.generate_ml_training_data(
            plan_id="plan-456",
            limit=10,
        )

        assert len(training_data) == 5
        assert all("features" in d for d in training_data)
        assert all("labels" in d for d in training_data)

    @pytest.mark.asyncio
    async def test_get_feedback_summary(self, service):
        """Testa obtenção de resumo de feedback."""
        # Coletar métricas para gerar sinais automáticos
        await service.collect_deployment_metrics(
            deployment_id="dep-123",
            plan_id="plan-456",
            workflow_id="wf-789",
            service_url="http://service.example.com",
        )

        # Obter resumo
        summary = await service.get_feedback_summary(
            plan_id="plan-456",
            days=7,
        )

        assert "period_days" in summary
        assert "total_signals" in summary
        assert "by_type" in summary
        assert "by_priority" in summary

    @pytest.mark.asyncio
    async def test_feedback_priority_calculation(self, service):
        """Testa cálculo de prioridade de feedback."""
        # Rating baixo deve gerar prioridade alta
        priority_low = service._calculate_feedback_priority({"rating": 1})
        assert priority_low == "critical"

        priority_mid = service._calculate_feedback_priority({"rating": 3})
        assert priority_mid == "high"

        priority_high = service._calculate_feedback_priority({"rating": 5})
        assert priority_high == "low"

    @pytest.mark.asyncio
    async def test_register_callbacks(self, service):
        """Testa registro de callbacks."""

        async def mock_specialist_callback(signal):
            pass

        async def mock_ml_callback(signal):
            pass

        service.register_specialist_callback(mock_specialist_callback)
        service.register_ml_callback(mock_ml_callback)

        assert len(service.specialist_callbacks) == 1
        assert len(service.ml_callbacks) == 1

    @pytest.mark.asyncio
    async def test_signal_queue_limit(self, service):
        """Testa limite da fila de sinais."""
        # Criar serviço com fila pequena
        small_service = FeedbackLoopService(feedback_queue_size=3)

        # Adicionar sinais além do limite
        for i in range(5):
            await small_service._add_feedback_signal(
                FeedbackSignal(
                    signal_type=f"test-{i}",
                    source=FeedbackSource.AUTOMATED,
                    plan_id="plan-456",
                    workflow_id="wf-789",
                    data={},
                )
            )

        # Fila deve estar no limite
        assert len(small_service.feedback_signals) == 3

    @pytest.mark.asyncio
    async def test_enrich_from_monitoring(self, service):
        """Testa enriquecimento com dados de monitoring."""
        metrics = DeploymentMetrics(
            deployment_id="dep-123",
            plan_id="plan-456",
            workflow_id="wf-789",
            service_url="http://service.example.com",
        )

        monitoring_data = {
            "response_time": 200.0,
            "error_rate": 0.01,
            "uptime": 99.5,
        }

        enriched = await service._enrich_from_monitoring(metrics, monitoring_data)

        assert enriched.response_time_ms == 200.0
        assert enriched.error_rate == 0.01
        assert enriched.uptime_pct == 99.5

    @pytest.mark.asyncio
    async def test_generate_feedback_signals(self, service):
        """Testa geração automática de sinais de feedback."""
        metrics = DeploymentMetrics(
            deployment_id="dep-123",
            plan_id="plan-456",
            workflow_id="wf-789",
            service_url="http://service.example.com",
        )

        # Simular métricas problemáticas
        metrics.response_time_ms = 600.0  # Acima do threshold
        metrics.test_coverage = 0.5  # Abaixo do threshold

        await service._generate_feedback_signals(metrics)

        # Deve ter gerado sinais
        assert len(service.feedback_signals) >= 2

        # Verificar tipos de sinais
        signal_types = [s.signal_type for s in service.feedback_signals]
        assert "performance_issue" in signal_types
        assert "quality_issue" in signal_types


class TestMetricTypeEnum:
    """Testes para MetricType enum."""

    def test_all_types(self):
        """Testa todos os tipos disponíveis."""
        assert MetricType.PERFORMANCE.value == "performance"
        assert MetricType.RELIABILITY.value == "reliability"
        assert MetricType.QUALITY.value == "quality"
        assert MetricType.USER_SATISFACTION.value == "user_satisfaction"
        assert MetricType.RESOURCE_USAGE.value == "resource_usage"


class TestFeedbackSourceEnum:
    """Testes para FeedbackSource enum."""

    def test_all_sources(self):
        """Testa todas as fontes disponíveis."""
        assert FeedbackSource.DEPLOYMENT.value == "deployment"
        assert FeedbackSource.MONITORING.value == "monitoring"
        assert FeedbackSource.USER.value == "user"
        assert FeedbackSource.AUTOMATED.value == "automated"
        assert FeedbackSource.SPECIALIST.value == "specialist"


class TestGetFeedbackLoopService:
    """Testes para função get_feedback_loop_service."""

    def test_singleton(self):
        """Testa padrão singleton."""
        service1 = get_feedback_loop_service()
        service2 = get_feedback_loop_service()

        assert service1 is service2
