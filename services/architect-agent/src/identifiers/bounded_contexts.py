"""Bounded Contexts Identifier using DDD principles."""

import json

from openai import AsyncOpenAI
from structlog import get_logger
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.models.bounded_context import (
    BoundedContext,
    BoundedContextRelationship,
    BoundedContextsAnalysis,
    UbiquitousLanguageTerm,
)

logger = get_logger(__name__)

# Constantes de validação
MAX_REQUIREMENTS_LENGTH = 15000
MIN_REQUIREMENTS_LENGTH = 50
MAX_DOMAIN_HINTS = 10


class BoundedContextsIdentifier:
    """Identifica Bounded Contexts baseado em DDD."""

    PROMPT_TEMPLATE = """
Você é um especialista em Domain-Driven Design (DDD).

Analise os seguintes requisitos e identifique os Bounded Contexts.

REQUISITOS:
{requirements}

Para cada Bounded Context, especifique:
1. Nome: Nome claro e conciso (ex: Identity, Billing, Catalog)
2. Descrição: Propósito principal do contexto
3. Responsabilidades: Lista do que este contexto é responsável
4. Domain Models: Lista de modelos de domínio principais
5. Linguagem Ubíqua: 3-5 termos específicos do domínio com definições

Relacionamentos entre contextos:
- Partnership: Colaboração necessária
- Shared Kernel: Models partilhados
- Customer-Supplier: Dependência direta
- Conformist: Seguindo convenções externas

Responda em formato JSON válido com esta estrutura:
{{
  "contexts": [
    {{
      "name": "Nome",
      "description": "Descrição",
      "responsibilities": ["resp1", "resp2"],
      "domain_models": ["Model1", "Model2"],
      "ubiquitous_language": [
        {{"term": "Termo", "definition": "Definição"}}
      ],
      "relationships": [
        {{"from": "ContextoA", "to": "ContextoB", "type": "Partnership", "description": "..."}}
      ]
    }}
  ],
  "confidence_score": 0.9
}}
"""

    def __init__(self, llm_client: AsyncOpenAI | None = None, model: str = "gpt-4"):
        """
        Inicializa o identificador de bounded contexts.

        Args:
            llm_client: Cliente OpenAI (opcional, cria padrão se não fornecido)
            model: Modelo LLM a usar
        """
        self._llm_client = llm_client or AsyncOpenAI()
        self._model = model
        self._logger = logger

    def _validate_input(self, requirements: str, domain_hints: list[str] | None):
        """Valida input antes de processar.

        Args:
            requirements: Texto com requisitos
            domain_hints: Lista de sugestões de contextos

        Raises:
            ValueError: Se input for inválido
        """
        if not requirements or not requirements.strip():
            raise ValueError("Requirements cannot be empty")

        requirements_length = len(requirements)
        if requirements_length < MIN_REQUIREMENTS_LENGTH:
            raise ValueError(
                f"Requirements too short: {requirements_length} < {MIN_REQUIREMENTS_LENGTH}"
            )
        if requirements_length > MAX_REQUIREMENTS_LENGTH:
            raise ValueError(
                f"Requirements too long: {requirements_length} > {MAX_REQUIREMENTS_LENGTH}"
            )

        if domain_hints and len(domain_hints) > MAX_DOMAIN_HINTS:
            raise ValueError(f"Too many domain hints: {len(domain_hints)} > {MAX_DOMAIN_HINTS}")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((ConnectionError, TimeoutError)),
        reraise=True,
    )
    async def _call_llm(self, prompt: str) -> dict:
        """Chama LLM com retry logic.

        Args:
            prompt: Prompt completo

        Returns:
            Dict com resposta JSON

        Raises:
            ConnectionError: Se falhar após 3 tentativas
            TimeoutError: Se timeout após 3 tentativas
        """
        response = await self._llm_client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": "Você é um especialista em DDD."},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.3,
        )

        return json.loads(response.choices[0].message.content)

    async def identify(
        self, requirements: str, domain_hints: list[str] | None = None
    ) -> BoundedContextsAnalysis:
        """
        Identifica bounded contexts a partir de requisitos.

        Args:
            requirements: Texto com requisitos do sistema
            domain_hints: Lista opcional de nomes de contextos sugeridos

        Returns:
            BoundedContextsAnalysis com contexts identificados

        Raises:
            ValueError: Se input for inválido
            ConnectionError: Se LLM API falhar após retries
            TimeoutError: Se LLM API timeout após retries
        """
        # Validar input
        self._validate_input(requirements, domain_hints)

        self._logger.info("identifying_bounded_contexts", domain_hints=domain_hints)

        prompt = self.PROMPT_TEMPLATE.format(requirements=requirements)

        if domain_hints:
            prompt += f"\n\nSUGESTÕES DE CONTEXTOS: {', '.join(domain_hints)}"

        try:
            # Chamar LLM com retry logic
            result_data = await self._call_llm(prompt)

            contexts = [
                self._parse_context(ctx_data) for ctx_data in result_data.get("contexts", [])
            ]

            analysis = BoundedContextsAnalysis(
                contexts=contexts,
                total_contexts=len(contexts),
                confidence_score=result_data.get("confidence_score", 0.8),
            )

            self._logger.info(
                "bounded_contexts_identified",
                count=len(contexts),
                confidence=analysis.confidence_score,
            )

            return analysis

        except ValueError:
            # Re-raise validation errors
            raise
        except (ConnectionError, TimeoutError) as e:
            # Re-raise retry errors com contexto
            self._logger.error("llm_call_failed_after_retries", error=str(e))
            raise
        except Exception as e:
            # Log outros errors inesperados
            self._logger.error(
                "failed_to_identify_contexts", error=str(e), error_type=type(e).__name__
            )
            raise

    def _parse_context(self, ctx_data: dict) -> BoundedContext:
        """Parse dados brutos para BoundedContext."""

        relationships = [
            BoundedContextRelationship(
                from_context=rel["from"],
                to_context=rel["to"],
                relationship_type=rel["type"],
                description=rel.get("description"),
            )
            for rel in ctx_data.get("relationships", [])
        ]

        ubiquitous_language = [
            UbiquitousLanguageTerm(
                term=term["term"], definition=term["definition"], examples=term.get("examples", [])
            )
            for term in ctx_data.get("ubiquitous_language", [])
        ]

        return BoundedContext(
            name=ctx_data["name"],
            description=ctx_data["description"],
            responsibilities=ctx_data.get("responsibilities", []),
            domain_models=ctx_data.get("domain_models", []),
            relationships=relationships,
            ubiquitous_language=ubiquitous_language,
        )
