"""
Logging configurado com PII masking para Approval Service.

GDPR/LGPD compliance - Artigo 25: Privacy by Design
"""

import structlog
from neural_hive_observability import mask_pii_processor


def configure_logging_with_pii_masking():
    """
    Configura structlog com processor de masking de PII.

    Campos como user_id e email são automaticamente mascarados
    nos logs usando hash SHA-256.

    O campo original user_id é substituído por hash truncado,
    e um campo user_id_hash é adicionado para correlação.
    """
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.dev.set_exc_info,
            mask_pii_processor,  # <-- PII masking aqui
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(20),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = None):
    """Retorna logger com PII masking configurado."""
    return structlog.get_logger(name)
