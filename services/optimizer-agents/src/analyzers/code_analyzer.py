"""Analyzer para código Python."""

import ast
import logging
from typing import Any

from .base import AnalysisResult, BaseAnalyzer, RecommendationType, Severity, TargetType

logger = logging.getLogger(__name__)


class CodeAnalyzer(BaseAnalyzer):
    """Analyzer para otimização de código Python."""

    def __init__(self):
        super().__init__()
        self.target_type = TargetType.CODE

    def supports(self, target_type: str) -> bool:
        return target_type.lower() in ["code", "python", "py"]

    async def analyze(self, context: dict[str, Any]) -> AnalysisResult:
        """Analisa código Python."""
        issues = []
        metrics = {"analyzed_functions": 0}

        code = context.get("code", "")
        if not code:
            return AnalysisResult(issues=issues, metrics=metrics, analyzed_at="now")

        try:
            tree = ast.parse(code)
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    metrics["analyzed_functions"] += 1
                    complexity = self._calculate_complexity(node)
                    if complexity > 15:
                        issues.append(
                            {
                                "type": RecommendationType.REDUCE_COMPLEXITY,
                                "severity": Severity.CRITICAL if complexity > 25 else Severity.HIGH,
                                "description": f"Função '{node.name}' tem complexidade {complexity}",
                                "estimated_improvement_pct": min(50, complexity * 2),
                                "target_type": TargetType.CODE,
                                "file_path": context.get("file_path"),
                                "line_number": node.lineno,
                            }
                        )

        except SyntaxError:
            pass

        return AnalysisResult(issues=issues, metrics=metrics, analyzed_at="now")

    def _calculate_complexity(self, node: ast.FunctionDef) -> int:
        """Calcula complexidade ciclomática."""
        complexity = 1
        for child in ast.walk(node):
            if isinstance(child, (ast.If, ast.While, ast.For)):
                complexity += 1
        return complexity
