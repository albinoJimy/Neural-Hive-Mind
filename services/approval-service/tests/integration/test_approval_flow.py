"""
Testes de integracao para fluxo de aprovacao

Testa fluxo completo: request → pending → approve/reject → response
Requer MongoDB e Kafka (usando testcontainers ou mocks).
"""

import pytest
import json
from datetime import datetime
from unittest.mock import MagicMock, AsyncMock, patch

from src.config.settings import Settings
from src.models.approval import (
    ApprovalRequest,
    ApprovalDecision,
    ApprovalResponse,
    ApprovalStatus,
    RiskBand
)
from src.services.approval_service import ApprovalService
from src.clients.mongodb_client import MongoDBClient
from src.producers.approval_response_producer import ApprovalResponseProducer
from src.consumers.approval_request_consumer import ApprovalRequestConsumer


class TestApprovalFlowEndToEnd:
    """Testes de fluxo end-to-end (com mocks)"""

    @pytest.fixture
    def mock_mongodb_client(self):
        """MongoDB client mockado que simula persistencia"""
        storage = {}

        async def save_request(approval):
            storage[approval.plan_id] = approval
            return approval.approval_id

        async def get_by_plan_id(plan_id):
            return storage.get(plan_id)

        async def update_decision(plan_id, decision):
            if plan_id in storage:
                storage[plan_id].status = ApprovalStatus(decision.decision)
                storage[plan_id].approved_by = decision.approved_by
                storage[plan_id].approved_at = decision.approved_at
                return True
            return False

        async def get_pending(limit, offset, filters):
            return [
                a for a in storage.values()
                if a.status == ApprovalStatus.PENDING
            ][:limit]

        client = MagicMock()
        client.save_approval_request = AsyncMock(side_effect=save_request)
        client.get_approval_by_plan_id = AsyncMock(side_effect=get_by_plan_id)
        client.update_approval_decision = AsyncMock(side_effect=update_decision)
        client.get_pending_approvals = AsyncMock(side_effect=get_pending)
        client._storage = storage

        return client

    @pytest.fixture
    def mock_producer(self):
        """Kafka producer mockado que captura mensagens"""
        messages = []

        async def send_response(response, **kwargs):
            messages.append(response)

        producer = MagicMock()
        producer.send_approval_response = AsyncMock(side_effect=send_response)
        producer._messages = messages

        return producer

    @pytest.fixture
    def approval_service(
        self, mock_settings, mock_mongodb_client, mock_producer, mock_metrics
    ):
        """Cria ApprovalService com mocks"""
        return ApprovalService(
            settings=mock_settings,
            mongodb_client=mock_mongodb_client,
            response_producer=mock_producer,
            metrics=mock_metrics
        )

    @pytest.mark.asyncio
    async def test_full_approval_flow(
        self, approval_service, mock_mongodb_client, mock_producer
    ):
        """Teste fluxo completo de aprovacao"""
        # 1. Receber request de aprovacao
        plan_data = {
            'plan_id': 'flow-plan-001',
            'intent_id': 'flow-intent-001',
            'risk_score': 0.85,
            'risk_band': 'high',
            'is_destructive': True,
            'destructive_tasks': ['task-2'],
            'requires_approval': True
        }

        approval = await approval_service.process_approval_request(plan_data)

        # Verificar persistencia
        assert approval.status == ApprovalStatus.PENDING
        assert mock_mongodb_client._storage['flow-plan-001'].status == ApprovalStatus.PENDING

        # 2. Listar pendentes
        pending = await approval_service.get_pending_approvals()
        assert len(pending) == 1
        assert pending[0].plan_id == 'flow-plan-001'

        # 3. Aprovar o plano
        decision = await approval_service.approve_plan(
            plan_id='flow-plan-001',
            user_id='admin@test.com',
            comments='Aprovado apos analise'
        )

        assert decision.decision == 'approved'
        assert decision.approved_by == 'admin@test.com'

        # 4. Verificar mensagem Kafka enviada
        assert len(mock_producer._messages) == 1
        kafka_msg = mock_producer._messages[0]
        assert kafka_msg.plan_id == 'flow-plan-001'
        assert kafka_msg.decision == 'approved'
        assert kafka_msg.cognitive_plan is not None

        # 5. Verificar que nao esta mais pendente
        pending = await approval_service.get_pending_approvals()
        assert len(pending) == 0

    @pytest.mark.asyncio
    async def test_full_rejection_flow(
        self, approval_service, mock_mongodb_client, mock_producer
    ):
        """Teste fluxo completo de rejeicao"""
        # 1. Receber request de aprovacao
        plan_data = {
            'plan_id': 'reject-plan-001',
            'intent_id': 'reject-intent-001',
            'risk_score': 0.95,
            'risk_band': 'critical',
            'is_destructive': True,
            'destructive_tasks': ['task-1', 'task-2', 'task-3']
        }

        await approval_service.process_approval_request(plan_data)

        # 2. Rejeitar o plano
        decision = await approval_service.reject_plan(
            plan_id='reject-plan-001',
            user_id='admin@test.com',
            reason='Risco critico sem justificativa suficiente',
            comments='Operacoes destrutivas em producao'
        )

        assert decision.decision == 'rejected'
        assert decision.rejection_reason == 'Risco critico sem justificativa suficiente'

        # 3. Verificar mensagem Kafka enviada
        kafka_msg = mock_producer._messages[0]
        assert kafka_msg.plan_id == 'reject-plan-001'
        assert kafka_msg.decision == 'rejected'
        assert kafka_msg.rejection_reason is not None
        # Para rejeicoes, cognitive_plan deve ser None
        assert kafka_msg.cognitive_plan is None

    @pytest.mark.asyncio
    async def test_multiple_plans_flow(
        self, approval_service, mock_mongodb_client, mock_producer
    ):
        """Teste com multiplos planos simultaneos"""
        # Criar 3 planos
        for i in range(3):
            await approval_service.process_approval_request({
                'plan_id': f'multi-plan-{i}',
                'intent_id': f'multi-intent-{i}',
                'risk_score': 0.7 + (i * 0.05),
                'risk_band': 'high'
            })

        # Verificar todos pendentes
        pending = await approval_service.get_pending_approvals()
        assert len(pending) == 3

        # Aprovar primeiro
        await approval_service.approve_plan(
            plan_id='multi-plan-0',
            user_id='admin@test.com'
        )

        # Rejeitar segundo
        await approval_service.reject_plan(
            plan_id='multi-plan-1',
            user_id='admin@test.com',
            reason='Rejeitado'
        )

        # Terceiro ainda pendente
        pending = await approval_service.get_pending_approvals()
        assert len(pending) == 1
        assert pending[0].plan_id == 'multi-plan-2'

        # Duas mensagens Kafka enviadas
        assert len(mock_producer._messages) == 2


