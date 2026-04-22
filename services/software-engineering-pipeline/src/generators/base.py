from abc import ABC, abstractmethod

from pydantic import BaseModel, ConfigDict, Field


class GeneratedPipeline(BaseModel):
    """Pipeline CI/CD gerado."""

    model_config = ConfigDict(extra="forbid")

    content: str = Field(description="Conteúdo YAML do pipeline gerado")
    filename: str = Field(description="Nome do arquivo de configuração")
    description: str = Field(description="Descrição do pipeline gerado")


class BasePipelineGenerator(ABC):
    """Classe base para geradores de pipeline CI/CD."""

    @abstractmethod
    async def generate(self, config: dict) -> GeneratedPipeline:
        """Gera uma configuração de pipeline.

        Args:
            config: Dicionário com configurações do projeto

        Returns:
            GeneratedPipeline com conteúdo YAML gerado
        """

    @abstractmethod
    def get_filename(self) -> str:
        """Retorna o nome padrão do arquivo para este tipo de pipeline."""
