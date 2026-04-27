"""
Modelos de Lineage para Feature Store

Define modelos Pydantic para rastreamento de origem e transformações de features.
"""

import hashlib
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.functional_serializers import field_serializer


class SourceType(str, Enum):
    """Tipo de origem da feature"""

    COGNITIVE_PLAN = "cognitive_plan"
    """Feature derivada diretamente de um plano cognitivo"""

    DERIVED = "derived"
    """Feature derivada de outras features"""

    AGGREGATED = "aggregated"
    """Feature agregada de múltiplas fontes"""

    ENRICHED = "enriched"
    """Feature enriquecida com dados externos"""

    CACHED = "cached"
    """Feature recuperada de cache"""


class TransformationType(str, Enum):
    """Tipo de transformação aplicada"""

    COMPUTED = "computed"
    """Feature computada via pipeline padrão"""

    MERGED = "merged"
    """Feature resultante de merge de múltiplas features"""

    FILTERED = "filtered"
    """Feature resultante de filtros aplicados"""

    ENRICHED = "enriched"
    """Feature enriquecida com dados externos"""

    AGGREGATED = "aggregated"
    """Feature agregada (sum, avg, count, etc.)"""

    TRANSFORMED = "transformed"
    """Feature transformada (normalização, encoding, etc.)"""


class LineageMetadata(BaseModel):
    """Metadados adicionais do lineage"""

    computation_duration_ms: Optional[float] = Field(
        None, description="Duração da computação em milissegundos"
    )
    computation_node: Optional[str] = Field(None, description="Nó que realizou a computação")
    cache_key: Optional[str] = Field(None, description="Chave de cache utilizada")
    feature_version: Optional[str] = Field(None, description="Versão da feature")
    tags: list[str] = Field(default_factory=list, description="Tags para categorização")
    custom_metadata: dict[str, Any] = Field(
        default_factory=dict, description="Metadados customizados"
    )


class FeatureLineage(BaseModel):
    """
    Rastreamento de origem e transformações de features

    Permite acompanhar a proveniência de cada feature computada,
    incluindo fontes de dados, transformações aplicadas e dependências.
    """

    # Identificação
    lineage_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()), description="ID único do rastreamento"
    )
    feature_id: str = Field(..., description="ID da feature rastreada")
    plan_id: str = Field(..., description="ID do plano cognitivo associado")

    # Origem
    source_type: SourceType = Field(..., description="Tipo de origem da feature")
    source_plan_ids: list[str] = Field(
        default_factory=list, description="IDs dos planos originais (para features derivadas)"
    )
    data_sources: list[str] = Field(
        default_factory=list, description="Fontes de dados (mongodb, neo4j, redis, etc.)"
    )

    # Transformação
    transformation_type: TransformationType = Field(
        ..., description="Tipo de transformação aplicada"
    )
    computation_version: str = Field(
        default="v1.0.0", description="Versão do pipeline de computação"
    )
    computation_hash: str = Field(
        ..., description="Hash do código de computação para rastrear mudanças"
    )

    # Dependências
    feature_dependencies: list[str] = Field(
        default_factory=list, description="IDs de features que esta feature depende"
    )
    parent_lineage_ids: list[str] = Field(
        default_factory=list, description="IDs de lineage dos pais (para features derivadas)"
    )

    # Auditoria
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp de criação do lineage",
    )
    created_by: str = Field(
        default="feature-store-service", description="Serviço que criou o lineage"
    )
    modified_at: Optional[datetime] = Field(None, description="Última modificação do lineage")
    modified_count: int = Field(
        default=0, ge=0, description="Número de vezes que o lineage foi modificado"
    )

    # Metadados de transformação
    transformation_metadata: dict[str, Any] = Field(
        default_factory=dict, description="Metadados específicos da transformação"
    )

    # Metadados estendidos
    metadata: LineageMetadata = Field(
        default_factory=LineageMetadata, description="Metadados adicionais do lineage"
    )

    @field_validator("computation_hash")
    @classmethod
    def validate_hash_format(cls, v: str) -> str:
        """Valida formato do hash"""
        if len(v) < 8:
            raise ValueError("computation_hash deve ter pelo menos 8 caracteres")
        return v

    def mark_modified(self) -> None:
        """Marca o lineage como modificado"""
        self.modified_at = datetime.now(timezone.utc)
        self.modified_count += 1

    def add_dependency(self, feature_id: str) -> None:
        """Adiciona uma dependência de feature"""
        if feature_id not in self.feature_dependencies:
            self.feature_dependencies.append(feature_id)
            self.mark_modified()

    def add_parent_lineage(self, lineage_id: str) -> None:
        """Adiciona um lineage pai"""
        if lineage_id not in self.parent_lineage_ids:
            self.parent_lineage_ids.append(lineage_id)
            self.mark_modified()

    def add_data_source(self, source: str) -> None:
        """Adiciona uma fonte de dados"""
        if source not in self.data_sources:
            self.data_sources.append(source)

    model_config = ConfigDict(use_enum_values=True)

    @field_serializer("created_at", "modified_at")
    @classmethod
    def serialize_datetime(cls, dt: datetime) -> str:
        """Serialize datetime to ISO format"""
        return dt.isoformat() if dt else None


