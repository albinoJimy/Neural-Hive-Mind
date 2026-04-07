"""Analyzer para MongoDB queries e pipelines."""

import logging
from typing import Any

from .base import AnalysisResult, BaseAnalyzer, RecommendationType, Severity, TargetType

logger = logging.getLogger(__name__)


class MongoDBAnalyzer(BaseAnalyzer):
    """Analyzer para otimização de queries MongoDB."""

    def __init__(self):
        super().__init__()
        self.target_type = TargetType.MONGODB

    def supports(self, target_type: str) -> bool:
        return target_type.lower() in ["mongodb", "mongo"]

    async def analyze(self, context: dict[str, Any]) -> AnalysisResult:
        """Analisa query/pipeline MongoDB."""
        issues = []
        metrics = {"analyzed_elements": 0}

        pipeline = context.get("pipeline")
        query = context.get("query")
        collection = context.get("collection", "unknown")

        if pipeline:
            issues = self._analyze_pipeline(pipeline, collection)
            metrics["analyzed_elements"] = len(pipeline) if isinstance(pipeline, list) else 1
        elif query:
            issues = self._analyze_query(query, collection)
            metrics["analyzed_elements"] = 1

        return AnalysisResult(issues=issues, metrics=metrics, analyzed_at="now")

    def _analyze_pipeline(self, pipeline: Any, collection: str) -> list:
        """Analisa aggregation pipeline."""
        issues = []
        if not isinstance(pipeline, list):
            return issues

        for i, stage in enumerate(pipeline):
            if isinstance(stage, dict):
                if "$lookup" in stage:
                    issues.append(
                        {
                            "type": RecommendationType.INDEX_SUGGESTION,
                            "severity": Severity.MEDIUM,
                            "description": f"$lookup stage em {collection}.{i}: garanta índices",
                            "estimated_improvement_pct": 40.0,
                            "target_type": TargetType.MONGODB,
                        }
                    )
                if "$sort" in stage:
                    issues.append(
                        {
                            "type": RecommendationType.INDEX_SUGGESTION,
                            "severity": Severity.HIGH,
                            "description": f"$sort em {collection}.{i}: crie índice",
                            "estimated_improvement_pct": 60.0,
                            "target_type": TargetType.MONGODB,
                        }
                    )

        return issues

    def _analyze_query(self, query: Any, collection: str) -> list:
        """Analisa query simples."""
        issues = []
        if isinstance(query, dict) and query:
            issues.append(
                {
                    "type": RecommendationType.INDEX_SUGGESTION,
                    "severity": Severity.MEDIUM,
                    "description": f"Query em {collection}: verifique índices",
                    "estimated_improvement_pct": 50.0,
                    "target_type": TargetType.MONGODB,
                }
            )
        return issues
