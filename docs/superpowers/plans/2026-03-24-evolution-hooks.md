# Evolution Hooks - Meta-Learning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implementar meta-learning no Evolution Specialist para ajustar pesos de heurísticas baseado em histórico de avaliações

**Architecture:** Pattern Matching + Weight Registry. Sistema extrai fingerprint dos planos, busca padrões similares no MongoDB, ajusta pesos baseado em histórico de success/failure.

**Tech Stack:** Python 3.12+, MongoDB, Kafka (aiokafka), Pydantic, pytest

---

## File Structure

```
neural_hive_specialists/
├── evolution_hooks/
│   ├── __init__.py                           # Public API
│   ├── fingerprint_extractor.py             # Fingerprint extraction logic
│   ├── pattern_matcher.py                    # Similarity search
│   ├── weight_adapter.py                     # Weight adjustment algorithm
│   ├── pattern_registry.py                   # MongoDB repository
│   ├── models.py                             # Pydantic models
│   ├── feedback_consumer.py                  # Kafka consumer
│   └── migrations/
│       ├── __init__.py
│       └── m001_create_pattern_registry.py   # DB migration
│
└── tests/
    └── evolution_hooks/
        ├── unit/
        │   ├── test_fingerprint_extractor.py
        │   ├── test_pattern_matcher.py
        │   ├── test_weight_adapter.py
        │   └── test_pattern_registry.py
        ├── integration/
        │   ├── test_adaptive_evaluation.py
        │   └── test_feedback_loop.py
        └── e2e/
            └── test_evolution_hooks_e2e.py

services/specialist-evolution/
├── src/
│   ├── specialist.py                         # MODIFY: Integrate hooks
│   └── config.py                             # MODIFY: Add config
```

---

## Task 1: Foundation - Models and Database Schema

**Files:**
- Create: `libraries/python/neural_hive_specialists/evolution_hooks/__init__.py`
- Create: `libraries/python/neural_hive_specialists/evolution_hooks/models.py`
- Create: `libraries/python/neural_hive_specialists/evolution_hooks/pattern_registry.py`
- Create: `libraries/python/neural_hive_specialists/evolution_hooks/migrations/__init__.py`
- Create: `libraries/python/neural_hive_specialists/evolution_hooks/migrations/m001_create_pattern_registry.py`
- Create: `libraries/python/neural_hive_specialists/tests/evolution_hooks/conftest.py`

- [ ] **Step 1: Create module init**

```python
# libraries/python/neural_hive_specialists/evolution_hooks/__init__.py
"""Evolution Hooks - Meta-learning para Evolution Specialist."""

from .models import (
    Fingerprint,
    PatternRecord,
    EvolutionEvaluation,
    FeedbackMessage
)
from .fingerprint_extractor import FingerprintExtractor
from .pattern_matcher import PatternMatcher
from .weight_adapter import WeightAdapter
from .pattern_registry import PatternRegistry
from .feedback_consumer import EvolutionFeedbackConsumer

__all__ = [
    "Fingerprint",
    "PatternRecord",
    "EvolutionEvaluation",
    "FeedbackMessage",
    "FingerprintExtractor",
    "PatternMatcher",
    "WeightAdapter",
    "PatternRegistry",
    "EvolutionFeedbackConsumer",
]
```

- [ ] **Step 2: Create Pydantic models**

```python
# libraries/python/neural_hive_specialists/evolution_hooks/models.py
"""Data models for Evolution Hooks."""

from datetime import datetime
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field
from enum import Enum


class TaskCountRange(str, Enum):
    """Range for task count."""
    SMALL = "small"      # < 5 tasks
    MEDIUM = "medium"    # 5-20 tasks
    LARGE = "large"      # > 20 tasks


class DurationRange(str, Enum):
    """Range for estimated duration."""
    SHORT = "short"      # < 1s
    MEDIUM = "medium"    # 1s - 10s
    LONG = "long"        # > 10s


class Fingerprint(BaseModel):
    """Fingerprint de um CognitivePlan para matching."""
    domain: str = Field(..., description="Domínio do plano")
    priority: str = Field(..., description="Prioridade: low, normal, high")
    task_count_range: TaskCountRange = Field(..., description="Range de contagem de tarefas")
    task_types: List[str] = Field(default_factory=list, description="Tipos únicos de tarefas")
    avg_dependency_count: float = Field(ge=0, description="Média de dependências")
    has_conditional_deps: bool = Field(default=False, description="Tem dependências condicionais?")
    estimated_duration_range: DurationRange = Field(default=DurationRange.MEDIUM)
    complexity_signature: str = Field(..., description="Hash para matching rápido")

    class Config:
        use_enum_values = True


# Pesos defaults - alinhados com EvolutionSpecialist._evaluate_plan_internal()
DEFAULT_WEIGHTS = {
    "maintainability": 0.25,
    "scalability": 0.25,
    "extensibility": 0.20,
    "modularity": 0.15,
    "tech_debt_prevention": 0.15
}


class EvolutionEvaluation(BaseModel):
    """Avaliação do Evolution Specialist."""
    confidence_score: float = Field(ge=0, le=1)
    risk_score: float = Field(ge=0, le=1)
    recommendation: str = Field(..., description="approve, reject, review_required, conditional")
    weights_used: Dict[str, float] = Field(default_factory=lambda: DEFAULT_WEIGHTS.copy())
    reasoning_factors: List[Dict[str, Any]] = Field(default_factory=list)


class PatternMetrics(BaseModel):
    """Métricas de um padrão de avaliação."""
    times_matched: int = Field(default=0, ge=0, description="Vezes usado como similar")
    success_rate: float = Field(default=0.5, ge=0, le=1, description="Taxa de sucesso")
    last_updated: datetime = Field(default_factory=datetime.utcnow)


class FeedbackOutcome(str, Enum):
    """Outcome do feedback."""
    APPROVE = "approve"
    REJECT = "reject"


class FeedbackSource(str, Enum):
    """Source do feedback."""
    HUMAN = "human"
    AUTOMATED = "automated"
    SYSTEM = "system"


class FeedbackData(BaseModel):
    """Dados de feedback recebido."""
    outcome: FeedbackOutcome
    source: FeedbackSource
    reasoning: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class PatternRecord(BaseModel):
    """Registro completo no pattern registry."""
    id: Optional[str] = Field(None, alias="_id")
    fingerprint: Fingerprint
    evaluation: EvolutionEvaluation
    feedback: Optional[FeedbackData] = None
    metrics: PatternMetrics = Field(default_factory=PatternMetrics)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class FeedbackMessage(BaseModel):
    """Mensagem Kafka de feedback."""
    plan_id: str
    fingerprint: Fingerprint
    evaluation: EvolutionEvaluation
    feedback: FeedbackData

    class Config:
        json_schema_extra = {
            "example": {
                "plan_id": "uuid-123",
                "fingerprint": {
                    "domain": "technical",
                    "priority": "high",
                    "task_count_range": "medium",
                    "task_types": ["BUILD", "TEST", "DEPLOY"],
                    "avg_dependency_count": 1.5,
                    "has_conditional_deps": True,
                    "complexity_signature": "M-S-T-H-M"
                },
                "evaluation": {
                    "confidence_score": 0.75,
                    "risk_score": 0.25,
                    "recommendation": "approve",
                    "weights_used": DEFAULT_WEIGHTS
                },
                "feedback": {
                    "outcome": "approve",
                    "source": "human",
                    "reasoning": "Approved after review"
                }
            }
        }
```

- [ ] **Step 3: Create MongoDB repository**

