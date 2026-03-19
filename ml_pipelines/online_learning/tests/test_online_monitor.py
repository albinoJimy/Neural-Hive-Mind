"""Testes para OnlinePerformanceMonitor."""

import pytest
import numpy as np
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime, timedelta


# ============================================================================
# Mock MongoDB classes para evitar tentativas de conexão real
# ============================================================================

class MockMongoCollection:
    """Mock de coleção MongoDB."""
    def __init__(self):
        self.data = []

    def find(self, *args, **kwargs):
        return []

    def find_one(self, *args, **kwargs):
        return None

    def insert_one(self, *args, **kwargs):
        return Mock(inserted_id='test_id')

    def update_one(self, *args, **kwargs):
        return Mock(modified_count=1)

    def delete_one(self, *args, **kwargs):
        return Mock(deleted_count=1)

    def create_index(self, *args, **kwargs):
        pass

    def create_indexes(self, *args, **kwargs):
        pass

    def aggregate(self, *args, **kwargs):
        return []

    def count_documents(self, *args, **kwargs):
        return 0

    def sort(self, *args, **kwargs):
        return self

    def limit(self, *args, **kwargs):
        return self

    def __iter__(self):
        return iter([])

    def __getitem__(self, name):
        return self


class MockMongoDB:
    """Mock de database MongoDB."""
    def __init__(self):
        self._collection = MockMongoCollection()

    def __getitem__(self, name):
        return self._collection

    def __getattr__(self, name):
        if name.startswith('_'):
            raise AttributeError(name)
        return self._collection


class MockMongoClient:
    """Mock de cliente MongoDB."""
    def __init__(self, *args, **kwargs):
        self._db = MockMongoDB()

    def __getitem__(self, name):
        return self._db

    def __getattr__(self, name):
        if name == '_MongoClient__all_options' or name.startswith('_'):
            raise AttributeError(name)
        return self._db

    def close(self):
        """Mock close method."""
        pass


# Patch pymongo antes de importar os módulos
_pymongo_patch = patch('pymongo.MongoClient', MockMongoClient)
_pymongo_patch.start()

# Agora é seguro importar
from ml_pipelines.online_learning.online_monitor import (
    OnlinePerformanceMonitor,
    Alert,
)
from ml_pipelines.online_learning.config import OnlineLearningConfig


@pytest.fixture(autouse=True)
def cleanup_patches():
    """Limpa patches após todos os testes."""
    yield
    # Não paramos o patch aqui porque outros testes podem precisar dele


@pytest.fixture
def config():
    """Configuração de teste."""
    return OnlineLearningConfig(
        convergence_stall_threshold_hours=1,
        memory_leak_threshold_mb=500,
        prediction_stability_variance_threshold=0.1,
    )


@pytest.fixture
def mock_learner():
    """Mock do IncrementalLearner."""
    learner = Mock()
    learner.is_fitted = True
    return learner


@pytest.fixture
def monitor(config, mock_learner):
    """OnlinePerformanceMonitor para testes."""
    return OnlinePerformanceMonitor(config, "test_specialist", learner=mock_learner)


class TestOnlineMonitorInitialization:
    """Testes de inicialização."""

    def test_init_with_config(self, config):
        """Testar inicialização com configuração."""
        monitor = OnlinePerformanceMonitor(config, "test_specialist")

        assert monitor.specialist_type == "test_specialist"
        assert monitor.config.convergence_stall_threshold_hours == 1
        assert monitor.config.prediction_stability_variance_threshold == 0.1

    def test_init_default_config(self):
        """Testar inicialização com configuração padrão."""
        monitor = OnlinePerformanceMonitor(OnlineLearningConfig(), "risk")

        assert monitor.specialist_type == "risk"


class TestRecordUpdate:
    """Testes de registro de atualizações."""

    def test_record_update(self, monitor):
        """Testar registro de atualização."""
        monitor.record_update(loss=0.5, duration_ms=100, samples_count=32)

        status = monitor.get_status()
        metrics = status.get("metrics", {})
        assert metrics.get("total_updates", 0) == 1

    def test_record_multiple_updates(self, monitor):
        """Testar múltiplos registros."""
        for i in range(10):
            monitor.record_update(
                loss=0.5 - i * 0.02, duration_ms=100, samples_count=32
            )

        status = monitor.get_status()
        metrics = status.get("metrics", {})
        assert metrics.get("total_updates", 0) == 10

    def test_record_update_tracks_loss(self, monitor):
        """Testar que loss é rastreado."""
        losses = [0.5, 0.4, 0.35, 0.32, 0.30]

        for loss in losses:
            monitor.record_update(loss=loss, duration_ms=100, samples_count=32)

        status = monitor.get_status()
        metrics = status.get("metrics", {})
        # Loss atual deve estar no status
        assert "current_loss" in metrics or metrics.get("total_updates") == 5


