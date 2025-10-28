import asyncio
import structlog
from aiokafka import AIOKafkaConsumer
from aiokafka.errors import KafkaError
import json
from ..services.insight_generator import InsightGenerator
from ..clients.mongodb_client import MongoDBClient
from ..clients.redis_client import RedisClient
from ..observability.metrics import record_insight_generated

logger = structlog.get_logger()


class ExecutionConsumer:
    def __init__(
        self,
        bootstrap_servers: str,
        topic: str,
        group_id: str,
        insight_generator: InsightGenerator,
        mongodb_client: MongoDBClient,
        redis_client: RedisClient,
        insight_producer,
        queen_agent_client
    ):
        self.bootstrap_servers = bootstrap_servers
        self.topic = topic
        self.group_id = group_id
        self.insight_generator = insight_generator
        self.mongodb_client = mongodb_client
        self.redis_client = redis_client
        self.insight_producer = insight_producer
        self.queen_agent_client = queen_agent_client
        self.consumer = None
        self.running = False

    async def initialize(self):
        """Inicializar consumer Kafka"""
        try:
            self.consumer = AIOKafkaConsumer(
                self.topic,
                bootstrap_servers=self.bootstrap_servers,
                group_id=self.group_id,
                auto_offset_reset='earliest',
                enable_auto_commit=False,
                value_deserializer=lambda m: json.loads(m.decode('utf-8'))
            )
            await self.consumer.start()
            logger.info('execution_consumer_initialized', topic=self.topic)
        except Exception as e:
            logger.error('execution_consumer_initialization_failed', error=str(e))
            raise

    async def start(self):
        """Iniciar loop de consumo"""
        self.running = True
        logger.info('execution_consumer_started')

        try:
            async for message in self.consumer:
                if not self.running:
                    break

                try:
                    await self.process_execution_result(message.value)
                    await self.consumer.commit()

                except Exception as e:
                    logger.error('execution_processing_failed', error=str(e))

        except KafkaError as e:
            logger.error('kafka_error', error=str(e))
        finally:
            await self.stop()

    async def stop(self):
        """Parar consumer gracefully"""
        self.running = False
        if self.consumer:
            await self.consumer.stop()
        logger.info('execution_consumer_stopped')

    async def process_execution_result(self, message: dict):
        """Processar resultado de execução"""
        try:
            # Extrair dados
            ticket_id = message.get('ticket_id', '')
            status = message.get('status', '')
            execution_time_ms = message.get('execution_time_ms', 0)
            sla_deadline = message.get('sla_deadline', 0)
            timestamp = message.get('timestamp', 0)

            logger.debug(
                'execution_result_received',
                ticket_id=ticket_id,
                status=status,
                execution_time=execution_time_ms
            )

            # Verificar violação de SLA
            if sla_deadline and timestamp > sla_deadline:
                await self._generate_sla_violation_insight(message)

            # Verificar falha
            if status in ['FAILED', 'ERROR']:
                await self._generate_failure_insight(message)

        except Exception as e:
            logger.error('process_execution_result_failed', error=str(e))
            raise

    async def _generate_sla_violation_insight(self, execution: dict):
        """Gerar insight de violação de SLA"""
        try:
            from ..models.insight import InsightType

            sla_deadline = execution.get('sla_deadline', 0)
            timestamp = execution.get('timestamp', 0)
            violation_ms = timestamp - sla_deadline

            insight_data = {
                'title': f'Violação de SLA detectada',
                'summary': f'Ticket {execution.get("ticket_id")} violou SLA por {violation_ms}ms',
                'detailed_analysis': f'Execução completada {violation_ms}ms após deadline. '
                                     f'SLA: {sla_deadline}, Timestamp: {timestamp}',
                'data_sources': ['execution_results', 'kafka'],
                'metrics': {
                    'violation_ms': violation_ms,
                    'sla_deadline': sla_deadline,
                    'actual_timestamp': timestamp
                },
                'correlation_id': execution.get('correlation_id', ''),
                'ticket_id': execution.get('ticket_id', ''),
                'time_window': {
                    'start': timestamp,
                    'end': timestamp
                },
                'tags': ['sla', 'violation', 'execution']
            }

            insight = await self.insight_generator.generate_insight(
                insight_data,
                InsightType.OPERATIONAL
            )

            await self.mongodb_client.save_insight(insight)
            await self.redis_client.cache_insight(insight)
            await self.insight_producer.publish_insight(insight)

            # Enviar ao Queen Agent (insights operacionais)
            await self.queen_agent_client.send_operational_insight(insight)

            record_insight_generated(insight.insight_type.value, insight.priority.value)

            logger.info('sla_violation_insight_generated', insight_id=insight.insight_id)

        except Exception as e:
            logger.error('generate_sla_violation_insight_failed', error=str(e))

    async def _generate_failure_insight(self, execution: dict):
        """Gerar insight de falha de execução"""
        try:
            from ..models.insight import InsightType

            insight_data = {
                'title': f'Falha de execução detectada',
                'summary': f'Ticket {execution.get("ticket_id")} falhou com status {execution.get("status")}',
                'detailed_analysis': f'Execução falhou. Status: {execution.get("status")}, '
                                     f'Error: {execution.get("error_message", "N/A")}',
                'data_sources': ['execution_results', 'kafka'],
                'metrics': {
                    'execution_time_ms': execution.get('execution_time_ms', 0),
                    'retry_count': execution.get('retry_count', 0)
                },
                'correlation_id': execution.get('correlation_id', ''),
                'ticket_id': execution.get('ticket_id', ''),
                'time_window': {
                    'start': execution.get('timestamp', 0),
                    'end': execution.get('timestamp', 0)
                },
                'tags': ['execution', 'failure', 'error']
            }

            insight = await self.insight_generator.generate_insight(
                insight_data,
                InsightType.OPERATIONAL
            )

            await self.mongodb_client.save_insight(insight)
            await self.redis_client.cache_insight(insight)
            await self.insight_producer.publish_insight(insight)

            # Enviar ao Queen Agent (insights operacionais)
            await self.queen_agent_client.send_operational_insight(insight)

            record_insight_generated(insight.insight_type.value, insight.priority.value)

            logger.info('failure_insight_generated', insight_id=insight.insight_id)

        except Exception as e:
            logger.error('generate_failure_insight_failed', error=str(e))
