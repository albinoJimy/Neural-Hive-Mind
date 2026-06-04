"""
Unit tests for neural_hive_context models.

TDD approach: tests first, then implementation.
"""

import pytest
from neural_hive_context.models.rich_context import (
    RichContext,
    IntentContext,
    SystemContext,
    TemporalContext,
    SecurityContext,
    ConversationContext,
)
from neural_hive_context.models.workflow import (
    WorkflowType,
    WorkflowClassification,
    WorkflowSignal,
)
from neural_hive_context.models.pii import (
    PIIType,
    PIIEntity,
    PIIResult,
    PIIDetectionConfig,
    PIIRiskLevel,
)


class TestIntentContext:
    """Tests para IntentContext."""

    def test_create_intent_context_minimal(self):
        """Deve criar IntentContext com apenas raw_text."""
        ctx = IntentContext(raw_text="test intent")
        assert ctx.raw_text == "test intent"
        assert ctx.intent_type is None
        assert ctx.entities == {}
        assert ctx.semantic_features == {}

    def test_create_intent_context_full(self):
        """Deve criar IntentContext com todos os campos."""
        ctx = IntentContext(
            raw_text="analyze data",
            intent_type="analysis",
            entities={"domain": "data"},
            semantic_features={"confidence": 0.9},
        )
        assert ctx.raw_text == "analyze data"
        assert ctx.intent_type == "analysis"
        assert ctx.entities == {"domain": "data"}
        assert ctx.semantic_features == {"confidence": 0.9}


class TestSystemContext:
    """Tests para SystemContext."""

    def test_create_system_context_empty(self):
        """Deve criar SystemContext vazio com defaults."""
        ctx = SystemContext()
        assert ctx.affected_services == []
        assert ctx.service_states == {}
        assert ctx.resource_utilization == {}
        assert ctx.active_workflows == 0

    def test_create_system_context_full(self):
        """Deve criar SystemContext com todos os campos."""
        ctx = SystemContext(
            affected_services=["worker-agents", "analyst-agents"],
            service_states={"worker-agents": "running"},
            resource_utilization={"worker-agents": 45.0},
            active_workflows=5,
        )
        assert len(ctx.affected_services) == 2
        assert ctx.service_states["worker-agents"] == "running"
        assert ctx.resource_utilization["worker-agents"] == 45.0
        assert ctx.active_workflows == 5


class TestTemporalContext:
    """Tests para TemporalContext."""

    def test_create_temporal_context(self):
        """Deve criar TemporalContext com todos os campos."""
        ctx = TemporalContext(
            current_time="2026-04-23T10:30:00Z",
            time_of_day="morning",
            day_of_week="Wednesday",
            is_business_hours=True,
        )
        assert ctx.time_of_day == "morning"
        assert ctx.is_business_hours is True


class TestSecurityContext:
    """Tests para SecurityContext."""

    def test_create_security_context_minimal(self):
        """Deve criar SecurityContext com defaults."""
        ctx = SecurityContext()
        assert ctx.user_id is None
        assert ctx.risk_score == 0.0
        assert ctx.requires_approval is False

    def test_risk_score_validation(self):
        """Deve validar range de risk_score."""
        with pytest.raises(ValueError):
            SecurityContext(risk_score=1.5)  # > 1.0

        with pytest.raises(ValueError):
            SecurityContext(risk_score=-0.1)  # < 0.0


class TestConversationContext:
    """Tests para ConversationContext."""

    def test_create_conversation_context(self):
        """Deve criar ConversationContext com histórico."""
        ctx = ConversationContext(
            turn_count=3, previous_intents=["intent1", "intent2"], has_repetition=False
        )
        assert ctx.turn_count == 3
        assert len(ctx.previous_intents) == 2


class TestRichContext:
    """Tests para RichContext."""

    @pytest.fixture
    def valid_rich_context(self):
        """RichContext válido para testes."""
        return RichContext(
            intent=IntentContext(raw_text="test"),
            system=SystemContext(),
            temporal=TemporalContext(
                current_time="2026-04-23T10:30:00Z",
                time_of_day="morning",
                day_of_week="Wednesday",
                is_business_hours=True,
            ),
            security=SecurityContext(),
            conversation=ConversationContext(),
            context_id="test-ctx-123",
            created_at="2026-04-23T10:30:00Z",
        )

    def test_create_rich_context(self, valid_rich_context):
        """Deve criar RichContext com todas as dimensões."""
        ctx = valid_rich_context
        assert ctx.context_id == "test-ctx-123"
        assert ctx.intent.raw_text == "test"
        assert ctx.ttl_seconds == 300  # default