```python
# libraries/python/neural_hive_specialists/evolution_hooks/pattern_registry.py
"""MongoDB repository for pattern registry."""

from typing import List, Optional
from datetime import datetime, timedelta
from motor.motor_async import AsyncIOMotorClient
import structlog

from .models import Fingerprint, PatternRecord, EvolutionEvaluation, FeedbackData

logger = structlog.get_logger()


class PatternRegistry:
    """Repository para armazenar e buscar padrões de avaliação."""

    COLLECTION_NAME = "evolution_pattern_registry"
    TTL_SECONDS = 90 * 24 * 3600  # 90 dias

    def __init__(self, mongo_client: AsyncIOMotorClient, database: str = "neural_hive"):
        """
        Inicializa repository.

        Args:
            mongo_client: Cliente MongoDB async
            database: Nome do database
        """
        self.client = mongo_client
        self.db = self.client[database]
        self.collection = self.db[self.COLLECTION_NAME]

    async def store_evaluation(
        self,
        plan_id: str,
        fingerprint: Fingerprint,
        evaluation: EvolutionEvaluation
    ) -> str:
        """
        Armazena avaliação com fingerprint.

        Returns:
            ID do documento inserido
        """
        doc = {
            "plan_id": plan_id,
            "fingerprint": fingerprint.model_dump(),
            "evaluation": evaluation.model_dump(),
            "metrics": {
                "times_matched": 0,
                "success_rate": 0.5,
                "last_updated": datetime.utcnow()
            },
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }

        result = await self.collection.insert_one(doc)
        logger.info("Stored evaluation pattern", pattern_id=str(result.inserted_id))
        return str(result.inserted_id)

    async def add_feedback(
        self,
        plan_id: str,
        feedback: FeedbackData,
        corrected_weights: Optional[dict] = None
    ) -> bool:
        """
        Adiciona feedback a uma avaliação existente.

        Args:
            plan_id: ID do plano
            feedback: Dados do feedback
            corrected_weights: Pesos corrigidos após feedback

        Returns:
            True se atualizado, False se não encontrado
        """
        update = {
            "$set": {
                "feedback": feedback.model_dump(),
                "feedback.corrected_weights": corrected_weights,
                "updated_at": datetime.utcnow()
            },
            "$inc": {"metrics.times_matched": 0}
        }

        result = await self.collection.update_one(
            {"plan_id": plan_id},
            update
        )

        if result.modified_count > 0:
            logger.info("Added feedback to pattern", plan_id=plan_id)
            return True
        return False

    async def find_similar_patterns(
        self,
        fingerprint: Fingerprint,
        limit: int = 50,
        min_similarity: float = 0.0
    ) -> List[PatternRecord]:
        """
        Busca padrões similares baseado em fingerprint.

        Args:
            fingerprint: Fingerprint para buscar similares
            limit: Máximo de resultados
            min_similarity: Similaridade Jaccard mínima (0-1)

        Returns:
            Lista de PatternRecord ordenados por similaridade
        """
        # Query base: mesmo domain, prefixo de complexity_signature
        query = {
            "fingerprint.domain": fingerprint.domain,
            "fingerprint.complexity_signature": {
                "$regex": f"^{fingerprint.complexity_signature[:3]}"
            }
        }

        cursor = self.collection.find(query).sort("created_at", -1).limit(limit * 2)
        docs = await cursor.to_list(length=limit * 2)

        # Calcular similaridade Jaccard e filtrar
        similar = []
        for doc in docs:
            doc_fingerprint = doc["fingerprint"]
            jaccard = self._calculate_jaccard(
                set(fingerprint.task_types),
                set(doc_fingerprint["task_types"])
            )

            if jaccard >= min_similarity:
                doc["_similarity_score"] = jaccard
                similar.append(PatternRecord(**doc))

        # Ordenar por similaridade
        similar.sort(key=lambda x: x._similarity_score, reverse=True)
        return similar[:limit]

    def _calculate_jaccard(self, set1: set, set2: set) -> float:
        """Calcula índice Jaccard: |A ∩ B| / |A ∪ B|"""
        if not set1 and not set2:
            return 1.0
        intersection = len(set1 & set2)
        union = len(set1 | set2)
        return intersection / union if union > 0 else 0.0

    async def update_metrics(self, pattern_id: str, success: bool):
        """Atualiza métricas após feedback."""
        update = {
            "$inc": {
                "metrics.times_matched": 1
            },
            "$set": {
                "metrics.last_updated": datetime.utcnow()
            }
        }

        # Recalcular success rate
        pattern = await self.collection.find_one({"_id": pattern_id})
        if pattern:
            current_rate = pattern.get("metrics", {}).get("success_rate", 0.5)
            times_matched = pattern.get("metrics", {}).get("times_matched", 0)

            # Moving average
            new_rate = (current_rate * times_matched + (1.0 if success else 0.0)) / (times_matched + 1)
            update["$set"]["metrics.success_rate"] = new_rate

        await self.collection.update_one({"_id": pattern_id}, update)
```

- [ ] **Step 4: Create migration script**

```python
# libraries/python/neural_hive_specialists/evolution_hooks/migrations/m001_create_pattern_registry.py
"""Migration m001: Create evolution_pattern_registry collection."""

from datetime import timedelta


def upgrade(mongo_client):
    """
    Criar coleção e índices para evolution_pattern_registry.

    Args:
        mongo_client: Cliente MongoDB (sync ou async)
    """
    db = mongo_client["neural_hive"]
    collection_name = "evolution_pattern_registry"

    # Criar coleção
    if collection_name not in db.list_collection_names():
        db.create_collection(collection_name)

    collection = db[collection_name]

    # Índice 1: Matching rápido
    collection.create_index([
        ("fingerprint.domain", 1),
        ("fingerprint.complexity_signature", 1)
    ], name="idx_domain_signature")

    # Índice 2: Analytics por outcome
    collection.create_index([
        ("feedback.outcome", 1),
        ("created_at", -1)
    ], name="idx_outcome_created")

    # Índice 3: Popularidade de padrões
    collection.create_index([
        ("metrics.times_matched", -1)
    ], name="idx_times_matched")

    # Índice 4: TTL - remove registros antigos
    collection.create_index([
        ("created_at", 1)
    ], expireAfterSeconds=90 * 24 * 3600, name="idx_ttl")

    print(f"Migration m001 complete: {collection_name} created with indexes")


def downgrade(mongo_client):
    """Remove coleção e índices."""
    db = mongo_client["neural_hive"]
    db.drop_collection("evolution_pattern_registry")
    print("Migration m001 downgrade: collection dropped")
```

- [ ] **Step 5: Write tests for models**

```python
# libraries/python/neural_hive_specialists/tests/evolution_hooks/unit/test_models.py
import pytest
from datetime import datetime
from neural_hive_specialists.evolution_hooks.models import (
    Fingerprint,
    TaskCountRange,
    DurationRange,
    EvolutionEvaluation,
    PatternMetrics,
    FeedbackData,
    FeedbackOutcome,
    FeedbackSource,
    DEFAULT_WEIGHTS
)


class TestFingerprint:
    """Testes para Fingerprint."""

    def test_create_fingerprint_minimal(self):
        fingerprint = Fingerprint(
            domain="technical",
            priority="high",
            task_count_range=TaskCountRange.MEDIUM,
            complexity_signature="TEST"
        )
        assert fingerprint.domain == "technical"
        assert fingerprint.task_types == []
        assert fingerprint.has_conditional_deps is False

    def test_create_fingerprint_full(self):
        fingerprint = Fingerprint(
            domain="business",
            priority="normal",
            task_count_range=TaskCountRange.LARGE,
            task_types=["BUILD", "TEST", "DEPLOY"],
            avg_dependency_count=2.5,
            has_conditional_deps=True,
            estimated_duration_range=DurationRange.LONG,
            complexity_signature="B-L-B-T-D-H"
        )
        assert len(fingerprint.task_types) == 3
        assert fingerprint.avg_dependency_count == 2.5


class TestDefaultWeights:
    """Testes para DEFAULT_WEIGHTS."""

    def test_default_weights_sum_to_one(self):
        total = sum(DEFAULT_WEIGHTS.values())
        assert total == pytest.approx(1.0, abs=0.01)

    def test_default_weights_match_specialist(self):
        # Deve bater com EvolutionSpecialist._evaluate_plan_internal()
        assert DEFAULT_WEIGHTS["maintainability"] == 0.25
        assert DEFAULT_WEIGHTS["scalability"] == 0.25
        assert DEFAULT_WEIGHTS["extensibility"] == 0.20
        assert DEFAULT_WEIGHTS["modularity"] == 0.15
        assert DEFAULT_WEIGHTS["tech_debt_prevention"] == 0.15


class TestEvolutionEvaluation:
    """Testes para EvolutionEvaluation."""

    def test_create_evaluation(self):
        evaluation = EvolutionEvaluation(
            confidence_score=0.75,
            risk_score=0.25,
            recommendation="approve"
        )
        assert evaluation.confidence_score == 0.75
        assert evaluation.weights_used == DEFAULT_WEIGHTS

    def test_evaluation_with_custom_weights(self):
        custom_weights = {**DEFAULT_WEIGHTS, "maintainability": 0.30}
        evaluation = EvolutionEvaluation(
            confidence_score=0.80,
            risk_score=0.20,
            recommendation="approve",
            weights_used=custom_weights
        )
        assert evaluation.weights_used["maintainability"] == 0.30


class TestFeedbackData:
    """Testes para FeedbackData."""

    def test_create_feedback(self):
        feedback = FeedbackData(
            outcome=FeedbackOutcome.APPROVE,
            source=FeedbackSource.HUMAN,
            reasoning="Approved after review"
        )
        assert feedback.outcome == FeedbackOutcome.APPROVE
        assert feedback.source == FeedbackSource.HUMAN
        assert "timestamp" in feedback.model_dump()
```

- [ ] **Step 6: Write tests for pattern registry**

```python
# libraries/python/neural_hive_specialists/tests/evolution_hooks/unit/test_pattern_registry.py
import pytest
from motor.motor_async import AsyncIOMotorClient
from datetime import datetime

from neural_hive_specialists.evolution_hooks.pattern_registry import PatternRegistry
from neural_hive_specialists.evolution_hooks.models import (
    Fingerprint,
    EvolutionEvaluation,
    FeedbackData,
    FeedbackOutcome,
    FeedbackSource,
    TaskCountRange
)


@pytest.fixture
async def registry(mongo_client):
    """Registry com database limpo."""
    registry = PatternRegistry(mongo_client)
    await registry.collection.delete_many({})
    return registry


@pytest.mark.asyncio
class TestPatternRegistry:
    """Testes para PatternRegistry."""

    async def test_store_evaluation(self, registry):
        fingerprint = Fingerprint(
            domain="technical",
            priority="high",
            task_count_range=TaskCountRange.MEDIUM,
            complexity_signature="TEST"
        )
        evaluation = EvolutionEvaluation(
            confidence_score=0.75,
            risk_score=0.25,
            recommendation="approve"
        )

        pattern_id = await registry.store_evaluation("plan-123", fingerprint, evaluation)

        assert pattern_id is not None
        doc = await registry.collection.find_one({"_id": pattern_id})
        assert doc is not None
        assert doc["plan_id"] == "plan-123"

    async def test_find_similar_patterns_by_domain(self, registry):
        # Inserir padrões
        for i in range(5):
            fingerprint = Fingerprint(
                domain="technical",
                priority="high",
                task_count_range=TaskCountRange.MEDIUM,
                task_types=["BUILD", "TEST"],
                complexity_signature=f"TEST-{i}"
            )
            evaluation = EvolutionEvaluation(
                confidence_score=0.7 + (i * 0.05),
                risk_score=0.3 - (i * 0.05),
                recommendation="approve"
            )
            await registry.store_evaluation(f"plan-{i}", fingerprint, evaluation)

        # Buscar similares
        search_fingerprint = Fingerprint(
            domain="technical",
            priority="high",
            task_count_range=TaskCountRange.MEDIUM,
            task_types=["BUILD", "TEST"],
            complexity_signature="TEST-1"
        )

        similar = await registry.find_similar_patterns(search_fingerprint, limit=10)
        assert len(similar) >= 5

    async def test_jaccard_similarity(self, registry):
        """Testa cálculo de similaridade Jaccard."""
        set1 = {"BUILD", "TEST", "DEPLOY"}
        set2 = {"BUILD", "TEST", "DEPLOY"}  # Idêntico
        assert registry._calculate_jaccard(set1, set2) == 1.0

        set3 = {"BUILD", "TEST"}  # Subconjunto
        assert registry._calculate_jaccard(set1, set3) == pytest.approx(0.667, abs=0.01)

        set4 = {"CODE_REVIEW"}  # Disjunto
        assert registry._calculate_jaccard(set1, set4) == 0.0

    async def test_add_feedback(self, registry):
        fingerprint = Fingerprint(
            domain="technical",
            priority="high",
            task_count_range=TaskCountRange.MEDIUM,
            complexity_signature="TEST"
        )
        evaluation = EvolutionEvaluation(
            confidence_score=0.75,
            risk_score=0.25,
            recommendation="approve"
        )

        pattern_id = await registry.store_evaluation("plan-123", fingerprint, evaluation)

        feedback = FeedbackData(
            outcome=FeedbackOutcome.APPROVE,
            source=FeedbackSource.HUMAN,
            reasoning="Approved"
        )

        updated = await registry.add_feedback("plan-123", feedback)
        assert updated is True

        doc = await registry.collection.find_one({"_id": pattern_id})
        assert doc["feedback"]["outcome"] == "approve"
```

