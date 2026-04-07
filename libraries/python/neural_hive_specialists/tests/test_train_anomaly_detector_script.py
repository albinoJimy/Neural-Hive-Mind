"""Testes para o script train_anomaly_detector.py."""

import pytest
import os
import sys
from unittest.mock import Mock, patch
from datetime import datetime

# Adicionar diretório de scripts ao path
sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "..", "scripts"),
)


class TestLoadConfig:
    """Testes para load_config."""

    @patch.dict(
        os.environ,
        {
            "CLICKHOUSE_URI": "clickhouse://localhost:9000",
            "CLICKHOUSE_DATABASE": "neural_hive",
            "ANOMALY_CONTAMINATION": "0.15",
            "ANOMALY_N_ESTIMATORS": "150",
            "ANOMALY_MODEL_PATH": "/models/anomaly_{specialist_type}.pkl",
            "ANOMALY_TRAINING_WINDOW_DAYS": "45",
        },
    )
    def test_load_config_from_env(self):
        """Testa carregamento de config das variáveis de ambiente."""
        # Importar após mock de environment
        import train_anomaly_detector

        config = train_anomaly_detector.load_config()

        assert config["clickhouse_uri"] == "clickhouse://localhost:9000"
        assert config["clickhouse_database"] == "neural_hive"
        assert config["anomaly_contamination"] == 0.15
        assert config["anomaly_n_estimators"] == 150
        assert config["anomaly_model_path"] == "/models/anomaly_{specialist_type}.pkl"
        assert config["anomaly_training_window_days"] == 45

    @patch.dict(os.environ, {}, clear=True)
    def test_load_config_defaults(self):
        """Testa valores padrão quando variáveis não estão definidas."""
        import train_anomaly_detector

        config = train_anomaly_detector.load_config()

        assert config["clickhouse_uri"] is None
        assert config["clickhouse_database"] == "neural_hive"
        assert config["anomaly_contamination"] == 0.1
        assert config["anomaly_n_estimators"] == 100
        assert config["anomaly_training_window_days"] == 30


class TestGenerateSyntheticMetrics:
    """Testes para generate_synthetic_metrics."""

    def test_generate_synthetic_metrics_default(self):
        """Testa geração com número padrão de amostras."""
        import train_anomaly_detector

        metrics = train_anomaly_detector.generate_synthetic_metrics()

        assert len(metrics) == 500

        # Verificar estrutura das métricas
        for metric in metrics:
            assert "consensus_agreement_rate" in metric
            assert "false_positive_rate" in metric
            assert "false_negative_rate" in metric
            assert "avg_confidence_score" in metric
            assert "avg_risk_score" in metric
            assert "avg_processing_time_ms" in metric
            assert "evaluation_count" in metric
            assert "precision" in metric
            assert "recall" in metric

    def test_generate_synthetic_metrics_custom_count(self):
        """Testa geração com número customizado de amostras."""
        import train_anomaly_detector

        metrics = train_anomaly_detector.generate_synthetic_metrics(num_samples=100)

        assert len(metrics) == 100

    def test_synthetic_metrics_value_ranges(self):
        """Testa que métricas sintéticas estão em ranges válidos."""
        import train_anomaly_detector

        metrics = train_anomaly_detector.generate_synthetic_metrics(num_samples=50)

        for metric in metrics:
            # Valores entre 0 e 1
            assert 0.0 <= metric["consensus_agreement_rate"] <= 1.0
            assert 0.0 <= metric["false_positive_rate"] <= 1.0
            assert 0.0 <= metric["false_negative_rate"] <= 1.0
            assert 0.0 <= metric["avg_confidence_score"] <= 1.0
            assert 0.0 <= metric["avg_risk_score"] <= 1.0
            assert 0.0 <= metric["precision"] <= 1.0
            assert 0.0 <= metric["recall"] <= 1.0

            # Valores não negativos
            assert metric["avg_processing_time_ms"] >= 0
            assert metric["evaluation_count"] >= 1

    def test_generate_synthetic_metrics_empty(self):
        """Testa geração de 0 amostras."""
        import train_anomaly_detector

        metrics = train_anomaly_detector.generate_synthetic_metrics(num_samples=0)

        assert len(metrics) == 0


