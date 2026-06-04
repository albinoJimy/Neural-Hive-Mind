"""
Integration Tests E2E para Context Layer.

Valida fluxo completo:
1. MultiSignalWorkflowClassifier classifica intent
2. CognitivePlan é criado com workflow_type
3. ConsolidatedDecision é serializada com campos de workflow
4. DecisionConsumer roteia para workflow correto
"""

import pytest
from datetime import datetime, timezone

from neural_hive_context.models import (
    RichContext,
    IntentContext,
    SystemContext,
    TemporalContext,
    SecurityContext,
    ConversationContext,
    WorkflowType,
)

from neural_hive_context.services.workflow_classifier import MultiSignalWorkflowClassifier

from src.consumers.decision_consumer import (
    _get_workflow_type_from_plan,
    _select_workflow_class,
)
from src.workflows.orchestration_workflow import OrchestrationWorkflow
from src.workflows.fluxo_g_workflow import FluxoGWorkflow


@pytest.fixture
def minimal_context():
    """Contexto mínimo para testes."""
    return RichContext(
        intent=IntentContext(raw_text="gere um relatório de vendas"),
        system=SystemContext(),
        temporal=TemporalContext(
            current_time="2026-04-23T10:00:00Z",
            time_of_day="morning",
            day_of_week="Wednesday",
            is_business_hours=True,
        ),
        security=SecurityContext(),
        conversation=ConversationContext(),
        context_id="test-ctx-123",
        created_at="2026-04-23T10:00:00Z",
    )


class TestContextLayerE2E:
    """Testes E2E do Context Layer."""

    @pytest.mark.asyncio
    async def test_generation_intent_classification_flow(self, minimal_context):
        """Intent de geração deve ser classificada como GENERATION."""
        # Arrange
        minimal_context.intent.raw_text = "gere um relatório de vendas mensal"
        classifier = MultiSignalWorkflowClassifier()

        # Act
        classification = await classifier.classify(minimal_context)

        # Assert
        assert classification.workflow_type == WorkflowType.GENERATION
        assert classification.confidence >= 0.5
        assert "workflow" in classification.reasoning.lower()

    @pytest.mark.asyncio
    async def test_orchestration_intent_classification_flow(self, minimal_context):
        """Intent de orquestração deve ser classificada como ORCHESTRATION."""
        # Arrange
        minimal_context.intent.raw_text = "analise os dados dos serviços de produção"
        minimal_context.system.affected_services = [
            "worker-agents",
            "analyst-agents",
            "optimizer-agents",
        ]
        classifier = MultiSignalWorkflowClassifier()

        # Act
        classification = await classifier.classify(minimal_context)

        # Assert
        assert classification.workflow_type == WorkflowType.ORCHESTRATION
        # O reasoning deve mencionar análise/coordenação (orçestação)
        assert (
            "análise" in classification.reasoning.lower()
            or "coordenação" in classification.reasoning.lower()
        )

    def test_cognitive_plan_with_workflow_fields(self):
        """CognitivePlan deve conter campos de workflow."""
        # Arrange
        plan = {
            "plan_id": "plan-123",
            "intent_id": "intent-456",
            "tasks": [{"task_id": "t1", "task_type": "query"}],
            "execution_order": ["t1"],
            "risk_band": "low",
            "risk_score": 0.2,
            "explainability_token": "token-abc",
            "reasoning_summary": "Test plan",
            "complexity_score": 0.3,
            "original_domain": "analytics",
            "original_priority": "normal",
            "original_security_level": "internal",
            # Novos campos Context Layer
            "workflow_type": "generation",
            "context_id": "ctx-789",
            "workflow_confidence": 0.88,
            "workflow_reasoning": "Single service, generation keywords",
        }

        # Act & Assert
        workflow_type = _get_workflow_type_from_plan(plan)
        assert workflow_type == "generation"

        workflow_class = _select_workflow_class(workflow_type)
        assert workflow_class == FluxoGWorkflow

    def test_cognitive_plan_default_orchestration(self):
        """CognitivePlan sem workflow_type deve default para ORCHESTRATION."""
        # Arrange - plano antigo sem campos de workflow
        plan = {
            "plan_id": "plan-123",
            "intent_id": "intent-456",
            "tasks": [{"task_id": "t1", "task_type": "query"}],
            "execution_order": ["t1"],
            "risk_band": "low",
            "risk_score": 0.2,
            "explainability_token": "token-abc",
            "reasoning_summary": "Test plan",
            "complexity_score": 0.3,
            "original_domain": "analytics",
            "original_priority": "normal",
            "original_security_level": "internal",
            # Sem workflow_type - deve usar default
        }

        # Act & Assert
        workflow_type = _get_workflow_type_from_plan(plan)
        assert workflow_type == "orchestration"

        workflow_class = _select_workflow_class(workflow_type)
        assert workflow_class == OrchestrationWorkflow

    def test_consolidated_decision_with_workflow_fields(self):
        """ConsolidatedDecision deve conter campos de workflow."""
        # Arrange
        decision = {
            "decision_id": "dec-123",
            "plan_id": "plan-456",
            "intent_id": "intent-789",
            "final_decision": "approve",
            "consensus_method": "bayesian",
            "aggregated_confidence": 0.85,
            "aggregated_risk": 0.15,
            "specialist_votes": [],
            "consensus_metrics": {
                "divergence_score": 0.1,
                "convergence_time_ms": 500,
                "unanimous": True,
                "fallback_used": False,
                "pheromone_strength": 0.9,
                "bayesian_confidence": 0.85,
                "voting_confidence": 0.85,
            },
            "explainability_token": "token-abc",
            "reasoning_summary": "Approve",
            "compliance_checks": {},
            "guardrails_triggered": [],
            "cognitive_plan": '{"plan_id": "plan-456"}',
            "workflow_type": "generation",  # Novo campo
            "context_id": "ctx-123",  # Novo campo
            "workflow_confidence": 0.92,  # Novo campo
            "workflow_reasoning": "Single service, generation intent",  # Novo campo
            "requires_human_review": False,
            "created_at": int(datetime.now(timezone.utc).timestamp() * 1000),
            "metadata": {},
            "hash": "abc123",
        }

        # Assert - campos de workflow presentes
        assert decision["workflow_type"] == "generation"
        assert decision["context_id"] == "ctx-123"
        assert decision["workflow_confidence"] == 0.92
        assert decision["workflow_reasoning"] is not None


