"""
Unit Tests para Batch Inference Engine - ML Inference API

Testes unitários para o processamento em lote de predições.
"""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.schemas import (
    BatchPredictResponse,
    DecisionType,
    PredictRequest,
    PredictResponse,
)
from src.observability.metrics import MLInferenceMetrics
from src.services.batch_engine import BatchInferenceEngine, get_batch_engine

# ===== FIXTURES =====


@pytest.fixture
def mock_settings():
    """Configurações mockadas para testes."""
    return SimpleNamespace(
        batch_max_size=100,
        default_timeout_ms=5000,
        max_workers=4,
        enable_gpu=False,
    )


@pytest.fixture
def mock_metrics():
    """Mock das métricas Prometheus."""
    metrics = MagicMock(spec=MLInferenceMetrics)

    # Mock counters
    metrics.batch_predictions_total = MagicMock()
    metrics.batch_predictions_total.inc = MagicMock()

    # Mock gauges
    metrics.batch_size = MagicMock()
    metrics.batch_size.observe = MagicMock()

    # Mock histograms
    metrics.batch_duration_seconds = MagicMock()
    metrics.batch_duration_seconds.observe = MagicMock()

    metrics.batch_avg_latency_ms = MagicMock()
    metrics.batch_avg_latency_ms.observe = MagicMock()

    return metrics


@pytest.fixture
def mock_predictor():
    """Mock do PredictorService."""
    predictor = AsyncMock()

    # Mock predict (método real do PredictorService)
    predictor.predict.return_value = {
        "decision": "approve",
        "confidence": 0.85,
        "probabilities": {"approve": 0.85, "reject": 0.15},
        "model_version": "v7",
    }

    return predictor


@pytest.fixture
def sample_batch_requests():
    """Requests de batch de exemplo como PredictRequest."""
    return [
        PredictRequest(
            intent_text="Create new user with email verification",
            specialist_confidence=0.9,
            specialist_type="technical",
        ),
        PredictRequest(
            intent_text="Add index to email column",
            specialist_confidence=0.85,
            specialist_type="technical",
        ),
        PredictRequest(
            intent_text="Enable two-factor authentication",
            specialist_confidence=0.95,
            specialist_type="security",
        ),
    ]


# ===== TESTES: Initialization =====


class TestBatchInferenceEngineInit:
    """Testes de inicialização do BatchInferenceEngine."""

    def test_init_creates_engine(self, mock_predictor, mock_metrics):
        """
        DADO: PredictorService e métricas válidos
        QUANDO: Crio BatchInferenceEngine
        ENTÃO: Deve inicializar corretamente
        """
        engine = BatchInferenceEngine(
            predictor_service=mock_predictor,
            metrics=mock_metrics,
        )

        assert engine.predictor_service == mock_predictor
        assert engine.metrics == mock_metrics
        assert engine.max_workers is None

    def test_init_with_custom_max_workers(self, mock_predictor, mock_metrics):
        """
        DADO: PredictorService e métricas válidos
        QUANDO: Crio BatchInferenceEngine com max_workers=8
        ENTÃO: Deve usar o max_workers customizado
        """
        engine = BatchInferenceEngine(
            predictor_service=mock_predictor,
            metrics=mock_metrics,
            max_workers=8,
        )

        assert engine.max_workers == 8


# ===== TESTES: Process Batch =====


