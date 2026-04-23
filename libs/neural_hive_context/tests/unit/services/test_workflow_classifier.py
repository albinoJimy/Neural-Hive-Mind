"""
Tests para MultiSignalWorkflowClassifier.

TDD approach.
"""

import pytest
from datetime import datetime

from neural_hive_context.services.workflow_classifier import MultiSignalWorkflowClassifier
from neural_hive_context.models import (
    RichContext,
    IntentContext,
    SystemContext,
    TemporalContext,
    SecurityContext,
    ConversationContext,
    WorkflowType,
)


class TestMultiSignalWorkflowClassifier:
    """Tests para MultiSignalWorkflowClassifier."""

    @pytest.fixture
    def minimal_context(self):
        """Contexto mínimo para testes."""
        return RichContext(
            intent=IntentContext(raw_text="test intent"),
            system=SystemContext(),
            temporal=TemporalContext(
                current_time="2026-04-23T10:00:00Z",
                time_of_day="morning",
                day_of_week="Wednesday",
                is_business_hours=True
            ),
            security=SecurityContext(),
            conversation=ConversationContext(),
            context_id="test-ctx-123",
            created_at="2026-04-23T10:00:00Z"
        )

    @pytest.mark.asyncio
    async def test_classify_returns_workflow_classification(self, minimal_context):
        """classify deve retornar WorkflowClassification válida."""
        classifier = MultiSignalWorkflowClassifier()
        result = await classifier.classify(minimal_context)

        assert result.workflow_type in [WorkflowType.ORCHESTRATION, WorkflowType.GENERATION]
        assert 0.0 <= result.confidence <= 1.0
        assert result.reasoning
        assert isinstance(result.signals, dict)
        assert 0.0 <= result.raw_score <= 1.0

    @pytest.mark.asyncio
    async def test_generation_keywords_favor_generation_workflow(self, minimal_context):
        """Keywords de geração devem favorecer workflow GENERATION."""
        minimal_context.intent.raw_text = "gere um relatório de vendas"
        classifier = MultiSignalWorkflowClassifier()
        result = await classifier.classify(minimal_context)

        # Keywords "gere" e "relatório" devem favorecer generation
        assert result.workflow_type == WorkflowType.GENERATION

    @pytest.mark.asyncio
    async def test_orchestration_keywords_favor_orchestration_workflow(self, minimal_context):
        """Keywords de orquestração devem favorecer workflow ORCHESTRATION."""
        minimal_context.intent.raw_text = "analise os dados dos serviços"
        classifier = MultiSignalWorkflowClassifier()
        result = await classifier.classify(minimal_context)

        # Keywords "analise" e "serviços" devem favorecer orchestration
        assert result.workflow_type == WorkflowType.ORCHESTRATION

    @pytest.mark.asyncio
    async def test_multiple_services_favor_orchestration(self, minimal_context):
        """Múltiplos serviços afetados devem favorecer ORCHESTRATION."""
        minimal_context.system.affected_services = [
            "worker-agents",
            "analyst-agents",
            "scout-agents",
            "optimizer-agents"
        ]
        classifier = MultiSignalWorkflowClassifier()
        result = await classifier.classify(minimal_context)

        assert result.workflow_type == WorkflowType.ORCHESTRATION
        assert "múltiplos serviços" in result.reasoning.lower()

    @pytest.mark.asyncio
    async def test_pii_signal_favors_orchestration(self, minimal_context):
        """Presença de PII deve favorecer ORCHESTRATION."""
        # Mock PII detector que retorna PII detectado
        class MockPIIDetector:
            def detect(self, text):
                from neural_hive_context.models import PIIResult, PIIRiskLevel
                return PIIResult(
                    has_pii=True,
                    entities=[],
                    risk_level=PIIRiskLevel.HIGH,
                    requires_redaction=True
                )

        classifier = MultiSignalWorkflowClassifier(pii_detector=MockPIIDetector())
        result = await classifier.classify(minimal_context)

        # PII deve favorecer orchestration
        assert result.workflow_type == WorkflowType.ORCHESTRATION
        assert "dados sensíveis" in result.reasoning.lower()

    @pytest.mark.asyncio
    async def test_confidence_calculation(self, minimal_context):
        """Confidence deve ser calculada baseado na consistência dos sinais."""
        classifier = MultiSignalWorkflowClassifier()
        result = await classifier.classify(minimal_context)

        # Confiança deve estar em range válido
        assert 0.5 <= result.confidence <= 0.95

    @pytest.mark.asyncio
    async def test_signal_weights_sum_to_one(self):
        """Pesos dos sinais devem somar 1.0."""
        weights = MultiSignalWorkflowClassifier.SIGNAL_WEIGHTS
        total = sum(weights.values())
        assert abs(total - 1.0) < 0.001

    @pytest.mark.asyncio
    async def test_single_service_with_generation_keywords(self, minimal_context):
        """Serviço único + keywords geração = forte sinal para GENERATION."""
        minimal_context.system.affected_services = ["worker-agents"]
        minimal_context.intent.raw_text = "crie um script de backup"

        classifier = MultiSignalWorkflowClassifier()
        result = await classifier.classify(minimal_context)

        assert result.workflow_type == WorkflowType.GENERATION

    @pytest.mark.asyncio
    async def test_high_active_workflows_favors_orchestration(self, minimal_context):
        """Muitos workflows ativos devem favorecer ORCHESTRATION."""
        minimal_context.system.active_workflows = 8
        classifier = MultiSignalWorkflowClassifier()
        result = await classifier.classify(minimal_context)

        assert result.workflow_type == WorkflowType.ORCHESTRATION

    @pytest.mark.asyncio
    async def test_reasoning_contains_explanation(self, minimal_context):
        """Reasoning deve conter explicação compreensível."""
        minimal_context.intent.raw_text = "gere um relatório"
        classifier = MultiSignalWorkflowClassifier()
        result = await classifier.classify(minimal_context)

        assert result.reasoning
        assert len(result.reasoning) > 10
        # Deve mencionar o workflow selecionado
        assert "workflow" in result.reasoning.lower()


