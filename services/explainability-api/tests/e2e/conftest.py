"""
E2E Test Configuration and Fixtures.

Configuração específica para testes de ponta a ponta do explainability-api.
"""

import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest

# Add project root to path for imports
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "src"))


# ========== E2E FIXTURES ==========


@pytest.fixture()
def sample_decision_votes() -> list:
    """Votos de decisão de exemplo para testes E2E."""
    return [
        {
            "specialist_id": "business_specialist_001",
            "specialist_type": "business",
            "seniority_level": "senior",
            "vote": "approve",
            "confidence": 0.85,
            "risk": 0.15,
            "reasoning": "Meets business requirements",
        },
        {
            "specialist_id": "technical_specialist_001",
            "specialist_type": "technical",
            "seniority_level": "expert",
            "vote": "approve",
            "confidence": 0.90,
            "risk": 0.10,
            "reasoning": "Technically sound",
        },
        {
            "specialist_id": "architecture_specialist_001",
            "specialist_type": "architecture",
            "seniority_level": "senior",
            "vote": "reject",
            "confidence": 0.70,
            "risk": 0.30,
            "reasoning": "Scalability concerns",
        },
        {
            "specialist_id": "security_specialist_001",
            "specialist_type": "security",
            "seniority_level": "senior",
            "vote": "approve",
            "confidence": 0.75,
            "risk": 0.25,
            "reasoning": "Security risks addressed",
        },
        {
            "specialist_id": "performance_specialist_001",
            "specialist_type": "performance",
            "seniority_level": "mid_level",
            "vote": "approve",
            "confidence": 0.65,
            "risk": 0.35,
            "reasoning": "Performance acceptable",
        },
    ]


@pytest.fixture()
def sample_consensus_decision(sample_decision_votes) -> dict[str, Any]:
    """Decisão de consenso de exemplo para testes E2E."""
    return {
        "decision_id": "e2e_test_decision_001",
        "timestamp": datetime.now(UTC).isoformat(),
        "final_decision": "approve",
        "final_confidence": 0.77,
        "specialist_votes": sample_decision_votes,
    }


@pytest.fixture()
def mock_mongodb():
    """Mock client MongoDB para testes E2E."""
    client = AsyncMock()

    # Mock consensus_decisions collection
    client.consensus_decisions = AsyncMock()

    # Sample votes for testing (matching sample_decision_votes fixture)
    test_votes = [
        {
            "specialist_id": "business_specialist_001",
            "specialist_type": "business",
            "seniority_level": "senior",
            "vote": "approve",
            "confidence": 0.85,
            "risk": 0.15,
            "reasoning": "Meets business requirements",
        },
        {
            "specialist_id": "technical_specialist_001",
            "specialist_type": "technical",
            "seniority_level": "expert",
            "vote": "approve",
            "confidence": 0.90,
            "risk": 0.10,
            "reasoning": "Technically sound",
        },
        {
            "specialist_id": "architecture_specialist_001",
            "specialist_type": "architecture",
            "seniority_level": "senior",
            "vote": "reject",
            "confidence": 0.70,
            "risk": 0.30,
            "reasoning": "Scalability concerns",
        },
        {
            "specialist_id": "security_specialist_001",
            "specialist_type": "security",
            "seniority_level": "senior",
            "vote": "approve",
            "confidence": 0.75,
            "risk": 0.25,
            "reasoning": "Security risks addressed",
        },
        {
            "specialist_id": "performance_specialist_001",
            "specialist_type": "performance",
            "seniority_level": "mid_level",
            "vote": "approve",
            "confidence": 0.65,
            "risk": 0.35,
            "reasoning": "Performance acceptable",
        },
    ]

    async def mock_find_one(query):
        if query.get("decision_id") == "e2e_test_decision_001":
            return {
                "decision_id": "e2e_test_decision_001",
                "final_decision": "approve",
                "final_confidence": 0.77,
                "specialist_votes": test_votes,
            }
        elif query.get("decision_id") == "nonexistent_decision":
            return None
        return None

    client.consensus_decisions.find_one = mock_find_one

    return client


@pytest.fixture()
def v3_service(mock_mongodb) -> "V3ExplanationService":
    """Serviço v3 configurado para testes E2E."""
    from api.routes.v3.hierarchical import V3ExplanationService

    return V3ExplanationService(mock_mongodb)
