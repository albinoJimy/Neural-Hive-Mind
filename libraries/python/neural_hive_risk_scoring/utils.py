"""
Utility functions for neural_hive_risk_scoring
"""

from typing import Union
from neural_hive_domain import UnifiedDomain


def get_domain_value(domain: Union[UnifiedDomain, str]) -> str:
    """Retorna valor string do domínio, lidando com enum ou string.

    Args:
        domain: UnifiedDomain ou string

    Returns:
        String do valor do domínio
    """
    return domain if isinstance(domain, str) else domain.value


def get_domain_enum(domain: Union[UnifiedDomain, str]) -> UnifiedDomain:
    """Retorna UnifiedDomain a partir de enum ou string.

    Args:
        domain: UnifiedDomain ou string

    Returns:
        Instância de UnifiedDomain
    """
    if isinstance(domain, UnifiedDomain):
        return domain
    return UnifiedDomain(domain)
