"""
Configuracao de logging com PII masking para GDPR Erasure Service
"""

import structlog

try:
    from neural_hive_observability.privacy import mask_pii_processor

    HAS_OBSERVABILITY = True
except ImportError:
    # Fallback simples se neural_hive_observability nao estiver disponivel
    def mask_pii_processor(logger, log_method, event_dict):
        """Processador simples de masking"""
        # Mask user_id e email se presentes
        if "user_id" in event_dict:
            import hashlib

            user_id = event_dict["user_id"]
            if isinstance(user_id, str):
                event_dict["user_id_hash"] = hashlib.sha256(
                    user_id.encode()
                ).hexdigest()[:16]
                del event_dict["user_id"]
        if "email" in event_dict:
            email = event_dict["email"]
            if isinstance(email, str) and "@" in email:
                local, domain = email.split("@", 1)
                event_dict["email"] = f"{local[0]}***@{domain}"
        return event_dict

    HAS_OBSERVABILITY = False


def configure_logging_with_pii_masking():
    """Configura structlog com masking de PII"""
    processors = [
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        mask_pii_processor,
        structlog.processors.JSONRenderer(),
    ]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            structlog.get_logger().level
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