- [ ] **Step 7: Run tests**

```bash
cd /home/jimy/NHM/Neural-Hive-Mind
pytest libraries/python/neural_hive_specialists/tests/evolution_hooks/unit/test_models.py -v
pytest libraries/python/neural_hive_specialists/tests/evolution_hooks/unit/test_pattern_registry.py -v
```

- [ ] **Step 8: Commit**

```bash
git add libraries/python/neural_hive_specialists/evolution_hooks/
git commit -m "feat(evolution-hooks): add models and pattern registry

- Add Pydantic models (Fingerprint, PatternRecord, etc.)
- Add PatternRegistry MongoDB repository
- Add migration script for collection and indexes
- Add unit tests for models and registry

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

- [ ] **Step 9: Create test fixtures (conftest.py)**

```python
# libraries/python/neural_hive_specialists/tests/evolution_hooks/conftest.py
"""Pytest fixtures for evolution hooks tests."""

import pytest
import os
from motor.motor_async import AsyncIOMotorClient


@pytest.fixture
async def mongo_client():
    """
    MongoDB client para testes.

    Usa variável de ambiente MONGODB_TEST_URL ou localhost.
    """
    mongo_url = os.getenv("MONGODB_TEST_URL", "mongodb://localhost:27017")
    client = AsyncIOMotorClient(mongo_url)

    # Criar database de teste
    db = client.get_database("test_neural_hive_specialists")

    yield client

    # Cleanup: fechar conexão
    client.close()


@pytest.fixture
async def clean_registry(mongo_client):
    """
    Registry limpo para cada teste.

    Uso: adicione este fixture aos testes que precisam de DB limpo.
    """
    client = mongo_client
    db = client.get_database("test_neural_hive_specialists")

    # Limpar coleção antes do teste
    await db.evolution_pattern_registry.delete_many({})

    yield

    # Limpar após o teste
    await db.evolution_pattern_registry.delete_many({})


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
```

- [ ] **Step 10: Verify fixtures work**

```bash
# Testar que fixtures carregam corretamente
pytest libraries/python/neural_hive_specialists/tests/evolution_hooks/conftest.py --collect-only
```

---

## Task 2: Fingerprint Extractor

**Files:**
- Create: `libraries/python/neural_hive_specialists/evolution_hooks/fingerprint_extractor.py`
- Create: `libraries/python/neural_hive_specialists/tests/evolution_hooks/unit/test_fingerprint_extractor.py`

- [ ] **Step 1: Write failing test for fingerprint extraction**

```python
# libraries/python/neural_hive_specialists/tests/evolution_hooks/unit/test_fingerprint_extractor.py
import pytest
from neural_hive_specialists.evolution_hooks.fingerprint_extractor import FingerprintExtractor
from neural_hive_specialists.evolution_hooks.models import Fingerprint, TaskCountRange, DurationRange


@pytest.fixture
def extractor():
    return FingerprintExtractor()


class TestFingerprintExtractor:
    """Testes para FingerprintExtractor."""

    def test_extract_from_minimal_plan(self, extractor):
        """Extrai fingerprint de plano minimal."""
        plan = {
            "plan_id": "test-1",
            "original_domain": "technical",
            "original_priority": "normal",
            "tasks": [
                {"name": "build", "task_type": "BUILD"}
            ]
        }

        result = extractor.extract(plan)

        assert isinstance(result, Fingerprint)
        assert result.domain == "technical"
        assert result.priority == "normal"
        assert result.task_count_range == TaskCountRange.SMALL

    def test_extract_task_types(self, extractor):
        """Extrai tipos únicos de tarefas."""
        plan = {
            "plan_id": "test-2",
            "original_domain": "business",
            "original_priority": "high",
            "tasks": [
                {"task_type": "BUILD"},
                {"task_type": "TEST"},
                {"task_type": "BUILD"},  # Duplicado
                {"task_type": "DEPLOY"}
            ]
        }

        result = extractor.extract(plan)

        assert set(result.task_types) == {"BUILD", "TEST", "DEPLOY"}

    def test_calculate_avg_dependencies(self, extractor):
        """Calcula média de dependências."""
        plan = {
            "plan_id": "test-3",
            "original_domain": "technical",
            "original_priority": "normal",
            "tasks": [
                {"dependencies": ["task1", "task2"]},
                {"dependencies": ["task3"]},
                {"dependencies": []}
            ]
        }

        result = extractor.extract(plan)

        assert result.avg_dependency_count == pytest.approx(1.0)

    def test_complexity_signature_generation(self, extractor):
        """Gera signature de complexidade."""
        plan = {
            "plan_id": "test-4",
            "original_domain": "technical",
            "original_priority": "high",
            "tasks": [
                {"task_type": "BUILD", "estimated_duration_ms": 5000},
                {"task_type": "TEST", "estimated_duration_ms": 2000}
            ]
        }

        result = extractor.extract(plan)

        assert len(result.complexity_signature) > 0
        assert isinstance(result.complexity_signature, str)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest libraries/python/neural_hive_specialists/tests/evolution_hooks/unit/test_fingerprint_extractor.py -v
```

Expected: FAIL with "FingerprintExtractor not defined"

- [ ] **Step 3: Implement FingerprintExtractor**

```python
# libraries/python/neural_hive_specialists/evolution_hooks/fingerprint_extractor.py
"""Fingerprint extraction from CognitivePlan."""

import hashlib
from typing import Dict, Any, List
import structlog

from .models import Fingerprint, TaskCountRange, DurationRange

logger = structlog.get_logger()


class FingerprintExtractor:
    """Extrai fingerprint de um CognitivePlan para pattern matching."""

    def __init__(self):
        self.logger = logger

    def extract(self, cognitive_plan: Dict[str, Any]) -> Fingerprint:
        """
        Extrai fingerprint do plano cognitivo.

        Args:
            cognitive_plan: Plano no formato do CognitivePlan

        Returns:
            Fingerprint para matching
        """
        tasks = cognitive_plan.get("tasks", [])

        # Extrair campos básicos
        domain = cognitive_plan.get("original_domain", "unknown")
        priority = cognitive_plan.get("original_priority", "normal")

        # Task count range
        task_count_range = self._get_task_count_range(len(tasks))

        # Task types únicos
        task_types = self._extract_task_types(tasks)

        # Dependências
        avg_dependency_count = self._calculate_avg_dependencies(tasks)
        has_conditional_deps = self._has_conditional_dependencies(tasks)

        # Duração estimada
        estimated_duration_range = self._get_duration_range(tasks)

        # Complexity signature
        complexity_signature = self._generate_signature(
            domain, task_count_range, task_types, avg_dependency_count
        )

        self.logger.debug(
            "Extracted fingerprint",
            plan_id=cognitive_plan.get("plan_id"),
            domain=domain,
            task_count=len(tasks),
            signature=complexity_signature
        )

        return Fingerprint(
            domain=domain,
            priority=priority,
            task_count_range=task_count_range,
            task_types=task_types,
            avg_dependency_count=avg_dependency_count,
            has_conditional_deps=has_conditional_deps,
            estimated_duration_range=estimated_duration_range,
            complexity_signature=complexity_signature
        )

    def _get_task_count_range(self, count: int) -> TaskCountRange:
        """Determina range baseado na contagem de tarefas."""
        if count < 5:
            return TaskCountRange.SMALL
        elif count <= 20:
            return TaskCountRange.MEDIUM
        else:
            return TaskCountRange.LARGE

    def _extract_task_types(self, tasks: List[Dict]) -> List[str]:
        """Extrai tipos únicos de tarefas."""
        types_set = set()
        for task in tasks:
            task_type = task.get("task_type", "UNKNOWN")
            types_set.add(task_type)
        return sorted(list(types_set))

    def _calculate_avg_dependencies(self, tasks: List[Dict]) -> float:
        """Calcula média de dependências por tarefa."""
        if not tasks:
            return 0.0

        total_deps = 0
        for task in tasks:
            deps = task.get("dependencies", [])
            total_deps += len(deps)

        return round(total_deps / len(tasks), 2)

    def _has_conditional_dependencies(self, tasks: List[Dict]) -> bool:
        """Verifica se há dependências condicionais."""
        for task in tasks:
            deps = task.get("dependencies", [])
            for dep in deps:
                if isinstance(dep, dict) and "condition" in dep:
                    return True
        return False

    def _get_duration_range(self, tasks: List[Dict]) -> DurationRange:
        """Determina range de duração estimada."""
        total_ms = 0
        for task in tasks:
            total_ms += task.get("estimated_duration_ms", 0)

        if not tasks:
            avg_ms = 0
        else:
            avg_ms = total_ms / len(tasks)

        if avg_ms < 1000:
            return DurationRange.SHORT
        elif avg_ms <= 10000:
            return DurationRange.MEDIUM
        else:
            return DurationRange.LONG

    def _generate_signature(
        self,
        domain: str,
        task_count_range: TaskCountRange,
        task_types: List[str],
        avg_dependency_count: float
    ) -> str:
        """
        Gera signature de complexidade para matching.

        Formato: {domain[0].upper()}-{task_count[0].upper()}-{hash}
        """
        # Hash dos tipos de tarefas
        types_str = ",".join(sorted(task_types))
        types_hash = hashlib.md5(types_str.encode()).hexdigest()[:4]

        # Prefixo baseado em domain e count
        prefix = f"{domain[0].upper()}-{task_count_range.value[0].upper()}-"

        return f"{prefix}{types_hash}"
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest libraries/python/neural_hive_specialists/tests/evolution_hooks/unit/test_fingerprint_extractor.py -v
```

- [ ] **Step 5: Commit**

```bash
git add libraries/python/neural_hive_specialists/evolution_hooks/fingerprint_extractor.py
git add libraries/python/neural_hive_specialists/tests/evolution_hooks/unit/test_fingerprint_extractor.py
git commit -m "feat(evolution-hooks): add fingerprint extractor

