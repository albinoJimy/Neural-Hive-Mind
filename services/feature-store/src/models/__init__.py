"""Models package"""

# Import lineage models FIRST to resolve forward references in FeatureVector
from .feature import (
    ComputationStatus,
    EmbeddingFeatures,
    FeatureComputationRequest,
    FeatureListResponse,
    FeatureMetrics,
    FeatureResponse,
    FeatureSource,
    FeatureVector,
    GraphFeatures,
    HealthResponse,
    MetadataFeatures,
    OntologyFeatures,
)
from .lineage import (
    FeatureLineage,
    LineageImpact,
    LineageIntegrityReport,
    LineageMetadata,
    LineageTree,
    SourceType,
    TransformationType,
    compute_computation_hash,
)

# Resolve forward references in FeatureVector
FeatureVector.model_rebuild()

__all__ = [
    # Lineage models (first to resolve forward refs)
    "SourceType",
    "TransformationType",
    "LineageMetadata",
    "FeatureLineage",
    "LineageTree",
    "LineageImpact",
    "LineageIntegrityReport",
    "compute_computation_hash",
    # Feature models
    "FeatureSource",
    "ComputationStatus",
    "MetadataFeatures",
    "OntologyFeatures",
    "GraphFeatures",
    "EmbeddingFeatures",
    "FeatureVector",
    "FeatureComputationRequest",
    "FeatureResponse",
    "FeatureListResponse",
    "HealthResponse",
    "FeatureMetrics",
]
