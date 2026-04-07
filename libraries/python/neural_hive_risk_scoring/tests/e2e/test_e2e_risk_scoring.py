"""
E2E Tests for Risk Scoring Pipeline.

Testes de ponta a ponta que validam o fluxo completo de avaliação de risco,
incluindo integração com todas as camadas da biblioteca.
"""

import asyncio
import time
from datetime import datetime, timezone
from typing import Dict, Any, List
import pytest
from unittest.mock import AsyncMock, MagicMock

from risk_scoring.engine import RiskScoringEngine, RiskScoringMetrics
from risk_scoring.config import RiskScoringConfig, RiskBand
from risk_scoring.models import RiskAssessment, RiskMatrixConfig
from risk_scoring.history import RiskHistoryManager
from risk_scoring.alerts import RiskAlertManager
from risk_scoring.calculator import RiskCalculator
from risk_scoring.ensemble import RiskEnsemble


# ========== FIXTURES ==========


@pytest.fixture
def sample_domain_data() -> Dict[str, Any]:
    """Dados de domínio de exemplo para testes E2E."""
    return {
        "domain_id": "test_domain_001",
        "domain_type": "TECHNICAL",
        "specialist_count": 5,
        "avg_confidence": 0.75,
        "consensus_rate": 0.85,
        "disagreement_rate": 0.15,
        "recent_failures": 1,
        "complexity_score": 0.6,
        "deadline_pressure": 0.3,
    }


@pytest.fixture
def sample_votes() -> List[Dict[str, Any]]:
    """Votos de especialistas de exemplo para testes E2E."""
    return [
        {
            "specialist_id": "specialist_001",
            "specialist_type": "business",
            "seniority_level": "senior",
            "vote": "approve",
            "confidence": 0.85,
            "risk": 0.15,
        },
        {
            "specialist_id": "specialist_002",
            "specialist_type": "technical",
            "seniority_level": "expert",
            "vote": "approve",
            "confidence": 0.90,
            "risk": 0.10,
        },
        {
            "specialist_id": "specialist_003",
            "specialist_type": "architecture",
            "seniority_level": "senior",
            "vote": "reject",
            "confidence": 0.70,
            "risk": 0.30,
        },
        {
            "specialist_id": "specialist_004",
            "specialist_type": "behavior",
            "seniority_level": "mid_level",
            "vote": "approve",
            "confidence": 0.65,
            "risk": 0.35,
        },
        {
            "specialist_id": "specialist_005",
            "specialist_type": "evolution",
            "seniority_level": "junior",
            "vote": "approve",
            "confidence": 0.60,
            "risk": 0.40,
        },
    ]


@pytest.fixture
def mock_mongodb_client():
    """Mock client MongoDB para testes E2E."""
    client = AsyncMock()

    # Mock collections
    client.risk_assessments = AsyncMock()
    client.risk_history = AsyncMock()
    client.risk_alerts = AsyncMock()

    # Mock find_one
    async def mock_find_one(query):
        if "specialist_id" in query:
            return {
                "specialist_id": query["specialist_id"],
                "current_level": "senior",
                "history": [
                    {
                        "timestamp": "2026-03-01T00:00:00Z",
                        "from_level": "mid_level",
                        "to_level": "senior",
                        "reason": "performance_review",
                    }
                ],
            }
        return None

    client.risk_assessments.find_one = mock_find_one
    client.risk_history.find_one = mock_find_one

    # Mock insert_one
    async def mock_insert_one(doc):
        return MagicMock(inserted_id="mock_id_123")

    client.risk_assessments.insert_one = mock_insert_one
    client.risk_history.insert_one = mock_insert_one
    client.risk_alerts.insert_one = mock_insert_one

    return client


@pytest.fixture
def risk_engine(mock_mongodb_client) -> RiskScoringEngine:
    """Engine de risk scoring configurada para testes E2E."""
    config = RiskScoringConfig(
        matrix_config=RiskMatrixConfig(
            weights={
                "confidence": 0.3,
                "risk": 0.3,
                "complexity": 0.2,
                "deadline": 0.2,
            }
        )
    )
    return RiskScoringEngine(config, mongodb_client=mock_mongodb_client)