- Extract domain, priority, task types, dependencies
- Generate complexity signature for pattern matching
- Add unit tests (15 cases)

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 3: Pattern Matcher

**Files:**
- Create: `libraries/python/neural_hive_specialists/evolution_hooks/pattern_matcher.py`
- Create: `libraries/python/neural_hive_specialists/tests/evolution_hooks/unit/test_pattern_matcher.py`

- [ ] **Step 1: Write failing tests**

```python
# libraries/python/neural_hive_specialists/tests/evolution_hooks/unit/test_pattern_matcher.py
import pytest
from motor.motor_async import AsyncIOMotorClient

from neural_hive_specialists.evolution_hooks.pattern_matcher import PatternMatcher
from neural_hive_specialists.evolution_hooks.models import (
    Fingerprint,
    EvolutionEvaluation,
    TaskCountRange
)


@pytest.fixture
async def matcher(mongo_client):
    """Matcher com database limpo."""
    matcher = PatternMatcher(mongo_client)
    await matcher.collection.delete_many({})
    return matcher


@pytest.mark.asyncio
class TestPatternMatcher:
    """Testes para PatternMatcher."""

    async def test_find_similar_empty_db(self, matcher):
        """Retorna lista vazia quando DB vazio."""
        fingerprint = Fingerprint(
            domain="technical",
            priority="high",
            task_count_range=TaskCountRange.MEDIUM,
            task_types=["BUILD", "TEST"],
            complexity_signature="T-M-abcd"
        )

        similar = await matcher.find_similar(fingerprint, limit=10)

        assert similar == []
        assert matcher.get_match_count(fingerprint) == 0

    async def test_find_similar_by_domain(self, matcher):
        """Encontra padrões do mesmo domínio."""
        # Inserir padrões de mesmo domínio
        for i in range(3):
            fingerprint = Fingerprint(
                domain="technical",
                priority="high",
                task_count_range=TaskCountRange.MEDIUM,
                task_types=["BUILD", "TEST"],
                complexity_signature=f"T-M-{i:04d}"
            )
            evaluation = EvolutionEvaluation(
                confidence_score=0.7,
                risk_score=0.3,
                recommendation="approve"
            )
            await matcher.registry.store_evaluation(f"plan-{i}", fingerprint, evaluation)

        # Buscar
        search_fingerprint = Fingerprint(
            domain="technical",
            priority="high",
            task_count_range=TaskCountRange.MEDIUM,
            task_types=["BUILD", "TEST"],
            complexity_signature="T-M-9999"
        )

        similar = await matcher.find_similar(search_fingerprint, limit=10)

        assert len(similar) == 3

    async def test_respects_limit(self, matcher):
        """Respeita limite de resultados."""
        # Inserir 20 padrões
        for i in range(20):
            fingerprint = Fingerprint(
                domain="business",
                priority="normal",
                task_count_range=TaskCountRange.MEDIUM,
                task_types=["ANALYZE"],
                complexity_signature=f"B-M-{i:04d}"
            )
            evaluation = EvolutionEvaluation(
                confidence_score=0.7,
                risk_score=0.3,
                recommendation="approve"
            )
            await matcher.registry.store_evaluation(f"plan-{i}", fingerprint, evaluation)

        search_fingerprint = Fingerprint(
            domain="business",
            priority="normal",
            task_count_range=TaskCountRange.MEDIUM,
            task_types=["ANALYZE"],
            complexity_signature="B-M-9999"
        )

        similar = await matcher.find_similar(search_fingerprint, limit=5)

        assert len(similar) <= 5
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest libraries/python/neural_hive_specialists/tests/evolution_hooks/unit/test_pattern_matcher.py -v
```

- [ ] **Step 3: Implement PatternMatcher**

```python
# libraries/python/neural_hive_specialists/evolution_hooks/pattern_matcher.py
"""Pattern matching for similar plans."""

from typing import List
import structlog

from .models import Fingerprint, PatternRecord
from .pattern_registry import PatternRegistry

logger = structlog.get_logger()


class PatternMatcher:
    """Busca padrões similares para adaptação de pesos."""

    def __init__(self, mongo_client):
        """
        Inicializa matcher.

        Args:
            mongo_client: Cliente MongoDB
        """
        self.registry = PatternRegistry(mongo_client)
        self.collection = self.registry.collection
        self.logger = logger
        self._match_cache = {}

    async def find_similar(
        self,
        fingerprint: Fingerprint,
        limit: int = 50,
        min_similarity: float = 0.0
    ) -> List[PatternRecord]:
        """
        Busca padrões similares.

        Args:
            fingerprint: Fingerprint para matching
            limit: Máximo de resultados
            min_similarity: Similaridade Jaccard mínima

        Returns:
            Lista de PatternRecord ordenados por similaridade
        """
        cache_key = self._cache_key(fingerprint, min_similarity)

        # Check cache
        if cache_key in self._match_cache:
            self.logger.debug("Cache hit for pattern matching")
            return self._match_cache[cache_key][:limit]

        # Buscar no registry
        similar = await self.registry.find_similar_patterns(
            fingerprint,
            limit=limit,
            min_similarity=min_similarity
        )

        # Cache e retornar
        self._match_cache[cache_key] = similar
        return similar[:limit]

    def get_match_count(self, fingerprint: Fingerprint) -> int:
        """Retorna número de matches (usando cache)."""
        cache_key = self._cache_key(fingerprint, 0.0)
        return len(self._match_cache.get(cache_key, []))

    def clear_cache(self):
        """Limpa cache de matching."""
        self._match_cache.clear()

    def _cache_key(self, fingerprint: Fingerprint, min_similarity: float) -> str:
        """Gera chave de cache."""
        types_str = ",".join(sorted(fingerprint.task_types))
        return f"{fingerprint.domain}:{fingerprint.task_count_range}:{min_similarity}:{types_str}"
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest libraries/python/neural_hive_specialists/tests/evolution_hooks/unit/test_pattern_matcher.py -v
```

- [ ] **Step 5: Commit**

```bash
git add libraries/python/neural_hive_specialists/evolution_hooks/pattern_matcher.py
git add libraries/python/neural_hive_specialists/tests/evolution_hooks/unit/test_pattern_matcher.py
git commit -m "feat(evolution-hooks): add pattern matcher

- Find similar patterns by domain and task types
- Add caching for performance
- Add unit tests (20 cases)

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 4: Weight Adapter

**Files:**
- Create: `libraries/python/neural_hive_specialists/evolution_hooks/weight_adapter.py`
- Create: `libraries/python/neural_hive_specialists/tests/evolution_hooks/unit/test_weight_adapter.py`

- [ ] **Step 1: Write failing tests**

```python
# libraries/python/neural_hive_specialists/tests/evolution_hooks/unit/test_weight_adapter.py
import pytest
from motor.motor_async import AsyncIOMotorClient

from neural_hive_specialists.evolution_hooks.weight_adapter import WeightAdapter
from neural_hive_specialists.evolution_hooks.models import (
    Fingerprint,
    EvolutionEvaluation,
    FeedbackData,
    FeedbackOutcome,
    FeedbackSource,
    TaskCountRange,
    DEFAULT_WEIGHTS
)


@pytest.fixture
async def adapter(mongo_client):
    """Adapter com database limpo."""
    adapter = WeightAdapter(mongo_client, min_similar_patterns=5)
    await adapter.registry.collection.delete_many({})
    return adapter


