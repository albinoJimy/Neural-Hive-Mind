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
# Fixtures de MongoDB (with mongomock fallback)
# =============================================================================

class MongoDBTestClient:
    """Cliente MongoDB para testes."""
    def __init__(self, client, db):
        self.client = client
        self.db = db


class AsyncMockCollection:
    """Wrapper assíncrono para coleção do mongomock."""

    def __init__(self, collection):
        self._collection = collection

    async def insert_one(self, document):
        return self._collection.insert_one(document)

    async def insert_many(self, documents):
        return self._collection.insert_many(documents)

    async def find_one(self, filter=None, *args, **kwargs):
        return self._collection.find_one(filter, *args, **kwargs)

    def find(self, filter=None, *args, **kwargs):
        return AsyncMockCursor(self._collection.find(filter, *args, **kwargs))

    async def count_documents(self, filter):
        return self._collection.count_documents(filter)

    async def delete_many(self, filter):
        return self._collection.delete_many(filter)

    async def create_index(self, keys, **kwargs):
        return self._collection.create_index(keys, **kwargs)

    def aggregate(self, pipeline, *args, **kwargs):
        return AsyncMockCursor(self._collection.aggregate(pipeline, *args, **kwargs))


class AsyncMockCursor:
    """Wrapper assíncrono para cursor do mongomock."""

    def __init__(self, cursor):
        self._cursor = cursor
        self._items = list(cursor) if hasattr(cursor, '__iter__') else []

    def sort(self, *args, **kwargs):
        # Para mongomock, sort retorna o mesmo cursor
        try:
            sorted_cursor = self._cursor.sort(*args, **kwargs)
            return AsyncMockCursor(sorted_cursor)
        except:
            return self

    def limit(self, n):
        self._items = self._items[:n]
        return self

    async def to_list(self, length=None):
        if length:
            return self._items[:length]
        return self._items


class AsyncMockDatabase:
    """Wrapper assíncrono para database do mongomock."""

    def __init__(self, db):
        self._db = db
        self._collections = {}

    def __getitem__(self, name):
        if name not in self._collections:
            self._collections[name] = AsyncMockCollection(self._db[name])
        return self._collections[name]


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


def _create_mongomock_client(db_name: str):
    """Cria cliente mongomock para testes sem MongoDB real."""
    try:
        import mongomock
        client = mongomock.MongoClient()
        db = client[db_name]

        # Cria índices (mongomock suporta)
        db['model_predictions'].create_index([('model_name', 1), ('timestamp', -1)])
        db['shadow_mode_comparisons'].create_index([('model_name', 1), ('created_at', -1)])
        db['model_audit_log'].create_index([('model_name', 1), ('event_type', 1)])
        db['validation_metrics'].create_index([('model_name', 1), ('metric_name', 1)])
        db['ml_promotions'].create_index([('model_name', 1), ('request_id', 1)])

        return client, db
    except ImportError:
        return None, None


@pytest.fixture(scope="session")
def mongodb_ml_client(mongodb_uri: str, mongodb_test_db_name: str, event_loop):
    """
    Cliente MongoDB para coleções ML.

    Usa MongoDB real se disponível, senão usa mongomock como fallback.
    """
    # Verifica se MongoDB real está disponível
    if _check_mongodb_available(mongodb_uri):
        # Usa MongoDB real
        client = AsyncIOMotorClient(mongodb_uri)
        db = client[mongodb_test_db_name]

        # Cria índices para as coleções de forma síncrona
        async def setup_indexes():
            await db['model_predictions'].create_index([('model_name', 1), ('timestamp', -1)])
            await db['shadow_mode_comparisons'].create_index([('model_name', 1), ('created_at', -1)])
            await db['model_audit_log'].create_index([('model_name', 1), ('event_type', 1)])
            await db['validation_metrics'].create_index([('model_name', 1), ('metric_name', 1)])
            await db['ml_promotions'].create_index([('model_name', 1), ('request_id', 1)])

        event_loop.run_until_complete(setup_indexes())

        mongo_client = MongoDBTestClient(client, db)

        yield mongo_client

        # Cleanup: remove banco de dados de teste
        async def cleanup():
            await client.drop_database(mongodb_test_db_name)

        event_loop.run_until_complete(cleanup())
        client.close()
    else:
        # Usa mongomock como fallback
        mock_client, mock_db = _create_mongomock_client(mongodb_test_db_name)

        if mock_client is None:
            pytest.skip("MongoDB não disponível e mongomock não instalado")

        # Cria wrapper assíncrono
        async_db = AsyncMockDatabase(mock_db)
        mongo_client = MongoDBTestClient(mock_client, async_db)

        yield mongo_client

        # Cleanup mongomock
        mock_client.close()


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
# Fixtures de Componentes ML (Real Instances)
# =============================================================================

try:
    from ml.model_registry import ModelRegistry
except ImportError:
    ModelRegistry = None


