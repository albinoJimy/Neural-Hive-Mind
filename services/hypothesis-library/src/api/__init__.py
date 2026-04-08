"""API module."""

from src.api.router import api_router
from src.api.views import (
    health_handler,
    metrics_handler,
    root_handler,
)

__all__ = [
    "api_router",
    "health_handler",
    "metrics_handler",
    "root_handler",
]
