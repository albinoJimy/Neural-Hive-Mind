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

# Set environment variables BEFORE any imports
os.environ.setdefault('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092')
os.environ.setdefault('MONGODB_URI', 'mongodb://localhost:27017')
os.environ.setdefault('MONGODB_DATABASE', 'test_analyst_agents')
os.environ.setdefault('REDIS_HOST', 'localhost')
os.environ.setdefault('REDIS_PORT', '6379')
os.environ.setdefault('NEO4J_URI', 'bolt://localhost:7687')
os.environ.setdefault('NEO4J_USER', 'neo4j')
os.environ.setdefault('NEO4J_PASSWORD', 'password')
os.environ.setdefault('CLICKHOUSE_HOST', 'localhost')
os.environ.setdefault('CLICKHOUSE_PORT', '8123')
os.environ.setdefault('CLICKHOUSE_USER', 'default')
os.environ.setdefault('CLICKHOUSE_PASSWORD', '')
os.environ.setdefault('CLICKHOUSE_DATABASE', 'test')
os.environ.setdefault('ELASTICSEARCH_HOSTS', '["http://localhost:9200"]')
os.environ.setdefault('PROMETHEUS_URL', 'http://localhost:9090')
os.environ.setdefault('QUEEN_AGENT_GRPC_HOST', 'localhost')
os.environ.setdefault('QUEEN_AGENT_GRPC_PORT', '50051')
os.environ.setdefault('SERVICE_REGISTRY_GRPC_HOST', 'localhost')
os.environ.setdefault('SERVICE_REGISTRY_GRPC_PORT', '50052')
os.environ.setdefault('FASTAPI_HOST', '0.0.0.0')
os.environ.setdefault('FASTAPI_PORT', '8000')
os.environ.setdefault('GRPC_ENABLED', 'false')
os.environ.setdefault('CORS_ORIGINS', '["*","http://localhost","http://localhost:8000"]')
os.environ.setdefault('SERVICE_VERSION', '0.1.0')
os.environ.setdefault('OTEL_EXPORTER_OTLP_ENDPOINT', 'http://localhost:4317')
os.environ.setdefault('ANALYTICS_MIN_CONFIDENCE', '0.5')
os.environ.setdefault('ANALYTICS_WINDOW_SIZE_SECONDS', '300')
os.environ.setdefault('REDIS_INSIGHTS_TTL', '3600')
os.environ.setdefault('KAFKA_CONSUMER_GROUP', 'test-group')
os.environ.setdefault('KAFKA_TOPICS_INSIGHTS', 'insights')
os.environ.setdefault('KAFKA_TOPICS_TELEMETRY', 'telemetry')
os.environ.setdefault('KAFKA_TOPICS_CONSENSUS', 'consensus')
os.environ.setdefault('KAFKA_TOPICS_EXECUTION', 'execution')
os.environ.setdefault('KAFKA_TOPICS_PHEROMONES', 'pheromones')

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Mock problematic modules before importing
sys.modules['elasticsearch'] = MagicMock()
sys.modules['elasticsearch.helpers'] = MagicMock()
sys.modules['clickhouse_driver'] = MagicMock()
sys.modules['neo4j'] = MagicMock()
sys.modules['prometheus_client'] = MagicMock()

# Create proper RpcError exception class for grpc
class GrpcRpcError(Exception):
    """Mock grpc.RpcError for testing"""
    def __init__(self, code):
        super().__init__(f"gRPC error: {code}")
        self._code = code

    def code(self):
        return self._code

# Create StatusCode enum for grpc
from enum import IntEnum
class StatusCode(IntEnum):
    OK = 0
    CANCELLED = 1
    UNKNOWN = 2
    INVALID_ARGUMENT = 3
    DEADLINE_EXCEEDED = 4
    NOT_FOUND = 5
    ALREADY_EXISTS = 6
    PERMISSION_DENIED = 7
    UNAUTHENTICATED = 16
    RESOURCE_EXHAUSTED = 8
    FAILED_PRECONDITION = 9
    ABORTED = 10
    OUT_OF_RANGE = 11
    UNIMPLEMENTED = 12
    INTERNAL = 13
    UNAVAILABLE = 14
    DATA_LOSS = 15

# Mock grpc with __version__ attribute (>= 1.68.1 for protobuf compatibility)
mock_grpc = MagicMock()
mock_grpc.__version__ = "1.68.1"
mock_grpc.ssl_channel_credentials = MagicMock()
mock_grpc.local_channel_credentials = MagicMock()
mock_grpc.server = MagicMock()
mock_grpc.secure_channel = MagicMock()
mock_grpc.insecure_channel = MagicMock()
mock_grpc.ChannelCredentials = MagicMock()
mock_grpc.LocalChannelCredentials = MagicMock()
mock_grpc.RpcError = GrpcRpcError
mock_grpc.StatusCode = StatusCode

