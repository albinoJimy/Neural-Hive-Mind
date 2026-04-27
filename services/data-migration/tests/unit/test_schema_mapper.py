"""
Testes unitários para Schema Mapper Service.

Cobre análise de schema legado, geração de mapeamentos com LLM,
aprovação de mapeamentos e sugestões de transformação.
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.models.migration import SchemaMapping
from src.services.schema_mapper import (
    LLMProviderError,
    SchemaAnalysisError,
    SchemaMapper,
    get_schema_mapper,
)


class TestSchemaMapperInitialization:
    """Testes para inicialização do Schema Mapper."""

    def test_schema_mapper_initialization_default(self):
        """Verifica inicialização com valores padrão."""
        with patch("src.services.schema_mapper.get_settings") as mock_settings:
            mock_settings.return_value.llm_provider = "openai"
            mock_settings.return_value.llm_model = "gpt-4-turbo-preview"
            mock_settings.return_value.llm_temperature = 0.3
            mock_settings.return_value.llm_max_tokens = 8000
            mock_settings.return_value.openai_api_key = "test-key"
            mock_settings.return_value.anthropic_api_key = "test-key"

            mapper = SchemaMapper()

            assert mapper.llm_provider == "openai"
            assert mapper.llm_model == "gpt-4-turbo-preview"
            assert mapper.llm_temperature == 0.3
            assert mapper.llm_max_tokens == 8000
            assert mapper.openai_api_key == "test-key"
            assert mapper.anthropic_api_key == "test-key"

    def test_schema_mapper_initialization_custom(self):
        """Verifica inicialização com valores customizados."""
        mapper = SchemaMapper(
            llm_provider="anthropic",
            llm_model="claude-3-opus-20240229",
            llm_temperature=0.5,
            llm_max_tokens=4000,
        )

        assert mapper.llm_provider == "anthropic"
        assert mapper.llm_model == "claude-3-opus-20240229"
        assert mapper.llm_temperature == 0.5
        assert mapper.llm_max_tokens == 4000


class TestAnalyzeLegacySchema:
    """Testes para análise de schema legado."""

    @pytest.mark.asyncio
    async def test_analyze_legacy_schema_success(self):
        """Verifica análise bem-sucedida de schema legado."""
        # Mock do PostgreSQL client
        mock_pg = AsyncMock()
        mock_pg.get_tables = AsyncMock(return_value=["users", "orders"])
        mock_pg.get_table_schema = AsyncMock(
            side_effect=[
                [  # users
                    {
                        "column_name": "id",
                        "data_type": "integer",
                        "is_nullable": "NO",
                        "column_default": "nextval('users_id_seq')",
                    },
                    {
                        "column_name": "name",
                        "data_type": "character varying",
                        "is_nullable": "NO",
                        "column_default": None,
                    },
                ],
                [  # orders
                    {
                        "column_name": "id",
                        "data_type": "integer",
                        "is_nullable": "NO",
                        "column_default": "nextval('orders_id_seq')",
                    },
                    {
                        "column_name": "user_id",
                        "data_type": "integer",
                        "is_nullable": "NO",
                        "column_default": None,
                    },
                ],
            ]
        )
        mock_pg.get_primary_keys = AsyncMock(side_effect=[["id"], ["id"]])
        mock_pg.get_foreign_keys = AsyncMock(
            side_effect=[
                [],  # users
                [  # orders
                    {
                        "column_name": "user_id",
                        "foreign_table_name": "users",
                        "foreign_column_name": "id",
                        "constraint_name": "fk_orders_user_id",
                    }
                ],
            ]
        )
        mock_pg.get_indexes = AsyncMock(
            side_effect=[
                [{"indexname": "idx_users_name", "indexdef": "CREATE INDEX..."}],
                [],
            ]
        )
        mock_pg.get_table_count = AsyncMock(side_effect=[100, 500])

        mapper = SchemaMapper()

        result = await mapper.analyze_legacy_schema(mock_pg, schema="public")

        assert result["schema"] == "public"
        assert len(result["tables"]) == 2
        assert result["tables"][0]["name"] == "users"
        assert result["tables"][1]["name"] == "orders"
        assert len(result["relationships"]) == 1
        assert result["relationships"][0]["from_table"] == "orders"
        assert result["relationships"][0]["to_table"] == "users"
        assert len(result["indexes"]) == 1

    @pytest.mark.asyncio
    async def test_analyze_legacy_schema_specific_tables(self):
        """Verifica análise de tabelas específicas."""
        mock_pg = AsyncMock()
        mock_pg.get_tables = AsyncMock(return_value=["users", "orders", "products"])
        mock_pg.get_table_schema = AsyncMock(
            return_value=[
                {
                    "column_name": "id",
                    "data_type": "integer",
                    "is_nullable": "NO",
                    "column_default": None,
                }
            ]
        )
        mock_pg.get_primary_keys = AsyncMock(return_value=["id"])
        mock_pg.get_foreign_keys = AsyncMock(return_value=[])
        mock_pg.get_indexes = AsyncMock(return_value=[])
        mock_pg.get_table_count = AsyncMock(return_value=100)

        mapper = SchemaMapper()

        # Analisar apenas tabela users
        result = await mapper.analyze_legacy_schema(mock_pg, schema="public", tables=["users"])

        assert len(result["tables"]) == 1
        assert result["tables"][0]["name"] == "users"

    @pytest.mark.asyncio
    async def test_analyze_legacy_schema_failure(self):
        """Verifica tratamento de erro na análise."""
        mock_pg = AsyncMock()
        mock_pg.get_tables = AsyncMock(side_effect=Exception("Connection lost"))

        mapper = SchemaMapper()

        with pytest.raises(SchemaAnalysisError):
            await mapper.analyze_legacy_schema(mock_pg)


class TestGenerateSchemaMapping:
    """Testes para geração de mapeamento de schema."""

    @pytest.mark.asyncio
    async def test_generate_schema_mapping_openai_success(self):
        """Verifica geração de mapeamento com OpenAI."""
        legacy_schema = {
            "schema": "public",
            "tables": [
                {
                    "name": "users",
                    "columns": [
                        {
                            "column_name": "id",
                            "data_type": "integer",
                            "is_nullable": "NO",
                        }
                    ],
                    "primary_keys": ["id"],
                    "foreign_keys": [],
                    "row_count": 100,
                }
            ],
            "relationships": [],
            "indexes": [],
        }

        # Resposta mock do LLM client (via neural_hive_llm)
        mock_response = Mock()
        mock_response.choices = [Mock()]
        # O novo wrapper usa dict para message
        mock_response.choices[0].message = {
            "role": "assistant",
            "content": """```json
        {
          "tables": [
            {
              "legacy_name": "users",
              "modern_name": "nhm_users",
              "fields": [
                {
                  "legacy_name": "id",
                  "modern_name": "id",
                  "data_type": "uuid",
                  "nullable": false,
                  "is_primary_key": true,
                  "transformation": "cast_to_uuid"
                }
              ]
            }
          ]
        }
        ```""",
        }

        with patch("src.services.schema_mapper.SchemaMapper._get_llm_client") as mock_client:
            mock_llm_client = Mock()
            mock_llm_client.generate = AsyncMock(return_value=mock_response)
            mock_client.return_value = mock_llm_client

            mapper = SchemaMapper(llm_provider="openai")

            result = await mapper.generate_schema_mapping(
                legacy_schema=legacy_schema,
                legacy_connection_id="postgres-legacy-01",
                nhm_target="feature-store",
            )

            assert isinstance(result, SchemaMapping)
            assert result.legacy_connection_id == "postgres-legacy-01"
            assert result.nhm_target == "feature-store"
            assert len(result.tables) == 1
            assert result.tables[0].source_table == "users"
            assert result.tables[0].target_table == "nhm_users"
            assert len(result.tables[0].fields) == 1
            assert result.tables[0].fields[0].source_field == "id"
            assert result.tables[0].fields[0].target_field == "id"
            assert result.tables[0].fields[0].data_type == "uuid"
            assert result.tables[0].fields[0].transform == "cast_to_uuid"

    @pytest.mark.asyncio
    async def test_generate_schema_mapping_anthropic_success(self):
        """Verifica geração de mapeamento com Anthropic."""
        legacy_schema = {
            "schema": "public",
            "tables": [
                {
                    "name": "products",
                    "columns": [{"column_name": "id", "data_type": "integer", "is_nullable": "NO"}],
                    "primary_keys": ["id"],
                    "foreign_keys": [],
                    "row_count": 50,
                }
            ],
            "relationships": [],
            "indexes": [],
        }

        # Resposta mock do LLM client (via neural_hive_llm)
        mock_response = Mock()
        mock_response.choices = [Mock()]
        # O novo wrapper usa dict para message
        mock_response.choices[0].message = {
            "role": "assistant",
            "content": """```json
        {
          "tables": [
            {
              "legacy_name": "products",
              "modern_name": "nhm_products",
              "fields": [
                {
                  "legacy_name": "id",
                  "modern_name": "id",
                  "data_type": "uuid",
                  "nullable": false,
                  "is_primary_key": true
                }
              ]
            }
          ]
        }
        ```""",
        }

        with patch("src.services.schema_mapper.SchemaMapper._get_llm_client") as mock_client:
            mock_llm_client = Mock()
            mock_llm_client.generate = AsyncMock(return_value=mock_response)
            mock_client.return_value = mock_llm_client

            mapper = SchemaMapper(llm_provider="anthropic")

            result = await mapper.generate_schema_mapping(
                legacy_schema=legacy_schema,
                legacy_connection_id="postgres-legacy-01",
                nhm_target="feature-store",
            )

            assert isinstance(result, SchemaMapping)
            assert len(result.tables) == 1
            assert result.tables[0].source_table == "products"

    @pytest.mark.asyncio
    async def test_generate_schema_mapping_with_filters_and_actions(self):
        """Verifica mapeamento com filtros e ações."""
        legacy_schema = {
            "schema": "public",
            "tables": [],
            "relationships": [],
            "indexes": [],
        }

        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message = {
            "role": "assistant",
            "content": """{
          "tables": [
            {
              "legacy_name": "orders",
              "modern_name": "nhm_orders",
              "fields": [],
              "filters": ["deleted_at IS NULL"],
              "pre_actions": ["DROP INDEX IF EXISTS idx_old"],
              "post_actions": ["CREATE INDEX idx_new ON nhm_orders(id)"]
            }
          ]
        }""",
        }

        with patch("src.services.schema_mapper.SchemaMapper._get_llm_client") as mock_client:
            mock_llm_client = Mock()
            mock_llm_client.generate = AsyncMock(return_value=mock_response)
            mock_client.return_value = mock_llm_client

            mapper = SchemaMapper(llm_provider="openai")

            result = await mapper.generate_schema_mapping(
                legacy_schema=legacy_schema,
                legacy_connection_id="postgres-legacy-01",
                nhm_target="feature-store",
            )

            assert result.tables[0].source_filter == "deleted_at IS NULL"
            assert len(result.tables[0].target_pre_actions) == 1
            assert "DROP INDEX" in result.tables[0].target_pre_actions[0]
            assert len(result.tables[0].target_post_actions) == 1
            assert "CREATE INDEX" in result.tables[0].target_post_actions[0]

    @pytest.mark.asyncio
    async def test_generate_schema_mapping_llm_failure_fail_soft(self):
        """Verifica fail-soft em caso de falha do LLM."""
        legacy_schema = {"schema": "public", "tables": []}

        with patch("src.services.schema_mapper.SchemaMapper._get_llm_client") as mock_client:
            mock_llm_client = Mock()
            mock_llm_client.generate = Mock(side_effect=Exception("API rate limit"))
            mock_client.return_value = mock_llm_client

            mapper = SchemaMapper(llm_provider="openai")

            result = await mapper.generate_schema_mapping(
                legacy_schema=legacy_schema,
                legacy_connection_id="postgres-legacy-01",
                nhm_target="feature-store",
            )

            # Deve retornar SchemaMapping vazio (fail-soft)
            assert isinstance(result, SchemaMapping)
            assert len(result.tables) == 0
            assert result.metadata.get("generation_failed") is True
            assert "error" in result.metadata

    @pytest.mark.asyncio
    async def test_generate_schema_mapping_invalid_llm_provider(self):
        """Verifica fail-soft com provedor LLM inválido."""
        mapper = SchemaMapper(llm_provider="invalid")

        result = await mapper.generate_schema_mapping(
            legacy_schema={},
            legacy_connection_id="test",
            nhm_target="test",
        )

        # Deve retornar SchemaMapping vazio (fail-soft)
        assert isinstance(result, SchemaMapping)
        assert len(result.tables) == 0
        assert result.metadata.get("generation_failed") is True
        assert "Provedor LLM inválido" in result.metadata.get("error", "")


class TestApproveMapping:
    """Testes para aprovação de mapeamento."""

    @pytest.mark.asyncio
    async def test_approve_mapping_success(self):
        """Verifica aprovação de mapeamento."""
        mapper = SchemaMapper()

        schema_mapping = SchemaMapping(
            legacy_connection_id="postgres-legacy-01",
            nhm_target="feature-store",
            tables=[],
        )

        original_updated_at = schema_mapping.updated_at

        # Pequeno delay para garantir timestamp diferente
        import asyncio

        await asyncio.sleep(0.01)

        result = await mapper.approve_mapping(
            schema_mapping=schema_mapping,
            approved_by="admin@example.com",
        )

        assert result.metadata.get("approved") is True
        assert result.metadata.get("approved_by") == "admin@example.com"
        assert "approved_at" in result.metadata
        assert result.updated_at > original_updated_at


class TestSuggestTransformations:
    """Testes para sugestões de transformação."""

    @pytest.mark.asyncio
    async def test_suggest_transformations_varchar_to_uuid(self):
        """Verifica sugestão para varchar -> uuid."""
        mapper = SchemaMapper()

        transformations = await mapper.suggest_transformations(
            source_type="varchar",
            target_type="uuid",
        )

        assert len(transformations) > 0
        assert transformations[0]["transformation"] == "cast_to_uuid"
        assert "CAST" in transformations[0]["sql_template"]

    @pytest.mark.asyncio
    async def test_suggest_transformations_varchar_to_integer(self):
        """Verifica sugestão para varchar -> integer."""
        mapper = SchemaMapper()

        transformations = await mapper.suggest_transformations(
            source_type="varchar",
            target_type="integer",
        )

        assert len(transformations) >= 2
        assert transformations[0]["transformation"] == "cast_to_int"
        assert transformations[1]["transformation"] == "extract_numeric"

    @pytest.mark.asyncio
    async def test_suggest_transformations_with_samples(self):
        """Verifica análise com valores de exemplo."""
        mapper = SchemaMapper()

        samples = ["123", "456", "789"]

        transformations = await mapper.suggest_transformations(
            source_type="varchar",
            target_type="integer",
            sample_values=samples,
        )

        assert len(transformations) > 0
        assert "sample_analysis" in transformations[0]
        assert transformations[0]["sample_analysis"]["sample_count"] == 3
        assert transformations[0]["sample_analysis"]["examples"] == samples

    @pytest.mark.asyncio
    async def test_suggest_transformations_unknown_types(self):
        """Verifica sugestão genérica para tipos desconhecidos."""
        mapper = SchemaMapper()

        transformations = await mapper.suggest_transformations(
            source_type="custom_type",
            target_type="another_custom",
        )

        assert len(transformations) > 0
        assert transformations[0]["transformation"] == "generic_cast"


class TestFormatSchemaForPrompt:
    """Testes para formatação de schema para prompt."""

    def test_format_schema_for_prompt_basic(self):
        """Verifica formatação básica de schema."""
        mapper = SchemaMapper()

        legacy_schema = {
            "schema": "public",
            "tables": [
                {
                    "name": "users",
                    "row_count": 100,
                    "columns": [
                        {
                            "column_name": "id",
                            "data_type": "integer",
                            "is_nullable": "NO",
                            "column_default": "nextval('users_id_seq')",
                        }
                    ],
                    "primary_keys": ["id"],
                    "foreign_keys": [],
                }
            ],
            "relationships": [],
            "indexes": [],
        }

        result = mapper._format_schema_for_prompt(legacy_schema)

        assert "Schema: public" in result
        assert "Table: users" in result
        assert "(100 rows)" in result
        assert "id: integer" in result
        assert "NOT NULL" in result
        assert "Primary Keys: id" in result

    def test_format_schema_for_prompt_with_relationships(self):
        """Verifica formatação com relacionamentos."""
        mapper = SchemaMapper()

        legacy_schema = {
            "schema": "public",
            "tables": [],
            "relationships": [
                {
                    "from_table": "orders",
                    "from_column": "user_id",
                    "to_table": "users",
                    "to_column": "id",
                }
            ],
            "indexes": [],
        }

        result = mapper._format_schema_for_prompt(legacy_schema)

        assert "Relationships:" in result
        assert "orders.user_id -> users.id" in result


class TestParseLLMResponse:
    """Testes para parse de resposta LLM."""

    def test_parse_llm_response_valid_json(self):
        """Verifica parse de JSON válido."""
        mapper = SchemaMapper()

        response = '{"tables": [{"legacy_name": "users"}]}'

        result = mapper._parse_llm_response(response)

        assert result["tables"][0]["legacy_name"] == "users"

    def test_parse_llm_response_with_markdown(self):
        """Verifica parse com markdown code blocks."""
        mapper = SchemaMapper()

        response = """```json
        {
          "tables": [
            {"legacy_name": "users", "modern_name": "nhm_users"}
          ]
        }
        ```"""

        result = mapper._parse_llm_response(response)

        assert result["tables"][0]["legacy_name"] == "users"
        assert result["tables"][0]["modern_name"] == "nhm_users"

    def test_parse_llm_response_invalid_json(self):
        """Verifica erro para JSON inválido."""
        mapper = SchemaMapper()

        response = "this is not valid json"

        with pytest.raises(LLMProviderError, match="Falha ao parsear resposta LLM"):
            mapper._parse_llm_response(response)


class TestCallOpenAI:
    """Testes para chamada da API OpenAI via neural_hive_llm."""

    @pytest.mark.asyncio
    async def test_call_openai_success(self):
        """Verifica chamada bem-sucedida ao OpenAI."""
        mock_response = Mock()
        mock_response.choices = [Mock()]
        # O novo wrapper usa dict para message
        mock_response.choices[0].message = {"role": "assistant", "content": '{"result": "success"}'}

        with patch("src.services.schema_mapper.SchemaMapper._get_llm_client") as mock_client:
            mock_llm_client = Mock()
            mock_llm_client.generate = AsyncMock(return_value=mock_response)
            mock_client.return_value = mock_llm_client

            mapper = SchemaMapper(llm_provider="openai")
            result = await mapper._call_openai("test prompt")

            assert result == '{"result": "success"}'

    @pytest.mark.asyncio
    async def test_call_openai_failure(self):
        """Verifica tratamento de erro na chamada OpenAI."""
        with patch("src.services.schema_mapper.SchemaMapper._get_llm_client") as mock_client:
            mock_llm_client = Mock()
            mock_llm_client.generate = Mock(side_effect=Exception("API error"))
            mock_client.return_value = mock_llm_client

            mapper = SchemaMapper(llm_provider="openai")

            with pytest.raises(LLMProviderError, match="Falha ao chamar OpenAI"):
                await mapper._call_openai("test prompt")


class TestCallAnthropic:
    """Testes para chamada da API Anthropic via neural_hive_llm."""

    @pytest.mark.asyncio
    async def test_call_anthropic_success(self):
        """Verifica chamada bem-sucedida ao Anthropic."""
        mock_response = Mock()
        mock_response.choices = [Mock()]
        # O novo wrapper usa dict para message
        mock_response.choices[0].message = {"role": "assistant", "content": '{"result": "success"}'}

        with patch("src.services.schema_mapper.SchemaMapper._get_llm_client") as mock_client:
            mock_llm_client = Mock()
            mock_llm_client.generate = AsyncMock(return_value=mock_response)
            mock_client.return_value = mock_llm_client

            mapper = SchemaMapper(llm_provider="anthropic")
            result = await mapper._call_anthropic("test prompt")

            assert result == '{"result": "success"}'

    @pytest.mark.asyncio
    async def test_call_anthropic_failure(self):
        """Verifica tratamento de erro na chamada Anthropic."""
        with patch("src.services.schema_mapper.SchemaMapper._get_llm_client") as mock_client:
            mock_llm_client = Mock()
            mock_llm_client.generate = Mock(side_effect=Exception("API error"))
            mock_client.return_value = mock_llm_client

            mapper = SchemaMapper(llm_provider="anthropic")

            with pytest.raises(LLMProviderError, match="Falha ao chamar Anthropic"):
                await mapper._call_anthropic("test prompt")


class TestGetSchemaMapper:
    """Testes para singleton get_schema_mapper."""

    def test_get_schema_mapper_singleton(self):
        """Verifica que get_schema_mapper retorna singleton."""
        mapper1 = get_schema_mapper()
        mapper2 = get_schema_mapper()

        assert mapper1 is mapper2

    def test_get_schema_mapper_reset(self):
        """Verifica reset do singleton para testes."""
        # Primeira chamada
        mapper1 = get_schema_mapper()

        # Reset para teste
        from src.services import schema_mapper

        schema_mapper._schema_mapper = None

        # Nova instância
        mapper2 = get_schema_mapper()

        # São objetos diferentes após reset
        assert mapper1 is not mapper2


class TestAnalyzeSamples:
    """Testes para análise de valores de exemplo."""

    def test_analyze_samples_basic(self):
        """Verifica análise básica de amostras."""
        mapper = SchemaMapper()

        samples = ["value1", "value2", "value3"]

        result = mapper._analyze_samples(samples, "varchar", "integer")

        assert result["sample_count"] == 3
        assert result["examples"] == samples
        assert result["source_type"] == "varchar"
        assert result["target_type"] == "integer"

    def test_analyze_samples_limits_examples(self):
        """Verifica limitação de exemplos retornados."""
        mapper = SchemaMapper()

        samples = [f"value{i}" for i in range(10)]

        result = mapper._analyze_samples(samples, "varchar", "text")

        # Deve retornar apenas primeiros 5
        assert len(result["examples"]) == 5
        assert result["examples"] == ["value0", "value1", "value2", "value3", "value4"]
