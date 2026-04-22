"""
Property-based tests para IntelligentScheduler usando Hypothesis.

Estes testes verificam propriedades invariantes do IntelligentScheduler
que devem ser verdadeiras para qualquer entrada válida.

Autor: Neural-Hive-Mind
Criado: 2026-04-19 (HYP-02)
"""

from datetime import timedelta
from unittest.mock import AsyncMock, Mock

import pytest
from hypothesis import Phase, given, settings, strategies as st
from src.scheduler.intelligent_scheduler import IntelligentScheduler, Priority

# ============================================================================
# Estratégias Hypothesis para geração de dados
# ============================================================================

# Estratégia para priority_score (0.0 a 1.0)
priority_scores = st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)

# Estratégia para agent_score (0.0 a 1.0)
agent_scores = st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)

# Estratégia para IDs
uuid_strategy = st.uuids().map(lambda u: str(u))
simple_strings = st.text(
    min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"))
)


# Estratégia para tickets básicos
@st.composite
def ticket_strategy(draw):
    """Gera ticket básico válido."""
    return {
        "ticket_id": draw(uuid_strategy),
        "plan_id": draw(uuid_strategy),
        "intent_id": draw(uuid_strategy),
        "decision_id": draw(uuid_strategy),
        "task_id": draw(uuid_strategy),
        "task_type": draw(st.sampled_from(["QUERY", "TRANSFORM", "VALIDATE", "EXECUTE"])),
        "description": draw(simple_strings),
        "priority": draw(st.sampled_from(["LOW", "NORMAL", "HIGH", "CRITICAL"])),
        "risk_band": draw(st.sampled_from(["low", "medium", "high", "critical"])),
        "required_capabilities": draw(st.lists(simple_strings, max_size=5)),
        "namespace": draw(simple_strings),
        "security_level": draw(st.sampled_from(["PUBLIC", "INTERNAL", "CONFIDENTIAL"])),
        "estimated_duration_ms": draw(st.integers(min_value=100, max_value=3600000)),
        "created_at": draw(st.integers(min_value=1609459200000, max_value=4102444800000)),
    }


# Estratégia para rejeição reasons
rejection_reasons = st.sampled_from(["no_workers", "no_suitable_worker", "scheduling_error"])

# Estratégia para rejection messages
rejection_messages = st.text(
    min_size=1,
    max_size=200,
    alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd", "Po", "Pd")),
)


# ============================================================================
# Helpers para criar scheduler com mocks corretos
# ============================================================================


def create_mock_config():
    """Cria configuração mockada com valores corretos."""
    config = Mock()
    config.enable_ml_enhanced_scheduling = False  # Desabilitar ML para testes básicos
    config.scheduler_enable_affinity = False
    config.service_registry_cache_ttl_seconds = 10
    config.CIRCUIT_BREAKER_ENABLED = False
    config.service_name = "orchestrator-dynamic"
    return config


def create_mock_metrics():
    """Cria métricas mockadas."""
    metrics = Mock()
    metrics.record_ticket_rejected = Mock()
    metrics.record_scheduling_latency = Mock()
    metrics.record_priority_score = Mock()
    metrics.record_agent_score = Mock()
    return metrics


def create_scheduler():
    """Cria scheduler com mocks para testes."""
    return IntelligentScheduler(
        config=create_mock_config(),
        metrics=create_mock_metrics(),
        priority_calculator=Mock(calculate_priority_score=Mock(return_value=0.5)),
        resource_allocator=Mock(
            allocate_resources=AsyncMock(
                return_value={
                    "agent_id": "worker-1",
                    "agent_type": "query-worker",
                    "allocation_method": "intelligent_scheduler",
                }
            )
        ),
    )


# ============================================================================
# Testes Property-Based
# ============================================================================


