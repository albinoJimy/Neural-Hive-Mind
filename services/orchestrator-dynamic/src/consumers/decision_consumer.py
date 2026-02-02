"""
Kafka consumer para tópico plans.consensus.
Consome decisões consolidadas e inicia workflows Temporal.

Suporta deserialização Avro (Confluent wire format) e JSON fallback.
Implementa deduplicação baseada em Redis para idempotência.
"""
import json
import io
import os
from typing import Optional

from aiokafka import AIOKafkaConsumer
from temporalio.client import Client
import structlog
from neural_hive_observability import trace_plan, get_tracer, instrument_kafka_consumer
from neural_hive_observability.context import extract_context_from_headers, set_baggage
from opentelemetry import trace

# Avro support
try:
    from confluent_kafka.schema_registry import SchemaRegistryClient
    import fastavro
    AVRO_AVAILABLE = True
except ImportError:
    AVRO_AVAILABLE = False

from src.workflows.orchestration_workflow import OrchestrationWorkflow

logger = structlog.get_logger()


def _deserialize_avro_or_json(raw_bytes: bytes, schema_registry_url: str = None) -> dict:
    """
    Deserialize message supporting both Avro (Confluent wire format) and JSON.

    Confluent wire format:
    - Byte 0: Magic byte (0x00)
    - Bytes 1-4: Schema ID (big-endian int)
    - Bytes 5+: Avro payload
    """
    # Log bytes brutos para debug (primeiros 100 bytes)
    logger.debug(
        "avro_deserialization_attempt",
        raw_bytes_hex=raw_bytes[:100].hex() if len(raw_bytes) >= 100 else raw_bytes.hex(),
        bytes_length=len(raw_bytes),
        first_bytes=list(raw_bytes[:20])
    )

    if len(raw_bytes) < 5:
        # Too short for Avro wire format, try JSON
        logger.debug("message_too_short_for_avro", trying_json=True)
        try:
            return json.loads(raw_bytes.decode('utf-8'))
        except json.JSONDecodeError as e:
            logger.error("json_deserialization_failed", error=str(e), raw_bytes_preview=raw_bytes[:100])
            raise ValueError(f"Failed to deserialize as JSON: {e}") from e

    magic_byte = raw_bytes[0]
    if magic_byte != 0:
        # Not Avro wire format, try JSON
        logger.debug("invalid_magic_byte", magic_byte=magic_byte, trying_json=True)
        try:
            return json.loads(raw_bytes.decode('utf-8'))
        except json.JSONDecodeError as e:
            logger.error("json_deserialization_failed", error=str(e), raw_bytes_preview=raw_bytes[:100])
            raise ValueError(f"Failed to deserialize as JSON: {e}") from e

    # Extract schema ID and Avro payload
    schema_id = int.from_bytes(raw_bytes[1:5], byteorder='big')
    avro_payload = raw_bytes[5:]

    logger.debug(
        "avro_wire_format_detected",
        schema_id=schema_id,
        payload_size=len(avro_payload),
        payload_hex=avro_payload[:50].hex() if len(avro_payload) >= 50 else avro_payload.hex()
    )

    if AVRO_AVAILABLE:
        try:
            client = SchemaRegistryClient({'url': schema_registry_url})
            schema = client.get_schema(schema_id)
            logger.debug("schema_retrieved", schema_id=schema_id, schema_schema_str=schema.schema_str[:200])
            writer_schema = fastavro.parse_schema(json.loads(schema.schema_str))
            reader = io.BytesIO(avro_payload)
            # schemaless_reader pode retornar um generator ou um dict diretamente
            avro_result = fastavro.schemaless_reader(reader, writer_schema)
            # Converter para dict se necessário (pode vir como dict ou como generator)
            result = dict(avro_result) if isinstance(avro_result, dict) or not isinstance(avro_result, dict) and hasattr(avro_result, '__iter__') else avro_result
            logger.info("avro_deserialization_success", schema_id=schema_id, result_type=type(result).__name__)
            return result
        except Exception as e:
            logger.error(
                "avro_deserialization_failed",
                schema_id=schema_id,
                error=str(e),
                error_type=type(e).__name__,
                payload_preview=avro_payload[:100].hex()
            )
            # Tentar JSON como fallback
            try:
                json_result = json.loads(avro_payload.decode('utf-8'))
                logger.warning("avro_failed_json_success", schema_id=schema_id)
                return json_result
            except (json.JSONDecodeError, UnicodeDecodeError) as json_err:
                logger.error(
                    "json_fallback_also_failed",
                    json_error=str(json_err),
                    avro_error=str(e)
                )
                raise ValueError(
                    f"Failed to deserialize Avro message: {e}. JSON fallback also failed: {json_err}"
                ) from e

    raise ValueError("Avro deserialization not available")


