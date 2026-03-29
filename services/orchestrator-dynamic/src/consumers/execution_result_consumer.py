"""
Consumer Kafka para execution.results - Fecha feedback loop de execução.

Processa resultados publicados pelos Worker Agents e envia signals
para workflows Temporal, permitindo que workflows continuem sem aguardar timeout.

Fluxo:
  Worker Agent → execution.results → Consumer → signal(ticket_completed) → Workflow Temporal
"""
import json
from typing import Optional, Dict, Any

import structlog
from aiokafka import AIOKafkaConsumer

logger = structlog.get_logger(__name__)


class ExecutionResultConsumer:
    """Consumer Kafka para execution.results"""

    TOPIC = "execution.results"
    WORKFLOW_CACHE_PREFIX = "workflow:by:ticket:"
    WORKFLOW_CACHE_TTL = 86400  # 24h

    def __init__(
        self,
        config,
        temporal_client,
        redis_client,
        metrics=None
    ):
        """
        Inicializa o consumer.

        Args:
            config: Configurações da aplicação
            temporal_client: Cliente Temporal para enviar signals
            redis_client: Cliente Redis para cache de workflow_id
            metrics: Instância de métricas (opcional)
        """
        self.config = config
        self.temporal_client = temporal_client
        self.redis_client = redis_client
        self.metrics = metrics
        self.consumer: Optional[AIOKafkaConsumer] = None
        self.running = False

    async def initialize(self):
        """Inicializa consumer Kafka."""
        logger.info(
            'execution_result_consumer_initializing',
            topic=self.TOPIC,
            group_id=getattr(self.config, 'execution_result_consumer_group', 'orchestrator-execution-results')
        )

        consumer_config = {
            'bootstrap_servers': self.config.kafka_bootstrap_servers,
            'group_id': getattr(self.config, 'execution_result_consumer_group', 'orchestrator-execution-results'),
            'auto_offset_reset': 'latest',
            'enable_auto_commit': False
        }

        # Configurar segurança se necessário
        security_protocol = getattr(self.config, 'kafka_security_protocol', 'PLAINTEXT')
        if security_protocol != 'PLAINTEXT':
            consumer_config['security_protocol'] = security_protocol
            consumer_config['sasl_mechanism'] = getattr(self.config, 'kafka_sasl_mechanism', 'PLAIN')
            consumer_config['sasl_plain_username'] = self.config.kafka_sasl_username
            consumer_config['sasl_plain_password'] = self.config.kafka_sasl_password

        self.consumer = AIOKafkaConsumer(self.TOPIC, **consumer_config)
        await self.consumer.start()

        logger.info('execution_result_consumer_initialized')

    async def start(self):
        """Loop de consumo de mensagens."""
        if not self.consumer:
            raise RuntimeError('Consumer não foi inicializado. Chame initialize() primeiro.')

        logger.info('execution_result_consumer_starting', topic=self.TOPIC)
        self.running = True

        try:
            async for message in self.consumer:
                if not self.running:
                    break

                try:
                    await self._process_result(message)
                except Exception as e:
                    logger.error(
                        'execution_result_processing_error',
                        topic=message.topic,
                        partition=message.partition,
                        offset=message.offset,
                        error=str(e),
                        exc_info=False
                    )
                    # Commit mesmo assim para não bloquear tópico
                    await self.consumer.commit()

        except Exception as e:
            logger.error('execution_result_consumer_loop_error', error=str(e), exc_info=True)
            raise
        finally:
            await self.stop()

    async def _process_result(self, message):
        """
        Processa ExecutionResult e envia signal para Temporal Workflow.

        Fluxo:
        1. Deserializar mensagem (JSON/Avro)
        2. Recuperar workflow_id (da mensagem ou cache Redis)
        3. Enviar signal ticket_completed para workflow
        4. Atualizar métricas e commit offset
        """
        try:
            # Deserializar mensagem
            result_data = self._deserialize(message)

            ticket_id = result_data.get('ticket_id')
            plan_id = result_data.get('plan_id')
            status = result_data.get('status')

            if not ticket_id:
                logger.warning('execution_result_missing_ticket_id', message_offset=message.offset)
                await self.consumer.commit()
                return

            # Recuperar workflow_id (da mensagem ou cache)
            workflow_id = result_data.get('workflow_id')
            if not workflow_id:
                workflow_id = await self._get_workflow_for_ticket(ticket_id, plan_id)

            if not workflow_id:
                logger.warning(
                    'workflow_id_not_found_for_result',
                    ticket_id=ticket_id,
                    plan_id=plan_id,
                    action='result_processed_but_no_signal_sent'
                )
                await self.consumer.commit()
                return

            # Enviar signal para Temporal
            await self._send_workflow_signal(
                workflow_id=workflow_id,
                ticket_id=ticket_id,
                result=result_data
            )

            # Commit offset após processamento bem-sucedido
            await self.consumer.commit()

            logger.info(
                'execution_result_processed',
                ticket_id=ticket_id,
                workflow_id=workflow_id,
                status=status,
                offset=message.offset
            )

            # Métricas
            if self.metrics:
                self.metrics.execution_results_processed_total.labels(status=status).inc()

        except Exception as e:
            logger.error(
                'execution_result_process_exception',
                ticket_id=result_data.get('ticket_id') if 'result_data' in locals() else 'unknown',
                error=str(e),
                exc_info=True
            )
            # Commit mesmo assim para não bloquear tópico
            try:
                await self.consumer.commit()
            except Exception:
                pass
            raise

    async def _get_workflow_for_ticket(
        self,
        ticket_id: str,
        plan_id: str
    ) -> Optional[str]:
        """
        Recupera workflow_id do cache Redis.

        Args:
            ticket_id: ID do ticket de execução
            plan_id: ID do plano (para logging)

        Returns:
            workflow_id se encontrado, None caso contrário
        """
        if not self.redis_client:
            logger.warning(
                'redis_client_unavailable_for_workflow_lookup',
                ticket_id=ticket_id,
                plan_id=plan_id
            )
            return None

        try:
            cache_key = f"{self.WORKFLOW_CACHE_PREFIX}{ticket_id}"
            workflow_id = await self.redis_client.get(cache_key)

            if workflow_id:
                logger.debug(
                    'workflow_id_found_in_cache',
                    ticket_id=ticket_id,
                    workflow_id=workflow_id
                )
                return workflow_id

            logger.debug(
                'workflow_id_not_in_cache',
                ticket_id=ticket_id,
                plan_id=plan_id
            )
            return None

        except Exception as e:
            logger.error(
                'workflow_cache_lookup_error',
                ticket_id=ticket_id,
                error=str(e)
            )
            return None

    async def _send_workflow_signal(
        self,
        workflow_id: str,
        ticket_id: str,
        result: Dict[str, Any]
    ):
        """
        Envia signal ticket_completed para workflow Temporal.

        Args:
            workflow_id: ID do workflow Temporal
            ticket_id: ID do ticket completado
            result: Resultado da execução
        """
        try:
            handle = self.temporal_client.get_workflow_handle(workflow_id)
            await handle.signal(
                "ticket_completed",  # Nome do signal definido no workflow
                ticket_id=ticket_id,
                result=result
            )
            logger.info(
                'workflow_signal_sent',
                workflow_id=workflow_id,
                ticket_id=ticket_id,
                status=result.get('status')
            )

            if self.metrics:
                self.metrics.workflow_signals_sent_total.inc()

        except Exception as e:
            logger.error(
                'workflow_signal_failed',
                workflow_id=workflow_id,
                ticket_id=ticket_id,
                error=str(e),
                exc_info=True
            )
            raise

    def _deserialize(self, message) -> Dict[str, Any]:
        """
        Deserializa mensagem Kafka (JSON com fallback).

        Args:
            message: Mensagem Kafka

        Returns:
            Dados deserializados
        """
        raw_value = message.value
        if isinstance(raw_value, bytes):
            try:
                return json.loads(raw_value.decode('utf-8'))
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                logger.error(
                    'execution_result_deserialization_failed',
                    error=str(e),
                    raw_bytes_preview=raw_value[:100].hex() if len(raw_value) >= 100 else raw_value.hex()
                )
                raise ValueError(f'Failed to deserialize execution result: {e}') from e
        return raw_value

    async def stop(self):
        """Para o consumer gracefulmente."""
        logger.info('execution_result_consumer_stopping')
        self.running = False

        if self.consumer:
            await self.consumer.stop()

        logger.info('execution_result_consumer_stopped')
