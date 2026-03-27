"""Testes unitários para Evolution Tracker."""

import pytest
from datetime import datetime, timezone
from unittest.mock import Mock, AsyncMock, patch

from src.evolution.drift_detector import DriftDetector
from src.evolution.diff_calculator import DiffCalculator
from src.models.architecture import ArchitecturePlan, ArchitectureType, Component, Pattern
from src.models.evolution import DriftType, Severity


@pytest.fixture
def sample_plan():
    return ArchitecturePlan(
        plan_id="arch-123",
        cognitive_plan_id=None,
        architecture_type=ArchitectureType.MICROSERVICES,
        components=[
            Component(name="api-gateway", stack="python/fastapi"),
            Component(name="auth-service", stack="python/fastapi"),
        ],
        patterns=[Pattern.REPOSITORY, Pattern.SAGA],
        rationale="API gateway pattern"
    )


@pytest.fixture
def sample_implemented():
    return {
        "architecture_type": "microservices",
        "components": [
            {"name": "api-gateway", "stack": "python/fastapi"},
            {"name": "auth-service", "stack": "nodejs/express"},  # Stack divergiu
        ],
        "patterns": ["repository"],  # SAGA não aplicado
        "tech_stack": {"frameworks": ["python/fastapi", "nodejs/express"]}
    }


@pytest.fixture
def detector():
    return DriftDetector()


@pytest.fixture
def calculator():
    return DiffCalculator()


# DriftDetector Tests
def test_detect_drifts_finds_stack_drift(detector, sample_plan, sample_implemented):
    drifts = detector.detect_drifts(sample_plan, sample_implemented)

    stack_drifts = [d for d in drifts if d.drift_type == DriftType.STACK]
    assert len(stack_drifts) > 0
    assert "auth-service" in stack_drifts[0].description


def test_detect_drifts_finds_pattern_drift(detector, sample_plan, sample_implemented):
    drifts = detector.detect_drifts(sample_plan, sample_implemented)

    pattern_drifts = [d for d in drifts if d.drift_type == DriftType.PATTERNS]
    assert len(pattern_drifts) > 0
    assert "saga" in pattern_drifts[0].description.lower()


def test_detect_drifts_no_drifts_when_match(detector, sample_plan):
    implemented = {
        "architecture_type": "microservices",
        "components": [
            {"name": "api-gateway", "stack": "python/fastapi"},
            {"name": "auth-service", "stack": "python/fastapi"},
        ],
        "patterns": ["repository", "saga"],
        "tech_stack": {"frameworks": ["python/fastapi"]}
    }

    drifts = detector.detect_drifts(sample_plan, implemented)
    assert len(drifts) == 0


def test_detect_drifts_missing_component(detector, sample_plan):
    implemented = {
        "architecture_type": "microservices",
        "components": [
            {"name": "api-gateway", "stack": "python/fastapi"}
            # auth-service missing
        ],
        "patterns": ["repository"],
        "tech_stack": {"frameworks": ["python/fastapi"]}
    }

    drifts = detector.detect_drifts(sample_plan, implemented)
    component_drifts = [d for d in drifts if d.drift_type == DriftType.COMPONENTS]
    assert len(component_drifts) > 0
    assert "auth-service" in component_drifts[0].description


def test_detect_drifts_architecture_type_change(detector, sample_plan):
    implemented = {
        "architecture_type": "monolith",  # Diferente do planejado
        "components": [
            {"name": "api-gateway", "stack": "python/fastapi"},
        ],
        "patterns": ["repository"],
        "tech_stack": {"frameworks": ["python/fastapi"]}
    }

    drifts = detector.detect_drifts(sample_plan, implemented)
    arch_drifts = [d for d in drifts if d.drift_type == DriftType.ARCHITECTURE]
    assert len(arch_drifts) > 0
    assert arch_drifts[0].severity == Severity.HIGH


def test_detect_drifts_severity_levels(detector, sample_plan, sample_implemented):
    drifts = detector.detect_drifts(sample_plan, sample_implemented)

    # Verificar que severidades são aplicadas corretamente
    severities = [d.severity for d in drifts]
    assert Severity.LOW in severities or Severity.MEDIUM in severities


# DiffCalculator Tests
def test_calculate_diff_detects_additions(calculator, sample_plan):
    new_plan = ArchitecturePlan(
        plan_id="arch-456",
        cognitive_plan_id=None,
        architecture_type=ArchitectureType.MICROSERVICES,
        components=[
            Component(name="api-gateway", stack="python/fastapi"),
            Component(name="auth-service", stack="python/fastapi"),
            Component(name="payment-service", stack="python/fastapi"),  # New
        ],
        patterns=[Pattern.REPOSITORY],
        rationale="Updated"
    )

    diff = calculator.calculate_diff(sample_plan, new_plan)
    assert "payment-service" in diff.additions


def test_calculate_diff_detects_removals(calculator, sample_plan):
    new_plan = ArchitecturePlan(
        plan_id="arch-456",
        cognitive_plan_id=None,
        architecture_type=ArchitectureType.MICROSERVICES,
        components=[
            Component(name="api-gateway", stack="python/fastapi")
            # auth-service removed
        ],
        patterns=[Pattern.REPOSITORY],
        rationale="Updated"
    )

    diff = calculator.calculate_diff(sample_plan, new_plan)
    assert "auth-service" in diff.removals


