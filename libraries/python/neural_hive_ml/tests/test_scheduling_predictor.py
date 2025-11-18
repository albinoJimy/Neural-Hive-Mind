"""Testes unitários para SchedulingPredictor."""

import pytest
import pytest_asyncio
import numpy as np
import pandas as pd
from unittest.mock import Mock, patch, AsyncMock
import tempfile
import os

from neural_hive_ml.predictive_models.scheduling_predictor import SchedulingPredictor


@pytest.fixture
def mock_config():
    """Configuração mock para SchedulingPredictor."""
    return {
        'model_name': 'scheduling-predictor',
        'model_type': 'xgboost',
        'hyperparameters': {}
    }


@pytest.fixture
def mock_config_ensemble():
    """Configuração mock para modo ensemble."""
    return {
        'model_name': 'scheduling-predictor',
        'model_type': 'ensemble',
        'ensemble_models': ['xgboost', 'lightgbm'],
        'hyperparameters': {}
    }


@pytest.fixture
def mock_registry():
    """ModelRegistry mock."""
    registry = Mock()
    registry.get_model_metadata = AsyncMock(return_value=None)
    return registry


@pytest.fixture
def mock_metrics():
    """Metrics client mock."""
    metrics = Mock()
    metrics.record_prediction_latency = Mock()
    metrics.record_prediction_accuracy = Mock()
    return metrics


@pytest.fixture
def sample_ticket():
    """Ticket de exemplo para testes."""
    return {
        'ticket_id': 'test-ticket-123',
        'risk_weight': 50,
        'capabilities': ['database', 'analytics', 'ml'],
        'qos': {
            'priority': 0.7,
            'consistency': 'AT_LEAST_ONCE',
            'durability': 'DURABLE'
        },
        'parameters': {'key1': 'value1', 'key2': 'value2'},
        'estimated_duration_ms': 5000,
        'sla_timeout_ms': 60000,
        'retry_count': 0,
        'task_type': 'data_processing'
    }


@pytest.fixture
def training_data():
    """Dados de treinamento sintéticos."""
    np.random.seed(42)
    n_samples = 1000

    data = {
        'risk_weight': np.random.uniform(10, 90, n_samples),
        'capabilities_count': np.random.randint(1, 10, n_samples),
        'parameters_size': np.random.randint(50, 2000, n_samples),
        'qos_priority': np.random.uniform(0.1, 1.0, n_samples),
        'qos_consistency': np.random.choice([0.0, 0.5, 1.0], n_samples),
        'qos_durability': np.random.choice([0.0, 0.5, 1.0], n_samples),
        'task_type_encoded': np.random.randint(0, 8, n_samples),
        'hour_of_day': np.random.randint(0, 24, n_samples),
        'day_of_week': np.random.randint(0, 7, n_samples),
        'is_weekend': np.random.choice([0, 1], n_samples),
        'is_business_hours': np.random.choice([0, 1], n_samples),
        'estimated_duration_ms': np.random.uniform(1000, 20000, n_samples),
        'sla_timeout_ms': np.random.uniform(30000, 120000, n_samples),
        'retry_count': np.random.randint(0, 3, n_samples),
        'avg_duration_by_task': np.random.uniform(3000, 18000, n_samples),
        'std_duration_by_task': np.random.uniform(500, 5000, n_samples),
        'success_rate_by_task': np.random.uniform(0.7, 1.0, n_samples),
        'avg_duration_by_risk': np.random.uniform(3000, 18000, n_samples),
        'risk_to_capabilities_ratio': np.random.uniform(3, 20, n_samples),
        'estimated_to_sla_ratio': np.random.uniform(0.05, 0.6, n_samples)
    }

    df = pd.DataFrame(data)

    # Gerar target baseado em features (duração real)
    # Duração = base + risco*10 + capabilities*500 + noise
    df['actual_duration_ms'] = (
        df['estimated_duration_ms'] * 0.8 +
        df['risk_weight'] * 10 +
        df['capabilities_count'] * 500 +
        np.random.normal(0, 1000, n_samples)
    )
    df['actual_duration_ms'] = df['actual_duration_ms'].clip(lower=1000)

    return df


