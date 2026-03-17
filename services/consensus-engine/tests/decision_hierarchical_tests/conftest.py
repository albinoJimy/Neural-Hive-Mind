"""
Minimal conftest for hierarchical decision model tests.
Avoids external dependencies like neural_hive_specialists.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock
from enum import Enum

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

# Mock neural_hive_observability
mock_observability = MagicMock()
mock_tracer = MagicMock()
mock_tracer.start_as_current_span = MagicMock()
mock_observability.get_tracer = MagicMock(return_value=mock_tracer)
sys.modules['neural_hive_observability'] = mock_observability

# Add src to path
src_path = Path(__file__).parent.parent.parent / 'src'
sys.path.insert(0, str(src_path))