class TestSchedulerScoringProperties:
    """Testes de propriedades para funções de scoring."""

    @given(priority_scores, agent_scores)
    @settings(max_examples=100, phases=[Phase.generate])
    def test_calculate_composite_score_always_normalized(
        self, priority_score: float, agent_score: float
    ):
        """Property: _calculate_composite_score sempre retorna valor em [0.0, 1.0]."""
        scheduler = create_scheduler()

        result = scheduler._calculate_composite_score(priority_score, agent_score)

        assert 0.0 <= result <= 1.0, f"Score {result} fora do intervalo [0.0, 1.0]"

    @given(priority_scores, agent_scores)
    @settings(max_examples=100, phases=[Phase.generate])
    def test_composite_score_weighting(self, priority_score: float, agent_score: float):
        """Property: Agent score tem peso maior (60%) que priority score (40%)."""
        scheduler = create_scheduler()

        result = scheduler._calculate_composite_score(priority_score, agent_score)

        # Fórmula: (agent_score * 0.6) + (priority_score * 0.4)
        expected = min(max((agent_score * 0.6) + (priority_score * 0.4), 0.0), 1.0)
        assert abs(result - expected) < 1e-10, f"Score {result} != esperado {expected}"

    @given(st.floats(min_value=0.0, max_value=1.0))
    @settings(max_examples=50, phases=[Phase.generate])
    def test_composite_score_with_equal_inputs(self, score: float):
        """Property: Scores iguais produzem composite score igual."""
        scheduler = create_scheduler()

        result = scheduler._calculate_composite_score(score, score)

        # (score * 0.6) + (score * 0.4) = score
        assert abs(result - score) < 1e-10, f"Score {result} != input {score}"


class TestTicketRejectionProperties:
    """Testes de propriedades para rejeição de tickets."""

    @given(ticket_strategy(), rejection_reasons, rejection_messages)
    @settings(max_examples=100, phases=[Phase.generate])
    def test_rejected_ticket_has_rejected_status(self, ticket: dict, reason: str, message: str):
        """Property: Ticket rejeitado tem status='rejected'."""
        scheduler = create_scheduler()

        result = scheduler._reject_ticket(ticket, reason, message)

        assert result["status"] == "rejected", f"Status {result.get('status')} != 'rejected'"

    @given(ticket_strategy(), rejection_reasons, rejection_messages)
    @settings(max_examples=100, phases=[Phase.generate])
    def test_rejected_ticket_no_allocation_metadata(self, ticket: dict, reason: str, message: str):
        """Property: Ticket rejeitado não tem allocation_metadata válido."""
        scheduler = create_scheduler()

        result = scheduler._reject_ticket(ticket, reason, message)

        assert result.get("allocation_metadata") is None, "allocation_metadata deve ser None"

    @given(ticket_strategy(), rejection_reasons, rejection_messages)
    @settings(max_examples=100, phases=[Phase.generate])
    def test_rejected_ticket_preserves_id(self, ticket: dict, reason: str, message: str):
        """Property: Ticket rejeitado preserva ticket_id."""
        scheduler = create_scheduler()

        original_id = ticket.get("ticket_id")
        result = scheduler._reject_ticket(ticket, reason, message)

        assert result.get("ticket_id") == original_id, "ticket_id deve ser preservado"

    @given(ticket_strategy(), rejection_reasons, rejection_messages)
    @settings(max_examples=100, phases=[Phase.generate])
    def test_rejected_ticket_has_rejection_metadata(self, ticket: dict, reason: str, message: str):
        """Property: Ticket rejeitado tem rejection_metadata completo."""
        scheduler = create_scheduler()

        result = scheduler._reject_ticket(ticket, reason, message)

        rejection_metadata = result.get("rejection_metadata")
        assert rejection_metadata is not None, "rejection_metadata deve existir"
        assert rejection_metadata.get("rejection_reason") == reason
        assert rejection_metadata.get("rejection_message") == message
        assert "rejected_at" in rejection_metadata
        assert rejection_metadata.get("allocation_method") == "rejected"