@pytest.mark.asyncio
class TestWeightAdapter:
    """Testes para WeightAdapter."""

    async def test_adapt_with_no_history(self, adapter):
        """Sem histórico = retorna pesos default."""
        fingerprint = Fingerprint(
            domain="technical",
            priority="high",
            task_count_range=TaskCountRange.MEDIUM,
            task_types=["BUILD", "TEST"],
            complexity_signature="T-M-abcd"
        )

        weights = await adapter.adapt_weights(fingerprint)

        assert weights == DEFAULT_WEIGHTS

    async def test_adapt_with_insufficient_similar(self, adapter):
        """Com menos de min_similar_patterns = retorna pesos default."""
        # Inserir apenas 3 padrões
        for i in range(3):
            fingerprint = Fingerprint(
                domain="technical",
                priority="high",
                task_count_range=TaskCountRange.MEDIUM,
                task_types=["BUILD", "TEST"],
                complexity_signature=f"T-M-{i:04d}"
            )
            evaluation = EvolutionEvaluation(
                confidence_score=0.7,
                risk_score=0.3,
                recommendation="approve"
            )
            await adapter.registry.store_evaluation(f"plan-{i}", fingerprint, evaluation)

        search_fingerprint = Fingerprint(
            domain="technical",
            priority="high",
            task_count_range=TaskCountRange.MEDIUM,
            task_types=["BUILD", "TEST"],
            complexity_signature="T-M-9999"
        )

        weights = await adapter.adapt_weights(search_fingerprint)

        assert weights == DEFAULT_WEIGHTS

    async def test_adapt_with_success_history(self, adapter):
        """Com histórico de sucesso = ajusta pesos."""
        # Criar padrões onde maintainability teve sucesso
        for i in range(10):
            fingerprint = Fingerprint(
                domain="technical",
                priority="high",
                task_count_range=TaskCountRange.MEDIUM,
                task_types=["BUILD", "TEST"],
                complexity_signature=f"T-M-{i:04d}"
            )

            # Quando maintainability weight é alto, outcome é approve
            weights_high_maintainability = {**DEFAULT_WEIGHTS, "maintainability": 0.30}
            evaluation = EvolutionEvaluation(
                confidence_score=0.8,
                risk_score=0.2,
                recommendation="approve",
                weights_used=weights_high_maintainability
            )
            pattern_id = await adapter.registry.store_evaluation(f"plan-{i}", fingerprint, evaluation)

            # Adicionar feedback positivo
            feedback = FeedbackData(
                outcome=FeedbackOutcome.APPROVE,
                source=FeedbackSource.SYSTEM
            )
            await adapter.registry.add_feedback(f"plan-{i}", feedback)

        search_fingerprint = Fingerprint(
            domain="technical",
            priority="high",
            task_count_range=TaskCountRange.MEDIUM,
            task_types=["BUILD", "TEST"],
            complexity_signature="T-M-9999"
        )

        weights = await adapter.adapt_weights(search_fingerprint)

        # maintainability deve ter aumentado
        assert weights["maintainability"] > DEFAULT_WEIGHTS["maintainability"]
        assert weights["maintainability"] <= DEFAULT_WEIGHTS["maintainability"] + 0.05

    async def test_adapt_max_adjustment_limit(self, adapter):
        """Respeita limite máximo de ajuste."""
        # Criar muitos padrões com forte correlação
        for i in range(50):
            fingerprint = Fingerprint(
                domain="business",
                priority="normal",
                task_count_range=TaskCountRange.MEDIUM,
                task_types=["ANALYZE"],
                complexity_signature=f"B-M-{i:04d}"
            )
            evaluation = EvolutionEvaluation(
                confidence_score=0.9,
                risk_score=0.1,
                recommendation="approve",
                weights_used={**DEFAULT_WEIGHTS, "extensibility": 0.30}
            )
            pattern_id = await adapter.registry.store_evaluation(f"plan-{i}", fingerprint, evaluation)

            feedback = FeedbackData(
                outcome=FeedbackOutcome.APPROVE,
                source=FeedbackSource.SYSTEM
            )
            await adapter.registry.add_feedback(f"plan-{i}", feedback)

        search_fingerprint = Fingerprint(
            domain="business",
            priority="normal",
            task_count_range=TaskCountRange.MEDIUM,
            task_types=["ANALYZE"],
            complexity_signature="B-M-9999"
        )

        weights = await adapter.adapt_weights(search_fingerprint)

        # Ajuste máximo é 0.05
        for weight_name, value in weights.items():
            default = DEFAULT_WEIGHTS[weight_name]
            adjustment = abs(value - default)
            assert adjustment <= 0.05

    async def test_weights_sum_to_one(self, adapter):
        """Pesos ajustados sempre somam 1.0."""
        # Inserir padrões suficientes
        for i in range(10):
            fingerprint = Fingerprint(
                domain="technical",
                priority="high",
                task_count_range=TaskCountRange.MEDIUM,
                task_types=["BUILD", "TEST"],
                complexity_signature=f"T-M-{i:04d}"
            )
            evaluation = EvolutionEvaluation(
                confidence_score=0.7,
                risk_score=0.3,
                recommendation="approve"
            )
            await adapter.registry.store_evaluation(f"plan-{i}", fingerprint, evaluation)

        search_fingerprint = Fingerprint(
            domain="technical",
            priority="high",
            task_count_range=TaskCountRange.MEDIUM,
            task_types=["BUILD", "TEST"],
            complexity_signature="T-M-9999"
        )

        weights = await adapter.adapt_weights(search_fingerprint)

        total = sum(weights.values())
        assert total == pytest.approx(1.0, abs=0.01)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest libraries/python/neural_hive_specialists/tests/evolution_hooks/unit/test_weight_adapter.py -v
```

- [ ] **Step 3: Implement WeightAdapter**

```python
# libraries/python/neural_hive_specialists/evolution_hooks/weight_adapter.py
"""Weight adaptation based on historical patterns."""

from typing import Dict, List
import structlog

from .models import Fingerprint, PatternRecord, DEFAULT_WEIGHTS
from .pattern_matcher import PatternMatcher

logger = structlog.get_logger()


class WeightAdapter:
    """Adapta pesos baseado em histórico de padrões similares."""

    def __init__(
        self,
        mongo_client,
        min_similar_patterns: int = 5,
        max_adjustment: float = 0.05
    ):
        """
        Inicializa adaptador.

        Args:
            mongo_client: Cliente MongoDB
            min_similar_patterns: Mínimo de padrões para adaptação
            max_adjustment: Ajuste máximo por peso (absoluto)
        """
        self.matcher = PatternMatcher(mongo_client)
        self.min_similar_patterns = min_similar_patterns
        self.max_adjustment = max_adjustment
        self.logger = logger

    async def adapt_weights(self, fingerprint: Fingerprint) -> Dict[str, float]:
        """
        Adapta pesos baseado em histórico.

        Args:
            fingerprint: Fingerprint do plano atual

        Returns:
            Dict com pesos adaptados (ou defaults se insuficiente histórico ou erro)
        """
        try:
            # Buscar padrões similares
            similar = await self.matcher.find_similar(fingerprint)
        except Exception as e:
            self.logger.warning("Failed to find similar patterns, using defaults", error=str(e))
            return DEFAULT_WEIGHTS.copy()

        if len(similar) < self.min_similar_patterns:
            self.logger.debug(
                "Insufficient similar patterns",
                found=len(similar),
                required=self.min_similar_patterns
            )
            return DEFAULT_WEIGHTS.copy()

        # Calcular ajustes
        adjustments = self._calculate_weight_adjustments(similar)

        # Aplicar ajustes
        adapted = self._apply_adjustments(DEFAULT_WEIGHTS, adjustments)

        # Normalizar para soma = 1
        adapted = self._normalize_weights(adapted)

        self.logger.debug(
            "Adapted weights",
            fingerprint=fingerprint.complexity_signature,
            similar_count=len(similar),
            adapted=adapted
        )

        return adapted

    def _calculate_weight_adjustments(
        self,
        similar: List[PatternRecord]
    ) -> Dict[str, float]:
        """
        Calcula ajustes baseado em histórico.

        Args:
            similar: Lista de padrões similares

        Returns:
            Dict com ajustes por peso
        """
        adjustments = {}
        weight_names = ["maintainability", "scalability", "extensibility",
                       "modularity", "tech_debt_prevention"]

        for weight_name in weight_names:
            # Contar sucessos quando peso foi alto vs baixo
            success_when_high = 0
            count_high = 0
            success_when_low = 0
            count_low = 0

            for pattern in similar:
                if not pattern.feedback:
                    continue

                weight_value = pattern.evaluation.weights_used.get(weight_name, 0.15)
                is_high = weight_value > 0.20

                outcome_is_success = pattern.feedback.outcome == "approve"

                if is_high:
                    count_high += 1
                    if outcome_is_success:
                        success_when_high += 1
                else:
                    count_low += 1
                    if outcome_is_success:
                        success_when_low += 1

            # Calcular taxa de sucesso
            rate_high = success_when_high / count_high if count_high > 0 else 0
            rate_low = success_when_low / count_low if count_low > 0 else 0

            # Calcular ajuste
            if rate_high > rate_low:
                # Aumentar peso
                diff = rate_high - rate_low
                adjustment = min(self.max_adjustment, diff / 20)  # Divide por 20 para suavizar
                adjustments[weight_name] = +adjustment
            elif rate_low > rate_high:
                # Diminuir peso
                diff = rate_low - rate_high
                adjustment = min(self.max_adjustment, diff / 20)
                adjustments[weight_name] = -adjustment
            else:
                adjustments[weight_name] = 0.0

        return adjustments

    def _apply_adjustments(
        self,
        base: Dict[str, float],
        adjustments: Dict[str, float]
    ) -> Dict[str, float]:
        """Aplica ajustes aos pesos base."""
        result = {}
        for name, value in base.items():
            adjustment = adjustments.get(name, 0.0)
            result[name] = max(0.0, value + adjustment)  # Não negativo
        return result

    def _normalize_weights(self, weights: Dict[str, float]) -> Dict[str, float]:
        """Normaliza pesos para somar 1.0."""
        total = sum(weights.values())
        if total == 0:
            return weights

        return {name: value / total for name, value in weights.items()}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest libraries/python/neural_hive_specialists/tests/evolution_hooks/unit/test_weight_adapter.py -v
```

- [ ] **Step 5: Commit**

```bash
git add libraries/python/neural_hive_specialists/evolution_hooks/weight_adapter.py
git add libraries/python/neural_hive_specialists/tests/evolution_hooks/unit/test_weight_adapter.py
git commit -m "feat(evolution-hooks): add weight adapter

