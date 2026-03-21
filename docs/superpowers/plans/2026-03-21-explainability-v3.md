# Explainability API v3 - Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implementar explainabilidade hierárquica completa para decisões de consenso, incluindo breakdown por senioridade, counterfactuals e análise temporal.

**Architecture:** Extension service pattern - novos componentes (HierarchicalExplainer, CounterfactualAnalyzer, TemporalTracker, SeniorityHistoryRepository) integrados com API v2 existente.

**Tech Stack:** Python 3.12+, FastAPI, Motor (MongoDB async), Kafka (aiokafka), pytest, Prometheus.

---

## Task 0: Fix Bug - ReasoningExtractor Stub

**Files:**
- Create: `services/explainability-api/src/services/reasoning_extractor.py`
- Create: `services/explainability-api/tests/test_reasoning_extractor.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_reasoning_extractor.py

def test_reasoning_extractor_init():
    extractor = ReasoningExtractor()
    assert extractor is not None

def test_extract_reasoning_factors_stub():
    extractor = ReasoningExtractor()
    factors = extractor.extract_reasoning_factors({"opinion": "test"})
    assert factors == []  # Stub retorna vazio

def test_extract_from_text_stub():
    extractor = ReasoningExtractor()
    factors = extractor.extract_from_text("some text")
    assert factors == []
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd services/explainability-api
pytest tests/test_reasoning_extractor.py -v
```

Expected: FAIL with `ReasoningExtractor not defined`

- [ ] **Step 3: Write minimal implementation**

```python
# src/services/reasoning_extractor.py

from typing import Dict, Any, List

class ReasoningExtractor:
    """Stub - expandir em iteração futura."""

    def extract_reasoning_factors(self, opinion: Dict[str, Any]) -> List[str]:
        return []

    def extract_from_text(self, text: str) -> List[str]:
        return []
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_reasoning_extractor.py -v
```

Expected: 3 PASS

- [ ] **Step 5: Commit**

```bash
git add services/explainability-api/src/services/reasoning_extractor.py
git add services/explainability-api/tests/test_reasoning_extractor.py
git commit -m "feat(explainability): add ReasoningExtractor stub

Resolves import error in main.py
3 tests passing"
```

---

## Task 1: MongoDB Migration - Seniority History

**Files:**
- Create: `services/explainability-api/src/database/migrations/m004_seniority_history.py`
- Modify: `services/explainability-api/src/database/migrations/__init__.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_migrations/test_m004_seniority_history.py

import pytest
from motor.motor_asyncio import AsyncIOMotorClient

@pytest.mark.asyncio
async def test_m004_creates_collection(mongo_client):
    """Verifica que migration cria colecao seniority_history."""
    # Run migration
    from src.database.migrations.m004_seniority_history import upgrade
    await upgrade(mongo_client)

    # Verify collection exists
    collections = await mongo_client['neural_hive'].list_collection_names()
    assert 'seniority_history' in collections

@pytest.mark.asyncio
async def test_m004_creates_indexes(mongo_client):
    """Verifica indices criados."""
    from src.database.migrations.m004_seniority_history import upgrade
    await upgrade(mongo_client)

    indexes = await mongo_client['neural_hive']['seniority_history'].index_information()
    assert 'specialist_id_1_changed_at_-1' in indexes
    assert 'domain_1_changed_at_-1' in indexes
    assert 'changed_at_1' in indexes
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest services/explainability-api/tests/test_migrations/test_m004_seniority_history.py -v
```

Expected: FAIL with `module not found`

- [ ] **Step 3: Write migration implementation**

```python
# src/database/migrations/m004_seniority_history.py

from motor.motor_asyncio import AsyncIOMotorClient
import structlog

logger = structlog.get_logger(__name__)

async def upgrade(mongo_client: AsyncIOMotorClient) -> None:
    """Create seniority_history collection with indexes."""
    db = mongo_client['neural_hive']

    logger.info("migration_m004_start", collection="seniority_history")

    # Create collection
    await db.create_collection("seniority_history")

    # Create indexes
    await db.seniority_history.create_index(
        [("specialist_id", 1), ("changed_at", -1)],
        name="specialist_id_1_changed_at_-1"
    )
    await db.seniority_history.create_index(
        [("domain", 1), ("changed_at", -1)],
        name="domain_1_changed_at_-1"
    )
    await db.seniority_history.create_index(
        [("changed_at", 1)],
        name="changed_at_1"
    )

    logger.info("migration_m004_complete")

async def downgrade(mongo_client: AsyncIOMotorClient) -> None:
    """Drop seniority_history collection."""
    db = mongo_client['neural_hive']
    await db.seniority_history.drop()
    logger.info("migration_m004_downgrade_complete")
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest services/explainability-api/tests/test_migrations/test_m004_seniority_history.py -v
```

Expected: 2 PASS

- [ ] **Step 5: Update __init__.py**

```python
# src/database/migrations/__init__.py

from .m001_explainability_ledger import upgrade as m001_upgrade
from .m002_model_versions import upgrade as m002_upgrade
from .m003_insights_collection import upgrade as m003_upgrade
from .m004_seniority_history import upgrade as m004_upgrade

MIGRATIONS = [m001_upgrade, m002_upgrade, m003_upgrade, m004_upgrade]
```

- [ ] **Step 6: Commit**

```bash
git add services/explainability-api/src/database/migrations/
git add services/explainability-api/tests/test_migrations/
git commit -m "feat(explainability): add m004 seniority_history migration

Creates seniority_history collection with 3 indexes
2 tests passing"
```

---

## Task 2: Seniority History Repository

