"""Analyzer para Neo4j Cypher queries."""

import logging
import re
from typing import Any

from .base import AnalysisResult, BaseAnalyzer, RecommendationType, Severity, TargetType

logger = logging.getLogger(__name__)


class Neo4jAnalyzer(BaseAnalyzer):
    """Analyzer para otimização de queries Cypher Neo4j."""

    def __init__(self):
        super().__init__()
        self.target_type = TargetType.NEO4J

    def supports(self, target_type: str) -> bool:
        return target_type.lower() in ["neo4j", "cypher", "graph"]

    async def analyze(self, context: dict[str, Any]) -> AnalysisResult:
        """Analisa query Cypher."""
        issues = []
        metrics = {"query_length": len(context.get("query", ""))}

        query = context.get("query", "")

        if re.search(r"MATCH\s+\([^)]+\)\s+RETURN", query, re.IGNORECASE):
            if "WHERE" not in query.upper():
                issues.append(
                    {
                        "type": RecommendationType.QUERY_OPTIMIZE,
                        "severity": Severity.MEDIUM,
                        "description": "MATCH sem filtro: pode retornar muitos nós",
                        "estimated_improvement_pct": 50.0,
                        "target_type": TargetType.NEO4J,
                    }
                )

        return AnalysisResult(issues=issues, metrics=metrics, analyzed_at="now")
