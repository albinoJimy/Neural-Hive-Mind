"""
SolutionSynthesizer - Combina descobertas de múltiplos scouts em recomendações.

Responsável por:
- Agregar resultados de múltiplas fontes (scouts)
- Deduplicar findings sobrepostos
- Resolver conflitos entre scouts
- Gerar recomendações acionáveis
- Priorizar por impacto/esforço
"""

import json
from collections import defaultdict
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger()


class SolutionSynthesizer:
    """Sintetiza soluções a partir de múltiplas fontes de descoberta."""

    # Estratégias de síntese padrão
    DEFAULT_STRATEGIES = {
        "merge": "combine_all_sources",
        "deduplicate": "by_name_and_location",
        "conflict_resolution": "highest_confidence_wins",
        "prioritization": "by_severity_then_impact",
    }

    def __init__(self, strategies: Optional[Dict[str, Any]] = None):
        """
        Inicializa o SolutionSynthesizer.

        Args:
            strategies: Dict customizado de estratégias de síntese
        """
        self.synthesis_strategies = strategies or dict(self.DEFAULT_STRATEGIES)

    def synthesize(self, source_data: Dict[str, Any], format: str = "dict") -> Dict[str, Any]:
        """
        Sintetiza dados de uma única fonte.

        Args:
            source_data: Dados da fonte (scout)
            format: Formato de saída (dict, json, markdown)

        Returns:
            Dict com dados sintetizados
        """
        result = {
            "sources": [source_data.get("source", "unknown")],
            "summary": self._generate_summary(source_data),
            "recommendations": [],
        }

        # Extrair padrões se presentes
        if "patterns" in source_data or "patterns_found" in source_data:
            patterns = source_data.get("patterns", source_data.get("patterns_found", []))
            result["patterns"] = patterns
            result["patterns_count"] = (
                len(patterns) if isinstance(patterns, list) else len(patterns.get("patterns", []))
            )

        # Extrair sugestões
        if "suggestions" in source_data:
            result["suggestions"] = source_data["suggestions"]

        # Gerar recomendações iniciais
        result["recommendations"] = self.generate_recommendations(source_data)

        return self._format_output(result, format)

    def synthesize_multiple(
        self, sources: List[Dict[str, Any]], format: str = "dict"
    ) -> Dict[str, Any]:
        """
        Sintetiza dados de múltiplas fontes.

        Args:
            sources: Lista de dicts de dados dos scouts
            format: Formato de saída

        Returns:
            Dict com dados agregados e sintetizados
        """
        if not sources:
            return {"sources": [], "patterns": [], "recommendations": []}

        # Agregar todas as fontes
        all_patterns = defaultdict(list)
        all_dependencies = defaultdict(set)
        all_recommendations = []
        all_confidences = []

        for source in sources:
            source_name = source.get("source", "unknown")

            # Coletar padrões
            patterns = source.get("patterns", [])
            if isinstance(patterns, dict) and "patterns" in patterns:
                patterns = patterns["patterns"]

            for pattern in patterns:
                pattern_name = pattern.get("name", "").lower()
                if pattern_name:
                    all_patterns[pattern_name].append({**pattern, "source": source_name})

            # Coletar dependências
            if "dependencies" in source:
                deps = source["dependencies"]
                if isinstance(deps, dict):
                    for file_key, dep_list in deps.items():
                        if file_key == "edges":
                            # Tratar edges separadamente
                            continue
                        if isinstance(dep_list, list):
                            all_dependencies[file_key].update(dep_list)

            # Coletar recomendações
            if "recommendations" in source:
                all_recommendations.extend(source["recommendations"])

            # Coletar confianças
            if "confidence" in source:
                all_confidences.append(source["confidence"])

            # Coletar confianças de padrões
            for pattern in patterns:
                if "confidence" in pattern:
                    all_confidences.append(pattern["confidence"])

        # Deduplicar e mesclar padrões
        merged_patterns = self._merge_patterns(all_patterns)

        # Construir resultado
        result = {
            "total_sources": len(sources),
            "sources": [s.get("source", "unknown") for s in sources],
            "patterns": merged_patterns,
            "patterns_count": len(merged_patterns),
            "dependencies": {k: list(v) for k, v in all_dependencies.items()},
            "recommendations": self._prioritize_recommendations(all_recommendations),
        }

        # Adicionar confiança agregada
        if all_confidences:
            result["aggregate_confidence"] = round(sum(all_confidences) / len(all_confidences), 2)

        return self._format_output(result, format)

    def _merge_patterns(self, all_patterns: Dict[str, List[Dict]]) -> List[Dict[str, Any]]:
        """Mescla padrões de múltiplas fontes."""
        merged = []

        for pattern_name, occurrences in all_patterns.items():
            # Unir locations únicas
            all_locations = set()
            all_confidences = []

            for occ in occurrences:
                if "locations" in occ:
                    if isinstance(occ["locations"], list):
                        all_locations.update(occ["locations"])
                if "confidence" in occ:
                    all_confidences.append(occ["confidence"])

            merged.append(
                {
                    "name": pattern_name,
                    "count": len(occurrences),
                    "confidence": (
                        round(sum(all_confidences) / len(all_confidences), 2)
                        if all_confidences
                        else 0.5
                    ),
                    "locations": (
                        list(all_locations)
                        if all_locations
                        else occurrences[0].get("locations", [])
                    ),
                }
            )

        # Ordenar por count
        merged.sort(key=lambda x: x["count"], reverse=True)
        return merged

    def _generate_summary(self, source_data: Dict[str, Any]) -> str:
        """Gera resumo dos dados da fonte."""
        parts = []

        if "patterns" in source_data:
            patterns = source_data["patterns"]
            if isinstance(patterns, list) and patterns:
                top_pattern = patterns[0].get("name", "unknown")
                parts.append(f"Primary pattern: {top_pattern}")

        if "complexity" in source_data:
            complexity = source_data["complexity"]
            if isinstance(complexity, dict):
                avg = complexity.get("average", 0)
                parts.append(f"Avg complexity: {avg}")

        if "files_analyzed" in source_data:
            parts.append(f"Files analyzed: {source_data['files_analyzed']}")

        return ". ".join(parts) if parts else "Analysis completed"

    def generate_recommendations(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Gera recomendações baseadas nos dados analisados."""
        recommendations = []

        # Recomendações baseadas em complexidade
        if "complexity_metrics" in data:
            metrics = data["complexity_metrics"]
            if isinstance(metrics, dict):
                high_complexity = metrics.get("high_complexity_files", [])
                for file_info in high_complexity[:3]:  # Top 3
                    recommendations.append(
                        {
                            "action": "Refactor",
                            "target": file_info.get("file", "unknown"),
                            "reason": f"High complexity ({file_info.get('complexity', 0)})",
                            "severity": "high" if file_info.get("complexity", 0) > 15 else "medium",
                            "effort": "high",
                        }
                    )

        # Recomendações de padrões
        if "missing_patterns" in data:
            for pattern in data["missing_patterns"]:
                recommendations.append(
                    {
                        "action": "Apply pattern",
                        "pattern": pattern.get("name"),
                        "target": pattern.get("suggested_locations", []),
                        "reason": f"Consider implementing {pattern.get('name')} pattern",
                        "severity": "medium",
                        "effort": "medium",
                    }
                )

        # Recomendações baseadas em issues
        if "issues" in data:
            for issue in data["issues"]:
                severity = issue.get("severity", "medium")
                recommendations.append(
                    {
                        "action": "Fix",
                        "description": issue.get("description"),
                        "severity": severity,
                        "effort": self._estimate_effort_by_severity(severity),
                    }
                )

        return self._prioritize_recommendations(recommendations)

    def _estimate_effort_by_severity(self, severity: str) -> str:
        """Estima esforço baseado em severidade."""
        effort_map = {"low": "low", "medium": "medium", "high": "high"}
        return effort_map.get(severity.lower(), "medium")

    def _prioritize_recommendations(
        self, recommendations: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Prioriza recomendações por severidade e esforço."""
        # Adicionar score de prioridade
        for rec in recommendations:
            severity_score = {"high": 10, "medium": 5, "low": 1}
            base_score = severity_score.get(rec.get("severity", "medium").lower(), 5)

            # Esforço menor aumenta prioridade, mas não supera severidade
            effort = rec.get("effort", "medium")
            effort_score = {"low": 2, "medium": 0, "high": -1}
            effort_modifier = effort_score.get(str(effort).lower(), 0)

            # Soma em vez de multiplicação para severidade ter mais peso
            rec["priority_score"] = base_score + effort_modifier

        # Ordenar por score decrescente
        recommendations.sort(key=lambda x: x.get("priority_score", 0), reverse=True)

        return recommendations

    def generate_actionable_insights(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Gera insights acionáveis a partir dos dados."""
        effort = "medium"
        # Tentar extrair effort dos dados
        if "estimated_effort" in data:
            effort = data["estimated_effort"]

        insights = {
            "summary": data.get("issue", data.get("suggestion", "Analysis complete")),
            "steps": [],
            "affected_files": data.get("affected_files", []),
            "effort": effort,
            "estimated_effort": effort,
        }

        # Gerar passos baseados no tipo de issue
        issue = data.get("issue", "")
        if "refactor" in issue.lower() or "extract" in issue.lower():
            insights["steps"] = [
                {
                    "action": "Identify extraction target",
                    "file": data.get("affected_files", [""])[0],
                },
                {"action": "Create new component", "type": "class/module"},
                {"action": "Move logic to new component", "refactor": True},
                {"action": "Update imports/references", "verify": True},
                {"action": "Run tests to validate", "test": True},
            ]
            insights["estimated_effort"] = "high"
        elif "pattern" in issue.lower() or str(data).lower() != "analysis complete":
            insights["steps"] = [
                {"action": "Review pattern requirements", "pattern": data.get("suggestion", "")},
                {"action": "Identify application points", "in": data.get("affected_files", [])},
                {"action": "Implement pattern structure", "create": True},
                {"action": "Migrate existing code", "refactor": True},
            ]

        # Estimar esforço das recomendações
        if "recommendations" in data:
            for rec in data["recommendations"]:
                rec_type = rec.get("type", "medium")
                effort_map = {"simple": 1, "medium": 3, "complex": 5}
                rec["effort"] = effort_map.get(rec_type, 3)

            insights["recommendations"] = data["recommendations"]

        return insights

    def calculate_quality_metrics(self, sources: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calcula métricas de qualidade da síntese."""
        metrics = {"coverage": 0.0, "confidence_distribution": {"high": 0, "medium": 0, "low": 0}}

        if not sources:
            return metrics

        # Calcular cobertura (razão de fontes com findings)
        sources_with_findings = sum(
            1 for s in sources if s.get("patterns") or s.get("findings") or s.get("files")
        )
        metrics["coverage"] = round(sources_with_findings / len(sources), 2)

        # Distribuir confianças
        for source in sources:
            # Confiança da fonte
            conf = source.get("confidence", 0.5)
            if conf >= 0.7:
                metrics["confidence_distribution"]["high"] += 1
            elif conf >= 0.4:
                metrics["confidence_distribution"]["medium"] += 1
            else:
                metrics["confidence_distribution"]["low"] += 1

            # Confianças de findings
            for finding in source.get("findings", []):
                conf = finding.get("confidence", 0.5)
                if conf >= 0.7:
                    metrics["confidence_distribution"]["high"] += 1
                elif conf >= 0.4:
                    metrics["confidence_distribution"]["medium"] += 1
                else:
                    metrics["confidence_distribution"]["low"] += 1

        return metrics

    def _format_output(self, data: Dict[str, Any], format: str) -> Any:
        """Formata a saída conforme especificado."""
        if format == "json":
            return json.dumps(data, indent=2, default=str)
        elif format == "markdown":
            return self._to_markdown(data)
        return data

    def _to_markdown(self, data: Dict[str, Any]) -> str:
        """Converte dados para formato Markdown."""
        lines = ["# Scout Analysis Report\n"]

        # Resumo
        if "summary" in data:
            lines.append(f"## Summary\n{data['summary']}\n")

        # Fontes
        if "sources" in data:
            lines.append("## Sources Analyzed")
            for source in data.get("sources", []):
                lines.append(f"- {source}")
            lines.append("")

        # Padrões
        if "patterns" in data and data["patterns"]:
            lines.append("## Patterns Found")
            for pattern in data["patterns"]:
                name = pattern.get("name", "unknown")
                count = pattern.get("count", 0)
                confidence = pattern.get("confidence", 0)
                lines.append(f"- **{name}**: {count} occurrences (confidence: {confidence})")
            lines.append("")

        # Recomendações
        if "recommendations" in data and data["recommendations"]:
            lines.append("## Recommendations")
            for i, rec in enumerate(data["recommendations"], 1):
                severity = rec.get("severity", "medium").upper()
                action = rec.get("action", "No action")
                target = rec.get("target", rec.get("description", ""))
                lines.append(f"{i}. **[{severity}]** {action}: {target}")
            lines.append("")

        return "\n".join(lines)
