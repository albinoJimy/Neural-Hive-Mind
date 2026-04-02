"""Configuração de tópicos Kafka para Worker Agents."""

from neural_hive_api.kafka import KafkaTopicsConfig


class WorkerTopics(KafkaTopicsConfig):
    """Tópicos Kafka usados pelo Worker Agents."""

    PREFIX = "worker"

    def get_all_topics(self) -> dict[str, str]:
        """Retorna mapping nome_tópico → tópico."""
        return {
            "tickets": self.get_topic("execution", "tickets"),
            "results": self.get_topic("execution", "results"),
            "dlq": self.get_topic("execution", "tickets.dlq"),
        }
