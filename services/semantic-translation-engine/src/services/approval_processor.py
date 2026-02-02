"""
Approval Processor - Serviço de processamento de respostas de aprovação

Responsável por processar decisões de aprovação do Approval Service,
atualizar o ledger e publicar planos aprovados para execução.
"""

import logging
import structlog
import time
from datetime import datetime
from typing import Dict, Optional, Any, Union

from tenacity import retry, stop_after_attempt, wait_exponential, before_sleep_log, RetryError

from src.clients.mongodb_client import MongoDBClient
from src.producers.plan_producer import KafkaPlanProducer
from src.producers.rejection_notifier import RejectionNotifier
from src.producers.approval_dlq_producer import ApprovalDLQProducer
from src.models.cognitive_plan import CognitivePlan, ApprovalStatus, PlanStatus
from src.models.approval_dlq import ApprovalDLQEntry
from src.observability.metrics import NeuralHiveMetrics
from src.sagas.approval_saga import ApprovalSaga

logger = structlog.get_logger()


def normalize_timestamp_millis(value: Any) -> Optional[datetime]:
    """
    Normaliza valor de timestamp para datetime UTC.

    Converte timestamps em milissegundos (comum em formatos Avro/JSON)
    para objetos datetime. Preserva objetos datetime existentes.

    Args:
        value: Valor a ser normalizado (int em millis, datetime, ou None)

    Returns:
        datetime UTC ou None
    """
    if value is None:
        return None

    if isinstance(value, datetime):
        return value

    if isinstance(value, (int, float)):
        # Timestamp em milissegundos - converter para datetime UTC
        try:
            return datetime.utcfromtimestamp(value / 1000)
        except (ValueError, OSError) as e:
            logger.warning(
                'Falha ao converter timestamp em millis para datetime',
                value=value,
                error=str(e)
            )
            return None

    if isinstance(value, str):
        # Tentar parsear ISO format
        try:
            return datetime.fromisoformat(value.replace('Z', '+00:00'))
        except ValueError:
            pass
        # Tentar como timestamp numérico em string
        try:
            return datetime.utcfromtimestamp(float(value) / 1000)
        except (ValueError, OSError):
            pass
        logger.warning(
            'Formato de timestamp não reconhecido',
            value=value
        )
        return None

    logger.warning(
        'Tipo de timestamp não suportado',
        value=value,
        value_type=type(value).__name__
    )
    return None


