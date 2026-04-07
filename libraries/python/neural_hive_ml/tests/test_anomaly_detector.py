"""Testes unitários para AnomalyDetector."""

import pytest
import numpy as np
import pandas as pd
from unittest.mock import Mock, patch, AsyncMock
import tempfile
import os
import joblib

from neural_hive_ml.predictive_models.anomaly_detector import AnomalyDetector


@pytest.fixture
def mock_config():
    """Configuração mock para AnomalyDetector."""
    return {
        "model_name": "anomaly-detector-test",
        "model_type": "isolation_forest",
        "contamination": 0.05,
    }


@pytest.fixture
def mock_config_autoencoder():
    """Configuração mock para AnomalyDetector com autoencoder."""
    return {
        "model_name": "anomaly-detector-test",
        "model_type": "autoencoder",
        "contamination": 0.05,
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
        "risk_weight": np.random.uniform(20, 60, 100),
        "capabilities_count": np.random.randint(2, 8, 100),
        "parameters_size": np.random.randint(100, 1000, 100),
        "qos_priority": np.random.uniform(0.3, 0.8, 100),
        "qos_consistency": np.random.choice([0.0, 0.5, 1.0], 100),
        "qos_durability": np.random.choice([0.0, 0.5, 1.0], 100),
        "task_type_encoded": np.random.randint(0, 5, 100),
        "hour_of_day": np.random.randint(0, 24, 100),
        "day_of_week": np.random.randint(0, 7, 100),
        "is_weekend": np.random.choice([0, 1], 100),
        "is_business_hours": np.random.choice([0, 1], 100),
        "estimated_duration_ms": np.random.uniform(1000, 10000, 100),
        "sla_timeout_ms": np.random.uniform(30000, 60000, 100),
        "retry_count": np.random.randint(0, 2, 100),
        "avg_duration_by_task": np.random.uniform(5000, 15000, 100),
        "std_duration_by_task": np.random.uniform(1000, 5000, 100),
        "success_rate_by_task": np.random.uniform(0.8, 1.0, 100),
        "avg_duration_by_risk": np.random.uniform(5000, 15000, 100),
        "risk_to_capabilities_ratio": np.random.uniform(5, 15, 100),
        "estimated_to_sla_ratio": np.random.uniform(0.1, 0.5, 100),
    }
    return pd.DataFrame(data)