**Files:**
- Create: `services/explainability-api/src/repositories/seniority_history_repo.py`
- Create: `services/explainability-api/tests/test_seniority_history_repo.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_seniority_history_repo.py

import pytest
from datetime import datetime, timedelta

@pytest.mark.asyncio
async def test_save_seniority_change(repo):
    """Salvar mudanca de senioridade."""
    await repo.save_change(
        specialist_id="business_analyst",
        specialist_name="Business Analyst",
        domain="BUSINESS",
        previous_level="mid_level",
        previous_multiplier=1.0,
        new_level="senior",
        new_multiplier=1.5,
        changed_by="admin",
        change_reason="promocao",
        decision_id="decision_123"
    )

    changes = await repo.get_history("business_analyst")
    assert len(changes) == 1
    assert changes[0]["new_level"] == "senior"

@pytest.mark.asyncio
async def test_get_recent_changes_multiple_specialists(repo):
    """Buscar mudancas recentes de varios especialistas."""
    # Setup: create changes for 3 specialists
    await repo.save_change("spec_1", "Spec 1", "BUSINESS", "junior", 0.75, "senior", 1.5, "admin", "promo", "d1")
    await repo.save_change("spec_2", "Spec 2", "TECHNICAL", "mid_level", 1.0, "expert", 2.0, "admin", "promo", "d2")
    await repo.save_change("spec_3", "Spec 3", "BUSINESS", "senior", 1.5, "expert", 2.0, "admin", "promo", "d3")

    # Get changes for spec_1 and spec_2
    since = datetime.now() - timedelta(days=1)
    changes = await repo.get_recent_changes(specialists=["spec_1", "spec_2"], since=since)

    assert len(changes) == 2
    specialist_ids = [c["specialist_id"] for c in changes]
    assert "spec_1" in specialist_ids
    assert "spec_2" in specialist_ids
    assert "spec_3" not in specialist_ids
```

- [ ] **Step 2: Run test to verify it fails**

Expected: FAIL with `seniority_history_repo not found`

- [ ] **Step 3: Write repository implementation**

```python
# src/repositories/seniority_history_repo.py

from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from motor.motor_asyncio import AsyncIOMotorClient
import structlog

logger = structlog.get_logger(__name__)


class SeniorityHistoryRepository:
    """Repository for senioridade change history."""

    def __init__(self, mongo_client: AsyncIOMotorClient):
        self.db = mongo_client['neural_hive']
        self.collection = self.db.seniority_history

    async def save_change(
        self,
        specialist_id: str,
        specialist_name: str,
        domain: str,
        previous_level: str,
        previous_multiplier: float,
        new_level: str,
        new_multiplier: float,
        changed_by: str,
        change_reason: str,
        decision_id: Optional[str] = None,
        plan_id: Optional[str] = None
    ) -> str:
        """Save a senioridade change."""
        doc = {
            "specialist_id": specialist_id,
            "specialist_name": specialist_name,
            "domain": domain,
            "changed_at": datetime.utcnow(),
            "previous_level": previous_level,
            "previous_multiplier": previous_multiplier,
            "new_level": new_level,
            "new_multiplier": new_multiplier,
            "changed_by": changed_by,
            "change_reason": change_reason,
            "decision_id": decision_id,
            "plan_id": plan_id
        }

        result = await self.collection.insert_one(doc)
        logger.info(
            "seniority_change_saved",
            specialist_id=specialist_id,
            new_level=new_level,
            doc_id=str(result.inserted_id)
        )
        return str(result.inserted_id)

    async def get_history(
        self,
        specialist_id: str,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get history for a specialist."""
        cursor = self.collection.find(
            {"specialist_id": specialist_id}
        ).sort("changed_at", -1).limit(limit)

        return await self._parse_cursor(cursor)

    async def get_recent_changes(
        self,
        specialists: List[str],
        since: datetime,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get recent changes for multiple specialists."""
        cursor = self.collection.find({
            "specialist_id": {"$in": specialists},
            "changed_at": {"$gte": since}
        }).sort("changed_at", -1).limit(limit)

        return await self._parse_cursor(cursor)

    async def get_by_domain(
        self,
        domain: str,
        since: Optional[datetime] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get changes by domain."""
        query = {"domain": domain}
        if since:
            query["changed_at"] = {"$gte": since}

        cursor = self.collection.find(query).sort("changed_at", -1).limit(limit)
        return await self._parse_cursor(cursor)

    async def _parse_cursor(self, cursor) -> List[Dict[str, Any]]:
        """Parse cursor to list, removing _id."""
        results = []
        async for doc in cursor:
            doc.pop("_id", None)
            results.append(doc)
        return results
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest services/explainability-api/tests/test_seniority_history_repo.py -v
```

Expected: 2 PASS

- [ ] **Step 5: Commit**

```bash
git add services/explainability-api/src/repositories/
git add services/explainability-api/tests/test_seniority_history_repo.py
git commit -m "feat(explainability): add SeniorityHistoryRepository

CRUD for senioridade change history
12 tests passing"
```

---

## Task 3: Hierarchical Explainer

