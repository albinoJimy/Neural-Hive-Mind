"""
DLQ Reprocessor Service - Lógica de reprocessamento para Dead Letter Queue

Serviço dedicado para reprocessar entradas da DLQ de aprovações,
republicando-as no tópico de respostas de aprovação para serem
processadas novamente pelo ApprovalProcessor.

Quando o reprocessamento falha, o serviço republica a entrada na DLQ
com retry_count incrementado para controle de max retries.
"""

import json
import structlog
from datetime import datetime
from typing import Dict, Any, Optional, TYPE_CHECKING

from confluent_kafka import Producer

from src.config.settings import Settings
from src.models.approval_dlq import ApprovalDLQEntry
from src.clients.mongodb_client import MongoDBClient
from src.observability.metrics import NeuralHiveMetrics

if TYPE_CHECKING:
    from src.producers.approval_dlq_producer import ApprovalDLQProducer

logger = structlog.get_logger()


class DLQReprocessor:
    """
    Serviço para reprocessamento de entradas da Dead Letter Queue.

    Responsável por:
    1. Verificar se retry_count excedeu o limite
    2. Republicar resposta de aprovação original no Kafka
    3. Quando falhar, republica na DLQ com retry_count incrementado
    4. Atualizar MongoDB para falhas permanentes
    5. Emitir métricas de reprocessamento
    """

    def __init__(
        self,
        mongodb_client: MongoDBClient,
        metrics: NeuralHiveMetrics,
        settings: Settings,
        dlq_producer: Optional['ApprovalDLQProducer'] = None
    ):
        self.mongodb_client = mongodb_client
        self.metrics = metrics
        self.settings = settings
        self.dlq_producer = dlq_producer
        self._producer: Optional[Producer] = None
        self._topic = settings.kafka_approval_responses_topic

    async def initialize(self):
        """Inicializa producer Kafka para republicação"""
        producer_config = {
            'bootstrap.servers': self.settings.kafka_bootstrap_servers,
            'enable.idempotence': True,
            'acks': 'all',
            'max.in.flight.requests.per.connection': 5,
        }

        # Configurações de segurança
        if self.settings.kafka_security_protocol != 'PLAINTEXT':
            producer_config.update({
                'security.protocol': self.settings.kafka_security_protocol,
                'sasl.mechanism': self.settings.kafka_sasl_mechanism,
                'sasl.username': self.settings.kafka_sasl_username,
                'sasl.password': self.settings.kafka_sasl_password,
            })

        self._producer = Producer(producer_config)
        logger.info(
            'DLQ Reprocessor producer inicializado',
            topic=self._topic
        )

    async def reprocess_dlq_entry(
        self,
        dlq_entry: ApprovalDLQEntry,
        trace_context: Dict[str, Any]
    ) -> bool:
        """
        Reprocessa uma entrada da DLQ.

        Args:
            dlq_entry: Entrada DLQ a ser reprocessada
            trace_context: Contexto de rastreamento (correlation_id, trace_id, span_id)

        Returns:
            True se reprocessamento bem-sucedido, falha permanente tratada,
                 ou falha transiente republicada na DLQ com retry_count incrementado
            False APENAS se não foi possível tratar a falha (sem DLQ producer)
        """
        correlation_id = trace_context.get('correlation_id') or dlq_entry.correlation_id
        risk_band = dlq_entry.risk_band or 'unknown'

        logger.info(
            'Iniciando reprocessamento de entrada DLQ',
            plan_id=dlq_entry.plan_id,
            intent_id=dlq_entry.intent_id,
            retry_count=dlq_entry.retry_count,
            max_retry_count=self.settings.dlq_max_retry_count,
            correlation_id=correlation_id
        )

        # Verificar se excedeu limite de retries
        if dlq_entry.retry_count > self.settings.dlq_max_retry_count:
            return await self._handle_permanent_failure(dlq_entry, trace_context, risk_band)

        # Tentar republicar no tópico de approval-responses
        try:
            await self._republish_approval_response(dlq_entry, trace_context)

            # Registrar métrica de sucesso
            self.metrics.increment_dlq_reprocessed('success', risk_band)

            logger.info(
                'Entrada DLQ republicada com sucesso',
                plan_id=dlq_entry.plan_id,
                intent_id=dlq_entry.intent_id,
                retry_count=dlq_entry.retry_count,
                correlation_id=correlation_id
            )

            return True

        except Exception as e:
            # Registrar métrica de falha
            error_type = type(e).__name__
            self.metrics.increment_dlq_reprocess_failure(error_type, risk_band)

            logger.error(
                'Falha ao republicar entrada DLQ',
                plan_id=dlq_entry.plan_id,
                intent_id=dlq_entry.intent_id,
                retry_count=dlq_entry.retry_count,
                error=str(e),
                error_type=error_type,
                correlation_id=correlation_id
            )

            # Incrementar retry_count e republicar na DLQ para controle de max retries
            return await self._handle_reprocess_failure(
                dlq_entry=dlq_entry,
                trace_context=trace_context,
                risk_band=risk_band,
                failure_reason=str(e)
            )

    async def _handle_reprocess_failure(
        self,
        dlq_entry: ApprovalDLQEntry,
        trace_context: Dict[str, Any],
        risk_band: str,
        failure_reason: str
    ) -> bool:
        """
        Trata falha no reprocessamento incrementando retry_count e republicando na DLQ.

        Se o novo retry_count exceder o limite, trata como falha permanente.
        Se não houver DLQ producer configurado, retorna False para retry local.

        Args:
            dlq_entry: Entrada DLQ original
            trace_context: Contexto de rastreamento
            risk_band: Faixa de risco
            failure_reason: Motivo da falha

        Returns:
            True se tratado (republished ou permanent failure)
            False se não foi possível tratar (sem DLQ producer)
        """
        correlation_id = trace_context.get('correlation_id') or dlq_entry.correlation_id
        new_retry_count = dlq_entry.retry_count + 1

        logger.info(
            'Tratando falha de reprocessamento DLQ',
            plan_id=dlq_entry.plan_id,
            old_retry_count=dlq_entry.retry_count,
            new_retry_count=new_retry_count,
            max_retry_count=self.settings.dlq_max_retry_count,
            correlation_id=correlation_id
        )

        # Verificar se novo retry_count excede limite
        if new_retry_count > self.settings.dlq_max_retry_count:
            logger.warning(
                'Retry count excedeu limite após falha de reprocessamento',
                plan_id=dlq_entry.plan_id,
                new_retry_count=new_retry_count,
                max_retry_count=self.settings.dlq_max_retry_count
            )
            # Criar entrada com retry_count atualizado para permanent failure
            updated_entry = ApprovalDLQEntry(
                plan_id=dlq_entry.plan_id,
                intent_id=dlq_entry.intent_id,
                failure_reason=f"[REPROCESS_FAILED] {failure_reason}",
                retry_count=new_retry_count,
                original_approval_response=dlq_entry.original_approval_response,
                failed_at=datetime.utcnow(),
                correlation_id=dlq_entry.correlation_id,
                trace_id=dlq_entry.trace_id,
                span_id=dlq_entry.span_id,
                approved_by=dlq_entry.approved_by,
                risk_band=dlq_entry.risk_band,
                is_destructive=dlq_entry.is_destructive
            )
            return await self._handle_permanent_failure(updated_entry, trace_context, risk_band)

        # Se não houver DLQ producer, retornar False para retry sem commit
        if not self.dlq_producer:
            logger.warning(
                'DLQ producer não configurado - mensagem será retentada localmente sem incremento de retry_count',
                plan_id=dlq_entry.plan_id,
                retry_count=dlq_entry.retry_count
            )
            return False

        # Republicar na DLQ com retry_count incrementado
        try:
            updated_entry = ApprovalDLQEntry(
                plan_id=dlq_entry.plan_id,
                intent_id=dlq_entry.intent_id,
                failure_reason=f"[REPROCESS_FAILED] {failure_reason}",
                retry_count=new_retry_count,
                original_approval_response=dlq_entry.original_approval_response,
                failed_at=datetime.utcnow(),
                correlation_id=dlq_entry.correlation_id,
                trace_id=dlq_entry.trace_id,
                span_id=dlq_entry.span_id,
                approved_by=dlq_entry.approved_by,
                risk_band=dlq_entry.risk_band,
                is_destructive=dlq_entry.is_destructive
            )

            await self.dlq_producer.send_dlq_entry(updated_entry)

            logger.info(
                'Entrada DLQ republicada com retry_count incrementado',
                plan_id=dlq_entry.plan_id,
                old_retry_count=dlq_entry.retry_count,
                new_retry_count=new_retry_count,
                correlation_id=correlation_id
            )

            # Retornar True para que consumer commite o offset da entrada antiga
            return True

        except Exception as e:
            logger.error(
                'Falha ao republicar entrada na DLQ com retry_count incrementado',
                plan_id=dlq_entry.plan_id,
                error=str(e)
            )
            # Se falhar ao republicar na DLQ, retornar False para retry sem commit
            return False

    async def _republish_approval_response(
        self,
        dlq_entry: ApprovalDLQEntry,
        trace_context: Dict[str, Any]
    ) -> None:
        """
        Republica a resposta de aprovação original no tópico de approval-responses.

        Args:
            dlq_entry: Entrada DLQ contendo original_approval_response
            trace_context: Contexto de rastreamento

        Raises:
            Exception: Se falha na publicação Kafka
        """
        original_response = dlq_entry.original_approval_response

        # Validar estrutura da resposta original
        required_fields = ['plan_id', 'intent_id', 'decision']
        for field in required_fields:
            if field not in original_response:
                raise ValueError(
                    f"Campo obrigatório ausente em original_approval_response: {field}"
                )

        # Incrementar retry_count para próxima tentativa
        original_response['dlq_retry_count'] = dlq_entry.retry_count + 1
        original_response['dlq_reprocessed_at'] = int(datetime.utcnow().timestamp() * 1000)

        # Preparar headers
        headers = [
            ('plan-id', dlq_entry.plan_id.encode('utf-8')),
            ('intent-id', dlq_entry.intent_id.encode('utf-8')),
            ('content-type', b'application/json'),
            ('dlq-reprocessed', b'true'),
            ('dlq-retry-count', str(dlq_entry.retry_count + 1).encode('utf-8')),
        ]

        if trace_context.get('correlation_id'):
            headers.append(('correlation-id', trace_context['correlation_id'].encode('utf-8')))
        if trace_context.get('trace_id'):
            headers.append(('trace-id', trace_context['trace_id'].encode('utf-8')))
        if trace_context.get('span_id'):
            headers.append(('span-id', trace_context['span_id'].encode('utf-8')))

        # Serializar resposta
        value = json.dumps(original_response, default=str).encode('utf-8')
        key = dlq_entry.plan_id.encode('utf-8')

        # Publicar mensagem
        self._producer.produce(
            topic=self._topic,
            key=key,
            value=value,
            headers=headers,
            on_delivery=self._delivery_callback
        )
        self._producer.flush()

        logger.debug(
            'Resposta de aprovação republicada para reprocessamento',
            plan_id=dlq_entry.plan_id,
            intent_id=dlq_entry.intent_id,
            decision=original_response.get('decision'),
            dlq_retry_count=original_response['dlq_retry_count'],
            topic=self._topic
        )

    def _delivery_callback(self, err, msg):
        """Callback de entrega de mensagens"""
        if err:
            logger.error(
                'Falha na entrega da republicação DLQ',
                error=str(err),
                topic=msg.topic()
            )
        else:
            logger.debug(
                'Republicação DLQ entregue',
                topic=msg.topic(),
                partition=msg.partition(),
                offset=msg.offset()
            )

    async def _handle_permanent_failure(
        self,
        dlq_entry: ApprovalDLQEntry,
        trace_context: Dict[str, Any],
        risk_band: str
    ) -> bool:
        """
        Trata falha permanente quando retry_count excede o limite.

        Args:
            dlq_entry: Entrada DLQ que excedeu limite
            trace_context: Contexto de rastreamento
            risk_band: Faixa de risco do plano

        Returns:
            True para commitar offset (falha tratada)
        """
        correlation_id = trace_context.get('correlation_id') or dlq_entry.correlation_id

        logger.warning(
            'Entrada DLQ excedeu limite de retries - marcando como permanentemente falhada',
            plan_id=dlq_entry.plan_id,
            intent_id=dlq_entry.intent_id,
            retry_count=dlq_entry.retry_count,
            max_retry_count=self.settings.dlq_max_retry_count,
            correlation_id=correlation_id
        )

        # Registrar métrica de falha permanente
        self.metrics.increment_dlq_permanently_failed(risk_band)

        # Atualizar MongoDB com status de falha permanente
        try:
            await self.mongodb_client.update_plan_dlq_status(
                plan_id=dlq_entry.plan_id,
                status='permanently_failed',
                failure_reason=f"Excedeu máximo de {self.settings.dlq_max_retry_count} tentativas de reprocessamento DLQ",
                retry_count=dlq_entry.retry_count,
                last_failure_at=datetime.utcnow()
            )

            logger.info(
                'Status de falha permanente registrado no MongoDB',
                plan_id=dlq_entry.plan_id,
                intent_id=dlq_entry.intent_id
            )

        except Exception as e:
            logger.error(
                'Falha ao atualizar MongoDB com status de falha permanente',
                plan_id=dlq_entry.plan_id,
                error=str(e)
            )
            # Não propaga erro - falha permanente já está logada

        return True  # Commita offset para não reprocessar indefinidamente

    async def close(self):
        """Fecha producer gracefully"""
        if self._producer:
            self._producer.flush()
            logger.info('DLQ Reprocessor producer fechado')
