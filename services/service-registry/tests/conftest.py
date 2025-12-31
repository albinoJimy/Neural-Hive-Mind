"""
Pytest configuration and shared fixtures for service-registry tests.
"""

import pytest
import sys
import os

# Adicionar src ao path para importação
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../src'))


@pytest.fixture
def mock_grpc_context():
    """Mock básico para gRPC context"""
    from unittest.mock import Mock
    context = Mock()
    context.abort = Mock()
    context.invocation_metadata = Mock(return_value=[])
    return context
