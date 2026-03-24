"""
Pytest fixtures para testes de evolution_hooks.

Este módulo fornece fixtures compartilhadas para todos os testes
do sistema Evolution Hooks.
"""

import pytest
from datetime import datetime
from unittest.mock import Mock


@pytest.fixture
async def mongo_client():
    """
    MongoDB client async mock para testes.

    Cria um mock que simula o comportamento do motor AsyncIOMotorClient.
    """
    class AsyncMockMongoCollection:
        def __init__(self):
            self.data = {}

        async def insert_one(self, doc):
            result = Mock()
            result.inserted_id = f"mock_id_{id(doc)}"
            self.data[result.inserted_id] = doc
            return result

        async def find_one(self, query):
            if "_id" in query:
                for pid, pdoc in self.data.items():
                    if pid == query["_id"]:
                        result = {**pdoc, "_id": pid}
                        return result
            elif "plan_id" in query:
                for pid, pdoc in self.data.items():
                    if pdoc.get("plan_id") == query["plan_id"]:
                        result = {**pdoc, "_id": pid}
                        return result
            return None

        def find(self, *args, **kwargs):
            # Retorna cursor mock que suporta chaining
            cursor = self
            cursor._query = args[0] if args else None
            return cursor

        def sort(self, *args):
            return self

        def limit(self, limit_val):
            self._limit = limit_val
            return self

        async def to_list(self, length=None):
            results = []
            for pid, pdoc in self.data.items():
                results.append({**pdoc, "_id": pid})
            return results[:getattr(self, '_limit', len(results))]

        async def update_one(self, query, update_doc):
            result = Mock()
            result.modified_count = 0

            if "$set" in update_doc and "plan_id" in query:
                for pid, pdoc in self.data.items():
                    if pdoc.get("plan_id") == query["plan_id"]:
                        pdoc.update(update_doc["$set"])
                        if "$inc" in update_doc:
                            for key, val in update_doc["$inc"].items():
                                parts = key.split(".")
                                curr = pdoc
                                for part in parts[:-1]:
                                    if part not in curr:
                                        curr[part] = {}
                                    curr = curr[part]
                                curr[parts[-1]] = curr.get(parts[-1], 0) + val
                        result.modified_count = 1
                        break
            return result

        async def count_documents(self, query=None):
            return len(self.data)

        def to_list(self, length=None):
            results = []
            for pid, pdoc in self.data.items():
                results.append({**pdoc, "_id": pid})
            return results[:getattr(self, '_limit', len(results))]

        def aggregate(self, pipeline):
            # Simular agregação simples para domain_distribution
            return self

    class AsyncMockMongoDatabase:
        def __init__(self):
            self._collections = {}

        def __getitem__(self, name):
            if name not in self._collections:
                self._collections[name] = AsyncMockMongoCollection()
            return self._collections[name]

        def command(self, *args, **kwargs):
            return {"ok": 1}

    class AsyncMockMongoClient:
        def __init__(self):
            self._db = AsyncMockMongoDatabase()
            self.admin = AsyncMockMongoDatabase()

        def __getitem__(self, name):
            return self._db

        def __getattr__(self, name):
            return self._db

        def close(self):
            pass

    client = AsyncMockMongoClient()
    yield client


@pytest.fixture
async def clean_registry(mongo_client):
    """
    Registry limpo para cada teste.

    Uso: adicione este fixture aos testes que precisam de DB limpo.
    """
    client = mongo_client
    db = client["test_neural_hive_specialists"]
    collection = db["evolution_pattern_registry"]

    # Limpar dados antes do teste
    collection.data.clear()

    yield

    # Limpar após o teste
    collection.data.clear()


@pytest.fixture
def sample_fingerprint():
    """
    Fingerprint de exemplo para testes.
    """
    from neural_hive_specialists.evolution_hooks.models import (
        Fingerprint,
        TaskCountRange,
        DurationRange
    )

    return Fingerprint(
        domain="technical",
        priority="high",
        task_count_range=TaskCountRange.MEDIUM,
        task_types=["BUILD", "TEST", "DEPLOY"],
        avg_dependency_count=1.5,
        has_conditional_deps=True,
        estimated_duration_range=DurationRange.MEDIUM,
        complexity_signature="T-H-B-T-D-M"
    )