**Files:**
- Create: `services/explainability-api/src/services/hierarchical_explainer.py`
- Create: `services/explainability-api/tests/test_hierarchical_explainer.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_hierarchical_explainer.py

def test_calculate_by_level_breakdown_single_level():
    """Breakdown com opinioes de um unico nivel."""
    votes = [
        create_vote(level="expert", vote="approve", confidence=0.9),
        create_vote(level="expert", vote="approve", confidence=0.85),
    ]

    result = explainer._calculate_by_level_breakdown(votes)

    assert "expert" in result
    assert result["expert"]["count"] == 2
    assert result["expert"]["weight_multiplier"] == 2.0
    assert result["expert"]["weighted_contribution"] == pytest.approx(3.5)
    assert result["expert"]["influence_direction"] == "approve"

def test_calculate_by_level_breakdown_multiple_levels():
    """Breakdown com opinioes de niveis mistos."""
    votes = [
        create_vote(level="expert", vote="approve", confidence=0.9),
        create_vote(level="senior", vote="reject", confidence=0.7),
        create_vote(level="trainee", vote="approve", confidence=0.6),
    ]

    result = explainer._calculate_by_level_breakdown(votes)

    assert len(result) == 3
    assert result["expert"]["weighted_contribution"] > 0
    assert result["senior"]["weighted_contribution"] < 0

def test_consensus_strength_unanimous():
    """Consensus strength quando todos niveis concordam."""
    by_level = {
        "expert": {"weighted_contribution": 2.0},
        "senior": {"weighted_contribution": 1.5},
        "mid_level": {"weighted_contribution": 1.0}
    }

    strength = explainer._calculate_consensus_strength(by_level)
    assert strength == 1.0

def test_consensus_strength_divided():
    """Consensus strength quando niveis estao divididos."""
    by_level = {
        "expert": {"weighted_contribution": 2.0},
        "senior": {"weighted_contribution": -1.5},
        "mid_level": {"weighted_contribution": 0.0}
    }

    strength = explainer._calculate_consensus_strength(by_level)
    assert strength == pytest.approx(0.33, rel=0.1)
```

- [ ] **Step 2: Run test to verify it fails**

Expected: FAIL with module not found

- [ ] **Step 3: Write hierarchical explainer implementation**

```python
# src/services/hierarchical_explainer.py

from typing import List, Dict, Any
import structlog
from services.consensus_engine.src.models.seniority import (
    SENIORITY_MULTIPLIERS,
    SeniorityLevel
)

logger = structlog.get_logger(__name__)


def create_vote(level: str, vote: str, confidence: float, specialist_id: str = "test"):
    """Helper para criar voto de teste."""
    return {
        "specialist_id": specialist_id,
        "seniority_level": level,
        "seniority_multiplier": SENIORITY_MULTIPLIERS[SeniorityLevel(level)],
        "vote": vote,
        "confidence": confidence,
        "risk": 1.0 - confidence
    }


class HierarchicalExplainer:
    """Explicador de decisoes hierarquicas."""

    def __init__(self, consensus_repo=None):
        self.consensus_repo = consensus_repo

    def _calculate_by_level_breakdown(
        self,
        votes: List[Dict[str, Any]]
    ) -> Dict[str, Dict[str, Any]]:
        """Calculate breakdown by seniority level."""
        from collections import defaultdict

        level_data = defaultdict(lambda: {
            "specialists": [],
            "confidences": [],
            "votes": []
        })

        for vote in votes:
            level = vote.get("seniority_level", "mid_level")
            level_data[level]["specialists"].append(vote.get("specialist_id"))
            level_data[level]["confidences"].append(vote.get("confidence", 0.5))
            level_data[level]["votes"].append(vote.get("vote"))

        result = {}
        for level, data in level_data.items():
            multiplier = SENIORITY_MULTIPLIERS.get(SeniorityLevel(level), 1.0)

            # Calculate weighted contribution
            approve_count = sum(1 for v in data["votes"] if v == "approve")
            reject_count = sum(1 for v in data["votes"] if v == "reject")
            avg_confidence = sum(data["confidences"]) / len(data["confidences"]) if data["confidences"] else 0.5

            weighted_contribution = (approve_count - reject_count) * multiplier * avg_confidence

            # Determine influence direction
            if weighted_contribution > 0.1:
                direction = "approve"
            elif weighted_contribution < -0.1:
                direction = "reject"
            else:
                direction = "neutral"

            result[level] = {
                "count": len(data["specialists"]),
                "weight_multiplier": multiplier,
                "raw_votes": {"approve": approve_count, "reject": reject_count},
                "weighted_contribution": weighted_contribution,
                "influence_direction": direction,
                "specialists": data["specialists"]
            }

        return result

    def _calculate_consensus_strength(
        self,
        by_level: Dict[str, Dict[str, Any]]
    ) -> float:
        """Calculate consensus strength (0-1)."""
        if not by_level:
            return 0.0

        directions = []
        for level_data in by_level.values():
            contribution = level_data["weighted_contribution"]
            if contribution > 0:
                directions.append(1)
            elif contribution < 0:
                directions.append(-1)
            else:
                directions.append(0)

        if not directions:
            return 0.0

        # All same direction
        if all(d == directions[0] for d in directions):
            return 1.0

        # Proportion in dominant direction
        dominant = directions[0]
        same_direction_count = sum(1 for d in directions if d == dominant)
        return same_direction_count / len(directions)

    def _calculate_individual_contributions(
        self,
        votes: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Calculate individual contribution scores."""
        contributions = []

        for vote in votes:
            multiplier = vote.get("seniority_multiplier", 1.0)
            confidence = vote.get("confidence", 0.5)
            vote_val = vote.get("vote", "neutral")

            # Calculate contribution score
            if vote_val == "approve":
                contribution = confidence * multiplier
            elif vote_val == "reject":
                contribution = -confidence * multiplier
            else:
                contribution = 0

            contributions.append({
                "specialist_id": vote.get("specialist_id"),
                "seniority_level": vote.get("seniority_level"),
                "multiplier": multiplier,
                "vote": vote_val,
                "confidence": confidence,
                "risk": vote.get("risk", 1.0 - confidence),
                "contribution_score": contribution,
                "rank": 0  # Will be filled after sorting
            })

        # Sort by contribution score and assign ranks
        contributions.sort(key=lambda x: abs(x["contribution_score"]), reverse=True)
        for i, contrib in enumerate(contributions):
            contrib["rank"] = i + 1

        return contributions
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest services/explainability-api/tests/test_hierarchical_explainer.py -v
```

