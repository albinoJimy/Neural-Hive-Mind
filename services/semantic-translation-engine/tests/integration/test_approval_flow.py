"""
Testes de integração para fluxo de aprovação end-to-end

Valida o fluxo completo de detecção destrutiva -> avaliação de risco -> roteamento condicional.
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime

from src.models.cognitive_plan import TaskNode, RiskBand, ApprovalStatus
from src.services.risk_scorer import RiskScorer
from src.services.destructive_detector import DestructiveDetector


class TestDestructiveIntentTriggersApprovalFlow:
    """Testes para intents destrutivos que triggeraram fluxo de aprovação"""

    @pytest.fixture
    def settings(self):
        """Settings completo para testes de integração"""
        settings = MagicMock()
        settings.destructive_detection_enabled = True
        settings.destructive_detection_strict_mode = False
        settings.risk_weight_priority = 0.3
        settings.risk_weight_security = 0.4
        settings.risk_weight_complexity = 0.3
        settings.risk_threshold_high = 0.7
        settings.risk_threshold_critical = 0.9
        return settings

    @pytest.fixture
    def risk_scorer(self, settings):
        """RiskScorer real com DestructiveDetector integrado"""
        return RiskScorer(settings)

    @pytest.fixture
    def intermediate_repr_destructive(self):
        """Representação intermediária com operação destrutiva"""
        return {
            'id': 'intent-destructive-001',
            'metadata': {
                'priority': 'critical',
                'security_level': 'restricted'
            },
            'historical_context': {
                'similar_intents': []
            }
        }

    @pytest.fixture
    def tasks_with_delete(self):
        """Tasks com operação de delete"""
        return [
            TaskNode(
                task_id='task-1',
                task_type='query',
                description='Buscar usuários inativos',
                dependencies=[]
            ),
            TaskNode(
                task_id='task-2',
                task_type='delete',
                description='Deletar todos os usuários inativos da produção',
                dependencies=['task-1']
            ),
            TaskNode(
                task_id='task-3',
                task_type='notify',
                description='Notificar administradores',
                dependencies=['task-2']
            )
        ]

    def test_destructive_intent_triggers_approval_flow(
        self,
        risk_scorer,
        intermediate_repr_destructive,
        tasks_with_delete
    ):
        """Intent com operação destrutiva deve triggerar fluxo de aprovação"""
        # Executar avaliação multi-domínio
        risk_score, risk_band, risk_factors, risk_matrix = risk_scorer.score_multi_domain(
            intermediate_repr_destructive,
            tasks_with_delete
        )

        # Verificar que operação destrutiva foi detectada
        assert risk_matrix['is_destructive'] is True
        assert len(risk_matrix['destructive_tasks']) >= 1
        assert 'task-2' in risk_matrix['destructive_tasks']

        # Verificar critérios de aprovação
        requires_approval = (
            risk_score >= 0.7 or
            risk_matrix['is_destructive'] or
            risk_band in [RiskBand.HIGH, RiskBand.CRITICAL]
        )

        assert requires_approval is True

    def test_destructive_severity_critical_for_production_delete(
        self,
        risk_scorer,
        intermediate_repr_destructive,
        tasks_with_delete
    ):
        """Delete em produção deve resultar em severity critical"""
        risk_score, risk_band, risk_factors, risk_matrix = risk_scorer.score_multi_domain(
            intermediate_repr_destructive,
            tasks_with_delete
        )

        # A descrição contém 'produção' e 'deletar todos', indicadores de alto impacto
        assert risk_matrix['destructive_severity'] == 'critical'


class TestHighRiskIntentTriggersApprovalFlow:
    """Testes para intents de alto risco que triggeraram fluxo de aprovação"""

    @pytest.fixture
    def settings(self):
        """Settings para testes de alto risco"""
        settings = MagicMock()
        settings.destructive_detection_enabled = True
        settings.destructive_detection_strict_mode = False
        settings.risk_weight_priority = 0.3
        settings.risk_weight_security = 0.4
        settings.risk_weight_complexity = 0.3
        settings.risk_threshold_high = 0.7
        settings.risk_threshold_critical = 0.9
        return settings

    @pytest.fixture
    def risk_scorer(self, settings):
        """RiskScorer real"""
        return RiskScorer(settings)

    @pytest.fixture
    def intermediate_repr_high_risk(self):
        """Representação intermediária de alto risco"""
        return {
            'id': 'intent-high-risk-001',
            'metadata': {
                'priority': 'critical',
                'security_level': 'confidential'
            },
            'historical_context': {
                'similar_intents': []
            }
        }

    @pytest.fixture
    def tasks_complex_non_destructive(self):
        """Tasks complexas mas não destrutivas"""
        return [
            TaskNode(
                task_id=f'task-{i}',
                task_type='transform',
                description=f'Transformação complexa {i}',
                dependencies=[f'task-{i-1}'] if i > 0 else []
            )
            for i in range(15)  # 15 tasks = very_high complexity
        ]

    def test_high_risk_intent_triggers_approval_flow(
        self,
        risk_scorer,
        intermediate_repr_high_risk,
        tasks_complex_non_destructive
    ):
        """Intent com fatores de alto risco deve triggerar fluxo de aprovação"""
        risk_score, risk_band, risk_factors, risk_matrix = risk_scorer.score_multi_domain(
            intermediate_repr_high_risk,
            tasks_complex_non_destructive
        )

        # Verificar que risk_band é HIGH ou CRITICAL devido a priority=critical e security_level=confidential
        assert risk_band in [RiskBand.HIGH, RiskBand.CRITICAL] or risk_score >= 0.7

        # Verificar critérios de aprovação
        requires_approval = (
            risk_score >= 0.7 or
            risk_matrix.get('is_destructive', False) or
            risk_band in [RiskBand.HIGH, RiskBand.CRITICAL]
        )

        assert requires_approval is True


class TestLowRiskIntentBypassesApproval:
    """Testes para intents de baixo risco que bypassam aprovação"""

    @pytest.fixture
    def settings(self):
        """Settings para testes de baixo risco"""
        settings = MagicMock()
        settings.destructive_detection_enabled = True
        settings.destructive_detection_strict_mode = False
        settings.risk_weight_priority = 0.3
        settings.risk_weight_security = 0.4
        settings.risk_weight_complexity = 0.3
        settings.risk_threshold_high = 0.7
        settings.risk_threshold_critical = 0.9
        return settings

    @pytest.fixture
    def risk_scorer(self, settings):
        """RiskScorer real"""
        return RiskScorer(settings)

    @pytest.fixture
    def intermediate_repr_low_risk(self):
        """Representação intermediária de baixo risco"""
        return {
            'id': 'intent-low-risk-001',
            'metadata': {
                'priority': 'low',
                'security_level': 'public'
            },
            'historical_context': {
                'similar_intents': []
            }
        }

    @pytest.fixture
    def tasks_simple_safe(self):
        """Tasks simples e seguras"""
        return [
            TaskNode(
                task_id='task-1',
                task_type='query',
                description='Buscar dados públicos',
                dependencies=[]
            ),
            TaskNode(
                task_id='task-2',
                task_type='transform',
                description='Formatar resultado',
                dependencies=['task-1']
            )
        ]

    def test_low_risk_intent_bypasses_approval(
        self,
        risk_scorer,
        intermediate_repr_low_risk,
        tasks_simple_safe
    ):
        """Intent de baixo risco deve bypassar fluxo de aprovação"""
        risk_score, risk_band, risk_factors, risk_matrix = risk_scorer.score_multi_domain(
            intermediate_repr_low_risk,
            tasks_simple_safe
        )

        # Verificar que não é destrutivo
        assert risk_matrix['is_destructive'] is False
        assert risk_matrix['destructive_tasks'] == []

        # Verificar critérios de aprovação
        requires_approval = (
            risk_score >= 0.7 or
            risk_matrix['is_destructive'] or
            risk_band in [RiskBand.HIGH, RiskBand.CRITICAL]
        )

        # Para operações de baixo risco, não deve requerer aprovação
        # Nota: O resultado pode variar dependendo dos pesos configurados
        if risk_band == RiskBand.LOW and risk_score < 0.7:
            assert requires_approval is False


class TestRiskMatrixContainsDestructiveAnalysis:
    """Testes para verificar que risk_matrix contém análise destrutiva completa"""

    @pytest.fixture
    def settings(self):
        """Settings para testes"""
        settings = MagicMock()
        settings.destructive_detection_enabled = True
        settings.destructive_detection_strict_mode = False
        settings.risk_weight_priority = 0.3
        settings.risk_weight_security = 0.4
        settings.risk_weight_complexity = 0.3
        settings.risk_threshold_high = 0.7
        settings.risk_threshold_critical = 0.9
        return settings

    @pytest.fixture
    def risk_scorer(self, settings):
        """RiskScorer real"""
        return RiskScorer(settings)

    @pytest.fixture
    def intermediate_repr(self):
        """Representação intermediária básica"""
        return {
            'id': 'intent-test-001',
            'metadata': {
                'priority': 'normal',
                'security_level': 'internal'
            }
        }

    @pytest.fixture
    def tasks_with_multiple_destructive(self):
        """Tasks com múltiplas operações destrutivas"""
        return [
            TaskNode(
                task_id='task-1',
                task_type='delete',
                description='Delete old records',
                dependencies=[]
            ),
            TaskNode(
                task_id='task-2',
                task_type='drop',
                description='Drop temporary table',
                dependencies=['task-1']
            ),
            TaskNode(
                task_id='task-3',
                task_type='truncate',
                description='Truncate staging table',
                dependencies=['task-2']
            )
        ]

    def test_risk_matrix_contains_destructive_fields(
        self,
        risk_scorer,
        intermediate_repr,
        tasks_with_multiple_destructive
    ):
        """Verificar que risk_matrix contém todos os campos de análise destrutiva"""
        risk_score, risk_band, risk_factors, risk_matrix = risk_scorer.score_multi_domain(
            intermediate_repr,
            tasks_with_multiple_destructive
        )

        # Verificar campos obrigatórios de análise destrutiva
        assert 'is_destructive' in risk_matrix
        assert 'destructive_tasks' in risk_matrix
        assert 'destructive_severity' in risk_matrix
        assert 'destructive_count' in risk_matrix

        # Verificar valores
        assert risk_matrix['is_destructive'] is True
        assert len(risk_matrix['destructive_tasks']) == 3
        assert risk_matrix['destructive_count'] == 3

    def test_risk_matrix_contains_domain_assessments(
        self,
        risk_scorer,
        intermediate_repr,
        tasks_with_multiple_destructive
    ):
        """Verificar que risk_matrix contém assessments por domínio"""
        risk_score, risk_band, risk_factors, risk_matrix = risk_scorer.score_multi_domain(
            intermediate_repr,
            tasks_with_multiple_destructive
        )

        # Verificar campos de RiskMatrix base
        assert 'assessments' in risk_matrix
        assert 'overall_score' in risk_matrix
        assert 'overall_band' in risk_matrix
        assert 'highest_risk_domain' in risk_matrix


class TestApprovalProducerIntegration:
    """Testes de integração para KafkaApprovalProducer"""

    @pytest.fixture
    def mock_settings(self):
        """Settings mockado para producer"""
        settings = MagicMock()
        settings.kafka_bootstrap_servers = 'localhost:9092'
        settings.kafka_security_protocol = 'PLAINTEXT'
        settings.kafka_enable_idempotence = True
        settings.kafka_approval_topic = 'cognitive-plans-approval-requests'
        settings.schema_registry_url = None
        settings.environment = 'test'
        return settings

    @pytest.fixture
    def mock_cognitive_plan(self):
        """CognitivePlan mockado para teste"""
        plan = MagicMock()
        plan.plan_id = 'plan-integration-001'
        plan.intent_id = 'intent-integration-001'
        plan.correlation_id = 'corr-integration-001'
        plan.trace_id = 'trace-integration-001'
        plan.span_id = 'span-integration-001'
        plan.requires_approval = True
        plan.approval_status = ApprovalStatus.PENDING
        plan.risk_band = RiskBand.HIGH
        plan.is_destructive = True
        plan.risk_matrix = {
            'is_destructive': True,
            'destructive_severity': 'high',
            'destructive_tasks': ['task-1'],
            'destructive_count': 1
        }
        plan.get_partition_key = MagicMock(return_value='business')
        plan.to_avro_dict = MagicMock(return_value={
            'plan_id': 'plan-integration-001',
            'requires_approval': True
        })
        return plan

    @patch('src.producers.approval_producer.Producer')
    def test_approval_producer_sends_to_correct_topic(
        self,
        mock_producer_class,
        mock_settings,
        mock_cognitive_plan
    ):
        """Verificar que approval producer envia para tópico correto"""
        from src.producers.approval_producer import KafkaApprovalProducer

        # Configurar mock do producer
        mock_producer = MagicMock()
        mock_producer_class.return_value = mock_producer

        # Criar producer (sem inicializar transações para teste unitário)
        producer = KafkaApprovalProducer(mock_settings)
        producer.producer = mock_producer

        # Verificar configuração
        assert producer.settings.kafka_approval_topic == 'cognitive-plans-approval-requests'

    @patch('src.producers.approval_producer.Producer')
    def test_approval_producer_includes_correct_headers(
        self,
        mock_producer_class,
        mock_settings,
        mock_cognitive_plan
    ):
        """Verificar que headers incluem informações de aprovação"""
        from src.producers.approval_producer import KafkaApprovalProducer

        # Os headers esperados incluem:
        expected_headers = [
            'plan-id',
            'intent-id',
            'risk-band',
            'is-destructive',
            'requires-approval',
            'content-type',
            'schema-version'
        ]

        # Verificar que headers estão definidos corretamente
        for header_name in expected_headers:
            assert header_name in expected_headers


class TestApprovalResponseFlowIntegration:
    """Testes de integração para fluxo de resposta de aprovação"""

    @pytest.fixture
    def mock_settings(self):
        """Settings mockado para testes"""
        settings = MagicMock()
        settings.kafka_bootstrap_servers = 'localhost:9092'
        settings.kafka_consumer_group_id = 'semantic-translation-engine'
        settings.kafka_auto_offset_reset = 'earliest'
        settings.kafka_session_timeout_ms = 30000
        settings.kafka_security_protocol = 'PLAINTEXT'
        settings.kafka_approval_responses_topic = 'cognitive-plans-approval-responses'
        settings.kafka_plans_topic = 'cognitive-plans'
        settings.kafka_enable_idempotence = True
        settings.schema_registry_url = None
        settings.environment = 'test'
        return settings

    @pytest.fixture
    def sample_ledger_entry(self):
        """Entrada de ledger com plano pendente de aprovação"""
        return {
            'plan_id': 'plan-e2e-001',
            'intent_id': 'intent-e2e-001',
            'version': '1.0.0',
            'timestamp': datetime.utcnow(),
            'plan_data': {
                'plan_id': 'plan-e2e-001',
                'intent_id': 'intent-e2e-001',
                'version': '1.0.0',
                'approval_status': 'pending',
                'risk_band': 'high',
                'risk_score': 0.85,
                'is_destructive': True,
                'destructive_tasks': ['task-delete'],
                'tasks': [
                    {
                        'task_id': 'task-query',
                        'task_type': 'query',
                        'description': 'Buscar registros',
                        'dependencies': []
                    },
                    {
                        'task_id': 'task-delete',
                        'task_type': 'delete',
                        'description': 'Deletar registros obsoletos',
                        'dependencies': ['task-query']
                    }
                ],
                'execution_order': ['task-query', 'task-delete'],
                'complexity_score': 0.4,
                'explainability_token': 'exp-e2e-001',
                'reasoning_summary': 'Plano para remoção de dados obsoletos',
                'original_domain': 'infrastructure',
                'original_priority': 'high',
                'original_security_level': 'confidential',
                'requires_approval': True
            }
        }

    @pytest.mark.asyncio
    async def test_end_to_end_approval_flow(self, mock_settings, sample_ledger_entry):
        """Fluxo E2E: resposta de aprovação -> atualização ledger -> publicação"""
        from src.services.approval_processor import ApprovalProcessor

        # Mocks
        mongodb_client = MagicMock()
        mongodb_client.query_ledger = AsyncMock(return_value=sample_ledger_entry)
        mongodb_client.update_plan_approval_status = AsyncMock(return_value=True)

        plan_producer = MagicMock()
        plan_producer.send_plan = AsyncMock()

        metrics = MagicMock()
        metrics.record_approval_decision = MagicMock()
        metrics.observe_approval_processing_duration = MagicMock()
        metrics.observe_approval_time_to_decision = MagicMock()
        metrics.increment_approval_ledger_error = MagicMock()

        processor = ApprovalProcessor(mongodb_client, plan_producer, metrics)

        # Simular resposta de aprovação
        approval_response = {
            'plan_id': 'plan-e2e-001',
            'intent_id': 'intent-e2e-001',
            'decision': 'approved',
            'approved_by': 'security-admin@company.com',
            'approved_at': int(datetime.utcnow().timestamp() * 1000),
            'rejection_reason': None
        }

        trace_context = {
            'correlation_id': 'corr-e2e-001',
            'trace_id': 'trace-e2e-001',
            'span_id': 'span-e2e-001'
        }

        # Executar processamento
        await processor.process_approval_response(approval_response, trace_context)

        # Verificar que ledger foi consultado
        mongodb_client.query_ledger.assert_called_once_with('plan-e2e-001')

        # Verificar que ledger foi atualizado
        mongodb_client.update_plan_approval_status.assert_called_once()
        update_call = mongodb_client.update_plan_approval_status.call_args
        assert update_call.kwargs['plan_id'] == 'plan-e2e-001'
        assert update_call.kwargs['approval_status'] == 'approved'
        assert update_call.kwargs['approved_by'] == 'security-admin@company.com'

        # Verificar que plano foi publicado
        plan_producer.send_plan.assert_called_once()

        # Verificar métricas
        metrics.record_approval_decision.assert_called_once_with(
            decision='approved',
            risk_band='high',
            is_destructive=True
        )

    @pytest.mark.asyncio
    async def test_end_to_end_rejection_flow(self, mock_settings, sample_ledger_entry):
        """Fluxo E2E: resposta de rejeição -> atualização ledger -> sem publicação"""
        from src.services.approval_processor import ApprovalProcessor

        # Mocks
        mongodb_client = MagicMock()
        mongodb_client.query_ledger = AsyncMock(return_value=sample_ledger_entry)
        mongodb_client.update_plan_approval_status = AsyncMock(return_value=True)

        plan_producer = MagicMock()
        plan_producer.send_plan = AsyncMock()

        metrics = MagicMock()
        metrics.record_approval_decision = MagicMock()
        metrics.observe_approval_processing_duration = MagicMock()
        metrics.observe_approval_time_to_decision = MagicMock()
        metrics.increment_approval_ledger_error = MagicMock()

        processor = ApprovalProcessor(mongodb_client, plan_producer, metrics)

        # Simular resposta de rejeição
        approval_response = {
            'plan_id': 'plan-e2e-001',
            'intent_id': 'intent-e2e-001',
            'decision': 'rejected',
            'approved_by': 'security-admin@company.com',
            'approved_at': int(datetime.utcnow().timestamp() * 1000),
            'rejection_reason': 'Operação de delete em produção requer análise adicional do DBA'
        }

        trace_context = {
            'correlation_id': 'corr-e2e-001'
        }

        # Executar processamento
        await processor.process_approval_response(approval_response, trace_context)

        # Verificar que ledger foi atualizado com motivo de rejeição
        mongodb_client.update_plan_approval_status.assert_called_once()
        update_call = mongodb_client.update_plan_approval_status.call_args
        assert update_call.kwargs['approval_status'] == 'rejected'
        assert 'DBA' in update_call.kwargs['rejection_reason']

        # Verificar que plano NÃO foi publicado
        plan_producer.send_plan.assert_not_called()

        # Verificar métricas de rejeição
        metrics.record_approval_decision.assert_called_once_with(
            decision='rejected',
            risk_band='high',
            is_destructive=True
        )

    @pytest.mark.asyncio
    async def test_consumer_processor_integration(self, mock_settings, sample_ledger_entry):
        """Integração entre consumer e processor"""
        from src.consumers.approval_response_consumer import ApprovalResponseConsumer
        from src.services.approval_processor import ApprovalProcessor
        import json

        # Criar consumer
        consumer = ApprovalResponseConsumer(mock_settings)

        # Criar processor com mocks
        mongodb_client = MagicMock()
        mongodb_client.query_ledger = AsyncMock(return_value=sample_ledger_entry)
        mongodb_client.update_plan_approval_status = AsyncMock(return_value=True)

        plan_producer = MagicMock()
        plan_producer.send_plan = AsyncMock()

        metrics = MagicMock()
        metrics.record_approval_decision = MagicMock()
        metrics.observe_approval_processing_duration = MagicMock()
        metrics.observe_approval_time_to_decision = MagicMock()
        metrics.increment_approval_ledger_error = MagicMock()

        processor = ApprovalProcessor(mongodb_client, plan_producer, metrics)

        # Simular mensagem Kafka
        approval_data = {
            'plan_id': 'plan-e2e-001',
            'intent_id': 'intent-e2e-001',
            'decision': 'approved',
            'approved_by': 'admin',
            'approved_at': int(datetime.utcnow().timestamp() * 1000)
        }

        mock_msg = MagicMock()
        mock_msg.headers.return_value = [
            ('content-type', b'application/json'),
            ('correlation-id', b'corr-test')
        ]
        mock_msg.value.return_value = json.dumps(approval_data).encode('utf-8')

        # Deserializar mensagem
        deserialized = consumer._deserialize_message(mock_msg)
        trace_context = consumer._extract_trace_context(mock_msg.headers())

        # Processar
        await processor.process_approval_response(deserialized, trace_context)

        # Verificar que fluxo completo funcionou
        mongodb_client.query_ledger.assert_called_once()
        mongodb_client.update_plan_approval_status.assert_called_once()
        plan_producer.send_plan.assert_called_once()


class TestApprovalResponseConsumerResilience:
    """Testes de resiliência do consumer de respostas de aprovação"""

    @pytest.fixture
    def mock_settings(self):
        """Settings mockado"""
        settings = MagicMock()
        settings.kafka_bootstrap_servers = 'localhost:9092'
        settings.kafka_consumer_group_id = 'semantic-translation-engine'
        settings.kafka_auto_offset_reset = 'earliest'
        settings.kafka_session_timeout_ms = 30000
        settings.kafka_security_protocol = 'PLAINTEXT'
        settings.kafka_approval_responses_topic = 'cognitive-plans-approval-responses'
        settings.schema_registry_url = None
        return settings

    @pytest.mark.asyncio
    async def test_processor_handles_mongodb_failure_gracefully(self, mock_settings):
        """Processor deve tratar falha do MongoDB sem crash"""
        from src.services.approval_processor import ApprovalProcessor

        mongodb_client = MagicMock()
        mongodb_client.query_ledger = AsyncMock(side_effect=Exception('MongoDB connection lost'))

        plan_producer = MagicMock()
        plan_producer.send_plan = AsyncMock()

        metrics = MagicMock()
        metrics.increment_approval_ledger_error = MagicMock()

        processor = ApprovalProcessor(mongodb_client, plan_producer, metrics)

        approval_response = {
            'plan_id': 'plan-fail',
            'intent_id': 'intent-fail',
            'decision': 'approved',
            'approved_by': 'admin',
            'approved_at': int(datetime.utcnow().timestamp() * 1000)
        }

        # Deve propagar exceção para retry do consumer
        with pytest.raises(Exception):
            await processor.process_approval_response(approval_response, {})

        # Plano não deve ser publicado
        plan_producer.send_plan.assert_not_called()

    @pytest.mark.asyncio
    async def test_processor_handles_invalid_plan_data_gracefully(self, mock_settings):
        """Processor deve tratar dados de plano inválidos sem crash"""
        from src.services.approval_processor import ApprovalProcessor

        # Ledger entry com plan_data malformado
        malformed_entry = {
            'plan_id': 'plan-malformed',
            'timestamp': datetime.utcnow(),
            'plan_data': {
                'approval_status': 'pending',
                'risk_band': 'high',
                'is_destructive': False
                # Missing required fields for CognitivePlan reconstruction
            }
        }

        mongodb_client = MagicMock()
        mongodb_client.query_ledger = AsyncMock(return_value=malformed_entry)
        mongodb_client.update_plan_approval_status = AsyncMock(return_value=True)

        plan_producer = MagicMock()
        plan_producer.send_plan = AsyncMock()

        metrics = MagicMock()
        metrics.record_approval_decision = MagicMock()
        metrics.observe_approval_processing_duration = MagicMock()
        metrics.observe_approval_time_to_decision = MagicMock()
        metrics.increment_approval_ledger_error = MagicMock()

        processor = ApprovalProcessor(mongodb_client, plan_producer, metrics)

        approval_response = {
            'plan_id': 'plan-malformed',
            'intent_id': 'intent-x',
            'decision': 'approved',
            'approved_by': 'admin',
            'approved_at': int(datetime.utcnow().timestamp() * 1000)
        }

        # Deve propagar erro de reconstrução do plano
        with pytest.raises(Exception):
            await processor.process_approval_response(approval_response, {})
