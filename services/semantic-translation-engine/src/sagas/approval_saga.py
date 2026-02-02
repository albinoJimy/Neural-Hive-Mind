"""
Approval Saga - Saga Pattern para aprovação de planos cognitivos

Implementa transação distribuída com compensação para garantir consistência
entre MongoDB ledger e Kafka durante o fluxo de aprovação.

Fluxo de Execução:
1. Atualiza ledger MongoDB com saga_state='executing'
2. Tenta publicar plano no Kafka (com retry)
3. Se sucesso: atualiza saga_state='completed'
4. Se falha: executa compensação (reverte para 'pending')

Diagrama de Sequência:
```mermaid
sequenceDiagram
    participant AP as ApprovalProcessor
    participant Saga as ApprovalSaga
    participant Mongo as MongoDB
    participant Kafka as Kafka Producer
    participant DLQ as DLQ Producer

    AP->>Saga: execute(plan, approved_by, ...)
    Saga->>Mongo: update(saga_state='executing')
    Mongo-->>Saga: success
    Saga->>Kafka: publish_with_retry(plan)
    alt Kafka Success
        Kafka-->>Saga: success
        Saga->>Mongo: update(saga_state='completed')
        Saga-->>AP: success
    else Kafka Failure (after retries)
        Kafka-->>Saga: RetryError
        Saga->>Saga: compensate()
        Saga->>Mongo: revert(approval_status='pending', saga_state='compensated')
        Saga->>DLQ: send(plan, reason='compensation_executed')
        Saga-->>AP: raise exception
    end
```
"""

import logging
import time
import structlog
from datetime import datetime
from typing import Dict, Optional, Any

from tenacity import retry, stop_after_attempt, wait_exponential, before_sleep_log, RetryError

from src.clients.mongodb_client import MongoDBClient
from src.producers.plan_producer import KafkaPlanProducer
from src.producers.approval_dlq_producer import ApprovalDLQProducer
from src.models.cognitive_plan import CognitivePlan
from src.models.approval_dlq import ApprovalDLQEntry
from src.observability.metrics import NeuralHiveMetrics

logger = structlog.get_logger()


class SagaState:
    """Estados possíveis da saga de aprovação"""
    EXECUTING = 'executing'
    COMPLETED = 'completed'
    COMPENSATED = 'compensated'
    FAILED = 'failed'


