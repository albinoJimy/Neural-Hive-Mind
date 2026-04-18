"""Routers do Requirements Engineering Service."""

from .api_design import router as api_design_router
from .requirements import router as requirements_router
from .ui_ux_design import router as ui_ux_design_router

__all__ = [
    "api_design_router",
    "requirements_router",
    "ui_ux_design_router",
]
