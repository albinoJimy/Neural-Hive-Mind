"""
Kafka Producer para eventos de sincronização de memória

Publica eventos para sincronização assíncrona MongoDB -> ClickHouse.
Utiliza serialização Avro conforme schema em schemas/memory-sync-event/memory-sync-event.avsc
"""
import io
import json
import asyncio
import structlog
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Any
from aiokafka import AIOKafkaProducer
from aiokafka.errors import KafkaError
from prometheus_client import Counter, Histogram
import fastavro
from fastavro.schema import load_schema

logger = structlog.get_logger(__name__)

# Caminho do schema Avro
AVRO_SCHEMA_PATH = Path(__file__).parent.parent.parent.parent.parent / 'schemas' / 'memory-sync-event' / 'memory-sync-event.avsc'

# Cache do schema Avro carregado
_avro_schema = None


def get_avro_schema():
    """
    Carrega e retorna o schema Avro para MemorySyncEvent.
    Usa cache para evitar leituras repetidas do arquivo.
    """
    global _avro_schema
    if _avro_schema is None:
        if AVRO_SCHEMA_PATH.exists():
            _avro_schema = fastavro.schema.load_schema(str(AVRO_SCHEMA_PATH))
            logger.info("Schema Avro carregado", path=str(AVRO_SCHEMA_PATH))
        else:
            logger.warning(
                "Schema Avro não encontrado, usando JSON fallback",
                path=str(AVRO_SCHEMA_PATH)
            )
    return _avro_schema


def serialize_avro(event: Dict[str, Any], schema) -> bytes:
    """
    Serializa evento usando Avro.

    Args:
        event: Evento a serializar
        schema: Schema Avro

    Returns:
        Bytes do evento serializado
    """
    buffer = io.BytesIO()
    fastavro.schemaless_writer(buffer, schema, event)
    return buffer.getvalue()

# Métricas Prometheus
SYNC_EVENTS_PUBLISHED = Counter(
    'memory_sync_events_published_total',
    'Total de eventos de sincronização publicados',
    ['status', 'data_type']
)

SYNC_PUBLISH_LATENCY = Histogram(
    'memory_sync_publish_latency_seconds',
    'Latência de publicação de eventos de sincronização',
    ['data_type'],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0]
)


