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


class PheromoneConsumer:
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
        self.pheromone_stats = {}

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
            logger.info('pheromone_consumer_initialized', topic=self.topic)
        except Exception as e:
            logger.error('pheromone_consumer_initialization_failed', error=str(e))
            raise

    async def start(self):
        """Iniciar loop de consumo"""
        self.running = True
        logger.info('pheromone_consumer_started')

        try:
            async for message in self.consumer:
                if not self.running:
                    break

                try:
                    await self.process_pheromone_signal(message.value)
                    await self.consumer.commit()

                except Exception as e:
                    logger.error('pheromone_processing_failed', error=str(e))

        except KafkaError as e:
            logger.error('kafka_error', error=str(e))
        finally:
            await self.stop()

    async def stop(self):
        """Parar consumer gracefully"""
        self.running = False
        if self.consumer:
            await self.consumer.stop()
        logger.info('pheromone_consumer_stopped')

    async def process_pheromone_signal(self, message: dict):
        """Processar sinal de feromônio"""
        try:
            # Extrair dados
            pheromone_type = message.get('type', '')
            domain = message.get('domain', '')
            strength = message.get('strength', 0.0)
            specialist_type = message.get('specialist_type', '')

            logger.debug(
                'pheromone_signal_received',
                type=pheromone_type,
                domain=domain,
                strength=strength
            )

            # Agregar estatísticas por domínio
            key = f'{domain}_{pheromone_type}'
            if key not in self.pheromone_stats:
                self.pheromone_stats[key] = {
                    'count': 0,
                    'total_strength': 0.0,
                    'success_count': 0,
                    'failure_count': 0
                }

            self.pheromone_stats[key]['count'] += 1
            self.pheromone_stats[key]['total_strength'] += strength

            if pheromone_type == 'SUCCESS':
                self.pheromone_stats[key]['success_count'] += 1
            elif pheromone_type == 'FAILURE':
                self.pheromone_stats[key]['failure_count'] += 1

            # Calcular taxa de falha
            stats = self.pheromone_stats[key]
            if stats['count'] >= 10:  # Mínimo de 10 sinais
                failure_rate = stats['failure_count'] / stats['count']

                # Detectar alta taxa de falha
                if failure_rate > 0.5:  # 50% threshold
                    await self._generate_high_failure_rate_insight(domain, pheromone_type, failure_rate, stats)

        except Exception as e:
            logger.error('process_pheromone_signal_failed', error=str(e))
            raise

    async def _generate_high_failure_rate_insight(self, domain: str, pheromone_type: str, failure_rate: float, stats: dict):
        """Gerar insight de alta taxa de falha em trilha de feromônios"""
        try:
            from ..models.insight import InsightType

            insight_data = {
                'title': f'Alta taxa de falha em trilha de feromônios',
                'summary': f'Domínio {domain} apresenta {failure_rate*100:.1f}% de falha em trilha {pheromone_type}',
                'detailed_analysis': f'Trilha de feromônios no domínio {domain} com alta taxa de falha. '
                                     f'Taxa de falha: {failure_rate*100:.1f}%, '
                                     f'Total de sinais: {stats["count"]}, '
                                     f'Falhas: {stats["failure_count"]}, '
                                     f'Sucessos: {stats["success_count"]}',
                'data_sources': ['pheromone_signals', 'kafka'],
                'metrics': {
                    'failure_rate': failure_rate,
                    'total_signals': stats['count'],
                    'failure_count': stats['failure_count'],
                    'success_count': stats['success_count'],
                    'avg_strength': stats['total_strength'] / stats['count']
                },
                'correlation_id': '',
                'domain': domain,
                'time_window': {
                    'start': 0,
                    'end': 0
                },
                'tags': ['pheromone', 'failure', 'coordination', domain]
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

            logger.info('pheromone_failure_insight_generated', insight_id=insight.insight_id, domain=domain)

            # Resetar estatísticas após gerar insight
            key = f'{domain}_{pheromone_type}'
            self.pheromone_stats[key] = {
                'count': 0,
                'total_strength': 0.0,
                'success_count': 0,
                'failure_count': 0
            }

        except Exception as e:
            logger.error('generate_pheromone_failure_insight_failed', error=str(e))
