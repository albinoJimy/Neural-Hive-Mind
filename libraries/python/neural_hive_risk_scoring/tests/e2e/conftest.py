"""
E2E Test Configuration and Fixtures.

Configuração específica para testes de ponta a ponta do neural_hive_risk_scoring.
"""

import sys
from pathlib import Path

# Add project root to path for imports
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import pytest
from datetime import datetime, timezone
from typing import Dict, Any, List
from unittest.mock import AsyncMock, MagicMock

from risk_scoring.config import RiskScoringConfig, RiskBand
from risk_scoring.models import RiskAssessment, RiskMatrixConfig


# ========== E2E FIXTURES ==========


@pytest.fixture(scope="session")
def e2e_config() -> RiskScoringConfig:
    """
    Configuração base para testes E2E.

    Usa valores realistas mas determinísticos para testes.
    """
    return RiskScoringConfig(
        matrix_config=RiskMatrixConfig(
            weights={
                "confidence": 0.30,
                "risk": 0.30,
                "complexity": 0.20,
                "deadline": 0.20,
            }
        ),
        risk_bands=[
            RiskBand(name="VERY_LOW", min_score=0.0, max_score=0.2, color="green"),
            RiskBand(name="LOW", min_score=0.2, max_score=0.4, color="blue"),
            RiskBand(name="MEDIUM", min_score=0.4, max_score=0.6, color="yellow"),
            RiskBand(name="HIGH", min_score=0.6, max_score=0.8, color="orange"),
            RiskBand(name="CRITICAL", min_score=0.8, max_score=1.0, color="red"),
        ],
        enable_history=True,
        enable_alerts=True,
        enable_ensemble=True,
    )


