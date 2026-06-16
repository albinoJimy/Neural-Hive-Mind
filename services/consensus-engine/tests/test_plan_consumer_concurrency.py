"""
Testes unitários para o modo concorrente do PlanConsumer (feature-flag
consensus_max_concurrent_plans > 1) e para o commit de offset por prefixo
CONTÍGUO por partição.

Objetivos cobertos:
- Default=1 mantém o modo SÉRIE (concorrência desligada).
- O commit contíguo nunca ultrapassa o offset de uma mensagem ainda em curso
  ou falhada (correção do offset preservada para rebalances).
- Conclusões fora de ordem só avançam o offset quando o prefixo é contíguo.
"""

from unittest.mock import MagicMock

import pytest
from src.consumers.plan_consumer import PlanConsumer
from src.observability.metrics import ConsensusMetrics


class _BaseConfig:
    """Config mínima para construir um PlanConsumer em testes."""

    kafka_plans_topic = "plans.ready"
    kafka_bootstrap_servers = "localhost:9092"
    kafka_consumer_group_id = "consensus-engine-test"
    kafka_auto_offset_reset = "earliest"
    kafka_enable_auto_commit = False
    enable_parallel_invocation = True
    grpc_timeout_ms = 5000
    consumer_max_consecutive_errors = 3
    consumer_base_backoff_seconds = 0.01
    consumer_max_backoff_seconds = 0.1
    consumer_poll_timeout_seconds = 0.01
    consumer_enable_dlq = False
    kafka_dlq_topic = "plans.ready.dlq"
    consumer_max_retries_before_dlq = 2
    min_confidence_score = 0.7
    max_divergence_threshold = 0.3
    critical_risk_threshold = 0.8
    high_risk_threshold = 0.7
    enable_pheromones = False
    enable_hierarchical_consensus = False
    specialist_seniority: dict = {}
    domain_specialist_weights: dict = {}
    require_unanimous_for_critical = True
    bayesian_prior_weight = 0.1
    enable_bayesian_averaging = True


class SerialConfig(_BaseConfig):
    consensus_max_concurrent_plans = 1


class ConcurrentConfig(_BaseConfig):
    consensus_max_concurrent_plans = 4


def _make_consumer(config):
    return PlanConsumer(
        config=config,
        specialists_client=MagicMock(),
        mongodb_client=MagicMock(),
        pheromone_client=MagicMock(),
    )


def _make_msg(topic: str, partition: int, offset: int):
    msg = MagicMock()
    msg.topic.return_value = topic
    msg.partition.return_value = partition
    msg.offset.return_value = offset
    return msg


@pytest.mark.unit()
class TestConcurrencyFlag:
    """A flag default mantém o comportamento série (anti-regressão)."""

    def test_default_is_serial(self):
        consumer = _make_consumer(SerialConfig())
        assert consumer._max_concurrent_plans == 1
        assert consumer._concurrent_enabled is False

    def test_flag_enables_concurrency(self):
        consumer = _make_consumer(ConcurrentConfig())
        assert consumer._max_concurrent_plans == 4
        assert consumer._concurrent_enabled is True

    def test_missing_attribute_defaults_to_serial(self):
        """Config sem o atributo (getattr fallback) => série."""

        class NoFlagConfig(_BaseConfig):
            pass

        consumer = _make_consumer(NoFlagConfig())
        assert consumer._max_concurrent_plans == 1
        assert consumer._concurrent_enabled is False


@pytest.mark.unit()
@pytest.mark.asyncio()
class TestContiguousOffsetCommit:
    """Commit de offset por prefixo contíguo por partição (modo concorrente)."""

    async def _build_concurrent_consumer(self, monkeypatch):
        import asyncio

        consumer = _make_consumer(ConcurrentConfig())
        # Inicializar primitivos normalmente criados em start().
        consumer._offset_lock = asyncio.Lock()
        consumer.config = ConcurrentConfig()

        committed: list = []

        async def fake_commit(topic, partition, offset):
            committed.append((topic, partition, offset))

        monkeypatch.setattr(consumer, "_commit_offset", fake_commit)
        # Evitar dependência das métricas reais.
        monkeypatch.setattr(ConsensusMetrics, "increment_offset_commit", lambda *a, **k: None)
        return consumer, committed

    async def test_in_order_completion_commits_each(self, monkeypatch):
        consumer, committed = await self._build_concurrent_consumer(monkeypatch)
        for off in (10, 11, 12):
            consumer._register_inflight_offset(_make_msg("plans.ready", 0, off))
        for off in (10, 11, 12):
            await consumer._mark_offset_completed(_make_msg("plans.ready", 0, off))
        # Cada conclusão contígua commita o seu offset.
        assert committed == [
            ("plans.ready", 0, 10),
            ("plans.ready", 0, 11),
            ("plans.ready", 0, 12),
        ]

    async def test_out_of_order_holds_until_contiguous(self, monkeypatch):
        consumer, committed = await self._build_concurrent_consumer(monkeypatch)
        for off in (10, 11, 12, 13):
            consumer._register_inflight_offset(_make_msg("plans.ready", 0, off))

        # 11 e 13 concluem primeiro: há buraco em 10 -> NADA commitado.
        await consumer._mark_offset_completed(_make_msg("plans.ready", 0, 11))
        await consumer._mark_offset_completed(_make_msg("plans.ready", 0, 13))
        assert committed == []

        # 10 conclui: 10,11 contíguos -> commita 11 (offset mais alto contíguo).
        await consumer._mark_offset_completed(_make_msg("plans.ready", 0, 10))
        assert committed == [("plans.ready", 0, 11)]

        # 12 conclui: 12,13 contíguos -> commita 13.
        await consumer._mark_offset_completed(_make_msg("plans.ready", 0, 12))
        assert committed == [("plans.ready", 0, 11), ("plans.ready", 0, 13)]

    async def test_failed_offset_never_surpassed(self, monkeypatch):
        """Um offset falhado (nunca marcado) retém todos os posteriores."""
        consumer, committed = await self._build_concurrent_consumer(monkeypatch)
        for off in (10, 11, 12, 13):
            consumer._register_inflight_offset(_make_msg("plans.ready", 0, off))

        # 12 falha => nunca é marcado concluído. 10,11 OK; 13 OK mas retido.
        await consumer._mark_offset_completed(_make_msg("plans.ready", 0, 10))
        await consumer._mark_offset_completed(_make_msg("plans.ready", 0, 11))
        await consumer._mark_offset_completed(_make_msg("plans.ready", 0, 13))

        committed_offsets = [c[2] for c in committed]
        # 12 e 13 nunca commitados: o prefixo não pode ultrapassar o offset falhado.
        assert 12 not in committed_offsets
        assert 13 not in committed_offsets
        assert max(committed_offsets) == 11

    async def test_partitions_are_independent(self, monkeypatch):
        """Cada partição mantém o seu próprio prefixo contíguo."""
        consumer, committed = await self._build_concurrent_consumer(monkeypatch)
        consumer._register_inflight_offset(_make_msg("plans.ready", 0, 5))
        consumer._register_inflight_offset(_make_msg("plans.ready", 1, 100))

        await consumer._mark_offset_completed(_make_msg("plans.ready", 1, 100))
        await consumer._mark_offset_completed(_make_msg("plans.ready", 0, 5))

        assert ("plans.ready", 1, 100) in committed
        assert ("plans.ready", 0, 5) in committed