# =============================================================================
# Testes de Inicialização
# =============================================================================

@pytest.mark.asyncio
async def test_initialization(mock_config, mock_registry, mock_metrics):
    """Testa inicialização básica do SchedulingPredictor."""
    predictor = SchedulingPredictor(
        config=mock_config,
        model_registry=mock_registry,
        metrics=mock_metrics
    )

    assert predictor.config == mock_config
    assert predictor.model_registry == mock_registry
    assert predictor.metrics == mock_metrics
    assert predictor.model is None  # Não carregado ainda


# =============================================================================
# Testes de Predição de Duração
# =============================================================================

@pytest.mark.asyncio
async def test_predict_duration_xgboost(
    mock_config,
    mock_registry,
    mock_metrics,
    sample_ticket,
    training_data
):
    """Testa predição de duração com XGBoost."""
    with patch('mlflow.set_tracking_uri'), \
         patch('mlflow.set_experiment'), \
         patch('mlflow.create_experiment'), \
         patch('mlflow.get_experiment_by_name', return_value=None), \
         patch('mlflow.start_run'), \
         patch('mlflow.log_param'), \
         patch('mlflow.log_metric'), \
         patch('mlflow.set_tag'), \
         patch('mlflow.log_artifact'), \
         patch('mlflow.xgboost.log_model'):

        predictor = SchedulingPredictor(
            config=mock_config,
            model_registry=mock_registry,
            metrics=mock_metrics
        )

        # Treinar modelo
        X = training_data.drop(columns=['actual_duration_ms'])
        y = training_data['actual_duration_ms']

        metrics_train = await predictor.train_model(X, y)

        # Validar métricas de treinamento
        assert 'mae' in metrics_train
        assert 'r2_score' in metrics_train
        assert 'mape' in metrics_train
        assert metrics_train['mae'] < 10000  # MAE < 10s
        assert metrics_train['r2_score'] > 0.7  # R² > 0.7
        assert metrics_train['mape'] < 30  # MAPE < 30%

        # Testar predição
        prediction = await predictor.predict_duration(sample_ticket)

        assert 'predicted_duration_ms' in prediction
        assert 'confidence' in prediction
        assert 'model_type' in prediction
        assert prediction['predicted_duration_ms'] > 0
        assert 0 <= prediction['confidence'] <= 1
        assert prediction['model_type'] == 'xgboost'


@pytest.mark.asyncio
async def test_predict_resources(
    mock_config,
    mock_registry,
    mock_metrics,
    sample_ticket,
    training_data
):
    """Testa predição de recursos (CPU/Memory)."""
    with patch('mlflow.set_tracking_uri'), \
         patch('mlflow.set_experiment'), \
         patch('mlflow.create_experiment'), \
         patch('mlflow.get_experiment_by_name', return_value=None), \
         patch('mlflow.start_run'), \
         patch('mlflow.log_param'), \
         patch('mlflow.log_metric'), \
         patch('mlflow.set_tag'), \
         patch('mlflow.log_artifact'), \
         patch('mlflow.xgboost.log_model'):

        predictor = SchedulingPredictor(
            config=mock_config,
            model_registry=mock_registry,
            metrics=mock_metrics
        )

        # Treinar modelo
        X = training_data.drop(columns=['actual_duration_ms'])
        y = training_data['actual_duration_ms']
        await predictor.train_model(X, y)

        # Testar predição de recursos
        resources = await predictor.predict_resources(sample_ticket)

        assert 'cpu_cores' in resources
        assert 'memory_mb' in resources
        assert 'confidence' in resources
        assert resources['cpu_cores'] >= 0.5
        assert resources['cpu_cores'] <= 4.0
        assert resources['memory_mb'] >= 256
        assert resources['memory_mb'] <= 4096
        assert 0 <= resources['confidence'] <= 1


