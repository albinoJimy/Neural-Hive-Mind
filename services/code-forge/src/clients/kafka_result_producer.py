import json
from typing import Optional
from aiokafka import AIOKafkaProducer
from aiokafka.errors import KafkaError
import structlog

from ..models.artifact import PipelineResult

logger = structlog.get_logger()


class KafkaResultProducer:
    """Cliente Kafka para publicar resultados de pipelines"""

    def __init__(self, bootstrap_servers: str, topic: str):
        self.bootstrap_servers = bootstrap_servers
        self.topic = topic
        self.producer: Optional[AIOKafkaProducer] = None

    async def start(self):
        """Inicia o producer Kafka"""
        try:
            self.producer = AIOKafkaProducer(
                bootstrap_servers=self.bootstrap_servers,
                value_serializer=lambda v: json.dumps(v).encode('utf-8'),
                acks='all',  # Garantir durabilidade
                enable_idempotence=True  # Garantir idempotência
            )
            await self.producer.start()
            logger.info(
                'kafka_producer_started',
                topic=self.topic
            )
        except KafkaError as e:
            logger.error('kafka_producer_start_failed', error=str(e))
            raise

    async def publish_result(self, pipeline_result: PipelineResult):
        """
        Publica resultado de pipeline no Kafka

        Args:
            pipeline_result: Resultado do pipeline a ser publicado
        """
        if not self.producer:
            raise RuntimeError('Producer não foi iniciado')

        try:
            # Serializar PipelineResult para dict
            data = pipeline_result.model_dump(mode='json')

            # Publicar com pipeline_id como chave para garantir ordem por pipeline
            key = pipeline_result.pipeline_id.encode('utf-8')

            # Adicionar headers com metadados de correlação
            headers = [
                ('trace_id', (pipeline_result.trace_id or '').encode('utf-8')),
                ('span_id', (pipeline_result.span_id or '').encode('utf-8')),
                ('correlation_id', (pipeline_result.correlation_id or '').encode('utf-8'))
            ]

            # Enviar mensagem e aguardar confirmação
            record_metadata = await self.producer.send_and_wait(
                self.topic,
                value=data,
                key=key,
                headers=headers
            )

            logger.info(
                'pipeline_result_published',
                pipeline_id=pipeline_result.pipeline_id,
                topic=record_metadata.topic,
                partition=record_metadata.partition,
                offset=record_metadata.offset
            )

        except Exception as e:
            logger.error(
                'pipeline_result_publish_failed',
                pipeline_id=pipeline_result.pipeline_id,
                error=str(e)
            )
            raise

    async def stop(self):
        """Para o producer gracefully"""
        if self.producer:
            await self.producer.stop()
            logger.info('kafka_producer_stopped')