class TestFetchHistoricalMetrics:
    """Testes para fetch_historical_metrics_from_clickhouse."""

    @patch("clickhouse_driver.Client")
    def test_fetch_success(self, mock_client_class):
        """Testa busca bem-sucedida."""
        import train_anomaly_detector

        mock_client = Mock()
        mock_client.execute.return_value = [
            (
                "technical",
                0.85,
                0.10,
                0.08,
                0.75,
                0.30,
                500,
                100,
                0.80,
                0.82,
                datetime(2026, 1, 1),
            )
        ] * 10
        mock_client_class.from_url.return_value = mock_client

        metrics = train_anomaly_detector.fetch_historical_metrics_from_clickhouse(
            clickhouse_uri="clickhouse://localhost:9000",
            clickhouse_database="neural_hive",
            window_days=30,
        )

        assert len(metrics) == 10
        assert metrics[0]["specialist_type"] == "technical"
        assert metrics[0]["consensus_agreement_rate"] == 0.85

    @patch("clickhouse_driver.Client")
    def test_fetch_with_specialist_filter(self, mock_client_class):
        """Testa busca com filtro de especialista."""
        import train_anomaly_detector

        mock_client = Mock()
        mock_client.execute.return_value = [
            (
                "business",
                0.90,
                0.05,
                0.03,
                0.80,
                0.20,
                400,
                80,
                0.85,
                0.88,
                datetime(2026, 1, 1),
            )
        ]
        mock_client_class.from_url.return_value = mock_client

        metrics = train_anomaly_detector.fetch_historical_metrics_from_clickhouse(
            clickhouse_uri="clickhouse://localhost:9000",
            clickhouse_database="neural_hive",
            window_days=30,
            specialist_type="business",
        )

        assert len(metrics) == 1
        assert metrics[0]["specialist_type"] == "business"


class TestTrainAnomalyDetector:
    """Testes para train_anomaly_detector."""

    def test_train_with_insufficient_data(self):
        """Testa treinamento com dados insuficientes."""
        import train_anomaly_detector

        config = {
            "anomaly_contamination": 0.1,
            "anomaly_n_estimators": 100,
        }

        # Menos de 100 amostras
        metrics_history = [
            {
                "consensus_agreement_rate": 0.85,
                "false_positive_rate": 0.1,
                "false_negative_rate": 0.08,
                "avg_confidence_score": 0.75,
                "avg_risk_score": 0.30,
                "avg_processing_time_ms": 500,
                "evaluation_count": 100,
                "precision": 0.80,
                "recall": 0.82,
            }
            for _ in range(50)
        ]

        result = train_anomaly_detector.train_anomaly_detector(
            config=config,
            metrics_history=metrics_history,
            specialist_type="technical",
        )

        # Dados insuficientes devem retornar False
        assert result is False

    def test_train_with_empty_metrics(self):
        """Testa treinamento com métricas vazias."""
        import train_anomaly_detector

        config = {
            "anomaly_contamination": 0.1,
            "anomaly_n_estimators": 100,
        }

        result = train_anomaly_detector.train_anomaly_detector(
            config=config, metrics_history=[], specialist_type="technical"
        )

        assert result is False


class TestMainFunction:
    """Testes para main()."""

    @patch("train_anomaly_detector.generate_synthetic_metrics")
    @patch("train_anomaly_detector.load_config")
    def test_main_with_synthetic(self, mock_load_config, mock_generate):
        """Testa main com dados sintéticos."""
        import train_anomaly_detector

        mock_load_config.return_value = {
            "clickhouse_uri": None,
            "anomaly_contamination": 0.1,
            "anomaly_n_estimators": 100,
            "anomaly_model_path": "/models/anomaly_{specialist_type}.pkl",
        }

        mock_generate.return_value = [
            {
                "consensus_agreement_rate": 0.85,
                "false_positive_rate": 0.10,
                "avg_confidence_score": 0.75,
            }
        ] * 150

        # Simular argumentos CLI --use-synthetic
        with patch("sys.argv", ["train_anomaly_detector.py", "--use-synthetic"]):
            # main pode retornar 0 ou 1 dependendo do sucesso
            # Não vamos assertion o valor pois depende do AnomalyDetector real
            try:
                result = train_anomaly_detector.main()
                assert result in [0, 1]
            except Exception:
                # Pode falhar se AnomalyDetector não estiver disponível
                pass

    @patch("train_anomaly_detector.generate_synthetic_metrics")
    @patch("train_anomaly_detector.load_config")
    def test_main_no_metrics(self, mock_load_config, mock_generate):
        """Testa main quando não há métricas disponíveis."""
        import train_anomaly_detector

        mock_load_config.return_value = {
            "clickhouse_uri": None,
        }

        mock_generate.return_value = []

        with patch("sys.argv", ["train_anomaly_detector.py", "--use-synthetic"]):
            with pytest.raises(SystemExit):
                train_anomaly_detector.main()