@pytest.fixture
def e2e_timestamp() -> datetime:
    """Timestamp consistente para testes E2E."""
    return datetime(2026, 4, 7, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def sample_decision_context(e2e_timestamp) -> Dict[str, Any]:
    """Contexto de decisão de exemplo para testes E2E."""
    return {
        "decision_id": "e2e_test_decision_001",
        "timestamp": e2e_timestamp.isoformat(),
        "workflow_id": "workflow_e2e_001",
        "trigger": "manual",
        "test_mode": True,
    }


@pytest.fixture
def low_risk_scenario() -> Dict[str, Any]:
    """Cenário de baixo risco para testes."""
    return {
        "domain_id": "low_risk_domain",
        "domain_type": "TECHNICAL",
        "avg_confidence": 0.92,
        "consensus_rate": 0.95,
        "disagreement_rate": 0.05,
        "recent_failures": 0,
        "complexity_score": 0.15,
        "deadline_pressure": 0.1,
        "specialist_count": 5,
        "seniority_distribution": {
            "expert": 2,
            "senior": 2,
            "mid_level": 1,
        },
    }


@pytest.fixture
def low_risk_votes() -> List[Dict[str, Any]]:
    """Votos de especialistas para cenário de baixo risco."""
    return [
        {
            "specialist_id": "expert_001",
            "specialist_type": "technical",
            "seniority_level": "expert",
            "vote": "approve",
            "confidence": 0.95,
            "risk": 0.05,
            "reasoning": "Solid implementation plan",
        },
        {
            "specialist_id": "expert_002",
            "specialist_type": "architecture",
            "seniority_level": "expert",
            "vote": "approve",
            "confidence": 0.92,
            "risk": 0.08,
            "reasoning": "Well-architected solution",
        },
        {
            "specialist_id": "senior_001",
            "specialist_type": "business",
            "seniority_level": "senior",
            "vote": "approve",
            "confidence": 0.90,
            "risk": 0.10,
            "reasoning": "Meets business requirements",
        },
        {
            "specialist_id": "senior_002",
            "specialist_type": "security",
            "seniority_level": "senior",
            "vote": "approve",
            "confidence": 0.88,
            "risk": 0.12,
            "reasoning": "Security concerns addressed",
        },
        {
            "specialist_id": "mid_001",
            "specialist_type": "performance",
            "seniority_level": "mid_level",
            "vote": "approve",
            "confidence": 0.85,
            "risk": 0.15,
            "reasoning": "Performance acceptable",
        },
    ]


@pytest.fixture
def high_risk_scenario() -> Dict[str, Any]:
    """Cenário de alto risco para testes."""
    return {
        "domain_id": "high_risk_domain",
        "domain_type": "BUSINESS",
        "avg_confidence": 0.35,
        "consensus_rate": 0.45,
        "disagreement_rate": 0.75,
        "recent_failures": 7,
        "complexity_score": 0.90,
        "deadline_pressure": 0.85,
        "specialist_count": 5,
        "seniority_distribution": {
            "trainee": 2,
            "junior": 2,
            "mid_level": 1,
        },
    }


@pytest.fixture
def high_risk_votes() -> List[Dict[str, Any]]:
    """Votos de especialistas para cenário de alto risco."""
    return [
        {
            "specialist_id": "trainee_001",
            "specialist_type": "business",
            "seniority_level": "trainee",
            "vote": "reject",
            "confidence": 0.40,
            "risk": 0.60,
            "reasoning": "Unclear requirements",
        },
        {
            "specialist_id": "trainee_002",
            "specialist_type": "technical",
            "seniority_level": "trainee",
            "vote": "reject",
            "confidence": 0.35,
            "risk": 0.65,
            "reasoning": "Technical feasibility concerns",
        },
        {
            "specialist_id": "junior_001",
            "specialist_type": "architecture",
            "seniority_level": "junior",
            "vote": "reject",
            "confidence": 0.45,
            "risk": 0.55,
            "reasoning": "Architecture not defined",
        },
        {
            "specialist_id": "junior_002",
            "specialist_type": "security",
            "seniority_level": "junior",
            "vote": "reject",
            "confidence": 0.30,
            "risk": 0.70,
            "reasoning": "Security risks identified",
        },
        {
            "specialist_id": "mid_001",
            "specialist_type": "performance",
            "seniority_level": "mid_level",
            "vote": "approve",
            "confidence": 0.50,
            "risk": 0.50,
            "reasoning": "Could work with optimization",
        },
    ]


@pytest.fixture
def mixed_risk_votes() -> List[Dict[str, Any]]:
    """Votos mistos para testar cenários de consenso dividido."""
    return [
        {
            "specialist_id": "expert_001",
            "specialist_type": "technical",
            "seniority_level": "expert",
            "vote": "approve",
            "confidence": 0.85,
            "risk": 0.15,
        },
        {
            "specialist_id": "senior_001",
            "specialist_type": "business",
            "seniority_level": "senior",
            "vote": "approve",
            "confidence": 0.75,
            "risk": 0.25,
        },
        {
            "specialist_id": "senior_002",
            "specialist_type": "architecture",
            "seniority_level": "senior",
            "vote": "reject",
            "confidence": 0.70,
            "risk": 0.30,
        },
        {
            "specialist_id": "mid_001",
            "specialist_type": "security",
            "seniority_level": "mid_level",
            "vote": "reject",
            "confidence": 0.60,
            "risk": 0.40,
        },
        {
            "specialist_id": "junior_001",
            "specialist_type": "performance",
            "seniority_level": "junior",
            "vote": "approve",
            "confidence": 0.55,
            "risk": 0.45,
        },
    ]


@pytest.fixture
def mock_async_mongodb():
    """Mock MongoDB client assíncrono para testes E2E."""
    client = AsyncMock()

    # Mock collections
    client.risk_assessments = AsyncMock()
    client.risk_history = AsyncMock()
    client.risk_alerts = AsyncMock()
    client.specialist_feedback = AsyncMock()

    # Mock find_one - retorna histórico de senioridade
    async def mock_find_one(query=None, *args, **kwargs):
        if query and "specialist_id" in query:
            return {
                "specialist_id": query["specialist_id"],
                "current_level": "senior",
                "previous_level": "mid_level",
                "promoted_at": "2026-03-15T00:00:00Z",
                "history": [
                    {
                        "timestamp": "2026-01-01T00:00:00Z",
                        "from_level": "junior",
                        "to_level": "mid_level",
                        "reason": "performance_review",
                    },
                    {
                        "timestamp": "2026-03-15T00:00:00Z",
                        "from_level": "mid_level",
                        "to_level": "senior",
                        "reason": "promotion",
                    },
                ],
            }
        return None

    client.risk_assessments.find_one = mock_find_one
    client.risk_history.find_one = mock_find_one

    # Mock insert_one
    insert_result = MagicMock()
    insert_result.inserted_id = "e2e_mock_insert_id"

    async def mock_insert_one(doc):
        return insert_result

    client.risk_assessments.insert_one = mock_insert_one
    client.risk_history.insert_one = mock_insert_one
    client.risk_alerts.insert_one = mock_insert_one

    # Mock update_one
    async def mock_update_one(query, update):
        return MagicMock(matched_count=1, modified_count=1)

    client.risk_assessments.update_one = mock_update_one
    client.risk_history.update_one = mock_update_one

    # Mock find (for queries)
    async def mock_find(query=None, *args, **kwargs):
        # Retornar cursor mockado
        cursor = AsyncMock()
        cursor.to_list = MagicMock(return_value=[])
        return cursor

    client.risk_history.find = mock_find
    client.risk_assessments.find = mock_find

    return client


@pytest.fixture
def e2e_performance_thresholds() -> Dict[str, float]:
    """Limites de performance para testes E2E."""
    return {
        "max_assessment_latency_ms": 100,
        "max_batch_avg_latency_ms": 50,
        "max_cache_lookup_ms": 1,
        "min_cache_hit_rate": 0.5,
    }


# ========== PYTEST HOOKS ==========


def pytest_configure(config):
    """Configuração adicional para pytest."""
    config.addinivalue_line(
        "markers",
        "e2e: marca testes como end-to-end (integrados)"
    )
    config.addinivalue_line(
        "markers",
        "slow: marca testes que podem demorar mais"
    )
    config.addinivalue_line(
        "markers",
        "performance: marca testes de performance"
    )
