import json
import structlog
from aiokafka import AIOKafkaConsumer
from typing import Optional

logger = structlog.get_logger()


class KafkaTicketConsumer:
    '''Consumer Kafka para tópico execution.tickets'''

    def __init__(self, config, execution_engine):
        self.config = config
        self.execution_engine = execution_engine
        self.logger = logger.bind(service='kafka_ticket_consumer')
        self.consumer: Optional[AIOKafkaConsumer] = None
        self.running = False

    async def initialize(self):
        '''Inicializar consumer Kafka'''
        try:
            self.consumer = AIOKafkaConsumer(
                self.config.kafka_tickets_topic,
                bootstrap_servers=self.config.kafka_bootstrap_servers,
                group_id=self.config.kafka_consumer_group_id,
                auto_offset_reset=self.config.kafka_auto_offset_reset,
                enable_auto_commit=self.config.kafka_enable_auto_commit,
                value_deserializer=lambda v: json.loads(v.decode('utf-8'))
            )

            await self.consumer.start()

            self.logger.info(
                'kafka_consumer_initialized',
                topic=self.config.kafka_tickets_topic,
                group_id=self.config.kafka_consumer_group_id
            )

            # TODO: Incrementar métrica worker_agent_kafka_consumer_initialized_total

        except Exception as e:
            self.logger.error('kafka_consumer_init_failed', error=str(e))
            raise

    async def start(self):
        '''Iniciar loop de consumo'''
        self.running = True

        try:
            async for message in self.consumer:
                if not self.running:
                    break

                try:
                    ticket = message.value

                    # Validar campos obrigatórios
                    required_fields = ['ticket_id', 'task_id', 'task_type', 'status', 'dependencies']
                    missing_fields = [f for f in required_fields if f not in ticket]
                    if missing_fields:
                        self.logger.warning(
                            'invalid_ticket_missing_fields',
                            ticket_id=ticket.get('ticket_id'),
                            missing_fields=missing_fields
                        )
                        await self.consumer.commit()
                        continue

                    # Verificar se task_type é suportado
                    task_type = ticket.get('task_type')
                    if task_type not in self.config.supported_task_types:
                        self.logger.warning(
                            'unsupported_task_type',
                            ticket_id=ticket.get('ticket_id'),
                            task_type=task_type
                        )
                        await self.consumer.commit()
                        continue

                    # Verificar status
                    status = ticket.get('status')
                    if status != 'PENDING':
                        self.logger.debug(
                            'skipping_non_pending_ticket',
                            ticket_id=ticket.get('ticket_id'),
                            status=status
                        )
                        await self.consumer.commit()
                        continue

                    # Processar ticket
                    self.logger.info(
                        'ticket_consumed',
                        ticket_id=ticket.get('ticket_id'),
                        task_type=task_type,
                        plan_id=ticket.get('plan_id')
                    )

                    # TODO: Incrementar métrica worker_agent_tickets_consumed_total{task_type=...}

                    await self.execution_engine.process_ticket(ticket)

                    # Commit offset após processamento bem-sucedido
                    await self.consumer.commit()

                except Exception as e:
                    self.logger.error(
                        'ticket_processing_failed',
                        ticket_id=ticket.get('ticket_id') if isinstance(ticket, dict) else None,
                        error=str(e),
                        topic=message.topic,
                        partition=message.partition,
                        offset=message.offset
                    )
                    # Não commit - permite retry
                    # TODO: Incrementar métrica worker_agent_kafka_consumer_errors_total{error_type=...}

        except Exception as e:
            self.logger.error('kafka_consumer_loop_failed', error=str(e))
            raise
        finally:
            self.running = False

    async def stop(self):
        '''Parar consumer'''
        self.running = False
        if self.consumer:
            await self.consumer.stop()
            self.logger.info('kafka_consumer_stopped')
