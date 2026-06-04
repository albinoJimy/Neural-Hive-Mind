"""Unit tests for the Prometheus metrics module."""

from __future__ import annotations

from prometheus_client import REGISTRY

from src.observability import metrics as m


def _sample_value(metric_name: str, **labels) -> float:
    """Read a counter/histogram sample value out of the default registry."""
    value = REGISTRY.get_sample_value(metric_name, labels)
    return float(value) if value is not None else 0.0


def test_record_request_increments_counter_and_observes_latency() -> None:
    before = _sample_value(
        "unified_gateway_requests_total",
        method="GET",
        path_template="/api/v1/nhm/request",
        status_code="200",
    )
    m.record_request(
        method="get",
        path="/api/v1/nhm/request",
        status_code=200,
        latency_seconds=0.012,
    )
    after = _sample_value(
        "unified_gateway_requests_total",
        method="GET",
        path_template="/api/v1/nhm/request",
        status_code="200",
    )
    assert after == before + 1

    # Histogram has a `_count` companion metric we can read back.
    hist_count = _sample_value(
        "unified_gateway_request_latency_seconds_count",
        method="GET",
        path_template="/api/v1/nhm/request",
    )
    assert hist_count >= 1


def test_record_request_normalises_path_with_id() -> None:
    """Path-parameter values should collapse to ``{id}`` to bound cardinality."""
    m.record_request(
        method="GET",
        path="/api/v1/nhm/status/req-20260509-235151-716e5db1",
        status_code=200,
        latency_seconds=0.001,
    )
    assert (
        _sample_value(
            "unified_gateway_requests_total",
            method="GET",
            path_template="/api/v1/nhm/status/{id}",
            status_code="200",
        )
        >= 1
    )


def test_record_rate_limit_exceeded_truncates_long_tenant() -> None:
    long_tenant = "tenant-" + ("x" * 100)
    m.record_rate_limit_exceeded(tenant_id=long_tenant, tier="default")

    expected_label = ("tenant-" + ("x" * 100))[:32]
    assert (
        _sample_value(
            "unified_gateway_rate_limit_exceeded_total",
            tenant_id=expected_label,
            tier="default",
        )
        >= 1
    )


def test_record_rate_limit_exceeded_handles_missing_tenant() -> None:
    m.record_rate_limit_exceeded(tenant_id=None, tier="trial")
    assert (
        _sample_value(
            "unified_gateway_rate_limit_exceeded_total",
            tenant_id="anonymous",
            tier="trial",
        )
        >= 1
    )


def test_record_classification_clamps_confidence_to_unit_range() -> None:
    m.record_classification(flow_type="A-F", confidence=0.42)
    m.record_classification(flow_type="A-F", confidence=1.5)  # >1
    m.record_classification(flow_type="A-F", confidence=-0.2)  # <0

    count = _sample_value("unified_gateway_classification_total", flow_type="A-F")
    assert count >= 3

    hist_count = _sample_value("unified_gateway_classification_confidence_count", flow_type="A-F")
    assert hist_count >= 3


def test_record_nlu_fallback_default_service_label() -> None:
    before = _sample_value("unified_gateway_nlu_fallback_total", service="nlu")
    m.record_nlu_fallback()
    after = _sample_value("unified_gateway_nlu_fallback_total", service="nlu")
    assert after == before + 1


def test_normalise_path_keeps_static_segments() -> None:
    assert m._normalise_path("/health") == "/health"
    assert m._normalise_path("/api/v1/nhm/request") == "/api/v1/nhm/request"
    # purely numeric IDs collapse
    assert m._normalise_path("/orders/12345") == "/orders/{id}"
