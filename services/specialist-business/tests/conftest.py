"""Configuração pytest para specialist-business."""

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
    config.specialist_id = "test-business-specialist"
    config.domain = "BUSINESS"
    config.mlflow_tracking_uri = "http://localhost:5000"
    config.model_name = "specialist_business_model"
    config.mlflow_model_name = "specialist_business_model"
    config.mlflow_model_stage = "Production"
    config.enable_caching = False
    config.enable_ledger = False
    config.ledger_required = False
    return config


@pytest.fixture
def sample_cognitive_plan():
    """Plano cognitivo de exemplo."""
    return {
        "plan_id": "plan-789",
        "original_domain": "business-process-automation",
        "original_priority": "high",
        "description": "Automate customer onboarding to improve conversion and reduce time",
        "tasks": [
            {
                "task_id": "task-1",
                "description": "Design efficient workflow with parallel processing",
                "dependencies": [],
                "estimated_duration_ms": 20000,
            },
            {
                "task_id": "task-2",
                "description": "Implement KPI tracking for conversion metrics",
                "dependencies": ["task-1"],
                "estimated_duration_ms": 30000,
            },
            {
                "task_id": "task-3",
                "description": "Optimize cost-effective implementation",
                "dependencies": ["task-2"],
                "estimated_duration_ms": 25000,
            },
        ],
    }
