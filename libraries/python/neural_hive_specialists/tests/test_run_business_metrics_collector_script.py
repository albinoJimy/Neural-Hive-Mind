"""Testes simplificados para o script run_business_metrics_collector.py."""

import os
import sys
import pytest
from unittest.mock import patch, Mock

# Adicionar diretório de scripts ao path
sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "..", "scripts"),
)

try:
    import run_business_metrics_collector

    SCRIPT_AVAILABLE = True
except ImportError:
    SCRIPT_AVAILABLE = False


@pytest.mark.skipif(not SCRIPT_AVAILABLE, reason="Script não disponível")
class TestLoadConfig:
    """Testes para load_config()."""

    @patch.dict(
        os.environ,
        {
            "MONGODB_URI": "mongodb://localhost:27017",
            "MONGODB_DATABASE": "test_db",
            "BUSINESS_METRICS_WINDOW_HOURS": "48",
            "ANOMALY_CONTAMINATION": "0.15",
        },
    )
    def test_load_config_from_env(self):
        """Testa carregamento de config das variáveis de ambiente."""
        config = run_business_metrics_collector.load_config()

        assert config["mongodb_uri"] == "mongodb://localhost:27017"
        assert config["mongodb_database"] == "test_db"
        assert config["business_metrics_window_hours"] == 48
        assert config["anomaly_contamination"] == 0.15

    @patch.dict(os.environ, {}, clear=True)
    def test_load_config_missing_mongodb_uri(self):
        """Testa erro quando MONGODB_URI não está definido."""
        with pytest.raises(SystemExit):
            run_business_metrics_collector.load_config()

    @patch.dict(
        os.environ,
        {
            "MONGODB_URI": "mongodb://localhost:27017",
            "ENABLE_BUSINESS_METRICS": "false",
        },
    )
    def test_load_config_business_metrics_disabled(self):
        """Testa configuração com business metrics desabilitado."""
        config = run_business_metrics_collector.load_config()
        assert config["enable_business_metrics"] is False


@pytest.mark.skipif(not SCRIPT_AVAILABLE, reason="Script não disponível")
class TestBuildAnomalyFeatures:
    """Testes para build_anomaly_features()."""

    def test_build_anomaly_features_complete(self):
        """Testa construção de features com dados completos."""
        metrics_summary = {
            "business_metrics": {
                "consensus_agreement_rate": 0.85,
                "false_positive_rate": 0.10,
                "false_negative_rate": 0.08,
                "precision": 0.80,
                "recall": 0.82,
            },
            "accuracy_score": 0.75,
            "avg_processing_time_ms": 500,
            "total_evaluations": 100,
        }

        features = run_business_metrics_collector.build_anomaly_features(metrics_summary)

        assert features["consensus_agreement_rate"] == 0.85
        assert features["false_positive_rate"] == 0.10
        assert features["avg_confidence_score"] == 0.75
        assert features["evaluation_count"] == 100

    def test_build_anomaly_features_empty(self):
        """Testa construção de features com dados vazios."""
        metrics_summary = {"business_metrics": {}}

        features = run_business_metrics_collector.build_anomaly_features(metrics_summary)

        assert features["consensus_agreement_rate"] == 0.0
        assert features["avg_confidence_score"] == 0.0
        assert features["evaluation_count"] == 0


@pytest.mark.skipif(not SCRIPT_AVAILABLE, reason="Script não disponível")
class TestPushMetricsToGateway:
    """Testes para push_metrics_to_gateway()."""

    def test_push_metrics_no_url(self):
        """Testa que nada acontece quando não há URL."""
        config = {"pushgateway_url": None}
        metrics_registry = {"technical": Mock()}

        # Não deve lançar erro
        run_business_metrics_collector.push_metrics_to_gateway(config, metrics_registry)

    def test_push_metrics_no_url(self):
        """Testa que nada acontece quando não há URL."""
        config = {"pushgateway_url": None}
        metrics_registry = {"technical": Mock()}

        # Não deve lançar erro
        run_business_metrics_collector.push_metrics_to_gateway(config, metrics_registry)
