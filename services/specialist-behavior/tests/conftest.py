"""Configuração pytest para specialist-behavior."""

import sys
import os
import pytest
from unittest.mock import MagicMock

# Adicionar paths para importação
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
sys.path.insert(0, '/app/libraries/python')


@pytest.fixture
def mock_specialist_config():
    """Configuração mock do especialista."""
    config = MagicMock()
    config.specialist_id = "test-behavior-specialist"
    config.domain = "BEHAVIOR"
    config.mlflow_tracking_uri = "http://localhost:5000"
    config.model_name = "specialist_behavior_model"
    config.mlflow_model_name = "specialist_behavior_model"
    config.mlflow_model_stage = "Production"
    config.enable_caching = False
    config.enable_ledger = False
    config.ledger_required = False
    return config


@pytest.fixture
def sample_cognitive_plan():
    """Plano cognitivo de exemplo."""
    return {
        'plan_id': 'behavior-plan-123',
        'original_domain': 'ui-design',
        'original_priority': 'high',
        'tasks': [
            {
                'task_id': 'task-1',
                'description': 'Design intuitive user interface',
                'dependencies': [],
                'estimated_duration_ms': 200
            },
            {
                'task_id': 'task-2',
                'description': 'Ensure WCAG AA accessibility compliance',
                'dependencies': ['task-1'],
                'estimated_duration_ms': 300
            },
            {
                'task_id': 'task-3',
                'description': 'Optimize response time for user actions',
                'dependencies': [],
                'estimated_duration_ms': 150
            }
        ]
    }

