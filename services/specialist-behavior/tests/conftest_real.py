"""
Configuração pytest para specialist-behavior com código REAL.

Este conftest é usado pelos testes que importam código real de src/.
"""

import sys
import os
import pytest
from unittest.mock import MagicMock

# Configurar paths para importação
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, "/app/libraries/python")


@pytest.fixture(scope="session")
def mock_env_vars():
    """Configura variáveis de ambiente para testes."""
    original_env = os.environ.copy()

    # Set required environment variables
    os.environ.update(
        {
            "ENVIRONMENT": "test",
            "LOG_LEVEL": "DEBUG",
            "MLFLOW_TRACKING_URI": "http://localhost:5000",
            "MONGODB_URI": "mongodb://localhost:27017/test",
            "REDIS_CLUSTER_NODES": "localhost:6379",
            "NEO4J_URI": "bolt://localhost:7687",
            "NEO4J_PASSWORD": "test_password",
            "JWT_SECRET_KEY": "test_secret_key_for_testing_only",
            "ENABLE_JWT_AUTH": "false",
            "ENABLE_CACHING": "false",
            "ENABLE_LEDGER": "false",
            "MODEL_REQUIRED": "false",
            "ENABLE_FEEDBACK_COLLECTION": "false",
            "FEEDBACK_API_ENABLED": "false",
            "ENABLE_PII_DETECTION": "false",
            "HTTP_PORT": "8001",
            "GRPC_PORT": "50051",
            "PROMETHEUS_PORT": "8002",
        }
    )

    yield

    # Restore original environment
    os.environ.clear()
    os.environ.update(original_env)


@pytest.fixture
def real_config(mock_env_vars):
    """Configuração real do BehaviorSpecialistConfig."""
    from src.config import BehaviorSpecialistConfig

    return BehaviorSpecialistConfig()


@pytest.fixture
def mock_mlflow_client():
    """Mock do cliente MLflow."""
    mock_client = MagicMock()
    mock_client._enabled = False
    return mock_client


@pytest.fixture
def mock_ledger_client():
    """Mock do cliente Ledger."""
    mock_client = MagicMock()
    mock_client.check_health.return_value = {"status": "healthy"}
    return mock_client


@pytest.fixture
def real_specialist(real_config, mock_mlflow_client, mock_ledger_client):
    """Instância real do BehaviorSpecialist."""
    from src.specialist import BehaviorSpecialist

    with patch("neural_hive_specialists.BaseSpecialist.__init__", return_value=None):
        with patch("src.specialist.structlog.get_logger"):
            specialist = BehaviorSpecialist(real_config)
            specialist.config = real_config
            specialist.specialist_type = "behavior"
            specialist.version = "1.0.0"
            specialist.mlflow_client = mock_mlflow_client
            specialist.ledger_client = mock_ledger_client
            specialist._model = None
            specialist.metrics = MagicMock()
            return specialist


@pytest.fixture
def sample_cognitive_plan():
    """Plano cognitivo de exemplo."""
    return {
        "plan_id": "behavior-plan-123",
        "original_domain": "ui-design",
        "original_priority": "high",
        "description": "Design intuitive user interface",
        "tasks": [
            {
                "task_id": "task-1",
                "description": "Design intuitive user interface",
                "dependencies": [],
                "estimated_duration_ms": 200,
            },
            {
                "task_id": "task-2",
                "description": "Ensure WCAG AA accessibility compliance",
                "dependencies": ["task-1"],
                "estimated_duration_ms": 300,
            },
            {
                "task_id": "task-3",
                "description": "Optimize response time for user actions",
                "dependencies": [],
                "estimated_duration_ms": 150,
            },
        ],
    }


# Import patch after defining fixtures
from unittest.mock import patch
