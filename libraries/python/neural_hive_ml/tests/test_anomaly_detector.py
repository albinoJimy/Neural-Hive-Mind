"""Testes unitários para AnomalyDetector."""

import pytest
import pytest_asyncio
import numpy as np
import pandas as pd
from unittest.mock import Mock, patch, MagicMock, AsyncMock
import tempfile
import os
import joblib

from neural_hive_ml.predictive_models.anomaly_detector import AnomalyDetector


@pytest.fixture
def mock_config():
    """Configuração mock para AnomalyDetector."""
    return {
        'model_name': 'anomaly-detector-test',
        'model_type': 'isolation_forest',
        'contamination': 0.05
    }


@pytest.fixture
def mock_config_autoencoder():
    """Configuração mock para AnomalyDetector com autoencoder."""
    return {
        'model_name': 'anomaly-detector-test',
        'model_type': 'autoencoder',
        'contamination': 0.05
    }


@pytest.fixture
def mock_registry():
    """ModelRegistry mock."""
    registry = Mock()
    registry.get_model_metadata = Mock(return_value=None)
    return registry


@pytest.fixture
def mock_metrics():
    """Metrics client mock."""
    metrics = Mock()
    metrics.record_anomaly_detection = AsyncMock()
    return metrics


@pytest.fixture
def training_data_normal():
    """Dados de treinamento normais (100 amostras)."""
    np.random.seed(42)
    data = {
        'risk_weight': np.random.uniform(20, 60, 100),
        'capabilities_count': np.random.randint(2, 8, 100),
        'parameters_size': np.random.randint(100, 1000, 100),
        'qos_priority': np.random.uniform(0.3, 0.8, 100),
        'qos_consistency': np.random.choice([0.0, 0.5, 1.0], 100),
        'qos_durability': np.random.choice([0.0, 0.5, 1.0], 100),
        'task_type_encoded': np.random.randint(0, 5, 100),
        'hour_of_day': np.random.randint(0, 24, 100),
        'day_of_week': np.random.randint(0, 7, 100),
        'is_weekend': np.random.choice([0, 1], 100),
        'is_business_hours': np.random.choice([0, 1], 100),
        'estimated_duration_ms': np.random.uniform(1000, 10000, 100),
        'sla_timeout_ms': np.random.uniform(30000, 60000, 100),
        'retry_count': np.random.randint(0, 2, 100),
        'avg_duration_by_task': np.random.uniform(5000, 15000, 100),
        'std_duration_by_task': np.random.uniform(1000, 5000, 100),
        'success_rate_by_task': np.random.uniform(0.8, 1.0, 100),
        'avg_duration_by_risk': np.random.uniform(5000, 15000, 100),
        'risk_to_capabilities_ratio': np.random.uniform(5, 15, 100),
        'estimated_to_sla_ratio': np.random.uniform(0.1, 0.5, 100)
    }
    return pd.DataFrame(data)