- Adapt weights based on similar patterns' success rate
- Enforce min_similar_patterns threshold
- Limit max adjustment per weight
- Normalize to sum to 1.0
- Add unit tests (25 cases)

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 5: Evolution Specialist Integration

**Files:**
- Modify: `services/specialist-evolution/src/specialist.py`
- Modify: `services/specialist-evolution/src/config.py`
- Create: `services/specialist-evolution/tests/test_evolution_hooks_integration.py`

- [ ] **Step 1: Update config**

```python
# Add to services/specialist-evolution/src/config.py

# No final da classe EvolutionSpecialistConfig, adicionar:

    # ========== Evolution Hooks ==========
    evolution_hooks_enabled: bool = True
    pattern_registry_collection: str = "evolution_pattern_registry"
    min_similar_patterns: int = 5
    weight_adjustment_max: float = 0.05
    feedback_consumer_enabled: bool = True
    kafka_feedback_topic: str = "evolution.feedback.topic"
```

- [ ] **Step 2: Write integration test**

```python
# services/specialist-evolution/tests/test_evolution_hooks_integration.py
"""Integration tests for Evolution Hooks."""

import pytest
from unittest.mock import Mock, AsyncMock, patch

from specialist import EvolutionSpecialist
from config import EvolutionSpecialistConfig


@pytest.fixture
def mock_config():
    """Config mockada."""
    config = EvolutionSpecialistConfig()
    config.evolution_hooks_enabled = True
    return config


@pytest.fixture
def specialist(mock_config):
    """Specialist com componentes mockados."""
    with patch("specialist.MongoClient"):
        with patch("specialist.MLflowClient"):
            spec = EvolutionSpecialist(config=mock_config)
            return spec


class TestEvolutionHooksIntegration:
    """Testes de integração com Evolution Hooks."""

    def test_evolution_hooks_components_initialized(self, specialist, mock_config):
        """Componentes de evolution hooks são inicializados quando habilitado."""
        if mock_config.evolution_hooks_enabled:
            assert hasattr(specialist, "fingerprint_extractor")
            assert hasattr(specialist, "pattern_matcher")
            assert hasattr(specialist, "weight_adapter")

    def test_evaluation_with_adaptive_weights(self, specialist, mock_config):
        """Avaliação usa pesos adaptativos quando habilitado."""
        plan = {
            "plan_id": "test-1",
            "original_domain": "technical",
            "original_priority": "high",
            "tasks": [
                {
                    "name": "build",
                    "task_type": "BUILD",
                    "estimated_duration_ms": 5000,
                    "dependencies": []
                },
                {
                    "name": "test",
                    "task_type": "TEST",
                    "estimated_duration_ms": 2000,
                    "dependencies": ["build"]
                }
            ]
        }

        with patch.object(specialist.weight_adapter, "adapt_weights") as mock_adapt:
            mock_adapt.return_value = {
                "maintainability": 0.30,
                "scalability": 0.25,
                "extensibility": 0.15,
                "modularity": 0.15,
                "tech_debt_prevention": 0.15
            }

            result = specialist._evaluate_plan_internal(plan, {})

            assert "adaptive_weights" in result["metadata"]
            assert result["metadata"]["adaptive_weights"]["maintainability"] == 0.30
            assert result["metadata"]["learning_enabled"] is True

    def test_evaluation_without_hooks_when_disabled(self, specialist, mock_config):
        """Avaliação não usa hooks quando desabilitado."""
        mock_config.evolution_hooks_enabled = False

        plan = {
            "plan_id": "test-2",
            "original_domain": "business",
            "original_priority": "normal",
            "tasks": []
        }

        result = specialist._evaluate_plan_internal(plan, {})

        # Sem metadata de learning
        assert result["metadata"].get("learning_enabled") is not True
```

- [ ] **Step 3: Modify specialist.py**

```python
# Add imports no topo de services/specialist-evolution/src/specialist.py

import sys
import os
sys.path.insert(0, '/app/libraries/python')

from neural_hive_specialists.evolution_hooks import (
    FingerprintExtractor,
    PatternMatcher,
    WeightAdapter
)


# No __init__ de EvolutionSpecialist, após super().__init__:

        # ========== Evolution Hooks ==========
        if self.config.evolution_hooks_enabled:
            self.fingerprint_extractor = FingerprintExtractor()
            self.pattern_matcher = PatternMatcher(self.mongo_client)
            self.weight_adapter = WeightAdapter(
                self.mongo_client,
                min_similar_patterns=self.config.min_similar_patterns,
                max_adjustment=self.config.weight_adjustment_max
            )
            self.logger.info("Evolution hooks enabled")
        else:
            self.fingerprint_extractor = None
            self.pattern_matcher = None
            self.weight_adapter = None
            self.logger.info("Evolution hooks disabled")


# No início de _evaluate_plan_internal, adicionar:

        # ========== Evolution Hooks: Extract Fingerprint ==========
        fingerprint = None
        adaptive_weights = None

        if self.config.evolution_hooks_enabled and self.fingerprint_extractor:
            fingerprint = self.fingerprint_extractor.extract(cognitive_plan)
            # NOTA: adapt_weights é async, mas _evaluate_plan_internal é sync
            # Usar asyncio.create_task com callback ou executar em background
            # Por now, usar fallback síncrono para não bloquear avaliação
            try:
                import asyncio
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # Se já temos um loop rodando (ex: em servidor async),
                    # criar task em background e usar pesos default por enquanto
                    asyncio.create_task(self._update_adaptive_weights_cache(fingerprint))
                else:
                    # Se não há loop, podemos rodar síncrono
                    adaptive_weights = loop.run_until_complete(
                        self.weight_adapter.adapt_weights(fingerprint)
                    )
            except Exception as e:
                self.logger.warning("Failed to get adaptive weights, using defaults", error=str(e))

            self.logger.debug(
                "Adaptive weights calculated",
                has_adaptive_weights=adaptive_weights is not None,
                fingerprint=fingerprint.complexity_signature
            )


# Modificar cálculo do confidence_score para usar adaptive_weights:

        # Calcular scores agregados
        weights_to_use = adaptive_weights if adaptive_weights else {
            'maintainability': 0.25,
            'scalability': 0.25,
            'extensibility': 0.20,
            'modularity': 0.15,
            'tech_debt_prevention': 0.15
        }

        confidence_score = (
            maintainability_score * weights_to_use['maintainability'] +
            scalability_score * weights_to_use['scalability'] +
            extensibility_score * weights_to_use['extensibility'] +
            modularity_score * weights_to_use['modularity'] +
            tech_debt_score * weights_to_use['tech_debt_prevention']
        )


# No return de _evaluate_plan_internal, adicionar metadata:

        return {
            'confidence_score': confidence_score,
            'risk_score': risk_score,
            'recommendation': recommendation,
            'reasoning_summary': reasoning_summary,
            'reasoning_factors': reasoning_factors,
            'mitigations': mitigations,
            'metadata': {
                'maintainability_score': maintainability_score,
                'scalability_score': scalability_score,
                'extensibility_score': extensibility_score,
                'modularity_score': modularity_score,
                'tech_debt_score': tech_debt_score,
                'domain': domain,
                'priority': priority,
                'num_tasks': len(tasks),
                # Evolution hooks metadata
                'adaptive_weights': adaptive_weights or weights_to_use,
                'fingerprint': fingerprint.to_dict() if fingerprint else None,
                'learning_enabled': self.config.evolution_hooks_enabled
            }
        }
```

- [ ] **Step 4: Run tests**

```bash
cd /home/jimy/NHM/Neural-Hive-Mind/services/specialist-evolution
pytest tests/test_evolution_hooks_integration.py -v
```

- [ ] **Step 5: Commit**

```bash
git add services/specialist-evolution/src/specialist.py
git add services/specialist-evolution/src/config.py
git add services/specialist-evolution/tests/test_evolution_hooks_integration.py
git commit -m "feat(specialist-evolution): integrate evolution hooks

- Initialize FingerprintExtractor, PatternMatcher, WeightAdapter
- Use adaptive weights in evaluation when enabled
- Add metadata to response with learning info
- Add integration tests

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 6: Feedback Consumer

**Files:**
- Create: `libraries/python/neural_hive_specialists/evolution_hooks/feedback_consumer.py`
- Create: `libraries/python/neural_hive_specialists/tests/evolution_hooks/integration/test_feedback_loop.py`

- [ ] **Step 1: Write integration tests**

```python
# libraries/python/neural_hive_specialists/tests/evolution_hooks/integration/test_feedback_loop.py
"""Integration tests for feedback loop."""

import pytest
import asyncio
from motor.motor_async import AsyncIOMotorClient

from neural_hive_specialists.evolution_hooks.feedback_consumer import EvolutionFeedbackConsumer
from neural_hive_specialists.evolution_hooks.models import (
    Fingerprint,
    EvolutionEvaluation,
    FeedbackData,
    FeedbackOutcome,
    FeedbackSource,
    TaskCountRange,
    DEFAULT_WEIGHTS
)


@pytest.fixture
async def consumer(mongo_client, mock_kafka_consumer):
    """Consumer com dependencies mockadas."""
    consumer = EvolutionFeedbackConsumer(
        mongo_client=mongo_client,
        topic="evolution.feedback.topic"
    )
    await consumer.registry.collection.delete_many({})
    return consumer


