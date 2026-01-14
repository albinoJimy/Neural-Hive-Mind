"""
Consumer Kafka para eventos de sincronização de memória

Consome eventos do Kafka e insere dados no ClickHouse.
Suporta deserialização Avro e JSON (fallback).
"""
import io
import json
import asyncio
import structlog
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Any
from aiokafka import AIOKafkaConsumer
from aiokafka.errors import KafkaError
from prometheus_client import Counter, Histogram, Gauge, REGISTRY
import fastavro

logger = structlog.get_logger(__name__)

# Caminho do schema Avro
AVRO_SCHEMA_PATH = Path(__file__).parent.parent.parent.parent / 'schemas' / 'memory-sync-event' / 'memory-sync-event.avsc'

# Cache do schema Avro carregado
_avro_schema = None

# Cache das metricas Prometheus (singleton pattern)
_metrics_initialized = False
SYNC_EVENTS_CONSUMED = None
SYNC_CONSUME_LATENCY = None
SYNC_CONSUMER_LAG = None
DLQ_EVENTS_SENT = None


def _get_or_create_metric(metric_class, name, description, labels=None, **kwargs):
    """
    Retorna metrica existente ou cria nova se nao existir.
    Verifica primeiro no REGISTRY para evitar duplicacao.
    """
    # Verificar se metrica ja existe no registry usando as chaves do dicionario
    if name in REGISTRY._names_to_collectors:
        return REGISTRY._names_to_collectors[name]

    # Para Counter, verificar tambem a versao base (sem _total)
    base_name = name.replace('_total', '') if name.endswith('_total') else name
    if base_name in REGISTRY._names_to_collectors:
        return REGISTRY._names_to_collectors[base_name]

    # Metrica nao existe, criar nova
    try:
        if labels:
            return metric_class(name, description, labels, **kwargs)
        return metric_class(name, description, **kwargs)
    except ValueError:
        # Fallback: buscar por _name do collector
        for collector in list(REGISTRY._names_to_collectors.values()):
            if hasattr(collector, '_name') and collector._name == name:
                return collector
        raise


def _initialize_metrics():
    """Inicializa metricas Prometheus apenas uma vez."""
    global _metrics_initialized, SYNC_EVENTS_CONSUMED, SYNC_CONSUME_LATENCY
    global SYNC_CONSUMER_LAG, DLQ_EVENTS_SENT

    if _metrics_initialized:
        return

    SYNC_EVENTS_CONSUMED = _get_or_create_metric(
        Counter,
        'memory_sync_events_consumed_total',
        'Total de eventos de sincronização consumidos',
        ['status', 'data_type']
    )

    SYNC_CONSUME_LATENCY = _get_or_create_metric(
        Histogram,
        'memory_sync_consume_latency_seconds',
        'Latência de processamento de eventos de sincronização',
        ['data_type'],
        buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
    )

    SYNC_CONSUMER_LAG = _get_or_create_metric(
        Gauge,
        'memory_sync_consumer_lag',
        'Lag do consumer de sincronização',
        ['partition']
    )

    DLQ_EVENTS_SENT = _get_or_create_metric(
        Counter,
        'memory_sync_dlq_events_total',
        'Total de eventos enviados para DLQ',
        ['reason']
    )

    _metrics_initialized = True


# Inicializa metricas na importacao do modulo
_initialize_metrics()


def get_avro_schema():
    """
    Carrega e retorna o schema Avro para MemorySyncEvent.
    Usa cache para evitar leituras repetidas do arquivo.
    """
    global _avro_schema
    if _avro_schema is None:
        if AVRO_SCHEMA_PATH.exists():
            _avro_schema = fastavro.schema.load_schema(str(AVRO_SCHEMA_PATH))
            logger.info("Schema Avro carregado para consumer", path=str(AVRO_SCHEMA_PATH))
        else:
            logger.warning(
                "Schema Avro não encontrado para consumer",
                path=str(AVRO_SCHEMA_PATH)
            )
    return _avro_schema


def deserialize_avro(data: bytes, schema) -> Dict[str, Any]:
    """
    Deserializa dados Avro.

    Args:
        data: Bytes do evento serializado
        schema: Schema Avro

    Returns:
        Dicionário com o evento deserializado
    """
    buffer = io.BytesIO(data)
    return fastavro.schemaless_reader(buffer, schema)


