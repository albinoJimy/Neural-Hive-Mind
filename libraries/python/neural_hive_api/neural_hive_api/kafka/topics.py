# libraries/python/neural_hive_api/neural_hive_api/kafka/topics.py
from abc import ABC, abstractmethod


class KafkaTopicsConfig(ABC):
    """Base class para configuração de tópicos Kafka."""

    PREFIX: str = ""

    def get_topic(self, domain: str, event: str) -> str:
        """Retorna tópico no formato {PREFIX}.{domain}.{event}."""
        # Get PREFIX from the instance's class
        prefix = getattr(self.__class__, "PREFIX", "")
        if not prefix:
            # Derive from class name if PREFIX not set
            name = self.__class__.__name__.lower().replace("topics", "").replace("config", "")
            prefix = name if name else "kafka"
        return f"{prefix}.{domain}.{event}"

    @abstractmethod
    def get_all_topics(self) -> dict[str, str]:
        """Retorna mapping nome_tópico → tópico."""
        pass