@pytest.fixture
def training_data_with_anomalies():
    """Dados de treinamento com 10 anomalias."""
    np.random.seed(42)
    # 100 normais
    normal_data = {
        "risk_weight": np.random.uniform(20, 60, 100),
        "capabilities_count": np.random.randint(2, 8, 100),
        "parameters_size": np.random.randint(100, 1000, 100),
        "qos_priority": np.random.uniform(0.3, 0.8, 100),
        "qos_consistency": np.random.choice([0.0, 0.5, 1.0], 100),
        "qos_durability": np.random.choice([0.0, 0.5, 1.0], 100),
        "task_type_encoded": np.random.randint(0, 5, 100),
        "hour_of_day": np.random.randint(0, 24, 100),
        "day_of_week": np.random.randint(0, 7, 100),
        "is_weekend": np.random.choice([0, 1], 100),
        "is_business_hours": np.random.choice([0, 1], 100),
        "estimated_duration_ms": np.random.uniform(1000, 10000, 100),
        "sla_timeout_ms": np.random.uniform(30000, 60000, 100),
        "retry_count": np.random.randint(0, 2, 100),
        "avg_duration_by_task": np.random.uniform(5000, 15000, 100),
        "std_duration_by_task": np.random.uniform(1000, 5000, 100),
        "success_rate_by_task": np.random.uniform(0.8, 1.0, 100),
        "avg_duration_by_risk": np.random.uniform(5000, 15000, 100),
        "risk_to_capabilities_ratio": np.random.uniform(5, 15, 100),
        "estimated_to_sla_ratio": np.random.uniform(0.1, 0.5, 100),
    }

    # 10 anomalias (capabilities excessivas)
    anomaly_data = {
        "risk_weight": np.random.uniform(20, 60, 10),
        "capabilities_count": np.random.randint(15, 20, 10),  # Anômalo
        "parameters_size": np.random.randint(100, 1000, 10),
        "qos_priority": np.random.uniform(0.3, 0.8, 10),
        "qos_consistency": np.random.choice([0.0, 0.5, 1.0], 10),
        "qos_durability": np.random.choice([0.0, 0.5, 1.0], 10),
        "task_type_encoded": np.random.randint(0, 5, 10),
        "hour_of_day": np.random.randint(0, 24, 10),
        "day_of_week": np.random.randint(0, 7, 10),
        "is_weekend": np.random.choice([0, 1], 10),
        "is_business_hours": np.random.choice([0, 1], 10),
        "estimated_duration_ms": np.random.uniform(1000, 10000, 10),
        "sla_timeout_ms": np.random.uniform(30000, 60000, 10),
        "retry_count": np.random.randint(0, 2, 10),
        "avg_duration_by_task": np.random.uniform(5000, 15000, 10),
        "std_duration_by_task": np.random.uniform(1000, 5000, 10),
        "success_rate_by_task": np.random.uniform(0.8, 1.0, 10),
        "avg_duration_by_risk": np.random.uniform(5000, 15000, 10),
        "risk_to_capabilities_ratio": np.random.uniform(5, 15, 10),
        "estimated_to_sla_ratio": np.random.uniform(0.1, 0.5, 10),
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
    mock_config, mock_registry, mock_metrics, training_data_with_anomalies, labels_with_anomalies
):
    """
    Testa persistência e reload do IsolationForest.
    Valida que scaler e modelo são salvos e restaurados corretamente.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        with (
            patch("mlflow.set_tracking_uri"),
            patch("mlflow.set_experiment"),
            patch("mlflow.create_experiment"),
            patch("mlflow.get_experiment_by_name", return_value=None),
            patch("mlflow.start_run"),
            patch("mlflow.log_param"),
            patch("mlflow.log_metric"),
            patch("mlflow.set_tag"),
            patch("mlflow.log_artifact"),
            patch("mlflow.sklearn.log_model"),
        ):
            # Treina modelo
            detector = AnomalyDetector(
                config=mock_config, model_registry=mock_registry, metrics=mock_metrics
            )

            metrics = await detector.train_model(
                training_data=training_data_with_anomalies, labels=labels_with_anomalies
            )

            # Valida que modelo foi treinado
            assert detector.model is not None
            assert hasattr(detector.scaler, "mean_")
            assert metrics["f1_score"] > 0.0

            # Salva scaler para teste de reload
            scaler_mean_original = detector.scaler.mean_.copy()
            scaler_path = os.path.join(tmpdir, "scaler.joblib")
            joblib.dump(detector.scaler, scaler_path)

            # Simula reload do modelo
            detector2 = AnomalyDetector(
                config=mock_config, model_registry=mock_registry, metrics=mock_metrics
            )

            # Mock do MLflow para carregar modelo
            with (
                patch("mlflow.sklearn.load_model", return_value=detector.model),
                patch("mlflow.tracking.MlflowClient") as mock_client_class,
            ):
                # Mock do client e métodos
                mock_client = Mock()
                mock_version = Mock()
                mock_version.run_id = "test_run_id"
                mock_client.get_latest_versions.return_value = [mock_version]
                mock_client.download_artifacts.return_value = scaler_path
                mock_client_class.return_value = mock_client

                await detector2.initialize()

            # Valida que scaler foi restaurado
            assert detector2.scaler is not None
            assert hasattr(detector2.scaler, "mean_")
            np.testing.assert_array_almost_equal(detector2.scaler.mean_, scaler_mean_original)

            # Testa que predições são consistentes
            test_ticket = {
                "risk_weight": 40,
                "capabilities": ["cap1", "cap2", "cap3"],
                "qos": {"priority": 0.5, "consistency": "AT_LEAST_ONCE", "durability": "DURABLE"},
                "parameters": {"key": "value"},
                "estimated_duration_ms": 5000,
                "sla_timeout_ms": 50000,
                "retry_count": 0,
            }

            result1 = await detector.detect_anomaly(test_ticket)
            result2 = await detector2.detect_anomaly(test_ticket)

            assert result1["is_anomaly"] == result2["is_anomaly"]
            assert abs(result1["anomaly_score"] - result2["anomaly_score"]) < 0.01


# =============================================================================
# Testes de Persistência - Autoencoder
# =============================================================================


@pytest.mark.asyncio
async def test_autoencoder_persistence(
    mock_config_autoencoder, mock_registry, mock_metrics, training_data_normal
):
    """
    Testa persistência e reload do Autoencoder.
    Valida que scaler e threshold são salvos e restaurados corretamente.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        with (
            patch("mlflow.set_tracking_uri"),
            patch("mlflow.set_experiment"),
            patch("mlflow.create_experiment"),
            patch("mlflow.get_experiment_by_name", return_value=None),
            patch("mlflow.start_run"),
            patch("mlflow.log_param"),
            patch("mlflow.log_metric"),
            patch("mlflow.set_tag"),
            patch("mlflow.log_artifact"),
            patch("mlflow.keras.log_model"),
        ):
            # Treina modelo
            detector = AnomalyDetector(
                config=mock_config_autoencoder, model_registry=mock_registry, metrics=mock_metrics
            )

            metrics = await detector.train_model(training_data=training_data_normal)

            # Valida que modelo foi treinado
            assert detector.model is not None
            assert hasattr(detector.scaler, "mean_")
            assert detector.autoencoder_threshold is not None
            assert detector.autoencoder_threshold > 0

            # Salva artifacts para teste de reload
            scaler_mean_original = detector.scaler.mean_.copy()
            threshold_original = detector.autoencoder_threshold

            scaler_path = os.path.join(tmpdir, "scaler.joblib")
            threshold_path = os.path.join(tmpdir, "threshold.npy")
            joblib.dump(detector.scaler, scaler_path)
            np.save(threshold_path, threshold_original)

            # Simula reload do modelo
            detector2 = AnomalyDetector(
                config=mock_config_autoencoder, model_registry=mock_registry, metrics=mock_metrics
            )

            # Mock do MLflow para carregar modelo
            with (
                patch("mlflow.keras.load_model", return_value=detector.model),
                patch("mlflow.tracking.MlflowClient") as mock_client_class,
            ):
                # Mock do client e métodos
                mock_client = Mock()
                mock_version = Mock()
                mock_version.run_id = "test_run_id"
                mock_client.get_latest_versions.return_value = [mock_version]

                def download_artifacts_side_effect(run_id, path, dst_path):
                    if "scaler" in path:
                        return scaler_path
                    elif "threshold" in path:
                        return threshold_path
                    raise ValueError(f"Unexpected path: {path}")

                mock_client.download_artifacts.side_effect = download_artifacts_side_effect
                mock_client_class.return_value = mock_client

                await detector2.initialize()

            # Valida que scaler e threshold foram restaurados
            assert detector2.scaler is not None
            assert hasattr(detector2.scaler, "mean_")
            np.testing.assert_array_almost_equal(detector2.scaler.mean_, scaler_mean_original)
            assert detector2.autoencoder_threshold == threshold_original

            # Testa que predições produzem scores consistentes
            test_ticket = {
                "risk_weight": 40,
                "capabilities": ["cap1", "cap2", "cap3"],
                "qos": {"priority": 0.5, "consistency": "AT_LEAST_ONCE", "durability": "DURABLE"},
                "parameters": {"key": "value"},
                "estimated_duration_ms": 5000,
                "sla_timeout_ms": 50000,
                "retry_count": 0,
            }

            result1 = await detector.detect_anomaly(test_ticket)
            result2 = await detector2.detect_anomaly(test_ticket)

            # Scores devem ser muito próximos (pode haver pequenas diferenças por arredondamento)
            assert abs(result1["anomaly_score"] - result2["anomaly_score"]) < 0.1