class SyncEventConsumer:
    """
    Consumer Kafka para eventos de sincronização de memória.

    Consome eventos de sincronização e insere dados no ClickHouse.
    Implementa idempotência e Dead Letter Queue para eventos com falha.
    """

    def __init__(self, settings, clickhouse_client, dlq_producer=None):
        """
        Inicializa o consumer Kafka.

        Args:
            settings: Configurações da aplicação
            clickhouse_client: Cliente ClickHouse para inserção de dados
            dlq_producer: Producer opcional para Dead Letter Queue
        """
        self.settings = settings
        self.clickhouse = clickhouse_client
        self.dlq_producer = dlq_producer
        self.consumer: Optional[AIOKafkaConsumer] = None
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._max_retries = 3
        self._processed_ids: set = set()  # Cache simples para idempotência
        self._processed_ids_max_size = 10000
        self._avro_schema = None
        self._use_avro = True  # Tenta usar Avro por padrão

    async def start(self):
        """Inicializa e conecta o consumer Kafka"""
        if self._running:
            logger.warning("Consumer já está rodando")
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

            self.consumer = AIOKafkaConsumer(
                self.settings.kafka_sync_topic,
                bootstrap_servers=self.settings.kafka_bootstrap_servers,
                group_id=self.settings.kafka_consumer_group,
                auto_offset_reset='earliest',
                enable_auto_commit=False,  # Commit manual após processamento
                max_poll_records=100,
                session_timeout_ms=30000,
                heartbeat_interval_ms=10000,
                **security_kwargs
            )

            await self.consumer.start()
            self._running = True

            # Inicia loop de consumo em background
            self._task = asyncio.create_task(self._consume_loop())

            logger.info(
                "Kafka sync consumer iniciado",
                topic=self.settings.kafka_sync_topic,
                group_id=self.settings.kafka_consumer_group,
                deserialization='avro' if self._use_avro else 'json'
            )

        except Exception as e:
            logger.error("Falha ao iniciar Kafka sync consumer", error=str(e))
            raise

    async def stop(self):
        """Para o consumer Kafka gracefully"""
        if not self._running:
            return

        self._running = False

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        if self.consumer:
            await self.consumer.stop()

        logger.info("Kafka sync consumer parado")

    async def _consume_loop(self):
        """Loop principal de consumo de mensagens"""
        try:
            async for msg in self.consumer:
                if not self._running:
                    break

                try:
                    await self._process_message(msg)
                    # Commit offset após processamento bem-sucedido
                    await self.consumer.commit()
                except Exception as e:
                    logger.error(
                        "Erro ao processar mensagem",
                        error=str(e),
                        topic=msg.topic,
                        partition=msg.partition,
                        offset=msg.offset
                    )

        except asyncio.CancelledError:
            logger.info("Consumer loop cancelado")
        except Exception as e:
            logger.error("Erro fatal no consumer loop", error=str(e))
            raise

    def _deserialize_message(self, msg) -> Dict[str, Any]:
        """
        Deserializa mensagem do Kafka usando Avro ou JSON.

        Tenta Avro primeiro, com fallback para JSON se falhar.

        Args:
            msg: Mensagem do Kafka

        Returns:
            Dicionário com o evento deserializado

        Raises:
            ValueError: Se não conseguir deserializar em nenhum formato
        """
        raw_data = msg.value

        # Tenta Avro primeiro se schema disponível
        if self._use_avro and self._avro_schema:
            try:
                event = deserialize_avro(raw_data, self._avro_schema)
                logger.debug("Mensagem deserializada com Avro")
                return event
            except Exception as avro_error:
                logger.debug(
                    "Falha na deserialização Avro, tentando JSON",
                    error=str(avro_error)
                )

        # Fallback para JSON
        try:
            event = json.loads(raw_data.decode('utf-8'))
            logger.debug("Mensagem deserializada com JSON")
            return event
        except json.JSONDecodeError as json_error:
            raise ValueError(f"Falha ao deserializar mensagem: Avro e JSON falharam. JSON error: {json_error}")

    async def _process_message(self, msg):
        """
        Processa uma mensagem do Kafka.

        Suporta deserialização Avro e JSON (fallback).

        Args:
            msg: Mensagem do Kafka
        """
        start_time = datetime.utcnow()

        try:
            # Deserializa evento (Avro ou JSON)
            event = self._deserialize_message(msg)
            event_id = event.get('event_id')
            data_type = event.get('data_type', 'unknown')

            # Verifica idempotência
            if event_id in self._processed_ids:
                logger.debug("Evento já processado, ignorando", event_id=event_id)
                SYNC_EVENTS_CONSUMED.labels(status='duplicate', data_type=data_type).inc()
                return

            # Processa evento com retries
            success = await self._process_event_with_retry(event)

            if success:
                # Marca como processado
                self._add_processed_id(event_id)
                SYNC_EVENTS_CONSUMED.labels(status='success', data_type=data_type).inc()
            else:
                # Envia para DLQ após todas as tentativas
                await self._send_to_dlq(event, 'max_retries_exceeded')
                SYNC_EVENTS_CONSUMED.labels(status='failed', data_type=data_type).inc()

            # Registra latência
            latency = (datetime.utcnow() - start_time).total_seconds()
            SYNC_CONSUME_LATENCY.labels(data_type=data_type).observe(latency)

        except ValueError as e:
            logger.error("Erro ao deserializar evento", error=str(e))
            await self._send_to_dlq({'raw': msg.value.decode('utf-8', errors='replace')}, 'decode_error')
            SYNC_EVENTS_CONSUMED.labels(status='decode_error', data_type='unknown').inc()

    async def _process_event_with_retry(self, event: Dict[str, Any]) -> bool:
        """
        Processa evento com retry logic.

        Args:
            event: Evento de sincronização

        Returns:
            True se processado com sucesso
        """
        for attempt in range(self._max_retries):
            try:
                await self._process_event(event)
                return True
            except Exception as e:
                logger.warning(
                    "Erro ao processar evento",
                    error=str(e),
                    attempt=attempt + 1,
                    max_attempts=self._max_retries,
                    event_id=event.get('event_id')
                )
                if attempt < self._max_retries - 1:
                    await asyncio.sleep(1.0 * (2 ** attempt))  # Exponential backoff

        return False

    async def _process_event(self, event: Dict[str, Any]):
        """
        Processa um evento de sincronização e insere no ClickHouse.

        Args:
            event: Evento de sincronização
        """
        operation = event.get('operation', 'INSERT')
        data_type = event.get('data_type', 'context')
        entity_id = event.get('entity_id')

        # Deserializa dados
        data_str = event.get('data', '{}')
        data = json.loads(data_str) if isinstance(data_str, str) else data_str

        if operation == 'DELETE':
            # Para DELETEs, não fazemos nada no ClickHouse (dados históricos são imutáveis)
            logger.debug("Operação DELETE ignorada para ClickHouse", entity_id=entity_id)
            return

        # Mapeia data_type para tabela ClickHouse
        table_mapping = {
            'context': 'operational_context_history',
            'operational_context': 'operational_context_history',
            'lineage': 'data_lineage_history',
            'data_lineage': 'data_lineage_history',
            'quality_metrics': 'quality_metrics_history',
            'data_quality_metrics': 'quality_metrics_history',
            'cognitive_plan': 'cognitive_plans_history',
            'consensus_decision': 'consensus_decisions_history',
            'specialist_opinion': 'specialist_opinions_history'
        }

        table_name = table_mapping.get(data_type, 'operational_context_history')

        # Prepara dados para inserção
        timestamp = event.get('timestamp', int(datetime.utcnow().timestamp() * 1000))
        created_at = datetime.fromtimestamp(timestamp / 1000)

        # Verifica idempotência no ClickHouse
        exists = await self._check_exists(table_name, entity_id, created_at)
        if exists:
            logger.debug(
                "Registro já existe no ClickHouse",
                entity_id=entity_id,
                table=table_name
            )
            return

        # Insere no ClickHouse
        await self._insert_to_clickhouse(table_name, entity_id, data, created_at, event)

        logger.debug(
            "Evento processado e inserido no ClickHouse",
            entity_id=entity_id,
            table=table_name,
            data_type=data_type
        )

    async def _check_exists(self, table: str, entity_id: str, created_at: datetime) -> bool:
        """
        Verifica se registro já existe no ClickHouse (idempotência).

        Args:
            table: Nome da tabela
            entity_id: ID da entidade
            created_at: Timestamp de criação

        Returns:
            True se já existe
        """
        try:
            # Query simples para verificar existência
            # Nota: Tabelas podem ter diferentes schemas, então verificamos por entity_id e timestamp
            query = f"""
                SELECT count(*) as cnt
                FROM {self.clickhouse.database}.{table}
                WHERE entity_id = %(entity_id)s
                  AND created_at = %(created_at)s
                LIMIT 1
            """
            result = self.clickhouse.client.query(
                query,
                parameters={'entity_id': entity_id, 'created_at': created_at}
            )
            return result.result_rows[0][0] > 0 if result.result_rows else False
        except Exception as e:
            # Se tabela não tem coluna entity_id, assume que não existe
            logger.debug("Verificação de existência falhou", error=str(e))
            return False

    async def _insert_to_clickhouse(
        self,
        table: str,
        entity_id: str,
        data: Dict,
        created_at: datetime,
        event: Dict
    ):
        """
        Insere dados no ClickHouse.

        Args:
            table: Nome da tabela
            entity_id: ID da entidade
            data: Dados a inserir
            created_at: Timestamp de criação
            event: Evento original
        """
        # Mapeia colunas baseado na tabela
        if table == 'operational_context_history':
            row = [
                entity_id,
                event.get('data_type', 'context'),
                created_at,
                json.dumps(data),
                event.get('metadata', '{}')
            ]
            columns = ['entity_id', 'data_type', 'created_at', 'data', 'metadata']

        elif table == 'data_lineage_history':
            row = [
                entity_id,
                data.get('operation', 'UNKNOWN'),
                created_at,
                data.get('source', ''),
                data.get('target', ''),
                json.dumps(data.get('metadata', {}))
            ]
            columns = ['entity_id', 'operation', 'created_at', 'source', 'target', 'metadata']

        elif table == 'quality_metrics_history':
            row = [
                event.get('collection', 'unknown'),
                created_at,
                data.get('completeness_score', 0.0),
                data.get('freshness_score', 0.0),
                data.get('consistency_score', 0.0),
                json.dumps(data.get('metadata', {}))
            ]
            columns = ['collection', 'created_at', 'completeness_score', 'freshness_score', 'consistency_score', 'metadata']

        elif table == 'cognitive_plans_history':
            row = [
                entity_id,
                data.get('intent_id', ''),
                data.get('domain', 'unknown'),
                created_at,
                float(data.get('risk_score', 0.0)),
                float(data.get('complexity_score', 0.0)),
                json.dumps(data.get('plan_data', {})),
                json.dumps(data.get('metadata', {}))
            ]
            columns = ['plan_id', 'intent_id', 'domain', 'created_at', 'risk_score', 'complexity_score', 'plan_data', 'metadata']

        else:
            # Fallback genérico
            row = [entity_id, created_at, json.dumps(data), event.get('metadata', '{}')]
            columns = ['entity_id', 'created_at', 'data', 'metadata']

        # Insere no ClickHouse
        await self.clickhouse.insert_batch(table, [row], columns)

    async def _send_to_dlq(self, event: Dict, reason: str):
        """
        Envia evento para Dead Letter Queue.

        Args:
            event: Evento que falhou
            reason: Motivo da falha
        """
        if not self.dlq_producer:
            logger.warning(
                "DLQ producer não configurado, evento perdido",
                event_id=event.get('event_id'),
                reason=reason
            )
            return

        try:
            dlq_event = {
                'original_event': event,
                'failure_reason': reason,
                'failed_at': datetime.utcnow().isoformat()
            }
            await self.dlq_producer.publish_sync_event(dlq_event)
            DLQ_EVENTS_SENT.labels(reason=reason).inc()
            logger.info(
                "Evento enviado para DLQ",
                event_id=event.get('event_id'),
                reason=reason
            )
        except Exception as e:
            logger.error("Falha ao enviar para DLQ", error=str(e))

    def _add_processed_id(self, event_id: str):
        """
        Adiciona ID ao cache de processados (com limite de tamanho).

        Args:
            event_id: ID do evento processado
        """
        if len(self._processed_ids) >= self._processed_ids_max_size:
            # Remove metade dos IDs mais antigos (FIFO aproximado)
            ids_list = list(self._processed_ids)
            self._processed_ids = set(ids_list[len(ids_list) // 2:])

        self._processed_ids.add(event_id)

    @property
    def is_running(self) -> bool:
        """Verifica se o consumer está rodando"""
        return self._running and self.consumer is not None


async def main():
    """
    Entrypoint assíncrono para execução do consumer como processo standalone.

    Inicializa Settings, ClickHouseClient e SyncEventConsumer, inicia o consumer
    e bloqueia até receber SIGTERM/SIGINT para shutdown graceful.
    """
    import signal
    from src.config.settings import Settings
    from src.clients.clickhouse_client import ClickHouseClient

    # Configura logging
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.add_log_level,
            structlog.processors.JSONRenderer()
        ]
    )

    logger.info("Iniciando Sync Event Consumer")

    # Carrega configurações
    settings = Settings()

    # Inicializa ClickHouse client
    clickhouse_client = ClickHouseClient(settings)
    await clickhouse_client.initialize()

    # Inicializa consumer
    consumer = SyncEventConsumer(
        settings=settings,
        clickhouse_client=clickhouse_client,
        dlq_producer=None  # DLQ producer opcional
    )

    # Evento para controle de shutdown
    shutdown_event = asyncio.Event()

    def signal_handler(sig, frame):
        """Handler para sinais SIGTERM e SIGINT"""
        logger.info("Sinal de shutdown recebido", signal=sig)
        shutdown_event.set()

    # Registra handlers de sinal
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    try:
        # Inicia consumer
        await consumer.start()
        logger.info("Sync Event Consumer iniciado com sucesso")

        # Aguarda sinal de shutdown
        await shutdown_event.wait()

    except Exception as e:
        logger.error("Erro fatal no Sync Event Consumer", error=str(e))
        raise

    finally:
        # Shutdown graceful
        logger.info("Iniciando shutdown graceful...")
        await consumer.stop()
        await clickhouse_client.close()
        logger.info("Sync Event Consumer encerrado")


if __name__ == "__main__":
    asyncio.run(main())
