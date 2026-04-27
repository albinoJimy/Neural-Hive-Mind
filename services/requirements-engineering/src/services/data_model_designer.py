"""Serviço para design de modelos de dados."""

import json
import re
import uuid
from typing import Any

import structlog
from src.clients.llm_client_wrapper import LLMClient
from src.config.settings import get_settings
from src.models.data_model import (
    DataField,
    DataFieldType,
    DataModel,
    DataSchema,
    EntityRelationship,
)
from src.models.requirements import RequirementsSet

logger = structlog.get_logger(__name__)

DATA_MODEL_GENERATION_PROMPT = """
Você é um arquiteto de software especialista em modelagem de dados. Analise os seguintes requisitos e proponha modelos de dados.

**Requisitos:**
{requirements_text}

**Instruções:**
1. Identifique as entidades principais do domínio
2. Para cada entidade, defina os campos com tipos apropriados
3. Identifique relacionamentos entre entidades (one-to-one, one-to-many, many-to-many)
4. Retorne APENAS JSON válido

**Formato JSON:**
{{
  "models": [
    {{
      "name": "NomeEntidade",
      "description": "Descrição da entidade",
      "fields": [
        {{
          "name": "nome_campo",
          "type": "string|integer|float|boolean|date|datetime|text|json|reference",
          "required": true|false,
          "description": "Descrição do campo",
          "reference_to": "EntidadeReferenciada (se tipo=reference)"
        }}
      ]
    }}
  ],
  "relationships": [
    {{
      "from": "EntidadeOrigem",
      "to": "EntidadeDestino",
      "type": "one_to_one|one_to_many|many_to_many",
      "cardinality": "1:N|N:M|1:1",
      "description": "Descrição do relacionamento"
    }}
  ]
}}
"""


class DataModelDesigner:
    """Serviço para design de modelos de dados usando LLM."""

    def __init__(self, llm_client: LLMClient | None = None):
        """Inicializa o DataModelDesigner.

        Args:
            llm_client: Cliente LLM (opcional, cria padrão se não fornecido)
        """
        settings = get_settings()
        self._llm_client = llm_client or LLMClient()
        self._model = settings.llm_model
        self._logger = logger

    async def design_from_requirements(
        self,
        requirements_set: RequirementsSet,
    ) -> DataSchema:
        """Desenha modelos de dados a partir de requisitos.

        Args:
            requirements_set: Conjunto de requisitos

        Returns:
            DataSchema com modelos e relacionamentos
        """
        self._logger.info(
            "designing_data_models",
            requirements_set_id=requirements_set.id,
            total_requirements=len(requirements_set.requirements),
        )

        # Preparar texto dos requisitos
        requirements_text = "\n".join(
            [
                f"- {r.title}: {r.description[:200]}..."
                for r in requirements_set.requirements[:10]  # Limitar para contexto
            ]
        )

        prompt = DATA_MODEL_GENERATION_PROMPT.format(requirements_text=requirements_text)

        try:
            response = await self._llm_client.generate(
                messages=[
                    {
                        "role": "system",
                        "content": "Você é um arquiteto de software especialista em modelagem de dados.",
                    },
                    {"role": "user", "content": prompt},
                ],
                model=self._model,
                temperature=0.5,
                max_tokens=3000,
            )

            content = response.choices[0].message["content"]

            # Extrair JSON da resposta
            json_match = self._extract_json(content)
            design_data = json.loads(json_match) if json_match else json.loads(content)

            # Criar DataSchema
            schema = DataSchema(
                id=f"DMS-{uuid.uuid4().hex[:8].upper()}",
                name=f"Schema-{requirements_set.id}",
                cognitive_plan_id=requirements_set.cognitive_plan_id,
                requirements_set_id=requirements_set.id,
            )

            # Processar modelos
            for model_data in design_data.get("models", []):
                data_model = self._create_data_model(model_data)
                schema.add_model(data_model)

            # Processar relacionamentos
            for rel_data in design_data.get("relationships", []):
                relationship = EntityRelationship(
                    **{  # Usar alias "from" e "to" diretamente
                        "from": rel_data.get("from", ""),
                        "to": rel_data.get("to", ""),
                        "relationship_type": rel_data.get("type", ""),
                        "cardinality": rel_data.get("cardinality", ""),
                        "description": rel_data.get("description"),
                    }
                )
                schema.relationships.append(relationship)

            self._logger.info(
                "data_models_designed",
                schema_id=schema.id,
                models_count=len(schema.models),
                relationships_count=len(schema.relationships),
            )

            return schema

        except Exception:
            self._logger.exception("failed_to_design_data_models")
            raise

    def _create_data_model(self, model_data: dict[str, Any]) -> DataModel:
        """Cria um DataModel a partir de dados JSON.

        Args:
            model_data: Dados do modelo

        Returns:
            DataModel populado
        """
        model_id = f"DM-{uuid.uuid4().hex[:6].upper()}"
        fields: list[DataField] = []

        # Campo ID primário por padrão
        fields.append(
            DataField(
                name="id",
                field_type=DataFieldType.STRING,
                required=True,
                unique=True,
                description="Identificador único",
            )
        )

        # Criar campos do modelo
        for field_data in model_data.get("fields", []):
            field = DataField(
                name=field_data.get("name", ""),
                field_type=self._parse_field_type(field_data.get("type", "string")),
                required=field_data.get("required", False),
                unique=field_data.get("unique", False),
                description=field_data.get("description"),
                reference_to=field_data.get("reference_to"),
            )
            fields.append(field)

        # Campo timestamps por padrão
        fields.extend(
            [
                DataField(
                    name="created_at",
                    field_type=DataFieldType.DATETIME,
                    required=True,
                    description="Data de criação",
                ),
                DataField(
                    name="updated_at",
                    field_type=DataFieldType.DATETIME,
                    required=False,
                    description="Data de atualização",
                ),
            ]
        )

        return DataModel(
            id=model_id,
            name=model_data.get("name", ""),
            description=model_data.get("description"),
            fields=fields,
            primary_key=["id"],
        )

    def _parse_field_type(self, value: str) -> DataFieldType:
        """Converte string para DataFieldType."""
        mapping = {
            "string": DataFieldType.STRING,
            "integer": DataFieldType.INTEGER,
            "float": DataFieldType.FLOAT,
            "boolean": DataFieldType.BOOLEAN,
            "date": DataFieldType.DATE,
            "datetime": DataFieldType.DATETIME,
            "text": DataFieldType.TEXT,
            "json": DataFieldType.JSON,
            "reference": DataFieldType.REFERENCE,
        }
        return mapping.get(value.lower(), DataFieldType.STRING)

    def _extract_json(self, text: str) -> str | None:
        """Extrai JSON de texto markdown."""
        # Tentar encontrar JSON em blocos markdown
        json_match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
        if json_match:
            return json_match.group(1)

        # Tentar encontrar JSON sem markdown
        json_match = re.search(r"\{.*\}", text, re.DOTALL)
        if json_match:
            return json_match.group(0)

        return None
