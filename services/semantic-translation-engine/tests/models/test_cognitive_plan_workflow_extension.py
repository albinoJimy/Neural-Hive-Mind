"""
Tests para CognitivePlan workflow_type extension.

TDD: Tests primeiro, implementação depois.
"""

import pytest
from datetime import datetime
from src.models.cognitive_plan import (
    CognitivePlan,
    TaskNode,
    PlanStatus,
    RiskBand,
    WorkflowType,
)


class TestWorkflowTypeExtension:
    """Tests para extensão workflow_type do CognitivePlan."""

    @pytest.fixture
    def minimal_plan_data(self):
        """Dados mínimos para criar CognitivePlan."""
        return {
            "plan_id": "test-plan-123",
            "intent_id": "intent-456",
            "tasks": [
                TaskNode(
                    task_id="task1",
                    task_type="query",
                    description="Test task"
                )
            ],
            "execution_order": ["task1"],
            "risk_score": 0.3,
            "risk_band": RiskBand.LOW,
            "explainability_token": "token123",
            "reasoning_summary": "Test reasoning",
            "complexity_score": 0.5,
            "original_domain": "test",
            "original_priority": "normal",
            "original_security_level": "standard",
        }

    def test_default_workflow_type_is_orchestration(self, minimal_plan_data):
        """workflow_type deve default para ORCHESTRATION (non-breaking)."""
        plan = CognitivePlan(**minimal_plan_data)
        assert plan.workflow_type == WorkflowType.ORCHESTRATION

    def test_workflow_type_can_be_set_to_generation(self, minimal_plan_data):
        """workflow_type pode ser explicitamente setado para GENERATION."""
        minimal_plan_data["workflow_type"] = WorkflowType.GENERATION
        plan = CognitivePlan(**minimal_plan_data)
        assert plan.workflow_type == WorkflowType.GENERATION

    def test_context_id_optional_with_default(self, minimal_plan_data):
        """context_id deve ser opcional com default None."""
        plan = CognitivePlan(**minimal_plan_data)
        assert plan.context_id is None

    def test_context_id_can_be_set(self, minimal_plan_data):
        """context_id pode ser explicitamente setado."""
        minimal_plan_data["context_id"] = "ctx-abc-123"
        plan = CognitivePlan(**minimal_plan_data)
        assert plan.context_id == "ctx-abc-123"

    def test_workflow_confidence_default(self, minimal_plan_data):
        """workflow_confidence deve default para 0.5."""
        plan = CognitivePlan(**minimal_plan_data)
        assert plan.workflow_confidence == 0.5

    def test_workflow_confidence_range_validation(self, minimal_plan_data):
        """workflow_confidence deve estar entre 0.0 e 1.0."""
        minimal_plan_data["workflow_confidence"] = 0.85
        plan = CognitivePlan(**minimal_plan_data)
        assert plan.workflow_confidence == 0.85

        with pytest.raises(ValueError):
            minimal_plan_data["workflow_confidence"] = 1.5
            CognitivePlan(**minimal_plan_data)

    def test_workflow_reasoning_optional(self, minimal_plan_data):
        """workflow_reasoning deve ser opcional."""
        plan = CognitivePlan(**minimal_plan_data)
        assert plan.workflow_reasoning is None

    def test_workflow_reasoning_can_be_set(self, minimal_plan_data):
        """workflow_reasoning pode ser setado."""
        minimal_plan_data["workflow_reasoning"] = "Generation workflow selected due to create keyword"
        plan = CognitivePlan(**minimal_plan_data)
        assert "Generation workflow" in plan.workflow_reasoning

    def test_to_avro_dict_includes_workflow_fields(self, minimal_plan_data):
        """to_avro_dict deve incluir os novos campos workflow."""
        minimal_plan_data.update({
            "workflow_type": WorkflowType.GENERATION,
            "context_id": "ctx-123",
            "workflow_confidence": 0.85,
            "workflow_reasoning": "Test reasoning"
        })
        plan = CognitivePlan(**minimal_plan_data)
        avro_dict = plan.to_avro_dict()

        assert avro_dict["workflow_type"] == "generation"
        assert avro_dict["context_id"] == "ctx-123"
        assert avro_dict["workflow_confidence"] == 0.85
        assert avro_dict["workflow_reasoning"] == "Test reasoning"

    def test_backward_compatibility_missing_workflow_fields(self, minimal_plan_data):
        """
        Deserialização de mensagens antigas (sem campos workflow)
        deve usar defaults e não quebrar.
        """
        # Simula mensagem Avro antiga (sem campos workflow)
        avro_dict_old = {
            "plan_id": "old-plan-123",
            "intent_id": "old-intent-456",
            "tasks": [
                {
                    "task_id": "task1",
                    "task_type": "query",
                    "description": "Old task",
                    "dependencies": [],
                    "estimated_duration_ms": None,
                    "required_capabilities": [],
                    "parameters": {},
                    "metadata": {},
                }
            ],
            "execution_order": ["task1"],
            "risk_score": 0.3,
            "risk_band": "low",
            "risk_factors": {},
            "explainability_token": "old-token",
            "reasoning_summary": "Old reasoning",
            "status": "draft",
            "created_at": 1234567890000,
            "valid_until": None,
            "estimated_total_duration_ms": None,
            "complexity_score": 0.5,
            "original_domain": "test",
            "original_priority": "normal",
            "original_security_level": "standard",
            "metadata": {},
            "requires_approval": False,
            "approval_status": None,
            "approved_by": None,
            "approved_at": None,
            "is_destructive": False,
            "destructive_tasks": [],
            "risk_matrix": None,
            "schema_version": 1,
            # NOTA: Sem workflow_type, context_id, workflow_confidence, workflow_reasoning
        }

        # Tenta criar plano com dados antigos
        # Deve usar defaults para campos faltantes
        # Isso será implementado no from_avro_dict() que criaremos
        # Por enquanto, testamos que o modelo aceita defaults
        plan_data = {
            "plan_id": avro_dict_old["plan_id"],
            "intent_id": avro_dict_old["intent_id"],
            "tasks": [
                TaskNode(**avro_dict_old["tasks"][0])
            ],
            "execution_order": avro_dict_old["execution_order"],
            "risk_score": avro_dict_old["risk_score"],
            "risk_band": RiskBand(avro_dict_old["risk_band"]),
            "explainability_token": avro_dict_old["explainability_token"],
            "reasoning_summary": avro_dict_old["reasoning_summary"],
            "complexity_score": avro_dict_old["complexity_score"],
            "original_domain": avro_dict_old["original_domain"],
            "original_priority": avro_dict_old["original_priority"],
            "original_security_level": avro_dict_old["original_security_level"],
        }

        plan = CognitivePlan(**plan_data)
        # Deve ter defaults
        assert plan.workflow_type == WorkflowType.ORCHESTRATION
        assert plan.context_id is None
        assert plan.workflow_confidence == 0.5


class TestWorkflowTypeEnum:
    """Tests para WorkflowType enum."""

    def test_workflow_type_values(self):
        """WorkflowType deve ter valores corretos."""
        assert WorkflowType.ORCHESTRATION == "orchestration"
        assert WorkflowType.GENERATION == "generation"

    def test_workflow_type_is_str_enum(self):
        """WorkflowType deve ser compatível com string."""
        assert isinstance(WorkflowType.ORCHESTRATION, str)
        assert WorkflowType.ORCHESTRATION == "orchestration"