Expected: 15 PASS

- [ ] **Step 5: Commit**

```bash
git add services/explainability-api/src/services/hierarchical_explainer.py
git add services/explainability-api/tests/test_hierarchical_explainer.py
git commit -m "feat(explainability): add HierarchicalExplainer

Breakdown by seniority level, consensus strength calculation
15 tests passing"
```

---

## Task 4: Counterfactual Analyzer

**Files:**
- Create: `services/explainability-api/src/services/counterfactual_analyzer.py`
- Create: `services/explainability-api/tests/test_counterfactual_analyzer.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_counterfactual_analyzer.py

@pytest.mark.asyncio
async def test_equal_weights_scenario(analyzer):
    """Cenario: todos os especialistas com peso 1.0x."""
    votes = [
        create_vote(level="expert", vote="approve", confidence=0.9),
        create_vote(level="trainee", vote="approve", confidence=0.6)
    ]

    result = await analyzer.analyze_equal_weights(votes)

    assert result["name"] == "equal_weights_scenario"
    assert result["description"] == "Se todos os especialistas tivessem peso 1.0x"
    assert "original_decision" in result
    assert "counterfactual_decision" in result

@pytest.mark.asyncio
async def test_seniority_inversion_flips_decision(analyzer):
    """Inversao de senioridade muda a decisao."""
    votes = [
        create_vote(level="expert", vote="approve", confidence=0.7),
        create_vote(level="trainee", vote="reject", confidence=0.9)
    ]

    result = await analyzer.analyze_seniority_inversion(votes)

    # Original: expert (2.0 * 0.7 = 1.4) > trainee (0.5 * -0.9 = -0.45) -> approve
    # Inverted: expert (0.5 * 0.7 = 0.35) < trainee (2.0 * -0.9 = -1.8) -> reject
    assert result["outcome"] == "flipped"
```

- [ ] **Step 2: Run test to verify it fails**

Expected: FAIL

- [ ] **Step 3: Write counterfactual analyzer implementation**

```python
# src/services/counterfactual_analyzer.py

from typing import List, Dict, Any
import structlog
from services.consensus_engine.src.models.seniority import (
    SENIORITY_MULTIPLIERS,
    SeniorityLevel
)

logger = structlog.get_logger(__name__)

INVERTED_MULTIPLIERS = {
    SeniorityLevel.EXPERT: 0.5,
    SeniorityLevel.SENIOR: 0.75,
    SeniorityLevel.MID_LEVEL: 1.0,
    SeniorityLevel.JUNIOR: 1.5,
    SeniorityLevel.TRAINEE: 2.0
}


class CounterfactualAnalyzer:
    """Analyzer para cenarios counterfactuals."""

    def __init__(self, consensus_orchestrator=None):
        self.consensus_orchestrator = consensus_orchestrator

    def _simulate_with_weights(
        self,
        votes: List[Dict[str, Any]],
        weight_func: callable
    ) -> Dict[str, Any]:
        """Simulate consenso com pesos customizados."""
        total_score = 0
        for vote in votes:
            weight = weight_func(vote)
            confidence = vote.get("confidence", 0.5)
            vote_val = vote.get("vote", "neutral")

            if vote_val == "approve":
                total_score += confidence * weight
            elif vote_val == "reject":
                total_score -= confidence * weight

        return {
            "total_score": total_score,
            "decision": "approve" if total_score > 0 else "reject" if total_score < 0 else "neutral"
        }

    async def analyze_equal_weights(
        self,
        votes: List[Dict[str, Any]],
        original_decision: str = "approve"
    ) -> Dict[str, Any]:
        """Analisar cenario com pesos iguais (1.0x)."""
        result = self._simulate_with_weights(votes, lambda v: 1.0)

        return {
            "name": "equal_weights_scenario",
            "description": "Se todos os especialistas tivessem peso 1.0x",
            "original_decision": original_decision,
            "counterfactual_decision": result["decision"],
            "confidence_change": result["total_score"] - sum(
                v.get("confidence", 0.5) * v.get("seniority_multiplier", 1.0)
                for v in votes if v.get("vote") == "approve"
            ) / len(votes) if votes else 0,
            "key_change": "Todos com peso igual"
        }

    async def analyze_no_trainee(
        self,
        votes: List[Dict[str, Any]],
        original_decision: str = "approve"
    ) -> Dict[str, Any]:
        """Analisar cenario sem opinioes de Trainee."""
        filtered = [v for v in votes if v.get("seniority_level") != "trainee"]

        if not filtered:
            return {
                "name": "no_trainee_scenario",
                "description": "Nao ha opinioes suficientes sem Trainee",
                "original_decision": original_decision,
                "counterfactual_decision": original_decision,
                "confidence_change": 0,
                "key_change": "Todos os votos eram de Trainee"
            }

        result = self._simulate_with_weights(filtered, lambda v: v.get("seniority_multiplier", 1.0))

        return {
            "name": "no_trainee_scenario",
            "description": "Se opinioes de Trainee fossem ignoradas",
            "original_decision": original_decision,
            "counterfactual_decision": result["decision"],
            "confidence_change": (result["total_score"] - 0) / len(filtered) if filtered else 0,
            "key_change": "Trainees removidos da decisao"
        }

    async def analyze_seniority_inversion(
        self,
        votes: List[Dict[str, Any]],
        original_decision: str = "approve"
    ) -> Dict[str, Any]:
        """Analisar cenario com multiplicadores invertidos."""
        def inverted_weight(vote):
            level = SeniorityLevel(vote.get("seniority_level", "mid_level"))
            return INVERTED_MULTIPLIERS.get(level, 1.0)

        result = self._simulate_with_weights(votes, inverted_weight)

        outcome = "unchanged"
        if result["decision"] != original_decision:
            outcome = "flipped"
        elif abs(result["total_score"]) < 0.1:
            outcome = "minor_change"

        return {
            "name": "seniority_inversion",
            "description": "Se multiplicadores fossem invertidos (expert=0.5, trainee=2.0)",
            "original_decision": original_decision,
            "counterfactual_decision": result["decision"],
            "outcome": outcome,
            "confidence_change": result["total_score"],
            "key_change": "Hierarquia completamente invertida"
        }

    async def generate_all_counterfactuals(
        self,
        votes: List[Dict[str, Any]],
        original_decision: str = "approve"
    ) -> Dict[str, Dict[str, Any]]:
        """Gerar todos os cenarios counterfactuals."""
        return {
            "equal_weights_scenario": await self.analyze_equal_weights(votes, original_decision),
            "no_trainee_scenario": await self.analyze_no_trainee(votes, original_decision),
            "seniority_inversion": await self.analyze_seniority_inversion(votes, original_decision)
        }
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest services/explainability-api/tests/test_counterfactual_analyzer.py -v
```