class DecisionConsumer:
    """Consumer Kafka para decisões consolidadas."""

    # TTL para deduplicação de decisões (24 horas)
    DEDUPLICATION_TTL_SECONDS = 86400
    # TTL para chave de processing (5 minutos - tempo máximo esperado de processamento)
    PROCESSING_TTL_SECONDS = 300

    def __init__(
        self,
        config,
        temporal_client,  # Client ou TemporalClientWrapper
        mongodb_client,
        redis_client=None,
        metrics=None,
        sasl_username_override: Optional[str] = None,
        sasl_password_override: Optional[str] = None
    ):
        """
        Inicializa o consumer.

        Args:
            config: Configurações da aplicação
            temporal_client: Cliente Temporal para iniciar workflows
            mongodb_client: Cliente MongoDB para buscar Cognitive Plans
            redis_client: Cliente Redis para deduplicação (opcional)
            metrics: Instância de OrchestratorMetrics para métricas compartilhadas
            sasl_username_override: Username SASL (ex: obtido do Vault)
            sasl_password_override: Password SASL (ex: obtido do Vault)
        """
        self.config = config
        self.temporal_client = temporal_client
        self.mongodb_client = mongodb_client
        self.redis_client = redis_client
        self.metrics = metrics
        self.consumer: Optional[AIOKafkaConsumer] = None
        self.running = False
        self.sasl_username = sasl_username_override if sasl_username_override is not None else config.kafka_sasl_username
        self.sasl_password = sasl_password_override if sasl_password_override is not None else config.kafka_sasl_password
        self.security_protocol = config.kafka_security_protocol
        self.sasl_mechanism = getattr(config, 'kafka_sasl_mechanism', 'PLAIN')
        self.schema_registry_url = os.getenv(
            'SCHEMA_REGISTRY_URL',
            'http://schema-registry.kafka.svc.cluster.local:8081/apis/ccompat/v6'
        )

    async def initialize(self):
        """Inicializa o consumer Kafka."""
        logger.info('Inicializando Kafka consumer', topic=self.config.kafka_consensus_topic)

        # Não usar value_deserializer - deserialização manual para suportar Avro e JSON
        consumer_config = {
            'bootstrap_servers': self.config.kafka_bootstrap_servers,
            'group_id': self.config.kafka_consumer_group_id,
            'auto_offset_reset': self.config.kafka_auto_offset_reset,
            'enable_auto_commit': self.config.kafka_enable_auto_commit,
            # Recebemos bytes crus para deserialização manual (Avro/JSON)
        }

        if self.security_protocol and self.security_protocol != 'PLAINTEXT':
            consumer_config.update({
                'security_protocol': self.security_protocol,
                'sasl_mechanism': self.sasl_mechanism,
                'sasl_plain_username': self.sasl_username,
                'sasl_plain_password': self.sasl_password,
            })
            logger.info(
                'Kafka consumer configurado com SASL',
                mechanism=self.sasl_mechanism,
                security_protocol=self.security_protocol
            )

        self.consumer = instrument_kafka_consumer(
            AIOKafkaConsumer(self.config.kafka_consensus_topic, **consumer_config)
        )
        logger.info("Kafka consumer instrumented with OpenTelemetry")

        await self.consumer.start()
        logger.info('Kafka consumer inicializado com sucesso')

    async def start(self):
        """Inicia loop de consumo de mensagens."""
        if not self.consumer:
            raise RuntimeError('Consumer não foi inicializado. Chame initialize() primeiro.')

        logger.info('Iniciando consumo de mensagens', topic=self.config.kafka_consensus_topic)
        self.running = True

        try:
            async for message in self.consumer:
                if not self.running:
                    break

                try:
                    await self._process_message(message)
                except Exception as e:
                    logger.error(
                        'Erro ao processar mensagem',
                        topic=message.topic,
                        partition=message.partition,
                        offset=message.offset,
                        error=str(e),
                        exc_info=True
                    )

        except Exception as e:
            logger.error('Erro no loop de consumo', error=str(e), exc_info=True)
            raise

    async def stop(self):
        """Para o consumer gracefully."""
        logger.info('Parando Kafka consumer')
        self.running = False

        if self.consumer:
            await self.consumer.stop()

        logger.info('Kafka consumer parado')

    async def _is_duplicate_decision(self, decision_id: str) -> bool:
        """
        Verificar se decisão já foi processada usando Redis (two-phase scheme).

        Implementa deduplicação em duas fases:
        1. Verifica se já existe chave 'processed' (processamento concluído anteriormente)
        2. Verifica se já existe chave 'processing' (processamento em andamento)
        3. Se nenhuma existe, marca como 'processing' com TTL curto

        Args:
            decision_id: ID da decisão consolidada

        Returns:
            True se duplicata (já processada ou em processamento), False caso contrário
        """
        if not self.redis_client:
            logger.warning('redis_client_not_available_skipping_deduplication')
            return False

        try:
            processed_key = f"decision:processed:{decision_id}"
            processing_key = f"decision:processing:{decision_id}"

            # Fase 1: Verificar se já foi processada com sucesso
            if await self.redis_client.exists(processed_key):
                logger.info(
                    'duplicate_decision_detected',
                    decision_id=decision_id,
                    message='Decisão já foi processada com sucesso, ignorando'
                )
                if self.metrics:
                    self.metrics.record_duplicate_detected('decision_consumer')
                return True

            # Fase 2: Tentar marcar como em processamento (SETNX)
            # Retorna True se chave foi criada (primeira vez), False se já existe
            is_new = await self.redis_client.set(
                processing_key,
                "1",
                ex=self.PROCESSING_TTL_SECONDS,
                nx=True
            )

            if not is_new:
                logger.info(
                    'decision_already_processing',
                    decision_id=decision_id,
                    message='Decisão já está em processamento por outro worker, ignorando'
                )
                if self.metrics:
                    self.metrics.record_duplicate_detected('decision_consumer')
                return True

            logger.debug('decision_marked_as_processing', decision_id=decision_id)
            return False

        except Exception as e:
            logger.error(
                'deduplication_check_failed',
                decision_id=decision_id,
                error=str(e),
                message='Continuando processamento sem deduplicação'
            )
            # Fail-open: continuar processamento em caso de erro no Redis
            return False

    async def _mark_decision_processed(self, decision_id: str) -> None:
        """
        Marca decisão como processada com sucesso e remove chave de processing.

        Args:
            decision_id: ID da decisão consolidada
        """
        if not self.redis_client:
            return

        try:
            processed_key = f"decision:processed:{decision_id}"
            processing_key = f"decision:processing:{decision_id}"

            # Marcar como processada com TTL longo
            await self.redis_client.set(
                processed_key,
                "1",
                ex=self.DEDUPLICATION_TTL_SECONDS
            )

            # Remover chave de processing
            await self.redis_client.delete(processing_key)

            logger.debug('decision_marked_as_processed', decision_id=decision_id)

        except Exception as e:
            logger.error(
                'mark_decision_processed_failed',
                decision_id=decision_id,
                error=str(e)
            )

    async def _clear_decision_processing(self, decision_id: str) -> None:
        """
        Limpa chave de processing para permitir reprocessamento após falha.

        Args:
            decision_id: ID da decisão consolidada
        """
        if not self.redis_client:
            return

        try:
            processing_key = f"decision:processing:{decision_id}"
            await self.redis_client.delete(processing_key)
            logger.debug('decision_processing_cleared', decision_id=decision_id)

        except Exception as e:
            logger.error(
                'clear_decision_processing_failed',
                decision_id=decision_id,
                error=str(e)
            )

    @trace_plan()
    async def _process_message(self, message):
        """
        Processa uma mensagem do Kafka.

        Args:
            message: Mensagem do Kafka contendo ConsolidatedDecision
        """
        # Preserve tracing headers as binary for W3C traceparent/baggage compatibility
        extract_context_from_headers(message.headers or [])

        business_headers = {}
        for key, value in (message.headers or []):
            if key in ('x-neural-hive-intent-id', 'x-neural-hive-plan-id', 'x-neural-hive-user-id'):
                if isinstance(value, bytes):
                    try:
                        business_headers[key] = value.decode('utf-8')
                    except Exception:
                        continue
                elif value is not None:
                    business_headers[key] = str(value)

        intent_id = business_headers.get('x-neural-hive-intent-id')
        plan_id = business_headers.get('x-neural-hive-plan-id')
        user_id = business_headers.get('x-neural-hive-user-id')

        if intent_id:
            set_baggage('intent_id', intent_id)
        if plan_id:
            set_baggage('plan_id', plan_id)
        if user_id:
            set_baggage('user_id', user_id)

        # Deserializar mensagem (suporta Avro e JSON)
        raw_value = message.value
        if isinstance(raw_value, bytes):
            try:
                consolidated_decision = _deserialize_avro_or_json(
                    raw_value,
                    self.schema_registry_url
                )
            except Exception as deser_err:
                logger.warning(
                    "avro_deserialization_failed_trying_json",
                    error=str(deser_err)
                )
                # Fallback para JSON
                consolidated_decision = json.loads(raw_value.decode('utf-8'))
        else:
            consolidated_decision = raw_value

        logger.info(
            'Mensagem recebida do Kafka',
            topic=message.topic,
            partition=message.partition,
            offset=message.offset,
            decision_id=consolidated_decision.get('decision_id'),
            plan_id=consolidated_decision.get('plan_id')
        )
        span = trace.get_current_span()
        decision_id = consolidated_decision.get('decision_id')
        span.set_attribute("neural.hive.decision.id", decision_id)
        span.set_attribute("neural.hive.plan.id", consolidated_decision.get('plan_id'))
        span.set_attribute("neural.hive.intent.id", consolidated_decision.get('intent_id'))
        span.set_attribute("messaging.kafka.topic", message.topic)
        span.set_attribute("messaging.kafka.partition", message.partition)
        span.set_attribute("messaging.kafka.offset", message.offset)

        # Verificar duplicata antes de processar
        if decision_id and await self._is_duplicate_decision(decision_id):
            span.set_attribute("neural.hive.duplicate", True)
            # Commit offset para não reprocessar
            await self.consumer.commit()
            logger.info(
                'duplicate_decision_skipped',
                decision_id=decision_id,
                offset=message.offset
            )
            return

        try:
            # Validar campos obrigatórios
            required_fields = ['decision_id', 'plan_id', 'final_decision']
            for field in required_fields:
                if field not in consolidated_decision:
                    logger.error(f'Campo obrigatório ausente: {field}')
                    return

            # Verificar se decisão foi aprovada
            final_decision = consolidated_decision.get('final_decision')
            if final_decision == 'reject':
                logger.warning('Decisão foi rejeitada, não gerando tickets', decision_id=consolidated_decision['decision_id'])
                await self.consumer.commit()
                return

            if consolidated_decision.get('requires_human_review', False):
                logger.info('Decisão requer revisão humana, aguardando aprovação', decision_id=consolidated_decision['decision_id'])
                await self.consumer.commit()
                return

            # Buscar Cognitive Plan associado no MongoDB
            plan_id = consolidated_decision['plan_id']
            cognitive_plan = await self.mongodb_client.get_cognitive_plan(plan_id)

            if not cognitive_plan:
                logger.error(
                    'Cognitive Plan não encontrado no ledger',
                    plan_id=plan_id,
                    decision_id=consolidated_decision['decision_id']
                )
                # Não commitar o offset para permitir retry
                # Este é um erro que pode ser temporário (plan ainda não persistido)
                return

            # Validar campos obrigatórios do Cognitive Plan
            required_plan_fields = ['tasks', 'execution_order', 'risk_band']
            for field in required_plan_fields:
                if field not in cognitive_plan:
                    logger.error(
                        'Cognitive Plan com campos obrigatórios ausentes',
                        plan_id=plan_id,
                        missing_field=field
                    )
                    # Commitar porque este é um erro permanente
                    await self.consumer.commit()
                    return

            logger.info(
                'Cognitive Plan recuperado com sucesso',
                plan_id=plan_id,
                task_count=len(cognitive_plan.get('tasks', [])),
                risk_band=cognitive_plan.get('risk_band')
            )

            # Iniciar workflow Temporal
            workflow_id = f'{self.config.temporal_workflow_id_prefix}{plan_id}'

            input_data = {
                'consolidated_decision': consolidated_decision,
                'cognitive_plan': cognitive_plan
            }

            logger.info('Iniciando workflow Temporal', workflow_id=workflow_id, plan_id=plan_id)

            await self.temporal_client.start_workflow(
                OrchestrationWorkflow.run,
                input_data,
                id=workflow_id,
                task_queue=self.config.temporal_task_queue
            )

            logger.info('Workflow Temporal iniciado com sucesso', workflow_id=workflow_id)

            # Commit manual do offset
            await self.consumer.commit()

            # Marcar decisão como processada com sucesso (two-phase scheme)
            if decision_id:
                await self._mark_decision_processed(decision_id)

            logger.info('Mensagem processada com sucesso', offset=message.offset)

        except Exception as e:
            logger.error(
                'Erro ao processar mensagem',
                error=str(e),
                decision_id=consolidated_decision.get('decision_id'),
                exc_info=True
            )
            # Limpar chave de processing para permitir retry (two-phase scheme)
            if decision_id:
                await self._clear_decision_processing(decision_id)
            # Não commitar offset para permitir retry
            raise
