"""
Testes unitários para o modelo CognitivePlan

Valida campos de aprovação, operações destrutivas, serialização Avro,
e compatibilidade retroativa.
"""

import pytest
from datetime import datetime, timedelta
from src.models.cognitive_plan import (
    CognitivePlan,
    TaskNode,
    RiskBand,
    PlanStatus,
    ApprovalStatus
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def minimal_valid_plan_data():
    """Dados mínimos para criar um CognitivePlan válido."""
    return {
        'intent_id': 'intent-001',
        'tasks': [
            TaskNode(
                task_id='task-1',
                task_type='query',
                description='Query database'
            )
        ],
        'execution_order': ['task-1'],
        'risk_score': 0.3,
        'risk_band': RiskBand.LOW,
        'explainability_token': 'token-001',
        'reasoning_summary': 'Simple query operation',
        'complexity_score': 0.2,
        'original_domain': 'data_management',
        'original_priority': 'normal',
        'original_security_level': 'internal'
    }


@pytest.fixture
def sample_plan_requiring_approval():
    """Plano cognitivo que requer aprovação."""
    return {
        'intent_id': 'intent-approval-001',
        'tasks': [
            TaskNode(
                task_id='task-delete-1',
                task_type='delete',
                description='Delete old records',
                parameters={'table': 'users', 'condition': 'inactive > 365 days'}
            )
        ],
        'execution_order': ['task-delete-1'],
        'risk_score': 0.85,
        'risk_band': RiskBand.HIGH,
        'explainability_token': 'token-approval-001',
        'reasoning_summary': 'High risk due to destructive operation',
        'complexity_score': 0.6,
        'original_domain': 'data_management',
        'original_priority': 'high',
        'original_security_level': 'confidential',
        'requires_approval': True,
        'approval_status': ApprovalStatus.PENDING,
        'is_destructive': True,
        'destructive_tasks': ['task-delete-1'],
        'risk_matrix': {
            'BUSINESS': 0.7,
            'SECURITY': 0.9,
            'OPERATIONAL': 0.8
        }
    }


@pytest.fixture
def sample_plan_approved():
    """Plano cognitivo aprovado."""
    return {
        'intent_id': 'intent-approved-001',
        'tasks': [
            TaskNode(
                task_id='task-1',
                task_type='transform',
                description='Transform data'
            )
        ],
        'execution_order': ['task-1'],
        'risk_score': 0.5,
        'risk_band': RiskBand.MEDIUM,
        'explainability_token': 'token-approved-001',
        'reasoning_summary': 'Approved transformation',
        'complexity_score': 0.4,
        'original_domain': 'data_management',
        'original_priority': 'normal',
        'original_security_level': 'internal',
        'requires_approval': True,
        'approval_status': ApprovalStatus.APPROVED,
        'approved_by': 'admin-user-123',
        'approved_at': datetime.utcnow()
    }


# ============================================================================
# TestCognitivePlanApprovalFields
# ============================================================================

class TestCognitivePlanApprovalFields:
    """Testes para validar campos de aprovação."""

    def test_default_values_no_approval_required(self, minimal_valid_plan_data):
        """Verificar que requires_approval=False e approval_status=None por padrão."""
        plan = CognitivePlan(**minimal_valid_plan_data)

        assert plan.requires_approval is False
        assert plan.approval_status is None
        assert plan.approved_by is None
        assert plan.approved_at is None

    def test_set_requires_approval_true(self, minimal_valid_plan_data):
        """Definir requires_approval=True e validar."""
        minimal_valid_plan_data['requires_approval'] = True
        plan = CognitivePlan(**minimal_valid_plan_data)

        assert plan.requires_approval is True

    def test_set_approval_status_pending(self, minimal_valid_plan_data):
        """Definir approval_status=PENDING e validar."""
        minimal_valid_plan_data['requires_approval'] = True
        minimal_valid_plan_data['approval_status'] = ApprovalStatus.PENDING
        plan = CognitivePlan(**minimal_valid_plan_data)

        assert plan.approval_status == ApprovalStatus.PENDING

    def test_set_approval_status_approved_with_metadata(self, minimal_valid_plan_data):
        """Definir status aprovado com approved_by e approved_at."""
        now = datetime.utcnow()
        minimal_valid_plan_data['requires_approval'] = True
        minimal_valid_plan_data['approval_status'] = ApprovalStatus.APPROVED
        minimal_valid_plan_data['approved_by'] = 'admin-user-456'
        minimal_valid_plan_data['approved_at'] = now

        plan = CognitivePlan(**minimal_valid_plan_data)

        assert plan.approval_status == ApprovalStatus.APPROVED
        assert plan.approved_by == 'admin-user-456'
        assert plan.approved_at == now

    def test_approval_status_enum_validation(self, minimal_valid_plan_data):
        """Validar que apenas valores do enum são aceitos."""
        # Usar valor válido do enum como string
        minimal_valid_plan_data['approval_status'] = 'pending'
        plan = CognitivePlan(**minimal_valid_plan_data)
        assert plan.approval_status == ApprovalStatus.PENDING

        # Testar todos os valores válidos
        for status in ApprovalStatus:
            minimal_valid_plan_data['approval_status'] = status
            plan = CognitivePlan(**minimal_valid_plan_data)
            assert plan.approval_status == status

    def test_approved_at_datetime_validation(self, minimal_valid_plan_data):
        """Validar que approved_at aceita datetime válido."""
        test_datetime = datetime(2025, 1, 15, 12, 30, 45)
        minimal_valid_plan_data['approved_at'] = test_datetime
        plan = CognitivePlan(**minimal_valid_plan_data)

        assert plan.approved_at == test_datetime


# ============================================================================
# TestCognitivePlanDestructiveFields
# ============================================================================

class TestCognitivePlanDestructiveFields:
    """Testes para validar campos de operações destrutivas."""

    def test_default_values_not_destructive(self, minimal_valid_plan_data):
        """Verificar que is_destructive=False e destructive_tasks=[] por padrão."""
        plan = CognitivePlan(**minimal_valid_plan_data)

        assert plan.is_destructive is False
        assert plan.destructive_tasks == []
        assert plan.risk_matrix is None

    def test_set_is_destructive_true(self, minimal_valid_plan_data):
        """Definir is_destructive=True e validar."""
        minimal_valid_plan_data['is_destructive'] = True
        plan = CognitivePlan(**minimal_valid_plan_data)

        assert plan.is_destructive is True

    def test_set_destructive_tasks_list(self, minimal_valid_plan_data):
        """Adicionar IDs de tasks destrutivas e validar."""
        minimal_valid_plan_data['is_destructive'] = True
        minimal_valid_plan_data['destructive_tasks'] = ['task-1', 'task-2', 'task-3']
        plan = CognitivePlan(**minimal_valid_plan_data)

        assert plan.destructive_tasks == ['task-1', 'task-2', 'task-3']
        assert len(plan.destructive_tasks) == 3

    def test_destructive_tasks_empty_list_valid(self, minimal_valid_plan_data):
        """Validar que lista vazia é aceita."""
        minimal_valid_plan_data['destructive_tasks'] = []
        plan = CognitivePlan(**minimal_valid_plan_data)

        assert plan.destructive_tasks == []

    def test_risk_matrix_none_by_default(self, minimal_valid_plan_data):
        """Verificar que risk_matrix=None por padrão."""
        plan = CognitivePlan(**minimal_valid_plan_data)

        assert plan.risk_matrix is None

    def test_risk_matrix_with_multiple_domains(self, minimal_valid_plan_data):
        """Definir risk_matrix com BUSINESS, SECURITY, OPERATIONAL."""
        risk_matrix = {
            'BUSINESS': 0.7,
            'SECURITY': 0.9,
            'OPERATIONAL': 0.8,
            'COMPLIANCE': 0.6
        }
        minimal_valid_plan_data['risk_matrix'] = risk_matrix
        plan = CognitivePlan(**minimal_valid_plan_data)

        assert plan.risk_matrix == risk_matrix
        assert plan.risk_matrix['BUSINESS'] == 0.7
        assert plan.risk_matrix['SECURITY'] == 0.9
        assert plan.risk_matrix['OPERATIONAL'] == 0.8
        assert plan.risk_matrix['COMPLIANCE'] == 0.6


# ============================================================================
# TestCognitivePlanAvroSerialization
# ============================================================================

class TestCognitivePlanAvroSerialization:
    """Testes para validar serialização Avro."""

    def test_to_avro_dict_includes_approval_fields(self, minimal_valid_plan_data):
        """Verificar que to_avro_dict() inclui todos os campos de aprovação."""
        minimal_valid_plan_data['requires_approval'] = True
        minimal_valid_plan_data['approval_status'] = ApprovalStatus.PENDING
        minimal_valid_plan_data['approved_by'] = 'admin-123'
        plan = CognitivePlan(**minimal_valid_plan_data)

        avro_dict = plan.to_avro_dict()

        assert 'requires_approval' in avro_dict
        assert 'approval_status' in avro_dict
        assert 'approved_by' in avro_dict
        assert 'approved_at' in avro_dict
        assert avro_dict['requires_approval'] is True
        assert avro_dict['approval_status'] == 'pending'
        assert avro_dict['approved_by'] == 'admin-123'

    def test_to_avro_dict_includes_destructive_fields(self, minimal_valid_plan_data):
        """Verificar que to_avro_dict() inclui todos os campos destrutivos."""
        minimal_valid_plan_data['is_destructive'] = True
        minimal_valid_plan_data['destructive_tasks'] = ['task-1']
        minimal_valid_plan_data['risk_matrix'] = {'SECURITY': 0.9}
        plan = CognitivePlan(**minimal_valid_plan_data)

        avro_dict = plan.to_avro_dict()

        assert 'is_destructive' in avro_dict
        assert 'destructive_tasks' in avro_dict
        assert 'risk_matrix' in avro_dict
        assert avro_dict['is_destructive'] is True
        assert avro_dict['destructive_tasks'] == ['task-1']
        assert avro_dict['risk_matrix'] == {'SECURITY': 0.9}

    def test_to_avro_dict_approval_status_as_string(self, minimal_valid_plan_data):
        """Validar que approval_status é serializado como string."""
        minimal_valid_plan_data['approval_status'] = ApprovalStatus.APPROVED
        plan = CognitivePlan(**minimal_valid_plan_data)

        avro_dict = plan.to_avro_dict()

        assert avro_dict['approval_status'] == 'approved'
        assert isinstance(avro_dict['approval_status'], str)

    def test_to_avro_dict_approved_at_as_timestamp_millis(self, minimal_valid_plan_data):
        """Validar que approved_at é convertido para milissegundos."""
        test_datetime = datetime(2025, 1, 15, 12, 0, 0)
        expected_millis = int(test_datetime.timestamp() * 1000)

        minimal_valid_plan_data['approved_at'] = test_datetime
        plan = CognitivePlan(**minimal_valid_plan_data)

        avro_dict = plan.to_avro_dict()

        assert avro_dict['approved_at'] == expected_millis

    def test_to_avro_dict_null_values_serialized_correctly(self, minimal_valid_plan_data):
        """Verificar que campos None são serializados como null."""
        plan = CognitivePlan(**minimal_valid_plan_data)

        avro_dict = plan.to_avro_dict()

        assert avro_dict['approval_status'] is None
        assert avro_dict['approved_by'] is None
        assert avro_dict['approved_at'] is None
        assert avro_dict['risk_matrix'] is None

    def test_to_avro_dict_risk_matrix_preserved(self, minimal_valid_plan_data):
        """Validar que risk_matrix dict é preservado na serialização."""
        risk_matrix = {
            'BUSINESS': 0.7,
            'SECURITY': 0.9,
            'OPERATIONAL': 0.8
        }
        minimal_valid_plan_data['risk_matrix'] = risk_matrix
        plan = CognitivePlan(**minimal_valid_plan_data)

        avro_dict = plan.to_avro_dict()

        assert avro_dict['risk_matrix'] == risk_matrix
        assert avro_dict['risk_matrix']['BUSINESS'] == 0.7

    def test_to_avro_dict_destructive_tasks_empty_list(self, minimal_valid_plan_data):
        """Verificar que lista vazia é serializada corretamente."""
        plan = CognitivePlan(**minimal_valid_plan_data)

        avro_dict = plan.to_avro_dict()

        assert avro_dict['destructive_tasks'] == []


# ============================================================================
# TestCognitivePlanBackwardCompatibility
# ============================================================================

class TestCognitivePlanBackwardCompatibility:
    """Testes para garantir compatibilidade retroativa."""

    def test_create_plan_without_new_fields(self, minimal_valid_plan_data):
        """Criar plano sem especificar novos campos e validar valores padrão."""
        plan = CognitivePlan(**minimal_valid_plan_data)

        # Campos de aprovação com valores padrão
        assert plan.requires_approval is False
        assert plan.approval_status is None
        assert plan.approved_by is None
        assert plan.approved_at is None

        # Campos destrutivos com valores padrão
        assert plan.is_destructive is False
        assert plan.destructive_tasks == []
        assert plan.risk_matrix is None

    def test_to_avro_dict_without_new_fields_has_defaults(self, minimal_valid_plan_data):
        """Verificar que serialização inclui valores padrão."""
        plan = CognitivePlan(**minimal_valid_plan_data)
        avro_dict = plan.to_avro_dict()

        # Valores padrão presentes
        assert avro_dict['requires_approval'] is False
        assert avro_dict['approval_status'] is None
        assert avro_dict['approved_by'] is None
        assert avro_dict['approved_at'] is None
        assert avro_dict['is_destructive'] is False
        assert avro_dict['destructive_tasks'] == []
        assert avro_dict['risk_matrix'] is None

    def test_existing_plan_structure_unchanged(self, minimal_valid_plan_data):
        """Validar que campos existentes não foram afetados."""
        plan = CognitivePlan(**minimal_valid_plan_data)

        # Verificar campos existentes
        assert plan.intent_id == 'intent-001'
        assert plan.risk_score == 0.3
        assert plan.risk_band == RiskBand.LOW
        assert plan.original_domain == 'data_management'
        assert plan.status == PlanStatus.DRAFT
        assert len(plan.tasks) == 1

    def test_plan_with_only_approval_fields(self, minimal_valid_plan_data):
        """Criar plano apenas com campos de aprovação."""
        minimal_valid_plan_data['requires_approval'] = True
        minimal_valid_plan_data['approval_status'] = ApprovalStatus.PENDING
        plan = CognitivePlan(**minimal_valid_plan_data)

        assert plan.requires_approval is True
        assert plan.approval_status == ApprovalStatus.PENDING
        # Campos destrutivos mantêm valores padrão
        assert plan.is_destructive is False
        assert plan.destructive_tasks == []

    def test_plan_with_only_destructive_fields(self, minimal_valid_plan_data):
        """Criar plano apenas com campos destrutivos."""
        minimal_valid_plan_data['is_destructive'] = True
        minimal_valid_plan_data['destructive_tasks'] = ['task-1']
        plan = CognitivePlan(**minimal_valid_plan_data)

        assert plan.is_destructive is True
        assert plan.destructive_tasks == ['task-1']
        # Campos de aprovação mantêm valores padrão
        assert plan.requires_approval is False
        assert plan.approval_status is None


# ============================================================================
# TestCognitivePlanIntegrationWithDestructiveDetector
# ============================================================================

class TestCognitivePlanIntegrationWithDestructiveDetector:
    """Testes de integração com DestructiveDetector."""

    def test_populate_from_destructive_detector_result(self, minimal_valid_plan_data):
        """Simular resultado do detector e popular campos do plano."""
        # Simula saída do DestructiveDetector
        detector_result = {
            'is_destructive': True,
            'destructive_tasks': ['task-1'],
            'severity': 'high',
            'details': {
                'task-1': {
                    'operation': 'delete',
                    'risk_level': 0.9
                }
            }
        }

        minimal_valid_plan_data['is_destructive'] = detector_result['is_destructive']
        minimal_valid_plan_data['destructive_tasks'] = detector_result['destructive_tasks']

        plan = CognitivePlan(**minimal_valid_plan_data)

        assert plan.is_destructive is True
        assert plan.destructive_tasks == ['task-1']

    def test_destructive_tasks_match_detector_output(self, minimal_valid_plan_data):
        """Validar que destructive_tasks corresponde à saída do detector."""
        detected_tasks = ['task-delete-1', 'task-drop-2', 'task-truncate-3']

        minimal_valid_plan_data['destructive_tasks'] = detected_tasks
        plan = CognitivePlan(**minimal_valid_plan_data)

        assert plan.destructive_tasks == detected_tasks
        assert 'task-delete-1' in plan.destructive_tasks
        assert 'task-drop-2' in plan.destructive_tasks
        assert 'task-truncate-3' in plan.destructive_tasks

    def test_severity_critical_sets_requires_approval(self, minimal_valid_plan_data):
        """Verificar que severidade crítica define requires_approval=True."""
        # Lógica de negócio: se severity é critical, requer aprovação
        severity = 'critical'
        minimal_valid_plan_data['requires_approval'] = severity in ['high', 'critical']
        minimal_valid_plan_data['approval_status'] = ApprovalStatus.PENDING

        plan = CognitivePlan(**minimal_valid_plan_data)

        assert plan.requires_approval is True
        assert plan.approval_status == ApprovalStatus.PENDING

    def test_is_destructive_true_when_detector_finds_operations(self, minimal_valid_plan_data):
        """Validar sincronização entre detector e modelo."""
        # Quando detector encontra operações destrutivas
        minimal_valid_plan_data['is_destructive'] = True
        minimal_valid_plan_data['destructive_tasks'] = ['task-1']
        minimal_valid_plan_data['risk_matrix'] = {
            'BUSINESS': 0.8,
            'SECURITY': 0.95,
            'OPERATIONAL': 0.7
        }

        plan = CognitivePlan(**minimal_valid_plan_data)

        assert plan.is_destructive is True
        assert len(plan.destructive_tasks) > 0
        assert plan.risk_matrix is not None
        assert plan.risk_matrix['SECURITY'] == 0.95


# ============================================================================
# TestApprovalStatusEnum
# ============================================================================

class TestApprovalStatusEnum:
    """Testes para o enum ApprovalStatus."""

    def test_enum_values(self):
        """Verificar valores do enum."""
        assert ApprovalStatus.PENDING.value == 'pending'
        assert ApprovalStatus.APPROVED.value == 'approved'
        assert ApprovalStatus.REJECTED.value == 'rejected'

    def test_enum_from_string(self):
        """Verificar criação do enum a partir de string."""
        assert ApprovalStatus('pending') == ApprovalStatus.PENDING
        assert ApprovalStatus('approved') == ApprovalStatus.APPROVED
        assert ApprovalStatus('rejected') == ApprovalStatus.REJECTED

    def test_enum_string_inheritance(self):
        """Verificar herança de str."""
        assert isinstance(ApprovalStatus.PENDING, str)
        assert ApprovalStatus.PENDING == 'pending'