@dataclass
class TestConfig:
    """Configuração de teste para componentes ML."""
    # Shadow Mode
    ml_shadow_mode_enabled: bool = True
    ml_shadow_mode_duration_minutes: float = 0.01  # 0.6 segundos para testes
    ml_shadow_mode_min_predictions: int = 10  # Baixo para testes rápidos
    ml_shadow_mode_agreement_threshold: float = 0.90
    ml_shadow_model_version: str = "v2.0"
    # Canary
    ml_canary_enabled: bool = True
    ml_canary_traffic_percentage: float = 10.0
    ml_canary_duration_minutes: float = 0.01  # 0.6 segundos
    ml_validation_mae_threshold: float = 0.15
    ml_validation_precision_threshold: float = 0.75
    ml_auto_rollback_enabled: bool = True
    ml_rollback_mae_increase_pct: float = 20.0
    # Gradual Rollout
    ml_gradual_rollout_enabled: bool = True
    ml_rollout_stages: list = None
    ml_checkpoint_duration_minutes: float = 0.01  # 0.6 segundos
    ml_checkpoint_mae_threshold_pct: float = 20.0
    ml_checkpoint_error_rate_threshold: float = 0.001
    # Validation
    ml_validation_use_mongodb: bool = True
    ml_validation_mongodb_collection: str = 'model_predictions'
    ml_validation_windows: list = None
    ml_validation_latency_enabled: bool = True
    ml_validation_alert_cooldown_minutes: int = 1

    def __post_init__(self):
        if self.ml_rollout_stages is None:
            self.ml_rollout_stages = [0.25, 0.50, 0.75, 1.0]
        if self.ml_validation_windows is None:
            self.ml_validation_windows = ['1h', '24h']


@pytest.fixture
def test_config() -> TestConfig:
    """Configuração de teste para componentes ML."""
    return TestConfig()


@pytest.fixture
def model_registry_test(mlflow_test_client, mlflow_test_tracking_uri, mock_duration_predictor, mock_duration_predictor_v2):
    """
    ModelRegistry real configurado para testes com MLflow de teste.
    """
    try:
        import mlflow
        from mlflow.tracking import MlflowClient
    except ImportError:
        pytest.skip("MLflow não disponível")

    # Registra modelos de teste no MLflow
    experiment_name = "test_model_promotion"
    try:
        experiment = mlflow_test_client.get_experiment_by_name(experiment_name)
        if experiment is None:
            mlflow_test_client.create_experiment(experiment_name)
    except Exception:
        pass

    mlflow.set_tracking_uri(mlflow_test_tracking_uri)
    mlflow.set_experiment(experiment_name)

    # Registra v1.0 (produção)
    with mlflow.start_run(run_name="duration_predictor_v1"):
        mlflow.sklearn.log_model(mock_duration_predictor, "model")
        mlflow.log_metric("mae_percentage", 10.0)
        mlflow.log_metric("precision", 0.80)
        mlflow.log_param("version", "v1.0")
        run_v1 = mlflow.active_run()

    # Registra v2.0 (candidato)
    with mlflow.start_run(run_name="duration_predictor_v2"):
        mlflow.sklearn.log_model(mock_duration_predictor_v2, "model")
        mlflow.log_metric("mae_percentage", 9.0)
        mlflow.log_metric("precision", 0.82)
        mlflow.log_param("version", "v2.0")
        run_v2 = mlflow.active_run()

    # Cria wrapper de registry para testes
    class TestModelRegistry:
        """Registry de teste que encapsula operações MLflow."""

        def __init__(self, client, tracking_uri, models):
            self.client = client
            self.tracking_uri = tracking_uri
            self._models = models  # Cache de modelos
            self._current_versions = {'duration_predictor': 'v1.0'}
            self._metadata = {
                'duration_predictor': {
                    'v1.0': {'metrics': {'mae_percentage': 10.0, 'precision': 0.80}},
                    'v2.0': {'metrics': {'mae_percentage': 9.0, 'precision': 0.82}}
                }
            }

        async def get_current_version(self, model_name: str) -> str:
            return self._current_versions.get(model_name, 'v1.0')

        async def load_model(self, model_name: str, version: str = None, stage: str = None):
            if version == 'v2.0' or (stage is None and version is None):
                return self._models.get('v2.0', self._models.get('v1.0'))
            return self._models.get('v1.0')

        async def get_model(self, model_name: str, version: str = None):
            return await self.load_model(model_name, version)

        async def get_model_metadata(self, model_name: str, version: str = None) -> Dict[str, Any]:
            model_meta = self._metadata.get(model_name, {})
            if version:
                return model_meta.get(version, {'metrics': {}})
            # Retorna metadata da versão atual
            current = self._current_versions.get(model_name, 'v1.0')
            return model_meta.get(current, {'metrics': {}})

        async def promote_model(self, model_name: str, version: str, stage: str) -> Dict[str, Any]:
            self._current_versions[model_name] = version
            return {'success': True, 'version': version, 'stage': stage}

        async def enrich_model_metadata(self, model_name: str, version: str, metadata: Dict[str, Any]):
            if model_name not in self._metadata:
                self._metadata[model_name] = {}
            if version not in self._metadata[model_name]:
                self._metadata[model_name][version] = {'metrics': {}}
            self._metadata[model_name][version].update(metadata)

        async def rollback_model(self, model_name: str, reason: str) -> Dict[str, Any]:
            self._current_versions[model_name] = 'v1.0'
            return {'success': True, 'restored_version': 'v1.0', 'reason': reason}

        async def register_model(self, model_name: str, model, version: str, metrics: Dict[str, Any] = None):
            self._models[version] = model
            if model_name not in self._metadata:
                self._metadata[model_name] = {}
            self._metadata[model_name][version] = {'metrics': metrics or {}}
            return {'success': True, 'version': version}

    registry = TestModelRegistry(
        client=mlflow_test_client,
        tracking_uri=mlflow_test_tracking_uri,
        models={'v1.0': mock_duration_predictor, 'v2.0': mock_duration_predictor_v2}
    )

    return registry


