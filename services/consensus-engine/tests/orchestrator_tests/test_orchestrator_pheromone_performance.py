"""
Testes das correções de performance/robustez do caminho de feromônios no
ConsensusOrchestrator.

Causa-raiz (proj_consensus_redis_client_degradation_2026-06-18): cliente Redis
singleton degradado fazia cada operação de feromônio cair em fallback MongoDB após
timeout; executadas em série para 5 especialistas isto somava ~6.5min e o publish
pós-decisão bloqueava a persistência da ConsolidatedDecision.

Correções verificadas aqui:
  1. _calculate_dynamic_weights busca os pesos de feromônio EM PARALELO.
  2. _publish_pheromones_best_effort isola timeout/erros (nunca bloqueia a decisão).
  3. Settings expõe timeouts de Redis e de publish com defaults sãos.

TDD: testes comportamentais que falham sem as correções.
"""

import asyncio
import importlib.util
import sys
import time
from enum import Enum
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest


# --- Mocks de módulos externos (mesmo padrão de test_orchestrator_hierarchical) ---
class UnifiedDomain(str, Enum):
    BUSINESS = "BUSINESS"
    SECURITY = "SECURITY"


class DomainMapper:
    @staticmethod
    def normalize(domain_str, context):
        return UnifiedDomain.BUSINESS


sys.modules["neural_hive_domain"] = MagicMock()
sys.modules["neural_hive_domain"].UnifiedDomain = UnifiedDomain
sys.modules["neural_hive_domain"].DomainMapper = DomainMapper

_mock_observability = MagicMock()
_mock_tracer = MagicMock()
_mock_tracer.start_as_current_span = MagicMock()
_mock_tracer.__enter__ = MagicMock(return_value=_mock_tracer)
_mock_tracer.__exit__ = MagicMock(return_value=False)
_mock_observability.get_tracer = MagicMock(return_value=_mock_tracer)
sys.modules["neural_hive_observability"] = _mock_observability

src_path = Path(__file__).parent.parent.parent / "src"
sys.path.insert(0, str(src_path))


def _load_orchestrator_class():
    spec = importlib.util.spec_from_file_location(
        "services.consensus_orchestrator",
        src_path / "services" / "consensus_orchestrator.py",
    )
    module = importlib.util.module_from_spec(spec)
    with patch("services.consensus_orchestrator.BayesianAggregator"):
        with patch("services.consensus_orchestrator.VotingEnsemble"):
            with patch("services.consensus_orchestrator.ComplianceFallback"):
                spec.loader.exec_module(module)
    return module.ConsensusOrchestrator


def _base_config():
    config = Mock()
    config.enable_pheromones = True
    config.enable_hierarchical_consensus = False
    config.specialist_seniority = {}
    config.domain_specialist_weights = {}
    config.pheromone_publish_timeout = 0.3
    return config


def _opinions(types):
    return [
        {"specialist_type": t, "opinion": {"confidence_score": 0.5, "risk_score": 0.5}}
        for t in types
    ]


class TestDynamicWeightsParallelism:
    """Fix #2: pesos de feromônio buscados em paralelo (não em série)."""

    @pytest.mark.asyncio()
    async def test_pheromone_weights_fetched_concurrently(self):
        ConsensusOrchestrator = _load_orchestrator_class()
        tracker = {"active": 0, "max": 0}

        class SlowPheromoneClient:
            async def calculate_dynamic_weight(self, specialist_type, domain, base_weight=0.2):
                tracker["active"] += 1
                tracker["max"] = max(tracker["max"], tracker["active"])
                await asyncio.sleep(0.1)
                tracker["active"] -= 1
                return 0.2

        orchestrator = ConsensusOrchestrator(_base_config(), SlowPheromoneClient())
        plan = {"plan_id": "p", "intent_id": "i", "original_domain": "BUSINESS"}
        opinions = _opinions(["a", "b", "c", "d", "e"])

        started = time.monotonic()
        weights = await orchestrator._calculate_dynamic_weights(plan, opinions)
        elapsed = time.monotonic() - started

        # Concorrência total: as 5 chamadas estiveram ativas ao mesmo tempo
        assert tracker["max"] == 5
        # Tempo ~= 1 chamada (0.1s), não a soma (0.5s). Em série falharia este limite.
        assert elapsed < 0.3
        assert len(weights) == 5
        assert all(w == 0.2 for w in weights.values())


class TestPublishPheromonesBestEffort:
    """Fix #3: publish pós-decisão nunca bloqueia nem falha a decisão."""

    @pytest.mark.asyncio()
    async def test_timeout_does_not_block_or_raise(self):
        ConsensusOrchestrator = _load_orchestrator_class()
        orchestrator = ConsensusOrchestrator(_base_config(), Mock())

        async def _hang(*args, **kwargs):
            await asyncio.sleep(10)  # muito além do timeout (0.3s)

        orchestrator._publish_pheromones = _hang

        decision = MagicMock()
        decision.decision_id = "d"
        decision.plan_id = "p"

        started = time.monotonic()
        # Não deve levantar e deve respeitar o timeout configurado
        await orchestrator._publish_pheromones_best_effort(decision, {}, [])
        elapsed = time.monotonic() - started

        assert elapsed < 1.0  # cortado pelo timeout de 0.3s, não 10s

    @pytest.mark.asyncio()
    async def test_exception_is_swallowed(self):
        ConsensusOrchestrator = _load_orchestrator_class()
        orchestrator = ConsensusOrchestrator(_base_config(), Mock())

        async def _boom(*args, **kwargs):
            raise RuntimeError("backend de feromônios indisponível")

        orchestrator._publish_pheromones = _boom

        decision = MagicMock()
        decision.decision_id = "d"
        decision.plan_id = "p"

        # Não deve propagar a exceção
        await orchestrator._publish_pheromones_best_effort(decision, {}, [])


class TestRedisTimeoutSettings:
    """Fix #1: settings expõe timeouts de Redis/publish com defaults sãos."""

    def test_redis_timeout_fields_exist_with_defaults(self):
        spec = importlib.util.spec_from_file_location(
            "config.settings", src_path / "config" / "settings.py"
        )
        settings_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(settings_module)

        fields = settings_module.Settings.model_fields
        assert "redis_socket_timeout" in fields
        assert "redis_socket_connect_timeout" in fields
        assert "pheromone_publish_timeout" in fields
        # Defaults curtos: falhar rápido p/ fallback em vez de pendurar minutos
        assert fields["redis_socket_timeout"].default == 2.0
        assert fields["redis_socket_connect_timeout"].default == 2.0
        assert fields["pheromone_publish_timeout"].default == 5.0
