"""
Interface IContextManager

Define o contrato para serviços de gerenciamento de contexto.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from neural_hive_context.models import (
    RichContext,
    WorkflowClassification,
)


class IContextManager(ABC):
    """
    Interface para serviços de gerenciamento de contexto.

    Define métodos para criar, enriquecer e gerenciar contextos de decisão.
    """

    @abstractmethod
    async def create_context(
        self,
        intent_text: str,
        intent_id: str,
        user_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        additional_context: Optional[Dict[str, Any]] = None,
    ) -> RichContext:
        """
        Cria RichContext completo a partir do intent do usuário.

        Args:
            intent_text: Texto do intent do usuário
            intent_id: ID único do intent
            user_id: ID do usuário (opcional)
            conversation_id: ID da conversa (opcional)
            additional_context: Contexto adicional (opcional)

        Returns:
            RichContext com todas as dimensões preenchidas
        """
        pass

    @abstractmethod
    async def classify_workflow(self, context: RichContext) -> WorkflowClassification:
        """
        Classifica o workflow baseado no RichContext.

        Args:
            context: RichContext com todas as dimensões

        Returns:
            WorkflowClassification com decisão e justificativa
        """
        pass

    @abstractmethod
    async def create_and_classify(
        self,
        intent_text: str,
        intent_id: str,
        user_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        additional_context: Optional[Dict[str, Any]] = None,
    ) -> tuple[RichContext, WorkflowClassification]:
        """
        Cria contexto e classifica workflow em uma única chamada.

        Args:
            intent_text: Texto do intent do usuário
            intent_id: ID único do intent
            user_id: ID do usuário (opcional)
            conversation_id: ID da conversa (opcional)
            additional_context: Contexto adicional (opcional)

        Returns:
            Tupla (RichContext, WorkflowClassification)
        """
        pass

    @abstractmethod
    async def enrich_cognitive_plan(
        self,
        cognitive_plan: Dict[str, Any],
        context: RichContext,
        classification: WorkflowClassification,
    ) -> Dict[str, Any]:
        """
        Enriquece CognitivePlan com campos do Context Layer.

        Args:
            cognitive_plan: CognitivePlan base (dict)
            context: RichContext da decisão
            classification: WorkflowClassification resultante

        Returns:
            CognitivePlan enriquecido com campos de workflow
        """
        pass