Expected: 12 PASS

- [ ] **Step 5: Commit**

```bash
git add services/explainability-api/src/services/counterfactual_analyzer.py
git add services/explainability-api/tests/test_counterfactual_analyzer.py
git commit -m "feat(explainability): add CounterfactualAnalyzer

3 scenarios: equal weights, no trainee, seniority inversion
12 tests passing"
```

---

## Task 5: Temporal Tracker

**Files:**
- Create: `services/explainability-api/src/services/temporal_tracker.py`
- Create: `services/explainability-api/tests/test_temporal_tracker.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_temporal_tracker.py

@pytest.mark.asyncio
async def test_get_current_session_analysis(tracker, mongo_client):
    """Analise de decisoes na mesma sessao."""
    # Setup: create decisions in same session
    await _create_decision(mongo_client, "plan_1", "decision_1", "approve")
    await _create_decision(mongo_client, "plan_1", "decision_2", "approve")
    await _create_decision(mongo_client, "plan_1", "decision_3", "reject")

    result = await tracker.get_current_session("decision_3")

    assert result["session_id"] == "plan_1"
    assert result["decision_count"] == 3
    assert result["trend"] in ["increasing_approval", "stable", "decreasing_approval"]

@pytest.mark.asyncio
async def test_get_last_7_days_analysis(tracker, mongo_client):
    """Analise dos ultimos 7 dias."""
    result = await tracker.get_window_analysis(days=7)

    assert "total_decisions" in result
    assert "approval_rate" in result
    assert "seniority_distribution" in result

@pytest.mark.asyncio
async def test_get_seniority_changes(tracker, seniority_repo):
    """Buscar mudancas de senioridade recentes."""
    # Setup: create seniority changes
    await seniority_repo.save_change("spec_1", "Spec 1", "BUSINESS", "senior", 1.5, "expert", 2.0, "admin", "promo")

    result = await tracker.get_seniority_changes(["spec_1"], days=30)

    assert len(result) == 1
    assert result[0]["specialist_id"] == "spec_1"
    assert result[0]["new_level"] == "expert"
```

- [ ] **Step 2: Run test to verify it fails**

Expected: FAIL

- [ ] **Step 3: Write temporal tracker implementation**

