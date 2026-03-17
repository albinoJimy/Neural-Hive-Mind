import sys
from unittest.mock import MagicMock
from enum import Enum

class UnifiedDomain(str, Enum):
    BUSINESS = 'BUSINESS'
    TECHNICAL = 'TECHNICAL'

class DomainMapper:
    @staticmethod
    def normalize(domain_str, context):
        return UnifiedDomain.BUSINESS

sys.modules['neural_hive_domain'] = MagicMock()
sys.modules['neural_hive_domain'].UnifiedDomain = UnifiedDomain
sys.modules['neural_hive_domain'].DomainMapper = DomainMapper

mock_observability = MagicMock()
mock_observability.get_tracer = MagicMock()
sys.modules['neural_hive_observability'] = mock_observability
