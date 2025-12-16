import sys
from pathlib import Path
from types import SimpleNamespace
from typing import List

import pytest

ROOT = Path(__file__).resolve().parents[2]
CONS_SRC = ROOT / "services" / "consensus-engine" / "src"
if str(CONS_SRC) not in sys.path:
    sys.path.append(str(CONS_SRC))

from src.config.settings import Settings  # noqa: E402
from src.services.consensus_orchestrator import ConsensusOrchestrator  # noqa: E402


class _DummyPheromoneClient:
    async def calculate_dynamic_weight(self, specialist_type: str, domain: str, base_weight: float = 0.2) -> float:
        return base_weight + 0.05

    async def get_aggregated_pheromone(self, specialist_type: str, domain: str):
        return {"net_strength": 0.1}


def build_mock_opinions():
    return [
        {
            "specialist_type": "technical",
            "opinion": {"confidence_score": 0.7, "risk_score": 0.2, "recommendation": "approve"},
        },
        {
            "specialist_type": "business",
            "opinion": {"confidence_score": 0.85, "risk_score": 0.25, "recommendation": "approve"},
        },
        {
            "specialist_type": "behavior",
            "opinion": {"confidence_score": 0.65, "risk_score": 0.35, "recommendation": "conditional"},
        },
    ]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_consensus_aggregation():
    settings = Settings(
        kafka_bootstrap_servers="localhost:9092",
        redis_cluster_nodes="localhost:6379",
        mongodb_uri="mongodb://localhost:27017",
    )
    orchestrator = ConsensusOrchestrator(settings, pheromone_client=_DummyPheromoneClient())
    opinions = build_mock_opinions()
    cognitive_plan = {"plan_id": "plan-001", "domain": "general"}

    decision = await orchestrator.process_consensus(cognitive_plan, opinions)

    assert 0.0 <= decision.confidence_score <= 1.0
    assert decision.method.value in ["bayesian", "voting", "unanimous", "fallback"]
    assert decision.explainability_token is not None
