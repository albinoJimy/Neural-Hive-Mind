"""
API Module for Orchestrator Dynamic.

Este módulo contém os routers e endpoints da API REST.
"""

from .model_audit import create_model_audit_router

__all__ = ['create_model_audit_router']
