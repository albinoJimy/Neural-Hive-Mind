"""
Neural Hive OPA - Open Policy Agent integration library.

Provides middleware for FastAPI applications to enforce authorization
policies via Open Policy Agent (OPA).
"""

from neural_hive_opa.client import OPAClient, OPARequestOptions
from neural_hive_opa.middleware import (
    OPAAuthorizationMiddleware,
    OPAMiddlewareConfig,
)

__all__ = [
    "OPAClient",
    "OPARequestOptions",
    "OPAAuthorizationMiddleware",
    "OPAMiddlewareConfig",
]

__version__ = "0.1.0"