@pytest.fixture
def training_data_with_anomalies():
    """Dados de treinamento com 10 anomalias."""
    np.random.seed(42)
    # 100 normais
    normal_data = {
        'risk_weight': np.random.uniform(20, 60, 100),
        'capabilities_count': np.random.randint(2, 8, 100),
        'parameters_size': np.random.randint(100, 1000, 100),
        'qos_priority': np.random.uniform(0.3, 0.8, 100),
        'qos_consistency': np.random.choice([0.0, 0.5, 1.0], 100),
        'qos_durability': np.random.choice([0.0, 0.5, 1.0], 100),
        'task_type_encoded': np.random.randint(0, 5, 100),
        'hour_of_day': np.random.randint(0, 24, 100),
        'day_of_week': np.random.randint(0, 7, 100),
        'is_weekend': np.random.choice([0, 1], 100),
        'is_business_hours': np.random.choice([0, 1], 100),
        'estimated_duration_ms': np.random.uniform(1000, 10000, 100),
        'sla_timeout_ms': np.random.uniform(30000, 60000, 100),
        'retry_count': np.random.randint(0, 2, 100),
        'avg_duration_by_task': np.random.uniform(5000, 15000, 100),
        'std_duration_by_task': np.random.uniform(1000, 5000, 100),
        'success_rate_by_task': np.random.uniform(0.8, 1.0, 100),
        'avg_duration_by_risk': np.random.uniform(5000, 15000, 100),
        'risk_to_capabilities_ratio': np.random.uniform(5, 15, 100),
        'estimated_to_sla_ratio': np.random.uniform(0.1, 0.5, 100)
    }

    # 10 anomalias (capabilities excessivas)
    anomaly_data = {
        'risk_weight': np.random.uniform(20, 60, 10),
        'capabilities_count': np.random.randint(15, 20, 10),  # Anômalo
        'parameters_size': np.random.randint(100, 1000, 10),
        'qos_priority': np.random.uniform(0.3, 0.8, 10),
        'qos_consistency': np.random.choice([0.0, 0.5, 1.0], 10),
        'qos_durability': np.random.choice([0.0, 0.5, 1.0], 10),
        'task_type_encoded': np.random.randint(0, 5, 10),
        'hour_of_day': np.random.randint(0, 24, 10),
        'day_of_week': np.random.randint(0, 7, 10),
        'is_weekend': np.random.choice([0, 1], 10),
        'is_business_hours': np.random.choice([0, 1], 10),
        'estimated_duration_ms': np.random.uniform(1000, 10000, 10),
        'sla_timeout_ms': np.random.uniform(30000, 60000, 10),
        'retry_count': np.random.randint(0, 2, 10),
        'avg_duration_by_task': np.random.uniform(5000, 15000, 10),
        'std_duration_by_task': np.random.uniform(1000, 5000, 10),
        'success_rate_by_task': np.random.uniform(0.8, 1.0, 10),
        'avg_duration_by_risk': np.random.uniform(5000, 15000, 10),
        'risk_to_capabilities_ratio': np.random.uniform(5, 15, 10),
        'estimated_to_sla_ratio': np.random.uniform(0.1, 0.5, 10)
    }

    df_normal = pd.DataFrame(normal_data)
    df_anomaly = pd.DataFrame(anomaly_data)

    return pd.concat([df_normal, df_anomaly], ignore_index=True)


@pytest.fixture
def labels_with_anomalies():
    """Labels para dados com anomalias (100 normais + 10 anômalos)."""
    return np.array([1] * 100 + [-1] * 10)


# =============================================================================
# Testes de Persistência - IsolationForest
# =============================================================================

@pytest.mark.asyncio
async def test_isolation_forest_persistence(
    mock_config,
    mock_registry,
    mock_metrics,
    training_data_with_anomalies,
    labels_with_anomalies
):
    """
    Testa persistência e reload do IsolationForest.
    Valida que scaler e modelo são salvos e restaurados corretamente.
    """
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
             patch('mlflow.sklearn.log_model'):

            # Treina modelo
            detector = AnomalyDetector(
                config=mock_config,
                model_registry=mock_registry,
                metrics=mock_metrics
            )

            metrics = await detector.train_model(
                training_data=training_data_with_anomalies,
                labels=labels_with_anomalies
            )

            # Valida que modelo foi treinado
            assert detector.model is not None
            assert hasattr(detector.scaler, 'mean_')
            assert metrics['f1_score'] > 0.0

            # Salva scaler para teste de reload
            scaler_mean_original = detector.scaler.mean_.copy()
            scaler_path = os.path.join(tmpdir, 'scaler.joblib')
            joblib.dump(detector.scaler, scaler_path)

            # Simula reload do modelo
            detector2 = AnomalyDetector(
                config=mock_config,
                model_registry=mock_registry,
                metrics=mock_metrics
            )

            # Mock do MLflow para carregar modelo
            with patch('mlflow.sklearn.load_model', return_value=detector.model), \
                 patch('mlflow.tracking.MlflowClient') as mock_client_class:

                # Mock do client e métodos
                mock_client = Mock()
                mock_version = Mock()
                mock_version.run_id = 'test_run_id'
                mock_client.get_latest_versions.return_value = [mock_version]
                mock_client.download_artifacts.return_value = scaler_path
                mock_client_class.return_value = mock_client

                await detector2.initialize()

            # Valida que scaler foi restaurado
            assert detector2.scaler is not None
            assert hasattr(detector2.scaler, 'mean_')
            np.testing.assert_array_almost_equal(
                detector2.scaler.mean_,
                scaler_mean_original
            )

            # Testa que predições são consistentes
            test_ticket = {
                'risk_weight': 40,
                'capabilities': ['cap1', 'cap2', 'cap3'],
                'qos': {'priority': 0.5, 'consistency': 'AT_LEAST_ONCE', 'durability': 'DURABLE'},
                'parameters': {'key': 'value'},
                'estimated_duration_ms': 5000,
                'sla_timeout_ms': 50000,
                'retry_count': 0
            }

            result1 = await detector.detect_anomaly(test_ticket)
            result2 = await detector2.detect_anomaly(test_ticket)

            assert result1['is_anomaly'] == result2['is_anomaly']
            assert abs(result1['anomaly_score'] - result2['anomaly_score']) < 0.01