@pytest.mark.asyncio
async def test_predict_duration_ensemble(
    mock_config_ensemble,
    mock_registry,
    mock_metrics,
    sample_ticket,
    training_data
):
    """Testa predição de duração com ensemble."""
    with patch('mlflow.set_tracking_uri'), \
         patch('mlflow.set_experiment'), \
         patch('mlflow.create_experiment'), \
         patch('mlflow.get_experiment_by_name', return_value=None), \
         patch('mlflow.start_run'), \
         patch('mlflow.log_param'), \
         patch('mlflow.log_metric'), \
         patch('mlflow.set_tag'), \
         patch('mlflow.log_artifact'), \
         patch('mlflow.xgboost.log_model'), \
         patch('mlflow.lightgbm.log_model'):

        predictor = SchedulingPredictor(
            config=mock_config_ensemble,
            model_registry=mock_registry,
            metrics=mock_metrics
        )

        X = training_data.drop(columns=['actual_duration_ms'])
        y = training_data['actual_duration_ms']

        metrics_train = await predictor.train_model(X, y)

        # Validar que ensemble foi treinado
        assert 'mae' in metrics_train
        assert predictor.model_type == 'ensemble'

        # Testar predição
        prediction = await predictor.predict_duration(sample_ticket)

        assert prediction['predicted_duration_ms'] > 0
        assert prediction['model_type'] == 'ensemble'


# =============================================================================
# Testes de Treinamento e Métricas
# =============================================================================

@pytest.mark.asyncio
async def test_train_model_metrics(
    mock_config,
    mock_registry,
    mock_metrics,
    training_data
):
    """Valida que métricas de treinamento atendem os requisitos."""
    with patch('mlflow.set_tracking_uri'), \
         patch('mlflow.set_experiment'), \
         patch('mlflow.create_experiment'), \
         patch('mlflow.get_experiment_by_name', return_value=None), \
         patch('mlflow.start_run'), \
         patch('mlflow.log_param'), \
         patch('mlflow.log_metric'), \
         patch('mlflow.set_tag'), \
         patch('mlflow.log_artifact'), \
         patch('mlflow.xgboost.log_model'):

        predictor = SchedulingPredictor(
            config=mock_config,
            model_registry=mock_registry,
            metrics=mock_metrics
        )

        X = training_data.drop(columns=['actual_duration_ms'])
        y = training_data['actual_duration_ms']

        metrics = await predictor.train_model(X, y)

        # Validar requisitos da documentação
        assert metrics['mae'] < 10000  # MAE < 10s
        assert metrics['r2_score'] > 0.85  # R² > 0.85
        assert metrics['mape'] < 20  # MAPE < 20%
        assert 'training_samples' in metrics
        assert metrics['training_samples'] == len(training_data)


@pytest.mark.asyncio
async def test_hyperparameter_tuning(
    mock_config,
    mock_registry,
    mock_metrics,
    training_data
):
    """Testa tuning de hiperparâmetros."""
    mock_config['enable_tuning'] = True

    with patch('mlflow.set_tracking_uri'), \
         patch('mlflow.set_experiment'), \
         patch('mlflow.create_experiment'), \
         patch('mlflow.get_experiment_by_name', return_value=None), \
         patch('mlflow.start_run'), \
         patch('mlflow.log_param'), \
         patch('mlflow.log_metric'), \
         patch('mlflow.set_tag'), \
         patch('mlflow.log_artifact'), \
         patch('mlflow.xgboost.log_model'), \
         patch('optuna.create_study') as mock_optuna:

        # Mock Optuna study
        mock_study = Mock()
        mock_study.best_params = {
            'max_depth': 6,
            'learning_rate': 0.1,
            'n_estimators': 100
        }
        mock_optuna.return_value = mock_study

        predictor = SchedulingPredictor(
            config=mock_config,
            model_registry=mock_registry,
            metrics=mock_metrics
        )

        X = training_data.drop(columns=['actual_duration_ms'])
        y = training_data['actual_duration_ms']

        metrics = await predictor.train_model(X, y)

        # Validar que tuning foi executado
        assert 'tuned_hyperparameters' in metrics or mock_optuna.called


# =============================================================================
# Testes de Fallback
# =============================================================================