class TestApprovalFlowConcurrency:
    """Testes de concorrencia no fluxo de aprovacao"""

    @pytest.fixture
    def approval_service(
        self, mock_settings, mock_mongodb_client, mock_response_producer, mock_metrics
    ):
        """Cria ApprovalService para testes"""
        return ApprovalService(
            settings=mock_settings,
            mongodb_client=mock_mongodb_client,
            response_producer=mock_response_producer,
            metrics=mock_metrics
        )

    @pytest.mark.asyncio
    async def test_concurrent_approval_same_plan(
        self, approval_service, sample_approval_request, mock_mongodb_client
    ):
        """Teste aprovacao concorrente do mesmo plano"""
        mock_mongodb_client.get_approval_by_plan_id.return_value = sample_approval_request
        mock_mongodb_client.update_approval_decision.return_value = True

        # Primeira aprovacao deve funcionar
        result1 = await approval_service.approve_plan(
            plan_id='plan-001',
            user_id='admin1@test.com'
        )
        assert result1.decision == 'approved'

        # Segunda aprovacao deve falhar (status ja nao e pendente)
        sample_approval_request.status = ApprovalStatus.APPROVED

        with pytest.raises(ValueError) as exc_info:
            await approval_service.approve_plan(
                plan_id='plan-001',
                user_id='admin2@test.com'
            )

        assert 'nao esta pendente' in str(exc_info.value)


class TestApprovalFlowEdgeCases:
    """Testes de casos de borda"""

    @pytest.fixture
    def approval_service(
        self, mock_settings, mock_mongodb_client, mock_response_producer, mock_metrics
    ):
        """Cria ApprovalService para testes"""
        return ApprovalService(
            settings=mock_settings,
            mongodb_client=mock_mongodb_client,
            response_producer=mock_response_producer,
            metrics=mock_metrics
        )

    @pytest.mark.asyncio
    async def test_approval_with_large_plan(
        self, approval_service, mock_mongodb_client
    ):
        """Teste aprovacao com plano grande"""
        large_plan = {
            'plan_id': 'large-plan-001',
            'intent_id': 'large-intent-001',
            'risk_score': 0.8,
            'risk_band': 'high',
            'tasks': [{'task_id': f'task-{i}'} for i in range(1000)],
            'metadata': {'key': 'value' * 1000}
        }

        result = await approval_service.process_approval_request(large_plan)

        assert result.plan_id == 'large-plan-001'
        mock_mongodb_client.save_approval_request.assert_called_once()

    @pytest.mark.asyncio
    async def test_approval_with_special_characters(
        self, approval_service, mock_mongodb_client
    ):
        """Teste aprovacao com caracteres especiais"""
        special_plan = {
            'plan_id': 'plan-日本語-001',
            'intent_id': 'intent-émojis-🎉',
            'risk_score': 0.5,
            'description': 'Descricao com acentuação e símbolos: @#$%'
        }

        result = await approval_service.process_approval_request(special_plan)

        assert result.plan_id == 'plan-日本語-001'

    @pytest.mark.asyncio
    async def test_rejection_with_long_reason(
        self, approval_service, sample_approval_request, mock_mongodb_client, mock_response_producer
    ):
        """Teste rejeicao com motivo muito longo"""
        mock_mongodb_client.get_approval_by_plan_id.return_value = sample_approval_request
        mock_mongodb_client.update_approval_decision.return_value = True

        long_reason = 'Motivo detalhado: ' + ('x' * 5000)

        result = await approval_service.reject_plan(
            plan_id='plan-001',
            user_id='admin@test.com',
            reason=long_reason
        )

        assert result.rejection_reason == long_reason