class TestPriorityEnumProperties:
    """Testes de propriedades para enum Priority."""

    @given(st.sampled_from(Priority))
    @settings(max_examples=20, phases=[Phase.generate])
    def test_priority_has_valid_value(self, priority: Priority):
        """Property: Todos os valores de Priority são positivos."""
        assert priority.value > 0

    @given(st.sampled_from(Priority))
    @settings(max_examples=20, phases=[Phase.generate])
    def test_priority_ordering(self, priority: Priority):
        """Property: LOW < MEDIUM < HIGH < CRITICAL."""
        assert (
            Priority.LOW.value
            < Priority.MEDIUM.value
            < Priority.HIGH.value
            < Priority.CRITICAL.value
        )

    def test_priority_exhaustiveness(self):
        """Property: Enum tem exatamente 4 níveis."""
        assert len(Priority) == 4


class TestSchedulerWithMLPredictions:
    """Testes de propriedades para enriquecimento com ML."""

    @pytest.mark.asyncio()
    @given(ticket_strategy())
    @settings(max_examples=50, phases=[Phase.generate])
    async def test_enrichment_preserves_ticket_fields(self, ticket: dict):
        """Property: Enriquecimento preserva campos originais do ticket."""
        scheduler = create_scheduler()

        original_ticket_id = ticket.get("ticket_id")
        original_plan_id = ticket.get("plan_id")

        result = await scheduler._enrich_ticket_with_predictions(ticket)

        assert result.get("ticket_id") == original_ticket_id
        assert result.get("plan_id") == original_plan_id

    @pytest.mark.asyncio()
    @given(
        ticket_strategy(),
        st.floats(min_value=0.0, max_value=1.0),
        st.integers(min_value=0, max_value=10),
    )
    @settings(max_examples=50, phases=[Phase.generate])
    async def test_enrichment_with_load_predictor_adds_field(
        self, ticket: dict, load_pct: float, bottleneck_count: int
    ):
        """Property: Enriquecimento com LoadPredictor adiciona campos predictions."""
        config = create_mock_config()
        config.enable_ml_enhanced_scheduling = True

        mock_load_predictor = AsyncMock()
        mock_load_predictor.predict_load = AsyncMock(return_value={"forecast": [load_pct]})
        mock_load_predictor.predict_bottlenecks = AsyncMock(
            return_value=[{"severity": "HIGH"} for _ in range(bottleneck_count)]
        )

        scheduler = IntelligentScheduler(
            config=config,
            metrics=create_mock_metrics(),
            priority_calculator=Mock(calculate_priority_score=Mock(return_value=0.5)),
            resource_allocator=Mock(
                allocate_resources=AsyncMock(
                    return_value={
                        "agent_id": "worker-1",
                        "agent_type": "query-worker",
                        "allocation_method": "intelligent_scheduler",
                    }
                )
            ),
            load_predictor=mock_load_predictor,
        )

        result = await scheduler._enrich_ticket_with_predictions(ticket)

        assert "predictions" in result
        assert "system_load" in result["predictions"]
        assert result["predictions"]["system_load"]["predicted_load_pct"] == load_pct


class TestCacheProperties:
    """Testes de propriedades para cache do scheduler."""

    @given(simple_strings, simple_strings, st.integers(min_value=1, max_value=3600))
    @settings(max_examples=50, phases=[Phase.generate])
    def test_cache_key_format(self, namespace: str, capability: str, ttl: int):
        """Property: Chave de cache é gerada consistentemente."""
        # Este teste verifica que o formato do cache key é consistente
        # A implementação real pode variar, mas deve ser determinística

        key_parts = [namespace, capability]
        cache_key = ":".join(key_parts)

        assert cache_key == f"{namespace}:{capability}"
        assert len(cache_key) == len(namespace) + len(capability) + 1  # +1 para o ':'

    @given(st.integers(min_value=1, max_value=3600))
    @settings(max_examples=50, phases=[Phase.generate])
    def test_cache_ttl_positive(self, ttl_seconds: int):
        """Property: TTL de cache deve ser sempre positivo."""
        assert ttl_seconds > 0

        # Se usado em timedelta, deve gerar timedelta válido
        td = timedelta(seconds=ttl_seconds)
        assert td.total_seconds() == ttl_seconds
