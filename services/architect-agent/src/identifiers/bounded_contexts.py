"""Bounded Contexts Identifier using DDD principles."""

from typing import List, Optional
import json
from openai import AsyncOpenAI
from structlog import get_logger

from architect.models.bounded_context import (
    BoundedContext,
    BoundedContextRelationship,
    BoundedContextsAnalysis,
    UbiquitousLanguageTerm
)

logger = get_logger(__name__)


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

    def __init__(
        self,
        llm_client: Optional[AsyncOpenAI] = None,
        model: str = "gpt-4"
    ):
        """
        Inicializa o identificador de bounded contexts.

        Args:
            llm_client: Cliente OpenAI (opcional, cria padrão se não fornecido)
            model: Modelo LLM a usar
        """
        self._llm_client = llm_client or AsyncOpenAI()
        self._model = model
        self._logger = logger

    async def identify(
        self,
        requirements: str,
        domain_hints: Optional[List[str]] = None
    ) -> BoundedContextsAnalysis:
        """
        Identifica bounded contexts a partir de requisitos.

        Args:
            requirements: Texto com requisitos do sistema
            domain_hints: Lista opcional de nomes de contextos sugeridos

        Returns:
            BoundedContextsAnalysis com contexts identificados
        """
        self._logger.info("identifying_bounded_contexts", domain_hints=domain_hints)

        prompt = self.PROMPT_TEMPLATE.format(requirements=requirements)

        if domain_hints:
            prompt += f"\n\nSUGESTÕES DE CONTEXTOS: {', '.join(domain_hints)}"

        try:
            response = await self._llm_client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": "Você é um especialista em DDD."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.3
            )

            result_data = json.loads(response.choices[0].message.content)

            contexts = [
                self._parse_context(ctx_data)
                for ctx_data in result_data.get("contexts", [])
            ]

            analysis = BoundedContextsAnalysis(
                contexts=contexts,
                total_contexts=len(contexts),
                confidence_score=result_data.get("confidence_score", 0.8)
            )

            self._logger.info(
                "bounded_contexts_identified",
                count=len(contexts),
                confidence=analysis.confidence_score
            )

            return analysis

        except Exception as e:
            self._logger.error("failed_to_identify_contexts", error=str(e))
            raise

    def _parse_context(self, ctx_data: dict) -> BoundedContext:
        """Parse dados brutos para BoundedContext."""

        relationships = [
            BoundedContextRelationship(
                from_context=rel["from"],
                to_context=rel["to"],
                relationship_type=rel["type"],
                description=rel.get("description")
            )
            for rel in ctx_data.get("relationships", [])
        ]

        ubiquitous_language = [
            UbiquitousLanguageTerm(
                term=term["term"],
                definition=term["definition"],
                examples=term.get("examples", [])
            )
            for term in ctx_data.get("ubiquitous_language", [])
        ]

        return BoundedContext(
            name=ctx_data["name"],
            description=ctx_data["description"],
            responsibilities=ctx_data.get("responsibilities", []),
            domain_models=ctx_data.get("domain_models", []),
            relationships=relationships,
            ubiquitous_language=ubiquitous_language
        )
