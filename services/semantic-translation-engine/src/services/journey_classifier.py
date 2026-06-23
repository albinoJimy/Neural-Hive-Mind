"""JourneyClassifier - decide a Journey (J1-J4) de um plano cognitivo.

Fase 1 (Task 2) da spec journey-router: **Tier 1 apenas** — sinais
estruturados determinísticos, SEM LLM. O Tier 2 (LLM semântico para casos
ambíguos) é a Fase 2 e fica como gancho explícito (`_classify_llm`).

Princípio de desenho (ver sub-specs/technical-spec.md):
1. Decidir cedo, propagar — a Journey é decidida no STE.
2. Híbrido tiered — sinais estruturados primeiro (rápido, barato, fiável).
3. Anti-verde-falso — `confidence` + `reasoning` + `classification_method`;
   sem sinal forte -> `UNKNOWN`, nunca força uma jornada cega.
4. Sinais, não keywords, para os ganchos — J4 por marcador `context.source`.

Ordem de precedência dos sinais (Tier 1):
    a. context.source == "doc-ingestion"            -> J4_MIGRATE
    b. constraints.execution_mode == "plan_only"    -> J1_PLAN_ONLY
    c. cognitive_plan.workflow_type == GENERATION   -> J3_BUILD
    d. cognitive_plan.workflow_type == ORCHESTRATION -> J2_ORCHESTRATE
    (sem sinal)                                     -> UNKNOWN (no_match)
"""

from typing import Any
from uuid import uuid4

import structlog
from neural_hive_domain import Journey, JourneyDecision

logger = structlog.get_logger(__name__)


# Threshold de confiança default, alinhado com o NLU (UnifiedDomain).
# Configurável via settings.journey_confidence_threshold.
JOURNEY_CONFIDENCE_THRESHOLD = 0.6

# Confiança atribuída a uma decisão por sinal estruturado determinístico.
_STRUCTURED_SIGNAL_CONFIDENCE = 0.95

# Confiança de uma não-decisão (anti-verde-falso): abaixo do threshold.
_NO_MATCH_CONFIDENCE = 0.0

# Marcador de ingestão (sinal estruturado fiável para J4).
_DOC_INGESTION_SOURCE = "doc-ingestion"

# Modo de execução que indica planeamento sem execução (J1).
_PLAN_ONLY_MODE = "plan_only"

# Valores canónicos de workflow_type (lowercase no enum WorkflowType),
# mapeados para a respetiva jornada. Aceita também a forma upper-case.
_WORKFLOW_TYPE_TO_JOURNEY = {
    "generation": Journey.J3_BUILD,
    "orchestration": Journey.J2_ORCHESTRATE,
}


