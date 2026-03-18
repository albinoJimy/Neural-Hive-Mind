"""Analyzer para PostgreSQL queries."""
import logging
import re
from typing import Any, Dict

from .base import BaseAnalyzer, AnalysisResult, RecommendationType, Severity, TargetType

logger = logging.getLogger(__name__)


class PostgreSQLAnalyzer(BaseAnalyzer):
    """Analyzer para otimização de queries PostgreSQL."""

    def __init__(self):
        super().__init__()
        self.target_type = TargetType.POSTGRESQL

    def supports(self, target_type: str) -> bool:
        return target_type.lower() in ["postgresql", "postgres", "psql"]

    async def analyze(self, context: Dict[str, Any]) -> AnalysisResult:
        """Analisa query PostgreSQL."""
        issues = []
        metrics = {"query_length": 0}

        query = context.get("query", "")
        if not query:
            return AnalysisResult(issues=issues, metrics=metrics, analyzed_at="now")

        metrics["query_length"] = len(query)

        if re.search(r"SELECT\s+\*\s+FROM", query, re.IGNORECASE):
            issues.append({
                "type": RecommendationType.QUERY_OPTIMIZE,
                "severity": Severity.HIGH,
                "description": "SELECT * detectado: especifique colunas",
                "estimated_improvement_pct": 25.0,
                "target_type": TargetType.POSTGRESQL,
            })

        if "ORDER BY" in query.upper() and "LIMIT" not in query.upper():
            issues.append({
                "type": RecommendationType.QUERY_OPTIMIZE,
                "severity": Severity.MEDIUM,
                "description": "ORDER BY sem LIMIT: adicione LIMIT",
                "estimated_improvement_pct": 20.0,
                "target_type": TargetType.POSTGRESQL,
            })

        return AnalysisResult(issues=issues, metrics=metrics, analyzed_at="now")
