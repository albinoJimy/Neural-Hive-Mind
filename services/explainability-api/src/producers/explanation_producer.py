"""
ExplanationProducer - Producer Kafka para explicações.

Responsável por:
- Publicar explicações no tópico consensus.explanations
- Serializar explicações como JSON
- Incluir headers de tracing/distributed context

GAPS-04 Task 6
"""

import asyncio
import json
from typing import Any, Dict, Optional

import structlog
from aiokafka import AIOKafkaProducer
from aiokafka.errors import KafkaError

logger = structlog.get_logger(__name__)


class ExplanationProducer:
    """
    Producer Kafka para publicar explicações de decisão.

    Publica explicações geradas no tópico consensus.explanations
    para consumo por outros serviços (UI, analytics, etc).
    """

    def __init__(self, bootstrap_servers: str, topic: str = "consensus.explanations"):
        """
        Inicializa o ExplanationProducer.

        Args:
            bootstrap_servers: Servidores Kafka
            topic: Tópico para publicar explicações (padrão: consensus.explanations)
        """
        self.bootstrap_servers = bootstrap_servers
        self.topic = topic
        self.producer: Optional[AIOKafkaProducer] = None

    async def connect(self) -> None:
        """
        Inicializa producer Kafka.

        Raises:
            Exception se falhar ao conectar
        """
        try:
            self.producer = AIOKafkaProducer(
                bootstrap_servers=self.bootstrap_servers,
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                # Acknowledgments: esperar replicação
                acks="all",
                # Retries
                retries=3,
                # Compressão
                compression_type="snappy",
            )

            await self.producer.start()

            logger.info(
                "explanation_producer.connected",
                bootstrap_servers=self.bootstrap_servers,
                topic=self.topic,
            )

        except Exception as e:
            logger.error("explanation_producer.connection_failed", error=str(e))
            raise

    async def disconnect(self) -> None:
        """
        Para producer Kafka.
        """
        logger.info("explanation_producer.disconnecting")

        if self.producer:
            await self.producer.stop()

        logger.info("explanation_producer.disconnected")

    async def publish_explanation(
        self, explanation: Dict[str, Any], key: Optional[str] = None
    ) -> None:
        """
        Publica explicação no tópico do Kafka.

        Args:
            explanation: Dicionário com dados da explicação
            key: Chave de partição (opcional, usa decision_id por padrão)

        Raises:
            Exception se falhar ao publicar
        """
        if not self.producer:
            raise RuntimeError("Producer not connected. Call connect() first.")

        decision_id = explanation.get("decision_id", "unknown")

        # Usar decision_id como chave para partição consistente
        partition_key = key or decision_id

        logger.info(
            "explanation_producer.publishing",
            decision_id=decision_id,
            explainability_token=explanation.get("explainability_token"),
        )

        try:
            # Extrair headers de tracing se presentes
            headers = self._extract_headers(explanation)

            # Publicar com confirmação (send_and_wait)
            await self.producer.send_and_wait(
                self.topic,
                value=explanation,
                key=partition_key.encode("utf-8") if partition_key else None,
                headers=headers,
            )

            logger.info("explanation_producer.published", decision_id=decision_id, topic=self.topic)

        except KafkaError as e:
            logger.error("explanation_producer.kafka_error", decision_id=decision_id, error=str(e))
            raise

        except Exception as e:
            logger.error(
                "explanation_producer.publish_failed", decision_id=decision_id, error=str(e)
            )
            raise

    def _extract_headers(self, explanation: Dict[str, Any]) -> list:
        """
        Extrai headers de tracing da explicação.

        Args:
            explanation: Dicionário com dados da explicação

        Returns:
            Lista de tuplas (key, value) para headers Kafka
        """
        headers = []

        # Headers de tracing padrão (OpenTelemetry)
        trace_parent = explanation.get("traceparent")
        if trace_parent:
            headers.append(("traceparent", trace_parent.encode("utf-8")))

        trace_id = explanation.get("trace_id")
        if trace_id:
            headers.append(("trace_id", str(trace_id).encode("utf-8")))

        span_id = explanation.get("span_id")
        if span_id:
            headers.append(("span_id", str(span_id).encode("utf-8")))

        # Headers adicionais
        correlation_id = explanation.get("correlation_id")
        if correlation_id:
            headers.append(("correlation_id", str(correlation_id).encode("utf-8")))

        return headers

    async def publish_batch(self, explanations: list, timeout_ms: int = 5000) -> Dict[str, Any]:
        """
        Publica lote de explicações de forma eficiente.

        Args:
            explanations: Lista de dicionários de explicação
            timeout_ms: Timeout para publicação (ms)

        Returns:
            Dicionário com estatísticas da publicação
        """
        if not self.producer:
            raise RuntimeError("Producer not connected. Call connect() first.")

        logger.info("explanation_producer.publishing_batch", count=len(explanations))

        stats = {"total": len(explanations), "published": 0, "failed": 0, "errors": []}

        try:
            # Criar tarefas de publicação em paralelo
            tasks = []
            for exp in explanations:
                task = asyncio.create_task(self._publish_with_timeout(exp, timeout_ms))
                tasks.append(task)

            # Aguardar todas as tarefas
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Compilar estatísticas
            for result in results:
                if isinstance(result, Exception):
                    stats["failed"] += 1
                    stats["errors"].append(str(result))
                else:
                    stats["published"] += 1

            logger.info("explanation_producer.batch_published", **stats)

            return stats

        except Exception as e:
            logger.error("explanation_producer.batch_publish_failed", error=str(e))
            stats["failed"] = len(explanations) - stats["published"]
            stats["errors"].append(str(e))
            return stats

    async def _publish_with_timeout(self, explanation: Dict[str, Any], timeout_ms: int) -> None:
        """
        Publica explicação com timeout.

        Args:
            explanation: Dicionário com dados da explicação
            timeout_ms: Timeout em milissegundos

        Raises:
            asyncio.TimeoutError se timeout
        """
        try:
            await asyncio.wait_for(
                self.publish_explanation(explanation), timeout=timeout_ms / 1000.0
            )
        except asyncio.TimeoutError:
            decision_id = explanation.get("decision_id", "unknown")
            logger.warning(
                "explanation_producer.publish_timeout",
                decision_id=decision_id,
                timeout_ms=timeout_ms,
            )
            raise