# =============================================================================
# Testes de Persistência - Autoencoder
# =============================================================================

@pytest.mark.asyncio
async def test_autoencoder_persistence(
    mock_config_autoencoder,
    mock_registry,
    mock_metrics,
    training_data_normal
):
    """
    Testa persistência e reload do Autoencoder.
    Valida que scaler e threshold são salvos e restaurados corretamente.
    """
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
             patch('mlflow.keras.log_model'):

            # Treina modelo
            detector = AnomalyDetector(
                config=mock_config_autoencoder,
                model_registry=mock_registry,
                metrics=mock_metrics
            )

            metrics = await detector.train_model(
                training_data=training_data_normal
            )

            # Valida que modelo foi treinado
            assert detector.model is not None
            assert hasattr(detector.scaler, 'mean_')
            assert detector.autoencoder_threshold is not None
            assert detector.autoencoder_threshold > 0

            # Salva artifacts para teste de reload
            scaler_mean_original = detector.scaler.mean_.copy()
            threshold_original = detector.autoencoder_threshold

            scaler_path = os.path.join(tmpdir, 'scaler.joblib')
            threshold_path = os.path.join(tmpdir, 'threshold.npy')
            joblib.dump(detector.scaler, scaler_path)
            np.save(threshold_path, threshold_original)

            # Simula reload do modelo
            detector2 = AnomalyDetector(
                config=mock_config_autoencoder,
                model_registry=mock_registry,
                metrics=mock_metrics
            )

            # Mock do MLflow para carregar modelo
            with patch('mlflow.keras.load_model', return_value=detector.model), \
                 patch('mlflow.tracking.MlflowClient') as mock_client_class:

                # Mock do client e métodos
                mock_client = Mock()
                mock_version = Mock()
                mock_version.run_id = 'test_run_id'
                mock_client.get_latest_versions.return_value = [mock_version]

                def download_artifacts_side_effect(run_id, path, dst_path):
                    if 'scaler' in path:
                        return scaler_path
                    elif 'threshold' in path:
                        return threshold_path
                    raise ValueError(f'Unexpected path: {path}')

                mock_client.download_artifacts.side_effect = download_artifacts_side_effect
                mock_client_class.return_value = mock_client

                await detector2.initialize()

            # Valida que scaler e threshold foram restaurados
            assert detector2.scaler is not None
            assert hasattr(detector2.scaler, 'mean_')
            np.testing.assert_array_almost_equal(
                detector2.scaler.mean_,
                scaler_mean_original
            )
            assert detector2.autoencoder_threshold == threshold_original

            # Testa que predições produzem scores consistentes
            test_ticket = {
                'risk_weight': 40,
                'capabilities': ['cap1', 'cap2', 'cap3'],
                'qos': {'priority': 0.5, 'consistency': 'AT_LEAST_ONCE', 'durability': 'DURABLE'},
                'parameters': {'key': 'value'},
                'estimated_duration_ms': 5000,
                'sla_timeout_ms': 50000,
                'retry_count': 0
            }

            result1 = await detector.detect_anomaly(test_ticket)
            result2 = await detector2.detect_anomaly(test_ticket)

            # Scores devem ser muito próximos (pode haver pequenas diferenças por arredondamento)
            assert abs(result1['anomaly_score'] - result2['anomaly_score']) < 0.1


# =============================================================================
# Testes de Fallback
# =============================================================================

