import json
import structlog
from aiokafka import AIOKafkaProducer
from typing import Dict, Optional, Any
from datetime import datetime

logger = structlog.get_logger()


class KafkaResultProducer:
    '''Producer Kafka para tópico execution.results'''

    def __init__(self, config):
        self.config = config
        self.logger = logger.bind(service='kafka_result_producer')
        self.producer: Optional[AIOKafkaProducer] = None

    async def initialize(self):
        '''Inicializar producer Kafka'''
        try:
            self.producer = AIOKafkaProducer(
                bootstrap_servers=self.config.kafka_bootstrap_servers,
                value_serializer=lambda v: json.dumps(v).encode('utf-8'),
                acks='all',
                retries=3,
                max_in_flight_requests_per_connection=1
            )

            await self.producer.start()

            self.logger.info(
                'kafka_producer_initialized',
                topic=self.config.kafka_results_topic
            )

            # TODO: Incrementar métrica worker_agent_kafka_producer_initialized_total

        except Exception as e:
            self.logger.error('kafka_producer_init_failed', error=str(e))
            raise

    async def publish_result(
        self,
        ticket_id: str,
        status: str,
        result: Dict[str, Any],
        error_message: Optional[str] = None,
        actual_duration_ms: Optional[int] = None
    ) -> Dict[str, Any]:
        '''Publicar resultado no Kafka'''
        try:
            payload = {
                'ticket_id': ticket_id,
                'status': status,
                'result': result,
                'error_message': error_message,
                'actual_duration_ms': actual_duration_ms,
                'agent_id': self.config.agent_id,
                'timestamp': int(datetime.now().timestamp() * 1000),
                'schema_version': 1
            }

            # Publicar com ticket_id como key para particionamento consistente
            metadata = await self.producer.send_and_wait(
                self.config.kafka_results_topic,
                key=ticket_id.encode('utf-8'),
                value=payload
            )

            self.logger.info(
                'result_published',
                ticket_id=ticket_id,
                status=status,
                topic=metadata.topic,
                partition=metadata.partition,
                offset=metadata.offset
            )

            # TODO: Incrementar métrica worker_agent_results_published_total{status=...}

            return {
                'topic': metadata.topic,
                'partition': metadata.partition,
                'offset': metadata.offset
            }

        except Exception as e:
            self.logger.error(
                'publish_result_failed',
                ticket_id=ticket_id,
                status=status,
                error=str(e)
            )
            # TODO: Incrementar métrica worker_agent_kafka_producer_errors_total
            raise

    async def stop(self):
        '''Parar producer'''
        if self.producer:
            await self.producer.stop()
            self.logger.info('kafka_producer_stopped')
