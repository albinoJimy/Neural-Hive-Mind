"""Configuração pytest para specialist-architecture."""

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
    config.specialist_id = "test-architecture-specialist"
    config.domain = "ARCHITECTURE"
    config.mlflow_tracking_uri = "http://localhost:5000"
    config.model_name = "specialist_architecture_model"
    config.mlflow_model_name = "specialist_architecture_model"
    config.mlflow_model_stage = "Production"
    config.coupling_threshold_high = 0.7
    config.enable_caching = False
    config.enable_ledger = False
    config.ledger_required = False
    return config


@pytest.fixture
def sample_cognitive_plan():
    """Plano cognitivo de exemplo."""
    return {
        'plan_id': 'arch-plan-123',
        'original_domain': 'architecture-design',
        'original_priority': 'high',
        'tasks': [
            {
                'task_id': 'task-1',
                'description': 'Implement factory pattern for object creation',
                'dependencies': [],
                'agent_id': 'service-a',
                'estimated_duration_ms': 25000
            },
            {
                'task_id': 'task-2',
                'description': 'Apply single responsibility principle to controller',
                'dependencies': ['task-1'],
                'agent_id': 'service-a',
                'estimated_duration_ms': 30000
            },
            {
                'task_id': 'task-3',
                'description': 'Add repository pattern for data access',
                'dependencies': [],
                'agent_id': 'service-b',
                'estimated_duration_ms': 20000
            }
        ]
    }
