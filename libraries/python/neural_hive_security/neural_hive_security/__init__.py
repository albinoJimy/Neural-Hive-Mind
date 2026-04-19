"""
Neural Hive Mind - Security Library

Biblioteca centralizada para configurações de segurança em todos os serviços.
Inclui CORS, rate limiting, validação de headers e outros controles de segurança.
"""

__version__ = "0.1.0"
__author__ = "Neural Hive Mind Team"

from .cors import CORSConfig
from .security_headers import (
    SecurityHeadersConfig,
    SecurityHeadersMiddleware,
    add_security_headers,
)

__all__ = [
    "CORSConfig",
    "SecurityHeadersConfig",
    "SecurityHeadersMiddleware",
    "add_security_headers",
]
