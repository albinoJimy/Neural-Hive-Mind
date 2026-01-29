"""
Testes para AnomalyDetector.

Testa:
- Treinamento do modelo Isolation Forest
- Detecção de anomalias em métricas
- Cálculo de severidade
- Identificação de features anômalas
- Persistência e carregamento de modelos
"""

import pytest
import numpy as np
import tempfile
import shutil
import os
from unittest.mock import Mock, patch

from neural_hive_specialists.observability.anomaly_detector import AnomalyDetector


@pytest.fixture
def mock_config():
    """Config mock para testes."""
    temp_dir = tempfile.mkdtemp()

    config = {
        "enable_anomaly_detection": True,
        "anomaly_contamination": 0.1,
        "anomaly_n_estimators": 50,  # Reduzido para testes mais rápidos
        "anomaly_model_path": os.path.join(
            temp_dir, "anomaly_detector_{specialist_type}.pkl"
        ),
        "anomaly_alert_threshold": -0.3,
    }

    yield config

    # Cleanup
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def detector(mock_config):
    """Instância de AnomalyDetector para testes."""
    return AnomalyDetector(mock_config)


@pytest.fixture
def normal_metrics_history():
    """Gera histórico de métricas normais (distribuição normal)."""
    np.random.seed(42)

    history = []
    for _ in range(150):  # Mais que o mínimo de 100
        history.append(
            {
                "consensus_agreement_rate": np.random.normal(0.85, 0.05),
                "false_positive_rate": np.random.normal(0.10, 0.03),
                "false_negative_rate": np.random.normal(0.08, 0.03),
                "avg_confidence_score": np.random.normal(0.75, 0.10),
                "avg_risk_score": np.random.normal(0.30, 0.10),
                "avg_processing_time_ms": np.random.normal(500, 100),
                "evaluation_count": np.random.randint(50, 150),
                "precision": np.random.normal(0.80, 0.05),
                "recall": np.random.normal(0.82, 0.05),
            }
        )

    return history


@pytest.fixture
def anomalous_metrics():
    """Gera métricas anômalas (fora da distribuição normal)."""
    return {
        "consensus_agreement_rate": 0.30,  # Muito baixo (normal ~0.85)
        "false_positive_rate": 0.50,  # Muito alto (normal ~0.10)
        "false_negative_rate": 0.45,  # Muito alto (normal ~0.08)
        "avg_confidence_score": 0.20,  # Muito baixo (normal ~0.75)
        "avg_risk_score": 0.80,  # Muito alto (normal ~0.30)
        "avg_processing_time_ms": 2000,  # Muito alto (normal ~500)
        "evaluation_count": 10,  # Muito baixo (normal ~100)
        "precision": 0.40,  # Muito baixo (normal ~0.80)
        "recall": 0.35,  # Muito baixo (normal ~0.82)
    }


class TestTrainOnHistoricalData:
    """Testes para train_on_historical_data."""

    def test_successful_training(self, detector, normal_metrics_history):
        """Testa treinamento bem-sucedido com dados suficientes."""
        result = detector.train_on_historical_data(
            normal_metrics_history, specialist_type="technical"
        )

        assert result is True
        assert detector.is_trained is True
        assert detector._model is not None
        assert detector._scaler is not None

    def test_insufficient_data(self, detector):
        """Testa com dados insuficientes (< 100 amostras)."""
        small_history = [
            {
                "consensus_agreement_rate": 0.85,
                "false_positive_rate": 0.10,
                "false_negative_rate": 0.08,
                "avg_confidence_score": 0.75,
                "avg_risk_score": 0.30,
                "avg_processing_time_ms": 500,
                "evaluation_count": 100,
                "precision": 0.80,
                "recall": 0.82,
            }
        ] * 50  # Apenas 50 amostras

        result = detector.train_on_historical_data(small_history)

        assert result is False
        assert detector.is_trained is False

    def test_empty_data(self, detector):
        """Testa com lista vazia."""
        result = detector.train_on_historical_data([])

        assert result is False
        assert detector.is_trained is False

    def test_training_disabled(self, detector):
        """Testa quando anomaly detection está desabilitado."""
        detector.enable_anomaly_detection = False

        result = detector.train_on_historical_data(
            [{"consensus_agreement_rate": 0.85}] * 100
        )

        assert result is False
        assert detector.is_trained is False

    def test_model_persistence(self, detector, normal_metrics_history, mock_config):
        """Testa que o modelo é salvo após treinamento."""
        result = detector.train_on_historical_data(
            normal_metrics_history, specialist_type="technical"
        )

        assert result is True

        # Verificar que arquivo foi criado
        base_path = (
            mock_config["anomaly_model_path"]
            .format(specialist_type="technical")
            .replace(".pkl", "")
        )
        latest_path = f"{base_path}_latest.pkl"

        assert os.path.exists(latest_path)