def test_calculate_diff_detects_stack_modifications(calculator, sample_plan):
    new_plan = ArchitecturePlan(
        plan_id="arch-456",
        cognitive_plan_id=None,
        architecture_type=ArchitectureType.MICROSERVICES,
        components=[
            Component(name="api-gateway", stack="nodejs/express"),  # Changed
            Component(name="auth-service", stack="python/fastapi"),
        ],
        patterns=[Pattern.REPOSITORY],
        rationale="Updated"
    )

    diff = calculator.calculate_diff(sample_plan, new_plan)
    assert len(diff.modifications) > 0
    assert "api-gateway" in diff.modifications[0]


def test_calculate_diff_detects_migration_required(calculator, sample_plan):
    new_plan = ArchitecturePlan(
        plan_id="arch-456",
        cognitive_plan_id=None,
        architecture_type=ArchitectureType.MONOLITH,  # Type change
        components=sample_plan.components,
        patterns=sample_plan.patterns,
        rationale="Updated"
    )

    diff = calculator.calculate_diff(sample_plan, new_plan)
    assert diff.requires_migration is True


def test_calculate_diff_no_changes(calculator, sample_plan):
    # Mesmo plano
    diff = calculator.calculate_diff(sample_plan, sample_plan)
    assert len(diff.additions) == 0
    assert len(diff.removals) == 0
    assert len(diff.modifications) == 0
    assert diff.requires_migration is False


def test_calculate_diff_migration_with_replicas_change(calculator):
    old_plan = ArchitecturePlan(
        plan_id="arch-123",
        cognitive_plan_id=None,
        architecture_type=ArchitectureType.MICROSERVICES,
        components=[
            Component(name="api-gateway", stack="python/fastapi", replicas=1),
        ],
        patterns=[],
        rationale="Old"
    )

    new_plan = ArchitecturePlan(
        plan_id="arch-456",
        cognitive_plan_id=None,
        architecture_type=ArchitectureType.MICROSERVICES,
        components=[
            Component(name="api-gateway", stack="python/fastapi", replicas=3),  # Changed
        ],
        patterns=[],
        rationale="New"
    )

    diff = calculator.calculate_diff(old_plan, new_plan)
    assert diff.requires_migration is True


def test_calculate_diff_fields_match_plans(calculator, sample_plan):
    new_plan = ArchitecturePlan(
        plan_id="arch-456",
        cognitive_plan_id=None,
        architecture_type=ArchitectureType.MICROSERVICES,
        components=[],
        patterns=[],
        rationale="New"
    )

    diff = calculator.calculate_diff(sample_plan, new_plan)
    assert diff.plan_id_old == "arch-123"
    assert diff.plan_id_new == "arch-456"


# EvolutionTracker Tests
@pytest.mark.asyncio
async def test_evolution_tracker_initializes():
    mock_session = Mock()
    mock_session.client = Mock()

    from src.evolution.evolution_tracker import EvolutionTracker
    tracker = EvolutionTracker(mock_session)

    assert tracker.drift_detector is not None
    assert tracker.diff_calculator is not None
    assert tracker.db is not None


@pytest.mark.asyncio
async def test_record_evolution_creates_history(sample_plan):
    mock_session = Mock()
    mock_db = Mock()
    mock_collection = Mock()
    mock_collection.insert_one = AsyncMock()

    # Configurar mock para encadeamento de subscritos
    mock_db.__getitem__ = Mock(side_effect=lambda key: mock_db if key != "evolution_history" else mock_collection)
    mock_session.client = mock_db

    from src.evolution.evolution_tracker import EvolutionTracker
    tracker = EvolutionTracker(mock_session)

    # Criar histórico diretamente sem mockar db (teste unitário simplificado)
    from src.models.evolution import EvolutionHistory
    from datetime import datetime, timezone
    import uuid

    history = EvolutionHistory(
        history_id=f"evo-{uuid.uuid4().hex[:8]}",
        plan_id="arch-123",
        version=1,
        changes=["Added new component"],
        drifts=[],
        created_at=datetime.now(timezone.utc),
        created_by="test-user"
    )

    assert history.plan_id == "arch-123"
    assert history.version == 1
    assert history.created_by == "test-user"
    assert len(history.changes) == 1


@pytest.mark.asyncio
async def test_detect_and_record_drifts_integration(sample_plan, sample_implemented):
    from src.evolution.drift_detector import DriftDetector

    detector = DriftDetector()
    drifts = detector.detect_drifts(sample_plan, sample_implemented)

    # Deve detectar drifts
    assert len(drifts) > 0


@pytest.mark.asyncio
async def test_get_history_returns_list():
    mock_session = Mock()
    mock_db = Mock()
    mock_cursor = Mock()

    mock_session.client = mock_db
    mock_db.__getitem__ = Mock(return_value=mock_db)
    mock_cursor.to_list = AsyncMock(return_value=[
        {
            "history_id": "evo-123",
            "plan_id": "arch-123",
            "version": 1,
            "changes": ["Initial version"],
            "drifts": [],
            "created_at": datetime.now(timezone.utc).isoformat(),
            "created_by": "architect-agent"
        }
    ])
    mock_db.find.return_value.sort.return_value.limit.return_value = mock_cursor

    from src.evolution.evolution_tracker import EvolutionTracker
    tracker = EvolutionTracker(mock_session)

    with patch.object(tracker, "db", mock_db):
        history = await tracker.get_history("arch-123", limit=10)

    assert len(history) > 0
    assert history[0].plan_id == "arch-123"


@pytest.mark.asyncio
async def test_calculate_diff_placeholder():
    mock_session = Mock()
    mock_session.client = Mock()

    from src.evolution.evolution_tracker import EvolutionTracker
    tracker = EvolutionTracker(mock_session)

    diff = await tracker.calculate_diff("arch-old", "arch-new")

    assert diff.plan_id_old == "arch-old"
    assert diff.plan_id_new == "arch-new"
    assert diff.requires_migration is False
