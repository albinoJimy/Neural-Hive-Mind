"""Helpers de tracing OpenTelemetry para Guard Agents"""
from functools import wraps
from typing import Callable, Any
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode
import structlog

logger = structlog.get_logger()
tracer = trace.get_tracer(__name__)


def trace_incident_flow(span_name: str):
    """
    Decorator para tracear operações do fluxo de incidentes (E1-E6)

    Usage:
        @trace_incident_flow("e1_detect_anomaly")
        async def detect_anomaly(event):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            with tracer.start_as_current_span(span_name) as span:
                try:
                    # Adicionar atributos úteis ao span
                    if args and hasattr(args[0], '__dict__'):
                        # Se primeiro argumento é self, pegar nome da classe
                        span.set_attribute("component", args[0].__class__.__name__)

                    # Executar função
                    result = await func(*args, **kwargs)

                    # Adicionar atributos de resultado
                    if isinstance(result, dict):
                        if 'incident_id' in result:
                            span.set_attribute("incident_id", result['incident_id'])
                        if 'severity' in result:
                            span.set_attribute("severity", result['severity'])
                        if 'success' in result:
                            span.set_attribute("success", result['success'])

                    span.set_status(Status(StatusCode.OK))
                    return result

                except Exception as e:
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    span.record_exception(e)
                    raise

        return wrapper
    return decorator


def add_incident_context_to_span(
    incident_id: str = None,
    threat_type: str = None,
    severity: str = None,
    runbook_id: str = None
):
    """Adiciona contexto de incidente ao span atual"""
    span = trace.get_current_span()

    if span:
        if incident_id:
            span.set_attribute("incident.id", incident_id)
        if threat_type:
            span.set_attribute("incident.threat_type", threat_type)
        if severity:
            span.set_attribute("incident.severity", severity)
        if runbook_id:
            span.set_attribute("incident.runbook_id", runbook_id)


def add_sla_metrics_to_span(mttd: float = None, mttr: float = None, sla_met: bool = None):
    """Adiciona métricas de SLA ao span atual"""
    span = trace.get_current_span()

    if span:
        if mttd is not None:
            span.set_attribute("sla.mttd_seconds", mttd)
        if mttr is not None:
            span.set_attribute("sla.mttr_seconds", mttr)
        if sla_met is not None:
            span.set_attribute("sla.met", sla_met)


def add_remediation_context_to_span(
    remediation_id: str = None,
    playbook: str = None,
    status: str = None,
    actions_count: int = None
):
    """Adiciona contexto de remediação ao span atual"""
    span = trace.get_current_span()

    if span:
        if remediation_id:
            span.set_attribute("remediation.id", remediation_id)
        if playbook:
            span.set_attribute("remediation.playbook", playbook)
        if status:
            span.set_attribute("remediation.status", status)
        if actions_count is not None:
            span.set_attribute("remediation.actions_count", actions_count)


class TracingHelper:
    """Helper centralizado para tracing de operações"""

    @staticmethod
    def create_span(name: str, attributes: dict = None):
        """Cria novo span com atributos opcionais"""
        span = tracer.start_span(name)

        if attributes:
            for key, value in attributes.items():
                span.set_attribute(key, value)

        return span

    @staticmethod
    def add_event(name: str, attributes: dict = None):
        """Adiciona evento ao span atual"""
        span = trace.get_current_span()

        if span:
            span.add_event(name, attributes or {})

    @staticmethod
    def record_exception(exception: Exception):
        """Registra exceção no span atual"""
        span = trace.get_current_span()

        if span:
            span.record_exception(exception)
            span.set_status(Status(StatusCode.ERROR, str(exception)))
