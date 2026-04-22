"""
Neural Hive-Mind Observability Library.

Biblioteca padronizada para instrumentação OpenTelemetry do Neural Hive-Mind.
Este arquivo torna neural_hive_observability um pacote regular (não namespace package).

Uso:
    from neural_hive_observability import init_observability, trace_intent
    from neural_hive_observability.context import extract_context_from_metadata, set_baggage
"""

import sys

# Importar submódulos do subpacote interno
from .neural_hive_observability import (
    config as _config_module,
    context as _context_module,
    grpc_instrumentation as _grpc_module,
    health as _health_module,
    kafka_instrumentation as _kafka_module,
    logging as _logging_module,
    metrics as _metrics_module,
    tracing as _tracing_module,
)

# Registrar aliases no sys.modules para permitir imports como:
# from neural_hive_observability.context import extract_context_from_metadata
sys.modules["neural_hive_observability.context"] = _context_module
sys.modules["neural_hive_observability.config"] = _config_module
sys.modules["neural_hive_observability.tracing"] = _tracing_module
sys.modules["neural_hive_observability.metrics"] = _metrics_module
sys.modules["neural_hive_observability.logging"] = _logging_module
sys.modules["neural_hive_observability.health"] = _health_module
sys.modules["neural_hive_observability.grpc_instrumentation"] = _grpc_module
sys.modules["neural_hive_observability.kafka_instrumentation"] = _kafka_module

# Expor como atributos do módulo também
context = _context_module
config = _config_module
tracing = _tracing_module
metrics = _metrics_module
logging = _logging_module
health = _health_module
grpc_instrumentation = _grpc_module
kafka_instrumentation = _kafka_module

# Re-export da implementação principal para conveniência
from .neural_hive_observability import (
    # Classes
    ContextManager,
    HealthChecker,
    InstrumentedAIOKafkaConsumer,
    InstrumentedAIOKafkaProducer,
    InstrumentedKafkaProducer,
    NeuralHiveGrpcServerInterceptor,
    NeuralHiveMetrics,
    ObservabilityConfig,
    create_instrumented_grpc_server,
    extract_grpc_context,
    get_config,
    get_context_manager,
    get_health_checker,
    # Logging
    get_logger,
    get_metrics,
    get_tracer,
    # gRPC instrumentation
    init_grpc_instrumentation,
    # Inicialização
    init_observability,
    # Context propagation
    inject_context_to_metadata,  # ADICIONADO - faltava no wrapper
    instrument_grpc_channel,  # ADICIONADO - faltava no wrapper
    instrument_kafka_consumer,
    # Kafka instrumentation
    instrument_kafka_producer,
    trace_grpc_method,
    # Tracing
    trace_intent,
    trace_plan,
)

__version__ = "1.2.0"  # Atualizado para corresponder ao pacote interno

__all__ = [
    # Inicialização
    "init_observability",
    "get_config",
    "get_metrics",
    "get_health_checker",
    "get_context_manager",
    # Tracing
    "trace_intent",
    "trace_plan",
    "get_tracer",
    "trace_grpc_method",
    # Classes
    "ContextManager",
    "NeuralHiveMetrics",
    "HealthChecker",
    "ObservabilityConfig",
    # Logging
    "get_logger",
    # gRPC instrumentation
    "init_grpc_instrumentation",
    "create_instrumented_grpc_server",
    "extract_grpc_context",
    "instrument_grpc_channel",  # ADICIONADO
    "NeuralHiveGrpcServerInterceptor",
    # Context propagation
    "inject_context_to_metadata",  # ADICIONADO
    # Kafka instrumentation
    "instrument_kafka_producer",
    "instrument_kafka_consumer",
    "InstrumentedKafkaProducer",
    "InstrumentedAIOKafkaConsumer",
    "InstrumentedAIOKafkaProducer",
]
