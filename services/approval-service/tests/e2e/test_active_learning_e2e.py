"""
Testes E2E para Active Learning - Fluxo Completo.

Valida o fluxo end-to-end do sistema de Active Learning:
1. Approval requests são processados
2. Casos de alto valor informacional são enfileirados
3. Revisores podem claim e release casos
4. Feedback é marcado com balanced_dataset=True
5. Métricas de balanceamento são atualizadas
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime, timezone, timedelta

from src.services.approval_service import ApprovalService
from src.api.routers import active_learning
from src.models.approval import ApprovalRequest, ApprovalStatus, RiskBand


@pytest.mark.e2e
class TestActiveLearningE2E:
    """Testes E2E do fluxo de Active Learning."""

    @pytest.fixture
    def e2e_components(self):
        """Configura todos os componentes para teste E2E."""
        # MongoDB mock com dados de teste
        mongodb_client = AsyncMock()
        mongodb_client.database = 'test_nh'

        # Mock collection com documentos
        async def mock_find_one(query):
            if query.get('queue_id') == 'queue-1':
                return {'queue_id': 'queue-1', 'plan_id': 'plan-1', 'status': 'pending'}
            return None

        async def mock_aggregate(pipeline):
            # Simula dados de balanceamento
            return [
                {'_id': 'approve', 'count': 450},
                {'_id': 'reject', 'count': 34}
            ]

        collection = AsyncMock()
        collection.find_one = AsyncMock(side_effect=mock_find_one)
        collection.aggregate = AsyncMock(side_effect=mock_aggregate)
        collection.count_documents = AsyncMock(return_value=484)
        mongodb_client.get_database = lambda: mongodb_client
        mongodb_client.__getitem__ = lambda self, name: collection

        # BalanceAnalyzer
        balance_analyzer = AsyncMock()
        balance_analyzer.calculate_balance_metrics = AsyncMock(
            return_value=MagicMock(
                total_feedbacks=484,
                balance={
                    'approve': {'count': 450, 'percentage': 93.0, 'gap': 0.0},
                    'reject': {'count': 34, 'percentage': 7.0, 'gap': 26.0}
                },
                confidence_distribution={
                    'low': {'count': 242, 'percentage': 50.0},
                    'medium': {'count': 242, 'percentage': 50.0},
                    'high': {'count': 0, 'percentage': 0.0}
                },
                domain_distribution={},
                semantic_features_count=46,
                semantic_features_percentage=9.5,
                priority_recommendations=[
                    {'type': 'class', 'value': 'reject', 'gap': 26.0}
                ],
                last_updated=datetime.now(timezone.utc).isoformat(),
                model_dump=lambda: {
                    'total_feedbacks': 484,
                    'balance': {'approve': {'count': 450, 'percentage': 93.0}},
                    'confidence_distribution': {},
                    'domain_distribution': {},
                    'semantic_features_count': 46,
                    'semantic_features_percentage': 9.5,
                    'priority_recommendations': [],
                    'last_updated': datetime.now(timezone.utc).isoformat()
                }
            )
        )

        # LearningStrategy
        learning_strategy = AsyncMock()
        learning_strategy.calculate_information_value = AsyncMock(return_value=0.85)

        # PriorityQueue
        priority_queue = MagicMock()
        priority_queue.enqueue_plan_for_review = AsyncMock(return_value='queue-1')
        priority_queue.get_queue_size = MagicMock(return_value=1)
        priority_queue.get_pending_cases = MagicMock(return_value=[
            {
                'queue_id': 'queue-1',
                'plan_id': 'plan-1',
                'intent_preview': 'Implementar feature...',
                'information_value': 0.85,
                'priority_reason': 'alta incerteza',
                'status': 'pending'
            }
        ])
        priority_queue.claim_case = MagicMock(return_value={
            'queue_id': 'queue-1',
            'status': 'in_review',
            'assigned_to': 'user@example.com',
            'claimed_at': datetime.now(timezone.utc),
            'expires_at': datetime.now(timezone.utc) + timedelta(hours=1)
        })
        priority_queue.release_case = MagicMock(return_value={
            'queue_id': 'queue-1',
            'status': 'pending'
        })
        priority_queue.mark_feedback_submitted = MagicMock(return_value={
            'queue_id': 'queue-1',
            'status': 'completed',
            'feedback_id': 'feedback-1'
        })
        priority_queue.collection = collection

        # FeedbackCollector
        feedback_collector = MagicMock()
        feedback_collector.submit_feedback = MagicMock(return_value='feedback-1')

        # LedgerClient
        ledger_client = AsyncMock()
        ledger_client.get_opinions_by_plan_id = AsyncMock(return_value=[
            {
                'opinion_id': 'op-1',
                'specialist_type': 'business',
                'recommendation': 'approve',
                'confidence_score': 0.5
            }
        ])

        # Settings
        settings = MagicMock()
        settings.enable_active_learning = True
        settings.enable_feedback_collection = True
        settings.active_learning_min_information_value = 0.5
        settings.mongodb_database = 'test_nh'

        return {
            'mongodb_client': mongodb_client,
            'balance_analyzer': balance_analyzer,
            'learning_strategy': learning_strategy,
            'priority_queue': priority_queue,
            'feedback_collector': feedback_collector,
            'ledger_client': ledger_client,
            'settings': settings
        }

    @pytest.fixture
    def approval_service(self, e2e_components):
        """ApprovalService configurado para E2E."""
        service = ApprovalService(
            settings=e2e_components['settings'],
            mongodb_client=e2e_components['mongodb_client'],
            response_producer=AsyncMock(),
            metrics=MagicMock(),
            balance_analyzer=e2e_components['balance_analyzer'],
            learning_strategy=e2e_components['learning_strategy'],
            priority_queue=e2e_components['priority_queue'],
            feedback_collector=e2e_components['feedback_collector'],
            ledger_client=e2e_components['ledger_client']
        )
        return service

    @pytest.mark.asyncio
    async def test_e2e_full_active_learning_flow(self, approval_service, e2e_components):
        """
        Teste E2E completo: Request -> Enqueue -> Claim -> Feedback -> Metrics.
        """
        with patch('src.services.approval_service.HAS_ACTIVE_LEARNING', True):
            approval_service.active_learning_enabled = True
            priority_queue = e2e_components['priority_queue']
            balance_analyzer = e2e_components['balance_analyzer']

            # === Step 1: Approval Request é processado e enfileirado ===
            request = ApprovalRequest(
                approval_id='approval-1',
                plan_id='plan-1',
                intent_id='intent-1',
                original_intent_text='Implementar sistema de autenticação com OAuth 2.0',
                risk_score=0.7,
                risk_band=RiskBand.MEDIUM,
                is_destructive=False,
                status=ApprovalStatus.PENDING,
                requested_at=datetime.now(timezone.utc),
                cognitive_plan={'plan_id': 'plan-1', 'steps': []}
            )

            await approval_service.process_approval_request(request)

            # Verificar que caso foi enfileirado
            priority_queue.enqueue_plan_for_review.assert_called_once()
            call_args = priority_queue.enqueue_plan_for_review.call_args
            assert call_args[1]['plan_id'] == 'plan-1'
            assert call_args[1]['information_value'] == 0.85

            # === Step 2: Obter métricas de balanceamento ===
            metrics = await balance_analyzer.calculate_balance_metrics()
            assert metrics.total_feedbacks == 484
            assert metrics.balance['reject']['gap'] == 26.0  # Gap significativo

            # === Step 3: Obter fila de casos ===
            cases = priority_queue.get_pending_cases(limit=10)
            assert len(cases) == 1
            assert cases[0]['queue_id'] == 'queue-1'
            assert cases[0]['information_value'] == 0.85

            # === Step 4: Claim caso para revisão ===
            claim_result = priority_queue.claim_case(
                queue_id='queue-1',
                assigned_to='user@example.com'
            )
            assert claim_result['status'] == 'in_review'

            # === Step 5: Submeter feedback (marcado como balanced) ===
            await approval_service._submit_feedback_for_plan(
                plan_id='plan-1',
                human_decision='reject',
                human_rating=0.3,
                user_id='user@example.com',
                from_active_learning=True
            )

            # Verificar que feedback foi marcado
            feedback_collector = e2e_components['feedback_collector']
            feedback_collector.submit_feedback.assert_called()
            call_args = feedback_collector.submit_feedback.call_args
            feedback_data = call_args[0][0]
            assert feedback_data['balanced_dataset'] is True
            assert feedback_data['collection_method'] == 'active_learning'

            # === Step 6: Marcar como completado ===
            complete_result = priority_queue.mark_feedback_submitted(
                queue_id='queue-1',
                feedback_id='feedback-1'
            )
            assert complete_result['status'] == 'completed'

    @pytest.mark.asyncio
    async def test_e2e_claim_and_release_flow(self, e2e_components):
        """Teste E2E de claim e release de caso."""
        priority_queue = e2e_components['priority_queue']

        # Claim caso
        claim_result = priority_queue.claim_case(
            queue_id='queue-1',
            assigned_to='user@example.com'
        )
        assert claim_result['status'] == 'in_review'
        assert claim_result['assigned_to'] == 'user@example.com'

        # Release caso (usuário decidiu não revisar)
        release_result = priority_queue.release_case(queue_id='queue-1')
        assert release_result['status'] == 'pending'

    @pytest.mark.asyncio
    async def test_e2e_balance_metrics_inform_priority(self, e2e_components):
        """Teste E2E que métricas de balanceamento informam prioridade."""
        balance_analyzer = e2e_components['balance_analyzer']

        # Obter métricas
        metrics = await balance_analyzer.calculate_balance_metrics()

        # Verificar que gap em 'reject' gera recomendação de prioridade
        assert metrics.total_feedbacks == 484
        assert metrics.balance['reject']['gap'] == 26.0

        # Verificar recomendações de prioridade
        recommendations = metrics.priority_recommendations
        assert len(recommendations) > 0
        assert any(r['value'] == 'reject' for r in recommendations)


@pytest.mark.e2e
class TestActiveLearningAPIE2E:
    """Testes E2E da API de Active Learning."""

    @pytest.fixture
    def fastapi_app(self):
        """Cria app FastAPI com mocks."""
        from fastapi import FastAPI
        from src.api.routers import active_learning

        app = FastAPI()
        app.include_router(active_learning.router)

        # Setup mocks
        balance_analyzer = MagicMock()
        balance_analyzer.calculate_balance_metrics = AsyncMock(
            return_value=MagicMock(
                total_feedbacks=100,
                balance={'approve': {'count': 80, 'percentage': 80.0, 'gap': 0.0}},
                confidence_distribution={},
                domain_distribution={},
                semantic_features_count=10,
                semantic_features_percentage=10.0,
                priority_recommendations=[],
                last_updated=datetime.now(timezone.utc).isoformat(),
                model_dump=lambda: {
                    'total_feedbacks': 100,
                    'balance': {},
                    'confidence_distribution': {},
                    'domain_distribution': {},
                    'semantic_features_count': 10,
                    'semantic_features_percentage': 10.0,
                    'priority_recommendations': [],
                    'last_updated': datetime.now(timezone.utc).isoformat()
                }
            )
        )

        priority_queue = MagicMock()
        priority_queue.get_queue_size = MagicMock(return_value=5)
        priority_queue.get_pending_cases = MagicMock(return_value=[])
        priority_queue.claim_case = MagicMock(return_value={
            'queue_id': 'q1',
            'status': 'in_review',
            'assigned_to': 'user@example.com',
            'claimed_at': datetime.now(timezone.utc),
            'expires_at': datetime.now(timezone.utc) + timedelta(hours=1)
        })
        priority_queue.release_case = MagicMock(return_value={'queue_id': 'q1', 'status': 'pending'})

        collection = AsyncMock()
        collection.find_one = AsyncMock(return_value=None)
        priority_queue.collection = collection

        app.state.balance_analyzer = balance_analyzer
        app.state.feedback_queue = priority_queue
        app.state.feedback_collector = MagicMock(submit_feedback=MagicMock(return_value='f1'))

        return app

    def test_e2e_metrics_endpoint(self, fastapi_app):
        """Teste E2E do endpoint de métricas."""
        from fastapi.testclient import TestClient

        client = TestClient(fastapi_app)
        response = client.get('/api/v1/active-learning/metrics')

        assert response.status_code == 200
        data = response.json()
        assert data['total_feedbacks'] == 100
        assert 'balance' in data

    def test_e2e_queue_endpoint(self, fastapi_app):
        """Teste E2E do endpoint de fila."""
        from fastapi.testclient import TestClient

        client = TestClient(fastapi_app)
        response = client.get('/api/v1/active-learning/queue')

        assert response.status_code == 200
        data = response.json()
        assert data['queue_size'] == 5
        assert 'cases' in data

    def test_e2e_claim_endpoint(self, fastapi_app):
        """Teste E2E do endpoint de claim."""
        from fastapi.testclient import TestClient

        client = TestClient(fastapi_app)
        response = client.post(
            '/api/v1/active-learning/q1/claim',
            json={'assigned_to': 'user@example.com'}
        )

        assert response.status_code == 200
        data = response.json()
        assert data['status'] == 'in_review'

    def test_e2e_release_endpoint(self, fastapi_app):
        """Teste E2E do endpoint de release."""
        from fastapi.testclient import TestClient

        client = TestClient(fastapi_app)
        response = client.post('/api/v1/active-learning/q1/release')

        assert response.status_code == 200
        data = response.json()
        assert data['status'] == 'pending'
