"""
Schema Mapper Service para Data Migration System.

Implementa análise de schema legado e geração de mapeamentos usando LLM
(OpenAI/Anthropic) para migração de dados.
"""

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import structlog

from src.config.settings import get_settings
from src.models.migration import FieldMapping, SchemaMapping, TableMapping

logger = structlog.get_logger()

# Prompt template para LLM
LLM_MAPPING_PROMPT = """You are a database migration expert. Analyze the following legacy database schema and generate a mapping to a modern schema.

Legacy Schema:
{legacy_schema}

Target Requirements:
- Modern PostgreSQL 17+
- Proper foreign keys
- Optimized data types
- Audit columns (created_at, updated_at)
- Exclude soft-deleted records where applicable

Generate a JSON mapping following this structure:
{{
  "tables": [
    {{
      "legacy_name": "users",
      "modern_name": "users",
      "action": "migrate",
      "fields": [
        {{
          "legacy_name": "id",
          "modern_name": "id",
          "data_type": "uuid",
          "transformation": "cast_to_uuid",
          "nullable": false,
          "is_primary_key": true
        }}
      ],
      "filters": ["status != 'deleted'"],
      "pre_actions": ["CREATE INDEX IF NOT EXISTS idx_users_email..."],
      "post_actions": ["ANALYZE users;"]
    }}
  ]
}}

Guidelines:
1. Use modern PostgreSQL data types (uuid, timestamp with time zone, jsonb, etc.)
2. Add created_at and updated_at columns if they don't exist
3. Suggest indexes for frequently queried columns
4. Identify foreign key relationships
5. Exclude soft-deleted records with filters
6. For incompatible types, suggest appropriate transformations
"""


class SchemaMapperError(Exception):
    """Exceção base para erros do Schema Mapper."""


class LLMProviderError(SchemaMapperError):
    """Erro ao chamar provedor LLM."""


class SchemaAnalysisError(SchemaMapperError):
    """Erro ao analisar schema legado."""