class TestSignalExtraction:
    """Tests para extração individual de sinais."""

    @pytest.fixture
    def classifier(self):
        return MultiSignalWorkflowClassifier()

    def test_user_input_signal_generation_keywords(self, classifier):
        """Keywords de geração devem retornar score baixo."""
        context = RichContext(
            intent=IntentContext(raw_text="gere um relatório"),
            system=SystemContext(),
            temporal=TemporalContext(
                current_time="2026-04-23T10:00:00Z",
                time_of_day="morning",
                day_of_week="Wednesday",
                is_business_hours=True
            ),
            security=SecurityContext(),
            conversation=ConversationContext(),
            context_id="test",
            created_at="2026-04-23T10:00:00Z"
        )

        signal = classifier._extract_user_input_signal(context)
        # Keywords de geração = score baixo (< 0.5)
        assert signal < 0.5

    def test_user_input_signal_orchestration_keywords(self, classifier):
        """Keywords de orquestração devem retornar score alto."""
        context = RichContext(
            intent=IntentContext(raw_text="analise os dados"),
            system=SystemContext(),
            temporal=TemporalContext(
                current_time="2026-04-23T10:00:00Z",
                time_of_day="morning",
                day_of_week="Wednesday",
                is_business_hours=True
            ),
            security=SecurityContext(),
            conversation=ConversationContext(),
            context_id="test",
            created_at="2026-04-23T10:00:00Z"
        )

        signal = classifier._extract_user_input_signal(context)
        # Keywords de orquestração = score alto (> 0.5)
        assert signal > 0.5

    def test_affected_services_signal_no_services(self, classifier):
        """Sem serviços afetados deve retornar neutro (0.5)."""
        context = RichContext(
            intent=IntentContext(raw_text="test"),
            system=SystemContext(affected_services=[]),
            temporal=TemporalContext(
                current_time="2026-04-23T10:00:00Z",
                time_of_day="morning",
                day_of_week="Wednesday",
                is_business_hours=True
            ),
            security=SecurityContext(),
            conversation=ConversationContext(),
            context_id="test",
            created_at="2026-04-23T10:00:00Z"
        )

        signal = classifier._extract_affected_services_signal(context)
        assert signal == 0.5

    def test_affected_services_signal_many_services(self, classifier):
        """Muitos serviços afetados deve retornar score alto."""
        context = RichContext(
            intent=IntentContext(raw_text="test"),
            system=SystemContext(affected_services=["a", "b", "c", "d", "e"]),
            temporal=TemporalContext(
                current_time="2026-04-23T10:00:00Z",
                time_of_day="morning",
                day_of_week="Wednesday",
                is_business_hours=True
            ),
            security=SecurityContext(),
            conversation=ConversationContext(),
            context_id="test",
            created_at="2026-04-23T10:00:00Z"
        )

        signal = classifier._extract_affected_services_signal(context)
        assert signal >= 0.8
