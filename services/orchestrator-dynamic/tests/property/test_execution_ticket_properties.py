"""
Property-based tests para ExecutionTicket usando Hypothesis.

Estes testes verificam propriedades invariantes do modelo ExecutionTicket
que devem ser verdadeiras para qualquer entrada válida.

Autor: Neural-Hive-Mind
Criado: 2026-04-19 (HYP-02)
"""


from uuid import uuid4

import pytest
from hypothesis import Phase, assume, given, settings, strategies as st
from src.models.execution_ticket import (
    SLA,
    Consistency,
    DeliveryMode,
    Durability,
    ExecutionTicket,
    Priority,
    QoS,
    RiskBand,
    SecurityLevel,
    TaskType,
    TicketStatus,
)

# ============================================================================
# Estratégias Hypothesis para geração de dados
# ============================================================================

# Estratégia para timestamps (millis) - usar valores fixos para consistência
BASE_TIME_MS = 1609459200000  # 2021-01-01 00:00:00 UTC
valid_timestamps = st.integers(min_value=BASE_TIME_MS, max_value=BASE_TIME_MS + 86400000 * 365)

# Estratégia para strings simples (nomes, descrições)
simple_strings = st.text(
    min_size=1,
    max_size=100,
    alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd", "Pd", "Po")),
)

# Estratégia para listas de strings
string_lists = st.lists(
    st.text(
        min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"))
    ),
    max_size=10,
)

