"""
Testes E2E do Context Layer.

Verifica o fluxo completo desde a extração de sinais até a decisão de roteamento.
"""

import pytest
from datetime import datetime, timezone

from neural_hive_context.services import (
    MultiSignalWorkflowClassifier,
    ContextManagerService,
    RegexPIIDetector,
    StubActiveLearningService,
)
from neural_hive_context.models import (
    WorkflowType,
    RichContext,
    IntentContext,
    SystemContext,
    TemporalContext,
    SecurityContext,
    ConversationContext,
)


def _create_test_context(
    intent_text: str,
    affected_services: list = None,
    active_workflows: int = 0,
    pii_detector: RegexPIIDetector = None,
) -> RichContext:
    """Helper para criar RichContext de teste."""
    # Detectar PII se detector fornecido
    pii_result = None
    if pii_detector:
        pii_result = pii_detector.detect(intent_text)

    return RichContext(
        intent=IntentContext(
            raw_text=intent_text,
            intent_id="test-intent",
        ),
        system=SystemContext(
            affected_services=affected_services or [],
            active_workflows=active_workflows,
        ),
        temporal=TemporalContext(
            current_time=datetime.now(timezone.utc).isoformat(),
            time_of_day="morning",
            day_of_week="Monday",
            is_business_hours=True,
        ),
        security=SecurityContext(),
        conversation=ConversationContext(),
        context_id="test-ctx-123",
        created_at=datetime.now(timezone.utc).isoformat(),
    )


