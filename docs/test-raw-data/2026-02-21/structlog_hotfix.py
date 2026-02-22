"""
Structlog Configuration Hotfix

Configura structlog para输出 logs corretamente nos serviços.
Este módulo deve ser importado antes de qualquer uso de structlog.get_logger().
"""
import structlog
import logging
import sys

def configure_structlog_for_neural_hive():
    """
    Configura structlog com processadores que outputam logs corretamente.

    Esta função deve ser chamada no início do módulo main.py dos serviços
    (STE, Consensus, Orchestrator) antes de usar structlog.get_logger().
    """
    # Configurar nível de log padrão
    log_level_name = "INFO"
    log_level = getattr(logging, log_level_name.upper(), logging.INFO)

    # Configurar root logger padrão
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Remover handlers existentes do root logger
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Criar handler para console stdout
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)

    # Formatter simples
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # Configurar loggers de bibliotecas externas para WARNING (reduzir noise)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("opentelemetry").setLevel(logging.WARNING)
    logging.getLogger("pymongo").setLevel(logging.WARNING)
    logging.getLogger("pymongo.serverSelection").setLevel(logging.WARNING)
    logging.getLogger("pymongo.connection").setLevel(logging.WARNING)
    logging.getLogger("pymongo.command").setLevel(logging.WARNING)

    # Configurar structlog
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
            # JSONRenderer para logs estruturados em produção
            structlog.processors.JSONRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

# Auto-executar quando importado
configure_structlog_for_neural_hive()
