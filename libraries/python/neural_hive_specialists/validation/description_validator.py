"""
Description Quality Validator - Validador de qualidade de descrições de tarefas

Garante que descrições de tarefas sejam ricas o suficiente para avaliação
heurística pelos specialists. Fornece scoring baseado em comprimento,
diversidade léxica, e keywords específicas de domínio.

Este módulo é compartilhado entre:
- services/semantic-translation-engine (runtime)
- ml_pipelines/training (geração de datasets)
"""

import re
import logging
from typing import Dict, List, Optional, Any

# Usar logging padrão para compatibilidade entre contextos
logger = logging.getLogger(__name__)


class DescriptionQualityValidator:
    """Validador de qualidade de descrições de tarefas com scoring e sugestões."""

    # Keywords específicas por domínio para validação de qualidade
    # Expandidas com sinônimos para melhor matching de descrições geradas por LLM
    DOMAIN_KEYWORDS: Dict[str, List[str]] = {
        "security-analysis": [
            # Keywords originais
            "auth",
            "security",
            "validate",
            "encrypt",
            "audit",
            "permission",
            "credential",
            "token",
            "sanitize",
            "injection",
            "access",
            "role",
            # Sinônimos e termos relacionados
            "authentication",
            "authorization",
            "password",
            "oauth",
            "jwt",
            "ssl",
            "tls",
            "https",
            "certificate",
            "vulnerability",
            "threat",
            "protect",
            "secure",
            "firewall",
            "xss",
            "csrf",
            "sql",
            "hash",
            "cipher",
            "decrypt",
            "key",
            "secret",
            "private",
            "public",
        ],
        "architecture-review": [
            # Keywords originais
            "service",
            "interface",
            "pattern",
            "design",
            "module",
            "component",
            "api",
            "integration",
            "layer",
            "dependency",
            "contract",
            "schema",
            # Sinônimos e termos relacionados
            "microservice",
            "monolith",
            "architecture",
            "structure",
            "system",
            "class",
            "function",
            "method",
            "endpoint",
            "rest",
            "grpc",
            "graphql",
            "database",
            "queue",
            "message",
            "event",
            "handler",
            "controller",
            "repository",
            "factory",
            "singleton",
            "adapter",
            "facade",
            "proxy",
        ],
        "performance-optimization": [
            # Keywords originais
            "cache",
            "index",
            "optimize",
            "parallel",
            "async",
            "batch",
            "latency",
            "throughput",
            "memory",
            "pool",
            "query",
            "buffer",
            # Sinônimos e termos relacionados
            "performance",
            "speed",
            "fast",
            "slow",
            "bottleneck",
            "profil",
            "benchmark",
            "scale",
            "concurrent",
            "thread",
            "process",
            "cpu",
            "disk",
            "network",
            "io",
            "response",
            "time",
            "load",
            "stress",
            "efficient",
            "resource",
            "consumption",
            "allocation",
            "garbage",
        ],
        "code-quality": [
            # Keywords originais
            "test",
            "error",
            "log",
            "document",
            "refactor",
            "lint",
            "coverage",
            "exception",
            "debug",
            "trace",
            "monitor",
            "metric",
            # Sinônimos e termos relacionados
            "quality",
            "clean",
            "readable",
            "maintain",
            "review",
            "comment",
            "unit",
            "integration",
            "e2e",
            "mock",
            "stub",
            "assert",
            "verify",
            "sonar",
            "eslint",
            "pylint",
            "format",
            "style",
            "convention",
            "typing",
            "type",
            "annotation",
            "docstring",
            "readme",
            "spec",
        ],
        "business-logic": [
            # Keywords originais
            "workflow",
            "kpi",
            "cost",
            "efficiency",
            "process",
            "metric",
            "rule",
            "policy",
            "compliance",
            "approval",
            "transaction",
            "pipeline",
            # Sinônimos e termos relacionados
            "business",
            "logic",
            "domain",
            "entity",
            "value",
            "aggregate",
            "event",
            "command",
            "handler",
            "saga",
            "state",
            "machine",
            "validation",
            "constraint",
            "requirement",
            "specification",
            "use case",
            "customer",
            "order",
            "payment",
            "invoice",
            "product",
            "inventory",
        ],
    }

    # Keywords por nível de segurança
    SECURITY_KEYWORDS: Dict[str, List[str]] = {
        "confidential": [
            "encrypt",
            "auth",
            "audit",
            "permission",
            "sanitize",
            "credential",
            "token",
            "secure",
            "private",
            "protected",
        ],
        "restricted": [
            "encrypt",
            "auth",
            "audit",
            "permission",
            "sanitize",
            "classified",
            "secret",
            "clearance",
            "compartment",
            "need-to-know",
        ],
        "internal": ["validate", "verify", "check", "access"],
        "public": [],
    }

    # Keywords de QoS
    QOS_KEYWORDS: Dict[str, List[str]] = {
        "exactly_once": [
            "idempotent",
            "transaction",
            "rollback",
            "exactly-once",
            "dedup",
            "deduplication",
        ],
        "at_least_once": ["retry", "acknowledge", "redelivery", "at-least-once"],
        "at_most_once": ["fire-and-forget", "best-effort", "at-most-once"],
    }

    # Contagem mínima e máxima de palavras
    MIN_WORDS = 15
    MAX_WORDS = 50
    OPTIMAL_MIN_WORDS = 15
    OPTIMAL_MAX_WORDS = 50

    # Pesos padrão para scoring - ajustados para ser menos restritivos
    # Reduzido peso de domain (era 30%, agora 20%) pois era o maior causador de rejeições
    DEFAULT_WEIGHTS = {
        "length": 0.30,  # Aumentado de 0.25 (comprimento é fácil de atingir)
        "diversity": 0.25,  # Aumentado de 0.20 (diversidade léxica)
        "domain": 0.20,  # Reduzido de 0.30 (keywords - era muito restritivo)
        "security": 0.15,  # Mantido
        "qos": 0.10,  # Mantido
    }

    def __init__(self):
        """Inicializa o validador com configurações padrão."""
        self._compile_patterns()

    def _compile_patterns(self):
        """Compila padrões regex para matching de keywords."""
        self._domain_patterns: Dict[str, List[re.Pattern]] = {}
        for domain, keywords in self.DOMAIN_KEYWORDS.items():
            self._domain_patterns[domain] = [
                re.compile(rf"\b{kw}\w*\b", re.IGNORECASE) for kw in keywords
            ]

    def validate_description(
        self,
        description: str,
        domain: str,
        security_level: Optional[str] = None,
        qos: Optional[str] = None,
    ) -> Dict:
        """
        Valida uma descrição de tarefa e retorna métricas de qualidade.

        Args:
            description: Descrição da tarefa a validar
            domain: Contexto de domínio (security-analysis, architecture-review, etc.)
            security_level: Nível de segurança opcional (public, internal, confidential, restricted)
            qos: Requisito de QoS opcional (exactly_once, at_least_once, at_most_once)

        Returns:
            Dict com:
                - score: float (0.0-1.0)
                - issues: List[str] descrevendo problemas
                - suggestions: List[str] com dicas de melhoria
                - metrics: Dict com scores detalhados
        """
        issues: List[str] = []

        # Calcular métricas individuais
        length_score, length_issues = self._score_length(description)
        diversity_score, diversity_issues = self._score_lexical_diversity(description)
        domain_score, domain_issues = self._score_domain_keywords(description, domain)
        security_score, security_issues = self._score_security_keywords(
            description, security_level
        )
        qos_score, qos_issues = self._score_qos_keywords(description, qos)

        # Agregar issues
        issues.extend(length_issues)
        issues.extend(diversity_issues)
        issues.extend(domain_issues)
        issues.extend(security_issues)
        issues.extend(qos_issues)

        # Calcular score ponderado
        weights = self.DEFAULT_WEIGHTS.copy()

        # Ajustar pesos baseado em contexto
        if security_level in ["confidential", "restricted"]:
            weights["security"] = 0.25
            weights["domain"] = 0.25
        if qos:
            weights["qos"] = 0.15
            weights["domain"] = 0.25

        # Normalizar pesos
        total_weight = sum(weights.values())
        weights = {k: v / total_weight for k, v in weights.items()}

        overall_score = (
            weights["length"] * length_score
            + weights["diversity"] * diversity_score
            + weights["domain"] * domain_score
            + weights["security"] * security_score
            + weights["qos"] * qos_score
        )

        # Gerar sugestões baseadas em issues
        suggestions = self._generate_suggestions(
            description,
            domain,
            security_level,
            qos,
            length_score,
            diversity_score,
            domain_score,
        )

        result = {
            "score": round(overall_score, 3),
            "issues": issues,
            "suggestions": suggestions,
            "metrics": {
                "length_score": round(length_score, 3),
                "diversity_score": round(diversity_score, 3),
                "domain_score": round(domain_score, 3),
                "security_score": round(security_score, 3),
                "qos_score": round(qos_score, 3),
                "word_count": len(description.split()),
                "domain_keywords_found": self._count_domain_keywords(
                    description, domain
                ),
            },
        }

        logger.debug(
            "description_validated: score=%.3f, word_count=%d, domain=%s, security_level=%s, num_issues=%d",
            result["score"],
            result["metrics"]["word_count"],
            domain,
            security_level,
            len(issues),
        )

        return result

    def validate_plan_descriptions(
        self,
        cognitive_plan: Dict[str, Any],
        min_quality_score: float = 0.5,  # Reduzido de 0.6 para 0.5 para maior taxa de aceitação
    ) -> Dict:
        """
        Valida qualidade de todas as descrições em um cognitive plan.

        Args:
            cognitive_plan: Plan completo com tasks
            min_quality_score: Score mínimo aceitável (default: 0.5)

        Returns:
            Dict com:
                - is_valid: bool indicando se plan é válido
                - avg_score: score médio das descrições
                - task_scores: lista de scores por task
                - issues: lista de todos os issues encontrados
                - low_quality_tasks: lista de tasks com score abaixo do mínimo
        """
        tasks = cognitive_plan.get("tasks", [])
        domain = cognitive_plan.get("original_domain", "code-quality")
        security_level = cognitive_plan.get("original_security_level", "internal")
        qos = cognitive_plan.get("qos")

        task_scores = []
        all_issues = []
        low_quality_tasks = []

        for task in tasks:
            description = task.get("description", "")
            result = self.validate_description(description, domain, security_level, qos)
            task_scores.append(result["score"])

            if result["issues"]:
                all_issues.extend(
                    [
                        f"Task {task.get('task_id')}: {issue}"
                        for issue in result["issues"]
                    ]
                )

            # Usar threshold mais baixo para tarefas individuais
            # Permite que algumas tarefas tenham score menor desde que a média seja boa
            individual_threshold = min(min_quality_score - 0.1, 0.4)
            if result["score"] < individual_threshold:
                low_quality_tasks.append(
                    {
                        "task_id": task.get("task_id"),
                        "description": description[:100],
                        "score": result["score"],
                    }
                )

        avg_score = sum(task_scores) / len(task_scores) if task_scores else 0.0
        # Validação mais flexível: aceita se média é boa
        # Antes: ambas condições (média E sem tarefas ruins) precisavam ser verdadeiras
        is_valid = avg_score >= min_quality_score

        return {
            "is_valid": is_valid,
            "avg_score": round(avg_score, 3),
            "task_scores": task_scores,
            "issues": all_issues,
            "low_quality_tasks": low_quality_tasks,
        }

    def _score_length(self, description: str) -> tuple:
        """Score baseado em contagem de palavras."""
        words = description.split()
        word_count = len(words)
        issues = []

        if word_count < 10:
            score = 0.0
            issues.append(
                f"Descrição muito curta ({word_count} palavras, mínimo 15 recomendado)"
            )
        elif word_count < self.OPTIMAL_MIN_WORDS:
            score = 0.5 * (word_count / self.OPTIMAL_MIN_WORDS)
            issues.append(f"Descrição precisa de mais detalhes ({word_count} palavras)")
        elif word_count <= self.OPTIMAL_MAX_WORDS:
            score = 1.0
        elif word_count <= self.MAX_WORDS * 1.5:
            score = 0.7
            issues.append(f"Descrição um pouco longa ({word_count} palavras)")
        else:
            score = 0.5
            issues.append(f"Descrição muito longa ({word_count} palavras, alvo 15-50)")

        return score, issues

    def _score_lexical_diversity(self, description: str) -> tuple:
        """Score baseado em ratio de palavras únicas."""
        words = description.lower().split()
        issues = []

        if len(words) == 0:
            return 0.0, ["Descrição está vazia"]

        # Remover stopwords comuns para cálculo de diversidade
        stopwords = {
            "the",
            "a",
            "an",
            "and",
            "or",
            "but",
            "in",
            "on",
            "at",
            "to",
            "for",
            "of",
            "with",
            "by",
            "from",
            "is",
            "are",
            "was",
            "were",
            "be",
            "been",
            "being",
            "have",
            "has",
            "had",
            "do",
            "does",
            "did",
            "will",
            "would",
            "could",
            "should",
            "may",
            "might",
            "must",
            "shall",
            "can",
            "need",
            "this",
            "that",
            "these",
            "those",
            "it",
            "its",
        }

        meaningful_words = [w for w in words if w not in stopwords and len(w) > 2]

        if len(meaningful_words) == 0:
            return 0.3, ["Falta vocabulário significativo na descrição"]

        unique_ratio = len(set(meaningful_words)) / len(meaningful_words)

        if unique_ratio >= 0.7:
            score = 1.0
        elif unique_ratio >= 0.5:
            score = 0.5 + (unique_ratio - 0.5) * 2.5
        else:
            score = unique_ratio
            issues.append(f"Baixa diversidade léxica (ratio: {unique_ratio:.2f})")

        return score, issues

    def _score_domain_keywords(self, description: str, domain: str) -> tuple:
        """Score baseado em presença de keywords específicas do domínio."""
        issues = []
        keywords = self.DOMAIN_KEYWORDS.get(domain, [])

        if not keywords:
            return 0.5, []  # Domínio desconhecido, score neutro

        description_lower = description.lower()
        found_keywords = []

        for kw in keywords:
            if re.search(rf"\b{kw}\w*\b", description_lower, re.IGNORECASE):
                found_keywords.append(kw)

        keyword_count = len(found_keywords)

        if keyword_count >= 3:
            score = 1.0
        elif keyword_count == 2:
            score = 0.8
        elif keyword_count == 1:
            score = 0.5
            issues.append(f"Apenas 1 keyword de domínio encontrada para {domain}")
        else:
            score = 0.0
            issues.append(f"Nenhuma keyword de domínio para {domain}")
            issues.append(f"Considere adicionar: {', '.join(keywords[:5])}")

        return score, issues

    def _count_domain_keywords(self, description: str, domain: str) -> int:
        """Conta keywords de domínio encontradas na descrição."""
        keywords = self.DOMAIN_KEYWORDS.get(domain, [])
        description_lower = description.lower()
        return sum(1 for kw in keywords if kw in description_lower)

    def _score_security_keywords(
        self, description: str, security_level: Optional[str]
    ) -> tuple:
        """Score baseado em keywords de segurança para níveis sensíveis."""
        if not security_level:
            return 1.0, []  # Sem contexto de segurança, score máximo

        keywords = self.SECURITY_KEYWORDS.get(security_level, [])
        if not keywords:
            return 1.0, []

        description_lower = description.lower()
        found = sum(1 for kw in keywords if kw in description_lower)
        issues = []

        if security_level in ["confidential", "restricted"]:
            if found >= 2:
                score = 1.0
            elif found == 1:
                score = 0.6
                issues.append(
                    f"Apenas 1 keyword de segurança para nível {security_level}"
                )
            else:
                score = 0.2
                issues.append(
                    f"Faltam keywords de segurança para nível {security_level}"
                )
        else:
            score = 1.0 if found > 0 else 0.8

        return score, issues

    def _score_qos_keywords(self, description: str, qos: Optional[str]) -> tuple:
        """Score baseado em keywords de QoS."""
        if not qos:
            return 1.0, []  # Sem contexto de QoS, score máximo

        keywords = self.QOS_KEYWORDS.get(qos, [])
        if not keywords:
            return 1.0, []

        description_lower = description.lower()
        found = sum(1 for kw in keywords if kw in description_lower)
        issues = []

        if found > 0:
            score = 1.0
        else:
            score = 0.5
            issues.append(f"Faltam hints de QoS para semântica {qos}")

        return score, issues

    def _generate_suggestions(
        self,
        description: str,
        domain: str,
        security_level: Optional[str],
        qos: Optional[str],
        length_score: float,
        diversity_score: float,
        domain_score: float,
    ) -> List[str]:
        """Gera sugestões acionáveis para melhoria."""
        suggestions = []

        if length_score < 0.6:
            suggestions.append(
                "Expanda a descrição para 15-50 palavras com verbos de ação específicos e contexto"
            )

        if diversity_score < 0.6:
            suggestions.append(
                "Use vocabulário mais variado; evite repetir os mesmos termos"
            )

        if domain_score < 0.6:
            domain_kws = self.DOMAIN_KEYWORDS.get(domain, [])[:5]
            if domain_kws:
                suggestions.append(
                    f"Inclua keywords de domínio: {', '.join(domain_kws)}"
                )

        if security_level in ["confidential", "restricted"]:
            security_kws = self.SECURITY_KEYWORDS.get(security_level, [])[:4]
            if security_kws and "encrypt" not in description.lower():
                suggestions.append(
                    f"Adicione contexto de segurança: {', '.join(security_kws)}"
                )

        if qos and qos in self.QOS_KEYWORDS:
            qos_kws = self.QOS_KEYWORDS[qos][:3]
            suggestions.append(f"Considere hints de QoS: {', '.join(qos_kws)}")

        return suggestions

    def suggest_improvements(self, description: str, context: Dict) -> str:
        """
        Gera uma versão melhorada de uma descrição pobre.

        Args:
            description: Descrição original
            context: Dict com domain, security_level, priority, entities, qos

        Returns:
            String com descrição melhorada
        """
        domain = context.get("domain", "code-quality")
        security_level = context.get("security_level", "internal")
        priority = context.get("priority", "normal")
        entities = context.get("entities", [])
        qos = context.get("qos")

        # Extrair objetivo da descrição original
        objective = description.lower().replace("operation", "").strip()

        # Construir descrição enriquecida
        parts = []

        # Expansão de verbos de ação baseado no objetivo
        action_verbs = self._get_action_verbs(objective)
        parts.append(action_verbs)

        # Contexto de entidades
        if entities:
            entity_summary = self._summarize_entities(entities)
            if entity_summary:
                parts.append(f"for {entity_summary}")

        # Hints de segurança
        if security_level in ["confidential", "restricted"]:
            parts.append("with authentication and encryption")

        # Contexto de domínio
        domain_hint = self._get_domain_hint(domain)
        if domain_hint:
            parts.append(domain_hint)

        # Hints de prioridade/QoS
        if priority in ["high", "critical"] or qos == "exactly_once":
            parts.append("with optimized caching and transaction guarantees")

        # Sufixo de metadata
        metadata = f"({domain}, {security_level}, {priority} priority)"
        parts.append(metadata)

        improved = " ".join(parts)

        logger.info(
            "description_improved: original='%s', improved='%s', domain=%s, security_level=%s",
            description,
            improved,
            domain,
            security_level,
        )

        return improved

    def _get_action_verbs(self, objective: str) -> str:
        """Mapeia objetivo para verbos de ação descritivos."""
        action_map = {
            "create": "Create and initialize resources",
            "update": "Modify and validate configuration",
            "query": "Retrieve and filter data",
            "validate": "Verify integrity and check compliance",
            "transform": "Process and convert data formats",
            "delete": "Remove and clean up resources",
            "deploy": "Deploy and configure services",
            "test": "Execute tests and validate results",
            "analyze": "Analyze patterns and generate insights",
            "monitor": "Monitor metrics and detect anomalies",
        }

        for key, value in action_map.items():
            if key in objective:
                return value

        return f"{objective.capitalize()} and process data"

    def _summarize_entities(self, entities: List[Dict]) -> str:
        """Resume entidades para contexto da descrição."""
        if not entities:
            return ""

        # Agrupar por tipo
        types = set()
        for entity in entities[:3]:  # Limitar aos 3 primeiros
            entity_type = entity.get("type", entity.get("entity_type", "data"))
            types.add(entity_type)

        if types:
            return ", ".join(sorted(types)[:2]) + " data"
        return ""

    def _get_domain_hint(self, domain: str) -> str:
        """Obtém hint de processamento específico do domínio."""
        hints = {
            "security-analysis": "applying security validation and audit logging",
            "architecture-review": "following service integration patterns",
            "performance-optimization": "using indexed queries and connection pooling",
            "code-quality": "with error handling and test coverage",
            "business-logic": "aligned with workflow policies and KPI metrics",
        }
        return hints.get(domain, "")


# Instância singleton para acesso fácil
_validator_instance: Optional[DescriptionQualityValidator] = None


def get_validator() -> DescriptionQualityValidator:
    """Obtém ou cria a instância singleton do validador."""
    global _validator_instance
    if _validator_instance is None:
        _validator_instance = DescriptionQualityValidator()
    return _validator_instance