class TestProcessBatch:
    """Testes do método process_batch."""

    @pytest.mark.asyncio
    async def test_process_batch_success(
        self, mock_predictor, mock_metrics, sample_batch_requests, mock_settings
    ):
        """
        DADO: Uma lista de requests válidos
        QUANDO: Chamo process_batch
        ENTÃO: Deve retornar BatchPredictResponse com resultados para todos os requests
        """
        with patch("src.services.batch_engine.settings", mock_settings):
            engine = BatchInferenceEngine(
                predictor_service=mock_predictor,
                metrics=mock_metrics,
            )

        result = await engine.process_batch(sample_batch_requests)

        assert isinstance(result, BatchPredictResponse)
        assert len(result.results) == 3
        assert result.total_processed == 3
        assert result.successful == 3
        assert result.failed == 0
        assert result.total_inference_time_ms >= 0

    @pytest.mark.asyncio
    async def test_process_batch_parallel(
        self, mock_predictor, mock_metrics, sample_batch_requests, mock_settings
    ):
        """
        DADO: Uma lista de requests válidos
        QUANDO: Chamo process_batch com parallel=True
        ENTÃO: Deve processar em paralelo
        """
        with patch("src.services.batch_engine.settings", mock_settings):
            engine = BatchInferenceEngine(
                predictor_service=mock_predictor,
                metrics=mock_metrics,
            )

        result = await engine.process_batch(sample_batch_requests, parallel=True)

        assert result.successful == 3
        # Verificar que predictor foi chamado 3 vezes
        assert mock_predictor.predict.call_count == 3

    @pytest.mark.asyncio
    async def test_process_batch_sequential(
        self, mock_predictor, mock_metrics, sample_batch_requests, mock_settings
    ):
        """
        DADO: Uma lista de requests válidos
        QUANDO: Chamo process_batch com parallel=False
        ENTÃO: Deve processar sequencialmente
        """
        with patch("src.services.batch_engine.settings", mock_settings):
            engine = BatchInferenceEngine(
                predictor_service=mock_predictor,
                metrics=mock_metrics,
            )

        result = await engine.process_batch(sample_batch_requests, parallel=False)

        assert result.successful == 3
        assert mock_predictor.predict.call_count == 3

    @pytest.mark.asyncio
    async def test_process_batch_exceeds_max_size(
        self, mock_predictor, mock_metrics, mock_settings
    ):
        """
        DADO: Uma lista maior que o batch_max_size
        QUANDO: Chamo process_batch
        ENTÃO: Deve raise ValueError
        """
        # Criar batch maior que o limite
        large_batch = [
            PredictRequest(
                intent_text=f"Test request {i}",
                specialist_confidence=0.8,
            )
            for i in range(101)
        ]

        with patch("src.services.batch_engine.settings", mock_settings):
            engine = BatchInferenceEngine(
                predictor_service=mock_predictor,
                metrics=mock_metrics,
            )

        with pytest.raises(ValueError, match="exceeds maximum"):
            await engine.process_batch(large_batch)

    @pytest.mark.asyncio
    async def test_process_batch_with_failures(
        self, mock_predictor, mock_metrics, mock_settings
    ):
        """
        DADO: Uma lista onde uma predição falha
        QUANDO: Chamo process_batch
        ENTÃO: Deve processar os restantes e contar falhas
        """
        requests = [
            PredictRequest(
                intent_text="Valid request 1",
                specialist_confidence=0.8,
            ),
            PredictRequest(
                intent_text="Valid request 2",
                specialist_confidence=0.9,
            ),
            PredictRequest(
                intent_text="Valid request 3",
                specialist_confidence=0.85,
            ),
        ]

        # Configurar side effect para falhar no segundo
        call_count = 0

        async def side_effect(intent_text, specialist_confidence, specialist_type=None):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise ValueError("Simulated prediction failure")
            return {
                "decision": "approve",
                "confidence": 0.85,
                "probabilities": {"approve": 0.85, "reject": 0.15},
                "model_version": "v7",
            }

        mock_predictor.predict.side_effect = side_effect

        with patch("src.services.batch_engine.settings", mock_settings):
            engine = BatchInferenceEngine(
                predictor_service=mock_predictor,
                metrics=mock_metrics,
            )

        result = await engine.process_batch(requests, parallel=False)

        assert result.total_processed == 3
        assert result.successful == 2
        assert result.failed == 1
        assert len(result.results) == 2  # Apenas os bem-sucedidos

    @pytest.mark.asyncio
    async def test_process_batch_empty_list(
        self, mock_predictor, mock_metrics, mock_settings
    ):
        """
        DADO: Uma lista vazia de requests
        QUANDO: Chamo process_batch
        ENTÃO: Deve retornar BatchPredictResponse vazio
        """
        with patch("src.services.batch_engine.settings", mock_settings):
            engine = BatchInferenceEngine(
                predictor_service=mock_predictor,
                metrics=mock_metrics,
            )

        result = await engine.process_batch([])

        assert result.total_processed == 0
        assert result.successful == 0
        assert result.failed == 0
        assert len(result.results) == 0

    @pytest.mark.asyncio
    async def test_process_batch_single_request(
        self, mock_predictor, mock_metrics, mock_settings
    ):
        """
        DADO: Uma lista com um único request
        QUANDO: Chamo process_batch
        ENTÃO: Deve processar normalmente
        """
        requests = [
            PredictRequest(
                intent_text="Single request",
                specialist_confidence=0.8,
            )
        ]

        with patch("src.services.batch_engine.settings", mock_settings):
            engine = BatchInferenceEngine(
                predictor_service=mock_predictor,
                metrics=mock_metrics,
            )

        result = await engine.process_batch(requests)

        assert result.total_processed == 1
        assert result.successful == 1
        assert len(result.results) == 1

    @pytest.mark.asyncio
    async def test_process_batch_with_threshold_option(
        self, mock_predictor, mock_metrics, mock_settings
    ):
        """
        DADO: Requests com threshold customizado
        QUANDO: Chamo process_batch
        ENTÃO: Deve aplicar threshold nas decisões
        """
        from src.models.schemas import PredictOptions

        requests = [
            PredictRequest(
                intent_text="Low confidence request",
                specialist_confidence=0.3,
                options=PredictOptions(threshold=0.8),
            )
        ]

        mock_predictor.predict.return_value = {
            "decision": "approve",
            "confidence": 0.5,  # Abaixo do threshold
            "probabilities": {"approve": 0.5, "reject": 0.5},
            "model_version": "v7",
        }

        with patch("src.services.batch_engine.settings", mock_settings):
            engine = BatchInferenceEngine(
                predictor_service=mock_predictor,
                metrics=mock_metrics,
            )

        result = await engine.process_batch(requests)

        # Deve ser REVIEW_REQUIRED devido ao threshold
        assert result.results[0].decision == DecisionType.REVIEW_REQUIRED

    @pytest.mark.asyncio
    async def test_process_batch_aggregate_stats(
        self, mock_predictor, mock_metrics, mock_settings
    ):
        """
        DADO: Um batch processado com sucesso
        QUANDO: Chamo process_batch
        ENTÃO: Deve calcular estatísticas agregadas
        """
        requests = [
            PredictRequest(
                intent_text=f"Request {i}",
                specialist_confidence=0.8,
            )
            for i in range(5)
        ]

        with patch("src.services.batch_engine.settings", mock_settings):
            engine = BatchInferenceEngine(
                predictor_service=mock_predictor,
                metrics=mock_metrics,
            )

        result = await engine.process_batch(requests)

        assert result.aggregate_stats is not None
        assert "decision_counts" in result.aggregate_stats
        assert "average_confidence" in result.aggregate_stats
        assert "average_inference_time_ms" in result.aggregate_stats
        assert result.aggregate_stats["average_confidence"] > 0