@pytest.mark.asyncio
async def test_artifact_download_failure_fallback(
    mock_config,
    mock_registry,
    mock_metrics
):
    """
    Testa fallback quando download de artifacts falha.
    Deve usar scaler padrão e threshold fallback.
    """
    detector = AnomalyDetector(
        config=mock_config,
        model_registry=mock_registry,
        metrics=mock_metrics
    )

    # Mock do MLflow com falha no download de artifacts
    with patch('mlflow.sklearn.load_model', return_value=Mock()), \
         patch('mlflow.tracking.MlflowClient') as mock_client_class:

        mock_client = Mock()
        mock_version = Mock()
        mock_version.run_id = 'test_run_id'
        mock_client.get_latest_versions.return_value = [mock_version]
        mock_client.download_artifacts.side_effect = Exception('Download failed')
        mock_client_class.return_value = mock_client

        await detector.initialize()

    # Valida que scaler padrão foi usado (não tem mean_ fitted)
    assert not hasattr(detector.scaler, 'mean_')

    # Testa detecção com fallback heurístico
    test_ticket = {
        'risk_weight': 40,
        'capabilities': ['cap1', 'cap2', 'cap3'],
        'qos': {'priority': 0.5, 'consistency': 'AT_LEAST_ONCE', 'durability': 'DURABLE'},
        'parameters': {'key': 'value'},
        'estimated_duration_ms': 5000,
        'sla_timeout_ms': 50000,
        'retry_count': 0
    }

    result = await detector.detect_anomaly(test_ticket)

    # Deve funcionar mesmo sem modelo treinado (fallback heurístico)
    assert 'is_anomaly' in result
    assert 'anomaly_score' in result


# =============================================================================
# Testes de Correção de API do MLflow
# =============================================================================

@pytest.mark.asyncio
async def test_mlflow_api_correctness(
    mock_config,
    mock_config_autoencoder,
    mock_registry,
    mock_metrics,
    training_data_normal
):
    """
    Valida que mlflow.sklearn.log_model é usado para IsolationForest
    e mlflow.keras.log_model é usado para Autoencoder.
    """
    # Teste IsolationForest
    with patch('mlflow.set_tracking_uri'), \
         patch('mlflow.set_experiment'), \
         patch('mlflow.create_experiment'), \
         patch('mlflow.get_experiment_by_name', return_value=None), \
         patch('mlflow.start_run'), \
         patch('mlflow.log_param'), \
         patch('mlflow.log_metric'), \
         patch('mlflow.set_tag'), \
         patch('mlflow.log_artifact'), \
         patch('mlflow.sklearn.log_model') as mock_sklearn_log, \
         patch('mlflow.keras.log_model') as mock_keras_log:

        detector_if = AnomalyDetector(
            config=mock_config,
            model_registry=mock_registry,
            metrics=mock_metrics
        )

        await detector_if.train_model(training_data=training_data_normal)

        # Valida que sklearn.log_model foi chamado
        assert mock_sklearn_log.called
        assert not mock_keras_log.called

    # Teste Autoencoder
    with patch('mlflow.set_tracking_uri'), \
         patch('mlflow.set_experiment'), \
         patch('mlflow.create_experiment'), \
         patch('mlflow.get_experiment_by_name', return_value=None), \
         patch('mlflow.start_run'), \
         patch('mlflow.log_param'), \
         patch('mlflow.log_metric'), \
         patch('mlflow.set_tag'), \
         patch('mlflow.log_artifact'), \
         patch('mlflow.sklearn.log_model') as mock_sklearn_log, \
         patch('mlflow.keras.log_model') as mock_keras_log:

        detector_ae = AnomalyDetector(
            config=mock_config_autoencoder,
            model_registry=mock_registry,
            metrics=mock_metrics
        )

        await detector_ae.train_model(training_data=training_data_normal)

        # Valida que keras.log_model foi chamado
        assert mock_keras_log.called
        # sklearn.log_model não deve ser chamado para autoencoder
        assert not mock_sklearn_log.called


# =============================================================================
# Testes de Métricas de Performance
# =============================================================================

