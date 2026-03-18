"""
Conftest para testes do Analyst Agents.
"""
import pytest
import asyncio
from datetime import datetime, timedelta
from motor.motor_asyncio import AsyncIOMotorClient
import sys
import os
from unittest.mock import MagicMock

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Mock problematic modules before importing
sys.modules['src.services.embedding_service'] = MagicMock()
sys.modules['src.services.code_analyzer'] = MagicMock()

from src.models.insight_extended import (
    InsightCreate,
    InsightResponse,
    AnalysisType,
    InsightSource,
    InsightStatus,
    InsightMetadata,
    InsightMetrics,
)
from src.repositories.insight_repository import InsightRepository

# Importar serviços diretamente
import src.services.timeseries_analyzer as ts_module
TimeSeriesAnalyzer = ts_module.TimeSeriesAnalyzer
import src.services.mcp_integration as mcp_module
MCPIntegration = mcp_module.MCPIntegration


@pytest.fixture
async def mongodb_client():
    """Cliente MongoDB para testes."""
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    yield client
    client.close()


@pytest.fixture
async def test_database(mongodb_client):
    """Database de teste."""
    db = mongodb_client["test_analyst_agents"]
    # Limpar antes dos testes
    await db.insights.delete_many({})
    await db.time_series_cache.delete_many({})
    yield db
    # Limpar após os testes
    await db.insights.delete_many({})
    await db.time_series_cache.delete_many({})


@pytest.fixture
async def insight_repository(mongodb_client, test_database):
    """Repositório de insights para testes."""
    repo = InsightRepository(
        client=mongodb_client,
        database=test_database.name,
        ttl_days=90,
        cache_ttl_hours=24,
    )
    await repo.initialize()
    yield repo


@pytest.fixture
def timeseries_analyzer():
    """Analisador de séries temporais para testes."""
    return TimeSeriesAnalyzer(
        anomaly_threshold=2.5,
        min_data_points=5,
        cache_ttl_seconds=3600,
    )


@pytest.fixture
def sample_insight_create():
    """Insight de exemplo para testes."""
    return InsightCreate(
        analysis_type=AnalysisType.TIMESERIES,
        title="Test Insight",
        description="Test description",
        data={"metric_name": "test_metric", "values": [1, 2, 3, 4, 5]},
        metadata=InsightMetadata(source=InsightSource.API, created_by="test"),
        tags=["test", "unit"],
    )


@pytest.fixture
def sample_timeseries_data():
    """Dados de série temporal de exemplo."""
    base_time = datetime.utcnow() - timedelta(hours=1)
    return [
        (base_time + timedelta(minutes=i * 5), 50.0 + i * 0.5)
        for i in range(12)
    ]


@pytest.fixture
def sample_timeseries_with_anomalies():
    """Dados de série temporal com anomalias."""
    import random
    random.seed(42)
    base_time = datetime.utcnow() - timedelta(hours=1)
    data = []
    for i in range(20):
        value = random.gauss(50, 5)
        # Adicionar anomalias
        if i == 5:
            value = 95.0
        elif i == 15:
            value = 5.0
        data.append((base_time + timedelta(minutes=i * 3), value))
    return data


@pytest.fixture
async def mcp_integration():
    """Integração MCP para testes."""
    integration = MCPIntegration(
        scout_url="http://localhost:8000",
        optimizer_url="http://localhost:8001",
        timeout=5.0,
        max_retries=1,
    )
    await integration.initialize()
    yield integration
    await integration.close()
