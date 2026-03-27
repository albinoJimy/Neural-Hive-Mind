"""Motor principal de validação de arquitetura."""

import uuid
from typing import Dict, Any
from datetime import datetime, timezone
import structlog

from src.models.validation import (
    ValidationReport, Violation, Suggestion, ViolationType, Severity, Trend
)
from src.validators.base import BaseValidator
from src.validators.scout_client import ScoutAgentsClient
from src.validators.opa_client import OPAClient
from src.validators.rules import ArchitecturalRules

logger = structlog.get_logger(__name__)


class ValidateEngine(BaseValidator):
    """Motor de validação que integra Scout, OPA e regras SOLID."""

    def __init__(self) -> None:
        self.scout_client = ScoutAgentsClient()
        self.opa_client = OPAClient()
        self.rules = ArchitecturalRules()

    async def validate(self, target: Dict[str, Any]) -> ValidationReport:
        """Executa validação completa de arquitetura.

        Args:
            target: Dicionário com repo_url e opcionalmente branch

        Returns:
            ValidationReport com violações e sugestões
        """
        repo_url = target.get("repo_url", "")
        branch = target.get("branch", "main")

        # 1. Coletar dados do Scout
        patterns = await self._get_patterns_safe(repo_url, branch)
        insights = await self._get_insights_safe(repo_url, branch)
        duplication = await self._check_duplication_safe(repo_url, branch)

        # 2. Validar regras SOLID
        solid_violations = self.rules.validate_all(patterns, insights)

        # 3. Validar com OPA (se disponível)
        opa_violations = await self._check_opa_safe(patterns, insights)

        # 4. Detectar duplicação
        dup_violations = self._check_duplication_violations(duplication)

        # 5. Consolidar violações
        all_violations = solid_violations + opa_violations + dup_violations
        violations = [self._to_violation(v) for v in all_violations]

        # 6. Gerar sugestões
        suggestions = self._generate_suggestions(all_violations, patterns, insights)

        # 7. Calcular health score
        health_score = self._calculate_health_score(violations, duplication)

        # 8. Determinar tendência (simplificado - STABLE por padrão)
        trend = Trend.STABLE

        return ValidationReport(
            report_id=f"val-{uuid.uuid4().hex[:8]}",
            repo_url=repo_url,
            branch=branch,
            commit_sha=insights.get("commit_sha"),
            health_score=health_score,
            trend=trend,
            violations=violations,
            suggestions=suggestions,
            metrics={
                "complexity": insights.get("complexity", 0),
                "duplication": duplication.get("percentage", 0),
                "test_coverage": insights.get("test_coverage", 0),
                "class_count": len([p for p in patterns if p.get("type") == "class"]),
                "interface_count": len([p for p in patterns if p.get("type") == "interface"]),
            },
            created_at=datetime.now(timezone.utc)
        )

    async def _get_patterns_safe(self, repo_url: str, branch: str) -> list:
        try:
            return await self.scout_client.get_patterns(repo_url, branch)
        except Exception as e:
            logger.warning(
                "scout_patterns_error",
                repo_url=repo_url,
                branch=branch,
                error=str(e)
            )
            return []

    async def _get_insights_safe(self, repo_url: str, branch: str) -> dict:
        try:
            return await self.scout_client.get_insights(repo_url, branch)
        except Exception as e:
            logger.warning(
                "scout_insights_error",
                repo_url=repo_url,
                branch=branch,
                error=str(e)
            )
            return {}

    async def _check_duplication_safe(self, repo_url: str, branch: str) -> dict:
        try:
            return await self.scout_client.check_duplication(repo_url, branch)
        except Exception as e:
            logger.warning(
                "scout_duplication_error",
                repo_url=repo_url,
                branch=branch,
                error=str(e)
            )
            return {"percentage": 0}

    async def _check_opa_safe(self, patterns: list, insights: dict) -> list:
        try:
            return await self.opa_client.check_architecture_rules(patterns, insights)
        except Exception as e:
            logger.warning(
                "opa_evaluation_error",
                patterns_count=len(patterns),
                error=str(e)
            )
            return []

    def _check_duplication_violations(self, duplication: dict) -> list:
        violations: list = []
        if duplication.get("percentage", 0) > 10:
            severity = "high" if duplication["percentage"] > 20 else "medium"
            violations.append({
                "type": ViolationType.DUPLICATION.value,
                "severity": severity,
                "location": "multiple",
                "description": f"{duplication['percentage']:.1f}% de código duplicado",
                "suggestion": "Extrair código duplicado para funções/módulos reutilizáveis"
            })
        return violations

    def _to_violation(self, v: dict) -> Violation:
        """Converte dict de violação para modelo Violation."""
        # Mapear SOLID principle string para ViolationType
        type_str = v.get("type", "complexity")
        try:
            violation_type = ViolationType(type_str)
        except ValueError:
            violation_type = ViolationType.COMPLEXITY

        # Mapear severity string para Severity enum
        severity_str = v.get("severity", "medium")
        try:
            severity = Severity(severity_str)
        except ValueError:
            severity = Severity.MEDIUM

        return Violation(
            type=violation_type,
            severity=severity,
            location=v.get("location", "unknown"),
            description=v.get("description", ""),
            suggestion=v.get("suggestion")
        )

    def _generate_suggestions(
        self, violations: list[dict], patterns: list, insights: dict
    ) -> list[Suggestion]:
        """Gera sugestões priorizadas baseadas nas violações."""
        suggestions: list[Suggestion] = []

        # Priorizar por severidade - violations são dicts neste ponto
        critical_violations = [v for v in violations if v.get("severity") == "critical"]
        high_violations = [v for v in violations if v.get("severity") == "high"]

        # Sugestões baseadas em violações críticas
        for v in critical_violations[:3]:
            suggestions.append(Suggestion(
                priority=1,
                description=v.get("suggestion") or v.get("description", ""),
                effort="M",
                affected_files=[v.get("location", "unknown")]
            ))

        # Sugestões para violações high
        for v in high_violations[:5]:
            suggestions.append(Suggestion(
                priority=2,
                description=v.get("suggestion") or v.get("description", ""),
                effort="L",
                affected_files=[v.get("location", "unknown")]
            ))

        # Sugestão de cobertura de testes se baixa
        test_coverage = insights.get("test_coverage", 100)
        if test_coverage < 70:
            suggestions.append(Suggestion(
                priority=3,
                description=f"Aumentar cobertura de testes de {test_coverage:.1f}% para 80%+",
                effort="XL",
                affected_files=[]
            ))

        return suggestions

    def _calculate_health_score(self, violations: list[Violation], duplication: dict) -> int:
        """Calcula score de saúde 0-100."""
        score = 100

        # Penalidade por violação baseada em severidade
        severity_weights: dict[Severity, int] = {
            Severity.CRITICAL: 25,
            Severity.HIGH: 15,
            Severity.MEDIUM: 8,
            Severity.LOW: 3
        }
        for v in violations:
            # v é um objeto Violation, acessar atributo diretamente
            score -= severity_weights.get(v.severity, 5)

        # Penalidade por duplicação
        dup_pct = duplication.get("percentage", 0)
        score -= int(dup_pct / 2)

        return max(0, min(100, score))