# Mock grpc._utilities for version check
mock_grpc_utilities = MagicMock()
mock_grpc_utilities.first_version_is_lower = lambda v1, v2: False  # Always return False (version is OK)
sys.modules['grpc._utilities'] = mock_grpc_utilities

sys.modules['grpc'] = mock_grpc

mock_grpc_aio = MagicMock()
mock_grpc_aio.__version__ = "1.68.1"
mock_grpc_aio.ssl_channel_credentials = MagicMock()
mock_grpc_aio.local_channel_credentials = MagicMock()
mock_grpc_aio.server = MagicMock()
mock_grpc_aio.secure_channel = MagicMock()
mock_grpc_aio.insecure_channel = MagicMock()
mock_grpc_aio.ChannelCredentials = MagicMock()
mock_grpc_aio.LocalChannelCredentials = MagicMock()
mock_grpc_aio.RpcError = GrpcRpcError
mock_grpc_aio.StatusCode = StatusCode
sys.modules['grpc.aio'] = mock_grpc_aio

sys.modules['src.services.embedding_service'] = MagicMock()
sys.modules['src.services.code_analyzer'] = MagicMock()
sys.modules['src.clients.elasticsearch_client'] = MagicMock()
sys.modules['src.clients.clickhouse_client'] = MagicMock()
sys.modules['src.clients.neo4j_client'] = MagicMock()
sys.modules['src.clients.prometheus_client'] = MagicMock()

# Mock neural_hive_observability package
mock_observability = MagicMock()
mock_observability.init_observability = MagicMock()
# instrument_grpc_channel deve retornar o channel que recebe
mock_observability.instrument_grpc_channel = lambda channel, **kwargs: channel
sys.modules['neural_hive_observability'] = mock_observability
sys.modules['neural_hive_observability.health'] = MagicMock()
sys.modules['neural_hive_observability.health_checks'] = MagicMock()
sys.modules['neural_hive_observability.health_checks.clickhouse'] = MagicMock()
sys.modules['neural_hive_observability.config'] = MagicMock()
# Mock inject_grpc_context to return empty list
mock_grpc_instrumentation = MagicMock()
mock_grpc_instrumentation.inject_grpc_context = lambda: []
sys.modules['neural_hive_observability.grpc_instrumentation'] = mock_grpc_instrumentation
sys.modules['neural_hive_observability.context'] = MagicMock()
sys.modules['neural_hive_observability.health_checks.clickhouse'] = MagicMock()

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
    """Cliente MongoDB mockado para testes."""
    from unittest.mock import AsyncMock, MagicMock

    # Mock database
    mock_db = MagicMock()
    mock_insights_collection = MagicMock()
    mock_cache_collection = MagicMock()

    # Mock collection methods
    async def mock_insert_one(doc):
        return MagicMock(inserted_id="mock_id")

    async def mock_find_one(query):
        return None

    async def mock_find(query=None):
        mock_cursor = AsyncMock()
        mock_cursor.sort = MagicMock(return_value=mock_cursor)
        mock_cursor.skip = MagicMock(return_value=mock_cursor)
        mock_cursor.limit = MagicMock(return_value=mock_cursor)

        async def iterate():
            return []
        mock_cursor.__aiter__ = lambda self: self
        mock_cursor.__anext__ = lambda self: (_ for _ in ()).throw(StopAsyncIteration)
        return mock_cursor

    async def mock_count_documents(query):
        return 0

    async def mock_update_one(query, update, upsert=False):
        return MagicMock(modified_count=0, upserted_id="mock_id")

    async def mock_delete_one(query):
        return MagicMock(deleted_count=0)

    async def mock_aggregate(pipeline):
        async def iterate():
            return []
        mock_cursor = AsyncMock()
        mock_cursor.__aiter__ = lambda self: self
        mock_cursor.__anext__ = lambda self: (_ for _ in ()).throw(StopAsyncIteration)
        return mock_cursor

    mock_insights_collection.insert_one = mock_insert_one
    mock_insights_collection.find_one = mock_find_one
    mock_insights_collection.find = mock_find
    mock_insights_collection.count_documents = mock_count_documents
    mock_insights_collection.update_one = mock_update_one
    mock_insights_collection.delete_one = mock_delete_one
    mock_insights_collection.aggregate = mock_aggregate

    mock_cache_collection.find_one = mock_find_one
    mock_cache_collection.update_one = mock_update_one
    mock_cache_collection.delete_one = mock_delete_one

    mock_db.insights = mock_insights_collection
    mock_db.time_series_cache = mock_cache_collection
    mock_db.name = "test_analyst_agents"

    # Mock client
    mock_client = AsyncMock()
    mock_client.__getitem__ = lambda self, name: mock_db

    yield mock_client