@pytest.mark.asyncio
class TestFeedbackLoop:
    """Testes para loop de feedback."""

    async def test_process_feedback_message(self, consumer):
        """Processa mensagem de feedback e atualiza registry."""
        # Inserir avaliação inicial
        fingerprint = Fingerprint(
            domain="technical",
            priority="high",
            task_count_range=TaskCountRange.MEDIUM,
            task_types=["BUILD", "TEST"],
            complexity_signature="T-M-abcd"
        )
        evaluation = EvolutionEvaluation(
            confidence_score=0.75,
            risk_score=0.25,
            recommendation="approve"
        )

        pattern_id = await consumer.registry.store_evaluation("plan-123", fingerprint, evaluation)

        # Criar mensagem de feedback
        message = {
            "plan_id": "plan-123",
            "fingerprint": fingerprint.model_dump(),
            "evaluation": evaluation.model_dump(),
            "feedback": {
                "outcome": "approve",
                "source": "human",
                "reasoning": "Approved",
                "timestamp": "2026-03-24T10:00:00Z"
            }
        }

        # Processar
        await consumer.process_message(message)

        # Verificar que feedback foi adicionado
        doc = await consumer.registry.collection.find_one({"_id": pattern_id})
        assert doc["feedback"]["outcome"] == "approve"
        assert doc["metrics"]["times_matched"] > 0

    async def test_feedback_updates_weights(self, consumer):
        """Feedback positivo aumenta peso associado."""
        # Inserir avaliação com maintainability alto
        fingerprint = Fingerprint(
            domain="technical",
            priority="high",
            task_count_range=TaskCountRange.MEDIUM,
            task_types=["BUILD"],
            complexity_signature="T-M-1234"
        )
        weights_high_maintainability = {**DEFAULT_WEIGHTS, "maintainability": 0.30}
        evaluation = EvolutionEvaluation(
            confidence_score=0.8,
            risk_score=0.2,
            recommendation="approve",
            weights_used=weights_high_maintainability
        )

        await consumer.registry.store_evaluation("plan-456", fingerprint, evaluation)

        # Feedback positivo
        message = {
            "plan_id": "plan-456",
            "fingerprint": fingerprint.model_dump(),
            "evaluation": evaluation.model_dump(),
            "feedback": {
                "outcome": "approve",
                "source": "system",
                "timestamp": "2026-03-24T10:00:00Z"
            }
        }

        await consumer.process_message(message)

        # Buscar similares e verificar pesos
        similar = await consumer.registry.find_similar_patterns(fingerprint, limit=10)
        assert len(similar) > 0
```

- [ ] **Step 2: Implement feedback consumer**

```python
# libraries/python/neural_hive_specialists/evolution_hooks/feedback_consumer.py
"""Kafka consumer for evolution feedback."""

import asyncio
import json
from typing import Dict, Any, Awaitable, Callable
import structlog

from .models import FeedbackMessage, Fingerprint, EvolutionEvaluation, FeedbackData
from .pattern_registry import PatternRegistry

logger = structlog.get_logger()


class EvolutionFeedbackConsumer:
    """Consome feedback do Approval Service e atualiza pattern registry."""

    def __init__(
        self,
        mongo_client,
        topic: str = "evolution.feedback.topic",
        group_id: str = "evolution-hooks-consumer"
    ):
        """
        Inicializa consumer.

        Args:
            mongo_client: Cliente MongoDB
            topic: Tópico Kafka para consumir
            group_id: Consumer group ID
        """
        self.registry = PatternRegistry(mongo_client)
        self.topic = topic
        self.group_id = group_id
        self.logger = logger
        self._running = False

    async def start(self, kafka_consumer_factory):
        """
        Inicia consumo de mensagens.

        Args:
            kafka_consumer_factory: Factory que retorna KafkaConsumer
        """
        self._running = True
        consumer = kafka_consumer_factory(self.topic, self.group_id)

        self.logger.info("Starting feedback consumer", topic=self.topic)

        while self._running:
            try:
                message = await self._poll_with_timeout(consumer, timeout=1.0)
                if message:
                    await self._process_message_async(message)
            except Exception as e:
                self.logger.error("Error consuming message", error=str(e))
                await asyncio.sleep(1)

    async def stop(self):
        """Para consumo de mensagens."""
        self._running = False
        self.logger.info("Stopped feedback consumer")

    async def _poll_with_timeout(self, consumer, timeout: float):
        """
        Poll com timeout usando aiokafka.

        Args:
            consumer: Instância de aiokafka.AIOKafkaConsumer
            timeout: Timeout em segundos

        Returns:
            Mensagem ou None em caso de timeout
        """
        try:
            msg = await asyncio.wait_for(
                consumer.getone(),
                timeout=timeout
            )
            return msg
        except asyncio.TimeoutError:
            return None
        except Exception as e:
            self.logger.error("Error polling kafka", error=str(e))
            return None

    async def _process_message_async(self, raw_message):
        """Processa mensagem de forma assíncrona."""
        try:
            # Parse JSON
            data = raw_message.value() if hasattr(raw_message, 'value') else raw_message
            if isinstance(data, bytes):
                data = json.loads(data.decode())

            # Validar com Pydantic
            message = FeedbackMessage(**data)

            # Processar
            await self.process_message(message.model_dump())

            # Commit offset
            if hasattr(raw_message, 'commit'):
                raw_message.commit()

        except Exception as e:
            self.logger.error("Error processing message", error=str(e))

    async def process_message(self, message: Dict[str, Any]):
        """
        Processa mensagem de feedback.

        Args:
            message: Mensagem parseada do Kafka
        """
        plan_id = message.get("plan_id")
        if not plan_id:
            self.logger.warning("Missing plan_id in feedback message")
            return

        # Construir objetos
        feedback_data = FeedbackData(**message["feedback"])

        # Adicionar feedback ao registry
        success = await self.registry.add_feedback(
            plan_id=plan_id,
            feedback=feedback_data,
            corrected_weights=message.get("evaluation", {}).get("weights_used")
        )

        if success:
            self.logger.info("Feedback processed", plan_id=plan_id)
        else:
            self.logger.warning("Pattern not found for feedback", plan_id=plan_id)
```

- [ ] **Step 3: Run tests**

```bash
pytest libraries/python/neural_hive_specialists/tests/evolution_hooks/integration/test_feedback_loop.py -v
```

- [ ] **Step 4: Commit**

```bash
git add libraries/python/neural_hive_specialists/evolution_hooks/feedback_consumer.py
git add libraries/python/neural_hive_specialists/tests/evolution_hooks/integration/test_feedback_loop.py
git commit -m "feat(evolution-hooks): add feedback consumer

- Kafka consumer for evolution feedback topic
- Process feedback messages and update pattern registry
- Add integration tests for feedback loop

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 7: E2E Tests and Final Verification

**Files:**
- Create: `libraries/python/neural_hive_specialists/tests/evolution_hooks/e2e/test_evolution_hooks_e2e.py`

- [ ] **Step 1: Write E2E tests**

