"""
Integrações do Orchestrator Dynamic com serviços externos.

Este módulo contém wrappers e clientes para integração com:
- OPA (Open Policy Agent)
- Feature Flags (Redis + OPA)
- Outros serviços de infraestrutura
"""
from src.integrations.opa_feature_flags import OPAFeatureFlagsClient

__all__ = ["OPAFeatureFlagsClient"]
