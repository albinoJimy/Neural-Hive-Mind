"""Configuração de tópicos Kafka para Architect Agent."""

from neural_hive_api.kafka import KafkaTopicsConfig


class ArchitectTopics(KafkaTopicsConfig):
    """Tópicos Kafka usados pelo Architect Agent."""

    PREFIX = "architect"

    def get_all_topics(self) -> dict[str, str]:
        """Retorna mapping nome_tópico → tópico."""
        return {
            "cognitive_plans": self.get_topic("cognitive", "plans.created"),
            "architecture_created": self.get_topic("architecture", "created"),
            "architecture_updated": self.get_topic("architecture", "updated"),
            "validation_completed": self.get_topic("validation", "completed"),
            "evolution_detected": self.get_topic("evolution", "detected"),
        }
