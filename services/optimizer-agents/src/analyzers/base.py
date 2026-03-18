"""Analyzer base para otimização."""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from dataclasses import dataclass
from enum import Enum


class RecommendationType(str, Enum):
    """Tipo de recomendação."""
    REDUCE_COMPLEXITY = "reduce_complexity"
    SPLIT_FUNCTION = "split_function"
    ADD_CACHING = "add_caching"
    REFACTOR = "refactor"
    QUERY_OPTIMIZE = "query_optimize"
    INDEX_SUGGESTION = "index_suggestion"
    KEY_PATTERN = "key_pattern"
    TTL_OPTIMIZATION = "ttl_optimization"
    PARTITIONING = "partitioning"


class Severity(str, Enum):
    """Nível de severidade."""
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TargetType(str, Enum):
    """Tipo de target da otimização."""
    CODE = "code"
    MONGODB = "mongodb"
    POSTGRESQL = "postgresql"
    NEO4J = "neo4j"
    REDIS = "redis"
    CLICKHOUSE = "clickhouse"


@dataclass
class AnalysisResult:
    """Resultado de uma análise."""
    issues: List[Dict[str, Any]]
    metrics: Dict[str, Any]
    analyzed_at: str


class BaseAnalyzer(ABC):
    """Analyzer base para otimização de código e queries."""

    def __init__(self):
        """Inicializa analyzer."""
        self.target_type: TargetType = TargetType.CODE

    @abstractmethod
    async def analyze(self, context: Dict[str, Any]) -> AnalysisResult:
        """Executa análise."""
        pass

    @abstractmethod
    def supports(self, target_type: str) -> bool:
        """Verifica se o analyzer suporta o tipo de target."""
        pass
