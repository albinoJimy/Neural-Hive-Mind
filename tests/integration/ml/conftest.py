# -*- coding: utf-8 -*-
"""
Fixtures específicas para testes de integração ML.

Configura MongoDB, MLflow e componentes do pipeline de promoção
para testes de integração.
"""

import asyncio
import os
import tempfile
import uuid
import datetime
from typing import Dict, Any
from unittest.mock import AsyncMock, MagicMock
from dataclasses import dataclass

import numpy as np
import pytest
from motor.motor_asyncio import AsyncIOMotorClient

# Importações do projeto - com fallback para mocks
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'services', 'orchestrator-dynamic', 'src'))

try:
    from ml.shadow_mode import ShadowModeRunner
except ImportError:
    ShadowModeRunner = None

try:
    from ml.model_promotion import (
        ModelPromotionManager,
        PromotionConfig,
        PromotionRequest,
        PromotionStage,
        PromotionResult
    )
except ImportError:
    ModelPromotionManager = None
    PromotionConfig = None
    PromotionRequest = None
    PromotionStage = None
    PromotionResult = None

try:
    from ml.continuous_validator import ContinuousValidator
except ImportError:
    ContinuousValidator = None


# Dataclass local para configuração de shadow mode em testes
@dataclass
class ShadowConfig:
    """Configuração de shadow mode para testes."""
    model_name: str
    shadow_model_version: str
    production_model_version: str
    min_predictions: int = 50
    agreement_threshold: float = 0.90
    duration_minutes: float = 0.1
    comparison_tolerance: float = 0.15


# =============================================================================
# Configurações de ambiente para testes
# =============================================================================

@pytest.fixture(scope="session")
def event_loop():
    """Cria event loop para testes assíncronos."""
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def mongodb_uri() -> str:
    """URI do MongoDB para testes."""
    return os.getenv("MONGODB_URI", "mongodb://localhost:27017")


@pytest.fixture(scope="session")
def mongodb_test_db_name() -> str:
    """Nome do banco de dados de teste."""
    return f"test_ml_integration_{uuid.uuid4().hex[:8]}"


# =============================================================================
# Fixtures de MongoDB
# =============================================================================

class MongoDBTestClient:
    """Cliente MongoDB para testes."""
    def __init__(self, client, db):
        self.client = client
        self.db = db


def _check_mongodb_available(uri: str, timeout: float = 2.0) -> bool:
    """Verifica se MongoDB está disponível."""
    try:
        from pymongo import MongoClient
        from pymongo.errors import ServerSelectionTimeoutError

        client = MongoClient(uri, serverSelectionTimeoutMS=int(timeout * 1000))
        client.admin.command('ping')
        client.close()
        return True
    except Exception:
        return False


@pytest.fixture(scope="session")
def mongodb_ml_client(mongodb_uri: str, mongodb_test_db_name: str, event_loop):
    """
    Cliente MongoDB para coleções ML.
    """
    # Verifica se MongoDB está disponível
    if not _check_mongodb_available(mongodb_uri):
        pytest.skip(f"MongoDB não disponível em {mongodb_uri}")

    client = AsyncIOMotorClient(mongodb_uri)
    db = client[mongodb_test_db_name]

    # Cria índices para as coleções de forma síncrona
    async def setup_indexes():
        await db['model_predictions'].create_index([('model_name', 1), ('timestamp', -1)])
        await db['shadow_mode_comparisons'].create_index([('model_name', 1), ('created_at', -1)])
        await db['model_audit_log'].create_index([('model_name', 1), ('event_type', 1)])
        await db['validation_metrics'].create_index([('model_name', 1), ('metric_name', 1)])

    event_loop.run_until_complete(setup_indexes())

    mongo_client = MongoDBTestClient(client, db)

    yield mongo_client

    # Cleanup: remove banco de dados de teste
    async def cleanup():
        await client.drop_database(mongodb_test_db_name)

    event_loop.run_until_complete(cleanup())
    client.close()


