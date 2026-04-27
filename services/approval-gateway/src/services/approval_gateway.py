"""Serviço Approval Gateway."""

from datetime import datetime, timezone
from typing import Optional

import structlog
from src.clients.llm_client_wrapper import LLMClient
from src.config.settings import get_settings
from src.models.approval import (
    ApprovalDecision,
    ApprovalMetrics,
    ApprovalPolicy,
    ApprovalRequest,
    ApprovalStatus,
)
from src.repositories.approvals_repository import ApprovalsRepository

logger = structlog.get_logger(__name__)


class ApprovalGateway:
    """Serviço de gateway de aprovações."""

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        repository: Optional[ApprovalsRepository] = None,
    ):
        """Inicializa o serviço."""
        settings = get_settings()
        self._llm_client = llm_client or LLMClient(api_key=settings.openai_api_key)
        self._llm_model = settings.llm_model
        self._llm_temperature = settings.llm_temperature
        self._logger = logger
        self._repository = repository or ApprovalsRepository()

        # Política padrão
        self._default_policy = ApprovalPolicy(
            id="default",
            name="Política Padrão",
            description="Política de aprovação padrão do sistema",
            auto_approve_threshold=settings.auto_approval_threshold,
            auto_reject_threshold=settings.auto_rejection_threshold,
            require_human_threshold=settings.require_human_threshold,
        )

    async def evaluate_request(
        self, request: ApprovalRequest, policy: Optional[ApprovalPolicy] = None
    ) -> ApprovalDecision:
        """
        Avalia uma solicitação de aprovação.

        Args:
            request: Solicitação a avaliar
            policy: Política a usar (usa padrão se não fornecida)

        Returns:
            Decisão de aprovação
        """
        policy = policy or self._default_policy
        self._logger.info(
            "evaluating_approval_request", request_id=request.id, request_type=request.type
        )

        # Verificar se a política se aplica
        if policy.applies_to_types and request.type not in policy.applies_to_types:
            self._logger.info(
                "policy_not_applicable",
                request_type=request.type,
                policy_types=policy.applies_to_types,
            )

        # Verificar regras de crítico
        complexity = request.context.get("complexity", 0)
        is_critical = request.context.get("is_critical", False)

        if is_critical and policy.require_human_for_critical:
            return await self._create_human_review_decision(request)

        if complexity > policy.max_auto_approve_complexity:
            return await self._create_human_review_decision(request)

        # Usar LLM para avaliar
        confidence, reasoning = await self._evaluate_with_llm(request)

        # Aplicar thresholds da política
        if confidence >= policy.auto_approve_threshold:
            status = ApprovalStatus.APPROVED
            approved_by = f"ai-{self._llm_model}"
        elif confidence <= policy.auto_reject_threshold:
            status = ApprovalStatus.REJECTED
            approved_by = f"ai-{self._llm_model}"
        else:
            # Zona cinzenta - requer humano
            status = ApprovalStatus.PENDING
            approved_by = None

        decision = ApprovalDecision(
            id=f"DEC-{request.id}",
            request_id=request.id,
            status=status,
            confidence_score=confidence,
            reasoning=reasoning,
            approved_by=approved_by,
            approved_at=datetime.now(timezone.utc),
        )

        self._logger.info(
            "decision_made", request_id=request.id, status=status.value, confidence=confidence
        )

        # Salvar no MongoDB
        await self._repository.save_request(request, decision)

        return decision

    async def _create_human_review_decision(self, request: ApprovalRequest) -> ApprovalDecision:
        """Cria decisão que requer revisão humana."""
        return ApprovalDecision(
            id=f"DEC-{request.id}",
            request_id=request.id,
            status=ApprovalStatus.PENDING,
            confidence_score=0.0,
            reasoning="Requer revisão humana devido a restrições de política",
            approved_by=None,
            approved_at=datetime.now(timezone.utc),
        )

    async def _evaluate_with_llm(self, request: ApprovalRequest) -> tuple[float, str]:
        """
        Avalia solicitação usando LLM.

        Returns:
            Tupla (confidence_score, reasoning)
        """
        prompt = self._build_evaluation_prompt(request)

        try:
            response = await self._llm_client.generate(
                model=self._llm_model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Você é um avaliador especialista em requisitos de software, "
                            "arquitetura e desenvolvimento. Avalie solicitações de forma "
                            "objetiva e detalhada."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=self._llm_temperature,
            )

            content = response.choices[0].message["content"]

            # Parse da resposta para extrair score e reasoning
            confidence = self._extract_confidence(content)
            reasoning = self._extract_reasoning(content)

            return confidence, reasoning

        except Exception as e:
            self._logger.error("llm_evaluation_failed", error=str(e))
            # Em caso de erro, retorna score médio e explicação
            return 0.5, f"Erro na avaliação automática: {e!s}"

    def _build_evaluation_prompt(self, request: ApprovalRequest) -> str:
        """Constrói prompt para avaliação."""
        context_str = "\n".join(f"- {k}: {v}" for k, v in request.context.items())

        return f"""Avalie a seguinte solicitação de aprovação:

**Tipo:** {request.type.value}
**Título:** {request.title}
**Descrição:** {request.description}
**Solicitado por:** {request.requested_by}

**Contexto Adicional:**
{context_str if context_str else "Nenhum"}

Por favor, forneça:

1. **Avaliação (0-100):** Qual a sua confiança de que esta solicitação deve ser APROVADA?
   - 0-30: Definitivamente rejeitar
   - 31-70: Requer análise humana mais detalhada
   - 71-100: Pode ser aprovada automaticamente

2. **Raciocínio:** Explique sua avaliação em 2-3 frases.

Formato de resposta:
AVALIACAO: <numero 0-100>
RACIOCINIO: <seu raciocinio>
"""

    def _extract_confidence(self, response: str) -> float:
        """Extrai score de confiança da resposta do LLM."""
        try:
            for line in response.split("\n"):
                if "AVALIACAO:" in line or "AVALIAÇÃO:" in line:
                    # Extrair número
                    number = "".join(c for c in line if c.isdigit() or c == ".")
                    if number:
                        score = float(number) / 100.0  # Converter para 0-1
                        return max(0.0, min(1.0, score))
        except Exception:
            pass
        return 0.5  # Valor padrão

    def _extract_reasoning(self, response: str) -> str:
        """Extrai raciocínio da resposta do LLM."""
        try:
            for line in response.split("\n"):
                if "RACIOCINIO:" in line:
                    return line.split("RACIOCINIO:")[-1].strip()
        except Exception:
            pass
        return response[:500]  # Retorna primeiros 500 chars

    async def get_metrics(self) -> ApprovalMetrics:
        """Retorna métricas de aprovações."""
        metrics_data = await self._repository.get_metrics()

        return ApprovalMetrics(
            total_requests=metrics_data.get("total", 0),
            pending_requests=metrics_data.get("pending", 0),
            approved_requests=metrics_data.get("approved", 0),
            rejected_requests=metrics_data.get("rejected", 0),
        )

    async def expire_pending_requests(self, timeout_hours: int = 24) -> int:
        """Expira solicitações pendentes antigas."""
        return await self._repository.expire_old_pending(timeout_hours)
