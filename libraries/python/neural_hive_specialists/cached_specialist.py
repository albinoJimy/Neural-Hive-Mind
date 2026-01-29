"""
Classe CachedSpecialist: especialista neural com cache de opinião habilitado.

Esta classe é uma subclasse leve de BaseSpecialist que garante que
o cache de opinião está habilitado.
"""

from .base_specialist import BaseSpecialist
from .config import SpecialistConfig
import structlog

logger = structlog.get_logger(__name__)


class CachedSpecialist(BaseSpecialist):
    """
    Especialista neural com cache de opinião obrigatório.

    Esta classe herda de BaseSpecialist e apenas valida que
    opinion_cache_enabled=True na configuração.

    Uso:
        config = SpecialistConfig(
            specialist_type='technical',
            opinion_cache_enabled=True,
            ...
        )
        specialist = CachedSpecialist(config)
    """

    def __init__(self, config: SpecialistConfig):
        """
        Inicializa CachedSpecialist.

        Args:
            config: Configuração do especialista

        Raises:
            ValueError: Se opinion_cache_enabled não estiver True
        """
        # Validar que cache está habilitado
        if not config.opinion_cache_enabled:
            raise ValueError(
                "CachedSpecialist requer opinion_cache_enabled=True na configuração. "
                "Use BaseSpecialist se cache não for necessário."
            )

        # Chamar __init__ do BaseSpecialist
        super().__init__(config)

        logger.info(
            "CachedSpecialist initialized",
            specialist_type=self.specialist_type,
            cache_enabled=config.opinion_cache_enabled,
            cache_ttl_seconds=config.opinion_cache_ttl_seconds,
        )
