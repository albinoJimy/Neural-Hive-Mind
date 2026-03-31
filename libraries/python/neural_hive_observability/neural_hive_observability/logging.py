"""
Logging estruturado com Structlog para Neural Hive-Mind.

Configura structlog com correlação automática de trace_id, span_id,
intent_id e plan_id para facilitar troubleshooting distribuído.
"""

import sys
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timezone

import structlog
from opentelemetry import trace

from .config import ObservabilityConfig


# Processor para adicionar correlação do OpenTelemetry
def _add_trace_correlation(
    logger: logging.Logger,
    method_name: str,
    event_dict: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Adiciona trace_id e span_id do OpenTelemetry ao log.

    Args:
        logger: Logger
        method_name: Nome do método
        event_dict: Dicionário de eventos do structlog

    Returns:
        event_dict atualizado com trace_id e span_id
    """
    span = trace.get_current_span()
    if span and span.get_span_context().is_valid:
        ctx = span.get_span_context()
        event_dict["trace_id"] = format(ctx.trace_id, "032x")
        event_dict["span_id"] = format(ctx.span_id, "016x")
    return event_dict


# Processor para adicionar timestamp UTC
def _add_timestamp_utc(
    logger: logging.Logger,
    method_name: str,
    event_dict: Dict[str, Any]
) -> Dict[str, Any]:
    """Adiciona timestamp UTC ao log."""
    event_dict["timestamp"] = datetime.now(timezone.utc).isoformat()
    return event_dict


# Processor para adicionar metadados do serviço
def _add_service_metadata(
    logger: logging.Logger,
    method_name: str,
    event_dict: Dict[str, Any]
) -> Dict[str, Any]:
    """Adiciona metadados do serviço ao log."""
    # Obtém configuração do context ou usa defaults
    config = event_dict.get("_config", None)
    if config:
        event_dict["service"] = {
            "name": config.service_name,
            "version": config.service_version,
            "instance_id": config.service_instance_id,
        }
        event_dict["neural_hive"] = {
            "component": config.neural_hive_component,
            "layer": config.neural_hive_layer,
            "domain": config.neural_hive_domain or "unknown",
        }
        event_dict["environment"] = config.environment
    return event_dict


# Processor para adicionar nível de log padrão
def _add_log_level(
    logger: logging.Logger,
    method_name: str,
    event_dict: Dict[str, Any]
) -> Dict[str, Any]:
    """Adiciona nível de log ao evento."""
    event_dict["level"] = method_name.upper()
    return event_dict


# Processor para adicionar nome do logger
def _add_logger_name(
    logger: logging.Logger,
    method_name: str,
    event_dict: Dict[str, Any]
) -> Dict[str, Any]:
    """Adiciona nome do logger ao evento."""
    event_dict["logger"] = logger.name
    return event_dict


class NeuralHiveLogger:
    """
    Logger estruturado com suporte a correlação.

    Esta classe fornece uma API simples baseada em structlog
    com suporte automático a correlation IDs (trace_id, span_id)
    e campos de negócio (intent_id, plan_id, user_id).
    """

    def __init__(
        self,
        name: str,
        config: Optional[ObservabilityConfig] = None
    ):
        """
        Inicializa logger.

        Args:
            name: Nome do logger
            config: Configuração de observabilidade
        """
        self._name = name
        self._config = config
        self._logger = structlog.get_logger(name)
        self._std_logger = logging.getLogger(name)

    def bind(self, **kwargs) -> "NeuralHiveLogger":
        """
        Bind context to this logger instance.

        Args:
            **kwargs: Context fields to bind

        Returns:
            Self for chaining
        """
        self._logger = self._logger.bind(**kwargs)
        return self

    def unbind(self, *keys) -> "NeuralHiveLogger":
        """
        Unbind context from this logger instance.

        Args:
            *keys: Context keys to unbind

        Returns:
            Self for chaining
        """
        self._logger = self._logger.unbind(*keys)
        return self

    def debug(self, msg: str, **kwargs):
        """Log debug message."""
        self._logger.debug(msg, _config=self._config, **kwargs)

    def info(self, msg: str, **kwargs):
        """Log info message."""
        self._logger.info(msg, _config=self._config, **kwargs)

    def warning(self, msg: str, **kwargs):
        """Log warning message."""
        self._logger.warning(msg, _config=self._config, **kwargs)

    def error(self, msg: str, **kwargs):
        """Log error message."""
        self._logger.error(msg, _config=self._config, **kwargs)

    def critical(self, msg: str, **kwargs):
        """Log critical message."""
        self._logger.critical(msg, _config=self._config, **kwargs)

    def exception(self, msg: str, **kwargs):
        """Log exception with traceback."""
        self._logger.exception(msg, _config=self._config, **kwargs)

    # Métodos com correlação explícita
    def with_intent(self, intent_id: str) -> "NeuralHiveLogger":
        """
        Retorna logger com intent_id vinculado.

        Args:
            intent_id: ID da intenção

        Returns:
            Logger com context bound
        """
        return self.bind(intent_id=intent_id)

    def with_plan(self, plan_id: str) -> "NeuralHiveLogger":
        """
        Retorna logger com plan_id vinculado.

        Args:
            plan_id: ID do plano

        Returns:
            Logger com context bound
        """
        return self.bind(plan_id=plan_id)

    def with_user(self, user_id: str) -> "NeuralHiveLogger":
        """
        Retorna logger com user_id vinculado.

        Args:
            user_id: ID do usuário

        Returns:
            Logger com context bound
        """
        return self.bind(user_id=user_id)

    def with_correlation(
        self,
        intent_id: Optional[str] = None,
        plan_id: Optional[str] = None,
        user_id: Optional[str] = None,
        **extra
    ) -> "NeuralHiveLogger":
        """
        Retorna logger com múltiplos IDs de correlação vinculados.

        Args:
            intent_id: ID da intenção
            plan_id: ID do plano
            user_id: ID do usuário
            **extra: Campos adicionais

        Returns:
            Logger com context bound
        """
        context = {}
        if intent_id:
            context["intent_id"] = intent_id
        if plan_id:
            context["plan_id"] = plan_id
        if user_id:
            context["user_id"] = user_id
        context.update(extra)
        return self.bind(**context)

    # Métodos específicos de operação
    def log_intent_start(
        self,
        intent_id: str,
        user_input: str,
        channel: str = "unknown"
    ):
        """Log início de processamento de intenção."""
        self.info(
            "Iniciando processamento de intenção",
            intent_id=intent_id,
            operation="intent_start",
            channel=channel,
            user_input_length=len(user_input)
        )

    def log_intent_completion(
        self,
        intent_id: str,
        confidence: float,
        processing_duration: float,
        channel: str = "unknown"
    ):
        """Log conclusão de processamento de intenção."""
        self.info(
            "Intenção processada com sucesso",
            intent_id=intent_id,
            operation="intent_completion",
            channel=channel,
            confidence=confidence,
            processing_duration_seconds=processing_duration
        )

    def log_plan_execution_start(
        self,
        plan_id: str,
        intent_id: Optional[str] = None,
        plan_type: str = "unknown"
    ):
        """Log início de execução de plano."""
        self.info(
            "Iniciando execução de plano",
            plan_id=plan_id,
            intent_id=intent_id,
            operation="plan_execution_start",
            plan_type=plan_type
        )

    def log_plan_execution_completion(
        self,
        plan_id: str,
        success: bool,
        execution_duration: float,
        intent_id: Optional[str] = None,
        plan_type: str = "unknown"
    ):
        """Log conclusão de execução de plano."""
        message = "Plano executado com sucesso" if success else "Falha na execução do plano"
        self.info(
            message,
            plan_id=plan_id,
            intent_id=intent_id,
            operation="plan_execution_completion",
            plan_type=plan_type,
            success=success,
            execution_duration_seconds=execution_duration
        )


def init_logging(config: ObservabilityConfig) -> None:
    """
    Inicializa logging estruturado com structlog.

    Configura structlog como logger primário com correlação automática
    de trace_id, span_id e suporte a intent_id, plan_id, user_id.

    Args:
        config: Configuração de observabilidade
    """
    # Configurar nível de log stdlib (para bibliotecas de terceiros)
    log_level = getattr(logging, config.log_level, logging.INFO)

    # Configurar root logger stdlib
    stdlib_logger = logging.getLogger()
    stdlib_logger.setLevel(log_level)

    # Remover handlers existentes
    for handler in stdlib_logger.handlers[:]:
        stdlib_logger.removeHandler(handler)

    # Criar handler para console
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)

    # Formato depende de config.log_format
    if config.log_format.lower() == "json":
        formatter = logging.Formatter(
            '%(message)s'  # structlog já formata como JSON
        )
    else:
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )

    console_handler.setFormatter(formatter)
    stdlib_logger.addHandler(console_handler)

    # Configurar loggers de bibliotecas externas
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("opentelemetry").setLevel(logging.WARNING)
    logging.getLogger("pymongo").setLevel(logging.WARNING)
    logging.getLogger("pymongo.serverSelection").setLevel(logging.WARNING)
    logging.getLogger("pymongo.connection").setLevel(logging.WARNING)
    logging.getLogger("grpc").setLevel(logging.WARNING)

    # Configurar processadores structlog
    shared_processors = [
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.UnicodeDecoder(),
        _add_timestamp_utc,
        _add_trace_correlation,
        _add_service_metadata,
    ]

    # Renderer baseado no formato
    if config.log_format.lower() == "json":
        renderer = structlog.processors.JSONRenderer()
    else:
        # Console renderer com cores desabilitado para output consistente
        renderer = structlog.dev.ConsoleRenderer(colors=False)

    # Configurar structlog
    structlog.configure(
        processors=shared_processors + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Configurar stdlib handler com structlog processor
    if config.log_format.lower() == "json":
        # Usar ProcessorFormatter para saída JSON
        processor = structlog.stdlib.ProcessorFormatter(
            processor=structlog.processors.JSONRenderer()
        )
    else:
        # Formato texto legível
        processor = structlog.stdlib.ProcessorFormatter(
            processor=renderer
        )

    console_handler.setFormatter(processor)


def get_logger(
    name: Optional[str] = None,
    config: Optional[ObservabilityConfig] = None
) -> NeuralHiveLogger:
    """
    Retorna logger estruturado com suporte a correlação.

    Args:
        name: Nome do logger (padrão: módulo chamador)
        config: Configuração de observabilidade (opcional)

    Returns:
        NeuralHiveLogger com suporte a correlation IDs

    Example:
        from neural_hive_observability import get_logger

        logger = get_logger(__name__)
        logger.info("Processing started")

        # Com correlação
        logger = logger.with_intent(intent_id="123")
        logger.info("Processing intent")

        # Com múltipla correlação
        logger.with_correlation(
            intent_id="123",
            plan_id="456",
            user_id="789"
        ).info("Executing plan")
    """
    if name is None:
        # Obter nome do módulo chamador
        import inspect
        frame = inspect.currentframe()
        if frame and frame.f_back:
            name = frame.f_back.f_globals.get("__name__", "unknown")
        else:
            name = "unknown"

    return NeuralHiveLogger(name, config)


# Legacy compatibility - mantém a antiga API para não quebrar código existente
class CorrelationFormatter(logging.Formatter):
    """Formatter legado para compatibilidade."""

    def __init__(self, config: ObservabilityConfig):
        super().__init__()
        self.config = config

    def format(self, record: logging.LogRecord) -> str:
        import json
        log_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        span = trace.get_current_span()
        if span and span.get_span_context().is_valid:
            ctx = span.get_span_context()
            log_data["trace_id"] = format(ctx.trace_id, "032x")
            log_data["span_id"] = format(ctx.span_id, "016x")

        return json.dumps(log_data, ensure_ascii=False, default=str)


class NeuralHiveLoggerAdapter(logging.LoggerAdapter):
    """Adapter legado para compatibilidade."""

    def __init__(self, logger: logging.Logger, extra: Optional[Dict[str, Any]] = None):
        super().__init__(logger, extra or {})

    def process(self, msg: str, kwargs: Dict[str, Any]) -> tuple:
        intent_id = kwargs.pop("intent_id", None)
        plan_id = kwargs.pop("plan_id", None)
        user_id = kwargs.pop("user_id", None)

        if intent_id:
            kwargs.setdefault("extra", {})["intent_id"] = intent_id
        if plan_id:
            kwargs.setdefault("extra", {})["plan_id"] = plan_id
        if user_id:
            kwargs.setdefault("extra", {})["user_id"] = user_id

        return msg, kwargs


# Funções legadas para compatibilidade
def log_intent_start(
    logger,
    intent_id: str,
    user_input: str,
    channel: str = "unknown"
):
    """Log início de processamento de intenção (legado)."""
    if isinstance(logger, NeuralHiveLogger):
        logger.log_intent_start(intent_id, user_input, channel)
    else:
        logger.info_with_correlation(
            "Iniciando processamento de intenção",
            intent_id=intent_id,
            extra_fields={"operation": "intent_start", "channel": channel}
        )


def log_intent_completion(
    logger,
    intent_id: str,
    confidence: float,
    processing_duration: float,
    channel: str = "unknown"
):
    """Log conclusão de processamento de intenção (legado)."""
    if isinstance(logger, NeuralHiveLogger):
        logger.log_intent_completion(intent_id, confidence, processing_duration, channel)
    else:
        logger.info_with_correlation(
            "Intenção processada com sucesso",
            intent_id=intent_id,
            extra_fields={
                "operation": "intent_completion",
                "confidence": confidence,
                "processing_duration_seconds": processing_duration
            }
        )


def log_plan_execution_start(
    logger,
    plan_id: str,
    intent_id: Optional[str] = None,
    plan_type: str = "unknown"
):
    """Log início de execução de plano (legado)."""
    if isinstance(logger, NeuralHiveLogger):
        logger.log_plan_execution_start(plan_id, intent_id, plan_type)
    else:
        logger.info_with_correlation(
            "Iniciando execução de plano",
            plan_id=plan_id,
            intent_id=intent_id,
            extra_fields={"operation": "plan_execution_start", "plan_type": plan_type}
        )


def log_plan_execution_completion(
    logger,
    plan_id: str,
    success: bool,
    execution_duration: float,
    intent_id: Optional[str] = None,
    plan_type: str = "unknown"
):
    """Log conclusão de execução de plano (legado)."""
    if isinstance(logger, NeuralHiveLogger):
        logger.log_plan_execution_completion(plan_id, success, execution_duration, intent_id, plan_type)
    else:
        message = "Plano executado com sucesso" if success else "Falha na execução do plano"
        logger.info_with_correlation(
            message,
            plan_id=plan_id,
            intent_id=intent_id,
            extra_fields={
                "operation": "plan_execution_completion",
                "plan_type": plan_type,
                "success": success,
                "execution_duration_seconds": execution_duration
            }
        )
