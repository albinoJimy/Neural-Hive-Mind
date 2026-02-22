"""
Logging estruturado para Neural Hive-Mind.

Configura logging JSON com correlação automática de trace_id, span_id,
intent_id e plan_id para facilitar troubleshooting distribuído.
"""

import json
import logging
import sys
from typing import Dict, Any, Optional
from datetime import datetime, timezone

from opentelemetry import trace

from .config import ObservabilityConfig


class CorrelationFormatter(logging.Formatter):
    """Formatter que adiciona correlação automática."""

    def __init__(self, config: ObservabilityConfig):
        """
        Inicializa formatter.

        Args:
            config: Configuração de observabilidade
        """
        super().__init__()
        self.config = config

    def format(self, record: logging.LogRecord) -> str:
        """
        Formata log record com correlação.

        Args:
            record: Log record

        Returns:
            JSON string formatado
        """
        # Base log data
        log_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Adicionar metadados do serviço
        log_data.update({
            "service": {
                "name": self.config.service_name,
                "version": self.config.service_version,
                "instance_id": self.config.service_instance_id,
            },
            "neural_hive": {
                "component": self.config.neural_hive_component,
                "layer": self.config.neural_hive_layer,
                "domain": self.config.neural_hive_domain or "unknown",
            },
            "environment": self.config.environment,
        })

        # Adicionar correlação de tracing
        trace_correlation = self._get_trace_correlation()
        if trace_correlation:
            log_data["trace"] = trace_correlation

        # Adicionar campos extras do record
        if hasattr(record, "intent_id") and record.intent_id:
            log_data["intent_id"] = record.intent_id

        if hasattr(record, "plan_id") and record.plan_id:
            log_data["plan_id"] = record.plan_id

        if hasattr(record, "user_id") and record.user_id:
            log_data["user_id"] = record.user_id

        if hasattr(record, "extra_fields") and record.extra_fields:
            log_data.update(record.extra_fields)

        # Adicionar stack trace se for exceção
        if record.exc_info:
            log_data["exception"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
                "stack_trace": self.formatException(record.exc_info),
            }

        return json.dumps(log_data, ensure_ascii=False, default=str)

    def _get_trace_correlation(self) -> Optional[Dict[str, str]]:
        """
        Extrai informações de correlação do trace atual.

        Returns:
            Dicionário com trace_id e span_id ou None
        """
        span = trace.get_current_span()
        if span and span.get_span_context().is_valid:
            return {
                "trace_id": format(span.get_span_context().trace_id, "032x"),
                "span_id": format(span.get_span_context().span_id, "016x"),
            }
        return None


class NeuralHiveLoggerAdapter(logging.LoggerAdapter):
    """Logger adapter com suporte a correlação."""

    def __init__(self, logger: logging.Logger, extra: Optional[Dict[str, Any]] = None):
        """
        Inicializa adapter.

        Args:
            logger: Logger base
            extra: Campos extras padrão
        """
        super().__init__(logger, extra or {})

    def process(self, msg: str, kwargs: Dict[str, Any]) -> tuple:
        """
        Processa log message adicionando contexto.

        Args:
            msg: Mensagem
            kwargs: Argumentos

        Returns:
            Tupla (msg, kwargs)
        """
        # Extrair campos especiais dos kwargs
        intent_id = kwargs.pop("intent_id", None)
        plan_id = kwargs.pop("plan_id", None)
        user_id = kwargs.pop("user_id", None)
        extra_fields = kwargs.pop("extra_fields", {})

        # Adicionar ao extra
        if intent_id:
            kwargs.setdefault("extra", {})["intent_id"] = intent_id
        if plan_id:
            kwargs.setdefault("extra", {})["plan_id"] = plan_id
        if user_id:
            kwargs.setdefault("extra", {})["user_id"] = user_id
        if extra_fields:
            kwargs.setdefault("extra", {})["extra_fields"] = extra_fields

        return msg, kwargs

    def info_with_correlation(
        self,
        msg: str,
        intent_id: Optional[str] = None,
        plan_id: Optional[str] = None,
        user_id: Optional[str] = None,
        **kwargs
    ):
        """Log info com correlação."""
        self.info(
            msg,
            intent_id=intent_id,
            plan_id=plan_id,
            user_id=user_id,
            **kwargs
        )

    def error_with_correlation(
        self,
        msg: str,
        intent_id: Optional[str] = None,
        plan_id: Optional[str] = None,
        user_id: Optional[str] = None,
        **kwargs
    ):
        """Log error com correlação."""
        self.error(
            msg,
            intent_id=intent_id,
            plan_id=plan_id,
            user_id=user_id,
            **kwargs
        )

    def warning_with_correlation(
        self,
        msg: str,
        intent_id: Optional[str] = None,
        plan_id: Optional[str] = None,
        user_id: Optional[str] = None,
        **kwargs
    ):
        """Log warning com correlação."""
        self.warning(
            msg,
            intent_id=intent_id,
            plan_id=plan_id,
            user_id=user_id,
            **kwargs
        )


