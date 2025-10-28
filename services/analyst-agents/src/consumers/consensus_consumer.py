import asyncio
import structlog
from aiokafka import AIOKafkaConsumer
from aiokafka.errors import KafkaError
import json
from typing import Dict
from ..services.analytics_engine import AnalyticsEngine
from ..services.insight_generator import InsightGenerator
from ..clients.mongodb_client import MongoDBClient
from ..clients.redis_client import RedisClient
from ..observability.metrics import record_insight_generated

logger = structlog.get_logger()


class ConsensusConsumer:
    def __init__(
        self,
        bootstrap_servers: str,
        topic: str,
        group_id: str,
        analytics_engine: AnalyticsEngine,
        insight_generator: InsightGenerator,
        mongodb_client: MongoDBClient,
        redis_client: RedisClient,
        insight_producer,
        queen_agent_client
    ):
        self.bootstrap_servers = bootstrap_servers
        self.topic = topic
        self.group_id = group_id
        self.analytics_engine = analytics_engine
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
            logger.info('consensus_consumer_initialized', topic=self.topic)
        except Exception as e:
            logger.error('consensus_consumer_initialization_failed', error=str(e))
            raise

    async def start(self):
        """Iniciar loop de consumo"""
        self.running = True
        logger.info('consensus_consumer_started')

        try:
            async for message in self.consumer:
                if not self.running:
                    break

                try:
                    await self.process_consensus_decision(message.value)
                    await self.consumer.commit()

                except Exception as e:
                    logger.error('consensus_processing_failed', error=str(e))

        except KafkaError as e:
            logger.error('kafka_error', error=str(e))
        finally:
            await self.stop()

    async def stop(self):
        """Parar consumer gracefully"""
        self.running = False
        if self.consumer:
            await self.consumer.stop()
        logger.info('consensus_consumer_stopped')

    async def process_consensus_decision(self, message: dict):
        """Processar decisão de consenso"""
        try:
            # Extrair métricas de consenso
            decision_id = message.get('decision_id', '')
            aggregated_confidence = message.get('aggregated_confidence', 0.0)
            aggregated_risk = message.get('aggregated_risk', 0.0)
            consensus_metrics = message.get('consensus_metrics', {})

            divergence_score = consensus_metrics.get('divergence_score', 0.0)
            convergence_time_ms = consensus_metrics.get('convergence_time_ms', 0)

            logger.debug(
                'consensus_decision_received',
                decision_id=decision_id,
                divergence=divergence_score,
                convergence_time=convergence_time_ms
            )

            # Detectar divergência alta
            if divergence_score > 0.05:  # 5% threshold
                await self._generate_divergence_insight(message, divergence_score)

            # Detectar convergência lenta
            if convergence_time_ms > 5000:  # 5 segundos threshold
                await self._generate_convergence_insight(message, convergence_time_ms)

        except Exception as e:
            logger.error('process_consensus_decision_failed', error=str(e))
            raise

    async def _generate_divergence_insight(self, decision: dict, divergence: float):
        """Gerar insight de divergência alta"""
        try:
            from ..models.insight import InsightType, Priority

            insight_data = {
                'title': f'Alta divergência entre especialistas',
                'summary': f'Divergência de {divergence*100:.1f}% detectada na decisão {decision.get("decision_id")}',
                'detailed_analysis': f'Múltiplas rejeições ou baixa confiança entre especialistas. '
                                     f'Divergência: {divergence*100:.1f}%, Confiança agregada: {decision.get("aggregated_confidence", 0)*100:.0f}%',
                'data_sources': ['consensus_engine', 'kafka'],
                'metrics': {
                    'divergence_score': divergence,
                    'aggregated_confidence': decision.get('aggregated_confidence', 0.0)
                },
                'correlation_id': decision.get('correlation_id', ''),
                'decision_id': decision.get('decision_id', ''),
                'time_window': {
                    'start': decision.get('timestamp', 0),
                    'end': decision.get('timestamp', 0)
                },
                'tags': ['consensus', 'divergence', 'high_priority']
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

            logger.info('divergence_insight_generated', insight_id=insight.insight_id)

        except Exception as e:
            logger.error('generate_divergence_insight_failed', error=str(e))

    async def _generate_convergence_insight(self, decision: dict, convergence_time: int):
        """Gerar insight de convergência lenta"""
        try:
            from ..models.insight import InsightType

            insight_data = {
                'title': f'Convergência lenta detectada',
                'summary': f'Tempo de convergência de {convergence_time}ms para decisão {decision.get("decision_id")}',
                'detailed_analysis': f'O consenso levou {convergence_time}ms para convergir, '
                                     f'acima do threshold de 5000ms. Possível gargalo no processo de decisão.',
                'data_sources': ['consensus_engine', 'kafka'],
                'metrics': {
                    'convergence_time_ms': convergence_time,
                    'threshold_ms': 5000
                },
                'correlation_id': decision.get('correlation_id', ''),
                'decision_id': decision.get('decision_id', ''),
                'time_window': {
                    'start': decision.get('timestamp', 0),
                    'end': decision.get('timestamp', 0)
                },
                'tags': ['consensus', 'convergence', 'performance']
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

            logger.info('convergence_insight_generated', insight_id=insight.insight_id)

        except Exception as e:
            logger.error('generate_convergence_insight_failed', error=str(e))
