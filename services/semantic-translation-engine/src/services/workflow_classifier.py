"""
Workflow Classifier Service - Classificação automática ORCHESTRATION vs GENERATION.

Multi-signal classification:
1. Keywords (criar, novo, from scratch)
2. Domain similarity (via Knowledge Graph)
3. Complexity score
4. Resource availability
"""

import re
from typing import Any

import structlog
from src.models.cognitive_plan import WorkflowType

logger = structlog.get_logger(__name__)


# Keywords for GENERATION workflow (indicate new software creation)
GENERATION_KEYWORDS = {
    "criar": ["criar", "create", "crie", "build", "desenvolva", "desenvolver"],
    "novo": ["novo", "nova", "new", "nov", "from scratch", "do zero", "from zero"],
    "gerar": ["gerar", "generate", "gere", "generating", "generation"],
    "implementar": ["implementar", "implement", "implemente", "implementing"],
    "microserviço": ["microserviço", "microservice", "micro-serviço", "ms"],
    "api": ["api", "rest api", "endpoint", "restful"],
    "sistema": ["sistema", "system", "aplicação", "application", "app"],
}

# Keywords for ORCHESTRATION workflow (indicate modification/coordination)
ORCHESTRATION_KEYWORDS = {
    "modificar": ["modificar", "modify", "alterar", "change", "update", "atualizar"],
    "consultar": ["consultar", "consult", "query", "buscar", "search", "listar", "list"],
    "executar": ["executar", "execute", "run", "rodar", "process"],
    "analisar": ["analisar", "analyze", "analysis", "relatório", "report", "dashboard"],
    "configurar": ["configurar", "configure", "setup", "config"],
    "monitorar": ["monitorar", "monitor", "observar", "observe", "check", "verify"],
}


