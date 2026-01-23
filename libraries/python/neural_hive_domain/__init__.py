"""Neural Hive Domain - Unified domain definitions for the Neural Hive Mind system.

This library provides centralized domain definitions and mapping utilities
to ensure consistency across all components of the Neural Hive Mind system.

Example usage:
    from neural_hive_domain import UnifiedDomain, DomainMapper

    # Use the unified domain enum
    domain = UnifiedDomain.SECURITY

    # Normalize domains from different sources
    normalized = DomainMapper.normalize('business', 'intent_envelope')

    # Generate standardized Redis pheromone keys
    key = DomainMapper.to_pheromone_key(
        domain=UnifiedDomain.BUSINESS,
        layer='strategic',
        pheromone_type='SUCCESS',
        id='uuid-123'
    )
"""

from .domain import UnifiedDomain
from .mapper import DomainMapper

__version__ = '1.0.0'
__all__ = ['UnifiedDomain', 'DomainMapper']