@pytest.fixture
def clean_ml_collections(mongodb_ml_client, event_loop):
    """Limpa coleções ML antes de cada teste."""
    collections = [
        'model_predictions',
        'shadow_mode_comparisons',
        'model_audit_log',
        'validation_metrics'
    ]

    async def clean():
        for collection in collections:
            await mongodb_ml_client.db[collection].delete_many({})

    event_loop.run_until_complete(clean())

    yield

    # Limpa após o teste também
    event_loop.run_until_complete(clean())


# =============================================================================
# Fixtures de MLflow
# =============================================================================

@pytest.fixture(scope="session")
def mlflow_test_tracking_uri():
    """
    Cria diretório temporário para tracking do MLflow.
    """
    temp_dir = tempfile.mkdtemp(prefix="mlflow_test_")
    tracking_uri = f"file://{temp_dir}"

    yield tracking_uri

    # Cleanup
    import shutil
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture(scope="session")
def mlflow_test_client(mlflow_test_tracking_uri: str):
    """
    Cliente MLflow configurado para testes.
    """
    try:
        import mlflow
        from mlflow.tracking import MlflowClient

        mlflow.set_tracking_uri(mlflow_test_tracking_uri)
        client = MlflowClient(tracking_uri=mlflow_test_tracking_uri)

        # Cria experimento de teste
        experiment_name = "test_model_promotion"
        try:
            client.create_experiment(experiment_name)
        except Exception:
            pass

        try:
            mlflow.set_experiment(experiment_name)
        except Exception:
            pass

        yield client
    except ImportError:
        # MLflow não instalado - retorna mock
        yield MagicMock()


# =============================================================================
# Fixtures de Modelos ML
# =============================================================================

@pytest.fixture
def mock_duration_predictor():
    """
    RandomForestRegressor treinado para predição de duração.
    """
    from sklearn.ensemble import RandomForestRegressor

    np.random.seed(42)
    X_train = np.random.rand(1000, 3)
    y_train = (X_train[:, 0] * 5000 + X_train[:, 1] * 2000 +
               X_train[:, 2] * 3000 + np.random.randn(1000) * 500)

    model = RandomForestRegressor(n_estimators=10, random_state=42)
    model.fit(X_train, y_train)

    return model


@pytest.fixture
def mock_duration_predictor_v2():
    """
    Modelo v2 para testar acordo no shadow mode.
    """
    from sklearn.ensemble import RandomForestRegressor

    np.random.seed(43)
    X_train = np.random.rand(1000, 3)
    y_train = (X_train[:, 0] * 5000 + X_train[:, 1] * 2000 +
               X_train[:, 2] * 3000 + np.random.randn(1000) * 500)

    model = RandomForestRegressor(n_estimators=10, random_state=43)
    model.fit(X_train, y_train)

    return model


@pytest.fixture
def mock_anomaly_detector():
    """
    IsolationForest treinado para detecção de anomalias.
    """
    from sklearn.ensemble import IsolationForest

    np.random.seed(42)
    X_train = np.random.randn(1000, 5)

    model = IsolationForest(contamination=0.1, random_state=42)
    model.fit(X_train)

    return model


@pytest.fixture
def test_features_dataset():
    """
    Dataset sintético de features para predições.
    """
    import pandas as pd

    np.random.seed(42)
    n_samples = 1000

    df = pd.DataFrame({
        'task_type_encoded': np.random.randint(0, 5, n_samples),
        'payload_size': np.random.randint(100, 10000, n_samples),
        'complexity_score': np.random.rand(n_samples),
        'priority': np.random.randint(1, 10, n_samples),
        'estimated_duration_ms': np.random.randint(1000, 60000, n_samples)
    })

    return df


# =============================================================================
# Fixtures de Componentes ML
# =============================================================================

