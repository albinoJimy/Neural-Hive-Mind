"""Testes de integração para Kafka topics com neural_hive_api."""

import pytest
import os

os.environ["KAFKA_BOOTSTRAP_SERVERS"] = "localhost:9092"
os.environ["ENVIRONMENT"] = "development"

from src.config.settings import get_settings, OptimizerTopics
from neural_hive_api.kafka import KafkaTopicsConfig


class TestOptimizerTopicsIntegration:
    """Testa integração do OptimizerTopics com optimizer-agents."""

    def test_optimizer_topics_exists(self):
        """Verifica que OptimizerTopics existe em settings."""
        settings = get_settings()
        assert hasattr(settings, "topics")
        assert isinstance(settings.topics, OptimizerTopics)

    def test_optimizer_topics_is_kafka_topics_config(self):
        """Verifica que OptimizerTopics herda de KafkaTopicsConfig."""
        assert issubclass(OptimizerTopics, KafkaTopicsConfig)

    def test_optimizer_topics_prefix(self):
        """Verifica que PREFIX está definido corretamente."""
        assert OptimizerTopics.PREFIX == "optimizer"

    def test_optimizer_topics_all_topics_defined(self):
        """Verifica que todos os tópicos estão definidos."""
        settings = get_settings()
        topics = settings.topics

        assert hasattr(topics, "TELEMETRY")
        assert hasattr(topics, "RECOMMENDATIONS")
        assert hasattr(topics, "EXPERIMENTS")
        assert hasattr(topics, "FEEDBACK")

    def test_optimizer_topics_values_format(self):
        """Verifica que os valores dos tópicos estão no formato correto."""
        settings = get_settings()
        topics = settings.topics

        # Formato esperado: {PREFIX}.{domain}.{event}
        assert topics.TELEMETRY.startswith("optimizer.")
        assert topics.RECOMMENDATIONS.startswith("optimizer.")
        assert topics.EXPERIMENTS.startswith("optimizer.")
        assert topics.FEEDBACK.startswith("optimizer.")

        # Verifica formato completo: optimizer.<domain>.<event>
        assert "." in topics.TELEMETRY
        assert topics.TELEMETRY == "optimizer.telemetry.aggregated"

    def test_optimizer_topics_get_all_topics(self):
        """Verifica que get_all_topics retorna o mapping correto."""
        settings = get_settings()
        topics = settings.topics
        all_topics = topics.get_all_topics()

        assert isinstance(all_topics, dict)
        assert "telemetry" in all_topics
        assert "recommendations" in all_topics
        assert "experiments" in all_topics
        assert "feedback" in all_topics

        assert all_topics["telemetry"] == topics.TELEMETRY
        assert all_topics["recommendations"] == topics.RECOMMENDATIONS
        assert all_topics["experiments"] == topics.EXPERIMENTS
        assert all_topics["feedback"] == topics.FEEDBACK