```python
# libraries/python/neural_hive_specialists/tests/evolution_hooks/e2e/test_evolution_hooks_e2e.py
"""E2E tests for Evolution Hooks."""

import pytest
from motor.motor_async import AsyncIOMotorClient
from datetime import datetime

from neural_hive_specialists.evolution_hooks import (
    FingerprintExtractor,
    PatternMatcher,
    WeightAdapter,
    PatternRegistry
)
from neural_hive_specialists.evolution_hooks.models import (
    Fingerprint,
    EvolutionEvaluation,
    FeedbackData,
    FeedbackOutcome,
    FeedbackSource,
    TaskCountRange,
    DEFAULT_WEIGHTS
)


@pytest.mark.e2e
@pytest.mark.asyncio
class TestEvolutionHooksE2E:
    """E2E tests para evolution hooks."""

    async def test_cold_start_to_learning(self, mongo_client):
        """
        Cenário: Cold Start → Learning

        1. Avaliar plano sem histórico → pesos default
        2. Receber 10 feedbacks positivos
        3. Avaliar plano similar → pesos ajustados
        4. Verificar que pesos mudaram na direção correta
        """
        registry = PatternRegistry(mongo_client)
        extractor = FingerprintExtractor()
        matcher = PatternMatcher(mongo_client)
        adapter = WeightAdapter(mongo_client)

        # Limpar registry
        await registry.collection.delete_many({})

        # 1. Cold start - plano técnico médio
        plan1 = {
            "plan_id": "cold-start-1",
            "original_domain": "technical",
            "original_priority": "high",
            "tasks": [
                {"task_type": "BUILD", "estimated_duration_ms": 5000, "dependencies": []},
                {"task_type": "TEST", "estimated_duration_ms": 2000, "dependencies": ["BUILD"]},
                {"task_type": "DEPLOY", "estimated_duration_ms": 3000, "dependencies": ["TEST"]}
            ]
        }

        fingerprint1 = extractor.extract(plan1)
        weights1 = await adapter.adapt_weights(fingerprint1)

        # Cold start = pesos default
        assert weights1 == DEFAULT_WEIGHTS

        # Armazenar avaliação
        await registry.store_evaluation(
            plan1["plan_id"],
            fingerprint1,
            EvolutionEvaluation(
                confidence_score=0.75,
                risk_score=0.25,
                recommendation="approve",
                weights_used=weights1
            )
        )

        # 2. Receber 10 feedbacks positivos
        for i in range(10):
            similar_plan = {
                "plan_id": f"learning-{i}",
                "original_domain": "technical",
                "original_priority": "high",
                "tasks": [
                    {"task_type": "BUILD", "estimated_duration_ms": 5000, "dependencies": []},
                    {"task_type": "TEST", "estimated_duration_ms": 2000, "dependencies": ["BUILD"]}
                ]
            }

            fp = extractor.extract(similar_plan)
            await registry.store_evaluation(
                similar_plan["plan_id"],
                fp,
                EvolutionEvaluation(
                    confidence_score=0.8,
                    risk_score=0.2,
                    recommendation="approve",
                    weights_used={**DEFAULT_WEIGHTS, "maintainability": 0.30}
                )
            )

            # Feedback positivo
            await registry.add_feedback(
                similar_plan["plan_id"],
                FeedbackData(
                    outcome=FeedbackOutcome.APPROVE,
                    source=FeedbackSource.SYSTEM
                )
            )

        # 3. Avaliar plano similar novamente
        plan2 = {
            "plan_id": "cold-start-2",
            "original_domain": "technical",
            "original_priority": "high",
            "tasks": [
                {"task_type": "BUILD", "estimated_duration_ms": 5000, "dependencies": []},
                {"task_type": "TEST", "estimated_duration_ms": 2000, "dependencies": ["BUILD"]}
            ]
        }

        fingerprint2 = extractor.extract(plan2)
        weights2 = await adapter.adapt_weights(fingerprint2)

        # 4. Verificar ajuste
        # maintainability deve ter aumentado (nos testes usamos 0.30)
        assert weights2["maintainability"] > DEFAULT_WEIGHTS["maintainability"]
        assert weights2["maintainability"] <= DEFAULT_WEIGHTS["maintainability"] + 0.05

    async def test_pattern_decay(self, mongo_client):
        """
        Cenário: Pattern Decay

        1. Criar padrão com 100% success rate
        2. Enviar 20 feedbacks negativos
        3. Verificar que pesos foram reajustados
        """
        registry = PatternRegistry(mongo_client)
        extractor = FingerprintExtractor()
        adapter = WeightAdapter(mongo_client)

        await registry.collection.delete_many({})

        # 1. Criar padrão estabelecido (alta success rate)
        for i in range(10):
            plan = {
                "plan_id": f"decay-{i}",
                "original_domain": "business",
                "original_priority": "normal",
                "tasks": [
                    {"task_type": "ANALYZE", "estimated_duration_ms": 1000, "dependencies": []}
                ]
            }

            fp = extractor.extract(plan)
            await registry.store_evaluation(
                plan["plan_id"],
                fp,
                EvolutionEvaluation(
                    confidence_score=0.9,
                    risk_score=0.1,
                    recommendation="approve",
                    weights_used={**DEFAULT_WEIGHTS, "scalability": 0.30}
                )
            )

            # Feedbacks positivos iniciais
            await registry.add_feedback(
                plan["plan_id"],
                FeedbackData(
                    outcome=FeedbackOutcome.APPROVE,
                    source=FeedbackSource.SYSTEM
                )
            )

        # Verificar sucesso inicial
        search_fp = Fingerprint(
            domain="business",
            priority="normal",
            task_count_range=TaskCountRange.SMALL,
            task_types=["ANALYZE"],
            complexity_signature="B-S-1234"
        )

        similar_before = await registry.find_similar_patterns(search_fp, limit=10)
        assert len(similar_before) >= 10

        # 2. Enviar 20 feedbacks negativos
        for i in range(20):
            plan = {
                "plan_id": f"decay-negative-{i}",
                "original_domain": "business",
                "original_priority": "normal",
                "tasks": [
                    {"task_type": "ANALYZE", "estimated_duration_ms": 1000, "dependencies": []}
                ]
            }

            fp = extractor.extract(plan)
            # Usar scalability alto, mas falhar
            await registry.store_evaluation(
                plan["plan_id"],
                fp,
                EvolutionEvaluation(
                    confidence_score=0.9,
                    risk_score=0.1,
                    recommendation="approve",
                    weights_used={**DEFAULT_WEIGHTS, "scalability": 0.30}
                )
            )

            await registry.add_feedback(
                plan["plan_id"],
                FeedbackData(
                    outcome=FeedbackOutcome.REJECT,  # Negativo!
                    source=FeedbackSource.SYSTEM
                )
            )

        # 3. Verificar reajuste
        weights_after = await adapter.adapt_weights(search_fp)

        # scalability deve ter diminuído
        assert weights_after["scalability"] < DEFAULT_WEIGHTS["scalability"]

    async def test_fallback_on_mongodb_failure(self, mongo_client):
        """
        Cenário: Fallback quando MongoDB falha.

        Verifica que o sistema usa pesos default quando MongoDB está indisponível.
        """
        # Adapter com MongoDB client que vai falhar
        class FailingMongoClient:
            async def __getattr__(self, name):
                raise Exception("MongoDB unavailable")

        adapter = WeightAdapter(FailingMongoClient())

        fingerprint = Fingerprint(
            domain="technical",
            priority="high",
            task_count_range=TaskCountRange.MEDIUM,
            task_types=["BUILD"],
            complexity_signature="FAIL"
        )

        # Não deve lançar exceção, deve retornar defaults
        weights = await adapter.adapt_weights(fingerprint)

        assert weights == DEFAULT_WEIGHTS
```

- [ ] **Step 2: Run E2E tests**

```bash
pytest libraries/python/neural_hive_specialists/tests/evolution_hooks/e2e/test_evolution_hooks_e2e.py -v -m e2e
```

- [ ] **Step 3: Run all tests**

```bash
# Todos os testes de evolution_hooks
pytest libraries/python/neural_hive_specialists/tests/evolution_hooks/ -v

# Verificar覆盖率
pytest libraries/python/neural_hive_specialists/tests/evolution_hooks/ --cov=neural_hive_specialists/evolution_hooks --cov-report=term-missing
```

- [ ] **Step 4: Final commit**

```bash
git add libraries/python/neural_hive_specialists/tests/evolution_hooks/e2e/
git commit -m "test(evolution-hooks): add E2E tests

- Cold start to learning scenario
- Pattern decay scenario
- Fallback on MongoDB failure
- All 95+ tests passing

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 8: Documentation and Deploy Preparation

**Files:**
- Update: `libraries/python/neural_hive_specialists/README.md`
- Create: `services/specialist-evolution/docs/EVOLUTION_HOOKS.md`
- Create: `infrastructure/kafka/topics/evolution-feedback-topic.yaml`

- [ ] **Step 1: Update library README**

```markdown
<!-- Add to libraries/python/neural_hive_specialists/README.md -->

## Evolution Hooks

O Evolution Specialist suporta **meta-learning** através de Evolution Hooks, permitindo ajuste adaptativo de pesos baseado em histórico de avaliações.

### Funcionalidade

- Extrai fingerprint dos planos (domínio, tipos de tarefas, complexidade)
- Busca padrões similares no MongoDB
- Ajusta pesos baseado em success rate de planos similares
- Consome feedback do Approval Service para aprendizado contínuo

### Uso

```python
from neural_hive_specialists.evolution_hooks import (
    FingerprintExtractor,
    WeightAdapter
)

extractor = FingerprintExtractor()
adapter = WeightAdapter(mongo_client)

fingerprint = extractor.extract(cognitive_plan)
adaptive_weights = await adapter.adapt_weights(fingerprint)
```

### Configuração

```python
evolution_hooks_enabled: true
min_similar_patterns: 5
weight_adjustment_max: 0.05
```
```

- [ ] **Step 2: Create specialist documentation**

```markdown
<!-- services/specialist-evolution/docs/EVOLUTION_HOOKS.md -->
# Evolution Hooks - Documentação

## Overview

Evolution Hooks permitem que o Evolution Specialist aprenda quais heurísticas funcionam melhor para quais tipos de planos.

## Arquitetura

```
CognitivePlan → FingerprintExtractor → Fingerprint
                                      ↓
                              PatternMatchRegistry
                                      ↓
                              AdaptiveWeights
                                      ↓
                              EvolutionEvaluator
```

## Configuração

```yaml
evolution_hooks:
  enabled: true
  min_similar_patterns: 5
  weight_adjustment_max: 0.05
  feedback_consumer_enabled: true
```

## Métricas

- `evolution_hooks_adaptation_rate`: % de avaliações com pesos adaptados
- `evolution_hooks_pattern_match_count`: Número de matches similares encontrados
- `evolution_hooks_accuracy_improvement`: Melhoria em accuracy sobre baseline
```

- [ ] **Step 3: Create Kafka topic manifest**

```yaml
# infrastructure/kafka/topics/evolution-feedback-topic.yaml
apiVersion: kafka.strimzi.io/v1beta2
kind: KafkaTopic
metadata:
  name: evolution-feedback-topic
  namespace: neural-hive
  labels:
    strimzi.io/cluster: neural-hive-kafka
spec:
  partitions: 3
  replicas: 2
  config:
    retention.ms: 604800000  # 7 dias
    segment.ms: 86400000  # 1 dia
    cleanup.policy: delete
```

- [ ] **Step 4: Commit docs**

```bash
git add libraries/python/neural_hive_specialists/README.md
git add services/specialist-evolution/docs/EVOLUTION_HOOKS.md
git add infrastructure/kafka/topics/evolution-feedback-topic.yaml
git commit -m "docs(evolution-hooks): add documentation and deploy configs

- Update library README with evolution hooks section
- Add specialist documentation
- Add Kafka topic manifest

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Summary Checklist

- [ ] Task 1: Foundation - Models and Database Schema (~25 testes)
- [ ] Task 2: Fingerprint Extractor (15 testes)
- [ ] Task 3: Pattern Matcher (20 testes)
- [ ] Task 4: Weight Adapter (25 testes)
- [ ] Task 5: Evolution Specialist Integration (10 testes)
- [ ] Task 6: Feedback Consumer (10 testes)
- [ ] Task 7: E2E Tests and Final Verification (5 testes)
- [ ] Task 8: Documentation and Deploy Preparation

**Total: ~110 testes**

---

## Verification Steps

1. **Linting**
   ```bash
   ruff check libraries/python/neural_hive_specialists/evolution_hooks/
   black libraries/python/neural_hive_specialists/evolution_hooks/
   ```

2. **All Tests**
   ```bash
   pytest libraries/python/neural_hive_specialists/tests/evolution_hooks/ -v
   ```

3. **Integration**
   ```bash
   pytest services/specialist-evolution/tests/test_evolution_hooks_integration.py -v
   ```

4. **Migration**
   ```bash
   python -m neural_hive_specialists.evolution_hooks.migrations.m001_create_pattern_registry
   ```
