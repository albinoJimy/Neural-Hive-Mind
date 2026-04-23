"""
Workflow Classifier Interface

Interface abstrata para classificação de workflow.
"""

from abc import ABC, abstractmethod
from neural_hive_context.models.rich_context import RichContext
from neural_hive_context.models.workflow import WorkflowClassification


class IWorkflowClassifier(ABC):
    """
    Interface para classificação de workflow.

    Implementações devem decidir entre ORCHESTRATION e GENERATION
    baseado no RichContext fornecido.
    """

    @abstractmethod
    async def classify(self, context: RichContext) -> WorkflowClassification:
        """
        Classifica o workflow apropriado para o contexto fornecido.

        Args:
            context: RichContext com todas as dimensões de contexto

        Returns:
            WorkflowClassification contendo:
            - workflow_type: ORCHESTRATION ou GENERATION
            - confidence: 0.0 a 1.0
            - reasoning: Explicação da decisão
            - signals: Sinais extraídos e seus pesos

        Raises:
            ValueError: Se o contexto estiver inválido
            TimeoutError: Se a classificação exceder timeout
        """
        pass
