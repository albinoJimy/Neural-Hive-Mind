"""Testes de integração para CodeForgeTopics com neural_hive_api."""

from neural_hive_api.kafka import KafkaTopicsConfig
from src.config.settings import CodeForgeTopics


class TestCodeForgeTopicsIntegration:
    """Testa integração do CodeForgeTopics com code-forge."""

    def test_topics_inherits_from_kafka_topics_config(self):
        """Verifica que CodeForgeTopics herda de KafkaTopicsConfig."""
        topics = CodeForgeTopics()
        assert isinstance(topics, KafkaTopicsConfig)

    def test_topics_has_correct_prefix(self):
        """Verifica que CodeForgeTopics tem PREFIX='code-forge'."""
        assert CodeForgeTopics.PREFIX == "code-forge"

    def test_topics_get_all_topics(self):
        """Verifica que get_all_topics retorna mapping correto."""
        topics = CodeForgeTopics()
        all_topics = topics.get_all_topics()
        assert isinstance(all_topics, dict)
        assert "tickets" in all_topics
        assert "results" in all_topics

    def test_topics_tickets_format(self):
        """Verifica formato do tópico de tickets."""
        topics = CodeForgeTopics()
        expected = "code-forge.execution.tickets"
        assert expected == topics.TICKETS

    def test_topics_results_format(self):
        """Verifica formato do tópico de resultados."""
        topics = CodeForgeTopics()
        expected = "code-forge.code-forge.results"
        assert expected == topics.RESULTS

    def test_topics_get_topic_method(self):
        """Verifica método get_topic gera tópicos corretamente."""
        topics = CodeForgeTopics()
        custom = topics.get_topic("custom", "event")
        expected = "code-forge.custom.event"
        assert custom == expected
