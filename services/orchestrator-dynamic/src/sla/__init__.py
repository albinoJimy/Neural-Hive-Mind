"""
Módulo de Monitoramento Proativo de SLA

Este módulo fornece monitoramento em tempo real de SLA para workflows do Orchestrator Dynamic,
integrando com o SLA Management System para verificação de budgets e deadlines.

Componentes principais:
- SLAMonitor: Verifica deadlines e consulta error budgets
- AlertManager: Publica alertas proativos e eventos de violação
"""

from src.sla.alert_manager import AlertManager
from src.sla.sla_monitor import SLAMonitor

__all__ = ["AlertManager", "SLAMonitor"]
