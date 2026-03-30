"""Configuração pytest para specialist-technical."""

import sys
import os
import pytest
from unittest.mock import MagicMock, AsyncMock

# Adicionar paths para importação
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
sys.path.insert(0, '/app/libraries/python')


@pytest.fixture
def mock_specialist_config():
    """Configuração mock do especialista."""
    config = MagicMock()
    config.specialist_id = "test-technical-specialist"
    config.domain = "TECHNICAL"
    config.mlflow_tracking_uri = "http://localhost:5000"
    config.model_name = "specialist_technical_model"
    config.mlflow_model_name = "specialist_technical_model"
    config.mlflow_model_stage = "Production"
    config.enable_caching = False
    config.enable_ledger = False
    config.ledger_required = False
    return config


@pytest.fixture
def mock_mlflow_client():
    """Cliente MLflow mock."""
    client = MagicMock()
    client._enabled = True
    client.predict = MagicMock(return_value={"recommendation": True, "confidence": 0.8})
    client.load_model_with_fallback = MagicMock(return_value=MagicMock())
    client.get_model_metadata = MagicMock(return_value={'version': 'v1.0.0'})
    return client


@pytest.fixture
def sample_cognitive_plan():
    """Plano cognitivo de exemplo."""
    return {
        'plan_id': 'plan-123',
        'original_domain': 'api-development',
        'original_priority': 'high',
        'tasks': [
            {
                'task_id': 'task-1',
                'description': 'Implement authentication with JWT token validation',
                'dependencies': [],
                'estimated_duration_ms': 30000
            },
            {
                'task_id': 'task-2',
                'description': 'Create user controller with input validation',
                'dependencies': ['task-1'],
                'estimated_duration_ms': 45000
            },
            {
                'task_id': 'task-3',
                'description': 'Add unit tests for all endpoints',
                'dependencies': ['task-2'],
                'estimated_duration_ms': 60000
            },
            {
                'task_id': 'task-4',
                'description': 'Implement caching layer with Redis',
                'dependencies': [],
                'estimated_duration_ms': 20000
            }
        ]
    }


@pytest.fixture
def sample_opinion():
    """Opinião de especialista de exemplo."""
    return {
        'specialist_id': 'technical-specialist',
        'specialist_type': 'technical',
        'plan_id': 'plan-123',
        'confidence_score': 0.78,
        'risk_score': 0.22,
        'recommendation': 'approve',
        'reasoning_summary': 'Technical evaluation passed',
        'reasoning_factors': [],
        'mitigations': []
    }
