"""Prometheus metric definitions for the Unified Gateway.

The naming convention mirrors what the runbook
(`docs/runbooks/TROUBLESHOOTING.md`) describes as the key SLO signals:
``unified_gateway_*``. Metrics use the default global registry so
``prometheus_client.make_asgi_app()`` (mounted at ``/metrics`` by
``main.py``) picks them up without extra wiring.

Only stable, low-cardinality labels are used:
- ``method``: HTTP verb (GET, POST, ...).
- ``path_template``: a normalised path token (``"/api/v1/nhm/request"``,
  ``"/api/v1/nhm/status/{id}"``); raw path strings would explode
  cardinality on any path-parameter endpoint.
- ``status_code``: response code as integer string.
- ``flow_type``: ``"A-F"`` / ``"G"`` / ``"H"``.
- ``tenant_id``: only emitted on ``rate_limit_exceeded_total`` and
  truncated to first 32 chars to bound cardinality.
- ``service``: ``"nlu"`` for the NLU fallback counter (kept generic so
  PII/other fallbacks can reuse the same metric in the future).
"""

from __future__ import annotations

from typing import Any

from prometheus_client import REGISTRY, Counter, Histogram

# ---------------------------------------------------------------------------
# Idempotent factory helpers
# ---------------------------------------------------------------------------
# O `prometheus_client.REGISTRY` é um singleton global; tentar registar
# duas vezes a mesma métrica levanta ``ValueError``. Nas suites de teste
# o módulo ``src.observability.metrics`` pode ser re-importado quando os
# fixtures fazem ``sys.modules`` purge para isolar as apps unified-gateway
# e pii-service. Os helpers abaixo garantem que cada métrica é criada
# uma única vez por nome, devolvendo a existente em re-imports.


def _existing_collector(name: str) -> Any | None:
    """Devolve o collector já registado com ``name`` (ou ``None``)."""
    # ``_names_to_collectors`` é interno do prometheus_client mas tem
    # semântica estável desde a 0.0.10; preferível ao varrimento manual.
    by_name = getattr(REGISTRY, "_names_to_collectors", None)
    if by_name is not None and name in by_name:
        return by_name[name]
    # Fallback: percorrer collectors registados.
    for collector in list(getattr(REGISTRY, "_collector_to_names", {}).keys()):
        names = REGISTRY._collector_to_names.get(collector, set())
        if name in names:
            return collector
    return None


def _make_counter(name: str, doc: str, labelnames: tuple[str, ...]) -> Counter:
    try:
        return Counter(name, doc, labelnames=labelnames)
    except ValueError:
        existing = _existing_collector(name)
        if existing is not None:
            return existing  # type: ignore[return-value]
        raise


def _make_histogram(
    name: str, doc: str, labelnames: tuple[str, ...], buckets: tuple[float, ...]
) -> Histogram:
    try:
        return Histogram(name, doc, labelnames=labelnames, buckets=buckets)
    except ValueError:
        existing = _existing_collector(name)
        if existing is not None:
            return existing  # type: ignore[return-value]
        raise


# ---------------------------------------------------------------------------
# Definitions
# ---------------------------------------------------------------------------

requests_total: Counter = _make_counter(
    "unified_gateway_requests_total",
    "Total number of HTTP requests processed by the Unified Gateway.",
    labelnames=("method", "path_template", "status_code"),
)

# Buckets tuned for the spec's <20 ms p95 SLO; the upper end (5 s) catches
# circuit-breaker timeouts and proxy failures.
request_latency_seconds: Histogram = _make_histogram(
    "unified_gateway_request_latency_seconds",
    "End-to-end request latency observed at the Unified Gateway.",
    labelnames=("method", "path_template"),
    buckets=(
        0.001,
        0.0025,
        0.005,
        0.0075,
        0.01,
        0.015,
        0.02,
        0.025,
        0.05,
        0.1,
        0.25,
        0.5,
        1.0,
        2.5,
        5.0,
    ),
)

rate_limit_exceeded_total: Counter = _make_counter(
    "unified_gateway_rate_limit_exceeded_total",
    "Number of requests rejected with HTTP 429 by the rate limiter.",
    labelnames=("tenant_id", "tier"),
)

classification_total: Counter = _make_counter(
    "unified_gateway_classification_total",
    "Total classifications produced by the Intent Classifier, by flow.",
    labelnames=("flow_type",),
)

# Confidence distribution helps spot when the classifier is degrading
# (mass shifting toward 0) or operating in a low-information regime.
classification_confidence: Histogram = _make_histogram(
    "unified_gateway_classification_confidence",
    "Confidence score returned by the Intent Classifier.",
    labelnames=("flow_type",),
    buckets=(0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0),
)

nlu_fallback_total: Counter = _make_counter(
    "unified_gateway_nlu_fallback_total",
    "Number of times an NLU call fell back to keyword-only classification.",
    labelnames=("service",),
)


# ---------------------------------------------------------------------------
# Helpers — small wrappers so callers don't need to know the labels.
# ---------------------------------------------------------------------------


def _truncate_tenant(tenant_id: str | None) -> str:
    """Bound cardinality for tenant labels.

    Caps the string at 32 chars and falls back to ``"anonymous"`` so the
    label dimension stays finite even with hostile input.
    """
    if not tenant_id:
        return "anonymous"
    return str(tenant_id)[:32]


def _normalise_path(path: str) -> str:
    """Collapse path-parameter values into placeholders.

    Tries to keep the structure visible (``/api/v1/nhm/status/{id}``)
    while preventing the cardinality explosion that would happen if
    each request_id became its own label value.
    """
    parts = path.split("/")
    normalised: list[str] = []
    for segment in parts:
        if not segment:
            normalised.append(segment)
            continue
        # Heuristic: hex/uuid-ish segments and obvious IDs become {id}.
        looks_like_id = (
            len(segment) >= 8
            and segment.replace("-", "").isalnum()
            and any(c.isdigit() for c in segment)
        ) or (segment.isdigit())
        normalised.append("{id}" if looks_like_id else segment)
    return "/".join(normalised)


def record_request(*, method: str, path: str, status_code: int, latency_seconds: float) -> None:
    """Record one completed request — counter + latency histogram."""
    template = _normalise_path(path)
    requests_total.labels(
        method=method.upper(), path_template=template, status_code=str(status_code)
    ).inc()
    request_latency_seconds.labels(method=method.upper(), path_template=template).observe(
        max(0.0, latency_seconds)
    )


def record_rate_limit_exceeded(*, tenant_id: str | None, tier: str) -> None:
    """Record a rate-limit rejection."""
    rate_limit_exceeded_total.labels(tenant_id=_truncate_tenant(tenant_id), tier=str(tier)).inc()


def record_classification(*, flow_type: str, confidence: float) -> None:
    """Record one classifier output — count + confidence distribution."""
    flow_label = str(flow_type)
    classification_total.labels(flow_type=flow_label).inc()
    classification_confidence.labels(flow_type=flow_label).observe(
        max(0.0, min(1.0, float(confidence)))
    )


def record_nlu_fallback(*, service: str = "nlu") -> None:
    """Record that an NLU/PII call fell back to a local heuristic."""
    nlu_fallback_total.labels(service=service).inc()