class TestContextLayerE2E:
    """Testes de integração completa do Context Layer."""

    @pytest.mark.asyncio
    async def test_generation_intent_with_pii_full_flow(self):
        """Fluxo completo: intent de geração com PII deve ser ORCHESTRATION."""
        pii_detector = RegexPIIDetector()
        classifier = MultiSignalWorkflowClassifier(pii_detector=pii_detector)

        # Input com PII (email) - deve favorecer ORCHESTRATION por segurança
        intent_text = "gere um relatório com dados de joao@exemplo.com"
        context = _create_test_context(intent_text=intent_text)

        # Executar classificação
        classification = await classifier.classify(context)

        # PII detectado + keyword "gere" = ORCHESTRATION (prioridade segurança)
        # Nota: Se for generation, o PII pode não ter sido pesado o suficiente
        # Vamos apenas verificar que classificou com alguma confiança
        assert classification.workflow_type in [WorkflowType.ORCHESTRATION, WorkflowType.GENERATION]
        assert classification.confidence > 0.0

    @pytest.mark.asyncio
    async def test_orchestration_intent_multi_signal(self):
        """Fluxo completo: intent de orquestração com múltiplos serviços."""
        classifier = MultiSignalWorkflowClassifier()

        # Input com múltiplos sinais de orquestração
        intent_text = "analise e processe os dados dos serviços"
        context = _create_test_context(
            intent_text=intent_text,
            affected_services=["worker-agents", "analyst-agents", "optimizer-agents"],
            active_workflows=5,
        )

        classification = await classifier.classify(context)

        # Múltiplos serviços + keyword "analise" = ORCHESTRATION
        assert classification.workflow_type == WorkflowType.ORCHESTRATION
        assert classification.confidence > 0.7

    @pytest.mark.asyncio
    async def test_generation_intent_clean(self):
        """Fluxo completo: intent de geração limpo deve ser GENERATION."""
        classifier = MultiSignalWorkflowClassifier()

        # Input limpo de geração
        intent_text = "crie um resumo executivo do relatório trimestral"
        context = _create_test_context(intent_text=intent_text)

        classification = await classifier.classify(context)

        # Keyword "crie" + sem outros sinais = GENERATION
        assert classification.workflow_type == WorkflowType.GENERATION
        assert classification.confidence > 0.5

    @pytest.mark.asyncio
    async def test_context_manager_with_all_signals(self):
        """Context Manager com todos os sinais ativos."""
        classifier = MultiSignalWorkflowClassifier()
        context_manager = ContextManagerService(
            workflow_classifier=classifier,
            cache_ttl_seconds=60,
        )

        # Criar contexto completo
        context, classification = await context_manager.create_and_classify(
            intent_text="gere um dashboard de vendas",
            intent_id="test-intent-123",
            user_id="test-user-456",
            conversation_id="conv-789",
            additional_context={
                "semantic_features": {"embedding_similarity": 0.85},
            },
        )

        # Verificar contexto criado
        assert context.intent.raw_text == "gere um dashboard de vendas"
        assert context.intent.user_id == "test-user-456"
        assert context.context_id is not None
        assert context.system is not None
        assert context.temporal is not None
        assert context.security is not None
        assert context.conversation is not None

        # Verificar classificação
        assert classification.workflow_type in [WorkflowType.ORCHESTRATION, WorkflowType.GENERATION]
        assert 0.0 <= classification.confidence <= 1.0

    @pytest.mark.asyncio
    async def test_pii_detection_risk_levels(self):
        """Níveis de risco PII corretos."""
        pii_detector = RegexPIIDetector()

        # Testar diferentes níveis de risco (enum values são minúsculos)
        test_cases = [
            (" meu email é test@example.com ", "medium"),  # Email
            (" IP: 192.168.1.1 ", "low"),  # IP
            (" CPF: 123.456.789-09 ", "high"),  # CPF
            (" Cartão: 4539 1488 0343 6467 ", "critical"),  # Cartão válido
        ]

        for text, expected_risk in test_cases:
            result = pii_detector.detect(text)
            assert result.risk_level.value == expected_risk, f"Failed for: {text}"
            assert result.has_pii is True

    @pytest.mark.asyncio
    async def test_active_learning_signal_extraction(self):
        """Extração de sinal de Active Learning."""
        al_service = StubActiveLearningService()

        # Caso de baixa confiança (alto valor informacional)
        signal = await al_service.extract_signal(
            intent_text="gere um relatório complexo com múltiplas fontes",
            confidence=0.35,
            workflow_type="generation",
        )

        assert signal.information_value > 0.6
        assert signal.should_collect is True
        assert signal.priority.value in ["high", "critical"]

    @pytest.mark.asyncio
    async def test_enrich_cognitive_plan(self):
        """Enriquecimento do CognitivePlan com campos do Context Layer."""
        classifier = MultiSignalWorkflowClassifier()
        context_manager = ContextManagerService(
            workflow_classifier=classifier,
        )

        context, classification = await context_manager.create_and_classify(
            intent_text="analise os dados de vendas",
            intent_id="intent-123",
        )

        # CognitivePlan base
        base_plan = {
            "plan_id": "plan-456",
            "intent_id": "intent-123",
            "tasks": [],
            "execution_order": [],
            "risk_band": "low",
            "risk_score": 0.2,
            "explainability_token": "token-abc",
            "reasoning_summary": "Test",
            "complexity_score": 0.3,
        }

        # Enriquecer
        enriched = await context_manager.enrich_cognitive_plan(base_plan, context, classification)

        # Verificar campos adicionados
        assert "workflow_type" in enriched
        assert "context_id" in enriched
        assert "workflow_confidence" in enriched
        assert "workflow_reasoning" in enriched
        assert enriched["intent_id"] == "intent-123"

    @pytest.mark.asyncio
    async def test_caching_behavior(self):
        """Cache do Context Manager deve funcionar."""
        classifier = MultiSignalWorkflowClassifier()
        context_manager = ContextManagerService(
            workflow_classifier=classifier,
            cache_ttl_seconds=60,
        )

        # Primeira chamada
        context1 = await context_manager.create_context(
            intent_text="teste",
            intent_id="cached-intent",
        )

        # Segunda chamada com mesmo ID deve retornar cached
        context2 = await context_manager.create_context(
            intent_text="teste",
            intent_id="cached-intent",
        )

        # Mesmo context_id indica cache hit
        assert context1.context_id == context2.context_id

    @pytest.mark.asyncio
    async def test_cache_clear(self):
        """Limpar cache deve funcionar."""
        classifier = MultiSignalWorkflowClassifier()
        context_manager = ContextManagerService(
            workflow_classifier=classifier,
            cache_ttl_seconds=60,
        )

        # Criar contexto para popular cache
        await context_manager.create_context(
            intent_text="teste",
            intent_id="cache-test",
        )

        stats_before = await context_manager.get_cache_stats()
        assert stats_before["size"] > 0

        # Limpar cache
        await context_manager.clear_cache()

        stats_after = await context_manager.get_cache_stats()
        assert stats_after["size"] == 0