# ===== TESTES: Predict Single =====


class TestPredictSingle:
    """Testes do método _predict_single."""

    @pytest.mark.asyncio
    async def test_predict_single_basic(
        self, mock_predictor, mock_metrics, mock_settings
    ):
        """
        DADO: Um request válido
        QUANDO: Chamo _predict_single
        ENTÃO: Deve retornar PredictResponse
        """
        request = PredictRequest(
            intent_text="Test request",
            specialist_confidence=0.8,
            specialist_type="technical",
        )

        mock_predictor.predict.return_value = {
            "decision": "approve",
            "confidence": 0.85,
            "probabilities": {"approve": 0.85, "reject": 0.15},
            "model_version": "v7",
        }

        with patch("src.services.batch_engine.settings", mock_settings):
            engine = BatchInferenceEngine(
                predictor_service=mock_predictor,
                metrics=mock_metrics,
            )

        result = await engine._predict_single(request)

        assert isinstance(result, PredictResponse)
        assert result.decision == DecisionType.APPROVE
        assert result.confidence == 0.85
        assert result.model_version == "v7"
        assert result.inference_time_ms >= 0

    @pytest.mark.asyncio
    async def test_predict_single_with_options(
        self, mock_predictor, mock_metrics, mock_settings
    ):
        """
        DADO: Um request com opções
        QUANDO: Chamo _predict_single com return_probabilities=True
        ENTÃO: Deve incluir probabilities na resposta
        """
        from src.models.schemas import PredictOptions

        request = PredictRequest(
            intent_text="Test request",
            specialist_confidence=0.8,
            options=PredictOptions(return_probabilities=True, return_features=False),
        )

        mock_predictor.predict.return_value = {
            "decision": "reject",
            "confidence": 0.3,
            "probabilities": {"approve": 0.3, "reject": 0.7},
            "features": {"feature_1": 0.5, "feature_2": 0.8},
            "model_version": "v7",
        }

        with patch("src.services.batch_engine.settings", mock_settings):
            engine = BatchInferenceEngine(
                predictor_service=mock_predictor,
                metrics=mock_metrics,
            )

        result = await engine._predict_single(request)

        assert result.decision == DecisionType.REJECT
        assert result.probabilities == {"approve": 0.3, "reject": 0.7}
        assert result.features is None  # return_features=False

    @pytest.mark.asyncio
    async def test_predict_single_with_features(
        self, mock_predictor, mock_metrics, mock_settings
    ):
        """
        DADO: Um request com return_features=True
        QUANDO: Chamo _predict_single
        ENTÃO: Deve incluir features na resposta
        """
        from src.models.schemas import PredictOptions

        request = PredictRequest(
            intent_text="Test request",
            specialist_confidence=0.8,
            options=PredictOptions(return_features=True),
        )

        mock_predictor.predict.return_value = {
            "decision": "approve",
            "confidence": 0.85,
            "probabilities": {"approve": 0.85, "reject": 0.15},
            "features": {"text_length": 15, "has_security_keyword": 1.0},
            "model_version": "v7",
        }

        with patch("src.services.batch_engine.settings", mock_settings):
            engine = BatchInferenceEngine(
                predictor_service=mock_predictor,
                metrics=mock_metrics,
            )

        result = await engine._predict_single(request)

        assert result.features == {"text_length": 15, "has_security_keyword": 1.0}


