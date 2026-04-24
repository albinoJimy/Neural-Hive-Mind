"""
Sistema de Notificações do Orchestrator Dynamic.

Este módulo fornece notificações multi-canal para eventos críticos do sistema,
incluindo drift detection, retrain triggers e status de modelos ML.

FASE 0 - IA/ML Integration - EPIC 3.5
"""

from .config import (
    NotificationConfig,
    NotificationPriority,
    NotificationTemplate,
)
from .notifier import (
    BaseNotifier,
    EmailNotifier,
    NotificationManager,
    NotificationResult,
    SlackNotifier,
)

__all__ = [
    "NotificationConfig",
    "NotificationPriority",
    "NotificationTemplate",
    "BaseNotifier",
    "EmailNotifier",
    "NotificationManager",
    "NotificationResult",
    "SlackNotifier",
]