class SchemaMapper:
    """
    Serviço de mapeamento de schema baseado em LLM.

    Analisa schema legado e gera mapeamentos para schema moderno
    usando OpenAI ou Anthropic Claude.
    """

    def __init__(
        self,
        llm_provider: Optional[str] = None,
        llm_model: Optional[str] = None,
        llm_temperature: Optional[float] = None,
        llm_max_tokens: Optional[int] = None,
    ):
        """
        Inicializa Schema Mapper.

        Args:
            llm_provider: Provedor LLM ('openai' ou 'anthropic')
            llm_model: Modelo a usar
            llm_temperature: Temperatura para geração
            llm_max_tokens: Máximo de tokens
        """
        settings = get_settings()

        self.llm_provider = llm_provider or settings.llm_provider
        self.llm_model = llm_model or settings.llm_model
        self.llm_temperature = llm_temperature or settings.llm_temperature
        self.llm_max_tokens = llm_max_tokens or settings.llm_max_tokens

        # API keys
        self.openai_api_key = settings.openai_api_key
        self.anthropic_api_key = settings.anthropic_api_key

        self._openai_client = None
        self._anthropic_client = None

    def _get_openai_client(self):
        """Retorna cliente OpenAI (lazy initialization)."""
        if self._openai_client is None:
            try:
                from openai import OpenAI

                if not self.openai_api_key:
                    raise LLMProviderError("OPENAI_API_KEY não configurada")

                self._openai_client = OpenAI(api_key=self.openai_api_key)
                logger.info("openai_client_initialized")
            except ImportError as e:
                raise LLMProviderError("OpenAI não disponível. Instale: pip install openai") from e
        return self._openai_client

    def _get_anthropic_client(self):
        """Retorna cliente Anthropic (lazy initialization)."""
        if self._anthropic_client is None:
            try:
                from anthropic import Anthropic

                if not self.anthropic_api_key:
                    raise LLMProviderError("ANTHROPIC_API_KEY não configurada")

                self._anthropic_client = Anthropic(api_key=self.anthropic_api_key)
                logger.info("anthropic_client_initialized")
            except ImportError as e:
                raise LLMProviderError(
                    "Anthropic não disponível. Instale: pip install anthropic"
                ) from e
        return self._anthropic_client

    async def analyze_legacy_schema(
        self,
        postgres_client,
        schema: str = "public",
        tables: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Analisa schema legado e extrai informações.

        Args:
            postgres_client: Cliente PostgreSQL conectado
            schema: Schema a analisar
            tables: Lista específica de tabelas (None = todas)

        Returns:
            Dicionário com schema analisado

        Raises:
            SchemaAnalysisError: Se falhar ao analisar schema
        """
        try:
            # Obter lista de tabelas
            if tables:
                table_list = tables
            else:
                table_list = await postgres_client.get_tables(schema=schema)

            logger.info(
                "analyzing_legacy_schema",
                schema=schema,
                table_count=len(table_list),
            )

            analyzed_schema = {
                "schema": schema,
                "tables": [],
                "relationships": [],
                "indexes": [],
            }

            for table_name in table_list:
                # Obter colunas
                columns = await postgres_client.get_table_schema(
                    table_name=table_name, schema=schema
                )

                # Obter primary keys
                primary_keys = await postgres_client.get_primary_keys(
                    table_name=table_name, schema=schema
                )

                # Obter foreign keys
                foreign_keys = await postgres_client.get_foreign_keys(
                    table_name=table_name, schema=schema
                )

                # Obter índices
                indexes = await postgres_client.get_indexes(table_name=table_name, schema=schema)

                # Contar linhas
                row_count = await postgres_client.get_table_count(
                    table_name=table_name, schema=schema
                )

                table_info = {
                    "name": table_name,
                    "columns": columns,
                    "primary_keys": primary_keys,
                    "foreign_keys": foreign_keys,
                    "row_count": row_count,
                }

                analyzed_schema["tables"].append(table_info)

                # Adicionar índices
                for idx in indexes:
                    analyzed_schema["indexes"].append({"table": table_name, **idx})

                # Adicionar relacionamentos
                for fk in foreign_keys:
                    analyzed_schema["relationships"].append(
                        {
                            "from_table": table_name,
                            "from_column": fk["column_name"],
                            "to_table": fk["foreign_table_name"],
                            "to_column": fk["foreign_column_name"],
                            "constraint_name": fk["constraint_name"],
                        }
                    )

            logger.info(
                "legacy_schema_analyzed",
                table_count=len(analyzed_schema["tables"]),
                relationship_count=len(analyzed_schema["relationships"]),
                index_count=len(analyzed_schema["indexes"]),
            )

            return analyzed_schema

        except Exception as e:
            logger.error("schema_analysis_failed", error=str(e))
            raise SchemaAnalysisError(f"Falha ao analisar schema: {e}") from e

    async def generate_schema_mapping(
        self,
        legacy_schema: Dict[str, Any],
        legacy_connection_id: str,
        nhm_target: str,
        target_schema: str = "public",
    ) -> SchemaMapping:
        """
        Usa LLM para gerar mapeamento de schema.

        Args:
            legacy_schema: Schema analisado (retorno de analyze_legacy_schema)
            legacy_connection_id: ID da conexão legada
            nhm_target: Serviço NHM de destino
            target_schema: Schema alvo (padrão: public)

        Returns:
            SchemaMapping com mapeamento gerado

        Raises:
            LLMProviderError: Se falhar chamada ao LLM
        """
        # Preparar schema para prompt
        schema_text = self._format_schema_for_prompt(legacy_schema)

        prompt = LLM_MAPPING_PROMPT.format(legacy_schema=schema_text)

        try:
            llm_response = await self._call_llm(prompt)

            # Parse JSON response
            mapping_data = self._parse_llm_response(llm_response)

            # Converter para modelos Pydantic
            table_mappings = []

            for table_data in mapping_data.get("tables", []):
                fields = []
                for field_data in table_data.get("fields", []):
                    field = FieldMapping(
                        source_field=field_data.get("legacy_name", ""),
                        target_field=field_data.get("modern_name", ""),
                        data_type=field_data.get("data_type", "text"),
                        nullable=field_data.get("nullable", True),
                        is_primary_key=field_data.get("is_primary_key", False),
                        is_foreign_key=field_data.get("is_foreign_key", False),
                        foreign_key_reference=field_data.get("foreign_key_reference"),
                        transform=field_data.get("transformation"),
                        default_value=field_data.get("default_value"),
                        description=field_data.get("description"),
                    )
                    fields.append(field)

                table_mapping = TableMapping(
                    source_schema=target_schema,
                    source_table=table_data.get("legacy_name", ""),
                    target_table=table_data.get("modern_name", ""),
                    target_schema=target_schema,
                    fields=fields,
                    source_filter=(
                        table_data.get("filters", [None])[0] if table_data.get("filters") else None
                    ),
                    target_pre_actions=table_data.get("pre_actions"),
                    target_post_actions=table_data.get("post_actions"),
                    batch_key_field=table_data.get("batch_key_field"),
                    estimated_rows=table_data.get("estimated_rows"),
                )
                table_mappings.append(table_mapping)

            schema_mapping = SchemaMapping(
                legacy_connection_id=legacy_connection_id,
                nhm_target=nhm_target,
                tables=table_mappings,
                metadata={
                    "llm_provider": self.llm_provider,
                    "llm_model": self.llm_model,
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "legacy_table_count": len(legacy_schema.get("tables", [])),
                },
            )

            logger.info(
                "schema_mapping_generated",
                table_count=len(table_mappings),
                llm_provider=self.llm_provider,
                llm_model=self.llm_model,
            )

            return schema_mapping

        except LLMProviderError as e:
            logger.error("llm_provider_error", error=str(e))
            # Retornar mapping vazio em caso de erro LLM (fail-soft)
            return SchemaMapping(
                legacy_connection_id=legacy_connection_id,
                nhm_target=nhm_target,
                tables=[],
                metadata={
                    "error": str(e),
                    "llm_provider": self.llm_provider,
                    "generation_failed": True,
                },
            )
        except Exception as e:
            logger.error("mapping_generation_failed", error=str(e))
            # Retornar mapping vazio em caso de erro (fail-soft)
            return SchemaMapping(
                legacy_connection_id=legacy_connection_id,
                nhm_target=nhm_target,
                tables=[],
                metadata={
                    "error": str(e),
                    "llm_provider": self.llm_provider,
                    "generation_failed": True,
                },
            )

    async def approve_mapping(
        self,
        schema_mapping: SchemaMapping,
        approved_by: str,
    ) -> SchemaMapping:
        """
        Marca mapeamento como aprovado para uso.

        Args:
            schema_mapping: SchemaMapping a aprovar
            approved_by: Usuário ou serviço que aprovou

        Returns:
            SchemaMapping atualizado
        """
        schema_mapping.metadata["approved"] = True
        schema_mapping.metadata["approved_by"] = approved_by
        schema_mapping.metadata["approved_at"] = datetime.now(timezone.utc).isoformat()
        schema_mapping.updated_at = datetime.now(timezone.utc)

        logger.info(
            "schema_mapping_approved",
            mapping_id=id(schema_mapping),
            approved_by=approved_by,
            table_count=len(schema_mapping.tables),
        )

        return schema_mapping

    async def suggest_transformations(
        self,
        source_type: str,
        target_type: str,
        sample_values: Optional[List[Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Sugere transformações para tipos de dados incompatíveis.

        Args:
            source_type: Tipo de dados origem
            target_type: Tipo de dados alvo
            sample_values: Valores de exemplo para análise

        Returns:
            Lista de transformações sugeridas
        """
        transformations = []

        # Mapeamentos comuns de tipo
        type_mappings = {
            ("varchar", "uuid"): [
                {
                    "transformation": "cast_to_uuid",
                    "sql_template": "CAST({source} AS UUID)",
                    "validation": "check if valid UUID format",
                    "requires": "source values must be valid UUID strings",
                }
            ],
            ("varchar", "integer"): [
                {
                    "transformation": "cast_to_int",
                    "sql_template": "CAST({source} AS INTEGER)",
                    "validation": "check if numeric",
                    "requires": "source values must be numeric strings",
                },
                {
                    "transformation": "extract_numeric",
                    "sql_template": "CAST(REGEXP_REPLACE({source}, '\\D', '', 'g') AS INTEGER)",
                    "validation": "extract numbers from string",
                    "requires": "extracts first numeric sequence",
                },
            ],
            ("varchar", "timestamp"): [
                {
                    "transformation": "parse_timestamp",
                    "sql_template": "CAST({source} AS TIMESTAMP)",
                    "validation": "check if valid timestamp format",
                    "requires": "ISO 8601 or compatible format",
                },
            ],
            ("timestamp", "timestamptz"): [
                {
                    "transformation": "convert_to_utc",
                    "sql_template": "CAST({source} AS TIMESTAMP WITH TIME ZONE)",
                    "validation": "assume local timezone",
                    "requires": "may need timezone adjustment",
                },
            ],
            ("text", "jsonb"): [
                {
                    "transformation": "parse_json",
                    "sql_template": "CAST({source} AS JSONB)",
                    "validation": "check if valid JSON",
                    "requires": "source must be valid JSON string",
                },
            ],
        }

        # Normalizar tipos
        source_norm = source_type.lower().split("(")[0]
        target_norm = target_type.lower().split("(")[0]

        key = (source_norm, target_norm)
        if key in type_mappings:
            transformations = type_mappings[key]
        else:
            # Sugerir cast genérico
            transformations = [
                {
                    "transformation": "generic_cast",
                    "sql_template": f"CAST({{{{source}}}} AS {target_type})",
                    "validation": "may lose precision or fail",
                    "requires": "compatible data required",
                }
            ]

        # Se valores de exemplo fornecidos, validar
        if sample_values:
            for transform in transformations:
                transform["sample_analysis"] = self._analyze_samples(
                    sample_values, source_type, target_type
                )

        logger.info(
            "transformations_suggested",
            source_type=source_type,
            target_type=target_type,
            count=len(transformations),
        )

        return transformations

    def _format_schema_for_prompt(self, legacy_schema: Dict[str, Any]) -> str:
        """Formata schema analisado para o prompt LLM."""
        lines = [f"Schema: {legacy_schema.get('schema', 'public')}\n"]

        for table in legacy_schema.get("tables", []):
            lines.append(f"Table: {table['name']} ({table.get('row_count', 0)} rows)")
            lines.append("  Columns:")

            for col in table.get("columns", []):
                nullable = "NULL" if col.get("is_nullable") == "YES" else "NOT NULL"
                default = f" DEFAULT {col['column_default']}" if col.get("column_default") else ""
                lines.append(f"    - {col['column_name']}: {col['data_type']}{default} {nullable}")

            if table.get("primary_keys"):
                lines.append(f"  Primary Keys: {', '.join(table['primary_keys'])}")

            if table.get("foreign_keys"):
                lines.append("  Foreign Keys:")
                for fk in table["foreign_keys"]:
                    lines.append(
                        f"    - {fk['column_name']} -> {fk['foreign_table_name']}.{fk['foreign_column_name']}"
                    )

            lines.append("")

        if legacy_schema.get("relationships"):
            lines.append("\nRelationships:")
            for rel in legacy_schema["relationships"]:
                lines.append(
                    f"  - {rel['from_table']}.{rel['from_column']} -> "
                    f"{rel['to_table']}.{rel['to_column']}"
                )

        return "\n".join(lines)

    def _parse_llm_response(self, response: str) -> Dict[str, Any]:
        """
        Faz parse da resposta LLM para JSON.

        Args:
            response: Resposta do LLM

        Returns:
            Dicionário com dados do mapeamento

        Raises:
            LLMProviderError: Se falhar parse
        """
        try:
            # Tentar extrair JSON da resposta
            # LLMs às vezes retornam markdown com ```json
            cleaned = response.strip()

            if cleaned.startswith("```"):
                # Remover markdown code blocks
                lines = cleaned.split("\n")
                if lines[0].startswith("```json"):
                    lines = lines[1:]
                elif lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].strip().startswith("```"):
                    lines = lines[:-1]
                # Remover indentação comum das linhas restantes
                if lines:
                    # Encontrar indentação mínima
                    min_indent = None
                    for line in lines:
                        if line.strip():  # Ignorar linhas vazias
                            indent = len(line) - len(line.lstrip())
                            if min_indent is None or indent < min_indent:
                                min_indent = indent
                    # Remover indentação mínima de todas as linhas
                    if min_indent and min_indent > 0:
                        lines = [
                            line[min_indent:] if len(line) >= min_indent else line for line in lines
                        ]
                cleaned = "\n".join(lines)

            return json.loads(cleaned)

        except json.JSONDecodeError as e:
            logger.error("llm_response_parse_failed", response=response[:500])
            raise LLMProviderError(f"Falha ao parsear resposta LLM: {e}") from e

    async def _call_llm(self, prompt: str) -> str:
        """
        Chama provedor LLM configurado.

        Args:
            prompt: Prompt para enviar ao LLM

        Returns:
            Resposta do LLM

        Raises:
            LLMProviderError: Se falhar chamada
        """
        if self.llm_provider == "openai":
            return await self._call_openai(prompt)
        elif self.llm_provider == "anthropic":
            return await self._call_anthropic(prompt)
        else:
            raise LLMProviderError(
                f"Provedor LLM inválido: {self.llm_provider}. " "Use 'openai' ou 'anthropic'"
            )

    async def _call_openai(self, prompt: str) -> str:
        """Chama API OpenAI."""
        try:
            client = self._get_openai_client()

            response = client.chat.completions.create(
                model=self.llm_model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a database migration expert. "
                        "Respond only with valid JSON.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=self.llm_temperature,
                max_tokens=self.llm_max_tokens,
            )

            result = response.choices[0].message.content
            logger.info("openai_call_success", model=self.llm_model)

            return result

        except Exception as e:
            logger.error("openai_call_failed", error=str(e))
            raise LLMProviderError(f"Falha ao chamar OpenAI: {e}") from e

    async def _call_anthropic(self, prompt: str) -> str:
        """Chama API Anthropic Claude."""
        try:
            client = self._get_anthropic_client()

            response = client.messages.create(
                model=self.llm_model,
                max_tokens=self.llm_max_tokens,
                temperature=self.llm_temperature,
                messages=[
                    {
                        "role": "user",
                        "content": "You are a database migration expert. "
                        "Respond only with valid JSON.\n\n" + prompt,
                    }
                ],
            )

            result = response.content[0].text
            logger.info("anthropic_call_success", model=self.llm_model)

            return result

        except Exception as e:
            logger.error("anthropic_call_failed", error=str(e))
            raise LLMProviderError(f"Falha ao chamar Anthropic: {e}") from e

    def _analyze_samples(
        self,
        sample_values: List[Any],
        source_type: str,
        target_type: str,
    ) -> Dict[str, Any]:
        """Analisa valores de exemplo para transformação."""
        return {
            "sample_count": len(sample_values),
            "examples": sample_values[:5],  # Primeiros 5
            "source_type": source_type,
            "target_type": target_type,
        }


# Singleton instance
_schema_mapper: Optional[SchemaMapper] = None


def get_schema_mapper() -> SchemaMapper:
    """
    Retorna singleton do Schema Mapper.

    Returns:
        Instância de SchemaMapper
    """
    global _schema_mapper
    if _schema_mapper is None:
        _schema_mapper = SchemaMapper()
    return _schema_mapper
