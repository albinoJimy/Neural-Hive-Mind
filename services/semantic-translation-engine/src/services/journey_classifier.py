"""JourneyClassifier - decide a Journey (J1-J4) de um plano cognitivo.

Fase 1 (Task 2) — **Tier 1** — sinais estruturados determinísticos, SEM LLM.
Fase 2 (Task 3) — **Tier 2** — LLM semântico (`neural_hive_llm`) para os casos
ambíguos que o Tier 1 não resolve. O cliente LLM é injetado no construtor
(`llm_client`) para testabilidade; em qualquer falha do LLM (timeout, circuit
breaker aberto, resposta malformada, baixa confiança) degrada para `UNKNOWN`
(anti-verde-falso), nunca bloqueando o pipeline.

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

import json
import re
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

# Tier 2 (LLM): temperatura baixa para decisão determinística/explicável.
_LLM_TEMPERATURE = 0.0
_LLM_MAX_TOKENS = 512

# Defesa contra prompt injection: campos de texto livre vindos do utilizador
# (entities/metadata/text serializados) são truncados antes de entrar no prompt.
# Mitigação principal é temperature=0 + threshold de confiança, mas truncar
# limita a superfície de manipulação por payloads gigantes/adversariais.
_LLM_MAX_FIELD_CHARS = 500

# Jornadas que o LLM pode propor como decisão positiva. UNKNOWN é tratada
# como não-decisão (anti-verde-falso): cai em _no_match() mesmo se o LLM a
# devolver com confiança alta.
_LLM_DECIDABLE_JOURNEYS = {
    Journey.J1_PLAN_ONLY,
    Journey.J2_ORCHESTRATE,
    Journey.J3_BUILD,
    Journey.J4_MIGRATE,
}

# System prompt do classificador semântico (Tier 2).
_LLM_SYSTEM_PROMPT = (
    "És um classificador de jornada de execução de um pipeline cognitivo. "
    "Analisas o contexto e os inputs de uma intenção e decides qual a jornada "
    "que melhor a descreve. Jornadas possíveis:\n"
    "- J1_PLAN_ONLY: apenas planeamento, sem execução a jusante.\n"
    "- J2_ORCHESTRATE: orquestração de um workflow/serviços já existentes.\n"
    "- J3_BUILD: geração/construção de novo código ou artefactos.\n"
    "- J4_MIGRATE: migração ou ingestão de dados/sistemas legados.\n"
    "- UNKNOWN: nenhuma jornada é claramente aplicável.\n"
    "Responde EXCLUSIVAMENTE com um objeto JSON válido com as chaves "
    '"journey" (um dos valores acima), "confidence" (float em [0,1]) e '
    '"reasoning" (string curta a explicar a decisão). Não acrescentes texto '
    "fora do JSON."
)


class JourneyClassifier:
    """Classifica um plano cognitivo numa :class:`Journey` (híbrido tiered).

    O método público :meth:`classify` (assíncrono) aplica primeiro os sinais
    estruturados do **Tier 1** (síncronos, sem await) por ordem de precedência.
    Sem sinal forte e havendo ``llm_client`` injetado, delega ao **Tier 2**
    (LLM semântico via ``neural_hive_llm``, ``await``); qualquer falha do LLM
    degrada para ``UNKNOWN`` (anti-verde-falso). Sem ``llm_client`` o caminho
    sem-sinal devolve ``UNKNOWN`` (no_match).
    """

    def __init__(self, settings: Any | None = None, llm_client: Any | None = None) -> None:
        """Inicializa o classificador.

        Args:
            settings: objeto de configuração opcional. Se tiver o atributo
                ``journey_confidence_threshold``, é usado; caso contrário
                aplica-se :data:`JOURNEY_CONFIDENCE_THRESHOLD`.
            llm_client: cliente LLM opcional (dependency injection) para o
                Tier 2. Deve expor um método assíncrono
                ``generate(prompt, system_prompt, ...) -> obj`` com atributo
                ``.text`` (contrato de ``neural_hive_llm.LLMClient``). Se for
                ``None``, o Tier 2 não é ativado (comportamento da Fase 1).
        """
        self.confidence_threshold = getattr(
            settings, "journey_confidence_threshold", JOURNEY_CONFIDENCE_THRESHOLD
        )
        self.llm_client = llm_client

    async def classify(
        self,
        intent_envelope: dict[str, Any] | None,
        cognitive_plan: dict[str, Any] | None,
    ) -> JourneyDecision:
        """Decide a Journey (Tier 1 síncrono; Tier 2/LLM via ``await``).

        Método assíncrono para integrar de forma natural com o orchestrator
        async do STE (``process_intent``): o Tier 1 (sinais estruturados) é
        puro/sem await; só o ramo do LLM faz ``await self._classify_llm(...)``.

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

        # Sem sinal forte. Tier 2/LLM (Fase 2): se houver cliente LLM injetado,
        # delega a decisão ao LLM; QUALQUER falha (timeout, circuit aberto,
        # resposta malformada, baixa confiança) degrada para UNKNOWN
        # (anti-verde-falso), nunca bloqueando o pipeline.
        if self.llm_client is not None:
            try:
                return await self._classify_llm(intent_envelope, cognitive_plan)
            except Exception as exc:  # fallback resiliente (qualquer falha do LLM)
                logger.warning(
                    "journey_llm_failed_fallback_no_match",
                    error=str(exc),
                    error_type=type(exc).__name__,
                )
                return self._no_match()

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
                "Sem decisão fiável: os sinais estruturados (Tier 1: "
                "context.source, constraints.execution_mode, "
                "cognitive_plan.workflow_type) não resolveram a jornada e o "
                "Tier 2/LLM não decidiu (sem cliente, falha, resposta "
                "malformada ou confiança abaixo do threshold) -> UNKNOWN "
                "(anti-verde-falso)."
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

    async def _classify_llm(
        self,
        intent_envelope: dict[str, Any] | None,
        cognitive_plan: dict[str, Any] | None,
    ) -> JourneyDecision:
        """Tier 2 (LLM semântico, async) — decide a jornada nos casos ambíguos.

        Invoca o ``neural_hive_llm`` (com circuit breaker próprio) via ``await``
        com um prompt estruturado que pede ``{journey, confidence, reasoning}``.
        A resposta é parseada defensivamente; se não parsear, ``journey`` for
        inválida/UNKNOWN, ``confidence`` estiver ausente ou abaixo do
        threshold -> degrada para :meth:`_no_match` (anti-verde-falso).

        Sem ``llm_client`` levanta ``NotImplementedError`` (não há como fazer
        a classificação semântica) — o caminho normal de ``classify`` só chama
        este método quando ``self.llm_client is not None``.
        """
        if self.llm_client is None:
            raise NotImplementedError(
                "Tier 2/LLM requer um llm_client injetado; nenhum disponível."
            )

        prompt = self._build_llm_prompt(intent_envelope, cognitive_plan)
        # generate(...) é assíncrono em neural_hive_llm; aguardamos diretamente
        # no event loop do orchestrator (sem asyncio.run / thread pool).
        response = await self.llm_client.generate(
            prompt=prompt,
            system_prompt=_LLM_SYSTEM_PROMPT,
            temperature=_LLM_TEMPERATURE,
            max_tokens=_LLM_MAX_TOKENS,
        )

        raw_text = getattr(response, "text", None)
        if not isinstance(raw_text, str) or not raw_text.strip():
            logger.warning("journey_llm_empty_response")
            return self._no_match()

        return self._decision_from_llm(raw_text)

    def _decision_from_llm(self, raw_text: str) -> JourneyDecision:
        """Parsing defensivo da resposta do LLM -> JourneyDecision ('llm').

        Qualquer anomalia (não-JSON, jornada inválida/UNKNOWN, confidence
        ausente/inválida ou abaixo do threshold) degrada para ``_no_match``.
        """
        payload = self._extract_json(raw_text)
        if not isinstance(payload, dict):
            logger.warning("journey_llm_unparseable", raw=raw_text[:200])
            return self._no_match()

        journey = self._coerce_journey(payload.get("journey"))
        if journey is None or journey not in _LLM_DECIDABLE_JOURNEYS:
            logger.warning("journey_llm_invalid_journey", value=payload.get("journey"))
            return self._no_match()

        confidence = self._coerce_confidence(payload.get("confidence"))
        if confidence is None:
            logger.warning("journey_llm_missing_confidence")
            return self._no_match()

        # Anti-verde-falso: baixa confiança não inventa jornada.
        if confidence < self.confidence_threshold:
            logger.info(
                "journey_llm_low_confidence_unknown",
                journey=journey.value,
                confidence=confidence,
                threshold=self.confidence_threshold,
            )
            return self._no_match()

        reasoning = payload.get("reasoning")
        if not isinstance(reasoning, str) or not reasoning.strip():
            reasoning = "(sem reasoning fornecido pelo LLM)"

        decision = JourneyDecision(
            journey=journey,
            journey_id=str(uuid4()),
            confidence=confidence,
            reasoning=f"Tier 2 (LLM): {reasoning}",
            classification_method="llm",
        )
        logger.info(
            "journey_classified",
            journey=journey.value,
            classification_method="llm",
            confidence=confidence,
        )
        return decision

    @staticmethod
    def _build_llm_prompt(
        intent_envelope: dict[str, Any] | None,
        cognitive_plan: dict[str, Any] | None,
    ) -> str:
        """Constrói o prompt estruturado com o contexto completo da intenção.

        Serializa de forma defensiva texto, entidades, domain, metadata e um
        resumo do cognitive_plan. Conteúdo não-serializável é convertido a
        string via ``default=str``.

        SEGURANÇA (prompt injection): ``text``, ``entities`` e ``metadata`` são
        texto livre controlado pelo utilizador e poderiam tentar manipular o
        classificador. São truncados a :data:`_LLM_MAX_FIELD_CHARS` para limitar
        a superfície de ataque. Mitigação principal continua a ser
        ``temperature=0`` + threshold de confiança (anti-verde-falso), mas
        truncar é uma defesa adicional contra payloads gigantes/adversariais.
        """
        envelope = intent_envelope if isinstance(intent_envelope, dict) else {}
        plan = cognitive_plan if isinstance(cognitive_plan, dict) else {}

        intent = envelope.get("intent") if isinstance(envelope.get("intent"), dict) else {}
        context = envelope.get("context") if isinstance(envelope.get("context"), dict) else {}

        # Resumo enxuto do plano (evita prompts gigantes/PII desnecessária).
        plan_summary = {
            "workflow_type": plan.get("workflow_type"),
            "domain": plan.get("domain") or intent.get("domain"),
            "num_tasks": len(plan.get("tasks", []))
            if isinstance(plan.get("tasks"), list)
            else None,
        }

        payload = {
            # Campos de texto livre do utilizador: truncar (defesa anti-injeção).
            "text": JourneyClassifier._truncate_field(intent.get("text") or envelope.get("text")),
            "entities": JourneyClassifier._truncate_field(
                intent.get("entities") or envelope.get("entities")
            ),
            "domain": intent.get("domain") or envelope.get("domain"),
            "metadata": JourneyClassifier._truncate_field(
                envelope.get("metadata") or context.get("metadata")
            ),
            "context_source": context.get("source"),
            "cognitive_plan_summary": plan_summary,
        }

        try:
            context_json = json.dumps(payload, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            context_json = str(payload)

        return (
            "Classifica a jornada da seguinte intenção. Contexto (JSON):\n"
            f"{context_json}\n\n"
            "Responde apenas com o JSON {journey, confidence, reasoning}."
        )

    @staticmethod
    def _truncate_field(value: Any) -> Any:
        """Trunca um campo de texto livre do utilizador (defesa anti-injeção).

        Serializa estruturas (listas/dicts de entidades/metadata) e corta a
        :data:`_LLM_MAX_FIELD_CHARS` chars, anexando um marcador de truncagem.
        Valores ``None`` passam intactos.
        """
        if value is None:
            return None
        if isinstance(value, str):
            text = value
        else:
            try:
                text = json.dumps(value, ensure_ascii=False, default=str)
            except (TypeError, ValueError):
                text = str(value)
        if len(text) > _LLM_MAX_FIELD_CHARS:
            return text[:_LLM_MAX_FIELD_CHARS] + "...[truncado]"
        return text

    @staticmethod
    def _extract_json(raw_text: str) -> dict[str, Any] | None:
        """Extrai um objeto JSON de uma resposta possivelmente ruidosa.

        Tenta: (1) JSON direto; (2) JSON dentro de um bloco ```json ... ```;
        (3) o primeiro objeto ``{...}`` encontrado no texto. Devolve ``None``
        se nada parsear.
        """
        text = raw_text.strip()

        # 1. JSON direto.
        try:
            parsed = json.loads(text)
            return parsed if isinstance(parsed, dict) else None
        except (json.JSONDecodeError, ValueError):
            pass

        # 2/3. Procurar o primeiro objeto {...} (cobre fences markdown e texto
        # extra à volta). Lazy (\{.*?\}) para não engolir do 1º { ao último }
        # quando há prefácio/sufixo, o que produziria JSON malformado.
        match = re.search(r"\{.*?\}", text, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group(0))
                return parsed if isinstance(parsed, dict) else None
            except (json.JSONDecodeError, ValueError):
                return None

        return None

    @staticmethod
    def _coerce_journey(value: Any) -> Journey | None:
        """Converte o valor devolvido pelo LLM para :class:`Journey` ou None."""
        if isinstance(value, Journey):
            return value
        if not isinstance(value, str):
            return None
        try:
            return Journey(value.strip())
        except ValueError:
            return None

    @staticmethod
    def _coerce_confidence(value: Any) -> float | None:
        """Converte ``confidence`` para float em [0,1] ou None se inválida."""
        if isinstance(value, bool):  # bool é subclasse de int — rejeitar
            return None
        if not isinstance(value, int | float):
            return None
        confidence = float(value)
        if not 0.0 <= confidence <= 1.0:
            return None
        return confidence

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
