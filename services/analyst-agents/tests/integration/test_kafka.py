"""Testes de integração para Kafka topics com neural_hive_api."""

import pytest

from src.config.settings import AnalystTopics, get_settings


@pytest.mark.asyncio
class TestKafkaTopicsIntegration:
    """Testa integração do KafkaTopicsConfig com analyst-agents."""

    def test_analyst_topics_class_exists(self):
        """Verifica que AnalystTopics pode ser instanciada."""
        topics = AnalystTopics()
        assert topics is not None
        assert topics.PREFIX == "analyst"

    def test_analyst_topics_has_all_required_topics(self):
        """Verifica que todos os tópicos requeridos estão definidos."""
        topics = AnalystTopics()
        assert hasattr(topics, "TELEMETRY")
        assert hasattr(topics, "CONSENSUS")
        assert hasattr(topics, "EXECUTION")
        assert hasattr(topics, "PHEROMONES")
        assert hasattr(topics, "INSIGHTS")

    def test_analyst_topics_format(self):
        """Verifica formato dos nomes dos tópicos."""
        topics = AnalystTopics()
        assert topics.TELEMETRY == "analyst.telemetry.aggregated"
        assert topics.CONSENSUS == "analyst.plans.consensus"
        assert topics.EXECUTION == "analyst.execution.results"
        assert topics.PHEROMONES == "analyst.pheromones.signals"
        assert topics.INSIGHTS == "analyst.insights.analyzed"

    def test_analyst_topics_get_all_topics(self):
        """Verifica método get_all_topics retorna mapping correto."""
        topics = AnalystTopics()
        all_topics = topics.get_all_topics()
        assert isinstance(all_topics, dict)
        assert "telemetry" in all_topics
        assert "consensus" in all_topics
        assert "execution" in all_topics
        assert "pheromones" in all_topics
        assert "insights" in all_topics
        assert all_topics["telemetry"] == topics.TELEMETRY
        assert all_topics["consensus"] == topics.CONSENSUS
        assert all_topics["execution"] == topics.EXECUTION
        assert all_topics["pheromones"] == topics.PHEROMONES
        assert all_topics["insights"] == topics.INSIGHTS

    def test_settings_has_topics_property(self):
        """Verifica que Settings tem propriedade topics."""
        settings = get_settings()
        assert hasattr(settings, "topics")
        assert isinstance(settings.topics, AnalystTopics)

    def test_settings_topics_are_accessible(self):
        """Verifica que topics em settings são acessíveis."""
        settings = get_settings()
        assert settings.topics.TELEMETRY == "analyst.telemetry.aggregated"
        assert settings.topics.CONSENSUS == "analyst.plans.consensus"
        assert settings.topics.EXECUTION == "analyst.execution.results"
        assert settings.topics.PHEROMONES == "analyst.pheromones.signals"
        assert settings.topics.INSIGHTS == "analyst.insights.analyzed"