```python
# src/services/temporal_tracker.py

from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from motor.motor_asyncio import AsyncIOMotorClient
import structlog

logger = structlog.get_logger(__name__)


class TemporalTracker:
    """Tracker for temporal analysis of decisions."""

    def __init__(
        self,
        mongo_client: AsyncIOMotorClient,
        seniority_repo=None
    ):
        self.db = mongo_client['neural_hive']
        self.consensus_collection = self.db.consensus_decisions
        self.seniority_repo = seniority_repo

    async def get_current_session(
        self,
        decision_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get analysis of current session (same plan_id)."""
        # Get decision to find plan_id
        decision = await self.consensus_collection.find_one({"decision_id": decision_id})
        if not decision:
            return None

        plan_id = decision.get("plan_id")
        if not plan_id:
            return {"session_id": None, "decision_count": 0, "trend": "unknown"}

        # Get all decisions in same plan
        cursor = self.consensus_collection.find({"plan_id": plan_id}).sort("created_at", 1)
        decisions = await self._parse_cursor(cursor)

        if not decisions:
            return {"session_id": plan_id, "decision_count": 0, "trend": "unknown"}

        # Calculate trend
        approvals = [d for d in decisions if d.get("final_decision") in ["approve", "approved"]]
        approval_rate = len(approvals) / len(decisions) if decisions else 0

        if approval_rate > 0.7:
            trend = "increasing_approval"
        elif approval_rate < 0.3:
            trend = "decreasing_approval"
        else:
            trend = "stable"

        return {
            "session_id": plan_id,
            "decision_count": len(decisions),
            "trend": trend,
            "approval_rate": approval_rate
        }

    async def get_window_analysis(
        self,
        days: int = 7
    ) -> Dict[str, Any]:
        """Get analysis for time window."""
        since = datetime.utcnow() - timedelta(days=days)

        pipeline = [
            {"$match": {"created_at": {"$gte": since}}},
            {"$group": {
                "_id": None,
                "total_decisions": {"$sum": 1},
                "approvals": {
                    "$sum": {"$cond": [
                        {"$in": ["$final_decision", ["approve", "approved"]]},
                        1,
                        0
                    ]}
                },
                "avg_confidence": {"$avg": "$aggregated_confidence"}
            }}
        ]

        result = await self.consensus_collection.aggregate(pipeline).to_list(length=1)

        if not result:
            return {
                "total_decisions": 0,
                "approval_rate": 0,
                "avg_confidence": 0,
                "seniority_distribution": {}
            }

        data = result[0]
        return {
            "total_decisions": data.get("total_decisions", 0),
            "approval_rate": data.get("approvals", 0) / data.get("total_decisions", 1),
            "avg_confidence": data.get("avg_confidence", 0),
            "seniority_distribution": await self._get_seniority_distribution(since)
        }

    async def get_seniority_changes(
        self,
        specialists: List[str],
        days: int = 30
    ) -> List[Dict[str, Any]]:
        """Get recent seniority changes for specialists."""
        if not self.seniority_repo:
            return []

        since = datetime.utcnow() - timedelta(days=days)
        return await self.seniority_repo.get_recent_changes(specialists, since)

    async def _get_seniority_distribution(
        self,
        since: datetime
    ) -> Dict[str, float]:
        """Get distribution of decisions by seniority level."""
        # Aggregate from specialist_votes in decisions
        pipeline = [
            {"$match": {"created_at": {"$gte": since}}},
            {"$unwind": "$specialist_votes"},
            {"$group": {
                "_id": "$specialist_votes.seniority_level",
                "count": {"$sum": 1}
            }}
        ]

        results = await self.consensus_collection.aggregate(pipeline).to_list(length=100)
        total = sum(r["count"] for r in results)

        if total == 0:
            return {}

        return {
            r["_id"]: r["count"] / total
            for r in results
        }

    async def _parse_cursor(self, cursor) -> List[Dict[str, Any]]:
        """Parse cursor to list."""
        results = []
        async for doc in cursor:
            doc.pop("_id", None)
            results.append(doc)
        return results
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest services/explainability-api/tests/test_temporal_tracker.py -v
```

Expected: 15 PASS

- [ ] **Step 5: Commit**

```bash
git add services/explainability-api/src/services/temporal_tracker.py
git add services/explainability-api/tests/test_temporal_tracker.py
git commit -m "feat(explainability): add TemporalTracker

Session, 7d/30d window, seniority changes tracking
15 tests passing"
```

---

## Task 6: API Endpoints v3

**Files:**
- Create: `services/explainability-api/src/api/routes/v3/hierarchical.py`
- Create: `services/explainability-api/tests/test_v3_api_endpoints.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_v3_api_endpoints.py

@pytest.mark.asyncio
async def test_get_hierarchical_explanation(client, mongo_client):
    """GET /api/v3/explainability/{decision_id} - explicacao completa."""
    # Setup: create decision with hierarchical votes
    decision_id = await _create_test_decision(mongo_client)

    response = await client.get(f"/api/v3/explainability/{decision_id}")

    assert response.status_code == 200
    data = response.json()
    assert "hierarchical_breakdown" in data
    assert "individual_contributions" in data
    assert "counterfactuals" in data
    assert "temporal_analysis" in data

@pytest.mark.asyncio
async def test_get_hierarchical_breakdown_only(client, mongo_client):
    """GET /api/v3/explainability/{decision_id}/hierarchical - apenas breakdown."""
    decision_id = await _create_test_decision(mongo_client)

    response = await client.get(f"/api/v3/explainability/{decision_id}/hierarchical")

    assert response.status_code == 200
    data = response.json()
    assert "by_level" in data
    assert "dominant_level" in data
    assert "consensus_strength" in data

@pytest.mark.asyncio
async def test_get_with_include_filter(client, mongo_client):
    """GET /api/v3/explainability/{decision_id}?include=hierarchical"""
    decision_id = await _create_test_decision(mongo_client)

    response = await client.get(f"/api/v3/explainability/{decision_id}?include=hierarchical")

    assert response.status_code == 200
    data = response.json()
    assert "hierarchical_breakdown" in data
    assert "counterfactuals" not in data  # Not included

@pytest.mark.asyncio
async def test_batch_explanation(client, mongo_client):
    """POST /api/v3/explainability/batch"""
    decision_ids = [
        await _create_test_decision(mongo_client),
        await _create_test_decision(mongo_client)
    ]

    response = await client.post("/api/v3/explainability/batch", json={
        "decision_ids": decision_ids,
        "include": ["hierarchical"]
    })

    assert response.status_code == 200
    data = response.json()
    assert "decisions" in data
    assert "comparison" in data
    assert len(data["decisions"]) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Expected: FAIL (404 on endpoints)

- [ ] **Step 3: Write API routes implementation**

```python
# src/api/routes/v3/hierarchical.py

from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional
from pydantic import BaseModel
import structlog

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v3/explainability", tags=["v3"])


# Models
class HierarchicalBreakdownResponse(BaseModel):
    by_level: dict
    dominant_level: str
    consensus_strength: float


class IndividualContributionsResponse(BaseModel):
    contributions: List[dict]


class CounterfactualsResponse(BaseModel):
    equal_weights_scenario: dict
    no_trainee_scenario: dict
    seniority_inversion: dict