class TestWorkflowType:
    """Tests para WorkflowType enum."""

    def test_workflow_type_values(self):
        """Deve ter os valores corretos."""
        assert WorkflowType.ORCHESTRATION == "orchestration"
        assert WorkflowType.GENERATION == "generation"


class TestWorkflowSignal:
    """Tests para WorkflowSignal."""

    def test_create_workflow_signal(self):
        """Deve criar WorkflowSignal com cálculo de contribution."""
        signal = WorkflowSignal(name="test_signal", value=0.8, weight=0.5, contribution=0.4)
        assert signal.name == "test_signal"
        assert signal.contribution == 0.4

    def test_value_range_validation(self):
        """Deve validar range de value."""
        with pytest.raises(ValueError):
            WorkflowSignal(name="test", value=1.5, weight=0.5, contribution=0.75)  # > 1.0

    def test_weight_range_validation(self):
        """Deve validar range de weight."""
        with pytest.raises(ValueError):
            WorkflowSignal(name="test", value=0.8, weight=1.2, contribution=0.96)  # > 1.0


class TestWorkflowClassification:
    """Tests para WorkflowClassification."""

    def test_create_workflow_classification_orchestration(self):
        """Deve criar classificação para ORCHESTRATION."""
        classification = WorkflowClassification(
            workflow_type=WorkflowType.ORCHESTRATION,
            confidence=0.85,
            reasoning="Multiple services affected",
            signals={"system_context": 0.8},
            raw_score=0.72,
        )
        assert classification.workflow_type == WorkflowType.ORCHESTRATION
        assert classification.confidence == 0.85
        assert "multiple" in classification.reasoning.lower()

    def test_confidence_range_validation(self):
        """Deve validar range de confidence."""
        with pytest.raises(ValueError):
            WorkflowClassification(
                workflow_type=WorkflowType.GENERATION,
                confidence=1.5,  # > 1.0
                reasoning="test",
                signals={},
                raw_score=0.5,
            )


class TestPIIType:
    """Tests para PIIType enum."""

    def test_pii_type_values(self):
        """Deve ter os tipos corretos."""
        assert PIIType.EMAIL == "email"
        assert PIIType.CPF == "cpf"
        assert PIIType.CREDIT_CARD == "credit_card"


class TestPIIEntity:
    """Tests para PIIEntity."""

    def test_create_pii_entity(self):
        """Deve criar PIIEntity válida."""
        entity = PIIEntity(
            type=PIIType.EMAIL,
            value="user@example.com",
            start_pos=10,
            end_pos=26,
            confidence=0.95,
            masked_value="u***@example.com",
        )
        assert entity.type == PIIType.EMAIL
        assert entity.start_pos < entity.end_pos
        assert entity.masked_value is not None


class TestPIIResult:
    """Tests para PIIResult."""

    def test_create_pii_result_no_pii(self):
        """Deve criar PIIResult sem PII detectado."""
        result = PIIResult(has_pii=False)
        assert result.has_pii is False
        assert result.entities == []
        assert result.risk_level == PIIRiskLevel.NONE

    def test_create_pii_result_with_pii(self):
        """Deve criar PIIResult com PII detectado."""
        result = PIIResult(
            has_pii=True,
            entities=[
                PIIEntity(
                    type=PIIType.EMAIL,
                    value="test@example.com",
                    start_pos=0,
                    end_pos=16,
                    confidence=0.9,
                )
            ],
            risk_level=PIIRiskLevel.MEDIUM,
            requires_redaction=True,
        )
        assert result.has_pii is True
        assert len(result.entities) == 1
        assert result.risk_level == PIIRiskLevel.MEDIUM


class TestPIIDetectionConfig:
    """Tests para PIIDetectionConfig."""

    def test_create_config_defaults(self):
        """Deve criar config com valores padrão."""
        config = PIIDetectionConfig()
        assert config.enabled is True
        assert config.mask_by_default is False
        assert config.min_confidence == 0.7
        assert config.strict_mode is False

    def test_min_confidence_validation(self):
        """Deve validar range de min_confidence."""
        with pytest.raises(ValueError):
            PIIDetectionConfig(min_confidence=1.5)
