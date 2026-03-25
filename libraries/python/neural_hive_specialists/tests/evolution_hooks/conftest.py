"""
Pytest fixtures para testes de evolution_hooks.

Este módulo fornece fixtures compartilhadas para todos os testes
do sistema Evolution Hooks.
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import Mock


@pytest.fixture
async def mongo_client():
    """
    MongoDB client async mock para testes.

    Cria um mock que simula o comportamento do motor AsyncIOMotorClient.
    """
    class AsyncMockCursor:
        """Cursor mock que suporta chaining."""
        def __init__(self, collection, query):
            self.collection = collection
            self._query = query
            self._limit = None
            self._aggregate_pipeline = None

        def sort(self, *args):
            return self

        def limit(self, limit_val):
            self._limit = limit_val
            return self

        def aggregate(self, pipeline):
            self._aggregate_pipeline = pipeline
            return self

        async def to_list(self, length=None):
            # Se foi chamado após aggregate(), retornar resultados agregados
            if self._aggregate_pipeline is not None:
                pipeline = self._aggregate_pipeline
                # Suportar agregação $group básica para domain_distribution
                for stage in pipeline:
                    if "$group" in stage:
                        group_spec = stage["$group"]
                        if "_id" in group_spec and group_spec["_id"] == "$fingerprint.domain":
                            # Agrupar por domain
                            domain_counts = {}
                            for pid, pdoc in self.collection.data.items():
                                domain = pdoc.get("fingerprint", {}).get("domain", "unknown")
                                domain_counts[domain] = domain_counts.get(domain, 0) + 1
                            return [{"_id": d, "count": c} for d, c in domain_counts.items()]
                # Fallback para agregações não suportadas
                return []

            # find() normal com filtragem por query
            results = []
            query = self._query

            for pid, pdoc in self.collection.data.items():
                # Filtrar por query se existir
                if query:
                    match = True
                    # Suportar filtro por fingerprint.domain
                    if "fingerprint.domain" in query:
                        if pdoc.get("fingerprint", {}).get("domain") != query["fingerprint.domain"]:
                            match = False
                    # Suportar filtro por fingerprint.complexity_signature com regex
                    if "fingerprint.complexity_signature" in query and match:
                        sig_query = query["fingerprint.complexity_signature"]
                        if isinstance(sig_query, dict) and "$regex" in sig_query:
                            pattern = sig_query["$regex"]
                            doc_sig = pdoc.get("fingerprint", {}).get("complexity_signature", "")
                            if not doc_sig.startswith(pattern.replace("^", "")):
                                match = False

                    if match:
                        results.append({**pdoc, "_id": pid})
                else:
                    results.append({**pdoc, "_id": pid})

            limit = self._limit if self._limit is not None else (length if length else len(results))
            return results[:limit]

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
            return AsyncMockCursor(self, args[0] if args else None)

        def aggregate(self, pipeline):
            # Retorna cursor mock para agregação
            cursor = AsyncMockCursor(self, None)
            cursor._aggregate_pipeline = pipeline
            return cursor

        async def update_one(self, query, update_doc):
            result = Mock()
            result.modified_count = 0

            def apply_nested_update(doc, update_dict):
                """Aplica atualização com suporte a notação de ponto."""
                for key, value in update_dict.items():
                    parts = key.split(".")
                    curr = doc
                    for part in parts[:-1]:
                        if part not in curr:
                            curr[part] = {}
                        curr = curr[part]
                    curr[parts[-1]] = value

            if "_id" in query:
                # Query por _id
                for pid, pdoc in self.data.items():
                    if pid == query["_id"]:
                        # Aplicar $set (com suporte a notação de ponto)
                        if "$set" in update_doc:
                            apply_nested_update(pdoc, update_doc["$set"])
                        # Aplicar $inc (separado do $set)
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
            elif "plan_id" in query:
                for pid, pdoc in self.data.items():
                    if pdoc.get("plan_id") == query["plan_id"]:
                        # Aplicar $set (com suporte a notação de ponto)
                        if "$set" in update_doc:
                            apply_nested_update(pdoc, update_doc["$set"])
                        # Aplicar $inc (separado do $set)
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
            if query is None:
                return len(self.data)
            # Filtragem básica por domínio se presente na query
            if "fingerprint.domain" in query:
                count = 0
                for pid, pdoc in self.data.items():
                    if pdoc.get("fingerprint", {}).get("domain") == query["fingerprint.domain"]:
                        count += 1
                return count
            # Filtragem por feedback.outcome
            if "feedback.outcome" in query:
                count = 0
                for pid, pdoc in self.data.items():
                    feedback = pdoc.get("feedback", {})
                    if feedback.get("outcome") == query["feedback.outcome"]:
                        count += 1
                return count
            # Filtragem por feedback existe (suporta tanto {"$exists": True} quanto só {"$exists": true})
            if "feedback" in query:
                count = 0
                for pid, pdoc in self.data.items():
                    feedback_exists = "feedback" in pdoc and pdoc["feedback"] is not None
                    if feedback_exists:
                        count += 1
                return count
            # Para outras queries, retorna total (simplificado)
            return len(self.data)

        async def delete_many(self, query):
            """Remove documentos do mock."""
            result = Mock()
            result.deleted_count = 0

            if query is None or query == {}:
                # Limpar todos
                count = len(self.data)
                self.data.clear()
                result.deleted_count = count
            else:
                # Filtrar e remover (simplificado)
                to_delete = []
                for pid, pdoc in self.data.items():
                    match = True
                    for key, val in query.items():
                        if key in pdoc and pdoc[key] != val:
                            match = False
                            break
                    if match:
                        to_delete.append(pid)

                for pid in to_delete:
                    del self.data[pid]
                result.deleted_count = len(to_delete)

            return result

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
        timestamp=datetime.now(timezone.utc)
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
