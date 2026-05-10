"""Observability primitives for the Unified Gateway.

Exposes Prometheus metrics that the runbook (`docs/runbooks/
TROUBLESHOOTING.md`) lists as key SLO indicators. The default
``prometheus_client`` registry is used so that ``main.py``'s
``make_asgi_app()`` mount on ``/metrics`` exposes them automatically.
"""

from .metrics import (
    classification_confidence,
    classification_total,
    nlu_fallback_total,
    rate_limit_exceeded_total,
    record_classification,
    record_nlu_fallback,
    record_rate_limit_exceeded,
    record_request,
    requests_total,
    request_latency_seconds,
)

__all__ = [
    "classification_confidence",
    "classification_total",
    "nlu_fallback_total",
    "rate_limit_exceeded_total",
    "record_classification",
    "record_nlu_fallback",
    "record_rate_limit_exceeded",
    "record_request",
    "requests_total",
    "request_latency_seconds",
]
