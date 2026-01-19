"""
Approval Processor - Serviço de processamento de respostas de aprovação

Responsável por processar decisões de aprovação do Approval Service,
atualizar o ledger e publicar planos aprovados para execução.
"""

import structlog
import time
from datetime import datetime
from typing import Dict, Optional, Any, Union

from src.clients.mongodb_client import MongoDBClient
from src.producers.plan_producer import KafkaPlanProducer
from src.producers.rejection_notifier import RejectionNotifier
from src.models.cognitive_plan import CognitivePlan, ApprovalStatus, PlanStatus
from src.observability.metrics import NeuralHiveMetrics

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
        rejection_notifier: Optional[RejectionNotifier] = None
    ):
        self.mongodb_client = mongodb_client
        self.plan_producer = plan_producer
        self.metrics = metrics
        self.rejection_notifier = rejection_notifier

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
        current_approval_status = ledger_entry.get('plan_data', {}).get('approval_status')
        if current_approval_status in ['approved', 'rejected']:
            logger.warning(
                'Plano já processado anteriormente - ignorando duplicata',
                plan_id=plan_id,
                current_status=current_approval_status,
                new_decision=decision
            )
            return

        # Calcular tempo desde request de aprovação
        plan_created_at = ledger_entry.get('timestamp')
        time_to_decision = None
        if plan_created_at:
            time_to_decision = (approved_at - plan_created_at).total_seconds()

        # Extrair informações de risco do plano original
        plan_data = ledger_entry.get('plan_data', {})
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
        Processa plano aprovado: atualiza ledger e publica para execução.
        """
        logger.info(
            'Processando plano aprovado',
            plan_id=plan_id,
            approved_by=approved_by
        )

        # Atualizar status no ledger
        updated = await self.mongodb_client.update_plan_approval_status(
            plan_id=plan_id,
            approval_status='approved',
            approved_by=approved_by,
            approved_at=approved_at
        )

        if not updated:
            logger.error(
                'Falha ao atualizar status de aprovação no ledger',
                plan_id=plan_id
            )
            self.metrics.increment_approval_ledger_error('update_failed')
            raise RuntimeError(f"Falha ao atualizar ledger para plan_id={plan_id}")

        # Reconstruir CognitivePlan para publicação
        plan_dict = cognitive_plan_dict or plan_data

        # Normalizar timestamps em milissegundos para datetime UTC
        # Campos de data podem vir em formato numérico (millis) de Avro/JSON
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

        # Publicar no tópico de execução
        await self.plan_producer.send_plan(cognitive_plan)

        logger.info(
            'Plano aprovado publicado para execução',
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