@pytest.fixture
def continuous_validator_test(mongodb_ml_client, clean_ml_collections, test_config, event_loop):
    """
    ContinuousValidator real com MongoDB de teste.
    """
    if ContinuousValidator is None:
        pytest.skip("ContinuousValidator não disponível")

    validator = ContinuousValidator(
        config=test_config,
        mongodb_client=mongodb_ml_client,
        clickhouse_client=None,
        metrics=None,
        alert_handlers=[]
    )

    return validator


@pytest.fixture
def shadow_runner_test(mongodb_ml_client, clean_ml_collections, test_config, mock_duration_predictor, mock_duration_predictor_v2, model_registry_test):
    """
    ShadowModeRunner real configurado para testes rápidos.
    """
    if ShadowModeRunner is None:
        pytest.skip("ShadowModeRunner não disponível")

    runner = ShadowModeRunner(
        config=test_config,
        prod_model=mock_duration_predictor,
        shadow_model=mock_duration_predictor_v2,
        model_registry=model_registry_test,
        mongodb_client=mongodb_ml_client,
        metrics=None,
        model_name="duration_predictor",
        shadow_version="v2.0"
    )

    return runner


@pytest.fixture
def promotion_manager_test(
    model_registry_test,
    continuous_validator_test,
    mongodb_ml_client,
    clean_ml_collections,
    test_config
):
    """
    ModelPromotionManager real configurado para testes de integração.
    """
    if ModelPromotionManager is None:
        pytest.skip("ModelPromotionManager não disponível")

    manager = ModelPromotionManager(
        config=test_config,
        model_registry=model_registry_test,
        model_validator=None,
        continuous_validator=continuous_validator_test,
        mongodb_client=mongodb_ml_client,
        metrics=None
    )

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
# Fixtures de Promoção (Real Instances)
# =============================================================================

@pytest.fixture
def promotion_config_fast() -> 'PromotionConfig':
    """
    PromotionConfig real com timeouts rápidos para testes.
    """
    if PromotionConfig is None:
        pytest.skip("PromotionConfig não disponível")

    return PromotionConfig(
        shadow_mode_enabled=True,
        shadow_mode_duration_minutes=0,  # Imediato para testes
        shadow_mode_min_predictions=10,  # Baixo para testes rápidos
        shadow_mode_agreement_threshold=0.90,
        canary_enabled=True,
        canary_traffic_pct=10.0,
        canary_duration_minutes=0,  # Imediato para testes
        mae_threshold_pct=15.0,
        precision_threshold=0.75,
        auto_rollback_enabled=True,
        rollback_mae_increase_pct=20.0,
        gradual_rollout_enabled=True,
        rollout_stages=[0.25, 0.50, 0.75, 1.0],
        checkpoint_duration_minutes=0,  # Imediato para testes
        checkpoint_mae_threshold_pct=20.0,
        checkpoint_error_rate_threshold=0.001
    )


@pytest.fixture
def promotion_request_sample(promotion_config_fast) -> 'PromotionRequest':
    """
    PromotionRequest real de exemplo.
    """
    if PromotionRequest is None:
        pytest.skip("PromotionRequest não disponível")

    return PromotionRequest(
        request_id=f"test_promotion_{uuid.uuid4().hex[:8]}",
        model_name="duration_predictor",
        source_version="v2.0",
        target_stage="Production",
        initiated_by="test_user",
        config=promotion_config_fast
    )


@pytest.fixture
def promotion_config_no_shadow() -> 'PromotionConfig':
    """
    PromotionConfig com shadow mode desabilitado.
    """
    if PromotionConfig is None:
        pytest.skip("PromotionConfig não disponível")

    return PromotionConfig(
        shadow_mode_enabled=False,
        canary_enabled=True,
        canary_traffic_pct=10.0,
        canary_duration_minutes=0,
        gradual_rollout_enabled=True,
        rollout_stages=[0.25, 0.50, 0.75, 1.0],
        checkpoint_duration_minutes=0
    )


@pytest.fixture
def promotion_config_direct() -> 'PromotionConfig':
    """
    PromotionConfig para promoção direta (sem shadow/canary/rollout).
    """
    if PromotionConfig is None:
        pytest.skip("PromotionConfig não disponível")

    return PromotionConfig(
        shadow_mode_enabled=False,
        canary_enabled=False,
        gradual_rollout_enabled=False
    )


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
