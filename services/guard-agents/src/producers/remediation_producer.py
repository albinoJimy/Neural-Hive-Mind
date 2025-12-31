"""Kafka producer para eventos de remediação"""
from typing import Dict, Any, Optional
import json
import structlog
from aiokafka import AIOKafkaProducer
from aiokafka.errors import KafkaError

from neural_hive_observability import instrument_kafka_producer

logger = structlog.get_logger()


class RemediationProducer:
    """
    Producer Kafka para publicar eventos de remediação no tópico remediation-actions.
    Integra com o self-healing engine para autocura end-to-end.
    """

    def __init__(self, bootstrap_servers: str, topic: str = "remediation-actions"):
        self.bootstrap_servers = bootstrap_servers
        self.topic = topic
        self.producer: Optional[AIOKafkaProducer] = None
        self._connected = False

    async def connect(self):
        """Conecta ao Kafka broker"""
        try:
            self.producer = AIOKafkaProducer(
                bootstrap_servers=self.bootstrap_servers,
                value_serializer=lambda v: json.dumps(v).encode('utf-8'),
                compression_type='gzip',
                acks='all',
                enable_idempotence=True
            )
            self.producer = instrument_kafka_producer(self.producer)
            await self.producer.start()
            self._connected = True
            logger.info(
                "remediation_producer.connected",
                bootstrap_servers=self.bootstrap_servers,
                topic=self.topic
            )
        except Exception as e:
            logger.error(
                "remediation_producer.connect_failed",
                error=str(e),
                bootstrap_servers=self.bootstrap_servers
            )
            raise

    async def close(self):
        """Fecha conexão com Kafka"""
        if self.producer:
            try:
                await self.producer.stop()
                self._connected = False
                logger.info("remediation_producer.closed")
            except Exception as e:
                logger.error("remediation_producer.close_failed", error=str(e))

    async def publish_remediation_action(
        self,
        remediation_id: str,
        incident_id: str,
        action_type: str,
        status: str,
        details: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Publica evento de ação de remediação.

        Args:
            remediation_id: ID único da remediação
            incident_id: ID do incidente relacionado
            action_type: Tipo de ação (restart_pod, scale_deployment, etc.)
            status: Status da ação (pending, in_progress, completed, failed)
            details: Detalhes específicos da ação
            metadata: Metadados adicionais

        Returns:
            bool: True se publicado com sucesso
        """
        if not self._connected or not self.producer:
            logger.error("remediation_producer.not_connected")
            return False

        try:
            event = {
                "remediation_id": remediation_id,
                "incident_id": incident_id,
                "action_type": action_type,
                "status": status,
                "details": details or {},
                "metadata": metadata or {},
                "timestamp": self._get_timestamp()
            }

            # Usa incident_id como key para garantir ordenação por incidente
            key = incident_id.encode('utf-8')

            result = await self.producer.send_and_wait(
                self.topic,
                value=event,
                key=key
            )

            logger.info(
                "remediation_producer.published",
                remediation_id=remediation_id,
                incident_id=incident_id,
                action_type=action_type,
                status=status,
                partition=result.partition,
                offset=result.offset
            )

            return True

        except KafkaError as e:
            logger.error(
                "remediation_producer.kafka_error",
                remediation_id=remediation_id,
                error=str(e)
            )
            return False
        except Exception as e:
            logger.error(
                "remediation_producer.publish_failed",
                remediation_id=remediation_id,
                error=str(e)
            )
            return False

    async def publish_remediation_result(
        self,
        remediation_id: str,
        result: Dict[str, Any]
    ) -> bool:
        """
        Publica resultado completo de remediação.

        Args:
            remediation_id: ID da remediação
            result: Resultado completo da remediação

        Returns:
            bool: True se publicado com sucesso
        """
        if not self._connected or not self.producer:
            logger.error("remediation_producer.not_connected")
            return False

        try:
            event = {
                "remediation_id": remediation_id,
                "result": result,
                "timestamp": self._get_timestamp()
            }

            incident_id = result.get("incident_id", remediation_id)
            key = incident_id.encode('utf-8')

            result_obj = await self.producer.send_and_wait(
                self.topic,
                value=event,
                key=key
            )

            logger.info(
                "remediation_producer.result_published",
                remediation_id=remediation_id,
                status=result.get("status"),
                partition=result_obj.partition,
                offset=result_obj.offset
            )

            return True

        except Exception as e:
            logger.error(
                "remediation_producer.publish_result_failed",
                remediation_id=remediation_id,
                error=str(e)
            )
            return False

    def is_connected(self) -> bool:
        """Verifica se producer está conectado"""
        return self._connected

    @staticmethod
    def _get_timestamp() -> str:
        """Retorna timestamp ISO 8601"""
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat()