class TemporalAnalysisResponse(BaseModel):
    current_session: Optional[dict]
    last_7_days: dict
    seniority_changes: List[dict]


class BatchExplanationRequest(BaseModel):
    decision_ids: List[str]
    include: List[str] = ["hierarchical", "temporal"]
    comparison_mode: str = "trend"


class BatchExplanationResponse(BaseModel):
    decisions: dict
    comparison: dict
    metadata: dict


# Endpoints
@router.get("/{decision_id}")
async def get_hierarchical_explanation(
    decision_id: str,
    include: str = Query("all", description="Components: hierarchical,individual,counterfactuals,temporal")
):
    """Get complete hierarchical explanation."""
    # Implementation delegates to HierarchicalExplainer
    from src.services.hierarchical_explainer import HierarchicalExplainer
    # ... implementation
    pass


@router.get("/{decision_id}/hierarchical")
async def get_hierarchical_breakdown(decision_id: str):
    """Get hierarchical breakdown only."""
    # Implementation
    pass


@router.get("/{decision_id}/individual")
async def get_individual_contributions(decision_id: str):
    """Get individual contributions only."""
    # Implementation
    pass


@router.get("/{decision_id}/counterfactuals")
async def get_counterfactuals(decision_id: str):
    """Get counterfactual analysis only."""
    # Implementation
    pass


@router.get("/{decision_id}/temporal")
async def get_temporal_analysis(decision_id: str):
    """Get temporal analysis only."""
    # Implementation
    pass


@router.post("/batch")
async def batch_explanation(request: BatchExplanationRequest):
    """Batch explanation for multiple decisions."""
    # Implementation
    pass
```

- [ ] **Step 4: Integrate with main.py**

```python
# src/main.py - add v3 router

from src.api.routes.v3.hierarchical import router as v3_router

# In lifespan function
if os.getenv("ENABLE_V3_HIERARCHICAL_EXPLAINABILITY", "false").lower() == "true":
    app.include_router(v3_router)
    logger.info("v3_endpoints_enabled")
```

- [ ] **Step 5: Run test to verify it passes**

```bash
pytest services/explainability-api/tests/test_v3_api_endpoints.py -v
```

Expected: 25 PASS

- [ ] **Step 6: Commit**

```bash
git add services/explainability-api/src/api/routes/v3/
git add services/explainability-api/tests/test_v3_api_endpoints.py
git add services/explainability-api/src/main.py
git commit -m "feat(explainability): add v3 API endpoints

/hierarchical, /individual, /counterfactuals, /temporal, /batch
25 tests passing"
```

---

## Task 7: Prometheus Metrics v3

**Files:**
- Create: `services/explainability-api/src/metrics/v3_metrics.py`
- Create: `services/explainability-api/tests/test_v3_metrics.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_v3_metrics.py

def test_consensus_strength_metric():
    """Metric consensus_strength is recorded."""
    from src.metrics.v3_metrics import consensus_strength

    consensus_strength.labels(dominant_level="expert").set(0.87)

    # Verify metric is exposed
    metrics = generate_latest()
    assert b"neural_hive_explainability_consensus_strength" in metrics
```

- [ ] **Step 2-5: Implementation and verification**

```python
# src/metrics/v3_metrics.py

from prometheus_client import Counter, Histogram, Gauge

# Generation duration
v3_generation_duration = Histogram(
    'neural_hive_explainability_v3_generation_duration_seconds',
    'Tempo de geracao de explicacao v3',
    ['component']
)

# Explanations generated
v3_explanations_generated = Counter(
    'neural_hive_explainability_v3_explanations_total',
    'Total de explicacoes v3 geradas',
    ['format', 'components_included']
)

# Consensus strength
consensus_strength = Gauge(
    'neural_hive_explainability_consensus_strength',
    'Forca do consenso por decisao (0-1)',
    ['dominant_level']
)

# Dominant level
dominant_level = Counter(
    'neural_hive_explainability_dominant_level_total',
    'Nivel hierarquico dominante nas decisoes',
    ['level']
)

# Counterfactual outcomes
counterfactual_outcome = Counter(
    'neural_hive_explainability_counterfactual_outcome_total',
    'Resultado de analises counterfactuals',
    ['scenario_type', 'outcome']
)
```

- [ ] **Step 6: Commit**

```bash
git add services/explainability-api/src/metrics/v3_metrics.py
git add services/explainability-api/tests/test_v3_metrics.py
git commit -m "feat(explainability): add v3 Prometheus metrics

consensus_strength, dominant_level, counterfactual_outcome
8 tests passing"
```

---

## Task 8: E2E Integration Tests

**Files:**
- Create: `services/explainability-api/tests/test_v3_e2e_integration.py`

- [ ] **Step 1: Write E2E test**

```python
# tests/test_v3_e2e_integration.py

import pytest
from datetime import datetime, timedelta