@pytest.fixture
async def test_database(mongodb_client):
    """Database de teste."""
    return mongodb_client["test_analyst_agents"]


@pytest.fixture
async def insight_repository(mongodb_client, test_database):
    """Repositório de insights para testes com mock."""
    from unittest.mock import AsyncMock, MagicMock
    from datetime import datetime, timedelta
    from src.models.insight_extended import InsightResponse, InsightCreate, InsightStatus, InsightMetrics, AnalysisType, InsightSource, InsightMetadata
    import uuid

    # In-memory storage para testes
    storage = {"insights": {}, "cache": {}}

    # Create a custom mock repository that actually stores data
    class MockInsightRepository(InsightRepository):
        def __init__(self):
            self.storage = storage
            self.collection = "insights"
            self.cache_collection = "time_series_cache"
            self._db = MagicMock()
            self._db[self.collection] = MagicMock()
            self._db[self.cache_collection] = MagicMock()

        async def create(self, insight: InsightCreate) -> InsightResponse:
            doc = insight.model_dump() if hasattr(insight, 'model_dump') else insight.dict()
            doc["insight_id"] = str(uuid.uuid4())
            doc["status"] = InsightStatus.PENDING.value
            doc["created_at"] = datetime.utcnow()
            doc["expires_at"] = datetime.utcnow() + timedelta(days=90)
            doc["metrics"] = InsightMetrics(processing_time_ms=0, confidence_score=0.0, data_points=0).model_dump()
            self.storage["insights"][doc["insight_id"]] = doc
            return InsightResponse(**doc)

        async def get_by_id(self, insight_id: str):
            doc = self.storage["insights"].get(insight_id)
            if doc:
                return InsightResponse(**doc)
            return None

        async def list(self, **kwargs):
            limit = kwargs.get('limit', 50)
            offset = kwargs.get('offset', 0)

            # Simple filtering
            items = list(self.storage["insights"].values())

            # Apply filters
            if kwargs.get('analysis_type'):
                items = [i for i in items if i.get('analysis_type') == kwargs['analysis_type'].value]
            if kwargs.get('source'):
                items = [i for i in items if i.get('metadata', {}).get('source') == kwargs['source'].value]
            if kwargs.get('tags'):
                tags = kwargs['tags']
                items = [i for i in items if any(t in i.get('tags', []) for t in tags)]
            if kwargs.get('status'):
                items = [i for i in items if i.get('status') == kwargs['status'].value]

            total = len(items)
            items = sorted(items, key=lambda x: x.get('created_at', datetime.min), reverse=True)
            items = items[offset:offset + limit]

            return [InsightResponse(**i) for i in items], total

        async def update_status(self, insight_id: str, status: InsightStatus, data=None):
            if insight_id in self.storage["insights"]:
                doc = self.storage["insights"][insight_id]
                doc["status"] = status.value
                if data:
                    doc["data"] = data
                return InsightResponse(**doc)
            return None

        async def update_metrics(self, insight_id: str, metrics: dict):
            if insight_id in self.storage["insights"]:
                doc = self.storage["insights"][insight_id]
                doc["metrics"] = metrics
                return InsightResponse(**doc)
            return None

        async def delete(self, insight_id: str):
            if insight_id in self.storage["insights"]:
                del self.storage["insights"][insight_id]
                return True
            return False

        async def cache_set(self, cache_key, metric_name, data, statistics):
            import copy
            doc = {
                "cache_key": cache_key,
                "metric_name": metric_name,
                "data": copy.copy(data),
                "statistics": copy.copy(statistics),
                "created_at": datetime.utcnow(),
                "expires_at": datetime.utcnow() + timedelta(hours=24),
            }
            self.storage["cache"][cache_key] = doc
            from src.models.insight_extended import TimeSeriesCacheEntry
            return TimeSeriesCacheEntry(**doc)

        async def cache_get(self, cache_key):
            if cache_key in self.storage["cache"]:
                from src.models.insight_extended import TimeSeriesCacheEntry
                return TimeSeriesCacheEntry(**self.storage["cache"][cache_key])
            return None

        async def cache_delete(self, cache_key):
            if cache_key in self.storage["cache"]:
                del self.storage["cache"][cache_key]
                return True
            return False

        async def get_analytics_summary(self, time_range_hours=24):
            items = list(self.storage["insights"].values())

            insights_by_type = {}
            for item in items:
                at = item.get('analysis_type', 'unknown')
                insights_by_type[at] = insights_by_type.get(at, 0) + 1

            return {
                "insights_by_type": insights_by_type,
                "anomalies_detected": 0,
                "avg_processing_time_ms": 0,
                "confidence_distribution": {"high": 0, "medium": 0, "low": 0},
                "top_sources": [],
            }

    yield MockInsightRepository()


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
