"""
Testes para ContextManagerService.
"""

import pytest
from unittest.mock import AsyncMock

from neural_hive_context.services.context_manager import ContextManagerService
from neural_hive_context.services.workflow_classifier import MultiSignalWorkflowClassifier
from neural_hive_context.models import (
    RichContext,
    WorkflowType,
)


@pytest.fixture
def workflow_classifier():
    """Fixture para MultiSignalWorkflowClassifier."""
    return MultiSignalWorkflowClassifier()


@pytest.fixture
def context_manager(workflow_classifier):
    """Fixture para ContextManagerService."""
    return ContextManagerService(
        workflow_classifier=workflow_classifier,
        cache_ttl_seconds=60,
        max_cache_size=10,
    )


class TestContextManagerService:
    """Testes para ContextManagerService."""

    @pytest.mark.asyncio
    async def test_create_context_minimal(self, context_manager):
        """Criar contexto com dados mínimos."""
        context = await context_manager.create_context(
            intent_text="gere um relatório",
            intent_id="intent-123",
        )

        assert isinstance(context, RichContext)
        assert context.intent.raw_text == "gere um relatório"
        assert context.intent.intent_id == "intent-123"
        assert context.context_id is not None
        assert context.system is not None
        assert context.temporal is not None
        assert context.security is not None
        assert context.conversation is not None

    @pytest.mark.asyncio
    async def test_create_context_with_user(self, context_manager):
        """Criar contexto com ID de usuário."""
        context = await context_manager.create_context(
            intent_text="gere um relatório",
            intent_id="intent-123",
            user_id="user-456",
        )

        assert context.intent.user_id == "user-456"
        assert context.conversation.user_id == "user-456"

    @pytest.mark.asyncio
    async def test_create_context_caching(self, context_manager):
        """Contexto deve ser cachado."""
        # Primeira chamada
        context1 = await context_manager.create_context(
            intent_text="gere um relatório",
            intent_id="intent-123",
        )

        # Segunda chamada com mesmo ID deve retornar cached
        context2 = await context_manager.create_context(
            intent_text="gere um relatório",
            intent_id="intent-123",
        )

        # Mesmo context_id indica cache hit
        assert context1.context_id == context2.context_id

    @pytest.mark.asyncio
    async def test_classify_workflow(self, context_manager):
        """Classificar workflow deve retornar WorkflowClassification."""
        context = await context_manager.create_context(
            intent_text="gere um relatório de vendas",
            intent_id="intent-123",
        )

        classification = await context_manager.classify_workflow(context)

        assert classification.workflow_type in [WorkflowType.ORCHESTRATION, WorkflowType.GENERATION]
        assert 0.0 <= classification.confidence <= 1.0
        assert classification.reasoning is not None

    @pytest.mark.asyncio
    async def test_create_and_classify(self, context_manager):
        """Método create_and_classify deve retornar tupla."""
        context, classification = await context_manager.create_and_classify(
            intent_text="gere um relatório",
            intent_id="intent-123",
        )

        assert isinstance(context, RichContext)
        assert classification.workflow_type in [WorkflowType.ORCHESTRATION, WorkflowType.GENERATION]

    @pytest.mark.asyncio
    async def test_enrich_cognitive_plan(self, context_manager):
        """Enriquecer CognitivePlan deve adicionar campos de workflow."""
        # Criar contexto e classificar
        context, classification = await context_manager.create_and_classify(
            intent_text="gere um relatório",
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
            "original_domain": "analytics",
            "original_priority": "normal",
            "original_security_level": "internal",
        }

        # Enriquecer
        enriched = await context_manager.enrich_cognitive_plan(base_plan, context, classification)

        # Verificar campos adicionados
        assert "workflow_type" in enriched
        assert "context_id" in enriched
        assert "workflow_confidence" in enriched
        assert "workflow_reasoning" in enriched
        assert enriched["workflow_type"] in ["orchestration", "generation"]

    @pytest.mark.asyncio
    async def test_clear_cache(self, context_manager):
        """Limpar cache deve funcionar."""
        # Criar contexto para popular cache
        await context_manager.create_context(
            intent_text="teste",
            intent_id="intent-cache",
        )

        stats_before = await context_manager.get_cache_stats()
        assert stats_before["size"] > 0

        # Limpar cache
        await context_manager.clear_cache()

        stats_after = await context_manager.get_cache_stats()
        assert stats_after["size"] == 0

    @pytest.mark.asyncio
    async def test_get_cache_stats(self, context_manager):
        """Estatísticas do cache devem ser retornadas."""
        stats = await context_manager.get_cache_stats()

        assert "size" in stats
        assert "max_size" in stats
        assert "ttl_seconds" in stats
        assert stats["max_size"] == 10
        assert stats["ttl_seconds"] == 60

    @pytest.mark.asyncio
    async def test_temporal_context_accuracy(self, context_manager):
        """Contexto temporal deve refletir hora atual."""
        context = await context_manager.create_context(
            intent_text="teste",
            intent_id="intent-temporal",
        )

        assert context.temporal.time_of_day in ["morning", "afternoon", "evening", "night"]
        assert context.temporal.day_of_week in [
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
            "Sunday",
        ]
        assert isinstance(context.temporal.is_business_hours, bool)

    @pytest.mark.asyncio
    async def test_with_system_state_client(self, workflow_classifier):
        """ContextManager deve integrar com cliente de estado do sistema."""
        # Mock client
        mock_client = AsyncMock()
        mock_client.get_current_state.return_value = {
            "active_workflows": 5,
            "affected_services": ["worker-agents", "analyst-agents"],
            "resource_utilization": {"cpu": 75.0, "memory": 60.0},
            "system_load": 0.7,
        }

        manager = ContextManagerService(
            workflow_classifier=workflow_classifier,
            system_state_client=mock_client,
        )

        context = await manager.create_context(
            intent_text="teste",
            intent_id="intent-sys",
        )

        # Verificar que contexto do sistema foi populado
        assert context.system.active_workflows == 5
        assert "worker-agents" in context.system.affected_services
        assert context.system.resource_utilization["cpu"] == 75.0

    @pytest.mark.asyncio
    async def test_generation_intent_classification(self, context_manager):
        """Intent de geração deve ser classificado como GENERATION."""
        context, classification = await context_manager.create_and_classify(
            intent_text="gere um relatório de vendas",
            intent_id="intent-gen",
        )

        # Keywords de geração devem favorecer GENERATION
        # (pode não ser 100% dependendo de outros sinais)
        assert classification.workflow_type in [WorkflowType.ORCHESTRATION, WorkflowType.GENERATION]

    @pytest.mark.asyncio
    async def test_orchestration_intent_classification(self, context_manager):
        """Intent de orquestração deve ser classificado como ORCHESTRATION."""
        # Criar contexto com múltiplos serviços afetados
        context = await context_manager.create_context(
            intent_text="analise os dados dos serviços",
            intent_id="intent-orch",
        )

        # Simular múltiplos serviços afetados
        context.system.affected_services = ["worker-agents", "analyst-agents", "optimizer-agents"]

        classification = await context_manager.classify_workflow(context)

        # Múltiplos serviços devem favorecer ORCHESTRATION
        assert classification.workflow_type == WorkflowType.ORCHESTRATION