class WorkflowClassifierService:
    """
    Serviço para classificar intents como ORCHESTRATION ou GENERATION.

    Usa múltiplos sinais para decisão:
    - Keyword matching
    - Intent similarity
    - Complexity analysis
    - Historical patterns
    """

    def __init__(
        self,
        generation_threshold: float = 0.6,
        enable_keywords: bool = True,
        enable_complexity: bool = True,
        enable_historical: bool = True,
    ):
        """
        Inicializa o classificador.

        Args:
            generation_threshold: Score mínimo para classificar como GENERATION
            enable_keywords: Usar keyword matching
            enable_complexity: Usar análise de complexidade
            enable_historical: Usar padrões históricos
        """
        self.generation_threshold = generation_threshold
        self.enable_keywords = enable_keywords
        self.enable_complexity = enable_complexity
        self.enable_historical = enable_historical

        # Compilar regex patterns para eficiência
        self._generation_patterns = self._compile_patterns(GENERATION_KEYWORDS)
        self._orchestration_patterns = self._compile_patterns(ORCHESTRATION_KEYWORDS)

    def classify(
        self,
        intent_envelope: dict[str, Any],
        intermediate_repr: dict[str, Any] | None = None,
    ) -> tuple[WorkflowType, dict[str, Any]]:
        """
        Classifica uma intent como ORCHESTRATION ou GENERATION.

        Args:
            intent_envelope: Intent envelope completo
            intermediate_repr: Representação intermediária do Semantic Parser

        Returns:
            Tupla (WorkflowType, classification_metadata)
        """
        intent = intent_envelope.get("intent", {})
        intent_text = intent.get("text", "")
        intent_id = intent_envelope.get("id", "unknown")

        logger.info(
            "workflow_classification_start",
            intent_id=intent_id,
            text_preview=intent_text[:100],
        )

        scores = {}
        total_score = 0.0
        signal_count = 0

        # Sinal 1: Keywords
        if self.enable_keywords:
            keyword_score = self._score_keywords(intent_text)
            scores["keywords"] = keyword_score
            total_score += keyword_score
            signal_count += 1

        # Sinal 2: Complexity
        if self.enable_complexity and intermediate_repr:
            complexity_score = self._score_complexity(intermediate_repr)
            scores["complexity"] = complexity_score
            total_score += complexity_score
            signal_count += 1

        # Sinal 3: Historical patterns
        if self.enable_historical:
            historical_score = self._score_historical(intent_envelope)
            scores["historical"] = historical_score
            total_score += historical_score
            signal_count += 1

        # Normalizar score
        normalized_score = total_score / signal_count if signal_count > 0 else 0.0

        # Decisão
        workflow_type = (
            WorkflowType.GENERATION
            if normalized_score >= self.generation_threshold
            else WorkflowType.ORCHESTRATION
        )

        confidence = abs(normalized_score - self.generation_threshold) / self.generation_threshold

        metadata = {
            "workflow_type": workflow_type.value,
            "score": normalized_score,
            "confidence": min(confidence, 1.0),
            "threshold": self.generation_threshold,
            "signals": scores,
            "signal_count": signal_count,
            "reason": self._explain_decision(normalized_score, scores),
        }

        logger.info(
            "workflow_classification_complete",
            intent_id=intent_id,
            workflow_type=workflow_type.value,
            score=normalized_score,
            confidence=metadata["confidence"],
            reason=metadata["reason"],
        )

        return workflow_type, metadata

    def _compile_patterns(self, keyword_groups: dict[str, list[str]]) -> list[tuple[str, re.Pattern]]:
        """Compila regex patterns para keyword groups."""
        patterns = []
        for group, keywords in keyword_groups.items():
            pattern_str = r"\b(" + "|".join(map(re.escape, keywords)) + r")"
            patterns.append((group, re.compile(pattern_str, re.IGNORECASE)))
        return patterns

    def _score_keywords(self, text: str) -> float:
        """
        Analisa keywords no texto da intent.

        Returns:
            Score 0-1, onde >0.5 indica GENERATION
        """
        if not text:
            return 0.0

        generation_matches = 0
        orchestration_matches = 0

        # Contar matches de geração
        for group, pattern in self._generation_patterns:
            matches = pattern.findall(text)
            if matches:
                generation_matches += len(matches)
                logger.debug(
                    "generation_keyword_match",
                    group=group,
                    matches=matches,
                )

        # Contar matches de orquestração
        for group, pattern in self._orchestration_patterns:
            matches = pattern.findall(text)
            if matches:
                orchestration_matches += len(matches)
                logger.debug(
                    "orchestration_keyword_match",
                    group=group,
                    matches=matches,
                )

        total = generation_matches + orchestration_matches
        if total == 0:
            return 0.5  # Neutro quando não há keywords

        # Score: 1.0 = puro generation, 0.0 = puro orchestration
        generation_ratio = generation_matches / total
        return generation_ratio

    def _score_complexity(self, intermediate_repr: dict[str, Any]) -> float:
        """
        Analisa a complexidade da tarefa.

        Tasks mais complexas tendem a ser GENERATION (novo software).
        Tasks mais simples tendem a ser ORCHESTRATION (operações).

        Returns:
            Score 0-1, onde >0.5 indica GENERATION
        """
        historical_context = intermediate_repr.get("historical_context", {})
        similar_intents = historical_context.get("similar_intents", [])

        # Analisar tasks
        tasks = intermediate_repr.get("tasks", [])
        task_count = len(tasks)

        # Task count muito alto pode indicar geração
        if task_count > 10:
            return 0.7
        elif task_count > 5:
            return 0.6
        elif task_count > 2:
            return 0.5
        else:
            return 0.4

    def _score_historical(self, intent_envelope: dict[str, Any]) -> float:
        """
        Analisa padrões históricos de intents similares.

        Returns:
            Score 0-1, onde >0.5 indica GENERATION
        """
        # TODO: Implementar busca histórica real
        # Por ora, usa heurística baseada em domain

        intent = intent_envelope.get("intent", {})
        domain = intent.get("domain", "").lower()

        # Domínios que tendem a ser GENERATION
        generation_domains = {"development", "dev", "engineering", "software"}

        # Domínios que tendem a ser ORCHESTRATION
        orchestration_domains = {
            "operations",
            "ops",
            "monitoring",
            "analytics",
            "reporting",
        }

        if domain in generation_domains:
            return 0.7
        elif domain in orchestration_domains:
            return 0.3
        else:
            return 0.5  # Neutro

    def _explain_decision(
        self, score: float, signals: dict[str, float]
    ) -> str:
        """Gera explicação da decisão."""
        if score >= self.generation_threshold:
            return f"Classificado como GENERATION (score {score:.2f} >= {self.generation_threshold})"
        else:
            return f"Classificado como ORCHESTRATION (score {score:.2f} < {self.generation_threshold})"


# Singleton instance
_default_classifier: WorkflowClassifierService | None = None


def get_classifier() -> WorkflowClassifierService:
    """Retorna o classificador padrão (singleton)."""
    global _default_classifier
    if _default_classifier is None:
        _default_classifier = WorkflowClassifierService()
    return _default_classifier
