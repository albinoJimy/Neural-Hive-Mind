"""Analyzer para ClickHouse queries."""

import logging
import re
from typing import Any

from .base import AnalysisResult, BaseAnalyzer, RecommendationType, Severity, TargetType

logger = logging.getLogger(__name__)


class ClickHouseAnalyzer(BaseAnalyzer):
    """Analyzer para otimização de queries ClickHouse."""

    def __init__(self):
        super().__init__()
        self.target_type = TargetType.CLICKHOUSE

    def supports(self, target_type: str) -> bool:
        return target_type.lower() in ["clickhouse", "ch"]

    async def analyze(self, context: dict[str, Any]) -> AnalysisResult:
        """Analisa query ClickHouse."""
        issues = []
        query = context.get("query", "")

        if "SELECT" in query.upper() and "SAMPLE" not in query.upper():
            issues.append(
                {
                    "type": RecommendationType.QUERY_OPTIMIZE,
                    "severity": Severity.LOW,
                    "description": "SELECT sem SAMPLE: considere amostragem",
                    "estimated_improvement_pct": 40.0,
                    "target_type": TargetType.CLICKHOUSE,
                }
            )

        if re.search(r"SELECT\s+\*", query, re.IGNORECASE):
            issues.append(
                {
                    "type": RecommendationType.QUERY_OPTIMIZE,
                    "severity": Severity.HIGH,
                    "description": "SELECT * detectado: especifique colunas",
                    "estimated_improvement_pct": 35.0,
                    "target_type": TargetType.CLICKHOUSE,
                }
            )

        return AnalysisResult(
            issues=issues, metrics={"query_length": len(query)}, analyzed_at="now"
        )