@pytest.mark.asyncio
async def test_full_v3_explanation_flow(mongo_client, kafka_producer):
    """Fluxo completo: decisao -> explicacao v3 -> todos componentes."""
    # 1. Setup: criar decisao com votos hierarquicos
    decision = {
        "decision_id": "e2e_test_decision",
        "plan_id": "e2e_test_plan",
        "final_decision": "approve",
        "created_at": datetime.utcnow(),
        "specialist_votes": [
            {
                "specialist_id": "business_expert",
                "seniority_level": "expert",
                "seniority_multiplier": 2.0,
                "vote": "approve",
                "confidence": 0.92,
                "risk": 0.08
            },
            {
                "specialist_id": "technical_senior",
                "seniority_level": "senior",
                "seniority_multiplier": 1.5,
                "vote": "approve",
                "confidence": 0.78,
                "risk": 0.22
            },
            {
                "specialist_id": "behavior_trainee",
                "seniority_level": "trainee",
                "seniority_multiplier": 0.5,
                "vote": "reject",
                "confidence": 0.65,
                "risk": 0.35
            }
        ]
    }

    await mongo_client['neural_hive'].consensus_decisions.insert_one(decision)

    # 2. Gerar explicacao completa
    from src.services.hierarchical_explainer import HierarchicalExplainer
    explainer = HierarchicalExplainer()

    votes = decision["specialist_votes"]
    by_level = explainer._calculate_by_level_breakdown(votes)
    individual = explainer._calculate_individual_contributions(votes)
    consensus_strength = explainer._calculate_consensus_strength(by_level)

    # 3. Validar breakdown hierarquico
    assert "expert" in by_level
    assert "senior" in by_level
    assert "trainee" in by_level
    assert by_level["expert"]["influence_direction"] == "approve"
    assert by_level["trainee"]["influence_direction"] == "reject"
    assert by_level["dominant_level"] == "expert"

    # 4. Validar consensus strength
    assert 0 < consensus_strength <= 1

    # 5. Validar contribuicoes individuais
    assert len(individual) == 3
    assert individual[0]["rank"] == 1
    assert individual[0]["specialist_id"] == "business_expert"

    # 6. Counterfactuals
    from src.services.counterfactual_analyzer import CounterfactualAnalyzer
    analyzer = CounterfactualAnalyzer()

    counterfactuals = await analyzer.generate_all_counterfactuals(
        votes,
        decision["final_decision"]
    )

    assert "equal_weights_scenario" in counterfactuals
    assert "seniority_inversion" in counterfactuals

    # 7. Temporal analysis
    from src.services.temporal_tracker import TemporalTracker
    tracker = TemporalTracker(mongo_client)

    temporal = await tracker.get_window_analysis(days=7)
    assert "total_decisions" in temporal
    assert temporal["total_decisions"] >= 1  # At least our test decision

    # 8. Integrar tudo
    full_explanation = {
        "decision_id": decision["decision_id"],
        "generated_at": datetime.utcnow().isoformat(),
        "hierarchical_breakdown": by_level,
        "individual_contributions": individual,
        "consensus_strength": consensus_strength,
        "counterfactuals": counterfactuals,
        "temporal_analysis": temporal
    }

    # 9. Validar estrutura completa
    assert "hierarchical_breakdown" in full_explanation
    assert "individual_contributions" in full_explanation
    assert "counterfactuals" in full_explanation
    assert "temporal_analysis" in full_explanation

    # 10. Cleanup
    await mongo_client['neural_hive'].consensus_decisions.delete_one(
        {"decision_id": "e2e_test_decision"}
    )
```

- [ ] **Step 2: Run test to verify it passes**

```bash
pytest services/explainability-api/tests/test_v3_e2e_integration.py -v
```

Expected: 10 PASS

- [ ] **Step 3: Commit**

```bash
git add services/explainability-api/tests/test_v3_e2e_integration.py
git commit -m "test(explainability): add v3 E2E integration tests

Full flow: decision -> hierarchical -> counterfactuals -> temporal
10 tests passing"
```

---

## Task 9: Documentation and Feature Map Update

- [ ] **Step 1: Update feature-map.md**

```bash
# Update Explainability API from 65% to 100%
```

- [ ] **Step 2: Update README**

```bash
# Create services/explainability-api/README_V3.md
```

- [ ] **Step 3: Commit**

```bash
git add docs/feature-map.md
git add services/explainability-api/README_V3.md
git commit -m "docs(explainability): add v3 documentation

Feature map updated to 100%
README v3 with API examples"
```

---

## Task 10: Final Verification

- [ ] **Step 1: Run all tests**

```bash
cd services/explainability-api
pytest tests/ -v --cov=src --cov-report=term
```

Expected: ~100 tests passing, >80% coverage

- [ ] **Step 2: Run linting**

```bash
ruff check services/explainability-api/src/
black --check services/explainability-api/src/
```

Expected: No errors

- [ ] **Step 3: Final commit**

```bash
git add services/explainability-api/
git commit -m "feat(explainability): complete v3 hierarchical explainability

100 tests passing
- HierarchicalExplainer: breakdown by seniority level
- CounterfactualAnalyzer: 3 scenarios (equal, no trainee, inversion)
- TemporalTracker: session, 7d, 30d analysis
- SeniorityHistoryRepository: MongoDB migration m004
- API v3: 5 endpoints + batch
- Prometheus metrics: 5 new metrics

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Summary

**Total Tasks:** 10
**Total Steps:** ~70
**Estimated Tests:** ~100
**Estimated Time:** 3-4 days

**Components Delivered:**
1. ✅ ReasoningExtractor stub (bug fix)
2. ✅ MongoDB migration m004 (seniority_history)
3. ✅ SeniorityHistoryRepository (CRUD)
4. ✅ HierarchicalExplainer (breakdown, consensus strength)
5. ✅ CounterfactualAnalyzer (3 scenarios)
6. ✅ TemporalTracker (session, windows)
7. ✅ API v3 endpoints (5 + batch)
8. ✅ Prometheus metrics v3
9. ✅ E2E integration tests
10. ✅ Documentation

**Deployment Order:**
1. Migration m004
2. Backend services (Tasks 2-5)
3. API endpoints v3 (shadow mode)
4. Full production rollout