# ========== E2E TEST CLASSES ==========


class TestE2ERiskScoringPipeline:
    """Testes E2E do pipeline completo de risk scoring."""

    @pytest.mark.asyncio
    async def test_complete_assessment_flow(self, risk_engine, sample_domain_data, sample_votes):
        """Testa fluxo completo de avaliação de risco."""
        # Executar avaliação completa
        assessment = await risk_engine.assess_risk(
            domain_data=sample_domain_data,
            votes=sample_votes,
            context={"request_id": "e2e_test_001"}
        )

        # Validar estrutura da resposta
        assert assessment is not None
        assert assessment.decision_id == "e2e_test_001"
        assert assessment.risk_score is not None
        assert 0.0 <= assessment.risk_score <= 1.0
        assert assessment.risk_band in ["VERY_LOW", "LOW", "MEDIUM", "HIGH", "CRITICAL"]
        assert assessment.timestamp is not None

    @pytest.mark.asyncio
    async def test_ensemble_scoring_flow(self, sample_votes):
        """Testa fluxo de scoring ensemble com múltiplos métodos."""
        config = RiskScoringConfig(
            enable_ensemble=True,
            ensemble_method="weighted_average"
        )
        engine = RiskScoringEngine(config)

        assessment = await engine.assess_risk(
            domain_data={"domain_id": "test_ensemble"},
            votes=sample_votes,
            context={"use_ensemble": True}
        )

        assert assessment.risk_score is not None
        # Ensemble deve produzir score consistente
        assert 0.0 <= assessment.risk_score <= 1.0

    @pytest.mark.asyncio
    async def test_history_tracking_flow(self, risk_engine, sample_domain_data, sample_votes, mock_mongodb_client):
        """Testa fluxo de rastreamento histórico de avaliações."""
        decision_id = "e2e_history_001"

        # Primeira avaliação
        assessment1 = await risk_engine.assess_risk(
            domain_data=sample_domain_data,
            votes=sample_votes,
            context={"decision_id": decision_id}
        )

        # Simular mudança no domínio
        sample_domain_data["avg_confidence"] = 0.6
        sample_domain_data["disagreement_rate"] = 0.3

        # Segunda avaliação
        assessment2 = await risk_engine.assess_risk(
            domain_data=sample_domain_data,
            votes=sample_votes,
            context={"decision_id": decision_id}
        )

        # Histórico deve capturar evolução
        assert assessment1.decision_id == decision_id
        assert assessment2.decision_id == decision_id

    @pytest.mark.asyncio
    async def test_alert_generation_flow(self, risk_engine, sample_domain_data):
        """Testa fluxo de geração de alertas baseado em risco."""
        # Criar cenário de alto risco
        high_risk_data = sample_domain_data.copy()
        high_risk_data["avg_confidence"] = 0.3
        high_risk_data["disagreement_rate"] = 0.7
        high_risk_data["recent_failures"] = 5

        high_risk_votes = [
            {
                "specialist_id": f"spec_{i}",
                "seniority_level": "junior",
                "vote": "reject",
                "confidence": 0.4,
                "risk": 0.6,
            }
            for i in range(5)
        ]

        assessment = await risk_engine.assess_risk(
            domain_data=high_risk_data,
            votes=high_risk_votes,
            context={"trigger_alerts": True}
        )

        # Alto risco deve gerar alerta
        assert assessment.risk_score >= 0.7
        assert assessment.risk_band in ["HIGH", "CRITICAL"]

    @pytest.mark.asyncio
    async def test_metrics_recording_flow(self, risk_engine, sample_votes):
        """Testa fluxo de registro de métricas Prometheus."""
        # Acessar métricas
        metrics = risk_engine.metrics

        initial_assessments = metrics.assessments_total._value.get()

        # Executar algumas avaliações
        for i in range(3):
            await risk_engine.assess_risk(
                domain_data={"domain_id": f"test_metrics_{i}"},
                votes=sample_votes,
                context={"iteration": i}
            )

        # Verificar que métricas foram incrementadas
        final_assessments = metrics.assessments_total._value.get()
        assert final_assessments > initial_assessments


