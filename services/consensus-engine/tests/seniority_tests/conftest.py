"""
Minimal conftest for seniority tests.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock
from enum import Enum

# Mock neural_hive_domain BEFORE any imports
class UnifiedDomain(str, Enum):
    BUSINESS = 'BUSINESS'
    TECHNICAL = 'TECHNICAL'
    ARCHITECTURE = 'ARCHITECTURE'

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
