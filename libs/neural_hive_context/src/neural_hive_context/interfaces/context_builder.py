"""
Context Builder Interface

Interface abstrata para construção de RichContext.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any
from neural_hive_context.models.rich_context import RichContext


class IContextBuilder(ABC):
    """
    Interface para construção de RichContext.

    Implementações devem agregar múltiplas dimensões de contexto
    (intent, sistema, temporal, segurança, conversação).

    Performance Target: <50ms p95
    """

    @abstractmethod
    async def build(self, intent_data: Dict[str, Any], user_context: Dict[str, Any]) -> RichContext:
        """
        Constrói RichContext agregando múltiplas dimensões.

        Args:
            intent_data: Dados do intent (texto, tipo, entidades)
            user_context: Contexto do usuário (session, auth, etc)

        Returns:
            RichContext com todas as dimensões preenchidas

        Raises:
            ValueError: Se os dados de entrada estiverem inválidos
            TimeoutError: Se a construção exceder timeout

        Performance:
            - p95 target: 50ms
            - p99 target: 100ms
            - max: 200ms
        """
        pass