# ===== TESTES: Aggregate Stats =====


class TestCalculateAggregateStats:
    """Testes do método _calculate_aggregate_stats."""

    def test_calculate_aggregate_stats_empty(self, mock_metrics, mock_settings):
        """
        DADO: Uma lista vazia de resultados
        QUANDO: Chamo _calculate_aggregate_stats
        ENTÃO: Deve retornar dict vazio
        """
        with patch("src.services.batch_engine.settings", mock_settings):
            engine = BatchInferenceEngine(
                predictor_service=AsyncMock(),
                metrics=mock_metrics,
            )

        result = engine._calculate_aggregate_stats([])

        assert result == {}

    def test_calculate_aggregate_stats_multiple(self, mock_metrics, mock_settings):
        """
        DADO: Uma lista de PredictResponse
        QUANDO: Chamo _calculate_aggregate_stats
        ENTÃO: Deve calcular estatísticas corretamente
        """
        responses = [
            PredictResponse(
                decision=DecisionType.APPROVE,
                confidence=0.85,
                model_version="v7",
                inference_time_ms=10.0,
            ),
            PredictResponse(
                decision=DecisionType.APPROVE,
                confidence=0.90,
                model_version="v7",
                inference_time_ms=15.0,
            ),
            PredictResponse(
                decision=DecisionType.REJECT,
                confidence=0.30,
                model_version="v7",
                inference_time_ms=8.0,
            ),
        ]

        with patch("src.services.batch_engine.settings", mock_settings):
            engine = BatchInferenceEngine(
                predictor_service=AsyncMock(),
                metrics=mock_metrics,
            )

        result = engine._calculate_aggregate_stats(responses)

        assert result["decision_counts"] == {"approve": 2, "reject": 1}
        assert result["average_confidence"] == pytest.approx(0.6833, rel=1e-3)
        assert result["average_inference_time_ms"] == pytest.approx(11.0, rel=1e-3)
        assert result["total_inference_time_ms"] == 33.0