class TestDetectAnomalies:
    """Testes para detect_anomalies."""

    def test_normal_metrics(self, detector, normal_metrics_history):
        """Testa detecção com métricas normais."""
        # Treinar modelo
        detector.train_on_historical_data(normal_metrics_history)

        # Testar com métricas normais
        normal_metrics = {
            "consensus_agreement_rate": 0.85,
            "false_positive_rate": 0.10,
            "false_negative_rate": 0.08,
            "avg_confidence_score": 0.75,
            "avg_risk_score": 0.30,
            "avg_processing_time_ms": 500,
            "evaluation_count": 100,
            "precision": 0.80,
            "recall": 0.82,
        }

        result = detector.detect_anomalies(normal_metrics)

        assert result["is_anomaly"] is False
        assert result["severity"] == "info"
        assert result["anomalous_features"] == []

    def test_anomalous_metrics(
        self, detector, normal_metrics_history, anomalous_metrics
    ):
        """Testa detecção com métricas anômalas."""
        # Treinar modelo
        detector.train_on_historical_data(normal_metrics_history)

        # Testar com métricas anômalas
        result = detector.detect_anomalies(anomalous_metrics)

        assert result["is_anomaly"] is True
        assert result["severity"] in ["warning", "critical"]
        assert len(result["anomalous_features"]) > 0

    def test_severity_thresholds(self, detector, normal_metrics_history):
        """Testa cálculo correto de severidade."""
        detector.train_on_historical_data(normal_metrics_history)

        # Mock score_samples para controlar anomaly score
        with patch.object(detector._model, "score_samples") as mock_score:
            # Testar severity: info (score > -0.3)
            mock_score.return_value = np.array([-0.2])
            with patch.object(detector._model, "predict", return_value=np.array([-1])):
                result = detector.detect_anomalies(anomalous_metrics)
                assert result["severity"] == "info"

            # Testar severity: warning (-0.5 < score <= -0.3)
            mock_score.return_value = np.array([-0.4])
            with patch.object(detector._model, "predict", return_value=np.array([-1])):
                result = detector.detect_anomalies(anomalous_metrics)
                assert result["severity"] == "warning"

            # Testar severity: critical (score <= -0.5)
            mock_score.return_value = np.array([-0.6])
            with patch.object(detector._model, "predict", return_value=np.array([-1])):
                result = detector.detect_anomalies(anomalous_metrics)
                assert result["severity"] == "critical"

    def test_model_not_trained(self, detector):
        """Testa detecção sem modelo treinado."""
        metrics = {"consensus_agreement_rate": 0.85}

        result = detector.detect_anomalies(metrics)

        assert result["is_anomaly"] is False
        assert "error" in result
        assert result["error"] == "model_not_trained"

    def test_detection_disabled(self, detector):
        """Testa quando detecção está desabilitada."""
        detector.enable_anomaly_detection = False

        result = detector.detect_anomalies({"consensus_agreement_rate": 0.85})

        assert result["is_anomaly"] is False
        assert result["anomaly_score"] == 0.0

    def test_identify_anomalous_features(
        self, detector, normal_metrics_history, anomalous_metrics
    ):
        """Testa identificação de features anômalas (z-score > 2)."""
        detector.train_on_historical_data(normal_metrics_history)

        result = detector.detect_anomalies(anomalous_metrics)

        # Deve identificar features com valores muito distantes da média
        if result["is_anomaly"]:
            assert len(result["anomalous_features"]) > 0
            # Consensus agreement rate muito baixo deve ser identificado
            assert any(
                "consensus_agreement" in f
                or "false_positive" in f
                or "false_negative" in f
                for f in result["anomalous_features"]
            )

    def test_invalid_features(self, detector, normal_metrics_history):
        """Testa com features inválidos."""
        detector.train_on_historical_data(normal_metrics_history)

        # Métricas com valores None
        invalid_metrics = {
            "consensus_agreement_rate": None,
            "false_positive_rate": "invalid",
            "false_negative_rate": 0.08,
        }

        result = detector.detect_anomalies(invalid_metrics)

        # Deve retornar erro de features inválidos
        assert "error" in result