@pytest.fixture
def model_registry_test(mlflow_test_client):
    """
    ModelRegistry configurado para testes.
    """
    registry = MagicMock()
    registry.get_current_version = AsyncMock(return_value="v1.0")
    registry.get_model = AsyncMock()
    registry.register_model = AsyncMock()
    registry.promote_model = AsyncMock()
    registry.load_model = AsyncMock()
    registry.get_model_metadata = AsyncMock(return_value={'metrics': {'mae_percentage': 10.0}})

    return registry


@pytest.fixture
def continuous_validator_test(mongodb_ml_client, clean_ml_collections):
    """
    ContinuousValidator com MongoDB de teste.
    """
    validator = MagicMock()

    validator.validate_model = AsyncMock(return_value={
        'is_valid': True,
        'mae_percentage': 9.0,
        'precision': 0.82,
        'error_rate': 0.001,
        'degradation_detected': False
    })

    validator.check_degradation = AsyncMock(return_value={
        'degraded': False,
        'metrics': {
            'mae_change_percent': 5.0,
            'precision_change': -0.02,
            'error_rate_change': 0.0005
        }
    })

    validator.get_baseline_metrics = AsyncMock(return_value={
        'mae_percentage': 10.0,
        'precision': 0.80,
        'error_rate': 0.002
    })

    validator.get_current_metrics = AsyncMock(return_value={
        'prediction_metrics': {
            '24h': {
                'mae': 5000,
                'mae_pct': 10.0,
                'r2': 0.85,
                'sample_count': 1000
            }
        },
        'latency_metrics': {
            '24h': {
                'p50': 50,
                'p95': 150,
                'p99': 300,
                'error_rate': 0.001
            }
        }
    })

    return validator


@pytest.fixture
def shadow_runner_test(mongodb_ml_client, clean_ml_collections):
    """
    ShadowModeRunner configurado para testes rápidos.
    """
    config = ShadowConfig(
        model_name="test_duration_predictor",
        shadow_model_version="v2.0",
        production_model_version="v1.0",
        min_predictions=50,
        agreement_threshold=0.90,
        duration_minutes=0.1,
        comparison_tolerance=0.15
    )

    runner = MagicMock()
    runner.config = config
    runner.is_running = False
    runner.model_name = "test_duration_predictor"
    runner.shadow_version = "v2.0"

    runner.start = AsyncMock()
    runner.stop = AsyncMock()
    runner.close = AsyncMock()
    runner.get_agreement_stats = MagicMock(return_value={
        'agreement_rate': 0.95,
        'prediction_count': 100,
        'avg_latency_ms': 50.0,
        'disagreement_count': 5
    })
    runner.compare_prediction = AsyncMock(return_value={
        'agreed': True,
        'production_prediction': 5000,
        'shadow_prediction': 5100,
        'diff_percent': 2.0
    })

    return runner


@pytest.fixture
def promotion_manager_test(
    model_registry_test,
    continuous_validator_test,
    mongodb_ml_client,
    clean_ml_collections
):
    """
    ModelPromotionManager configurado para testes.
    """
    manager = MagicMock()

    manager.model_registry = model_registry_test
    manager.continuous_validator = continuous_validator_test
    manager.mongodb_client = mongodb_ml_client

    manager._shadow_runners = {}
    manager._active_promotions = {}

    manager.promote_model = AsyncMock()
    manager.rollback_model = AsyncMock()
    manager.get_promotion_status = AsyncMock()
    manager.cancel_promotion = AsyncMock()
    manager.get_shadow_runner = MagicMock()

    return manager


# =============================================================================
# Fixtures de Dados de Teste
# =============================================================================

