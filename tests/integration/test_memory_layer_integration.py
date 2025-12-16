import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MEM_SRC = ROOT / "services" / "memory-layer-api" / "src"
if str(MEM_SRC) not in sys.path:
    sys.path.append(str(MEM_SRC))

from src.config.settings import Settings  # noqa: E402
from src.services.data_quality_monitor import DataQualityMonitor  # noqa: E402


class _FakeMongo:
    async def find(self, collection: str, filter, limit: int = 1000):
        # Simula documentos armazenados no MongoDB
        return [
            {"entity_id": "e1", "created_at": "2024-01-01T00:00:00", "value": 10},
            {"entity_id": "e2", "created_at": "2024-01-01T00:00:00", "value": 20},
        ]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_memory_layer_data_quality_monitor(monkeypatch):
    settings = Settings(
        neo4j_password="test",
        clickhouse_password="test",
    )
    monitor = DataQualityMonitor(_FakeMongo(), settings)

    is_valid, violations = await monitor.validate_data(
        {"entity_id": "e1", "created_at": "2024-01-01T00:00:00", "value": 10},
        {"required": ["entity_id", "created_at"], "types": {"value": int}},
    )
    assert is_valid is True
    assert violations == []

    scores = await monitor.calculate_quality_score(data_type="context", sample_size=10)
    assert set(scores.keys()) == {
        "completeness_score",
        "accuracy_score",
        "timeliness_score",
        "uniqueness_score",
        "consistency_score",
        "overall_score",
    }