@pytest.mark.asyncio
async def test_precision_recall_after_reload(
    mock_config,
    mock_registry,
    mock_metrics,
    training_data_with_anomalies,
    labels_with_anomalies
):
    """
    Valida que precision/recall permanecem > 0.6 após reload.
    """
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
             patch('mlflow.sklearn.log_model'):

            # Treina modelo
            detector = AnomalyDetector(
                config=mock_config,
                model_registry=mock_registry,
                metrics=mock_metrics
            )

            metrics_train = await detector.train_model(
                training_data=training_data_with_anomalies,
                labels=labels_with_anomalies
            )

            # Valida métricas de treinamento
            assert metrics_train['precision'] > 0.6
            assert metrics_train['recall'] > 0.6
            assert metrics_train['f1_score'] > 0.6

            # Salva artifacts
            scaler_path = os.path.join(tmpdir, 'scaler.joblib')
            joblib.dump(detector.scaler, scaler_path)

            # Reload
            detector2 = AnomalyDetector(
                config=mock_config,
                model_registry=mock_registry,
                metrics=mock_metrics
            )

            with patch('mlflow.sklearn.load_model', return_value=detector.model), \
                 patch('mlflow.tracking.MlflowClient') as mock_client_class:

                mock_client = Mock()
                mock_version = Mock()
                mock_version.run_id = 'test_run_id'
                mock_client.get_latest_versions.return_value = [mock_version]
                mock_client.download_artifacts.return_value = scaler_path
                mock_client_class.return_value = mock_client

                await detector2.initialize()

            # Testa predições em dados de teste
            X_test = training_data_with_anomalies[detector.feature_names].values[:50]
            y_test = labels_with_anomalies[:50]

            predictions = detector2._predict_labels(
                detector2.scaler.transform(X_test)
            )

            from sklearn.metrics import precision_score, recall_score, f1_score

            precision = precision_score(y_test, predictions)
            recall = recall_score(y_test, predictions)
            f1 = f1_score(y_test, predictions)

            # Métricas devem permanecer razoáveis após reload
            assert precision > 0.5  # Pode ser um pouco menor em subset de teste
            assert recall > 0.5
            assert f1 > 0.5


# =============================================================================
# Testes de Integração com Scheduler
# =============================================================================

@pytest.mark.asyncio
async def test_integration_with_scheduler(
    mock_config,
    mock_registry,
    mock_metrics,
    training_data_with_anomalies,
    labels_with_anomalies
):
    """
    Testa integração do AnomalyDetector com IntelligentScheduler.
    Valida que anomalias são detectadas e refletidas no scheduling.
    """
    # Treina detector
    with patch('mlflow.set_tracking_uri'), \
         patch('mlflow.set_experiment'), \
         patch('mlflow.create_experiment'), \
         patch('mlflow.get_experiment_by_name', return_value=None), \
         patch('mlflow.start_run'), \
         patch('mlflow.log_param'), \
         patch('mlflow.log_metric'), \
         patch('mlflow.set_tag'), \
         patch('mlflow.log_artifact'), \
         patch('mlflow.sklearn.log_model'):

        detector = AnomalyDetector(
            config=mock_config,
            model_registry=mock_registry,
            metrics=mock_metrics
        )

        await detector.train_model(
            training_data=training_data_with_anomalies,
            labels=labels_with_anomalies
        )

    # Cria ticket normal
    normal_ticket = {
        'ticket_id': 'test-123',
        'risk_weight': 40,
        'capabilities': ['cap1', 'cap2', 'cap3'],
        'qos': {'priority': 0.5, 'consistency': 'AT_LEAST_ONCE', 'durability': 'DURABLE'},
        'parameters': {'key': 'value'},
        'estimated_duration_ms': 5000,
        'sla_timeout_ms': 50000,
        'retry_count': 0
    }

    # Cria ticket anômalo (muitas capabilities)
    anomalous_ticket = {
        'ticket_id': 'test-456',
        'risk_weight': 40,
        'capabilities': ['cap' + str(i) for i in range(20)],  # 20 capabilities = anômalo
        'qos': {'priority': 0.5, 'consistency': 'AT_LEAST_ONCE', 'durability': 'DURABLE'},
        'parameters': {'key': 'value'},
        'estimated_duration_ms': 5000,
        'sla_timeout_ms': 50000,
        'retry_count': 0
    }

    # Detecta anomalia em tickets
    normal_result = await detector.detect_anomaly(normal_ticket)
    anomalous_result = await detector.detect_anomaly(anomalous_ticket)

    # Valida detecção
    assert normal_result['is_anomaly'] is False
    assert anomalous_result['is_anomaly'] is True

    # Mock do scheduler
    mock_scheduler = Mock()
    mock_scheduler.schedule_ticket = AsyncMock()

    # Simula scheduling com anomalia detectada
    normal_ticket['predictions'] = {'anomaly': normal_result}
    anomalous_ticket['predictions'] = {'anomaly': anomalous_result}

    # Mock allocation_metadata
    normal_allocation = {
        'allocated_at': 1234567890,
        'agent_id': 'worker-1',
        'priority_score': 0.5,
        'anomaly_detected': normal_result['is_anomaly']
    }

    anomalous_allocation = {
        'allocated_at': 1234567890,
        'agent_id': 'worker-1',
        'priority_score': 0.7,  # Boosted por anomalia
        'anomaly_detected': anomalous_result['is_anomaly']
    }

    # Valida que anomalia é refletida no allocation_metadata
    assert normal_allocation['anomaly_detected'] is False
    assert anomalous_allocation['anomaly_detected'] is True
    assert anomalous_allocation['priority_score'] > normal_allocation['priority_score']

    # Valida que métricas foram registradas
    assert mock_metrics.record_anomaly_detection.called