@pytest.fixture
def seed_baseline_metrics(mongodb_ml_client, clean_ml_collections, event_loop) -> Dict[str, Any]:
    """
    Popula MongoDB com métricas baseline de predição.
    """
    np.random.seed(42)

    predictions = []
    base_time = datetime.datetime.utcnow() - datetime.timedelta(days=7)

    for i in range(1000):
        actual = np.random.randint(1000, 60000)
        predicted = actual + np.random.randn() * actual * 0.1

        predictions.append({
            'model_name': 'duration_predictor',
            'model_version': 'v1.0',
            'actual_value': actual,
            'predicted_value': predicted,
            'error_percent': abs(actual - predicted) / actual * 100,
            'timestamp': base_time + datetime.timedelta(minutes=i),
            'task_type': f'type_{i % 5}'
        })

    async def insert():
        await mongodb_ml_client.db['model_predictions'].insert_many(predictions)

    event_loop.run_until_complete(insert())

    errors = [p['error_percent'] for p in predictions]
    baseline = {
        'mae_percentage': np.mean(errors),
        'precision': 0.80,
        'error_rate': 0.002,
        'prediction_count': len(predictions)
    }

    return baseline


@pytest.fixture
def seed_shadow_comparisons(mongodb_ml_client, clean_ml_collections, event_loop) -> Dict[str, Any]:
    """
    Popula MongoDB com comparações de shadow mode.
    """
    np.random.seed(42)

    comparisons = []
    base_time = datetime.datetime.utcnow() - datetime.timedelta(hours=1)

    agreements = 0
    for i in range(100):
        prod_pred = np.random.randint(1000, 60000)
        shadow_pred = prod_pred * (1 + np.random.randn() * 0.05)
        diff_percent = abs(prod_pred - shadow_pred) / prod_pred * 100
        agreed = diff_percent < 15

        if agreed:
            agreements += 1

        comparisons.append({
            'model_name': 'duration_predictor',
            'production_version': 'v1.0',
            'shadow_version': 'v2.0',
            'production_prediction': prod_pred,
            'shadow_prediction': shadow_pred,
            'diff_percent': diff_percent,
            'agreed': agreed,
            'created_at': base_time + datetime.timedelta(seconds=i * 10)
        })

    async def insert():
        await mongodb_ml_client.db['shadow_mode_comparisons'].insert_many(comparisons)

    event_loop.run_until_complete(insert())

    return {
        'total_comparisons': len(comparisons),
        'agreement_count': agreements,
        'agreement_rate': agreements / len(comparisons)
    }


# =============================================================================
# Fixtures de Promoção
# =============================================================================

@pytest.fixture
def promotion_config_fast() -> Dict[str, Any]:
    """
    Configuração de promoção com timeouts rápidos para testes.
    """
    return {
        'shadow_mode_enabled': True,
        'shadow_mode_duration_minutes': 0.1,
        'shadow_mode_min_predictions': 50,
        'shadow_mode_agreement_threshold': 0.90,
        'canary_enabled': True,
        'canary_duration_minutes': 0.1,
        'canary_traffic_pct': 10.0,
        'gradual_rollout_enabled': True,
        'rollout_stages': [0.25, 0.50, 0.75, 1.0],
        'checkpoint_duration_minutes': 0.05,
        'auto_rollback_enabled': True,
        'rollback_mae_increase_pct': 20.0,
        'checkpoint_error_rate_threshold': 0.001
    }


@pytest.fixture
def promotion_request_sample(promotion_config_fast) -> Dict[str, Any]:
    """
    Requisição de promoção de exemplo.
    """
    return {
        'request_id': f"test_promotion_{uuid.uuid4().hex[:8]}",
        'model_name': "duration_predictor",
        'source_version': "v2.0",
        'target_stage': "production",
        'config': promotion_config_fast,
        'initiated_by': "test_user"
    }


# =============================================================================
# Markers de Pytest
# =============================================================================

def pytest_configure(config):
    """Registra markers personalizados."""
    config.addinivalue_line(
        "markers", "ml: marca testes específicos de ML"
    )
    config.addinivalue_line(
        "markers", "ml_integration: marca testes de integração ML"
    )
    config.addinivalue_line(
        "markers", "ml_promotion: marca testes do pipeline de promoção"
    )
    config.addinivalue_line(
        "markers", "slow_ml: marca testes ML lentos (>30 segundos)"
    )
