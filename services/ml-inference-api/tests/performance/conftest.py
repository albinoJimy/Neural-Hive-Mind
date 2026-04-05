"""
Configuração e fixtures para testes de performance.

Os targets do spec são:
- Latência p50 < 50ms
- Latência p99 < 200ms
- Throughput > 1000 req/s
- Batch 10x mais eficiente que individual
"""
import os
import sys
from collections.abc import AsyncGenerator, Generator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

# Adicionar src ao path
service_dir = Path(__file__).resolve().parents[2]
src_path = str(service_dir / "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)

# Adicionar ml_pipelines ao path
ml_pipelines_path = str(service_dir.parent / "ml_pipelines")
if ml_pipelines_path not in sys.path:
    sys.path.insert(0, ml_pipelines_path)

# Configurar variáveis de ambiente para testes
os.environ.setdefault("MLFLOW_TRACKING_URI", "http://localhost:5000")
os.environ.setdefault("MODEL_NAME", "approval_model")
os.environ.setdefault("MODEL_VERSION", "Production")
os.environ.setdefault("REDIS_HOST", "localhost")
os.environ.setdefault("REDIS_PORT", "6379")
os.environ.setdefault("REDIS_DB", "0")
os.environ.setdefault("PROMETHEUS_PORT", "9090")
os.environ.setdefault("LOG_LEVEL", "WARNING")  # Reduzir噪音 em testes de performance
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("SERVICE_NAME", "ml-inference-api")
os.environ.setdefault("MAX_BATCH_SIZE", "100")
os.environ.setdefault("DEFAULT_TIMEOUT_MS", "5000")
os.environ.setdefault("CIRCUIT_BREAKER_THRESHOLD", "5")
os.environ.setdefault("CIRCUIT_BREAKER_TIMEOUT_MS", "60000")
os.environ.setdefault("ENABLE_GPU", "false")
os.environ.setdefault("ENABLE_RATE_LIMITING", "false")  # Desabilitar para testes de carga


# Mock do ApprovalPredictor - muito mais rápido que carregar modelo real
class MockApprovalPredictor:
    """Mock rápido do ApprovalPredictor para testes de performance."""

    def __init__(self):
        self.model_info = {
            "name": "approval_model",
            "version": "test_mock",
            "type": "MockModel",
            "features": ["confidence", "risk", "specialist_type_encoded"],
        }

    def predict(self, features: dict) -> tuple[str, float, dict]:
        """Retorna predição determinística baseada em features."""
        # Simular latência de processamento (configurável via env)
        base_latency_ms = float(os.environ.get("MOCK_LATENCY_MS", "1"))
        import time
        time.sleep(base_latency_ms / 1000.0)

        confidence = features.get("confidence", 0.5)
        risk = features.get("risk", 0.5)

        # Lógica determinística
        if confidence > 0.7 and risk < 0.3:
            decision = "approve"
            pred_confidence = 0.85 + (confidence * 0.1)
        elif confidence < 0.3 or risk > 0.7:
            decision = "reject"
            pred_confidence = 0.85 + ((1 - confidence) * 0.1)
        else:
            decision = "review_required"
            pred_confidence = 0.6 + (confidence * 0.2)

        pred_confidence = min(0.99, max(0.51, pred_confidence))

        probabilities = {
            "approve": 0.3 if decision == "reject" else 0.7,
            "reject": 0.3 if decision == "approve" else 0.7,
        }
        probabilities[decision] = pred_confidence

        return decision, pred_confidence, probabilities


@pytest.fixture
def mock_predictor() -> MockApprovalPredictor:
    """Retorna mock do ApprovalPredictor."""
    return MockApprovalPredictor()


@pytest.fixture
def mock_app_state(mock_predictor: MockApprovalPredictor) -> MagicMock:
    """Retorna mock do app.state com predictor e batch engine."""
    from src.services.batch_engine import BatchInferenceEngine

    state = MagicMock()

    # Mock do predictor service
    predictor_service = MagicMock()
    predictor_service.predict = AsyncMock(
        side_effect=lambda intent_text, specialist_confidence, specialist_type: {
            "decision": "approve" if specialist_confidence > 0.5 else "review_required",
            "confidence": 0.8,
            "probabilities": {"approve": 0.8, "reject": 0.2},
            "model_version": "test_mock",
        }
    )
    predictor_service.model_info = mock_predictor.model_info
    predictor_service.reset_circuit_breaker = MagicMock()

    state.predictor_service = predictor_service

    # Mock do batch engine - sem métricas Prometheus para evitar duplicação
    batch_engine = BatchInferenceEngine(predictor_service, metrics=None)
    state.batch_engine = batch_engine

    # Mock do limiter
    state.limiter = None

    # Mock das métricas
    state.metrics = None

    return state


@pytest.fixture
async def performance_client(mock_app_state: MagicMock) -> AsyncGenerator[AsyncClient, None]:
    """
    Retorna cliente HTTP assíncrono para testes de performance.

    Usa um app FastAPI simplificado com mocks para máxima velocidade.
    """
    import httpx
    from fastapi import FastAPI

    from src.api.inference import router as inference_router

    app = FastAPI()
    app.state = mock_app_state
    app.include_router(inference_router)

    # Usar ASGITransport para httpx
    from httpx import ASGITransport

    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
def sample_request_data() -> dict:
    """Retorna dados de request padrão para testes."""
    return {
        "intent_text": "Analisar approval de plano cognitivo para tarefa de análise de dados",
        "specialist_confidence": 0.75,
        "specialist_type": "analyst",
        "options": {
            "return_probabilities": True,
            "return_features": False,
        },
    }


@pytest.fixture
def batch_request_factory(sample_request_data: dict) -> callable:
    """
    Factory para criar batch requests de diferentes tamanhos.

    Args:
        sample_request_data: Template de request

    Returns:
        Função que recebe tamanho e retorna lista de requests
    """
    def create_batch(size: int) -> list[dict]:
        """Cria batch de requests com dados variados."""
        batch = []
        for i in range(size):
            data = sample_request_data.copy()
            # Variar dados para simular requests reais
            data["specialist_confidence"] = 0.3 + (i % 7) * 0.1
            data["intent_text"] = f"Request {i}: {data['intent_text']}"
            batch.append(data)
        return batch

    return create_batch


# Classes auxiliares para medição de latência
class LatencyMetrics:
    """Coletor de métricas de latência."""

    def __init__(self):
        self.latencies: list[float] = []

    def add(self, latency_ms: float) -> None:
        """Adiciona latência em ms."""
        self.latencies.append(latency_ms)

    def p50(self) -> float:
        """Retorna latência p50 (mediana)."""
        if not self.latencies:
            return 0.0
        sorted_latencies = sorted(self.latencies)
        return sorted_latencies[len(sorted_latencies) // 2]

    def p95(self) -> float:
        """Retorna latência p95."""
        if not self.latencies:
            return 0.0
        sorted_latencies = sorted(self.latencies)
        idx = int(len(sorted_latencies) * 0.95)
        return sorted_latencies[min(idx, len(sorted_latencies) - 1)]

    def p99(self) -> float:
        """Retorna latência p99."""
        if not self.latencies:
            return 0.0
        sorted_latencies = sorted(self.latencies)
        idx = int(len(sorted_latencies) * 0.99)
        return sorted_latencies[min(idx, len(sorted_latencies) - 1)]

    def avg(self) -> float:
        """Retorna latência média."""
        if not self.latencies:
            return 0.0
        return sum(self.latencies) / len(self.latencies)

    def min(self) -> float:
        """Retorna latência mínima."""
        if not self.latencies:
            return 0.0
        return min(self.latencies)

    def max(self) -> float:
        """Retorna latência máxima."""
        if not self.latencies:
            return 0.0
        return max(self.latencies)

    def count(self) -> int:
        """Retorna número de medições."""
        return len(self.latencies)


@pytest.fixture
def latency_metrics() -> LatencyMetrics:
    """Retorna coletor de métricas de latência."""
    return LatencyMetrics()


# Targets de performance do spec
@pytest.fixture
def performance_targets() -> dict:
    """
    Retorna os alvos de performance definidos no spec.

    ML-001-08: Performance Tests
    - Latência p50 < 50ms
    - Latência p99 < 200ms
    - Throughput > 1000 req/s
    - Batch 10x mais eficiente que individual
    """
    return {
        "latency_p50_max_ms": 50,
        "latency_p95_max_ms": 100,
        "latency_p99_max_ms": 200,
        "throughput_min_req_per_sec": 1000,
        "batch_efficiency_ratio": 10,  # batch deve ser 10x mais eficiente
    }


@pytest.fixture
def memory_profiler() -> Generator:
    """
    Fixture para profiling de memória.

    Requer 'memory_profiler' instalado.
    """
    try:
        from memory_profiler import memory_usage

        def profile(func, *args, **kwargs):
            """Executa função e retorna uso de memória."""
            mem_usage, result = memory_usage(
                (func, args, kwargs),
                retval=True,
                interval=0.01,
                timeout=None,
            )
            return {
                "max_mb": max(mem_usage),
                "min_mb": min(mem_usage),
                "avg_mb": sum(mem_usage) / len(mem_usage),
                "result": result,
            }

        yield profile
    except ImportError:
        pytest.skip("memory_profiler não instalado - pip install memory_profiler")
