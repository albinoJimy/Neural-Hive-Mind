"""
Modelos de Dados para Feature Store

Define os modelos Pydantic para armazenamento e computação de features.
"""

import uuid
from datetime import datetime
from typing import Dict, List, Any, Optional, Literal
from enum import Enum
from pydantic import BaseModel, Field, field_validator


class FeatureSource(str, Enum):
    """Fontes de features"""
    METADATA = "metadata"
    ONTOLOGY = "ontology"
    GRAPH = "graph"
    EMBEDDING = "embedding"


class ComputationStatus(str, Enum):
    """Status da computação de features"""
    PENDING = "pending"
    COMPUTING = "computing"
    COMPLETED = "completed"
    FAILED = "failed"


# Metadata Features
class MetadataFeatures(BaseModel):
    """Features extraídas dos metadados do plano"""
    num_tasks: int = Field(..., description="Número de tarefas no plano")
    priority_score: float = Field(..., ge=0.0, le=1.0, description="Score de prioridade")
    total_duration_ms: Optional[float] = Field(None, description="Duração total estimada")
    avg_duration_ms: Optional[float] = Field(None, description="Duração média por tarefa")
    risk_score: Optional[float] = Field(None, ge=0.0, le=1.0, description="Score de risco")
    complexity_score: Optional[float] = Field(None, description="Score de complexidade")


# Ontology Features
class OntologyFeatures(BaseModel):
    """Features extraídas da ontologia do plano"""
    domain_risk_weight: Optional[float] = Field(None, ge=0.0, le=1.0, description="Peso de risco do domínio")
    avg_task_complexity_factor: Optional[float] = Field(None, description="Fator médio de complexidade")
    num_patterns_detected: Optional[int] = Field(None, ge=0, description="Número de padrões detectados")
    num_anti_patterns_detected: Optional[int] = Field(None, ge=0, description="Número de anti-padrões")
    avg_pattern_quality: Optional[float] = Field(None, ge=0.0, le=1.0, description="Qualidade média dos padrões")
    total_anti_pattern_penalty: Optional[float] = Field(None, description="Penalidade total de anti-padrões")


# Graph Features
class GraphFeatures(BaseModel):
    """Features extraídas do grafo de dependências"""
    num_nodes: Optional[int] = Field(None, ge=0, description="Número de nós")
    num_edges: Optional[int] = Field(None, ge=0, description="Número de arestas")
    density: Optional[float] = Field(None, ge=0.0, le=1.0, description="Densidade do grafo")
    avg_in_degree: Optional[float] = Field(None, ge=0.0, description="Grau de entrada médio")
    max_in_degree: Optional[int] = Field(None, ge=0, description="Grau de entrada máximo")
    critical_path_length: Optional[int] = Field(None, ge=0, description="Comprimento do caminho crítico")
    max_parallelism: Optional[int] = Field(None, ge=0, description="Paralelismo máximo")
    num_levels: Optional[int] = Field(None, ge=0, description="Número de níveis no DAG")
    avg_coupling: Optional[float] = Field(None, ge=0.0, description="Acoplamento médio")
    num_bottlenecks: Optional[int] = Field(None, ge=0, description="Número de gargalos")
    graph_complexity_score: Optional[float] = Field(None, ge=0.0, le=1.0, description="Score de complexidade")


# Embedding Features
class EmbeddingFeatures(BaseModel):
    """Features extraídas dos embeddings"""
    mean_norm: Optional[float] = Field(None, ge=0.0, description="Norma média dos embeddings")
    std_norm: Optional[float] = Field(None, ge=0.0, description="Desvio padrão da norma")
    avg_diversity: Optional[float] = Field(None, ge=0.0, le=1.0, description="Diversidade média")


# Feature Vector completo
class FeatureVector(BaseModel):
    """Vetor completo de features para um plano"""
    # Metadados
    feature_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    plan_id: str = Field(..., description="ID do plano cognitivo")
    computed_at: datetime = Field(default_factory=datetime.utcnow)

    # Features por categoria
    metadata: MetadataFeatures
    ontology: Optional[OntologyFeatures] = None
    graph: Optional[GraphFeatures] = None
    embedding: Optional[EmbeddingFeatures] = None

    # Status
    computation_status: ComputationStatus = Field(
        default=ComputationStatus.COMPLETED,
        description="Status da computação"
    )
    computation_error: Optional[str] = Field(None, description="Erro na computação")

    # Cache metadata
    cache_hit: bool = Field(default=False, description="Se foi um cache hit")
    ttl_seconds: Optional[int] = Field(None, description="TTL do cache")

    class Config:
        use_enum_values = True


# Input para computação
class FeatureComputationRequest(BaseModel):
    """Request para computar features de um plano"""
    plan_id: str = Field(..., description="ID do plano")
    cognitive_plan: Dict[str, Any] = Field(..., description="Dados do plano cognitivo")
    force_recompute: bool = Field(default=False, description="Forçar recomputação")
    skip_cache: bool = Field(default=False, description="Pular cache")


# Response da API
class FeatureResponse(BaseModel):
    """Response padrão da API"""
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class FeatureListResponse(BaseModel):
    """Response para lista de features"""
    success: bool
    count: int
    features: List[Dict[str, Any]]
    message: str


# Health check
class HealthResponse(BaseModel):
    """Response de health check"""
    status: Literal["healthy", "unhealthy", "degraded"]
    service: str
    version: str
    timestamp: datetime
    dependencies: Dict[str, Literal["healthy", "unhealthy", "unknown"]]


# Métricas
class FeatureMetrics(BaseModel):
    """Métricas do Feature Store"""
    total_features: int
    cached_features: int
    computation_count: int
    avg_computation_time_ms: float
    cache_hit_rate: float