class ApprovalSaga:
    """
    Saga para aprovação de planos cognitivos com compensação transacional.

    Garante consistência eventual entre MongoDB e Kafka através do padrão Saga.
    Se a publicação no Kafka falhar após retries, a saga reverte o status
    do plano no MongoDB de 'approved' para 'pending'.

    Attributes:
        mongodb_client: Cliente MongoDB para operações no ledger
        plan_producer: Producer Kafka para publicação de planos
        dlq_producer: Producer para Dead Letter Queue
        metrics: Métricas Prometheus
    """

    def __init__(
        self,
        mongodb_client: MongoDBClient,
        plan_producer: KafkaPlanProducer,
        dlq_producer: Optional[ApprovalDLQProducer],
        metrics: NeuralHiveMetrics
    ):
        self.mongodb_client = mongodb_client
        self.plan_producer = plan_producer
        self.dlq_producer = dlq_producer
        self.metrics = metrics
        self._logger = logging.getLogger(__name__)

    async def execute(
        self,
        plan_id: str,
        intent_id: str,
        approved_by: str,
        approved_at: datetime,
        cognitive_plan: CognitivePlan,
        trace_context: Dict,
        risk_band: str,
        is_destructive: bool
    ) -> bool:
        """
        Executa a saga de aprovação completa.

        Args:
            plan_id: ID do plano
            intent_id: ID do intent
            approved_by: Quem aprovou o plano
            approved_at: Timestamp da aprovação
            cognitive_plan: Plano cognitivo a ser publicado
            trace_context: Contexto de rastreamento (correlation_id, trace_id, span_id)
            risk_band: Faixa de risco do plano
            is_destructive: Se o plano contém operações destrutivas

        Returns:
            True se saga completou com sucesso

        Raises:
            RuntimeError: Se falha na atualização inicial do ledger
            RetryError: Se publicação falhar após compensação
        """
        start_time = time.time()
        correlation_id = trace_context.get('correlation_id')

        logger.info(
            'Iniciando saga de aprovação',
            plan_id=plan_id,
            intent_id=intent_id,
            correlation_id=correlation_id,
            saga_state=SagaState.EXECUTING
        )

        # Passo 1: Atualizar ledger com saga_state='executing'
        updated = await self.mongodb_client.update_plan_approval_status(
            plan_id=plan_id,
            approval_status='approved',
            approved_by=approved_by,
            approved_at=approved_at,
            saga_state=SagaState.EXECUTING
        )

        if not updated:
            logger.error(
                'Falha ao iniciar saga - ledger não atualizado',
                plan_id=plan_id,
                saga_state=SagaState.FAILED
            )
            self.metrics.increment_approval_ledger_error('saga_init_failed')
            raise RuntimeError(f"Falha ao iniciar saga para plan_id={plan_id}")

        # Passo 2: Tentar publicar no Kafka com retry
        try:
            await self._publish_with_retry(cognitive_plan, plan_id, intent_id)

            # Passo 3a: Sucesso - atualizar saga_state='completed'
            completion_success = await self._update_completion_status_with_retry(
                plan_id=plan_id,
                approved_by=approved_by,
                approved_at=approved_at,
                correlation_id=correlation_id
            )

            duration = time.time() - start_time

            if completion_success:
                self.metrics.observe_saga_duration(duration, SagaState.COMPLETED)
                logger.info(
                    'Saga de aprovação completada com sucesso',
                    plan_id=plan_id,
                    intent_id=intent_id,
                    correlation_id=correlation_id,
                    saga_state=SagaState.COMPLETED,
                    duration_ms=round(duration * 1000, 2)
                )
            else:
                # Publicação foi bem-sucedida mas atualização do ledger falhou
                # Logar erro e marcar como failed - plano já foi publicado
                self.metrics.observe_saga_duration(duration, SagaState.FAILED)
                self.metrics.increment_approval_ledger_error('saga_completion_update_failed')
                logger.error(
                    'Saga publicou plano mas falhou ao atualizar ledger para completed',
                    plan_id=plan_id,
                    intent_id=intent_id,
                    correlation_id=correlation_id,
                    saga_state=SagaState.FAILED,
                    duration_ms=round(duration * 1000, 2)
                )

            return True

        except RetryError as e:
            # Passo 3b: Falha - executar compensação
            # Extrair mensagem da exceção original para logging mais útil
            original_error = e.last_attempt.exception() if e.last_attempt else None
            failure_reason = str(original_error) if original_error else str(e)

            logger.warning(
                'Publicação Kafka falhou após retries - iniciando compensação',
                plan_id=plan_id,
                intent_id=intent_id,
                error=failure_reason
            )

            await self._compensate(
                plan_id=plan_id,
                intent_id=intent_id,
                failure_reason=failure_reason,
                trace_context=trace_context,
                approved_by=approved_by,
                approved_at=approved_at,
                cognitive_plan=cognitive_plan,
                risk_band=risk_band,
                is_destructive=is_destructive
            )

            duration = time.time() - start_time
            self.metrics.observe_saga_duration(duration, SagaState.COMPENSATED)

            # Re-lançar exceção para que consumer não commite offset
            raise

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        before_sleep=before_sleep_log(logging.getLogger(__name__), logging.WARNING)
    )
    async def _publish_with_retry(
        self,
        cognitive_plan: CognitivePlan,
        plan_id: str,
        intent_id: str
    ) -> None:
        """
        Publica plano no Kafka com retry para falhas transientes.

        Args:
            cognitive_plan: Plano a ser publicado
            plan_id: ID do plano
            intent_id: ID do intent
        """
        logger.info(
            'Tentando publicar plano aprovado',
            plan_id=plan_id,
            intent_id=intent_id
        )

        await self.plan_producer.send_plan(cognitive_plan)

        logger.info(
            'Plano publicado com sucesso',
            plan_id=plan_id,
            intent_id=intent_id
        )

    async def _update_completion_status_with_retry(
        self,
        plan_id: str,
        approved_by: str,
        approved_at: datetime,
        correlation_id: Optional[str],
        max_retries: int = 3
    ) -> bool:
        """
        Atualiza saga_state para 'completed' com retry em caso de falha.

        Se todas as tentativas falharem, marca como 'failed' via best-effort update.

        Args:
            plan_id: ID do plano
            approved_by: Quem aprovou
            approved_at: Timestamp da aprovação
            correlation_id: ID de correlação
            max_retries: Número máximo de tentativas

        Returns:
            True se atualizado para 'completed', False se marcado como 'failed'
        """
        last_error = None

        for attempt in range(max_retries):
            try:
                updated = await self.mongodb_client.update_plan_approval_status(
                    plan_id=plan_id,
                    approval_status='approved',
                    approved_by=approved_by,
                    approved_at=approved_at,
                    saga_state=SagaState.COMPLETED
                )

                if updated:
                    return True

                logger.warning(
                    'Update para saga_state=completed retornou false',
                    plan_id=plan_id,
                    attempt=attempt + 1,
                    max_retries=max_retries
                )

            except Exception as e:
                last_error = e
                logger.warning(
                    'Erro ao atualizar saga_state para completed',
                    plan_id=plan_id,
                    attempt=attempt + 1,
                    max_retries=max_retries,
                    error=str(e)
                )

        # Todas as tentativas falharam - marcar como failed via best-effort
        logger.error(
            'Falha ao atualizar saga_state para completed após retries - marcando como failed',
            plan_id=plan_id,
            last_error=str(last_error) if last_error else 'update returned false',
            correlation_id=correlation_id
        )

        try:
            await self.mongodb_client.update_plan_approval_status(
                plan_id=plan_id,
                approval_status='approved',
                approved_by=approved_by,
                approved_at=approved_at,
                saga_state=SagaState.FAILED,
                saga_failure_reason=f"Falha ao persistir completion: {last_error or 'update returned false'}"
            )
        except Exception as e:
            logger.error(
                'Best-effort update para saga_state=failed também falhou',
                plan_id=plan_id,
                error=str(e)
            )

        return False

    async def _compensate(
        self,
        plan_id: str,
        intent_id: str,
        failure_reason: str,
        trace_context: Dict,
        approved_by: str,
        approved_at: datetime,
        cognitive_plan: CognitivePlan,
        risk_band: str,
        is_destructive: bool
    ) -> None:
        """
        Executa compensação: reverte status do ledger e envia para DLQ.

        A compensação é best-effort - erros são logados mas não propagados
        para permitir que o fluxo continue.

        Args:
            plan_id: ID do plano
            intent_id: ID do intent
            failure_reason: Razão da falha original
            trace_context: Contexto de rastreamento
            approved_by: Quem havia aprovado
            approved_at: Quando foi aprovado
            cognitive_plan: Plano que falhou na publicação
            risk_band: Faixa de risco
            is_destructive: Se é destrutivo
        """
        correlation_id = trace_context.get('correlation_id')

        logger.info(
            'Executando compensação da saga',
            plan_id=plan_id,
            intent_id=intent_id,
            correlation_id=correlation_id,
            saga_state=SagaState.COMPENSATED
        )

        # Reverter status no MongoDB
        compensation_success = await self._revert_ledger_status(
            plan_id=plan_id,
            failure_reason=failure_reason
        )

        if not compensation_success:
            logger.error(
                'Falha na compensação - ledger não foi revertido',
                plan_id=plan_id,
                intent_id=intent_id,
                saga_state=SagaState.FAILED
            )

            # Best-effort: marcar saga_state='failed' para não deixar ledger em estado inconsistente
            await self._mark_saga_as_failed(
                plan_id=plan_id,
                failure_reason=f"Compensação falhou: {failure_reason}",
                correlation_id=correlation_id
            )

            # Registrar métrica específica para falha de compensação
            self.metrics.increment_saga_compensation_failure(risk_band)

            # Marcar como failed no DLQ
            failure_reason = f"COMPENSATION_FAILED: {failure_reason}"

        # Registrar métrica de compensação
        self.metrics.record_saga_compensation(
            reason='kafka_publish_failed',
            risk_band=risk_band
        )

        # Enviar para DLQ com metadados de compensação
        await self._send_to_dlq_with_compensation_metadata(
            plan_id=plan_id,
            intent_id=intent_id,
            failure_reason=failure_reason,
            trace_context=trace_context,
            approved_by=approved_by,
            approved_at=approved_at,
            cognitive_plan=cognitive_plan,
            risk_band=risk_band,
            is_destructive=is_destructive,
            compensation_executed=compensation_success
        )

        logger.info(
            'Compensação da saga concluída',
            plan_id=plan_id,
            intent_id=intent_id,
            compensation_success=compensation_success,
            saga_state=SagaState.COMPENSATED if compensation_success else SagaState.FAILED
        )

    async def _revert_ledger_status(
        self,
        plan_id: str,
        failure_reason: str
    ) -> bool:
        """
        Reverte status do plano no ledger para 'pending'.

        Args:
            plan_id: ID do plano
            failure_reason: Razão da reversão

        Returns:
            True se revertido com sucesso
        """
        try:
            reverted = await self.mongodb_client.revert_plan_approval_status(
                plan_id=plan_id,
                saga_state=SagaState.COMPENSATED,
                compensation_reason=failure_reason
            )

            if reverted:
                logger.info(
                    'Status do plano revertido para pending',
                    plan_id=plan_id,
                    saga_state=SagaState.COMPENSATED
                )
            else:
                logger.warning(
                    'Nenhum documento atualizado na reversão',
                    plan_id=plan_id
                )

            return reverted

        except Exception as e:
            logger.error(
                'Erro ao reverter status do plano',
                plan_id=plan_id,
                error=str(e)
            )
            return False

    async def _mark_saga_as_failed(
        self,
        plan_id: str,
        failure_reason: str,
        correlation_id: Optional[str]
    ) -> None:
        """
        Marca saga_state como 'failed' via best-effort update.

        Usado quando a compensação falha para não deixar o ledger
        em estado inconsistente (approved/executing).

        Args:
            plan_id: ID do plano
            failure_reason: Razão da falha
            correlation_id: ID de correlação
        """
        try:
            await self.mongodb_client.update_plan_saga_state(
                plan_id=plan_id,
                saga_state=SagaState.FAILED,
                saga_failure_reason=failure_reason
            )
            logger.info(
                'Saga marcada como failed após falha de compensação',
                plan_id=plan_id,
                saga_state=SagaState.FAILED,
                correlation_id=correlation_id
            )
        except Exception as e:
            logger.error(
                'Best-effort update para saga_state=failed falhou',
                plan_id=plan_id,
                error=str(e),
                correlation_id=correlation_id
            )
            # Não propagar erro - é best-effort

    async def _send_to_dlq_with_compensation_metadata(
        self,
        plan_id: str,
        intent_id: str,
        failure_reason: str,
        trace_context: Dict,
        approved_by: str,
        approved_at: datetime,
        cognitive_plan: CognitivePlan,
        risk_band: str,
        is_destructive: bool,
        compensation_executed: bool
    ) -> None:
        """
        Envia entrada para DLQ com metadados de compensação.

        Args:
            plan_id: ID do plano
            intent_id: ID do intent
            failure_reason: Razão da falha
            trace_context: Contexto de rastreamento
            approved_by: Quem aprovou
            approved_at: Timestamp da aprovação
            cognitive_plan: Plano cognitivo
            risk_band: Faixa de risco
            is_destructive: Se é destrutivo
            compensation_executed: Se a compensação foi executada com sucesso
        """
        if not self.dlq_producer:
            logger.warning(
                'DLQ producer não configurado - entrada não enviada',
                plan_id=plan_id
            )
            return

        try:
            # Incluir metadados de compensação na razão da falha
            enhanced_reason = failure_reason
            if compensation_executed:
                enhanced_reason = f"[COMPENSATED] {failure_reason}"
            else:
                enhanced_reason = f"[COMPENSATION_FAILED] {failure_reason}"

            dlq_entry = ApprovalDLQEntry(
                plan_id=plan_id,
                intent_id=intent_id,
                failure_reason=enhanced_reason,
                retry_count=3,
                original_approval_response={
                    'plan_id': plan_id,
                    'intent_id': intent_id,
                    'decision': 'approved',
                    'approved_by': approved_by,
                    'approved_at': int(approved_at.timestamp() * 1000),
                    'cognitive_plan': cognitive_plan.to_avro_dict(),
                    'saga_compensation_executed': compensation_executed
                },
                correlation_id=trace_context.get('correlation_id'),
                trace_id=trace_context.get('trace_id'),
                span_id=trace_context.get('span_id'),
                approved_by=approved_by,
                risk_band=risk_band,
                is_destructive=is_destructive
            )

            await self.dlq_producer.send_dlq_entry(dlq_entry)

            logger.info(
                'Entrada DLQ enviada com metadados de compensação',
                plan_id=plan_id,
                intent_id=intent_id,
                compensation_executed=compensation_executed
            )

            # Registrar métrica
            self.metrics.increment_approval_dlq_messages(
                reason='saga_compensation',
                risk_band=risk_band,
                is_destructive=is_destructive
            )

        except Exception as e:
            logger.error(
                'Falha ao enviar entrada para DLQ',
                plan_id=plan_id,
                error=str(e)
            )
            # Não propagar erro - DLQ é best-effort