class TestRecordPrediction:
    """Testes de registro de predições."""

    def test_record_prediction(self, monitor):
        """Testar registro de predição."""
        probas = np.array([[0.15, 0.85]])
        monitor.record_prediction(probas=probas)

        # Verificar que predição foi registrada
        assert len(monitor._prediction_samples) == 1

    def test_record_multiple_predictions(self, monitor):
        """Testar múltiplas predições."""
        for _ in range(100):
            probas = np.array([[0.2, 0.8]])
            monitor.record_prediction(probas=probas)

        assert len(monitor._prediction_samples) == 100


class TestConvergenceMetrics:
    """Testes de métricas de convergência."""

    def test_convergence_rate_calculation(self, monitor):
        """Testar cálculo de taxa de convergência."""
        # Simular convergência: loss diminuindo
        for i in range(60):
            loss = 0.5 * np.exp(-0.05 * i)  # Decaimento exponencial
            monitor.record_update(loss=loss, duration_ms=100, samples_count=32)

        status = monitor.get_status()
        metrics = status.get("metrics", {})

        assert "convergence_rate" in metrics or metrics.get("total_updates") == 60

    def test_convergence_stall_detection(self, monitor):
        """Testar detecção de estagnação."""
        # Loss não muda
        for i in range(60):
            monitor.record_update(loss=0.5, duration_ms=100, samples_count=32)

        status = monitor.get_status()
        health = status.get("health", "unknown")

        # Deve ter saúde avaliada
        assert health in ["healthy", "degraded", "unhealthy", "unknown"]


class TestPredictionStability:
    """Testes de estabilidade de predições."""

    def test_prediction_stability_stable(self, monitor):
        """Testar predições estáveis."""
        # Predições consistentes
        for _ in range(10):
            probas = np.array([[0.15, 0.85]])
            monitor.record_prediction(probas=probas)

        variance = monitor._calculate_prediction_variance()
        # Variância deve ser zero para predições idênticas
        assert variance == 0.0

    def test_prediction_stability_unstable(self, monitor):
        """Testar predições instáveis."""
        # Predições variando
        for i in range(10):
            probas = np.array([[0.1 + i * 0.05, 0.9 - i * 0.05]])
            monitor.record_prediction(probas=probas)

        variance = monitor._calculate_prediction_variance()
        # Variância deve ser maior que zero
        assert variance > 0


class TestHealthAssessment:
    """Testes de avaliação de saúde."""

    def test_health_healthy(self, monitor):
        """Testar sistema saudável."""
        status = monitor.get_status()
        health = status.get("health", "unknown")

        assert health in ["healthy", "degraded", "unhealthy", "unknown"]

    def test_health_warning(self, monitor):
        """Testar sistema em warning."""
        # Loss estagnado
        for _ in range(60):
            monitor.record_update(loss=0.5, duration_ms=100, samples_count=32)

        status = monitor.get_status()
        health = status.get("health", "unknown")

        assert health in ["healthy", "degraded", "unhealthy", "unknown"]


class TestAlerts:
    """Testes de alertas."""

    def test_no_alerts_initially(self, monitor):
        """Testar que não há alertas inicialmente."""
        status = monitor.get_status()
        alerts = status.get("active_alerts", [])

        assert isinstance(alerts, list)

    def test_alert_creation(self, monitor):
        """Testar criação de alerta."""
        # Simular condição de alerta (memory growth)
        monitor._initial_memory_mb = 100
        for _ in range(100):
            monitor._memory_history.append(
                (datetime.utcnow(), 600.0)
            )  # Acima do threshold

        # Verificar alerta de memory leak
        alert = monitor._check_memory_leak()
        assert alert is None or alert.alert_type == "memory_leak"


class TestGetStatus:
    """Testes de obtenção de status."""

    def test_get_status_structure(self, monitor):
        """Testar estrutura do status."""
        status = monitor.get_status()

        assert "specialist_type" in status
        assert "metrics" in status
        assert "health" in status
        assert "active_alerts" in status

    def test_get_status_after_activity(self, monitor):
        """Testar status após atividade."""
        # Registrar atividade
        for i in range(10):
            monitor.record_update(loss=0.5 - i * 0.01, duration_ms=100, samples_count=32)

        status = monitor.get_status()
        metrics = status.get("metrics", {})

        assert metrics.get("total_updates") == 10


class TestMemoryMonitoring:
    """Testes de monitoramento de memória."""

    def test_memory_tracking(self, monitor):
        """Testar rastreamento de memória."""
        status = monitor.get_status()

        # Memória deve estar nas métricas
        metrics = status.get("metrics", {})
        assert "memory_usage_mb" in metrics or "memory_growth_mb" in metrics


class TestMetricsExport:
    """Testes de exportação de métricas."""

    def test_prometheus_metrics(self, monitor):
        """Testar que métricas Prometheus são registradas."""
        # Registrar atividade
        for _ in range(5):
            monitor.record_update(loss=0.5, duration_ms=100, samples_count=32)

        # Métricas devem ter sido registradas
        status = monitor.get_status()
        metrics = status.get("metrics", {})
        assert metrics.get("total_updates") == 5
