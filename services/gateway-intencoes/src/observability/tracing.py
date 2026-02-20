"""
Tracing integration for Gateway service using Neural Hive observability library.

This module provides a thin wrapper around the shared library for service-specific tracing needs.
"""

from typing import Dict, Any, Optional
from functools import wraps
import logging

from neural_hive_observability import get_tracer, get_context_manager
from neural_hive_observability.correlation import CorrelationContext

logger = logging.getLogger(__name__)

# Get tracer instance
tracer = get_tracer()


def trace_gateway_operation(operation_name: str, include_args: bool = False):
    """
    Decorator to trace Gateway-specific operations with correlation context.

    Args:
        operation_name: Name of the operation being traced
        include_args: Whether to include function arguments in span attributes
    """

    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            with tracer.start_as_current_span(operation_name) as span:
                try:
                    # Add standard attributes
                    span.set_attribute("neural.hive.component", "gateway")
                    span.set_attribute("neural.hive.layer", "experiencia")
                    span.set_attribute("neural.hive.operation", operation_name)

                    # Extract correlation IDs from request if available
                    if "request" in kwargs:
                        request = kwargs["request"]
                        if hasattr(request, "headers"):
                            intent_id = request.headers.get("x-neural-hive-intent-id")
                            plan_id = request.headers.get("x-neural-hive-plan-id")
                            user_id = request.headers.get("x-neural-hive-user-id")
                            domain = request.headers.get("x-neural-hive-domain")

                            if intent_id:
                                span.set_attribute("neural.hive.intent.id", intent_id)
                            if plan_id:
                                span.set_attribute("neural.hive.plan.id", plan_id)
                            if user_id:
                                span.set_attribute("neural.hive.user.id", user_id)
                            if domain:
                                span.set_attribute("neural.hive.domain", domain)

                    # Include function arguments if requested (be careful with sensitive data)
                    if include_args:
                        safe_args = _sanitize_args(args, kwargs)
                        for key, value in safe_args.items():
                            span.set_attribute(
                                f"args.{key}", str(value)[:100]
                            )  # Limit length

                    result = await func(*args, **kwargs)

                    # Add result attributes if it's a dict
                    if isinstance(result, dict):
                        if "intent_id" in result:
                            span.set_attribute(
                                "neural.hive.intent.id", result["intent_id"]
                            )
                        if "confidence" in result:
                            span.set_attribute(
                                "neural.hive.confidence", result["confidence"]
                            )
                        if "domain" in result:
                            span.set_attribute("neural.hive.domain", result["domain"])
                        if "status" in result:
                            span.set_attribute("neural.hive.status", result["status"])

                    span.set_status("OK")
                    return result

                except Exception as e:
                    span.set_status("ERROR", str(e))
                    span.set_attribute("error.type", type(e).__name__)
                    span.set_attribute("error.message", str(e))
                    raise

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            with tracer.start_as_current_span(operation_name) as span:
                try:
                    # Add standard attributes
                    span.set_attribute("neural.hive.component", "gateway")
                    span.set_attribute("neural.hive.layer", "experiencia")
                    span.set_attribute("neural.hive.operation", operation_name)

                    # Include function arguments if requested
                    if include_args:
                        safe_args = _sanitize_args(args, kwargs)
                        for key, value in safe_args.items():
                            span.set_attribute(f"args.{key}", str(value)[:100])

                    result = func(*args, **kwargs)
                    span.set_status("OK")
                    return result

                except Exception as e:
                    span.set_status("ERROR", str(e))
                    span.set_attribute("error.type", type(e).__name__)
                    span.set_attribute("error.message", str(e))
                    raise

        # Return appropriate wrapper based on function type
        import asyncio

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


def _sanitize_args(args, kwargs) -> Dict[str, Any]:
    """
    Sanitize function arguments to avoid logging sensitive data.

    Args:
        args: Positional arguments
        kwargs: Keyword arguments

    Returns:
        Dictionary of sanitized arguments
    """
    safe_args = {}

    # Sanitize kwargs
    for key, value in kwargs.items():
        if key.lower() in ["password", "token", "secret", "key", "auth", "credential"]:
            safe_args[key] = "[REDACTED]"
        elif key == "audio_file" and hasattr(value, "size"):
            safe_args[key] = f"<audio_file:{value.content_type}:{value.size}bytes>"
        elif isinstance(value, (str, int, float, bool)):
            safe_args[key] = value
        else:
            safe_args[key] = f"<{type(value).__name__}>"

    return safe_args


def add_correlation_to_span(
    span,
    intent_id: Optional[str] = None,
    plan_id: Optional[str] = None,
    user_id: Optional[str] = None,
    domain: Optional[str] = None,
):
    """
    Add correlation IDs to the current span.

    Args:
        span: OpenTelemetry span
        intent_id: Intent ID for correlation
        plan_id: Plan ID for correlation
        user_id: User ID for correlation
        domain: Domain for correlation
    """
    if intent_id:
        span.set_attribute("neural.hive.intent.id", intent_id)
    if plan_id:
        span.set_attribute("neural.hive.plan.id", plan_id)
    if user_id:
        span.set_attribute("neural.hive.user.id", user_id)
    if domain:
        span.set_attribute("neural.hive.domain", domain)


def create_correlation_context(
    intent_id: Optional[str] = None,
    plan_id: Optional[str] = None,
    user_id: Optional[str] = None,
    domain: Optional[str] = None,
) -> CorrelationContext:
    """
    Create a correlation context for distributed tracing.

    Args:
        intent_id: Intent ID for correlation
        plan_id: Plan ID for correlation
        user_id: User ID for correlation
        domain: Domain for correlation

    Returns:
        CorrelationContext instance
    """
    context_manager = get_context_manager()
    if context_manager:
        return context_manager.correlation_context(
            intent_id=intent_id, plan_id=plan_id, user_id=user_id, domain=domain
        )
    else:
        logger.warning("Context manager not available, correlation context disabled")
        return _dummy_context()


class _DummyContext:
    """Dummy context manager when observability is not available."""

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


def _dummy_context():
    return _DummyContext()