class LineageTree(BaseModel):
    """
    Representa a árvore completa de lineage de uma feature

    Inclui upstream (fontes) e downstream (derivadas).
    """

    feature_id: str = Field(..., description="ID da feature raiz")
    lineage: Optional[FeatureLineage] = Field(None, description="Metadados de lineage da feature")
    upstream: dict[str, list[dict[str, Any]]] = Field(
        default_factory=dict, description="Features upstream (fontes) por nível de profundidade"
    )
    downstream: dict[str, list[dict[str, Any]]] = Field(
        default_factory=dict,
        description="Features downstream (derivadas) por nível de profundidade",
    )
    tree_depth: int = Field(default=0, ge=0, description="Profundidade máxima da árvore")


class LineageImpact(BaseModel):
    """
    Resultado da análise de impacto de uma feature

    Indica quais features seriam afetadas se esta feature mudar.
    """

    feature_id: str = Field(..., description="ID da feature analisada")
    direct_dependencies: int = Field(
        default=0, ge=0, description="Número de dependências diretas (depth 1)"
    )
    total_downstream: int = Field(
        default=0, ge=0, description="Total de features downstream afetadas"
    )
    affected_plans: list[str] = Field(
        default_factory=list, description="IDs dos planos cognitivos afetados"
    )
    critical_path: list[str] = Field(
        default_factory=list, description="Caminho crítico de dependências"
    )
    impact_score: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Score de impacto (0=baixo, 1=crítico)"
    )


class LineageIntegrityReport(BaseModel):
    """
    Relatório de validação de integridade de lineage

    Resultado da validação de consistência e corretude do lineage.
    """

    feature_id: str = Field(..., description="ID da feature validada")
    has_cycle: bool = Field(default=False, description="Indica se foi detectado ciclo no grafo")
    timestamps_valid: bool = Field(
        default=True, description="Indica se os timestamps são consistentes"
    )
    datasources_consistent: bool = Field(
        default=True, description="Indica se as fontes de dados são consistentes"
    )
    all_sources_exist: bool = Field(default=True, description="Indica se todas as sources existem")
    valid: bool = Field(
        default=True, description="Indica se o lineage é válido (todas as checagens passaram)"
    )
    errors: list[str] = Field(default_factory=list, description="Lista de erros encontrados")
    warnings: list[str] = Field(default_factory=list, description="Lista de avisos")
    validation_timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), description="Timestamp da validação"
    )


def compute_computation_hash(code: str) -> str:
    """
    Computa hash do código de computação

    Args:
        code: Código fonte para computar hash

    Returns:
        Hash SHA256 truncado (16 caracteres)
    """
    return hashlib.sha256(code.encode()).hexdigest()[:16]