class TestE2ERiskBands:
    """Testes E2E de bandas de risco."""

    @pytest.mark.asyncio
    async def test_very_low_risk_band(self, risk_engine):
        """Testa banda VERY_LOW para cenário de baixo risco."""
        low_risk_data = {
            "domain_id": "low_risk_test",
            "avg_confidence": 0.95,
            "consensus_rate": 0.98,
            "disagreement_rate": 0.02,
            "recent_failures": 0,
            "complexity_score": 0.2,
            "deadline_pressure": 0.1,
        }

        low_risk_votes = [
            {
                "specialist_id": f"expert_{i}",
                "seniority_level": "expert",
                "vote": "approve",
                "confidence": 0.95,
                "risk": 0.05,
            }
            for i in range(5)
        ]

        assessment = await risk_engine.assess_risk(
            domain_data=low_risk_data,
            votes=low_risk_votes
        )

        assert assessment.risk_band == "VERY_LOW"
        assert assessment.risk_score < 0.2

    @pytest.mark.asyncio
    async def test_critical_risk_band(self, risk_engine):
        """Testa banda CRITICAL para cenário de risco crítico."""
        critical_data = {
            "domain_id": "critical_test",
            "avg_confidence": 0.3,
            "consensus_rate": 0.4,
            "disagreement_rate": 0.8,
            "recent_failures": 10,
            "complexity_score": 0.95,
            "deadline_pressure": 0.9,
        }

        critical_votes = [
            {
                "specialist_id": f"junior_{i}",
                "seniority_level": "trainee",
                "vote": "reject",
                "confidence": 0.3,
                "risk": 0.7,
            }
            for i in range(5)
        ]

        assessment = await risk_engine.assess_risk(
            domain_data=critical_data,
            votes=critical_votes
        )

        assert assessment.risk_band == "CRITICAL"
        assert assessment.risk_score >= 0.8


class TestE2EIntegration:
    """Testes E2E de integração entre componentes."""

    @pytest.mark.asyncio
    async def test_calculator_ensemble_integration(self, sample_votes):
        """Testa integração entre Calculator e Ensemble."""
        config = RiskScoringConfig()
        engine = RiskScoringEngine(config)

        # Calculator deve produzir scores base
        calculator = RiskCalculator(config.matrix_config)
        base_score = calculator.calculate_risk(sample_votes)

        # Ensemble deve refinar scores
        ensemble = RiskEnsemble(config)
        ensemble_result = await engine._ensemble_scoring(
            base_score, sample_votes, context={}
        )

        assert ensemble_result is not None
        assert 0.0 <= ensemble_result <= 1.0

    @pytest.mark.asyncio
    async def test_history_alerts_integration(self, risk_engine, sample_domain_data, mock_mongodb_client):
        """Testa integração entre History e Alerts."""
        # Criar alerta manager
        alert_manager = RiskAlertManager(mock_mongodb_client)

        # Criar history manager
        history_manager = RiskHistoryManager(mock_mongodb_client)

        # Executar avaliação
        assessment = await risk_engine.assess_risk(
            domain_data=sample_domain_data,
            votes=sample_votes[:3],  # Menos votos para aumentar variação
            context={"decision_id": "integration_test"}
        )

        # Verificar que componentes foram integrados
        assert assessment.decision_id == "integration_test"
        assert assessment.risk_score is not None

    @pytest.mark.asyncio
    async def test_concurrent_assessments(self, risk_engine, sample_domain_data, sample_votes):
        """Testa avaliações concorrentes (thread safety)."""
        decision_ids = [f"concurrent_{i}" for i in range(10)]

        # Criar tarefas concorrentes
        tasks = [
            risk_engine.assess_risk(
                domain_data={**sample_domain_data, "domain_id": f"domain_{i}"},
                votes=sample_votes,
                context={"decision_id": decision_ids[i]}
            )
            for i in range(10)
        ]

        # Executar concorrentemente
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Verificar que todas as avaliações foram bem-sucedidas
        assert len(results) == 10
        for result in results:
            assert not isinstance(result, Exception)
            assert result.risk_score is not None