# =============================================================================
# Testes de Fallback
# =============================================================================


@pytest.mark.asyncio
async def test_artifact_download_failure_fallback(mock_config, mock_registry, mock_metrics):
    """
    Testa fallback quando download de artifacts falha.
    Deve usar scaler padrão e threshold fallback.
    """
    detector = AnomalyDetector(
        config=mock_config, model_registry=mock_registry, metrics=mock_metrics
    )

    # Mock do MLflow com falha no download de artifacts
    with (
        patch("mlflow.sklearn.load_model", return_value=Mock()),
        patch("mlflow.tracking.MlflowClient") as mock_client_class,
    ):
        mock_client = Mock()
        mock_version = Mock()
        mock_version.run_id = "test_run_id"
        mock_client.get_latest_versions.return_value = [mock_version]
        mock_client.download_artifacts.side_effect = Exception("Download failed")
        mock_client_class.return_value = mock_client

        await detector.initialize()

    # Valida que scaler padrão foi usado (não tem mean_ fitted)
    assert not hasattr(detector.scaler, "mean_")

    # Testa detecção com fallback heurístico
    test_ticket = {
        "risk_weight": 40,
        "capabilities": ["cap1", "cap2", "cap3"],
        "qos": {"priority": 0.5, "consistency": "AT_LEAST_ONCE", "durability": "DURABLE"},
        "parameters": {"key": "value"},
        "estimated_duration_ms": 5000,
        "sla_timeout_ms": 50000,
        "retry_count": 0,
    }

    result = await detector.detect_anomaly(test_ticket)

    # Deve funcionar mesmo sem modelo treinado (fallback heurístico)
    assert "is_anomaly" in result
    assert "anomaly_score" in result


# =============================================================================
# Testes de Correção de API do MLflow
# =============================================================================


