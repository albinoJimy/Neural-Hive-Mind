"""
Feature Definitions: Define features estruturadas para modelos ML.

Centraliza definições de features, tipos, transformações e validações.
"""

from typing import Dict, List, Any
from dataclasses import dataclass
from enum import Enum


class FeatureType(Enum):
    """Tipos de features."""
    NUMERIC = "numeric"
    CATEGORICAL = "categorical"
    EMBEDDING = "embedding"
    BOOLEAN = "boolean"


@dataclass
class FeatureDefinition:
    """Definição de uma feature."""
    name: str
    feature_type: FeatureType
    description: str
    source: str  # metadata, ontology, graph, embedding
    nullable: bool = False
    default_value: Any = None
    validation_rules: Dict[str, Any] = None


# Features de Metadados
METADATA_FEATURES = [
    FeatureDefinition(
        name="num_tasks",
        feature_type=FeatureType.NUMERIC,
        description="Número de tarefas no plano",
        source="metadata"
    ),
    FeatureDefinition(
        name="priority_score",
        feature_type=FeatureType.NUMERIC,
        description="Score numérico de prioridade (0.0-1.0)",
        source="metadata",
        validation_rules={"min": 0.0, "max": 1.0}
    ),
    FeatureDefinition(
        name="total_duration_ms",
        feature_type=FeatureType.NUMERIC,
        description="Duração total estimada em milissegundos",
        source="metadata"
    ),
    FeatureDefinition(
        name="avg_duration_ms",
        feature_type=FeatureType.NUMERIC,
        description="Duração média por tarefa",
        source="metadata"
    ),
    FeatureDefinition(
        name="risk_score",
        feature_type=FeatureType.NUMERIC,
        description="Score de risco do plano",
        source="metadata",
        nullable=True,
        validation_rules={"min": 0.0, "max": 1.0}
    ),
    FeatureDefinition(
        name="complexity_score",
        feature_type=FeatureType.NUMERIC,
        description="Score de complexidade do plano",
        source="metadata",
        nullable=True
    )
]

# Features de Ontologia
ONTOLOGY_FEATURES = [
    FeatureDefinition(
        name="domain_risk_weight",
        feature_type=FeatureType.NUMERIC,
        description="Peso de risco do domínio",
        source="ontology",
        validation_rules={"min": 0.0, "max": 1.0}
    ),
    FeatureDefinition(
        name="avg_task_complexity_factor",
        feature_type=FeatureType.NUMERIC,
        description="Fator médio de complexidade de tarefas",
        source="ontology"
    ),
    FeatureDefinition(
        name="num_patterns_detected",
        feature_type=FeatureType.NUMERIC,
        description="Número de padrões arquiteturais detectados",
        source="ontology"
    ),
    FeatureDefinition(
        name="num_anti_patterns_detected",
        feature_type=FeatureType.NUMERIC,
        description="Número de anti-padrões detectados",
        source="ontology"
    ),
    FeatureDefinition(
        name="avg_pattern_quality",
        feature_type=FeatureType.NUMERIC,
        description="Qualidade média dos padrões detectados",
        source="ontology",
        validation_rules={"min": 0.0, "max": 1.0}
    ),
    FeatureDefinition(
        name="total_anti_pattern_penalty",
        feature_type=FeatureType.NUMERIC,
        description="Penalidade total de anti-padrões",
        source="ontology"
    )
]

# Features de Grafo
GRAPH_FEATURES = [
    FeatureDefinition(
        name="num_nodes",
        feature_type=FeatureType.NUMERIC,
        description="Número de nós no grafo",
        source="graph"
    ),
    FeatureDefinition(
        name="num_edges",
        feature_type=FeatureType.NUMERIC,
        description="Número de arestas no grafo",
        source="graph"
    ),
    FeatureDefinition(
        name="density",
        feature_type=FeatureType.NUMERIC,
        description="Densidade do grafo",
        source="graph",
        validation_rules={"min": 0.0, "max": 1.0}
    ),
    FeatureDefinition(
        name="avg_in_degree",
        feature_type=FeatureType.NUMERIC,
        description="Grau de entrada médio",
        source="graph"
    ),
    FeatureDefinition(
        name="max_in_degree",
        feature_type=FeatureType.NUMERIC,
        description="Grau de entrada máximo",
        source="graph"
    ),
    FeatureDefinition(
        name="critical_path_length",
        feature_type=FeatureType.NUMERIC,
        description="Comprimento do caminho crítico",
        source="graph"
    ),
    FeatureDefinition(
        name="max_parallelism",
        feature_type=FeatureType.NUMERIC,
        description="Paralelismo máximo possível",
        source="graph"
    ),
    FeatureDefinition(
        name="num_levels",
        feature_type=FeatureType.NUMERIC,
        description="Número de níveis no DAG",
        source="graph"
    ),
    FeatureDefinition(
        name="avg_coupling",
        feature_type=FeatureType.NUMERIC,
        description="Acoplamento médio",
        source="graph"
    ),
    FeatureDefinition(
        name="num_bottlenecks",
        feature_type=FeatureType.NUMERIC,
        description="Número de gargalos identificados",
        source="graph"
    ),
    FeatureDefinition(
        name="graph_complexity_score",
        feature_type=FeatureType.NUMERIC,
        description="Score de complexidade do grafo",
        source="graph",
        validation_rules={"min": 0.0, "max": 1.0}
    )
]

# Features de Embeddings
EMBEDDING_FEATURES = [
    FeatureDefinition(
        name="mean_norm",
        feature_type=FeatureType.NUMERIC,
        description="Norma média dos embeddings",
        source="embedding"
    ),
    FeatureDefinition(
        name="std_norm",
        feature_type=FeatureType.NUMERIC,
        description="Desvio padrão da norma",
        source="embedding"
    ),
    FeatureDefinition(
        name="avg_diversity",
        feature_type=FeatureType.NUMERIC,
        description="Diversidade média entre embeddings",
        source="embedding"
    )
]

# Todas as features
ALL_FEATURES = (
    METADATA_FEATURES +
    ONTOLOGY_FEATURES +
    GRAPH_FEATURES +
    EMBEDDING_FEATURES
)


def get_feature_schema() -> Dict[str, Any]:
    """Retorna schema de features para MLflow."""
    schema = {}
    for feature in ALL_FEATURES:
        schema[feature.name] = {
            'type': feature.feature_type.value,
            'description': feature.description,
            'source': feature.source,
            'nullable': feature.nullable,
            'validation_rules': feature.validation_rules or {}
        }
    return schema


def get_feature_names() -> List[str]:
    """Retorna lista de nomes de features."""
    return [f.name for f in ALL_FEATURES]
