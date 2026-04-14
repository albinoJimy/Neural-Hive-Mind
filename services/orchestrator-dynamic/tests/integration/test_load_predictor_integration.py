"""
Testes de integração do LoadPredictor no Orchestrator.

Valida:
- Criação do LoadPredictor via factory
- Integração com IntelligentScheduler
- Enriquecimento de workers com load forecast
- Cache Redis
- Métricas Prometheus
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime, timedelta

from src.ml.load_predictor_factory import LoadPredictorFactory, LoadPredictorWrapper
from src.scheduler.intelligent_scheduler import IntelligentScheduler
from src.scheduler.resource_allocator import ResourceAllocator
from src.config.settings import OrchestratorSettings
from src.observability.metrics import OrchestratorMetrics


@pytest.fixture
def mock_config():
    """Configuração mockada com LoadPredictor habilitado."""
    config = Mock(spec=OrchestratorSettings)
    config.load_predictor_enabled = True
    config.load_predictor_forecast_horizons = [60, 360, 1440]
    config.load_predictor_bottleneck_threshold = 0.8
    config.load_predictor_cache_ttl_seconds = 300
    config.load_predictor_weight_in_scoring = 0.2
    config.enable_ml_enhanced_scheduling = True
    config.scheduler_enable_affinity = True
    config.scheduler_affinity_plan_weight = 0.6
    config.scheduler_affinity_anti_weight = 0.3
    config.scheduler_affinity_intent_weight = 0.1
    config.scheduler_affinity_plan_threshold = 3
    config.service_registry_cache_ttl_seconds = 10
    config.environment = "development"
    return config


@pytest.fixture
def mock_redis():
    """Cliente Redis mockado."""
    mock = AsyncMock()
    mock.get = AsyncMock(return_value=None)
    mock.setex = AsyncMock()
    mock.delete = AsyncMock()
    mock.ping = AsyncMock(return_value=True)
    return mock


@pytest.fixture
def mock_mongodb():
    """Cliente MongoDB mockado."""
    mock = AsyncMock()
    mock.db = {"execution_tickets": AsyncMock()}
    return mock


@pytest.fixture
def mock_metrics():
    """Métricas mockadas."""
    metrics = Mock(spec=OrchestratorMetrics)
    metrics.record_load_forecast_latency = Mock()
    metrics.record_load_forecast_mape = Mock()
    metrics.record_load_forecast_cache_hit = Mock()
    metrics.record_load_forecast_error = Mock()
    metrics.record_bottlenecks_detected = Mock()
    return metrics


@pytest.fixture
def mock_registry_client():
    """Cliente do Service Registry mockado."""
    mock = AsyncMock()
    mock.discover_agents = AsyncMock(
        return_value=[
            {
                "agent_id": "worker-1",
                "agent_type": "query-worker",
                "status": "HEALTHY",
                "capabilities": ["query", "sql"],
                "telemetry": {
                    "success_rate": 0.95,
                    "avg_duration_ms": 2000,
                    "total_executions": 50,
                },
                "endpoint": "grpc://worker-1:8005",
            },
            {
                "agent_id": "worker-2",
                "agent_type": "query-worker",
                "status": "HEALTHY",
                "capabilities": ["query", "sql"],
                "telemetry": {
                    "success_rate": 0.90,
                    "avg_duration_ms": 2500,
                    "total_executions": 30,
                },
                "endpoint": "grpc://worker-2:8005",
            },
        ]
    )
    return mock


@pytest.fixture
def mock_priority_calculator():
    """PriorityCalculator mockado."""
    mock = Mock()
    mock.calculate_priority_score = Mock(return_value=0.75)
    return mock


@pytest.fixture
def load_predictor_wrapper(mock_config, mock_redis, mock_metrics, mock_mongodb):
    """Wrapper do LoadPredictor para testes."""
    with patch("src.ml.load_predictor_factory.ML_AVAILABLE", True):
        factory = LoadPredictorFactory(
            config=mock_config,
            redis_client=mock_redis,
            mongodb_client=mock_mongodb,
            metrics=mock_metrics,
        )

        return factory.create_load_predictor()


class TestLoadPredictorIntegration:
    """Testes de integração do LoadPredictor."""

    @pytest.mark.asyncio
    async def test_factory_creates_enabled_wrapper(
        self, mock_config, mock_redis, mock_metrics, mock_mongodb
    ):
        """Testa que factory cria wrapper habilitado quando ML disponível."""
        with patch("src.ml.load_predictor_factory.ML_AVAILABLE", True):
            mock_load_predictor = AsyncMock()
            mock_load_predictor.initialize = AsyncMock()
            mock_load_predictor.predict_load = AsyncMock(return_value={"forecast": [0.5]})
            mock_load_predictor.predict_bottlenecks = AsyncMock(return_value=[])

            with patch(
                "src.ml.load_predictor_factory.CentralLoadPredictor",
                return_value=mock_load_predictor,
            ):
                factory = LoadPredictorFactory(
                    config=mock_config,
                    redis_client=mock_redis,
                    mongodb_client=mock_mongodb,
                    metrics=mock_metrics,
                )

                wrapper = await factory.create_load_predictor()

                assert wrapper is not None
                assert wrapper.enabled is True

    @pytest.mark.asyncio
    async def test_factory_creates_disabled_wrapper_when_ml_unavailable(
        self, mock_config, mock_redis, mock_metrics, mock_mongodb
    ):
        """Testa que factory cria wrapper desabilitado quando ML indisponível."""
        with patch("src.ml.load_predictor_factory.ML_AVAILABLE", False):
            factory = LoadPredictorFactory(
                config=mock_config,
                redis_client=mock_redis,
                mongodb_client=mock_mongodb,
                metrics=mock_metrics,
            )

            wrapper = await factory.create_load_predictor()

            assert wrapper is not None
            assert wrapper.enabled is False

    @pytest.mark.asyncio
    async def test_wrapper_returns_forecast_from_cache(
        self, mock_config, mock_redis, mock_metrics, mock_mongodb
    ):
        """Testa que wrapper retorna forecast do cache."""
        with patch("src.ml.load_predictor_factory.ML_AVAILABLE", True):
            cached_forecast = '{"forecast": [0.4, 0.5, 0.6], "timestamps": ["2026-04-05T10:00:00"]}'
            mock_redis.get.return_value = cached_forecast

            factory = LoadPredictorFactory(
                config=mock_config,
                redis_client=mock_redis,
                mongodb_client=mock_mongodb,
                metrics=mock_metrics,
            )

            wrapper = await factory.create_load_predictor()
            result = await wrapper.predict_load(horizon_minutes=60)

            assert result["forecast"] == [0.4, 0.5, 0.6]
            # Não deve setar cache quando há hit
            mock_redis.setex.assert_not_called()


class TestIntelligentSchedulerIntegration:
    """Testes de integração com IntelligentScheduler."""

    @pytest.mark.asyncio
    async def test_scheduler_obtains_load_forecast(
        self,
        mock_config,
        mock_redis,
        mock_mongodb,
        mock_registry_client,
        mock_priority_calculator,
        mock_metrics,
    ):
        """Testa que scheduler obtém load forecast do LoadPredictor."""
        with patch("src.ml.load_predictor_factory.ML_AVAILABLE", True):
            mock_load_predictor = AsyncMock()
            mock_load_predictor.initialize = AsyncMock()
            mock_load_predictor.predict_load = AsyncMock(
                return_value={"forecast": [0.5, 0.6], "timestamps": ["2026-04-05T10:00:00"]}
            )
            mock_load_predictor.predict_bottlenecks = AsyncMock(return_value=[])

            with patch(
                "src.ml.load_predictor_factory.CentralLoadPredictor",
                return_value=mock_load_predictor,
            ):
                # Patch clients
                with patch(
                    "src.scheduler.intelligent_scheduler.get_redis_client", return_value=mock_redis
                ):
                    with patch(
                        "src.scheduler.intelligent_scheduler.get_mongodb_client",
                        return_value=mock_mongodb,
                    ):
                        # Criar scheduler
                        resource_allocator = ResourceAllocator(
                            registry_client=mock_registry_client,
                            config=mock_config,
                            metrics=mock_metrics,
                        )

                        scheduler = IntelligentScheduler(
                            config=mock_config,
                            metrics=mock_metrics,
                            priority_calculator=mock_priority_calculator,
                            resource_allocator=resource_allocator,
                        )

                        # Obter load forecast
                        forecast = await scheduler._get_load_forecast(horizon_minutes=60)

                        assert forecast is not None
                        assert forecast["forecast"] == [0.5, 0.6]

    @pytest.mark.asyncio
    async def test_scheduler_detects_bottlenecks(
        self,
        mock_config,
        mock_redis,
        mock_mongodb,
        mock_registry_client,
        mock_priority_calculator,
        mock_metrics,
    ):
        """Testa que scheduler detecta bottlenecks via LoadPredictor."""
        with patch("src.ml.load_predictor_factory.ML_AVAILABLE", True):
            mock_bottlenecks = [
                {
                    "timestamp": "2026-04-05T14:00:00",
                    "predicted_load": 0.85,
                    "severity": "HIGH",
                    "type": "worker_saturation",
                    "minutes_ahead": 120,
                }
            ]

            mock_load_predictor = AsyncMock()
            mock_load_predictor.initialize = AsyncMock()
            mock_load_predictor.predict_load = AsyncMock(return_value={"forecast": [0.5]})
            mock_load_predictor.predict_bottlenecks = AsyncMock(return_value=mock_bottlenecks)

            with patch(
                "src.ml.load_predictor_factory.CentralLoadPredictor",
                return_value=mock_load_predictor,
            ):
                with patch(
                    "src.scheduler.intelligent_scheduler.get_redis_client", return_value=mock_redis
                ):
                    with patch(
                        "src.scheduler.intelligent_scheduler.get_mongodb_client",
                        return_value=mock_mongodb,
                    ):
                        resource_allocator = ResourceAllocator(
                            registry_client=mock_registry_client,
                            config=mock_config,
                            metrics=mock_metrics,
                        )

                        scheduler = IntelligentScheduler(
                            config=mock_config,
                            metrics=mock_metrics,
                            priority_calculator=mock_priority_calculator,
                            resource_allocator=resource_allocator,
                        )

                        bottlenecks = await scheduler._get_predicted_bottlenecks(
                            horizon_minutes=360
                        )

                        assert len(bottlenecks) == 1
                        assert bottlenecks[0]["severity"] == "HIGH"
                        assert bottlenecks[0]["predicted_load"] == 0.85


class TestResourceAllocatorIntegration:
    """Testes de integração com ResourceAllocator."""

    @pytest.mark.asyncio
    async def test_allocator_enriches_workers_with_load_forecast(
        self, mock_config, mock_redis, mock_metrics, mock_mongodb
    ):
        """Testa que ResourceAllocator enriquece workers com load forecast."""
        with patch("src.ml.load_predictor_factory.ML_AVAILABLE", True):
            mock_forecast = {
                "forecast": [0.5, 0.6, 0.55],
                "timestamps": ["2026-04-05T10:00:00", "2026-04-05T10:01:00", "2026-04-05T10:02:00"],
            }

            mock_load_predictor = AsyncMock()
            mock_load_predictor.initialize = AsyncMock()
            mock_load_predictor.predict_load = AsyncMock(return_value=mock_forecast)
            mock_load_predictor.predict_bottlenecks = AsyncMock(return_value=[])

            with patch(
                "src.ml.load_predictor_factory.CentralLoadPredictor",
                return_value=mock_load_predictor,
            ):
                factory = LoadPredictorFactory(
                    config=mock_config,
                    redis_client=mock_redis,
                    mongodb_client=mock_mongodb,
                    metrics=mock_metrics,
                )

                wrapper = await factory.create_load_predictor()

                workers = [
                    {
                        "agent_id": "worker-1",
                        "status": "HEALTHY",
                        "telemetry": {"total_executions": 50},
                    },
                    {
                        "agent_id": "worker-2",
                        "status": "HEALTHY",
                        "telemetry": {"total_executions": 100},
                    },
                ]

                allocator = ResourceAllocator(
                    registry_client=AsyncMock(),
                    config=mock_config,
                    metrics=mock_metrics,
                    load_predictor_wrapper=wrapper,
                )

                enriched = await allocator.enrich_workers_with_load_forecast(
                    workers=workers, load_forecast=mock_forecast
                )

                # Verificar que workers foram enriquecidos
                assert len(enriched) == 2
                assert all("predicted_load_pct" in w for w in enriched)
                assert all(w.get("ml_enriched") for w in enriched)
                assert all(w.get("load_predictor_enriched") for w in enriched)

                # Workers com mais execuções devem ter carga mais alta
                load_worker_1 = next(w for w in enriched if w["agent_id"] == "worker-1")[
                    "predicted_load_pct"
                ]
                load_worker_2 = next(w for w in enriched if w["agent_id"] == "worker-2")[
                    "predicted_load_pct"
                ]
                assert load_worker_2 > load_worker_1


@pytest.mark.asyncio
async def test_end_to_end_load_predictor_in_scheduling(
    mock_config,
    mock_redis,
    mock_mongodb,
    mock_registry_client,
    mock_priority_calculator,
    mock_metrics,
):
    """
    Teste E2E: LoadPredictor no fluxo completo de scheduling.

    1. Scheduler obtém load forecast
    2. Allocator enriquece workers
    3. Melhor worker é selecionado considerando load
    """
    with patch("src.ml.load_predictor_factory.ML_AVAILABLE", True):
        mock_forecast = {
            "forecast": [0.5, 0.6, 0.7],
            "timestamps": ["2026-04-05T10:00:00", "2026-04-05T10:01:00", "2026-04-05T10:02:00"],
        }

        mock_load_predictor = AsyncMock()
        mock_load_predictor.initialize = AsyncMock()
        mock_load_predictor.predict_load = AsyncMock(return_value=mock_forecast)
        mock_load_predictor.predict_bottlenecks = AsyncMock(return_value=[])

        with patch("src.ml.load_predictor_factory.LoadPredictor", return_value=mock_load_predictor):
            with patch(
                "src.scheduler.intelligent_scheduler.get_redis_client", return_value=mock_redis
            ):
                with patch(
                    "src.scheduler.intelligent_scheduler.get_mongodb_client",
                    return_value=mock_mongodb,
                ):
                    # Criar wrapper para allocator
                    factory = LoadPredictorFactory(
                        config=mock_config,
                        redis_client=mock_redis,
                        mongodb_client=mock_mongodb,
                        metrics=mock_metrics,
                    )
                    wrapper = await factory.create_load_predictor()

                    resource_allocator = ResourceAllocator(
                        registry_client=mock_registry_client,
                        config=mock_config,
                        metrics=mock_metrics,
                        load_predictor_wrapper=wrapper,
                    )

                    scheduler = IntelligentScheduler(
                        config=mock_config,
                        metrics=mock_metrics,
                        priority_calculator=mock_priority_calculator,
                        resource_allocator=resource_allocator,
                    )

                    # Ticket de teste
                    ticket = {
                        "ticket_id": "test-ticket-1",
                        "plan_id": "plan-123",
                        "intent_id": "intent-456",
                        "risk_band": "medium",
                        "priority": "MEDIUM",
                        "required_capabilities": ["query"],
                        "namespace": "neural-hive",
                        "security_level": "INTERNAL",
                        "estimated_duration_ms": 5000,
                    }

                    # Agendar ticket
                    result = await scheduler.schedule_ticket(ticket)

                    # Verificar alocação
                    assert "allocation_metadata" in result
                    assert result["allocation_metadata"]["agent_id"] in ["worker-1", "worker-2"]
                    assert (
                        result["allocation_metadata"]["allocation_method"]
                        == "intelligent_scheduler"
                    )


class TestEnrichTicketWithPredictions:
    """Testes INFRA-011: Enriquecimento de ticket com LoadPredictor."""

    @pytest.mark.asyncio
    async def test_enrich_ticket_with_load_predictions(
        self, mock_config, mock_redis, mock_mongodb, mock_metrics
    ):
        """Testa que ticket é enriquecido com previsões de carga do LoadPredictor."""
        # Criar mock do LoadPredictor
        mock_load_predictor = AsyncMock()
        mock_load_predictor.initialize = AsyncMock()

        # Mock predict_load para retornar forecast
        mock_load_predictor.predict_load = AsyncMock(
            return_value={"predicted_load_pct": 0.75, "confidence": 0.85}
        )

        # Mock predict_bottlenecks para retornar bottlenecks
        mock_load_predictor.predict_bottlenecks = AsyncMock(
            return_value=[
                {"component": "worker-query", "severity": "HIGH", "load_pct": 0.92},
                {"component": "worker-sql", "severity": "MEDIUM", "load_pct": 0.78},
            ]
        )

        # Criar scheduler com load_predictor
        resource_allocator = Mock()
        priority_calculator = Mock()

        scheduler = IntelligentScheduler(
            config=mock_config,
            metrics=mock_metrics,
            priority_calculator=priority_calculator,
            resource_allocator=resource_allocator,
            load_predictor=mock_load_predictor,
        )

        # Ticket de teste
        ticket = {"ticket_id": "test-123", "task_type": "query", "priority": "MEDIUM"}

        # Enriquecer ticket
        enriched = await scheduler._enrich_ticket_with_predictions(ticket)

        # Verificar que predictions foi adicionado
        assert "predictions" in enriched
        assert "system_load" in enriched["predictions"]
        assert enriched["predictions"]["system_load"] == 0.75
        assert "bottlenecks" in enriched["predictions"]

        # Verificar que ticket tem campos diretos
        assert enriched.get("predicted_load_pct") == 0.75
        assert enriched.get("predicted_bottlenecks") is not None

    @pytest.mark.asyncio
    async def test_enrich_ticket_without_load_predictor(
        self, mock_config, mock_redis, mock_mongodb, mock_metrics
    ):
        """Testa que enriquecimento funciona sem LoadPredictor (fallback)."""
        resource_allocator = Mock()
        priority_calculator = Mock()

        scheduler = IntelligentScheduler(
            config=mock_config,
            metrics=mock_metrics,
            priority_calculator=priority_calculator,
            resource_allocator=resource_allocator,
            load_predictor=None,  # Sem LoadPredictor
            scheduling_predictor=None,  # Sem scheduling_predictor
            anomaly_detector=None,  # Sem anomaly_detector
        )

        # Ticket de teste
        ticket = {"ticket_id": "test-123", "task_type": "query", "priority": "MEDIUM"}

        # Enriquecer ticket
        enriched = await scheduler._enrich_ticket_with_predictions(ticket)

        # Sem preditores, não deve ter predictions (código só adiciona se houver predições)
        assert "predictions" not in enriched
        assert enriched.get("predicted_load_pct") is None

    @pytest.mark.asyncio
    async def test_enrich_ticket_load_predictor_failure(
        self, mock_config, mock_redis, mock_mongodb, mock_metrics
    ):
        """Testa que falha do LoadPredictor é tratada gracefulmente."""
        # Criar mock que falha
        mock_load_predictor = AsyncMock()
        mock_load_predictor.initialize = AsyncMock()

        # Mock para levantar exceção
        mock_load_predictor.predict_load = AsyncMock(
            side_effect=Exception("Load prediction service unavailable")
        )
        mock_load_predictor.predict_bottlenecks = AsyncMock(
            side_effect=Exception("Load prediction service unavailable")
        )

        resource_allocator = Mock()
        priority_calculator = Mock()

        scheduler = IntelligentScheduler(
            config=mock_config,
            metrics=mock_metrics,
            priority_calculator=priority_calculator,
            resource_allocator=resource_allocator,
            load_predictor=mock_load_predictor,
            scheduling_predictor=None,  # Sem outros preditores
            anomaly_detector=None,
        )

        # Ticket de teste
        ticket = {"ticket_id": "test-123", "task_type": "query", "priority": "MEDIUM"}

        # Enriquecer ticket - não deve levantar exceção
        enriched = await scheduler._enrich_ticket_with_predictions(ticket)

        # Com falha do LoadPredictor e sem outros preditores, não deve ter predictions
        assert "predictions" not in enriched

        # Métricas de falha devem ter sido registradas
        mock_metrics.record_load_predictor_usage.assert_called_with(success=False)