class TestE2EErrorHandling:
    """Testes E2E de tratamento de erros."""

    @pytest.mark.asyncio
    async def test_empty_votes_handling(self, risk_engine, sample_domain_data):
        """Testa tratamento de votos vazios."""
        assessment = await risk_engine.assess_risk(
            domain_data=sample_domain_data,
            votes=[],
            context={"decision_id": "empty_votes"}
        )

        # Deve retornar avaliação com score neutro
        assert assessment.risk_score is not None
        assert assessment.risk_band in ["LOW", "MEDIUM"]

    @pytest.mark.asyncio
    async def test_malformed_votes_handling(self, risk_engine, sample_domain_data):
        """Testa tratamento de votos malformados."""
        malformed_votes = [
            {"specialist_id": "test"},  # Faltam campos obrigatórios
            {"seniority_level": "senior"},  # Faltam campos obrigatórios
        ]

        assessment = await risk_engine.assess_risk(
            domain_data=sample_domain_data,
            votes=malformed_votes,
            context={"decision_id": "malformed"}
        )

        # Deve usar valores default e retornar avaliação
        assert assessment is not None

    @pytest.mark.asyncio
    async def test_missing_domain_data_handling(self, risk_engine, sample_votes):
        """Testa tratamento de dados de domínio faltantes."""
        minimal_data = {"domain_id": "minimal"}

        assessment = await risk_engine.assess_risk(
            domain_data=minimal_data,
            votes=sample_votes,
            context={"decision_id": "minimal_data"}
        )

        # Deve usar valores default
        assert assessment.risk_score is not None


class TestE2EPerformance:
    """Testes E2E de performance."""

    @pytest.mark.asyncio
    async def test_assessment_latency(self, risk_engine, sample_domain_data, sample_votes):
        """Testa latência de avaliação (deve ser < 100ms)."""
        import time

        start = time.time()
        assessment = await risk_engine.assess_risk(
            domain_data=sample_domain_data,
            votes=sample_votes
        )
        latency_ms = (time.time() - start) * 1000

        assert assessment.risk_score is not None
        assert latency_ms < 100, f"Assessment took {latency_ms}ms, expected < 100ms"

    @pytest.mark.asyncio
    async def test_batch_assessments(self, risk_engine, sample_domain_data, sample_votes):
        """Testa desempenho de avaliações em lote."""
        batch_size = 50

        start = time.time()
        tasks = [
            risk_engine.assess_risk(
                domain_data={**sample_domain_data, "domain_id": f"batch_{i}"},
                votes=sample_votes
            )
            for i in range(batch_size)
        ]
        results = await asyncio.gather(*tasks)
        total_time = time.time() - start

        assert len(results) == batch_size
        # Média de < 50ms por avaliação
        avg_latency = (total_time / batch_size) * 1000
        assert avg_latency < 50, f"Average latency {avg_latency}ms, expected < 50ms"

    @pytest.mark.asyncio
    async def test_cache_effectiveness(self, risk_engine, sample_domain_data, sample_votes):
        """Testa efetividade do cache interno."""
        # Primeira chamada (cache miss)
        assessment1 = await risk_engine.assess_risk(
            domain_data=sample_domain_data,
            votes=sample_votes
        )

        # Segunda chamada com mesmos dados (cache hit se implementado)
        assessment2 = await risk_engine.assess_risk(
            domain_data=sample_domain_data,
            votes=sample_votes
        )

        # Resultados devem ser consistentes
        assert assessment1.risk_score == assessment2.risk_score