class ApprovalProcessor:
    """
    Processador de respostas de aprovação de planos cognitivos.

    Responsabilidades:
    - Validar mensagem de aprovação
    - Atualizar status do plano no MongoDB ledger
    - Publicar plano aprovado no tópico de execução
    - Registrar métricas de aprovação
    """

    def __init__(
        self,
        mongodb_client: MongoDBClient,
        plan_producer: KafkaPlanProducer,
        metrics: NeuralHiveMetrics,
        rejection_notifier: Optional[RejectionNotifier] = None,
        dlq_producer: Optional[ApprovalDLQProducer] = None
    ):
        self.mongodb_client = mongodb_client
        self.plan_producer = plan_producer
        self.metrics = metrics
        self.rejection_notifier = rejection_notifier
        self.dlq_producer = dlq_producer
        self._logger = logging.getLogger(__name__)

        # Inicializar saga para transações distribuídas
        self.approval_saga = ApprovalSaga(
            mongodb_client=mongodb_client,
            plan_producer=plan_producer,
            dlq_producer=dlq_producer,
            metrics=metrics
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        before_sleep=before_sleep_log(logging.getLogger(__name__), logging.WARNING)
    )
    async def _publish_approved_plan_with_retry(
        self,
        cognitive_plan: CognitivePlan,
        plan_id: str,
        intent_id: str
    ) -> None:
        """
        Publica plano aprovado no Kafka com retry para falhas transientes.

        Configurado para 3 tentativas com backoff exponencial (2-10 segundos).
        Loga automaticamente warnings antes de cada retry via before_sleep_log.

        Args:
            cognitive_plan: Plano cognitivo a ser publicado
            plan_id: ID do plano para logging
            intent_id: ID do intent para logging
        """
        logger.info(
            'Tentando republicar plano aprovado',
            plan_id=plan_id,
            intent_id=intent_id
        )

        await self.plan_producer.send_plan(cognitive_plan)

        logger.info(
            'Plano republicado com sucesso',
            plan_id=plan_id,
            intent_id=intent_id
        )

    async def _send_to_dlq(
        self,
        plan_id: str,
        intent_id: str,
        failure_reason: str,
        approval_response: Dict,
        trace_context: Dict,
        approved_by: Optional[str] = None,
        risk_band: Optional[str] = None,
        is_destructive: Optional[bool] = None
    ) -> None:
        """
        Envia plano aprovado que falhou na republicação para Dead Letter Queue.

        Args:
            plan_id: ID do plano
            intent_id: ID do intent
            failure_reason: Razão da falha
            approval_response: Resposta de aprovação original
            trace_context: Contexto de rastreamento
            approved_by: Quem aprovou
            risk_band: Risk band do plano
            is_destructive: Se o plano é destrutivo
        """
        if not self.dlq_producer:
            logger.warning(
                'DLQ producer não configurado - mensagem não será enviada para DLQ',
                plan_id=plan_id,
                intent_id=intent_id
            )
            return

        try:
            dlq_entry = ApprovalDLQEntry(
                plan_id=plan_id,
                intent_id=intent_id,
                failure_reason=failure_reason,
                retry_count=3,  # Sempre 3 após esgotamento dos retries
                original_approval_response=approval_response,
                correlation_id=trace_context.get('correlation_id'),
                trace_id=trace_context.get('trace_id'),
                span_id=trace_context.get('span_id'),
                approved_by=approved_by,
                risk_band=risk_band,
                is_destructive=is_destructive
            )

            await self.dlq_producer.send_dlq_entry(dlq_entry)

            logger.info(
                'Plano aprovado enviado para DLQ após falha na republicação',
                plan_id=plan_id,
                intent_id=intent_id,
                failure_reason=failure_reason,
                correlation_id=trace_context.get('correlation_id')
            )

            # Registrar métrica
            self.metrics.increment_approval_dlq_messages(
                reason='republish_failed',
                risk_band=risk_band or 'unknown',
                is_destructive=is_destructive or False
            )

        except Exception as e:
            logger.error(
                'Falha ao enviar plano para DLQ de aprovação',
                plan_id=plan_id,
                intent_id=intent_id,
                error=str(e)
            )
            # Não propagar erro - DLQ é best-effort

    async def process_approval_response(
        self,
        approval_response: Dict,
        trace_context: Dict
    ) -> None:
        """
        Processa resposta de aprovação e publica plano se aprovado.

        Args:
            approval_response: Dict com plan_id, decision, approved_by, etc.
            trace_context: Contexto de rastreamento
        """
        start_time = time.time()

        plan_id = approval_response.get('plan_id')
        intent_id = approval_response.get('intent_id')
        decision = approval_response.get('decision')
        approved_by = approval_response.get('approved_by')
        approved_at_ts = approval_response.get('approved_at')
        rejection_reason = approval_response.get('rejection_reason')
        cognitive_plan_dict = approval_response.get('cognitive_plan')

        logger.info(
            'Processando resposta de aprovação',
            plan_id=plan_id,
            intent_id=intent_id,
            decision=decision,
            approved_by=approved_by,
            correlation_id=trace_context.get('correlation_id')
        )

        # Validar campos obrigatórios
        if not plan_id or not decision:
            logger.error(
                'Resposta de aprovação inválida: campos obrigatórios ausentes',
                plan_id=plan_id,
                decision=decision
            )
            return

        # Converter timestamp
        approved_at = datetime.utcfromtimestamp(approved_at_ts / 1000) if approved_at_ts else datetime.utcnow()

        # Buscar plano no ledger
        ledger_entry = await self.mongodb_client.query_ledger(plan_id)

        if not ledger_entry:
            logger.error(
                'Plano não encontrado no ledger - resposta de aprovação ignorada',
                plan_id=plan_id
            )
            # Registrar métrica de erro
            self.metrics.increment_approval_ledger_error('plan_not_found')
            return

        # Verificar se plano já foi processado (idempotência)
        # Regras:
        # - Se rejected: sempre ignorar (decisão final)
        # - Se approved E saga_state='completed': ignorar (saga finalizou com sucesso)
        # - Se approved mas saga_state é missing/executing/compensated/failed: prosseguir
        #   (permite reprocessamento após crash ou falha)
        plan_data = ledger_entry.get('plan_data', {})
        current_approval_status = plan_data.get('approval_status')
        current_saga_state = plan_data.get('saga_state')

        if current_approval_status == 'rejected':
            logger.warning(
                'Plano já foi rejeitado anteriormente - ignorando duplicata',
                plan_id=plan_id,
                current_status=current_approval_status,
                new_decision=decision
            )
            return

        if current_approval_status == 'approved' and current_saga_state == 'completed':
            logger.warning(
                'Plano já foi aprovado e saga completada - ignorando duplicata',
                plan_id=plan_id,
                current_status=current_approval_status,
                saga_state=current_saga_state,
                new_decision=decision
            )
            return

        # Se approved mas saga não completou (missing, executing, compensated, failed),
        # prosseguir para reprocessamento - permite recuperação após crash
        if current_approval_status == 'approved' and current_saga_state in [None, 'executing', 'compensated', 'failed']:
            logger.info(
                'Reprocessando plano aprovado com saga incompleta',
                plan_id=plan_id,
                current_status=current_approval_status,
                saga_state=current_saga_state,
                new_decision=decision
            )

        # Calcular tempo desde request de aprovação
        plan_created_at = ledger_entry.get('timestamp')
        time_to_decision = None
        if plan_created_at:
            time_to_decision = (approved_at - plan_created_at).total_seconds()

        # Extrair informações de risco do plano original (plan_data já definido acima)
        risk_band = plan_data.get('risk_band', 'unknown')
        is_destructive = plan_data.get('is_destructive', False)

        if decision == 'approved':
            await self._process_approved_plan(
                plan_id=plan_id,
                intent_id=intent_id,
                approved_by=approved_by,
                approved_at=approved_at,
                cognitive_plan_dict=cognitive_plan_dict,
                plan_data=plan_data,
                trace_context=trace_context,
                risk_band=risk_band,
                is_destructive=is_destructive,
                time_to_decision=time_to_decision
            )
        else:
            await self._process_rejected_plan(
                plan_id=plan_id,
                intent_id=intent_id,
                approved_by=approved_by,
                approved_at=approved_at,
                rejection_reason=rejection_reason,
                risk_band=risk_band,
                is_destructive=is_destructive,
                time_to_decision=time_to_decision,
                correlation_id=trace_context.get('correlation_id')
            )

        # Registrar duração do processamento
        processing_duration = time.time() - start_time
        self.metrics.observe_approval_processing_duration(processing_duration)

        logger.info(
            'Resposta de aprovação processada',
            plan_id=plan_id,
            decision=decision,
            processing_duration_ms=round(processing_duration * 1000, 2)
        )

    async def _process_approved_plan(
        self,
        plan_id: str,
        intent_id: str,
        approved_by: str,
        approved_at: datetime,
        cognitive_plan_dict: Optional[Dict],
        plan_data: Dict,
        trace_context: Dict,
        risk_band: str,
        is_destructive: bool,
        time_to_decision: Optional[float]
    ) -> None:
        """
        Processa plano aprovado usando Saga Pattern para consistência transacional.

        A saga garante que se a publicação no Kafka falhar após retries,
        o status do plano no MongoDB será revertido para 'pending'.
        """
        logger.info(
            'Processando plano aprovado via saga',
            plan_id=plan_id,
            approved_by=approved_by
        )

        # Reconstruir CognitivePlan para publicação
        plan_dict = cognitive_plan_dict or plan_data

        # Normalizar timestamps em milissegundos para datetime UTC
        if 'created_at' in plan_dict:
            plan_dict['created_at'] = normalize_timestamp_millis(plan_dict['created_at']) or datetime.utcnow()
        if 'valid_until' in plan_dict:
            plan_dict['valid_until'] = normalize_timestamp_millis(plan_dict['valid_until'])

        # Atualizar campos de aprovação
        plan_dict['approval_status'] = 'approved'
        plan_dict['approved_by'] = approved_by
        plan_dict['approved_at'] = approved_at
        plan_dict['status'] = 'approved'

        # Adicionar trace context
        if trace_context.get('correlation_id'):
            plan_dict['correlation_id'] = trace_context['correlation_id']
        if trace_context.get('trace_id'):
            plan_dict['trace_id'] = trace_context['trace_id']
        if trace_context.get('span_id'):
            plan_dict['span_id'] = trace_context['span_id']

        try:
            cognitive_plan = CognitivePlan(**plan_dict)
        except Exception as e:
            logger.error(
                'Falha ao reconstruir CognitivePlan',
                plan_id=plan_id,
                error=str(e)
            )
            self.metrics.increment_approval_ledger_error('plan_reconstruction_failed')
            raise

        # Executar saga de aprovação (atualiza ledger + publica Kafka com compensação)
        await self.approval_saga.execute(
            plan_id=plan_id,
            intent_id=intent_id,
            approved_by=approved_by,
            approved_at=approved_at,
            cognitive_plan=cognitive_plan,
            trace_context=trace_context,
            risk_band=risk_band,
            is_destructive=is_destructive
        )

        logger.info(
            'Plano aprovado publicado para execução via saga',
            plan_id=plan_id,
            intent_id=intent_id,
            approved_by=approved_by,
            risk_band=risk_band
        )

        # Registrar métricas
        self.metrics.record_approval_decision(
            decision='approved',
            risk_band=risk_band,
            is_destructive=is_destructive
        )

        if time_to_decision is not None:
            self.metrics.observe_approval_time_to_decision(
                duration=time_to_decision,
                decision='approved'
            )

    async def _process_rejected_plan(
        self,
        plan_id: str,
        intent_id: str,
        approved_by: str,
        approved_at: datetime,
        rejection_reason: Optional[str],
        risk_band: str,
        is_destructive: bool,
        time_to_decision: Optional[float],
        correlation_id: Optional[str] = None
    ) -> None:
        """
        Processa plano rejeitado: atualiza ledger com motivo da rejeição
        e notifica consumidores downstream.
        """
        logger.warning(
            'Processando plano rejeitado',
            plan_id=plan_id,
            rejected_by=approved_by,
            rejection_reason=rejection_reason
        )

        # Atualizar status no ledger
        updated = await self.mongodb_client.update_plan_approval_status(
            plan_id=plan_id,
            approval_status='rejected',
            approved_by=approved_by,
            approved_at=approved_at,
            rejection_reason=rejection_reason
        )

        if not updated:
            logger.error(
                'Falha ao atualizar status de rejeição no ledger',
                plan_id=plan_id
            )
            self.metrics.increment_approval_ledger_error('update_failed')
            raise RuntimeError(f"Falha ao atualizar ledger para plan_id={plan_id}")

        logger.info(
            'Plano rejeitado registrado no ledger',
            plan_id=plan_id,
            intent_id=intent_id,
            rejected_by=approved_by,
            rejection_reason=rejection_reason,
            risk_band=risk_band
        )

        # Notificar consumidores downstream sobre a rejeição
        if self.rejection_notifier:
            try:
                await self.rejection_notifier.notify_rejection(
                    plan_id=plan_id,
                    intent_id=intent_id,
                    rejection_reason=rejection_reason,
                    correlation_id=correlation_id,
                    rejected_by=approved_by,
                    risk_band=risk_band
                )
                logger.info(
                    'Notificação de rejeição enviada',
                    plan_id=plan_id,
                    intent_id=intent_id,
                    correlation_id=correlation_id
                )
            except Exception as e:
                # Log erro mas não falha o processamento
                # Ledger já foi atualizado com sucesso
                logger.error(
                    'Falha ao enviar notificação de rejeição',
                    plan_id=plan_id,
                    error=str(e)
                )
                self.metrics.increment_approval_ledger_error('notification_failed')
        else:
            logger.debug(
                'Rejection notifier não configurado - notificação de rejeição não enviada',
                plan_id=plan_id
            )

        # Registrar métricas
        self.metrics.record_approval_decision(
            decision='rejected',
            risk_band=risk_band,
            is_destructive=is_destructive
        )

        if time_to_decision is not None:
            self.metrics.observe_approval_time_to_decision(
                duration=time_to_decision,
                decision='rejected'
            )