class TestModelPersistence:
    """Testes para persistência e carregamento de modelos."""

    def test_save_and_load_model(self, detector, normal_metrics_history, mock_config):
        """Testa salvar e carregar modelo."""
        # Treinar e salvar
        detector.train_on_historical_data(
            normal_metrics_history, specialist_type="technical"
        )

        # Criar novo detector e carregar modelo
        new_detector = AnomalyDetector(mock_config)
        result = new_detector.load_model_for_specialist("technical")

        assert result is True
        assert new_detector.is_trained is True
        assert new_detector._model is not None
        assert new_detector._scaler is not None

    def test_load_nonexistent_model(self, detector):
        """Testa carregar modelo que não existe."""
        result = detector.load_model_for_specialist("nonexistent")

        assert result is False
        assert detector.is_trained is False

    def test_model_versioning(self, detector, normal_metrics_history, mock_config):
        """Testa versionamento de modelos."""
        # Treinar múltiplas vezes
        detector.train_on_historical_data(
            normal_metrics_history, specialist_type="technical"
        )

        base_path = (
            mock_config["anomaly_model_path"]
            .format(specialist_type="technical")
            .replace(".pkl", "")
        )

        # Verificar que versão timestamped foi criada
        import glob

        versioned_files = glob.glob(f"{base_path}_*.pkl")

        # Deve ter pelo menos latest + uma versão timestamped
        assert len(versioned_files) >= 2


class TestFeaturePreparation:
    """Testes para preparação de features."""

    def test_prepare_features_valid(self, detector):
        """Testa preparação de features válidos."""
        metrics = {
            "consensus_agreement_rate": 0.85,
            "false_positive_rate": 0.10,
            "false_negative_rate": 0.08,
            "avg_confidence_score": 0.75,
            "avg_risk_score": 0.30,
            "avg_processing_time_ms": 500,
            "evaluation_count": 100,
            "precision": 0.80,
            "recall": 0.82,
        }

        features = detector._prepare_features(metrics)

        assert features is not None
        assert features.shape == (9,)  # 9 features
        assert all(isinstance(v, (int, float)) for v in features)

    def test_prepare_features_missing_keys(self, detector):
        """Testa preparação com keys faltando (deve usar 0.0)."""
        metrics = {"consensus_agreement_rate": 0.85, "precision": 0.80}

        features = detector._prepare_features(metrics)

        assert features is not None
        assert features.shape == (9,)
        # Features faltando devem ser 0.0
        assert features[1] == 0.0  # false_positive_rate

    def test_prepare_features_invalid_values(self, detector):
        """Testa preparação com valores inválidos."""
        metrics = {
            "consensus_agreement_rate": None,
            "false_positive_rate": "invalid",
            "false_negative_rate": 0.08,
        }

        features = detector._prepare_features(metrics)

        # Deve retornar array com valores inválidos convertidos para 0.0
        assert features is not None
        assert features[0] == 0.0  # None -> 0.0

    def test_prepare_features_batch(self, detector):
        """Testa preparação de batch de métricas."""
        metrics_list = [
            {"consensus_agreement_rate": 0.85, "precision": 0.80},
            {"consensus_agreement_rate": 0.90, "precision": 0.85},
            {"consensus_agreement_rate": 0.75, "precision": 0.70},
        ]

        features_batch = detector._prepare_features_batch(metrics_list)

        assert features_batch.shape == (3, 9)  # 3 amostras, 9 features


class TestEdgeCases:
    """Testes para casos extremos."""

    def test_extreme_values(self, detector, normal_metrics_history):
        """Testa com valores extremos."""
        detector.train_on_historical_data(normal_metrics_history)

        extreme_metrics = {
            "consensus_agreement_rate": 0.0,
            "false_positive_rate": 1.0,
            "false_negative_rate": 1.0,
            "avg_confidence_score": 0.0,
            "avg_risk_score": 1.0,
            "avg_processing_time_ms": 10000,
            "evaluation_count": 1,
            "precision": 0.0,
            "recall": 0.0,
        }

        result = detector.detect_anomalies(extreme_metrics)

        # Valores extremos devem ser detectados como anômalos
        assert result["is_anomaly"] is True
        assert result["severity"] == "critical"

    def test_all_zero_metrics(self, detector, normal_metrics_history):
        """Testa com todas as métricas em zero."""
        detector.train_on_historical_data(normal_metrics_history)

        zero_metrics = {k: 0.0 for k in detector.feature_names}

        result = detector.detect_anomalies(zero_metrics)

        assert result["is_anomaly"] is True


class TestUtilityMethods:
    """Testes para métodos utilitários."""

    def test_get_feature_importance(self, detector, normal_metrics_history):
        """Testa obtenção de feature importance."""
        # Antes de treinar
        importance = detector.get_feature_importance()
        assert importance == {}

        # Após treinar
        detector.train_on_historical_data(normal_metrics_history)
        importance = detector.get_feature_importance()

        assert len(importance) == 9
        # Isolation Forest retorna pesos uniformes
        assert all(v == 1.0 / 9 for v in importance.values())

    def test_get_anomaly_threshold(self, detector):
        """Testa obtenção de threshold."""
        threshold = detector.get_anomaly_threshold()

        assert threshold == -0.3

    def test_is_trained_property(self, detector, normal_metrics_history):
        """Testa propriedade is_trained."""
        assert detector.is_trained is False

        detector.train_on_historical_data(normal_metrics_history)

        assert detector.is_trained is True
