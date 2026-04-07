"""Configuração pytest para specialist-evolution."""

import sys
import os
import pytest
from unittest.mock import MagicMock

# Adicionar paths para importação
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, "/app/libraries/python")


@pytest.fixture
def mock_specialist_config():
    """Configuração mock do especialista."""
    config = MagicMock()
    config.specialist_id = "test-evolution-specialist"
    config.domain = "EVOLUTION"
    config.mlflow_tracking_uri = "http://localhost:5000"
    config.model_name = "specialist_evolution_model"
    config.mlflow_model_name = "specialist_evolution_model"
    config.mlflow_model_stage = "Production"
    config.evolution_hooks_enabled = False
    config.evolution_hooks_min_similar_patterns = 5
    config.evolution_hooks_max_adjustment = 0.05
    config.evolution_hooks_pattern_registry_db = "neural_hive"
    config.enable_caching = False
    config.enable_ledger = False
    config.ledger_required = False
    return config


@pytest.fixture
def sample_cognitive_plan():
    """Plano cognitivo de exemplo."""
    return {
        "plan_id": "evolution-plan-123",
        "original_domain": "software-evolution",
        "original_priority": "high",
        "tasks": [
            {
                "task_id": "task-1",
                "name": "Create service module",
                "task_type": "service",
                "description": "Design modular service with clear responsibility",
                "dependencies": [],
                "estimated_duration_ms": 5000,
            },
            {
                "task_id": "task-2",
                "name": "Add repository",
                "task_type": "data",
                "description": "Implement repository pattern for data access",
                "dependencies": ["task-1"],
                "estimated_duration_ms": 4000,
            },
            {
                "task_id": "task-3",
                "name": "Unit tests",
                "task_type": "testing",
                "description": "Write unit tests for all modules",
                "dependencies": ["task-2"],
                "estimated_duration_ms": 6000,
            },
        ],
    }