# Estratégia para dicionários de metadados
metadata_dicts = st.dictionaries(
    keys=st.text(
        min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"))
    ),
    values=st.text(max_size=100, alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"))),
    max_size=5,
)

# Estratégia para dicionários de parâmetros (valores podem ser various tipos)
param_values = st.one_of(
    st.text(max_size=100),
    st.integers(),
    st.floats(allow_infinity=False, allow_nan=False, min_value=-1e10, max_value=1e10),
    st.lists(st.text(max_size=50)),
)
param_dicts = st.dictionaries(
    keys=st.text(
        min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"))
    ),
    values=param_values,
    max_size=5,
)

# Estratégia para dicionários de predições
prediction_dicts = st.dictionaries(
    keys=st.text(
        min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"))
    ),
    values=st.one_of(
        st.integers(min_value=0, max_value=10000), st.floats(min_value=0.0, max_value=1.0)
    ),
    max_size=5,
)

# Enums
task_types = st.sampled_from(TaskType)
ticket_statuses = st.sampled_from(TicketStatus)
priorities = st.sampled_from(Priority)
risk_bands = st.sampled_from(RiskBand)
security_levels = st.sampled_from(SecurityLevel)
delivery_modes = st.sampled_from(DeliveryMode)
consistencies = st.sampled_from(Consistency)
durabilities = st.sampled_from(Durability)

# Estratégia para UUIDs como strings
uuid_strategy = st.uuids().map(lambda u: str(u))


# Estratégia para SLA - usando composite para garantir consistência
@st.composite
def sla_strategy(draw):
    """Gera SLA válido."""
    timeout = draw(st.integers(min_value=1000, max_value=86400000))
    deadline = draw(
        st.integers(min_value=BASE_TIME_MS + timeout, max_value=BASE_TIME_MS + 86400000 * 7)
    )
    max_retries = draw(st.integers(min_value=0, max_value=10))
    return SLA(deadline=deadline, timeout_ms=timeout, max_retries=max_retries)


# Estratégia para QoS
@st.composite
def qos_strategy(draw):
    """Gera QoS válido."""
    return QoS(
        delivery_mode=draw(delivery_modes),
        consistency=draw(consistencies),
        durability=draw(durabilities),
    )


# Estratégia para ExecutionTicket
@st.composite
def execution_ticket_strategy(draw):
    """Gera ExecutionTicket válido."""
    # Desenhar timestamps primeiro para garantir consistência
    created_at = draw(valid_timestamps)
    sla = draw(sla_strategy())
    qos = draw(qos_strategy())

    # started_at pode ser None ou um timestamp >= created_at
    started_at = draw(
        st.none() | st.integers(min_value=created_at, max_value=created_at + sla.timeout_ms)
    )

    # completed_at deve ser > started_at se ambos existem
    completed_at = None
    if started_at is not None:
        min_completed = started_at + 1
        max_completed = started_at + sla.timeout_ms
        completed_at = draw(
            st.none() | st.integers(min_value=min_completed, max_value=max_completed)
        )

    return ExecutionTicket(
        ticket_id=draw(uuid_strategy),
        plan_id=draw(uuid_strategy),
        intent_id=draw(uuid_strategy),
        decision_id=draw(uuid_strategy),
        correlation_id=draw(st.none() | uuid_strategy),
        trace_id=draw(st.none() | uuid_strategy),
        span_id=draw(st.none() | uuid_strategy),
        task_id=draw(uuid_strategy),
        task_type=draw(task_types),
        description=draw(simple_strings),
        dependencies=draw(st.lists(uuid_strategy, max_size=5)),
        status=draw(ticket_statuses),
        priority=draw(priorities),
        risk_band=draw(risk_bands),
        sla=sla,
        qos=qos,
        parameters=draw(param_dicts),
        required_capabilities=draw(string_lists),
        security_level=draw(security_levels),
        created_at=created_at,
        started_at=started_at,
        completed_at=completed_at,
        estimated_duration_ms=draw(st.none() | st.integers(min_value=100, max_value=86400000)),
        actual_duration_ms=draw(st.none() | st.integers(min_value=100, max_value=86400000)),
        retry_count=draw(st.integers(min_value=0, max_value=20)),
        error_message=draw(st.none() | st.text(max_size=500)),
        compensation_ticket_id=draw(st.none() | uuid_strategy),
        metadata=draw(metadata_dicts),
        predictions=draw(st.none() | prediction_dicts),
        schema_version=1,  # Valor fixo, não strategy
    )


# ============================================================================
# Testes Property-Based
# ============================================================================


class TestExecutionTicketProperties:
    """Testes de propriedades para ExecutionTicket."""

    @given(execution_ticket_strategy())
    @settings(max_examples=100, phases=[Phase.generate])
    def test_ticket_to_avro_dict_is_serializable(self, ticket: ExecutionTicket):
        """Property: to_avro_dict() sempre retorna dict serializável."""
        result = ticket.to_avro_dict()

        assert isinstance(result, dict)
        assert "ticket_id" in result
        assert "task_type" in result
        assert "sla" in result
        assert "qos" in result

        # Verificar que todos os valores são tipos JSON básicos
        for key, value in result.items():
            is_json_type = value is None or isinstance(value, (str, int, float, bool, list, dict))
            assert is_json_type, f"Campo {key} tem tipo não serializável: {type(value)}"

    @given(execution_ticket_strategy())
    @settings(max_examples=100, phases=[Phase.generate])
    def test_ticket_from_avro_dict_roundtrip(self, ticket: ExecutionTicket):
        """Property: from_avro_dict(to_avro_dict(x)) == x para campos relevantes."""
        avro_dict = ticket.to_avro_dict()
        restored = ExecutionTicket.from_avro_dict(avro_dict)

        # Campos que devem ser preservados
        assert restored.ticket_id == ticket.ticket_id
        assert restored.plan_id == ticket.plan_id
        assert restored.intent_id == ticket.intent_id
        assert restored.decision_id == ticket.decision_id
        assert restored.task_id == ticket.task_id
        assert restored.description == ticket.description

        # Enums devem ser preservados
        assert restored.task_type == ticket.task_type
        assert restored.status == ticket.status
        assert restored.priority == ticket.priority
        assert restored.risk_band == ticket.risk_band
        assert restored.security_level == ticket.security_level

        # SLA e QoS devem ser preservados
        assert restored.sla.deadline == ticket.sla.deadline
        assert restored.sla.timeout_ms == ticket.sla.timeout_ms
        assert restored.sla.max_retries == ticket.sla.max_retries
        assert restored.qos.delivery_mode == ticket.qos.delivery_mode
        assert restored.qos.consistency == ticket.qos.consistency
        assert restored.qos.durability == ticket.qos.durability

    @given(execution_ticket_strategy())
    @settings(max_examples=100, phases=[Phase.generate])
    def test_completed_at_greater_than_started_at(self, ticket: ExecutionTicket):
        """Property: Se completed_at existe, deve ser > started_at."""
        # Este teste deve sempre passar porque o validator garante isso
        if ticket.completed_at is not None and ticket.started_at is not None:
            assert ticket.completed_at > ticket.started_at

    @given(execution_ticket_strategy())
    @settings(max_examples=100, phases=[Phase.generate])
    def test_can_retry_consistent_with_sla(self, ticket: ExecutionTicket):
        """Property: can_retry() é True se e somente se retry_count < max_retries."""
        can_retry = ticket.can_retry()
        expected = ticket.retry_count < ticket.sla.max_retries
        assert can_retry == expected

    @given(execution_ticket_strategy())
    @settings(max_examples=100, phases=[Phase.generate])
    def test_calculate_hash_is_deterministic(self, ticket: ExecutionTicket):
        """Property: calculate_hash() retorna mesmo valor para mesma instância."""
        hash1 = ticket.calculate_hash()
        hash2 = ticket.calculate_hash()
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA-256 hex = 64 caracteres

    @given(execution_ticket_strategy(), execution_ticket_strategy())
    @settings(max_examples=50, phases=[Phase.generate])
    def test_different_tickets_different_hashes(
        self, ticket1: ExecutionTicket, ticket2: ExecutionTicket
    ):
        """Property: Tickets diferentes produzem hashes diferentes (com alta probabilidade)."""
        assume(ticket1.ticket_id != ticket2.ticket_id)
        hash1 = ticket1.calculate_hash()
        hash2 = ticket2.calculate_hash()
        # Mesmo ticket_id diferente garante hash diferente
        assert hash1 != hash2


class TestSLAProperties:
    """Testes de propriedades para SLA."""

    @given(sla_strategy())
    @settings(max_examples=100, phases=[Phase.generate])
    def test_sla_timeout_positive(self, sla: SLA):
        """Property: timeout_ms deve ser sempre positivo."""
        assert sla.timeout_ms > 0

    @given(sla_strategy())
    @settings(max_examples=100, phases=[Phase.generate])
    def test_sla_max_retries_non_negative(self, sla: SLA):
        """Property: max_retries deve ser não-negativo."""
        assert sla.max_retries >= 0


class TestQoSProperties:
    """Testes de propriedades para QoS."""

    @given(qos_strategy())
    @settings(max_examples=100, phases=[Phase.generate])
    def test_qos_has_valid_enums(self, qos: QoS):
        """Property: QoS enums devem ser valores válidos."""
        # Valores podem ser strings ou Enums, verificar ambos
        assert str(qos.delivery_mode) in [e.value for e in DeliveryMode]
        assert str(qos.consistency) in [e.value for e in Consistency]
        assert str(qos.durability) in [e.value for e in Durability]


class TestExecutionTicketLegacyCompatibility:
    """Testes de compatibilidade com formato legado."""

    @given(st.integers(min_value=1, max_value=10))
    @settings(max_examples=20, phases=[Phase.generate])
    def test_legacy_priority_mapping(self, legacy_priority: int):
        """Property: Prioridade legada (int) é mapeada corretamente."""
        ticket = ExecutionTicket(
            ticket_id=str(uuid4()),
            plan_id=str(uuid4()),
            intent_id=str(uuid4()),
            decision_id=str(uuid4()),
            task_id=str(uuid4()),
            task_type=TaskType.QUERY,
            description="Test",
            priority=legacy_priority,  # int legado
            risk_band=RiskBand.medium,
            sla=SLA(
                deadline=BASE_TIME_MS + 3600000,
                timeout_ms=60000,
                max_retries=3,
            ),
            qos=QoS(
                delivery_mode=DeliveryMode.AT_LEAST_ONCE,
                consistency=Consistency.EVENTUAL,
                durability=Durability.PERSISTENT,
            ),
            security_level=SecurityLevel.INTERNAL,
            created_at=BASE_TIME_MS,
        )

        # Verificar mapeamento correto
        if legacy_priority <= 2:
            assert ticket.priority == Priority.LOW
        elif legacy_priority <= 5:
            assert ticket.priority == Priority.NORMAL
        elif legacy_priority <= 8:
            assert ticket.priority == Priority.HIGH
        else:
            assert ticket.priority == Priority.CRITICAL


class TestExecutionTicketValidation:
    """Testes de validação com Hypothesis."""

    @given(uuid_strategy, st.lists(uuid_strategy, min_size=1, max_size=10))
    @settings(max_examples=50, phases=[Phase.generate])
    def test_ticket_cannot_depend_on_itself(self, ticket_id: str, dependencies: list):
        """Property: Ticket não pode ter auto-dependência."""
        assume(ticket_id not in dependencies)  # Assume valid input first

        # Criar ticket válido
        ticket = ExecutionTicket(
            ticket_id=ticket_id,
            plan_id=str(uuid4()),
            intent_id=str(uuid4()),
            decision_id=str(uuid4()),
            task_id=str(uuid4()),
            task_type=TaskType.QUERY,
            description="Test",
            priority=Priority.NORMAL,
            risk_band=RiskBand.medium,
            sla=SLA(
                deadline=BASE_TIME_MS + 3600000,
                timeout_ms=60000,
                max_retries=3,
            ),
            qos=QoS(
                delivery_mode=DeliveryMode.AT_LEAST_ONCE,
                consistency=Consistency.EVENTUAL,
                durability=Durability.PERSISTENT,
            ),
            dependencies=dependencies,
            security_level=SecurityLevel.INTERNAL,
            created_at=BASE_TIME_MS,
        )

        # Tentar adicionar auto-dependência deve falhar
        invalid_deps = dependencies + [ticket_id]
        with pytest.raises(ValueError, match="auto.dependency|si mesmo|cannot depend"):
            ExecutionTicket(
                ticket_id=ticket_id,
                plan_id=str(uuid4()),
                intent_id=str(uuid4()),
                decision_id=str(uuid4()),
                task_id=str(uuid4()),
                task_type=TaskType.QUERY,
                description="Test",
                priority=Priority.NORMAL,
                risk_band=RiskBand.medium,
                sla=SLA(
                    deadline=BASE_TIME_MS + 3600000,
                    timeout_ms=60000,
                    max_retries=3,
                ),
                qos=QoS(
                    delivery_mode=DeliveryMode.AT_LEAST_ONCE,
                    consistency=Consistency.EVENTUAL,
                    durability=Durability.PERSISTENT,
                ),
                dependencies=invalid_deps,
                security_level=SecurityLevel.INTERNAL,
                created_at=BASE_TIME_MS,
            )

    @given(sla_strategy(), st.integers(min_value=0, max_value=20))
    @settings(max_examples=100, phases=[Phase.generate])
    def test_can_retry_boundary_conditions(self, sla: SLA, retry_count: int):
        """Property: can_retry() respeita limites de max_retries."""
        ticket = ExecutionTicket(
            ticket_id=str(uuid4()),
            plan_id=str(uuid4()),
            intent_id=str(uuid4()),
            decision_id=str(uuid4()),
            task_id=str(uuid4()),
            task_type=TaskType.QUERY,
            description="Test",
            priority=Priority.NORMAL,
            risk_band=RiskBand.medium,
            sla=sla,
            qos=QoS(
                delivery_mode=DeliveryMode.AT_LEAST_ONCE,
                consistency=Consistency.EVENTUAL,
                durability=Durability.PERSISTENT,
            ),
            security_level=SecurityLevel.INTERNAL,
            created_at=BASE_TIME_MS,
            retry_count=retry_count,
        )

        can_retry = ticket.can_retry()
        expected = retry_count < sla.max_retries
        assert can_retry == expected
