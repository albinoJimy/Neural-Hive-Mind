"""
API package for Explainability API.
"""

from fastapi import APIRouter
from .routes.v3 import hierarchical

__all__ = ["hierarchical"]
