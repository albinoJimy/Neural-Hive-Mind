"""Modelos de dados para Learning Documentation Generator"""

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class DocumentFormat(str, Enum):
    """Formatos de documento suportados"""

    MARKDOWN = "markdown"
    PDF = "pdf"
    HTML = "html"


class DocumentType(str, Enum):
    """Tipos de documento"""

    EXPERIMENT_REPORT = "experiment_report"
    WEEKLY_SUMMARY = "weekly_summary"
    MONTHLY_SUMMARY = "monthly_summary"
    DAILY_SUMMARY = "daily_summary"
    PROMOTION_REPORT = "promotion_report"
    ROLLBACK_ANALYSIS = "rollback_analysis"


class DocumentStatus(str, Enum):
    """Status do documento"""

    PENDING = "pending"
    GENERATING = "generating"
    COMPLETED = "completed"
    FAILED = "failed"


class InsightConfidence(str, Enum):
    """Níveis de confiança para insights"""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ExperimentMetric(BaseModel):
    """Métrica de experimento"""

    name: str = Field(..., description="Nome da métrica")
    value: float = Field(..., description="Valor da métrica")
    step: Optional[int] = Field(default=None, description="Step da métrica")
    timestamp: Optional[datetime] = Field(default=None, description="Timestamp da métrica")


class ExperimentParameter(BaseModel):
    """Parâmetro de experimento"""

    name: str = Field(..., description="Nome do parâmetro")
    value: Any = Field(..., description="Valor do parâmetro")


class ExperimentRun(BaseModel):
    """Run de experimento MLflow"""

    run_id: str = Field(..., description="ID do run MLflow")
    experiment_id: int = Field(..., description="ID do experimento")
    name: str = Field(..., description="Nome do run")
    status: str = Field(..., description="Status do run")
    start_time: Optional[datetime] = Field(default=None, description="Data de início")
    end_time: Optional[datetime] = Field(default=None, description="Data de fim")
    metrics: dict[str, float] = Field(default_factory=dict, description="Métricas")
    params: dict[str, Any] = Field(default_factory=dict, description="Parâmetros")
    tags: dict[str, str] = Field(default_factory=dict, description="Tags")
    artifact_uri: Optional[str] = Field(default=None, description="URI dos artefatos")


class Insight(BaseModel):
    """Insight extraído de experimentos"""

    title: str = Field(..., description="Título do insight")
    description: str = Field(..., description="Descrição detalhada")
    evidence: dict[str, Any] = Field(..., description="Evidências/métricas")
    confidence: InsightConfidence = Field(..., description="Nível de confiança")
    experiment_ids: list[str] = Field(
        default_factory=list, description="IDs dos experimentos relacionados"
    )
    category: Optional[str] = Field(default=None, description="Categoria do insight")


class LearningDocument(BaseModel):
    """Documento de aprendizado gerado"""

    id: Optional[str] = Field(default=None, description="ID do documento (MongoDB)")
    title: str = Field(..., description="Título do documento")
    type: DocumentType = Field(..., description="Tipo do documento")
    status: DocumentStatus = Field(default=DocumentStatus.PENDING, description="Status")
    format: DocumentFormat = Field(default=DocumentFormat.MARKDOWN, description="Formato")

    # Metadados
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Data de criação")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="Data de atualização")
    generated_at: Optional[datetime] = Field(default=None, description="Data de geração")

    # Período coberto
    period_start: Optional[datetime] = Field(default=None, description="Início do período")
    period_end: Optional[datetime] = Field(default=None, description="Fim do período")

    # Conteúdo
    summary: str = Field(default="", description="Resumo executivo")
    insights: list[Insight] = Field(default_factory=list, description="Insights extraídos")
    experiment_runs: list[ExperimentRun] = Field(
        default_factory=list, description="Experimentos analisados"
    )

    # Recomendações
    recommendations: list[str] = Field(default_factory=list, description="Recomendações geradas")

    # Arquivos
    markdown_content: Optional[str] = Field(default=None, description="Conteúdo Markdown")
    pdf_path: Optional[str] = Field(default=None, description="Caminho do PDF")
    plots: list[str] = Field(default_factory=list, description="Caminhos dos gráficos")

    # Metadados adicionais
    metadata: dict[str, Any] = Field(default_factory=dict, description="Metadados adicionais")

    # Template
    template_version: str = Field(default="1.0.0", description="Versão do template")

    class Config:
        use_enum_values = False


class DocumentGenerationRequest(BaseModel):
    """Request para geração de documento"""

    type: DocumentType = Field(..., description="Tipo de documento")
    title: Optional[str] = Field(default=None, description="Título personalizado")

    # Filtros de experimentos
    experiment_ids: Optional[list[str]] = Field(
        default=None, description="IDs específicos de experimentos"
    )
    experiment_name_pattern: Optional[str] = Field(
        default=None, description="Pattern para filtrar por nome"
    )

    # Período
    period_start: Optional[datetime] = Field(default=None, description="Início do período")
    period_end: Optional[datetime] = Field(default=None, description="Fim do período")

    # Formato
    format: DocumentFormat = Field(default=DocumentFormat.MARKDOWN, description="Formato")

    # Opções
    include_plots: bool = Field(default=True, description="Incluir gráficos")
    plot_format: str = Field(default="png", description="Formato dos gráficos")

    # Metadados
    metadata: dict[str, Any] = Field(default_factory=dict, description="Metadados adicionais")


class DocumentGenerationResponse(BaseModel):
    """Response para geração de documento"""

    document_id: str = Field(..., description="ID do documento gerado")
    status: DocumentStatus = Field(..., description="Status")
    message: str = Field(..., description="Mensagem")
    download_url: Optional[str] = Field(default=None, description="URL de download")


class DocumentListResponse(BaseModel):
    """Response para listagem de documentos"""

    total: int = Field(..., description="Total de documentos")
    page: int = Field(..., description="Página atual")
    page_size: int = Field(..., description="Tamanho da página")
    documents: list[LearningDocument] = Field(..., description="Documentos")