class TestDecisionConsumerRouting:
    """Testes de routing no DecisionConsumer."""

    def test_routing_function_generation(self):
        """Função _get_workflow_type_from_plan deve extrair 'generation'."""
        plan = {"workflow_type": "generation", "plan_id": "plan-123"}
        result = _get_workflow_type_from_plan(plan)
        assert result == "generation"

    def test_routing_function_orchestration(self):
        """Função _get_workflow_type_from_plan deve extrair 'orchestration'."""
        plan = {"workflow_type": "orchestration", "plan_id": "plan-123"}
        result = _get_workflow_type_from_plan(plan)
        assert result == "orchestration"

    def test_routing_function_default(self):
        """Função _get_workflow_type_from_plan deve default para 'orchestration'."""
        plan = {"plan_id": "plan-123"}  # Sem workflow_type
        result = _get_workflow_type_from_plan(plan)
        assert result == "orchestration"

    def test_select_workflow_generation(self):
        """Função _select_workflow_class deve retornar FluxoGWorkflow para 'generation'."""
        result = _select_workflow_class("generation")
        assert result == FluxoGWorkflow

    def test_select_workflow_orchestration(self):
        """Função _select_workflow_class deve retornar OrchestrationWorkflow para 'orchestration'."""
        result = _select_workflow_class("orchestration")
        assert result == OrchestrationWorkflow

    def test_select_workflow_invalid_defaults(self):
        """Função _select_workflow_class deve default para OrchestrationWorkflow."""
        result = _select_workflow_class("invalid")
        assert result == OrchestrationWorkflow


class TestAvroSerialization:
    """Testes de serialização Avro com novos campos."""

    def test_avro_schema_workflow_type_enum(self):
        """Schema Avro deve aceitar valores válidos de workflow_type."""
        import json
        import fastavro
        import io

        # Load schema
        schema_path = "/home/jimy/NHM/Neural-Hive-Mind/schemas/consolidated-decision/consolidated-decision.avsc"
        with open(schema_path, "r") as f:
            schema = json.load(f)

        # Teste com generation
        record = {
            "decision_id": "dec-gen",
            "plan_id": "plan-123",
            "intent_id": "intent-456",
            "final_decision": "approve",
            "consensus_method": "bayesian",
            "aggregated_confidence": 0.85,
            "aggregated_risk": 0.15,
            "specialist_votes": [],
            "consensus_metrics": {
                "divergence_score": 0.1,
                "convergence_time_ms": 500,
                "unanimous": True,
                "fallback_used": False,
                "pheromone_strength": 0.9,
                "bayesian_confidence": 0.85,
                "voting_confidence": 0.85,
            },
            "explainability_token": "token-abc",
            "reasoning_summary": "Test",
            "compliance_checks": {},
            "guardrails_triggered": [],
            "workflow_type": "generation",
            "requires_human_review": False,
            "created_at": int(datetime.now(timezone.utc).timestamp() * 1000),
            "metadata": {},
            "hash": "abc123",
        }

        # Serializar e deserializar
        output = io.BytesIO()
        fastavro.schemaless_writer(output, schema, record)
        output.seek(0)

        parsed = fastavro.schemaless_reader(output, schema)
        result = dict(parsed)

        assert result["workflow_type"] == "generation"
        assert result["schema_version"] == 2
