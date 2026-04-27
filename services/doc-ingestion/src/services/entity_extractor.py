"""Extrator de Entidades usando LLM."""

import json
import uuid
from typing import Any

import structlog

from src.clients.llm_client_wrapper import LLMClient
from src.config.settings import get_settings
from src.models.entities import EntityType, ExtractedEntity

logger = structlog.get_logger(__name__)


class EntityExtractor:
    """Extrai entidades de documentos usando LLM (OpenAI ou Anthropic)."""

    def __init__(
        self,
        llm_client: LLMClient | None = None,
        provider: str | None = None,
        min_confidence: float = 0.7,
    ):
        """Inicializa o extrator.

        Args:
            llm_client: Cliente LLM (opcional, cria padrão se None)
            provider: Provider LLM ("openai" ou "anthropic", usa settings se None)
            min_confidence: Confiança mínima para incluir entidade (0.0 a 1.0)
        """
        settings = get_settings()

        if llm_client is None:
            provider_name = provider or settings.llm_provider
            self._client = LLMClient(model=settings.llm_model, provider=provider_name)
            self._provider = provider_name
        else:
            self._client = llm_client
            self._provider = provider or settings.llm_provider

        self._model = settings.llm_model
        self._min_confidence = min_confidence
        self._logger = logger

    async def extract(
        self,
        document_id: str,
        text: str,
        context: dict[str, Any] | None = None,
    ) -> list[ExtractedEntity]:
        """
        Extrai entidades de um texto de documento.

        Args:
            document_id: ID do documento
            text: Texto para analisar
            context: Contexto adicional opcional (tipo de doc, seção, etc.)

        Returns:
            Lista de entidades extraídas filtradas por confiança mínima
        """
        self._logger.info(
            "entity_extraction_started",
            document_id=document_id,
            text_length=len(text),
            provider=self._provider,
        )

        prompt = self._build_extraction_prompt(text, context)

        try:
            if self._provider == "openai":
                content = await self._call_openai(prompt)
            else:  # anthropic
                content = await self._call_anthropic(prompt)

            entities = self._parse_llm_response(content, document_id)

            # Filtrar por confiança mínima
            filtered_entities = [e for e in entities if e.confidence_score >= self._min_confidence]

            self._logger.info(
                "entity_extraction_completed",
                document_id=document_id,
                total_extracted=len(entities),
                filtered_count=len(filtered_entities),
            )

            return filtered_entities

        except Exception as e:
            self._logger.error(
                "entity_extraction_failed",
                document_id=document_id,
                error=str(e),
                exc_info=True,
            )
            raise

    async def _call_openai(self, prompt: str) -> str:
        """Faz chamada à API OpenAI."""
        response = await self._client.generate(
            messages=[
                {"role": "system", "content": self._get_system_prompt()},
                {"role": "user", "content": prompt},
            ],
            model=self._model,
            temperature=0.3,
            max_tokens=8000,
        )
        # Acessar content via dict (compatibilidade neural_hive_llm)
        content = response.choices[0].message.get("content", "[]")
        return content or "[]"

    async def _call_anthropic(self, prompt: str) -> str:
        """Faz chamada à API Anthropic (via neural_hive_llm wrapper)."""
        response = await self._client.generate(
            messages=[
                {"role": "system", "content": self._get_system_prompt()},
                {"role": "user", "content": prompt},
            ],
            model=self._model,
            temperature=0.3,
            max_tokens=8000,
        )
        # Acessar content via dict (compatibilidade neural_hive_llm)
        content = response.choices[0].message.get("content", "[]")
        return content or "[]"

    def _get_system_prompt(self) -> str:
        """Retorna o prompt de sistema para o LLM."""
        return """You are an expert software analyst specialized in extracting structured information from technical documentation.

Your task is to analyze the provided text and extract meaningful entities such as:
- Functionalities (features, capabilities)
- Requirements (functional and non-functional)
- Data Models (entities, fields, relationships)
- APIs (endpoints, methods, parameters)
- Tech Stack mentions
- Dependencies

For each extracted entity, provide:
1. type: One of "functionality", "requirement", "data_model", "api", "tech_stack", "dependency"
2. name: A concise name/title
3. description: Detailed description
4. source_text: The exact text from which this was extracted
5. confidence_score: Your confidence (0.0 to 1.0) that this is a valid entity

Respond ONLY with a valid JSON array. No markdown, no explanation."""

    def _build_extraction_prompt(self, text: str, context: dict[str, Any] | None) -> str:
        """Constrói o prompt para extração."""
        context_section = ""
        if context:
            context_section = f"\n\nAdditional Context:\n{json.dumps(context, indent=2)}"

        # Truncar texto se muito longo para o modelo
        max_text_length = 10000
        truncated_text = text[:max_text_length]
        if len(text) > max_text_length:
            truncated_text += "\n\n[Text truncated due to length...]"

        return f"""Analyze the following documentation text and extract all meaningful entities.

{truncated_text}{context_section}

Respond with a JSON array of entities."""

    def _parse_llm_response(self, content: str, document_id: str) -> list[ExtractedEntity]:
        """Parse a resposta do LLM para entidades."""
        try:
            # Limpar markdown code blocks se presente
            cleaned_content = content.strip()
            if "```json" in cleaned_content:
                cleaned_content = cleaned_content.split("```json")[1].split("```")[0].strip()
            elif "```" in cleaned_content:
                cleaned_content = cleaned_content.split("```")[1].split("```")[0].strip()

            data = json.loads(cleaned_content)

            entities = []
            for item in data:
                try:
                    entity_type = EntityType(item.get("type", "functionality"))
                    entity = ExtractedEntity(
                        id=str(uuid.uuid4()),
                        document_id=document_id,
                        type=entity_type,
                        name=item.get("name", ""),
                        description=item.get("description", ""),
                        source_text=item.get("source_text", ""),
                        confidence_score=item.get("confidence_score", 0.8),
                        metadata={
                            k: v
                            for k, v in item.items()
                            if k
                            not in [
                                "type",
                                "name",
                                "description",
                                "source_text",
                                "confidence_score",
                            ]
                        },
                    )
                    entities.append(entity)
                except (ValueError, KeyError) as e:
                    self._logger.warning("failed_to_parse_entity", item=item, error=str(e))
                    continue

            return entities

        except json.JSONDecodeError as e:
            self._logger.error("llm_response_not_json", content=content[:500], error=str(e))
            raise ValueError(f"LLM response is not valid JSON: {e}") from e
