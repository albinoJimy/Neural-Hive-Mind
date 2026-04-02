# libraries/python/neural_hive_api/neural_hive_api/kafka/topics.py
from abc import ABC, abstractmethod


class KafkaTopicsConfig(ABC):
    """Base class para configuração de tópicos Kafka."""

    PREFIX: str = ""

    @classmethod
    def get_topic(cls, domain: str, event: str) -> str:
        """Retorna tópico no formato {PREFIX}.{domain}.{event}."""
        prefix = (
            cls.PREFIX if cls.PREFIX else cls.__name__.lower().replace("topics", "")
        )
        return f"{prefix}.{domain}.{event}"

    @abstractmethod
    def get_all_topics(self) -> dict[str, str]:
        """Retorna mapping nome_tópico → tópico."""