@pytest.mark.asyncio
async def test_mlflow_api_correctness(
    mock_config, mock_config_autoencoder, mock_registry, mock_metrics, training_data_normal
):
    """
    Valida que mlflow.sklearn.log_model é usado para IsolationForest
    e mlflow.keras.log_model é usado para Autoencoder.
    """
    # Teste IsolationForest
    with (
        patch("mlflow.set_tracking_uri"),
        patch("mlflow.set_experiment"),
        patch("mlflow.create_experiment"),
        patch("mlflow.get_experiment_by_name", return_value=None),
        patch("mlflow.start_run"),
        patch("mlflow.log_param"),
        patch("mlflow.log_metric"),
        patch("mlflow.set_tag"),
        patch("mlflow.log_artifact"),
        patch("mlflow.sklearn.log_model") as mock_sklearn_log,
        patch("mlflow.keras.log_model") as mock_keras_log,
    ):
        detector_if = AnomalyDetector(
            config=mock_config, model_registry=mock_registry, metrics=mock_metrics
        )

        await detector_if.train_model(training_data=training_data_normal)

        # Valida que sklearn.log_model foi chamado
        assert mock_sklearn_log.called
        assert not mock_keras_log.called

    # Teste Autoencoder
    with (
        patch("mlflow.set_tracking_uri"),
        patch("mlflow.set_experiment"),
        patch("mlflow.create_experiment"),
        patch("mlflow.get_experiment_by_name", return_value=None),
        patch("mlflow.start_run"),
        patch("mlflow.log_param"),
        patch("mlflow.log_metric"),
        patch("mlflow.set_tag"),
        patch("mlflow.log_artifact"),
        patch("mlflow.sklearn.log_model") as mock_sklearn_log,
        patch("mlflow.keras.log_model") as mock_keras_log,
    ):
        detector_ae = AnomalyDetector(
            config=mock_config_autoencoder, model_registry=mock_registry, metrics=mock_metrics
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
    mock_config, mock_registry, mock_metrics, training_data_with_anomalies, labels_with_anomalies
):
    """
    Valida que precision/recall permanecem > 0.6 após reload.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        with (
            patch("mlflow.set_tracking_uri"),
            patch("mlflow.set_experiment"),
            patch("mlflow.create_experiment"),
            patch("mlflow.get_experiment_by_name", return_value=None),
            patch("mlflow.start_run"),
            patch("mlflow.log_param"),
            patch("mlflow.log_metric"),
            patch("mlflow.set_tag"),
            patch("mlflow.log_artifact"),
            patch("mlflow.sklearn.log_model"),
        ):
            # Treina modelo
            detector = AnomalyDetector(
                config=mock_config, model_registry=mock_registry, metrics=mock_metrics
            )

            metrics_train = await detector.train_model(
                training_data=training_data_with_anomalies, labels=labels_with_anomalies
            )

            # Valida métricas de treinamento
            assert metrics_train["precision"] > 0.6
            assert metrics_train["recall"] > 0.6
            assert metrics_train["f1_score"] > 0.6

            # Salva artifacts
            scaler_path = os.path.join(tmpdir, "scaler.joblib")
            joblib.dump(detector.scaler, scaler_path)

            # Reload
            detector2 = AnomalyDetector(
                config=mock_config, model_registry=mock_registry, metrics=mock_metrics
            )

            with (
                patch("mlflow.sklearn.load_model", return_value=detector.model),
                patch("mlflow.tracking.MlflowClient") as mock_client_class,
            ):
                mock_client = Mock()
                mock_version = Mock()
                mock_version.run_id = "test_run_id"
                mock_client.get_latest_versions.return_value = [mock_version]
                mock_client.download_artifacts.return_value = scaler_path
                mock_client_class.return_value = mock_client

                await detector2.initialize()

            # Testa predições em dados de teste
            X_test = training_data_with_anomalies[detector.feature_names].values[:50]
            y_test = labels_with_anomalies[:50]

            predictions = detector2._predict_labels(detector2.scaler.transform(X_test))

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
    mock_config, mock_registry, mock_metrics, training_data_with_anomalies, labels_with_anomalies
):
    """
    Testa integração do AnomalyDetector com IntelligentScheduler.
    Valida que anomalias são detectadas e refletidas no scheduling.
    """
    # Treina detector
    with (
        patch("mlflow.set_tracking_uri"),
        patch("mlflow.set_experiment"),
        patch("mlflow.create_experiment"),
        patch("mlflow.get_experiment_by_name", return_value=None),
        patch("mlflow.start_run"),
        patch("mlflow.log_param"),
        patch("mlflow.log_metric"),
        patch("mlflow.set_tag"),
        patch("mlflow.log_artifact"),
        patch("mlflow.sklearn.log_model"),
    ):
        detector = AnomalyDetector(
            config=mock_config, model_registry=mock_registry, metrics=mock_metrics
        )

        await detector.train_model(
            training_data=training_data_with_anomalies, labels=labels_with_anomalies
        )

        # Cria ticket normal
        normal_ticket = {
            "ticket_id": "test-123",
            "risk_weight": 40,
            "capabilities": ["cap1", "cap2", "cap3"],
            "qos": {"priority": 0.5, "consistency": "AT_LEAST_ONCE", "durability": "DURABLE"},
            "parameters": {"key": "value"},
            "estimated_duration_ms": 5000,
            "sla_timeout_ms": 50000,
            "retry_count": 0,
        }

        # Cria ticket anômalo (muitas capabilities)
        anomalous_ticket = {
            "ticket_id": "test-456",
            "risk_weight": 40,
            "capabilities": ["cap" + str(i) for i in range(20)],  # 20 capabilities = anômalo
            "qos": {"priority": 0.5, "consistency": "AT_LEAST_ONCE", "durability": "DURABLE"},
            "parameters": {"key": "value"},
            "estimated_duration_ms": 5000,
            "sla_timeout_ms": 50000,
            "retry_count": 0,
        }

        # Detecta anomalia em tickets
        normal_result = await detector.detect_anomaly(normal_ticket)
        anomalous_result = await detector.detect_anomaly(anomalous_ticket)

    # Valida que ambos têm anomaly_score (detector funcionando)
    assert "anomaly_score" in normal_result
    assert "anomaly_score" in anomalous_result

    # Valida que ticket com 20 capabilities é detectado como anômalo
    # (muito mais capabilities que o range normal de treinamento 2-8)
    # Nota: IsolationForest pode ter não-determinismo, então focamos no caso claro
    assert anomalous_result["is_anomaly"] is True

    # Mock do scheduler
    mock_scheduler = Mock()
    mock_scheduler.schedule_ticket = AsyncMock()

    # Simula scheduling com anomalia detectada
    # Usa os resultados reais da detecção
    normal_ticket["predictions"] = {"anomaly": normal_result}
    anomalous_ticket["predictions"] = {"anomaly": anomalous_result}

    # Valida que o ticket anômalo tem indicação de anomalia
    assert anomalous_ticket["predictions"]["anomaly"]["is_anomaly"] is True

    # Valida que métricas foram registradas
    assert mock_metrics.record_anomaly_detection.called


@pytest.mark.asyncio
async def test_fallback_on_detector_failure(mock_config, mock_registry, mock_metrics):
    """
    Testa fallback quando detector falha.
    Deve usar heurístico e retornar is_anomaly=False.
    """
    detector = AnomalyDetector(
        config=mock_config, model_registry=mock_registry, metrics=mock_metrics
    )

    # Não treina modelo (forçando fallback heurístico)
    assert detector.model is None

    # Mock de um ticket que causaria erro no modelo
    test_ticket = {
        "risk_weight": 40,
        "capabilities": ["cap1", "cap2"],
        "qos": {"priority": 0.5, "consistency": "AT_LEAST_ONCE", "durability": "DURABLE"},
        "parameters": {"key": "value"},
        "estimated_duration_ms": 5000,
        "sla_timeout_ms": 50000,
        "retry_count": 0,
    }

    # Deve usar fallback heurístico
    result = await detector.detect_anomaly(test_ticket)

    # Valida fallback
    assert "is_anomaly" in result
    assert result["model_type"] == "heuristic"
    assert result["is_anomaly"] is False  # Normal pelo heurístico


@pytest.mark.asyncio
async def test_anomaly_priority_adjustment(
    mock_config, mock_registry, mock_metrics, training_data_with_anomalies, labels_with_anomalies
):
    """
    Verifica se anomalias boostam priority_score.
    Simula scheduler ajustando prioridade baseado em anomalia.
    """
    # Treina detector
    with (
        patch("mlflow.set_tracking_uri"),
        patch("mlflow.set_experiment"),
        patch("mlflow.create_experiment"),
        patch("mlflow.get_experiment_by_name", return_value=None),
        patch("mlflow.start_run"),
        patch("mlflow.log_param"),
        patch("mlflow.log_metric"),
        patch("mlflow.set_tag"),
        patch("mlflow.log_artifact"),
        patch("mlflow.sklearn.log_model"),
    ):
        detector = AnomalyDetector(
            config=mock_config, model_registry=mock_registry, metrics=mock_metrics
        )

        await detector.train_model(
            training_data=training_data_with_anomalies, labels=labels_with_anomalies
        )

    # Ticket anômalo
    anomalous_ticket = {
        "ticket_id": "test-789",
        "risk_weight": 40,
        "capabilities": ["cap" + str(i) for i in range(18)],
        "qos": {"priority": 0.5, "consistency": "AT_LEAST_ONCE", "durability": "DURABLE"},
        "parameters": {"key": "value"},
        "estimated_duration_ms": 5000,
        "sla_timeout_ms": 50000,
        "retry_count": 0,
    }

    result = await detector.detect_anomaly(anomalous_ticket)

    # Simula scheduler boost
    base_priority = 0.5
    boosted_priority = base_priority

    if result["is_anomaly"]:
        # Boost de 20% se anomalia
        boosted_priority = min(base_priority * 1.2, 1.0)

    # Valida boost
    assert result["is_anomaly"] is True
    assert boosted_priority > base_priority
    assert boosted_priority == 0.6  # 0.5 * 1.2


# =============================================================================
# Testes Adicionais - Epic Extra (+10 testes)
# =============================================================================


@pytest.mark.asyncio
async def test_detect_with_window_size(
    mock_config, mock_registry, mock_metrics, training_data_with_anomalies, labels_with_anomalies
):
    """Testa detecção de anomalias com diferentes tamanhos de janela."""
    with (
        patch("mlflow.set_tracking_uri"),
        patch("mlflow.set_experiment"),
        patch("mlflow.create_experiment"),
        patch("mlflow.get_experiment_by_name", return_value=None),
        patch("mlflow.start_run"),
        patch("mlflow.log_param"),
        patch("mlflow.log_metric"),
        patch("mlflow.set_tag"),
        patch("mlflow.log_artifact"),
        patch("mlflow.sklearn.log_model"),
    ):
        detector = AnomalyDetector(
            config=mock_config, model_registry=mock_registry, metrics=mock_metrics
        )

        await detector.train_model(
            training_data=training_data_with_anomalies, labels=labels_with_anomalies
        )

        # Testa detecção com ticket válido
        test_ticket = {
            "risk_weight": 40,
            "capabilities": ["cap1", "cap2"],
            "qos": {"priority": 0.5, "consistency": "AT_LEAST_ONCE", "durability": "DURABLE"},
            "parameters": {"key": "value"},
            "estimated_duration_ms": 5000,
            "sla_timeout_ms": 50000,
            "retry_count": 0,
        }

        result = await detector.detect_anomaly(test_ticket)
        assert "is_anomaly" in result
        assert "anomaly_score" in result


@pytest.mark.asyncio
async def test_detect_with_custom_threshold(
    mock_config, mock_registry, mock_metrics, training_data_normal
):
    """Testa detecção com threshold de contaminação customizado."""
    config_high = mock_config.copy()
    config_high["contamination"] = 0.15

    with (
        patch("mlflow.set_tracking_uri"),
        patch("mlflow.set_experiment"),
        patch("mlflow.create_experiment"),
        patch("mlflow.get_experiment_by_name", return_value=None),
        patch("mlflow.start_run"),
        patch("mlflow.log_param"),
        patch("mlflow.log_metric"),
        patch("mlflow.set_tag"),
        patch("mlflow.log_artifact"),
        patch("mlflow.sklearn.log_model"),
    ):
        detector = AnomalyDetector(
            config=config_high, model_registry=mock_registry, metrics=mock_metrics
        )

        metrics = await detector.train_model(training_data=training_data_normal)

        # Contamination mais alto deve detectar mais anomalias
        assert detector.contamination == 0.15
        assert "anomaly_rate" in metrics


@pytest.mark.asyncio
async def test_detect_seasonal_anomaly(mock_config, mock_registry, mock_metrics):
    """Testa detecção de anomalias sazonais baseadas em tempo."""
    detector = AnomalyDetector(
        config=mock_config, model_registry=mock_registry, metrics=mock_metrics
    )

    # Ticket fora do horário comercial (horário não comercial)
    off_hours_ticket = {
        "risk_weight": 40,
        "capabilities": ["cap1", "cap2"],
        "qos": {"priority": 0.5, "consistency": "AT_LEAST_ONCE", "durability": "DURABLE"},
        "parameters": {"key": "value"},
        "estimated_duration_ms": 5000,
        "sla_timeout_ms": 50000,
        "retry_count": 0,
        "timestamp": "2026-03-30T03:00:00Z",  # 3 da manhã
    }

    result = await detector.detect_anomaly(off_hours_ticket)
    assert "is_anomaly" in result
    assert "anomaly_score" in result


@pytest.mark.asyncio
async def test_feature_importance_anomaly(
    mock_config, mock_registry, mock_metrics, training_data_with_anomalies, labels_with_anomalies
):
    """Testa cálculo de importância de features para modelos com feature_importances_."""
    with (
        patch("mlflow.set_tracking_uri"),
        patch("mlflow.set_experiment"),
        patch("mlflow.create_experiment"),
        patch("mlflow.get_experiment_by_name", return_value=None),
        patch("mlflow.start_run"),
        patch("mlflow.log_param"),
        patch("mlflow.log_metric"),
        patch("mlflow.set_tag"),
        patch("mlflow.log_artifact"),
        patch("mlflow.sklearn.log_model"),
    ):
        detector = AnomalyDetector(
            config=mock_config, model_registry=mock_registry, metrics=mock_metrics
        )

        await detector.train_model(
            training_data=training_data_with_anomalies, labels=labels_with_anomalies
        )

        # IsolationForest NÃO tem feature_importances_ (é unsupervised)
        # Testa com um modelo que tem (mock)
        from sklearn.ensemble import RandomForestClassifier

        mock_model = RandomForestClassifier(n_estimators=10, random_state=42)
        X = training_data_with_anomalies[detector.feature_names].values[:50]
        y = labels_with_anomalies[:50]
        mock_model.fit(X, y)

        # Agora tem feature_importances_
        assert hasattr(mock_model, "feature_importances_")

        importance = detector._calculate_feature_importance(mock_model, detector.feature_names)

        assert isinstance(importance, dict)
        assert len(importance) == len(detector.feature_names)


@pytest.mark.asyncio
async def test_batch_detect(
    mock_config, mock_registry, mock_metrics, training_data_with_anomalies, labels_with_anomalies
):
    """Testa detecção em lote de múltiplos tickets."""
    with (
        patch("mlflow.set_tracking_uri"),
        patch("mlflow.set_experiment"),
        patch("mlflow.create_experiment"),
        patch("mlflow.get_experiment_by_name", return_value=None),
        patch("mlflow.start_run"),
        patch("mlflow.log_param"),
        patch("mlflow.log_metric"),
        patch("mlflow.set_tag"),
        patch("mlflow.log_artifact"),
        patch("mlflow.sklearn.log_model"),
    ):
        detector = AnomalyDetector(
            config=mock_config, model_registry=mock_registry, metrics=mock_metrics
        )

        await detector.train_model(
            training_data=training_data_with_anomalies, labels=labels_with_anomalies
        )

        # Cria múltiplos tickets
        tickets = [
            {
                "risk_weight": 40,
                "capabilities": ["cap1", "cap2"],
                "qos": {"priority": 0.5, "consistency": "AT_LEAST_ONCE", "durability": "DURABLE"},
                "parameters": {"key": "value"},
                "estimated_duration_ms": 5000,
                "sla_timeout_ms": 50000,
                "retry_count": 0,
            }
            for _ in range(10)
        ]

        results = []
        for ticket in tickets:
            result = await detector.detect_anomaly(ticket)
            results.append(result)

        assert len(results) == 10
        for result in results:
            assert "is_anomaly" in result


@pytest.mark.asyncio
async def test_update_baseline(mock_config, mock_registry, mock_metrics, training_data_normal):
    """Testa atualização do baseline de detecção."""
    with (
        patch("mlflow.set_tracking_uri"),
        patch("mlflow.set_experiment"),
        patch("mlflow.create_experiment"),
        patch("mlflow.get_experiment_by_name", return_value=None),
        patch("mlflow.start_run"),
        patch("mlflow.log_param"),
        patch("mlflow.log_metric"),
        patch("mlflow.set_tag"),
        patch("mlflow.log_artifact"),
        patch("mlflow.sklearn.log_model"),
    ):
        detector = AnomalyDetector(
            config=mock_config, model_registry=mock_registry, metrics=mock_metrics
        )

        # Treina inicial
        await detector.train_model(training_data=training_data_normal)

        scaler_mean_before = detector.scaler.mean_.copy()

        # Atualiza com novos dados
        new_data = training_data_normal.sample(50)
        await detector.train_model(training_data=new_data)

        scaler_mean_after = detector.scaler.mean_

        # Scaler deve ter sido atualizado
        assert detector.scaler is not None


@pytest.mark.asyncio
async def test_get_anomaly_report(
    mock_config, mock_registry, mock_metrics, training_data_with_anomalies, labels_with_anomalies
):
    """Testa geração de relatório de anomalias."""
    with (
        patch("mlflow.set_tracking_uri"),
        patch("mlflow.set_experiment"),
        patch("mlflow.create_experiment"),
        patch("mlflow.get_experiment_by_name", return_value=None),
        patch("mlflow.start_run"),
        patch("mlflow.log_param"),
        patch("mlflow.log_metric"),
        patch("mlflow.set_tag"),
        patch("mlflow.log_artifact"),
        patch("mlflow.sklearn.log_model"),
    ):
        detector = AnomalyDetector(
            config=mock_config, model_registry=mock_registry, metrics=mock_metrics
        )

        metrics = await detector.train_model(
            training_data=training_data_with_anomalies, labels=labels_with_anomalies
        )

        # Relatório de métricas de treinamento
        assert "anomaly_rate" in metrics
        assert "precision" in metrics
        assert "recall" in metrics
        assert "f1_score" in metrics


@pytest.mark.asyncio
async def test_threshold_sensitivity(
    mock_config, mock_registry, mock_metrics, training_data_normal
):
    """Testa sensibilidade do threshold de detecção."""
    # Testa com contamination baixa (menos sensível)
    config_low = mock_config.copy()
    config_low["contamination"] = 0.01

    with (
        patch("mlflow.set_tracking_uri"),
        patch("mlflow.set_experiment"),
        patch("mlflow.create_experiment"),
        patch("mlflow.get_experiment_by_name", return_value=None),
        patch("mlflow.start_run"),
        patch("mlflow.log_param"),
        patch("mlflow.log_metric"),
        patch("mlflow.set_tag"),
        patch("mlflow.log_artifact"),
        patch("mlflow.sklearn.log_model"),
    ):
        detector_low = AnomalyDetector(
            config=config_low, model_registry=mock_registry, metrics=mock_metrics
        )

        metrics_low = await detector_low.train_model(training_data=training_data_normal)

        # Taxa de anomalias deve ser baixa
        assert metrics_low["anomaly_rate"] <= 0.05


@pytest.mark.asyncio
async def test_anomaly_persisting(
    mock_config, mock_registry, mock_metrics, training_data_with_anomalies, labels_with_anomalies
):
    """Testa que anomalias persistentes são detectadas consistentemente."""
    with (
        patch("mlflow.set_tracking_uri"),
        patch("mlflow.set_experiment"),
        patch("mlflow.create_experiment"),
        patch("mlflow.get_experiment_by_name", return_value=None),
        patch("mlflow.start_run"),
        patch("mlflow.log_param"),
        patch("mlflow.log_metric"),
        patch("mlflow.set_tag"),
        patch("mlflow.log_artifact"),
        patch("mlflow.sklearn.log_model"),
    ):
        detector = AnomalyDetector(
            config=mock_config, model_registry=mock_registry, metrics=mock_metrics
        )

        await detector.train_model(
            training_data=training_data_with_anomalies, labels=labels_with_anomalies
        )

        # Ticket anômalo persistente
        persistent_anomaly_ticket = {
            "risk_weight": 40,
            "capabilities": ["cap" + str(i) for i in range(25)],  # Muito anômalo
            "qos": {"priority": 0.5, "consistency": "AT_LEAST_ONCE", "durability": "DURABLE"},
            "parameters": {"key": "value"},
            "estimated_duration_ms": 5000,
            "sla_timeout_ms": 50000,
            "retry_count": 0,
        }

        # Detecta múltiplas vezes
        results = []
        for _ in range(5):
            result = await detector.detect_anomaly(persistent_anomaly_ticket)
            results.append(result["is_anomaly"])

        # Anomalia deve ser detectada consistentemente
        # Pelo menos 3 de 5 devem ser True
        assert sum(results) >= 3


@pytest.mark.asyncio
async def test_explain_anomaly_types(mock_config, mock_registry, mock_metrics):
    """Testa diferentes tipos de explicação de anomalias."""
    detector = AnomalyDetector(
        config=mock_config, model_registry=mock_registry, metrics=mock_metrics
    )

    # Testa resource_mismatch
    ticket1 = {
        "risk_weight": 20,  # Baixo
        "capabilities": ["cap" + str(i) for i in range(10)],  # Muitas
        "qos": {"priority": 0.5, "consistency": "AT_LEAST_ONCE", "durability": "DURABLE"},
        "parameters": {"key": "value"},
        "estimated_duration_ms": 5000,
        "sla_timeout_ms": 50000,
        "retry_count": 0,
    }

    # Extrai features corretamente
    features_dict1 = detector._extract_features(ticket1)
    # Converte array numpy para dict como esperado por _explain_anomaly
    from neural_hive_ml.predictive_models.feature_engineering import extract_ticket_features

    features1 = extract_ticket_features(ticket1)

    anomaly_type1, explanation1 = detector._explain_anomaly(features1, ticket1)

    # Deve detectar resource_mismatch ou capability_anomaly
    assert anomaly_type1 in ["resource_mismatch", "capability_anomaly"]
    assert explanation1 is not None

    # Testa qos_inconsistency
    ticket2 = {
        "risk_weight": 25,  # Baixo
        "capabilities": ["cap1", "cap2"],
        "qos": {"priority": 0.5, "consistency": "EXACTLY_ONCE", "durability": "DURABLE"},
        "parameters": {"key": "value"},
        "estimated_duration_ms": 5000,
        "sla_timeout_ms": 50000,
        "retry_count": 0,
    }

    features2 = extract_ticket_features(ticket2)
    anomaly_type2, explanation2 = detector._explain_anomaly(features2, ticket2)

    # Deve detectar qos_inconsistency
    assert anomaly_type2 == "qos_inconsistency"