def init_logging(config: ObservabilityConfig) -> None:
    """
    Inicializa logging estruturado.

    Configura tanto logging padrão quanto structlog para uso consistente
    em todos os serviços do Neural Hive-Mind.

    Args:
        config: Configuração de observabilidade
    """
    # Importar structlog aqui para evitar dependência circular
    try:
        import structlog
    except ImportError:
        structlog = None

    # Configurar nível de log
    log_level = getattr(logging, config.log_level, logging.INFO)

    # Configurar root logger padrão
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Remover handlers existentes
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Criar handler para console
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)

    # Configurar formatter baseado no formato
    if config.log_format.lower() == "json":
        formatter = CorrelationFormatter(config)
    else:
        # Formato texto simples
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )

    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # Configurar loggers de bibliotecas externas
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("opentelemetry").setLevel(logging.WARNING)
    logging.getLogger("pymongo").setLevel(logging.WARNING)
    logging.getLogger("pymongo.serverSelection").setLevel(logging.WARNING)
    logging.getLogger("pymongo.connection").setLevel(logging.WARNING)

    # Configurar structlog se disponível (usado por STE, Consensus, Orchestrator)
    if structlog is not None:
        try:
            # Configurar structlog com processadores que outputam logs corretamente
            structlog.configure(
                processors=[
                    structlog.stdlib.filter_by_level,
                    structlog.stdlib.add_logger_name,
                    structlog.stdlib.add_log_level,
                    structlog.stdlib.PositionalArgumentsFormatter(),
                    structlog.processors.TimeStamper(fmt="iso"),
                    structlog.processors.StackInfoRenderer(),
                    structlog.processors.format_exc_info,
                    structlog.processors.UnicodeDecoder(),
                    # Usar JSONRenderer para formato JSON ou dev para formato legível
                    structlog.processors.JSONRenderer() if config.log_format.lower() == "json"
                    else structlog.dev.ConsoleRenderer(colors=False),
                ],
                context_class=dict,
                logger_factory=structlog.stdlib.LoggerFactory(),
                wrapper_class=structlog.stdlib.BoundLogger,
                cache_logger_on_first_use=True,
            )
        except Exception as e:
            # Se structlog configure falhar, log mas não quebre startup
            root_logger.warning(f"Failed to configure structlog: {e}")


def get_logger(name: Optional[str] = None) -> NeuralHiveLoggerAdapter:
    """
    Retorna logger com suporte a correlação.

    Args:
        name: Nome do logger (padrão: módulo chamador)

    Returns:
        Logger adapter
    """
    if name is None:
        # Obter nome do módulo chamador
        import inspect
        frame = inspect.currentframe()
        if frame and frame.f_back:
            name = frame.f_back.f_globals.get("__name__", "unknown")
        else:
            name = "unknown"

    logger = logging.getLogger(name)
    return NeuralHiveLoggerAdapter(logger)


def log_intent_start(
    logger: NeuralHiveLoggerAdapter,
    intent_id: str,
    user_input: str,
    channel: str = "unknown"
):
    """
    Log início de processamento de intenção.

    Args:
        logger: Logger
        intent_id: ID da intenção
        user_input: Input do usuário
        channel: Canal de origem
    """
    logger.info_with_correlation(
        "Iniciando processamento de intenção",
        intent_id=intent_id,
        extra_fields={
            "operation": "intent_start",
            "channel": channel,
            "user_input_length": len(user_input),
        }
    )


def log_intent_completion(
    logger: NeuralHiveLoggerAdapter,
    intent_id: str,
    confidence: float,
    processing_duration: float,
    channel: str = "unknown"
):
    """
    Log conclusão de processamento de intenção.

    Args:
        logger: Logger
        intent_id: ID da intenção
        confidence: Confiança da intenção
        processing_duration: Duração do processamento
        channel: Canal de origem
    """
    logger.info_with_correlation(
        "Intenção processada com sucesso",
        intent_id=intent_id,
        extra_fields={
            "operation": "intent_completion",
            "channel": channel,
            "confidence": confidence,
            "processing_duration_seconds": processing_duration,
        }
    )


def log_plan_execution_start(
    logger: NeuralHiveLoggerAdapter,
    plan_id: str,
    intent_id: Optional[str] = None,
    plan_type: str = "unknown"
):
    """
    Log início de execução de plano.

    Args:
        logger: Logger
        plan_id: ID do plano
        intent_id: ID da intenção relacionada
        plan_type: Tipo do plano
    """
    logger.info_with_correlation(
        "Iniciando execução de plano",
        intent_id=intent_id,
        plan_id=plan_id,
        extra_fields={
            "operation": "plan_execution_start",
            "plan_type": plan_type,
        }
    )


def log_plan_execution_completion(
    logger: NeuralHiveLoggerAdapter,
    plan_id: str,
    success: bool,
    execution_duration: float,
    intent_id: Optional[str] = None,
    plan_type: str = "unknown"
):
    """
    Log conclusão de execução de plano.

    Args:
        logger: Logger
        plan_id: ID do plano
        success: Se a execução foi bem-sucedida
        execution_duration: Duração da execução
        intent_id: ID da intenção relacionada
        plan_type: Tipo do plano
    """
    message = "Plano executado com sucesso" if success else "Falha na execução do plano"

    logger.info_with_correlation(
        message,
        intent_id=intent_id,
        plan_id=plan_id,
        extra_fields={
            "operation": "plan_execution_completion",
            "plan_type": plan_type,
            "success": success,
            "execution_duration_seconds": execution_duration,
        }
    )