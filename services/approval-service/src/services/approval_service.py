"""
Approval Service - Logica de negocio para aprovacao de planos

Camada de servico que coordena operacoes entre API, MongoDB e Kafka.
"""

import structlog
from datetime import datetime
from typing import Dict, List, Optional, Any
from pymongo.errors import DuplicateKeyError

from src.config.settings import Settings
from src.models.approval import (
    ApprovalRequest,
    ApprovalDecision,
    ApprovalResponse,
    ApprovalStats,
    ApprovalStatus
)
from src.clients.mongodb_client import MongoDBClient
from src.producers.approval_response_producer import ApprovalResponseProducer
from src.observability.metrics import NeuralHiveMetrics

logger = structlog.get_logger()


class ApprovalService:
    """Servico de logica de negocio para aprovacoes"""

    def __init__(
        self,
        settings: Settings,
        mongodb_client: MongoDBClient,
        response_producer: ApprovalResponseProducer,
        metrics: NeuralHiveMetrics
    ):
        self.settings = settings
        self.mongodb_client = mongodb_client
        self.response_producer = response_producer
        self.metrics = metrics

    async def process_approval_request(self, approval_request: ApprovalRequest) -> ApprovalRequest:
        """
        Processa novo request de aprovacao recebido do Kafka

        Args:
            approval_request: ApprovalRequest ja deserializado pelo consumer

        Returns:
            ApprovalRequest criado e persistido

        Raises:
            DuplicateKeyError: Se plan_id ja existe
            ValueError: Se dados invalidos
        """
        try:
            # Valida campos obrigatorios
            if not approval_request.plan_id or not approval_request.intent_id:
                raise ValueError('plan_id e intent_id sao obrigatorios')

            # Persiste no MongoDB
            await self.mongodb_client.save_approval_request(approval_request)

            # Emite metricas
            self.metrics.increment_approval_requests_received(
                risk_band=approval_request.risk_band,
                is_destructive=approval_request.is_destructive
            )
            self.metrics.update_pending_gauge()

            logger.info(
                'Approval request processado',
                plan_id=approval_request.plan_id,
                intent_id=approval_request.intent_id,
                risk_band=approval_request.risk_band,
                is_destructive=approval_request.is_destructive
            )

            return approval_request

        except DuplicateKeyError:
            logger.warning(
                'Plan ja existe no sistema de aprovacao',
                plan_id=approval_request.plan_id
            )
            raise
        except Exception as e:
            logger.error(
                'Erro ao processar approval request',
                error=str(e),
                plan_id=approval_request.plan_id
            )
            raise

    async def approve_plan(
        self,
        plan_id: str,
        user_id: str,
        comments: Optional[str] = None
    ) -> ApprovalDecision:
        """
        Aprova um plano cognitivo

        Args:
            plan_id: ID do plano
            user_id: ID do usuario que esta aprovando
            comments: Comentarios opcionais

        Returns:
            ApprovalDecision com a decisao

        Raises:
            ValueError: Se plano nao encontrado ou nao esta pendente
        """
        start_time = datetime.utcnow()

        # Busca plano
        approval = await self.mongodb_client.get_approval_by_plan_id(plan_id)
        if not approval:
            raise ValueError(f'Plano nao encontrado: {plan_id}')

        if approval.status != ApprovalStatus.PENDING:
            raise ValueError(
                f'Plano nao esta pendente. Status atual: {approval.status}'
            )

        # Cria decisao
        decision = ApprovalDecision(
            plan_id=plan_id,
            decision='approved',
            approved_by=user_id,
            approved_at=datetime.utcnow(),
            comments=comments
        )

        # Atualiza MongoDB
        updated = await self.mongodb_client.update_approval_decision(plan_id, decision)
        if not updated:
            raise ValueError('Falha ao atualizar decisao no MongoDB')

        # Publica no Kafka
        response = ApprovalResponse(
            plan_id=plan_id,
            intent_id=approval.intent_id,
            decision='approved',
            approved_by=user_id,
            approved_at=decision.approved_at,
            cognitive_plan=approval.cognitive_plan
        )
        await self.response_producer.send_approval_response(response)

        # Emite metricas
        duration = (datetime.utcnow() - start_time).total_seconds()
        time_to_decision = (decision.approved_at - approval.requested_at).total_seconds()

        self.metrics.increment_approvals_total('approved', approval.risk_band)
        self.metrics.observe_processing_duration(duration, 'approved')
        self.metrics.observe_time_to_decision(time_to_decision, 'approved', approval.risk_band)
        self.metrics.update_pending_gauge()

        logger.info(
            'Plano aprovado',
            plan_id=plan_id,
            approved_by=user_id,
            time_to_decision_seconds=time_to_decision
        )

        return decision

    async def reject_plan(
        self,
        plan_id: str,
        user_id: str,
        reason: str,
        comments: Optional[str] = None
    ) -> ApprovalDecision:
        """
        Rejeita um plano cognitivo

        Args:
            plan_id: ID do plano
            user_id: ID do usuario que esta rejeitando
            reason: Motivo da rejeicao (obrigatorio)
            comments: Comentarios opcionais

        Returns:
            ApprovalDecision com a decisao

        Raises:
            ValueError: Se plano nao encontrado, nao pendente, ou reason vazio
        """
        if not reason or not reason.strip():
            raise ValueError('Motivo da rejeicao e obrigatorio')

        start_time = datetime.utcnow()

        # Busca plano
        approval = await self.mongodb_client.get_approval_by_plan_id(plan_id)
        if not approval:
            raise ValueError(f'Plano nao encontrado: {plan_id}')

        if approval.status != ApprovalStatus.PENDING:
            raise ValueError(
                f'Plano nao esta pendente. Status atual: {approval.status}'
            )

        # Cria decisao
        decision = ApprovalDecision(
            plan_id=plan_id,
            decision='rejected',
            approved_by=user_id,
            approved_at=datetime.utcnow(),
            rejection_reason=reason,
            comments=comments
        )

        # Atualiza MongoDB
        updated = await self.mongodb_client.update_approval_decision(plan_id, decision)
        if not updated:
            raise ValueError('Falha ao atualizar decisao no MongoDB')

        # Publica no Kafka (sem cognitive_plan para rejeicoes)
        response = ApprovalResponse(
            plan_id=plan_id,
            intent_id=approval.intent_id,
            decision='rejected',
            approved_by=user_id,
            approved_at=decision.approved_at,
            rejection_reason=reason,
            cognitive_plan=None
        )
        await self.response_producer.send_approval_response(response)

        # Emite metricas
        duration = (datetime.utcnow() - start_time).total_seconds()
        time_to_decision = (decision.approved_at - approval.requested_at).total_seconds()

        self.metrics.increment_approvals_total('rejected', approval.risk_band)
        self.metrics.observe_processing_duration(duration, 'rejected')
        self.metrics.observe_time_to_decision(time_to_decision, 'rejected', approval.risk_band)
        self.metrics.update_pending_gauge()

        logger.info(
            'Plano rejeitado',
            plan_id=plan_id,
            rejected_by=user_id,
            reason=reason,
            time_to_decision_seconds=time_to_decision
        )

        return decision

    async def get_pending_approvals(
        self,
        limit: int = 50,
        offset: int = 0,
        risk_band: Optional[str] = None,
        is_destructive: Optional[bool] = None
    ) -> List[ApprovalRequest]:
        """
        Lista aprovacoes pendentes com filtros

        Args:
            limit: Limite de resultados
            offset: Offset para paginacao
            risk_band: Filtro por banda de risco
            is_destructive: Filtro por destrutivo

        Returns:
            Lista de ApprovalRequest pendentes
        """
        filters = {}
        if risk_band:
            filters['risk_band'] = risk_band
        if is_destructive is not None:
            filters['is_destructive'] = is_destructive

        approvals = await self.mongodb_client.get_pending_approvals(
            limit=limit,
            offset=offset,
            filters=filters if filters else None
        )

        # Emite metrica de API
        self.metrics.increment_api_requests('pending', '200')

        return approvals

    async def get_approval_by_plan_id(self, plan_id: str) -> Optional[ApprovalRequest]:
        """
        Busca aprovacao por plan_id

        Args:
            plan_id: ID do plano

        Returns:
            ApprovalRequest ou None
        """
        return await self.mongodb_client.get_approval_by_plan_id(plan_id)

    async def get_approval_stats(self) -> ApprovalStats:
        """
        Retorna estatisticas de aprovacao

        Returns:
            ApprovalStats com contagens e metricas
        """
        stats = await self.mongodb_client.get_approval_stats()

        # Emite metrica de API
        self.metrics.increment_api_requests('stats', '200')

        return stats