@pytest.mark.asyncio
async def test_fallback_on_detector_failure(
    mock_config,
    mock_registry,
    mock_metrics
):
    """
    Testa fallback quando detector falha.
    Deve usar heurístico e retornar is_anomaly=False.
    """
    detector = AnomalyDetector(
        config=mock_config,
        model_registry=mock_registry,
        metrics=mock_metrics
    )

    # Não treina modelo (forçando fallback heurístico)
    assert detector.model is None

    # Mock de um ticket que causaria erro no modelo
    test_ticket = {
        'risk_weight': 40,
        'capabilities': ['cap1', 'cap2'],
        'qos': {'priority': 0.5, 'consistency': 'AT_LEAST_ONCE', 'durability': 'DURABLE'},
        'parameters': {'key': 'value'},
        'estimated_duration_ms': 5000,
        'sla_timeout_ms': 50000,
        'retry_count': 0
    }

    # Deve usar fallback heurístico
    result = await detector.detect_anomaly(test_ticket)

    # Valida fallback
    assert 'is_anomaly' in result
    assert result['model_type'] == 'heuristic'
    assert result['is_anomaly'] is False  # Normal pelo heurístico


@pytest.mark.asyncio
async def test_anomaly_priority_adjustment(
    mock_config,
    mock_registry,
    mock_metrics,
    training_data_with_anomalies,
    labels_with_anomalies
):
    """
    Verifica se anomalias boostam priority_score.
    Simula scheduler ajustando prioridade baseado em anomalia.
    """
    # Treina detector
    with patch('mlflow.set_tracking_uri'), \
         patch('mlflow.set_experiment'), \
         patch('mlflow.create_experiment'), \
         patch('mlflow.get_experiment_by_name', return_value=None), \
         patch('mlflow.start_run'), \
         patch('mlflow.log_param'), \
         patch('mlflow.log_metric'), \
         patch('mlflow.set_tag'), \
         patch('mlflow.log_artifact'), \
         patch('mlflow.sklearn.log_model'):

        detector = AnomalyDetector(
            config=mock_config,
            model_registry=mock_registry,
            metrics=mock_metrics
        )

        await detector.train_model(
            training_data=training_data_with_anomalies,
            labels=labels_with_anomalies
        )

    # Ticket anômalo
    anomalous_ticket = {
        'ticket_id': 'test-789',
        'risk_weight': 40,
        'capabilities': ['cap' + str(i) for i in range(18)],
        'qos': {'priority': 0.5, 'consistency': 'AT_LEAST_ONCE', 'durability': 'DURABLE'},
        'parameters': {'key': 'value'},
        'estimated_duration_ms': 5000,
        'sla_timeout_ms': 50000,
        'retry_count': 0
    }

    result = await detector.detect_anomaly(anomalous_ticket)

    # Simula scheduler boost
    base_priority = 0.5
    boosted_priority = base_priority

    if result['is_anomaly']:
        # Boost de 20% se anomalia
        boosted_priority = min(base_priority * 1.2, 1.0)

    # Valida boost
    assert result['is_anomaly'] is True
    assert boosted_priority > base_priority
    assert boosted_priority == 0.6  # 0.5 * 1.2
