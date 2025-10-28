import asyncio
import structlog
from aiokafka import AIOKafkaConsumer
from aiokafka.errors import KafkaError
import json
from typing import Dict, List
from ..services.analytics_engine import AnalyticsEngine
from ..services.insight_generator import InsightGenerator
from ..models.insight import InsightType, TimeWindow
from ..clients.mongodb_client import MongoDBClient
from ..clients.redis_client import RedisClient
from ..observability.metrics import record_insight_generated, update_kafka_consumer_lag

logger = structlog.get_logger()


class TelemetryConsumer:
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
        queen_agent_client,
        window_size_seconds: int = 300
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
        self.window_size_seconds = window_size_seconds
        self.consumer = None
        self.running = False
        self.telemetry_buffer = []

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
            logger.info('telemetry_consumer_initialized', topic=self.topic)
        except Exception as e:
            logger.error('telemetry_consumer_initialization_failed', error=str(e))
            raise

    async def start(self):
        """Iniciar loop de consumo"""
        self.running = True
        logger.info('telemetry_consumer_started')

        try:
            async for message in self.consumer:
                if not self.running:
                    break

                try:
                    await self.process_telemetry(message.value)

                    # Commit offset após processamento bem-sucedido
                    await self.consumer.commit()

                    # Atualizar lag
                    lag = await self._get_consumer_lag()
                    update_kafka_consumer_lag(self.topic, str(message.partition), lag)

                except Exception as e:
                    logger.error('telemetry_processing_failed', error=str(e), message=message.value)
                    # Não faz commit em caso de erro

        except KafkaError as e:
            logger.error('kafka_error', error=str(e))
        finally:
            await self.stop()

    async def stop(self):
        """Parar consumer gracefully"""
        self.running = False
        if self.consumer:
            await self.consumer.stop()
        logger.info('telemetry_consumer_stopped')

    async def process_telemetry(self, message: dict):
        """Processar mensagem de telemetria"""
        try:
            # Extrair dados
            correlation_id = message.get('correlation_id', '')
            intent_id = message.get('intent_id', '')
            plan_id = message.get('plan_id', '')
            metrics = message.get('metrics', {})

            # Adicionar ao buffer
            self.telemetry_buffer.append(message)

            # Log
            logger.debug('telemetry_received', correlation_id=correlation_id, metrics_count=len(metrics))

            # Verificar se janela temporal está completa
            if self._should_analyze_window():
                await self._analyze_window()

        except Exception as e:
            logger.error('process_telemetry_failed', error=str(e))
            raise

    def _should_analyze_window(self) -> bool:
        """Verificar se janela temporal deve ser analisada"""
        if not self.telemetry_buffer:
            return False

        # Análise simples: buffer atingiu tamanho mínimo
        return len(self.telemetry_buffer) >= 10

    async def _analyze_window(self):
        """Analisar janela de telemetria"""
        try:
            if not self.telemetry_buffer:
                return

            # Extrair timestamps
            timestamps = [msg.get('timestamp', 0) for msg in self.telemetry_buffer if 'timestamp' in msg]
            if not timestamps:
                return

            time_window = TimeWindow(
                start_timestamp=min(timestamps),
                end_timestamp=max(timestamps)
            )

            # Extrair métricas
            latency_values = []
            error_rates = []

            for msg in self.telemetry_buffer:
                metrics = msg.get('metrics', {})
                if 'latency_ms' in metrics:
                    latency_values.append(float(metrics['latency_ms']))
                if 'error_rate' in metrics:
                    error_rates.append(float(metrics['error_rate']))

            # Detectar anomalias em latência
            if latency_values:
                anomalies = self.analytics_engine.detect_anomalies(
                    'latency_ms',
                    latency_values,
                    method='zscore',
                    threshold=3.0
                )

                # Gerar insight para cada anomalia detectada
                for anomaly in anomalies:
                    await self._generate_anomaly_insight(anomaly, time_window)

            # Limpar buffer
            self.telemetry_buffer = []

            logger.info('telemetry_window_analyzed', window_size=len(self.telemetry_buffer))

        except Exception as e:
            logger.error('analyze_window_failed', error=str(e))

    async def _generate_anomaly_insight(self, anomaly: dict, time_window: TimeWindow):
        """Gerar insight de anomalia"""
        try:
            anomaly_data = {
                'metric_name': 'latency_ms',
                'value': anomaly.get('value'),
                'zscore': anomaly.get('zscore'),
                'method': 'zscore',
                'time_window': {
                    'start': time_window.start_timestamp,
                    'end': time_window.end_timestamp
                },
                'correlation_id': '',
                'tags': ['anomaly', 'latency']
            }

            # Gerar insight
            insight = await self.insight_generator.generate_anomaly_insight(anomaly_data)

            # Persistir
            await self.mongodb_client.save_insight(insight)

            # Cachear
            await self.redis_client.cache_insight(insight)

            # Publicar no Kafka
            await self.insight_producer.publish_insight(insight)

            # Enviar ao Queen Agent se operacional
            from ..models.insight import InsightType
            if insight.insight_type == InsightType.OPERATIONAL:
                await self.queen_agent_client.send_operational_insight(insight)

            # Registrar métrica
            record_insight_generated(insight.insight_type.value, insight.priority.value)

            logger.info('anomaly_insight_generated', insight_id=insight.insight_id, priority=insight.priority)

        except Exception as e:
            logger.error('generate_anomaly_insight_failed', error=str(e))

    async def _get_consumer_lag(self) -> int:
        """Obter lag do consumer"""
        try:
            # Implementação simplificada
            return 0
        except Exception as e:
            logger.error('get_consumer_lag_failed', error=str(e))
            return 0
