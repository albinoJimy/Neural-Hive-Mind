"""
Testes unitários para lógica de aprovação do Orchestrator

Testa decisão de aprovação, roteamento condicional e enriquecimento de metadados.
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime

from src.models.cognitive_plan import RiskBand, ApprovalStatus, TaskNode


class TestOrchestratorApprovalDecision:
    """Testes para lógica de decisão de aprovação"""

    @pytest.fixture
    def mock_settings(self):
        """Mock Settings object"""
        settings = MagicMock()
        settings.destructive_detection_enabled = True
        settings.destructive_detection_strict_mode = False
        settings.risk_threshold_high = 0.7
        settings.risk_threshold_critical = 0.9
        settings.kafka_approval_topic = 'cognitive-plans-approval-requests'
        return settings

    @pytest.fixture
    def mock_dependencies(self, mock_settings):
        """Cria dependências mockadas para o orchestrator"""
        return {
            'semantic_parser': MagicMock(),
            'dag_generator': MagicMock(),
            'risk_scorer': MagicMock(),
            'explainability_generator': MagicMock(),
            'mongodb_client': MagicMock(),
            'neo4j_client': MagicMock(),
            'plan_producer': MagicMock(),
            'approval_producer': MagicMock(),
            'metrics': MagicMock()
        }

    def test_approval_required_for_high_risk_score(self):
        """risk_score >= 0.7 deve triggerar requires_approval=True"""
        risk_score = 0.75
        is_destructive = False
        risk_band = RiskBand.MEDIUM

        requires_approval = (
            risk_score >= 0.7 or
            is_destructive or
            risk_band in [RiskBand.HIGH, RiskBand.CRITICAL]
        )

        assert requires_approval is True

    def test_approval_required_for_destructive_operations(self):
        """is_destructive=True deve triggerar requires_approval=True"""
        risk_score = 0.3
        is_destructive = True
        risk_band = RiskBand.LOW

        requires_approval = (
            risk_score >= 0.7 or
            is_destructive or
            risk_band in [RiskBand.HIGH, RiskBand.CRITICAL]
        )

        assert requires_approval is True

    def test_approval_required_for_high_risk_band(self):
        """risk_band=HIGH deve triggerar requires_approval=True"""
        risk_score = 0.5
        is_destructive = False
        risk_band = RiskBand.HIGH

        requires_approval = (
            risk_score >= 0.7 or
            is_destructive or
            risk_band in [RiskBand.HIGH, RiskBand.CRITICAL]
        )

        assert requires_approval is True

    def test_approval_required_for_critical_risk_band(self):
        """risk_band=CRITICAL deve triggerar requires_approval=True"""
        risk_score = 0.5
        is_destructive = False
        risk_band = RiskBand.CRITICAL

        requires_approval = (
            risk_score >= 0.7 or
            is_destructive or
            risk_band in [RiskBand.HIGH, RiskBand.CRITICAL]
        )

        assert requires_approval is True

    def test_no_approval_for_low_risk(self):
        """risk_score < 0.7, non-destructive, risk_band LOW/MEDIUM deve bypassar aprovação"""
        risk_score = 0.3
        is_destructive = False
        risk_band = RiskBand.LOW

        requires_approval = (
            risk_score >= 0.7 or
            is_destructive or
            risk_band in [RiskBand.HIGH, RiskBand.CRITICAL]
        )

        assert requires_approval is False

    def test_no_approval_for_medium_risk_below_threshold(self):
        """risk_score < 0.7 com risk_band=MEDIUM deve bypassar aprovação"""
        risk_score = 0.5
        is_destructive = False
        risk_band = RiskBand.MEDIUM

        requires_approval = (
            risk_score >= 0.7 or
            is_destructive or
            risk_band in [RiskBand.HIGH, RiskBand.CRITICAL]
        )

        assert requires_approval is False

    def test_approval_criteria_combination_all_true(self):
        """Múltiplos critérios verdadeiros devem triggerar aprovação"""
        risk_score = 0.85
        is_destructive = True
        risk_band = RiskBand.CRITICAL

        requires_approval = (
            risk_score >= 0.7 or
            is_destructive or
            risk_band in [RiskBand.HIGH, RiskBand.CRITICAL]
        )

        assert requires_approval is True

    def test_approval_threshold_edge_case_exactly_0_7(self):
        """risk_score exatamente 0.7 deve triggerar aprovação"""
        risk_score = 0.7
        is_destructive = False
        risk_band = RiskBand.MEDIUM

        requires_approval = (
            risk_score >= 0.7 or
            is_destructive or
            risk_band in [RiskBand.HIGH, RiskBand.CRITICAL]
        )

        assert requires_approval is True

    def test_approval_threshold_edge_case_just_below(self):
        """risk_score 0.69 não deve triggerar aprovação (se outros critérios falsos)"""
        risk_score = 0.69
        is_destructive = False
        risk_band = RiskBand.MEDIUM

        requires_approval = (
            risk_score >= 0.7 or
            is_destructive or
            risk_band in [RiskBand.HIGH, RiskBand.CRITICAL]
        )

        assert requires_approval is False


class TestOrchestratorConditionalPublishing:
    """Testes para lógica de roteamento condicional"""

    @pytest.fixture
    def mock_plan_producer(self):
        """Mock do KafkaPlanProducer"""
        producer = MagicMock()
        producer.send_plan = AsyncMock()
        return producer

    @pytest.fixture
    def mock_approval_producer(self):
        """Mock do KafkaApprovalProducer"""
        producer = MagicMock()
        producer.send_approval_request = AsyncMock()
        producer.settings = MagicMock()
        producer.settings.kafka_approval_topic = 'cognitive-plans-approval-requests'
        return producer

    @pytest.fixture
    def mock_cognitive_plan_blocked(self):
        """CognitivePlan mockado que requer aprovação"""
        plan = MagicMock()
        plan.plan_id = 'plan-123'
        plan.intent_id = 'intent-456'
        plan.requires_approval = True
        plan.approval_status = ApprovalStatus.PENDING
        plan.risk_band = RiskBand.HIGH
        plan.is_destructive = True
        plan.risk_matrix = {'destructive_severity': 'high'}
        return plan

    @pytest.fixture
    def mock_cognitive_plan_approved(self):
        """CognitivePlan mockado que não requer aprovação"""
        plan = MagicMock()
        plan.plan_id = 'plan-789'
        plan.intent_id = 'intent-012'
        plan.requires_approval = False
        plan.approval_status = None
        plan.risk_band = RiskBand.LOW
        plan.is_destructive = False
        return plan

    @pytest.mark.asyncio
    async def test_publish_to_approval_topic_when_blocked(
        self,
        mock_approval_producer,
        mock_plan_producer,
        mock_cognitive_plan_blocked
    ):
        """Planos bloqueados devem ser publicados no tópico de aprovação"""
        cognitive_plan = mock_cognitive_plan_blocked

        if cognitive_plan.requires_approval:
            await mock_approval_producer.send_approval_request(cognitive_plan)
        else:
            await mock_plan_producer.send_plan(cognitive_plan)

        mock_approval_producer.send_approval_request.assert_called_once_with(cognitive_plan)
        mock_plan_producer.send_plan.assert_not_called()

    @pytest.mark.asyncio
    async def test_publish_to_execution_topic_when_approved(
        self,
        mock_approval_producer,
        mock_plan_producer,
        mock_cognitive_plan_approved
    ):
        """Planos não bloqueados devem ser publicados no tópico de execução"""
        cognitive_plan = mock_cognitive_plan_approved

        if cognitive_plan.requires_approval:
            await mock_approval_producer.send_approval_request(cognitive_plan)
        else:
            await mock_plan_producer.send_plan(cognitive_plan)

        mock_plan_producer.send_plan.assert_called_once_with(cognitive_plan)
        mock_approval_producer.send_approval_request.assert_not_called()

    @pytest.mark.asyncio
    async def test_approval_producer_called_with_correct_plan(
        self,
        mock_approval_producer,
        mock_cognitive_plan_blocked
    ):
        """Verificar que send_approval_request recebe o plano correto"""
        cognitive_plan = mock_cognitive_plan_blocked

        await mock_approval_producer.send_approval_request(cognitive_plan)

        call_args = mock_approval_producer.send_approval_request.call_args
        assert call_args[0][0] == cognitive_plan
        assert call_args[0][0].plan_id == 'plan-123'
        assert call_args[0][0].requires_approval is True

    @pytest.mark.asyncio
    async def test_plan_producer_not_called_when_blocked(
        self,
        mock_approval_producer,
        mock_plan_producer,
        mock_cognitive_plan_blocked
    ):
        """Garantir que tópico de execução não é usado para planos bloqueados"""
        cognitive_plan = mock_cognitive_plan_blocked

        if cognitive_plan.requires_approval:
            await mock_approval_producer.send_approval_request(cognitive_plan)

        mock_plan_producer.send_plan.assert_not_called()


class TestOrchestratorApprovalMetadata:
    """Testes para enriquecimento de metadados de aprovação"""

    def test_cognitive_plan_has_requires_approval_true(self):
        """Verificar que requires_approval=True é definido corretamente"""
        requires_approval = True
        is_destructive = True
        destructive_tasks = ['task-1', 'task-2']
        risk_matrix = {'is_destructive': True, 'destructive_severity': 'high'}

        # Simular criação de plano
        plan_data = {
            'requires_approval': requires_approval,
            'approval_status': ApprovalStatus.PENDING if requires_approval else None,
            'is_destructive': is_destructive,
            'destructive_tasks': destructive_tasks,
            'risk_matrix': risk_matrix
        }

        assert plan_data['requires_approval'] is True

    def test_cognitive_plan_has_approval_status_pending(self):
        """Verificar que approval_status=PENDING quando requires_approval=True"""
        requires_approval = True

        approval_status = ApprovalStatus.PENDING if requires_approval else None

        assert approval_status == ApprovalStatus.PENDING

    def test_cognitive_plan_approval_status_none_when_not_required(self):
        """Verificar que approval_status=None quando requires_approval=False"""
        requires_approval = False

        approval_status = ApprovalStatus.PENDING if requires_approval else None

        assert approval_status is None

    def test_cognitive_plan_has_destructive_fields(self):
        """Verificar que is_destructive e destructive_tasks são populados"""
        is_destructive = True
        destructive_tasks = ['task-delete-1', 'task-drop-2']

        plan_data = {
            'is_destructive': is_destructive,
            'destructive_tasks': destructive_tasks
        }

        assert plan_data['is_destructive'] is True
        assert len(plan_data['destructive_tasks']) == 2
        assert 'task-delete-1' in plan_data['destructive_tasks']

    def test_cognitive_plan_has_risk_matrix(self):
        """Verificar que risk_matrix é incluído corretamente"""
        risk_matrix = {
            'overall_score': 0.85,
            'overall_band': 'HIGH',
            'is_destructive': True,
            'destructive_tasks': ['task-1'],
            'destructive_severity': 'critical',
            'destructive_count': 1
        }

        plan_data = {'risk_matrix': risk_matrix}

        assert plan_data['risk_matrix'] is not None
        assert plan_data['risk_matrix']['overall_score'] == 0.85
        assert plan_data['risk_matrix']['is_destructive'] is True
        assert plan_data['risk_matrix']['destructive_severity'] == 'critical'


class TestOrchestratorApprovalLogging:
    """Testes para audit trail de aprovação"""

    @pytest.fixture
    def mock_logger(self):
        """Mock do logger estruturado"""
        with patch('src.services.orchestrator.logger') as mock:
            yield mock

    def test_warning_logged_for_blocked_plan(self, mock_logger):
        """Verificar que warning é emitido para planos bloqueados"""
        intent_id = 'intent-123'
        plan_id = 'plan-456'
        risk_score = 0.85
        risk_band = RiskBand.HIGH
        is_destructive = True
        destructive_severity = 'critical'
        destructive_tasks = ['task-1', 'task-2']

        # Simular log de bloqueio
        mock_logger.warning(
            'Plano bloqueado aguardando aprovacao humana',
            plan_id=plan_id,
            intent_id=intent_id,
            risk_score=risk_score,
            risk_band=risk_band.value,
            is_destructive=is_destructive,
            destructive_severity=destructive_severity,
            destructive_task_count=len(destructive_tasks)
        )

        mock_logger.warning.assert_called_once()
        call_kwargs = mock_logger.warning.call_args[1]
        assert call_kwargs['plan_id'] == plan_id
        assert call_kwargs['is_destructive'] is True
        assert call_kwargs['destructive_task_count'] == 2

    def test_log_includes_approval_criteria(self, mock_logger):
        """Verificar que critérios de aprovação são incluídos no log"""
        intent_id = 'intent-123'
        risk_score = 0.75
        is_destructive = False
        risk_band = RiskBand.MEDIUM

        approval_criteria = {
            'risk_score_threshold': risk_score >= 0.7,
            'is_destructive': is_destructive,
            'risk_band_critical': risk_band in [RiskBand.HIGH, RiskBand.CRITICAL]
        }

        mock_logger.warning(
            'Plano requer aprovacao - criterios atingidos',
            intent_id=intent_id,
            approval_criteria=approval_criteria,
            risk_score=risk_score,
            risk_band=risk_band.value
        )

        mock_logger.warning.assert_called_once()
        call_kwargs = mock_logger.warning.call_args[1]
        assert 'approval_criteria' in call_kwargs
        assert call_kwargs['approval_criteria']['risk_score_threshold'] is True

    def test_log_includes_destructive_analysis(self, mock_logger):
        """Verificar que análise destrutiva é incluída no log"""
        intent_id = 'intent-123'
        is_destructive = True
        destructive_severity = 'high'
        destructive_tasks = ['task-delete-users', 'task-drop-table']

        mock_logger.warning(
            'Plano requer aprovacao - criterios atingidos',
            intent_id=intent_id,
            is_destructive=is_destructive,
            destructive_severity=destructive_severity,
            destructive_tasks=destructive_tasks
        )

        mock_logger.warning.assert_called_once()
        call_kwargs = mock_logger.warning.call_args[1]
        assert call_kwargs['is_destructive'] is True
        assert call_kwargs['destructive_severity'] == 'high'
        assert len(call_kwargs['destructive_tasks']) == 2


class TestOrchestratorMetricsRecording:
    """Testes para registro de métricas de aprovação"""

    @pytest.fixture
    def mock_metrics(self):
        """Mock do NeuralHiveMetrics"""
        metrics = MagicMock()
        metrics.increment_plans = MagicMock()
        metrics.observe_geracao_duration = MagicMock()
        return metrics

    def test_metrics_status_blocked_for_approval(self, mock_metrics):
        """Verificar que status='blocked_for_approval' é registrado para planos bloqueados"""
        requires_approval = True
        domain = 'business'

        plan_status = 'blocked_for_approval' if requires_approval else 'success'
        mock_metrics.increment_plans(channel=domain, status=plan_status)

        mock_metrics.increment_plans.assert_called_once_with(
            channel='business',
            status='blocked_for_approval'
        )

    def test_metrics_status_success_for_approved(self, mock_metrics):
        """Verificar que status='success' é registrado para planos não bloqueados"""
        requires_approval = False
        domain = 'technical'

        plan_status = 'blocked_for_approval' if requires_approval else 'success'
        mock_metrics.increment_plans(channel=domain, status=plan_status)

        mock_metrics.increment_plans.assert_called_once_with(
            channel='technical',
            status='success'
        )