# ===== TESTES: Context Manager =====


class TestContextManager:
    """Testes do context manager."""

    @pytest.mark.asyncio
    async def test_async_context_manager(self, mock_predictor, mock_metrics):
        """
        DADO: Um BatchInferenceEngine
        QUANDO: Uso como async context manager
        ENTÃO: Deve entrar e sair corretamente
        """
        engine = BatchInferenceEngine(
            predictor_service=mock_predictor,
            metrics=mock_metrics,
        )

        async with engine:
            assert engine is not None

        # Verificar que executor foi limpo (se foi criado)
        assert engine._executor is None or engine._executor._shutdown


# ===== TESTES: Singleton =====


class TestGetBatchEngine:
    """Testes da função get_batch_engine."""

    def test_get_batch_engine_singleton(self, mock_predictor, mock_metrics):
        """
        DADO: PredictorService e métricas
        QUANDO: Chamo get_batch_engine duas vezes
        ENTÃO: Deve retornar a mesma instância
        """
        # Reset singleton
        import src.services.batch_engine as batch_module
        batch_module._batch_engine = None

        engine1 = get_batch_engine(mock_predictor, mock_metrics)
        engine2 = get_batch_engine(mock_predictor, mock_metrics)

        assert engine1 is engine2


# ===== TESTES: Parallel Processing Order =====


class TestParallelProcessingOrder:
    """Testes de ordem no processamento paralelo."""

    @pytest.mark.asyncio
    async def test_parallel_preserves_order(self, mock_metrics, mock_settings):
        """
        DADO: Uma lista de requests
        QUANDO: Processo em paralelo
        ENTÃO: A ordem dos resultados deve corresponder à ordem dos requests
        """
        # Criar mock manualmente
        from unittest.mock import AsyncMock

        predictor = AsyncMock()

        requests = [
            PredictRequest(
                intent_text=f"Request {i}",
                specialist_confidence=0.8,
            )
            for i in range(5)
        ]

        # Mapear intent_text para confidence específica
        confidence_map = {
            "Request 0": 0.81,
            "Request 1": 0.82,
            "Request 2": 0.83,
            "Request 3": 0.84,
            "Request 4": 0.85,
        }

        async def predict_with_confidence(intent_text, specialist_confidence, specialist_type=None):
            # Delay baseado no índice para simular processamento fora de ordem
            idx = int(intent_text.split()[1])
            delay = {0: 0.05, 1: 0.01, 2: 0.03, 3: 0.02, 4: 0.04}.get(idx, 0.01)
            await asyncio.sleep(delay)
            return {
                "decision": "approve",
                "confidence": confidence_map.get(intent_text, 0.8),
                "probabilities": {},
                "model_version": "v7",
            }

        predictor.predict = predict_with_confidence

        with patch("src.services.batch_engine.settings", mock_settings):
            engine = BatchInferenceEngine(
                predictor_service=predictor,
                metrics=mock_metrics,
            )

        result = await engine.process_batch(requests, parallel=True)

        # Verificar ordem pelas confianças
        confidences = [r.confidence for r in result.results]
        expected = [0.81, 0.82, 0.83, 0.84, 0.85]
        assert confidences == expected
