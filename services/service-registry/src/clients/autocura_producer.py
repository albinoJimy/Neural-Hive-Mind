"""
Producer Kafka para publicação de eventos de autocura.
"""

import json
from datetime import timezone
from typing import Any

import structlog
from confluent_kafka import KafkaError, Producer

logger = structlog.get_logger()


class AutocuraEventProducer:
    """
    Producer Kafka para publicar eventos de autocura.

    Publica eventos quando agentes são marcados como UNHEALTHY ou DEGRADED
    para que o Self-Healing Engine possa tomar ações corretivas.
    """

    def __init__(self, bootstrap_servers: str, topic: str = "autocura.events"):
        """
        Inicializa o producer.

        Args:
            bootstrap_servers: Endereço dos brokers Kafka
            topic: Tópico para publicação de eventos
        """
        self.bootstrap_servers = bootstrap_servers
        self.topic = topic
        self._producer = None

        config = {
            "bootstrap.servers": bootstrap_servers,
            "client.id": "service-registry-autocura",
            "acks": "1",
            "compression.type": "snappy",
            "queue.buffering.max.messages": "10000",
            "queue.buffering.max.kbytes": "10240",
        }

        try:
            self._producer = Producer(config)
            logger.info(
                "autocura_producer_initialized",
                bootstrap_servers=bootstrap_servers,
                topic=topic,
            )
        except Exception as e:
            logger.error("autocura_producer_init_failed", error=str(e))
            self._producer = None

    def publish_agent_degraded(
        self,
        agent_id: str,
        agent_type: str,
        status: str,
        last_seen: int,
    ) -> bool:
        """
        Publica evento de agente degradado.

        Args:
            agent_id: ID do agente
            agent_type: Tipo do agente
            status: Status atual
            last_seen: Timestamp da última atividade

        Returns:
            True se publicado com sucesso
        """
        if not self._producer:
            logger.warning("autocura_producer_not_available")
            return False

        event = {
            "event_type": "agent_degraded",
            "agent_id": agent_id,
            "agent_type": agent_type,
            "status": status,
            "last_seen": last_seen,
            "timestamp": last_seen,
        }

        return self._publish(event)

    def publish_agent_unhealthy(
        self,
        agent_id: str,
        agent_type: str,
        status: str,
        last_seen: int,
    ) -> bool:
        """
        Publica evento de agente não saudável.

        Args:
            agent_id: ID do agente
            agent_type: Tipo do agente
            status: Status atual
            last_seen: Timestamp da última atividade

        Returns:
            True se publicado com sucesso
        """
        if not self._producer:
            logger.warning("autocura_producer_not_available")
            return False

        event = {
            "event_type": "agent_unhealthy",
            "agent_id": agent_id,
            "agent_type": agent_type,
            "status": status,
            "last_seen": last_seen,
            "timestamp": last_seen,
            "severity": "high",
        }

        return self._publish(event)

    def publish_agent_recovered(
        self,
        agent_id: str,
        agent_type: str,
        status: str,
    ) -> bool:
        """
        Publica evento de recuperação de agente.

        Args:
            agent_id: ID do agente
            agent_type: Tipo do agente
            status: Status atual

        Returns:
            True se publicado com sucesso
        """
        if not self._producer:
            logger.warning("autocura_producer_not_available")
            return False

        from datetime import datetime

        event = {
            "event_type": "agent_recovered",
            "agent_id": agent_id,
            "agent_type": agent_type,
            "status": status,
            "timestamp": int(datetime.now(timezone.utc).timestamp()),
            "severity": "info",
        }

        return self._publish(event)

    def _publish(self, event: dict[str, Any]) -> bool:
        """
        Publica evento no Kafka.

        Args:
            event: Dados do evento

        Returns:
            True se publicado com sucesso
        """
        try:
            value = json.dumps(event).encode("utf-8")

            def delivery_report(err, msg):
                if err is not None:
                    logger.error(
                        "autocura_event_delivery_failed",
                        event_type=event.get("event_type"),
                        error=str(err),
                    )
                else:
                    logger.info(
                        "autocura_event_delivered",
                        event_type=event.get("event_type"),
                        agent_id=event.get("agent_id"),
                    )

            self._producer.produce(
                topic=self.topic,
                value=value,
                key=event.get("agent_id", "").encode("utf-8"),
                on_delivery=delivery_report,
            )

            # Esperar delivery (timeout curto) e verificar se todas as mensagens foram enviadas
            pending = self._producer.flush(timeout=5)
            return pending == 0

        except KafkaError as e:
            logger.error("autocura_event_kafka_error", error=str(e))
            return False
        except Exception as e:
            logger.error("autocura_event_publish_failed", error=str(e))
            return False

    def close(self):
        """Fecha o producer Kafka."""
        if self._producer:
            self._producer.flush(timeout=10)
            # Nota: Producer do confluent_kafka não tem método close()
            # O recurso é liberado automaticamente pelo garbage collector
            logger.info("autocura_producer_closed")

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