class JourneyClassifier:
    """Classifica um plano cognitivo numa :class:`Journey` (Tier 1, sem LLM).

    O método público :meth:`classify` aplica os sinais estruturados por ordem
    de precedência. Sem sinal forte devolve ``UNKNOWN`` (Tier 2/LLM é Fase 2).
    """

    def __init__(self, settings: Any | None = None) -> None:
        """Inicializa o classificador.

        Args:
            settings: objeto de configuração opcional. Se tiver o atributo
                ``journey_confidence_threshold``, é usado; caso contrário
                aplica-se :data:`JOURNEY_CONFIDENCE_THRESHOLD`.
        """
        self.confidence_threshold = getattr(
            settings, "journey_confidence_threshold", JOURNEY_CONFIDENCE_THRESHOLD
        )

    def classify(
        self,
        intent_envelope: dict[str, Any] | None,
        cognitive_plan: dict[str, Any] | None,
    ) -> JourneyDecision:
        """Decide a Journey por sinais estruturados (Tier 1).

        Args:
            intent_envelope: envelope da intenção (pode faltar campos).
            cognitive_plan: plano cognitivo (pode faltar campos / ser None).

        Returns:
            :class:`JourneyDecision` com journey, journey_id (UUID), confidence,
            reasoning e classification_method.
        """
        # Acesso defensivo: campos podem faltar ou vir com tipos inesperados.
        context = self._safe_dict(intent_envelope, "context")
        constraints = self._safe_dict(intent_envelope, "constraints")
        plan = cognitive_plan if isinstance(cognitive_plan, dict) else {}

        source = context.get("source")
        execution_mode = constraints.get("execution_mode")
        workflow_type = plan.get("workflow_type")

        # a. Marcador de ingestão -> J4_MIGRATE (sinal mais forte/específico).
        if source == _DOC_INGESTION_SOURCE:
            return self._structured(
                Journey.J4_MIGRATE,
                f"context.source == '{_DOC_INGESTION_SOURCE}' (marcador de ingestão)",
            )

        # b. execution_mode plan_only -> J1_PLAN_ONLY.
        if execution_mode == _PLAN_ONLY_MODE:
            return self._structured(
                Journey.J1_PLAN_ONLY,
                f"constraints.execution_mode == '{_PLAN_ONLY_MODE}'",
            )

        # c/d. workflow_type -> J3_BUILD / J2_ORCHESTRATE.
        if isinstance(workflow_type, str):
            journey = _WORKFLOW_TYPE_TO_JOURNEY.get(workflow_type.lower())
            if journey is not None:
                return self._structured(
                    journey,
                    f"cognitive_plan.workflow_type == '{workflow_type}'",
                )

        # Sem sinal forte. O Tier 2/LLM (Fase 2) ainda não existe, por isso
        # devolvemos UNKNOWN em vez de inventar uma jornada (anti-verde-falso).
        # TODO(Fase 2): substituir a linha de return abaixo por:
        #   return self._classify_llm(intent_envelope, cognitive_plan)
        # (com fallback para self._no_match() em falha/baixa confiança do LLM).
        return self._no_match()

    def _structured(self, journey: Journey, reason: str) -> JourneyDecision:
        """Constrói uma decisão por sinal estruturado determinístico."""
        decision = JourneyDecision(
            journey=journey,
            journey_id=str(uuid4()),
            confidence=_STRUCTURED_SIGNAL_CONFIDENCE,
            reasoning=f"Tier 1 (sinal estruturado): {reason} -> {journey.value}.",
            classification_method="structured_signal",
        )
        logger.info(
            "journey_classified",
            journey=journey.value,
            classification_method="structured_signal",
            confidence=decision.confidence,
            reason=reason,
        )
        return decision

    def _no_match(self) -> JourneyDecision:
        """Constrói uma decisão UNKNOWN (sem sinal forte; anti-verde-falso)."""
        decision = JourneyDecision(
            journey=Journey.UNKNOWN,
            journey_id=str(uuid4()),
            confidence=_NO_MATCH_CONFIDENCE,
            reasoning=(
                "Tier 1 (sem sinal estruturado forte): nenhum dos sinais "
                "(context.source, constraints.execution_mode, "
                "cognitive_plan.workflow_type) resolveu a jornada. "
                "Tier 2/LLM ainda não disponível (Fase 2) -> UNKNOWN."
            ),
            classification_method="no_match",
        )
        logger.info(
            "journey_unknown",
            classification_method="no_match",
            confidence=decision.confidence,
            threshold=self.confidence_threshold,
        )
        return decision

    def _classify_llm(
        self,
        intent_envelope: dict[str, Any] | None,
        cognitive_plan: dict[str, Any] | None,
    ) -> JourneyDecision:
        """Tier 2 (LLM semântico) — gancho da Fase 2, NÃO implementado.

        Quando o Tier 1 não der sinal forte, esta camada deverá invocar o
        ``neural_hive_llm`` (com circuit breaker) com um prompt estruturado que
        devolve ``{journey, confidence, reasoning}``. Confiança abaixo do
        threshold -> UNKNOWN + requires_manual_validation.
        """
        raise NotImplementedError(
            "Tier 2/LLM é a Fase 2 da spec journey-router; ainda não implementado."
        )

    @staticmethod
    def _safe_dict(source: dict[str, Any] | None, key: str) -> dict[str, Any]:
        """Devolve um sub-dict de forma defensiva (sempre um dict)."""
        if not isinstance(source, dict):
            return {}
        value = source.get(key)
        return value if isinstance(value, dict) else {}


# Singleton instance (espelha o padrão de workflow_classifier).
_default_classifier: JourneyClassifier | None = None


def get_journey_classifier() -> JourneyClassifier:
    """Retorna o classificador de jornada padrão (singleton)."""
    global _default_classifier
    if _default_classifier is None:
        _default_classifier = JourneyClassifier()
    return _default_classifier