@pytest.fixture
def sample_evaluation():
    """
    Avaliação de exemplo para testes.
    """
    from neural_hive_specialists.evolution_hooks.models import (
        EvolutionEvaluation,
        DEFAULT_WEIGHTS
    )

    return EvolutionEvaluation(
        confidence_score=0.75,
        risk_score=0.25,
        recommendation="approve",
        weights_used=DEFAULT_WEIGHTS.copy(),
        reasoning_factors=[
            {
                "factor_name": "maintainability",
                "weight": 0.25,
                "score": 0.8,
                "description": "Good maintainability"
            }
        ]
    )


@pytest.fixture
def sample_feedback():
    """
    Feedback de exemplo para testes.
    """
    from neural_hive_specialists.evolution_hooks.models import (
        FeedbackData,
        FeedbackOutcome,
        FeedbackSource
    )

    return FeedbackData(
        outcome=FeedbackOutcome.APPROVE,
        source=FeedbackSource.HUMAN,
        reasoning="Approved after review",
        timestamp=datetime.utcnow()
    )


@pytest.fixture
def sample_plan_dict():
    """
    Plano cognitivo de exemplo como dict.
    """
    return {
        "plan_id": "test-plan-123",
        "version": "1.0.0",
        "intent_id": "test-intent-456",
        "correlation_id": "test-corr-789",
        "trace_id": "test-trace-abc",
        "tasks": [
            {
                "task_id": "task-1",
                "task_type": "BUILD",
                "name": "Build Application",
                "description": "Build the application",
                "dependencies": [],
                "estimated_duration_ms": 5000,
                "required_capabilities": ["build"],
                "parameters": {},
                "metadata": {}
            },
            {
                "task_id": "task-2",
                "task_type": "TEST",
                "name": "Run Tests",
                "description": "Run unit tests",
                "dependencies": ["task-1"],
                "estimated_duration_ms": 3000,
                "required_capabilities": ["test"],
                "parameters": {},
                "metadata": {}
            },
            {
                "task_id": "task-3",
                "task_type": "DEPLOY",
                "name": "Deploy",
                "description": "Deploy to production",
                "dependencies": ["task-2"],
                "estimated_duration_ms": 2000,
                "required_capabilities": ["deploy"],
                "parameters": {},
                "metadata": {}
            }
        ],
        "execution_order": ["task-1", "task-2", "task-3"],
        "original_domain": "technical",
        "original_priority": "high",
        "original_security_level": "public",
        "risk_score": 0.3,
        "risk_band": "low",
        "complexity_score": 0.5,
        "metadata": {},
        "requires_approval": False,
        "approval_status": None,
        "approved_by": None,
        "approved_at": None,
        "is_destructive": False,
        "destructive_tasks": [],
        "risk_matrix": None
    }


# Mock Kafka consumer para testes de integração
@pytest.fixture
def mock_kafka_consumer():
    """Mock Kafka consumer para testes de integração."""
    class MockKafkaConsumer:
        def __init__(self, topic, group_id):
            self.topic = topic
            self.group_id = group_id
            self.messages = []

        async def getone(self):
            """Simula consumo com timeout."""
            import asyncio
            await asyncio.sleep(0.01)
            if self.messages:
                return self.messages.pop(0)
            return None

        def add_message(self, message):
            """Adiciona mensagem para consumo."""
            self.messages.append(message)

    return MockKafkaConsumer


@pytest.fixture
def mock_aiokafka_consumer():
    """Mock específico para aiokafka.AIOKafkaConsumer."""
    class MockAIOKafkaConsumer:
        async def start(self):
            pass

        async def stop(self):
            pass

        async def getone(self):
            import asyncio
            await asyncio.sleep(0.01)
            return None

    return MockAIOKafkaConsumer()
