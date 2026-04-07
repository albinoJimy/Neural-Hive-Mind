"""
Configuration file for pytest.

Fixes import path for the src module.
"""

import sys
from pathlib import Path

# Add the parent directory to sys.path so we can import src
# This allows tests to run with 'from src.xxx import yyy'
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import pytest
from unittest.mock import AsyncMock, MagicMock, Mock
from datetime import datetime, timezone
from uuid import uuid4


@pytest.fixture
def mock_settings():
    """Mock settings for testing."""
    settings = Mock()
    settings.ab_test_min_sample_size = 100
    settings.ab_test_default_alpha = 0.05
    settings.ab_test_default_power = 0.80
    settings.max_weight_adjustment = 0.5
    settings.experiment_timeout_seconds = 3600
    return settings


@pytest.fixture
def mock_mongodb_client():
    """Mock MongoDB client for testing."""
    client = AsyncMock()
    client.save_experiment = AsyncMock(return_value=True)
    client.get_experiment = AsyncMock(return_value=None)
    client.update_experiment_status = AsyncMock(return_value=True)
    client.list_experiments = AsyncMock(return_value=[])
    return client


@pytest.fixture
def mock_redis_client():
    """Mock Redis client for testing."""
    client = AsyncMock()
    client.lock_component = AsyncMock(return_value=True)
    client.unlock_component = AsyncMock(return_value=True)
    client.keys = AsyncMock(return_value=[])
    client.get = AsyncMock(return_value=None)
    client.lrange = AsyncMock(return_value=[])
    client.set = AsyncMock(return_value=True)
    return client


@pytest.fixture
def mock_argo_client():
    """Mock Argo client for testing."""
    client = AsyncMock()
    client.submit_experiment_workflow = AsyncMock(return_value="workflow-test-001")
    client.get_workflow_status = AsyncMock(return_value="Running")
    client.get_workflow_results = AsyncMock(return_value={})
    client.delete_workflow = AsyncMock(return_value=True)
    return client


@pytest.fixture
def mock_consensus_engine_client():
    """Mock Consensus Engine gRPC client for testing."""
    client = AsyncMock()
    client.rollback_weights = AsyncMock(return_value=True)
    return client


@pytest.fixture
def mock_orchestrator_client():
    """Mock Orchestrator gRPC client for testing."""
    client = AsyncMock()
    client.rollback_slos = AsyncMock(return_value=True)
    return client


@pytest.fixture
def sample_optimization_hypothesis():
    """Sample optimization hypothesis for testing."""
    from src.models.optimization_hypothesis import (
        OptimizationHypothesis,
        OptimizationType,
        ProposedAdjustment,
    )

    return OptimizationHypothesis(
        hypothesis_id=str(uuid4()),
        hypothesis_text="Reduce latency by adjusting consensus weights",
        optimization_type=OptimizationType.WEIGHT_RECALIBRATION,
        target_component="consensus-engine",
        baseline_metrics={"latency_p95": 200.0, "error_rate": 0.01, "throughput": 1000.0},
        target_metrics={"latency_p95": 150.0, "error_rate": 0.01},
        proposed_adjustments=[
            ProposedAdjustment(
                parameter_name="business_weight",
                old_value="0.25",
                new_value="0.30",
                previous_value=0.25,
            ),
            ProposedAdjustment(
                parameter_name="technical_weight",
                old_value="0.25",
                new_value="0.20",
                previous_value=0.25,
            ),
        ],
        expected_improvement=0.25,
        confidence_score=0.85,
        risk_score=0.3,
        priority=3,
        metadata={"created_by": "optimizer-agents", "context_id": "test-context-001"},
    )


@pytest.fixture
def sample_code_recommendation():
    """Sample code optimization recommendation for testing."""
    return {
        "id": "code-opt-001",
        "type": "code",
        "target_type": "code",
        "file_path": "services/consensus-engine/src/services/consensus_orchestrator.py",
        "severity": "low",
        "auto_apply": True,
        "code_diff": """--- a/services/consensus-engine/src/services/consensus_orchestrator.py
+++ b/services/consensus-engine/src/services/consensus_orchestrator.py
@@ -150,7 +150,7 @@
         # Cache weights for performance
         self._weights_cache = {}
-        self._cache_ttl = 300  # 5 minutes
+        self._cache_ttl = 600  # 10 minutes
         self._last_cache_update = None
""",
        "description": "Increase weights cache TTL for better performance",
    }


@pytest.fixture
def sample_database_recommendation():
    """Sample database optimization recommendation for testing."""
    return {
        "id": "db-opt-001",
        "type": "index",
        "target_type": "mongodb",
        "file_path": "plan_approvals",
        "severity": "medium",
        "auto_apply": False,
        "query_suggestion": "db.plan_approvals.createIndex({created_at: 1, status: 1})",
        "description": "Add compound index for status queries",
    }


@pytest.fixture
def sample_unsafe_recommendation():
    """Sample unsafe recommendation (test file) for testing."""
    return {
        "id": "unsafe-opt-001",
        "type": "code",
        "target_type": "code",
        "file_path": "services/consensus-engine/tests/test_consensus.py",
        "severity": "low",
        "auto_apply": True,
        "code_diff": "--- a/test.py\n+++ b/test.py\n@@ -1,1 +1,1 @@\n-old\n+new\n",
        "description": "Should be blocked by safety check",
    }


@pytest.fixture
def sample_critical_recommendation():
    """Sample critical recommendation for testing."""
    return {
        "id": "critical-opt-001",
        "type": "code",
        "target_type": "code",
        "file_path": "services/gateway/src/main.py",
        "severity": "critical",
        "auto_apply": True,
        "code_diff": "--- a/main.py\n+++ b/main.py\n@@ -1,1 +1,1 @@\n-old\n+new\n",
        "description": "Critical change requiring manual review",
    }


@pytest.fixture
def sample_experiment_request():
    """Sample experiment request for testing."""
    from src.models.experiment_request import (
        ExperimentRequest,
        ExperimentType,
        RandomizationStrategy,
    )

    return ExperimentRequest(
        experiment_id=str(uuid4()),
        correlation_id="test-correlation-001",
        trace_id="test-trace-001",
        span_id="test-span-001",
        hypothesis="Test hypothesis for latency improvement",
        objective="Validate weight recalibration for consensus-engine",
        experiment_type=ExperimentType.A_B_TEST,
        target_component="consensus-engine",
        baseline_configuration={"latency_p95": "200.0"},
        experimental_configuration={"business_weight": "0.30"},
        success_criteria=[
            {
                "metric_name": "latency_p95",
                "operator": "LTE",
                "threshold": 150.0,
                "confidence_level": 0.95,
            }
        ],
        guardrails=[
            {
                "metric_name": "error_rate",
                "max_degradation_percentage": 0.05,
                "abort_threshold": 0.10,
            }
        ],
        traffic_percentage=0.1,
        duration_seconds=3600,
        sample_size=500,
        randomization_strategy=RandomizationStrategy.RANDOM,
        ethical_approval_required=False,
        rollback_on_failure=True,
        created_at=int(datetime.now(timezone.utc).timestamp() * 1000),
        created_by="optimizer-agents",
    )


@pytest.fixture
def sample_ab_test_config():
    """Sample A/B test configuration for testing."""
    return {
        "name": "test-ab-001",
        "hypothesis": "Test hypothesis",
        "primary_metrics": ["latency_p95", "error_rate"],
        "traffic_split": 0.5,
        "minimum_sample_size": 500,
        "maximum_duration_seconds": 3600,
        "early_stopping_enabled": True,
        "bayesian_analysis_enabled": True,
    }