@pytest.mark.asyncio
async def test_fallback_on_prediction_error(
    mock_config,
    mock_registry,
    mock_metrics,
    sample_ticket
):
    """Testa fallback quando predição falha."""
    predictor = SchedulingPredictor(
        config=mock_config,
        model_registry=mock_registry,
        metrics=mock_metrics
    )

    # Não treinar modelo (forçando fallback heurístico)
    assert predictor.model is None

    # Deve usar heurística baseada em estimated_duration_ms
    prediction = await predictor.predict_duration(sample_ticket)

    assert 'predicted_duration_ms' in prediction
    assert prediction['predicted_duration_ms'] > 0
    assert prediction['confidence'] == 0.0  # Baixa confiança no fallback
    assert 'fallback' in prediction.get('model_type', '').lower() or prediction['confidence'] == 0.0


# =============================================================================
# Testes de Latência
# =============================================================================

@pytest.mark.asyncio
async def test_prediction_latency(
    mock_config,
    mock_registry,
    mock_metrics,
    sample_ticket,
    training_data
):
    """Valida que latência de predição < 100ms."""
    with patch('mlflow.set_tracking_uri'), \
         patch('mlflow.set_experiment'), \
         patch('mlflow.create_experiment'), \
         patch('mlflow.get_experiment_by_name', return_value=None), \
         patch('mlflow.start_run'), \
         patch('mlflow.log_param'), \
         patch('mlflow.log_metric'), \
         patch('mlflow.set_tag'), \
         patch('mlflow.log_artifact'), \
         patch('mlflow.xgboost.log_model'):

        predictor = SchedulingPredictor(
            config=mock_config,
            model_registry=mock_registry,
            metrics=mock_metrics
        )

        X = training_data.drop(columns=['actual_duration_ms'])
        y = training_data['actual_duration_ms']
        await predictor.train_model(X, y)

        import time

        # Testar latência de predição
        start = time.time()
        prediction = await predictor.predict_duration(sample_ticket)
        latency_ms = (time.time() - start) * 1000

        # Validar latência < 100ms
        assert latency_ms < 100
        assert prediction['predicted_duration_ms'] > 0


# =============================================================================
# Testes de Persistência
# =============================================================================

@pytest.mark.asyncio
async def test_model_persistence_and_reload(
    mock_config,
    mock_registry,
    mock_metrics,
    sample_ticket,
    training_data
):
    """Testa que modelo pode ser salvo e recarregado."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch('mlflow.set_tracking_uri'), \
             patch('mlflow.set_experiment'), \
             patch('mlflow.create_experiment'), \
             patch('mlflow.get_experiment_by_name', return_value=None), \
             patch('mlflow.start_run'), \
             patch('mlflow.log_param'), \
             patch('mlflow.log_metric'), \
             patch('mlflow.set_tag'), \
             patch('mlflow.log_artifact'), \
             patch('mlflow.xgboost.log_model'):

            # Treinar modelo original
            predictor1 = SchedulingPredictor(
                config=mock_config,
                model_registry=mock_registry,
                metrics=mock_metrics
            )

            X = training_data.drop(columns=['actual_duration_ms'])
            y = training_data['actual_duration_ms']
            await predictor1.train_model(X, y)

            # Fazer predição original
            pred1 = await predictor1.predict_duration(sample_ticket)

            # Simular reload do modelo
            predictor2 = SchedulingPredictor(
                config=mock_config,
                model_registry=mock_registry,
                metrics=mock_metrics
            )

            # Mock do MLflow para carregar modelo
            with patch('mlflow.xgboost.load_model', return_value=predictor1.model), \
                 patch('mlflow.tracking.MlflowClient') as mock_client_class:

                mock_client = Mock()
                mock_version = Mock()
                mock_version.run_id = 'test_run_id'
                mock_client.get_latest_versions.return_value = [mock_version]
                mock_client_class.return_value = mock_client

                await predictor2.initialize()

            # Fazer predição com modelo recarregado
            pred2 = await predictor2.predict_duration(sample_ticket)

            # Validar que predições são consistentes
            assert abs(pred1['predicted_duration_ms'] - pred2['predicted_duration_ms']) < 100
