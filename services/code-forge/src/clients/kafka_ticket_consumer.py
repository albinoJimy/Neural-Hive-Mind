import asyncio
import json
from typing import Optional, AsyncIterator
from aiokafka import AIOKafkaConsumer
from aiokafka.errors import KafkaError
import structlog

from ..models.execution_ticket import ExecutionTicket, TaskType

logger = structlog.get_logger()


class KafkaTicketConsumer:
    """Cliente Kafka para consumir Execution Tickets"""

    def __init__(
        self,
        bootstrap_servers: str,
        topic: str,
        group_id: str,
        auto_offset_reset: str = 'earliest',
        enable_auto_commit: bool = False
    ):
        self.bootstrap_servers = bootstrap_servers
        self.topic = topic
        self.group_id = group_id
        self.consumer: Optional[AIOKafkaConsumer] = None
        self.auto_offset_reset = auto_offset_reset
        self.enable_auto_commit = enable_auto_commit
        self._running = False

    async def start(self):
        """Inicia o consumer Kafka"""
        try:
            self.consumer = AIOKafkaConsumer(
                self.topic,
                bootstrap_servers=self.bootstrap_servers,
                group_id=self.group_id,
                auto_offset_reset=self.auto_offset_reset,
                enable_auto_commit=self.enable_auto_commit,
                value_deserializer=lambda m: json.loads(m.decode('utf-8'))
            )
            await self.consumer.start()
            self._running = True
            logger.info(
                'kafka_consumer_started',
                topic=self.topic,
                group_id=self.group_id
            )
        except KafkaError as e:
            logger.error('kafka_consumer_start_failed', error=str(e))
            raise

    async def consume(self) -> AsyncIterator[ExecutionTicket]:
        """
        Consome mensagens do Kafka e retorna Execution Tickets do tipo BUILD

        Yields:
            ExecutionTicket: Tickets de execução validados
        """
        if not self.consumer or not self._running:
            raise RuntimeError('Consumer não foi iniciado')

        retry_count = 0
        max_retries = 3
        backoff_base = 2

        try:
            async for message in self.consumer:
                try:
                    # Deserializar mensagem
                    data = message.value

                    # Validar com Pydantic
                    ticket = ExecutionTicket(**data)

                    # Filtrar apenas tickets BUILD
                    if ticket.task_type == TaskType.BUILD:
                        logger.info(
                            'build_ticket_received',
                            ticket_id=ticket.ticket_id,
                            plan_id=ticket.plan_id
                        )
                        yield ticket
                        retry_count = 0  # Reset retry count on success
                    else:
                        logger.debug(
                            'ticket_filtered_out',
                            ticket_id=ticket.ticket_id,
                            task_type=ticket.task_type
                        )

                except Exception as e:
                    logger.error(
                        'message_deserialization_error',
                        error=str(e),
                        partition=message.partition,
                        offset=message.offset
                    )

                    retry_count += 1
                    if retry_count >= max_retries:
                        # Enviar para dead letter queue (futuro)
                        logger.error(
                            'message_sent_to_dlq',
                            partition=message.partition,
                            offset=message.offset
                        )
                        retry_count = 0
                    else:
                        # Backoff exponencial
                        await asyncio.sleep(backoff_base ** retry_count)

        except Exception as e:
            logger.error('kafka_consume_error', error=str(e))
            raise

    async def commit(self):
        """Commit manual de offsets"""
        if self.consumer:
            await self.consumer.commit()
            logger.debug('kafka_offsets_committed')

    async def stop(self):
        """Para o consumer gracefully"""
        self._running = False
        if self.consumer:
            await self.consumer.stop()
            logger.info('kafka_consumer_stopped')
