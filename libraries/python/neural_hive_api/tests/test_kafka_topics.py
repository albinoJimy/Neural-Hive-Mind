# libraries/python/neural_hive_api/tests/test_kafka_topics.py
import pytest

from neural_hive_api.kafka import KafkaTopicsConfig


class TestTopics(KafkaTopicsConfig):
    PREFIX = "test"

    def get_all_topics(self) -> dict[str, str]:
        return {"EXECUTION": self.get_topic("execution", "results")}


def test_topic_format_service_domain_event():
    """Tópico deve seguir formato service.domain.event"""
    topics = TestTopics()
    assert topics.get_all_topics()["EXECUTION"] == "test.execution.results"


def test_empty_prefix_allowed():
    """PREFIX vazio deve ser permitido."""

    class NoPrefixTopics(KafkaTopicsConfig):
        PREFIX = ""

        def get_all_topics(self) -> dict[str, str]:
            return {"TEST": self.get_topic("test", "event")}

    topics = NoPrefixTopics()
    # When PREFIX is empty, derive from class name: "noprefix" -> "noprefix"
    assert topics.get_all_topics()["TEST"] == "noprefix.test.event"


def test_get_all_topics_raises_not_implemented():
    """get_all_topics deve ser implementado por subclasses."""
    with pytest.raises(TypeError):
        KafkaTopicsConfig()
