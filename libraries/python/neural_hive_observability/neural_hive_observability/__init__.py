"""
Neural Hive-Mind Observability Library

Biblioteca padronizada para instrumentação OpenTelemetry do Neural Hive-Mind.
Facilita instrumentação consistente entre serviços com decorators, context propagation
e métricas customizadas.

Funcionalidades:
- Tracing automático com correlação por intent_id/plan_id
- Métricas padronizadas por camada arquitetural
- Logging estruturado com correlação automática
- Health checks distribuídos
- Context propagation transparente

Exemplo de uso:
```python
from neural_hive_observability import init_observability, trace_intent, metrics

# Inicializar observabilidade
init_observability(
    service_name="gateway-intencoes",
    service_version="1.0.0",
    neural_hive_component="gateway",
    neural_hive_layer="experiencia"
)

# Usar decorador para tracing automático
@trace_intent
def process_intention(intent_id: str, user_input: str):
    metrics.intencoes_processadas.inc()
    return {"status": "processed", "intent_id": intent_id}
```
"""

import logging as stdlib_logging  # Import with alias to avoid conflict with local .logging module
import os
from typing import Optional, Dict, Any

from .config import ObservabilityConfig
from .tracing import init_tracing, trace_intent, trace_plan, get_tracer, trace_grpc_method
from .metrics import init_metrics, NeuralHiveMetrics
from .logging import init_logging, get_logger
from .health import HealthChecker
from .context import ContextManager
from .grpc_instrumentation import (
    init_grpc_instrumentation,
    create_instrumented_grpc_server,
    extract_grpc_context,
    NeuralHiveGrpcServerInterceptor
)
from .kafka_instrumentation import (
    instrument_kafka_producer,
    instrument_kafka_consumer,
    InstrumentedKafkaProducer,
    InstrumentedAIOKafkaConsumer,
    InstrumentedAIOKafkaProducer
)

# Versão da biblioteca
__version__ = "1.1.0"

# Logger da biblioteca
logger = stdlib_logging.getLogger(__name__)

# Instâncias globais
_config: Optional[ObservabilityConfig] = None
_metrics: Optional[NeuralHiveMetrics] = None
_health_checker: Optional[HealthChecker] = None
_context_manager: Optional[ContextManager] = None

def init_observability(
    service_name: str,
    service_version: str = "unknown",
    neural_hive_component: str = "unknown",
    neural_hive_layer: str = "unknown",
    neural_hive_domain: Optional[str] = None,
    environment: Optional[str] = None,
    otel_endpoint: Optional[str] = None,
    prometheus_port: int = 8000,
    log_level: str = "INFO",
    enable_health_checks: bool = True,
    **kwargs
) -> None:
    """
    Inicializa a observabilidade completa do Neural Hive-Mind.

    Args:
        service_name: Nome do serviço
        service_version: Versão do serviço
        neural_hive_component: Componente do Neural Hive-Mind
        neural_hive_layer: Camada arquitetural
        neural_hive_domain: Domínio específico (opcional)
        environment: Ambiente (production, staging, development)
        otel_endpoint: Endpoint do OpenTelemetry Collector
        prometheus_port: Porta para métricas Prometheus
        log_level: Nível de log
        enable_health_checks: Habilitar health checks
        **kwargs: Configurações adicionais
    """
    global _config, _metrics, _health_checker, _context_manager

    # Criar configuração
    _config = ObservabilityConfig(
        service_name=service_name,
        service_version=service_version,
        neural_hive_component=neural_hive_component,
        neural_hive_layer=neural_hive_layer,
        neural_hive_domain=neural_hive_domain,
        environment=environment or os.getenv("ENVIRONMENT", "production"),
        otel_endpoint=otel_endpoint or os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://opentelemetry-collector:4317"),
        prometheus_port=prometheus_port,
        log_level=log_level,
        enable_health_checks=enable_health_checks,
        **kwargs
    )

    logger.info(f"Inicializando observabilidade para {service_name} ({neural_hive_component})")

    try:
        # Inicializar componentes
        init_tracing(_config)
        # Inicializar instrumentação gRPC
        try:
            init_grpc_instrumentation(_config)
            logger.info("gRPC instrumentation initialized")
        except Exception as e:
            logger.warning(f"Failed to initialize gRPC instrumentation: {e}")
        init_logging(_config)
        _metrics = init_metrics(_config)

        # Inicializar context manager
        _context_manager = ContextManager(_config)

        # Inicializar health checker se habilitado
        if enable_health_checks:
            _health_checker = HealthChecker(_config)
            _health_checker.register_default_checks()

        logger.info("Observabilidade inicializada com sucesso")

        # Registrar métricas de inicialização
        if _metrics:
            _metrics.service_startup_total.labels(
                **_config.common_labels
            ).inc()

    except Exception as e:
        logger.error(f"Erro ao inicializar observabilidade: {e}")
        raise

def get_config() -> Optional[ObservabilityConfig]:
    """Retorna a configuração atual de observabilidade."""
    return _config

def get_metrics() -> Optional[NeuralHiveMetrics]:
    """Retorna a instância de métricas."""
    return _metrics

def get_health_checker() -> Optional[HealthChecker]:
    """Retorna o health checker."""
    return _health_checker

def get_context_manager() -> Optional[ContextManager]:
    """Retorna o context manager."""
    return _context_manager

# Aliases para facilitar o uso
# Nota: Usando nomes com underscore para evitar conflito com módulos
_metrics = property(lambda: get_metrics())
_health = property(lambda: get_health_checker())
_context = property(lambda: get_context_manager())

# Aliases públicos (para compatibilidade retroativa via get_* functions)
# Use get_metrics(), get_health_checker(), get_context_manager() diretamente

# Re-export principais funcionalidades
__all__ = [
    # Função principal
    "init_observability",

    # Tracing
    "trace_intent",
    "trace_plan",
    "get_tracer",

    # Métricas
    "NeuralHiveMetrics",
    "get_metrics",

    # Logging
    "get_logger",

    # Health checks
    "HealthChecker",
    "get_health_checker",

    # Context
    "ContextManager",
    "get_context_manager",

    # Config
    "ObservabilityConfig",
    "get_config",

    # Utilitários (use as funções get_* em vez das properties)
    # "_metrics", "_health", "_context" são privados

    # gRPC instrumentation
    "init_grpc_instrumentation",
    "create_instrumented_grpc_server",
    "extract_grpc_context",
    "NeuralHiveGrpcServerInterceptor",
    "trace_grpc_method",

    # Kafka instrumentation
    "instrument_kafka_producer",
    "instrument_kafka_consumer",
    "InstrumentedKafkaProducer",
    "InstrumentedAIOKafkaConsumer",
    "InstrumentedAIOKafkaProducer",
]
