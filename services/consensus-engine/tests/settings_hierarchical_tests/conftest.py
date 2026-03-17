"""
Minimal conftest for hierarchical settings tests.
Avoids external dependencies.
"""

import sys
import os
from pathlib import Path
from unittest.mock import MagicMock
from enum import Enum
import pytest

# Mock neural_hive_domain BEFORE any imports
class UnifiedDomain(str, Enum):
    BUSINESS = 'BUSINESS'
    TECHNICAL = 'TECHNICAL'
    SECURITY = 'SECURITY'
    ARCHITECTURE = 'ARCHITECTURE'
    BEHAVIOR = 'BEHAVIOR'
    INFRASTRUCTURE = 'INFRASTRUCTURE'
    OPERATIONAL = 'OPERATIONAL'
    COMPLIANCE = 'COMPLIANCE'

class DomainMapper:
    @staticmethod
    def normalize(domain_str, context):
        return UnifiedDomain.BUSINESS

sys.modules['neural_hive_domain'] = MagicMock()
sys.modules['neural_hive_domain'].UnifiedDomain = UnifiedDomain
sys.modules['neural_hive_domain'].DomainMapper = DomainMapper

# Add src to path
src_path = Path(__file__).parent.parent.parent / 'src'
sys.path.insert(0, str(src_path))


@pytest.fixture(autouse=True)
def clear_settings_and_env(monkeypatch):
    """Clear Settings singleton and env vars before each test."""
    # Clear hierarchical env vars
    hierarchical_vars = [
        'ENABLE_HIERARCHICAL_CONSENSUS',
        'SPECIALIST_SENIORITY',
        'DEFAULT_SENIORITY_LEVEL',
        'DOMAIN_SPECIALIST_WEIGHTS',
    ]
    for var in hierarchical_vars:
        monkeypatch.delenv(var, raising=False)

    # Clear the Settings singleton
    import src.config.settings as settings_module
    settings_module._settings = None

    yield
