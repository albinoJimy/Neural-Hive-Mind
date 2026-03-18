"""Analyzer para Redis usage patterns."""
import logging
from typing import Any, Dict

from .base import BaseAnalyzer, AnalysisResult, RecommendationType, Severity, TargetType

logger = logging.getLogger(__name__)


class RedisAnalyzer(BaseAnalyzer):
    """Analyzer para otimização de uso Redis."""

    def __init__(self):
        super().__init__()
        self.target_type = TargetType.REDIS

    def supports(self, target_type: str) -> bool:
        return target_type.lower() in ["redis", "cache"]

    async def analyze(self, context: Dict[str, Any]) -> AnalysisResult:
        """Analisa padrões de uso Redis."""
        issues = []
        keys = context.get("keys", [])

        for key_info in keys:
            if isinstance(key_info, dict):
                ttl = key_info.get("ttl", -1)
                if ttl == -1:
                    issues.append({
                        "type": RecommendationType.TTL_OPTIMIZATION,
                        "severity": Severity.LOW,
                        "description": f"Chave '{key_info.get('key')}' sem TTL",
                        "estimated_improvement_pct": 20.0,
                        "target_type": TargetType.REDIS,
                    })

        return AnalysisResult(issues=issues, metrics={"analyzed_keys": len(keys)}, analyzed_at="now")
