"""Neural Hive OPA - Biblioteca padronizada para integração com Open Policy Agent.

Esta biblioteca fornece uma interface unificada para integração com OPA (Open Policy Agent)
através de todos os serviços do Neural-Hive-Mind, eliminando duplicação e inconsistências.

Features:
- Cliente HTTP assíncrono com connection pooling
- Cache LRU com TTL configurável
- Circuit breaker para prevenir cascading failures
- Batch evaluation otimizada
- Métricas Prometheus integradas
- Retry com exponential backoff
- Middleware FastAPI pronto para uso

Example:
    from neural_hive_opa import OPAClient, OPAConfig

    config = OPAConfig(
        opa_url="http://opa:8181",
        opa_cache_ttl_seconds=300,
        opa_circuit_breaker_enabled=True,
    )

    client = OPAClient(config)
    await client.initialize()

    result = await client.evaluate(
        policy="neuralhive/orchestrator/allow",
        input_data={"resource": "cpu", "amount": 4}
    )
"""

__version__ = "0.1.0"

# Importações principais expostas
from neural_hive_opa.client import OPAClient
from neural_hive_opa.config import OPAConfig
from neural_hive_opa.exceptions import (
    OPAConnectionError,
    OPAEvaluationError,
    OPAPolicyNotFoundError,
    OPATimeoutError,
    OPACircuitBreakerOpenError,
)
from neural_hive_opa.models import (
    PolicyRequest,
    PolicyResponse,
    Violation,
    ViolationSeverity,
)
from neural_hive_opa.metrics import OPAMetrics
from neural_hive_opa.observability import (
    get_registry,
    init_opa_metrics,
    get_opa_metrics,
    reset_opa_metrics,
)

__all__ = [
    "OPAClient",
    "OPAConfig",
    "OPAConnectionError",
    "OPAEvaluationError",
    "OPAPolicyNotFoundError",
    "OPATimeoutError",
    "OPACircuitBreakerOpenError",
    "PolicyRequest",
    "PolicyResponse",
    "Violation",
    "ViolationSeverity",
    "OPAMetrics",
    "get_registry",
    "init_opa_metrics",
    "get_opa_metrics",
    "reset_opa_metrics",
    "__version__",
]