class KafkaSyncProducer:
    """
    Producer Kafka para eventos de sincronização de memória.

    Publica eventos de sincronização para processamento assíncrono
    pelo consumer que insere dados no ClickHouse.
    Utiliza serialização Avro quando o schema está disponível.
    """

    def __init__(self, settings):
        """
        Inicializa o producer Kafka.

        Args:
            settings: Configurações da aplicação
        """
        self.settings = settings
        self.producer: Optional[AIOKafkaProducer] = None
        self._started = False
        self._retry_attempts = 3
        self._retry_delay = 1.0
        self._avro_schema = None
        self._use_avro = True  # Tenta usar Avro por padrão

    async def start(self):
        """Inicializa e conecta o producer Kafka"""
        if self._started:
            logger.warning("Producer já está rodando")
            return

        try:
            # Carrega schema Avro
            self._avro_schema = get_avro_schema()
            if self._avro_schema is None:
                self._use_avro = False
                logger.warning("Avro schema não disponível, usando JSON")

            # Configuração de segurança
            security_kwargs = {}
            if self.settings.kafka_security_protocol != 'PLAINTEXT':
                security_kwargs['security_protocol'] = self.settings.kafka_security_protocol
                if self.settings.kafka_sasl_username and self.settings.kafka_sasl_password:
                    security_kwargs['sasl_mechanism'] = 'PLAIN'
                    security_kwargs['sasl_plain_username'] = self.settings.kafka_sasl_username
                    security_kwargs['sasl_plain_password'] = self.settings.kafka_sasl_password

            self.producer = AIOKafkaProducer(
                bootstrap_servers=self.settings.kafka_bootstrap_servers,
                acks='all',  # Garante durabilidade
                compression_type='gzip',
                enable_idempotence=True,  # Previne duplicatas
                max_request_size=1048576,  # 1MB
                request_timeout_ms=30000,
                retry_backoff_ms=100,
                **security_kwargs
            )

            await self.producer.start()
            self._started = True
            logger.info(
                "Kafka sync producer iniciado",
                bootstrap_servers=self.settings.kafka_bootstrap_servers,
                topic=self.settings.kafka_sync_topic,
                serialization='avro' if self._use_avro else 'json'
            )

        except Exception as e:
            logger.error("Falha ao iniciar Kafka sync producer", error=str(e))
            raise

    async def stop(self):
        """Para o producer Kafka gracefully"""
        if not self._started or not self.producer:
            return

        try:
            await self.producer.stop()
            self._started = False
            logger.info("Kafka sync producer parado")
        except Exception as e:
            logger.error("Erro ao parar Kafka sync producer", error=str(e))

    def _prepare_avro_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """
        Prepara evento para serialização Avro, garantindo conformidade com o schema.

        Args:
            event: Evento original

        Returns:
            Evento formatado para Avro
        """
        return {
            'event_id': str(event.get('event_id', '')),
            'entity_id': str(event.get('entity_id', '')),
            'data_type': str(event.get('data_type', 'unknown')),
            'operation': str(event.get('operation', 'INSERT')),
            'collection': str(event.get('collection', '')),
            'timestamp': int(event.get('timestamp', int(datetime.utcnow().timestamp() * 1000))),
            'data': str(event.get('data', '{}')),
            'metadata': event.get('metadata') if event.get('metadata') else None
        }

    async def publish_sync_event(self, event: Dict[str, Any]) -> bool:
        """
        Publica evento de sincronização no Kafka.

        Utiliza serialização Avro quando disponível, com fallback para JSON.

        Args:
            event: Evento de sincronização com campos:
                - event_id: ID único do evento
                - entity_id: ID da entidade
                - data_type: Tipo de dado
                - operation: INSERT, UPDATE ou DELETE
                - collection: Coleção MongoDB de origem
                - timestamp: Timestamp em milissegundos
                - data: Dados serializados em JSON
                - metadata: Metadados opcionais

        Returns:
            True se publicado com sucesso, False caso contrário
        """
        if not self._started or not self.producer:
            logger.warning("Producer não está rodando, evento não publicado")
            return False

        data_type = event.get('data_type', 'unknown')
        start_time = datetime.utcnow()

        for attempt in range(self._retry_attempts):
            try:
                # Serializa evento usando Avro ou JSON
                if self._use_avro and self._avro_schema:
                    avro_event = self._prepare_avro_event(event)
                    value = serialize_avro(avro_event, self._avro_schema)
                else:
                    value = json.dumps(event).encode('utf-8')

                key = event.get('entity_id', '').encode('utf-8')

                # Publica no Kafka
                await self.producer.send_and_wait(
                    topic=self.settings.kafka_sync_topic,
                    value=value,
                    key=key
                )

                # Registra métricas
                latency = (datetime.utcnow() - start_time).total_seconds()
                SYNC_EVENTS_PUBLISHED.labels(status='success', data_type=data_type).inc()
                SYNC_PUBLISH_LATENCY.labels(data_type=data_type).observe(latency)

                logger.debug(
                    "Evento de sincronização publicado",
                    event_id=event.get('event_id'),
                    entity_id=event.get('entity_id'),
                    data_type=data_type,
                    latency_ms=int(latency * 1000),
                    serialization='avro' if self._use_avro else 'json'
                )

                return True

            except KafkaError as e:
                SYNC_EVENTS_PUBLISHED.labels(status='error', data_type=data_type).inc()
                logger.warning(
                    "Erro ao publicar evento de sincronização",
                    error=str(e),
                    attempt=attempt + 1,
                    max_attempts=self._retry_attempts
                )

                if attempt < self._retry_attempts - 1:
                    await asyncio.sleep(self._retry_delay * (2 ** attempt))
                else:
                    logger.error(
                        "Falha ao publicar evento após todas as tentativas",
                        event_id=event.get('event_id'),
                        entity_id=event.get('entity_id'),
                        error=str(e)
                    )
                    return False

            except Exception as e:
                SYNC_EVENTS_PUBLISHED.labels(status='error', data_type=data_type).inc()
                logger.error(
                    "Erro inesperado ao publicar evento de sincronização",
                    error=str(e),
                    event_id=event.get('event_id')
                )
                return False

        return False

    async def publish_batch(self, events: list) -> int:
        """
        Publica batch de eventos de sincronização.

        Args:
            events: Lista de eventos de sincronização

        Returns:
            Número de eventos publicados com sucesso
        """
        if not events:
            return 0

        success_count = 0
        for event in events:
            if await self.publish_sync_event(event):
                success_count += 1

        logger.info(
            "Batch de eventos publicado",
            total=len(events),
            success=success_count,
            failed=len(events) - success_count
        )

        return success_count

    @property
    def is_running(self) -> bool:
        """Verifica se o producer está rodando"""
        return self._started and self.producer is not None
