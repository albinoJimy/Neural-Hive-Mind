"""
Testes unitários para Data Validator Service.

Cobre validação de contagem de linhas, integridade referencial,
distribuição de valores e geração de relatórios.
"""

from unittest.mock import AsyncMock

import pytest

from src.models.migration import FieldMapping, SchemaMapping, TableMapping
from src.services.data_validator import (
    DataValidationError,
    DataValidator,
    ValidationResult,
    ValidationType,
    get_data_validator,
)


class TestValidationResult:
    """Testes para modelo ValidationResult."""

    def test_validation_result_creation_success(self):
        """Verifica criação de resultado de validação com sucesso."""
        result = ValidationResult(
            table_name="users",
            validation_type=ValidationType.ROW_COUNT,
            passed=True,
            legacy_count=1000,
            modern_count=1000,
            discrepancy=0,
            details={"message": "Contagem corresponde"},
        )

        assert result.table_name == "users"
        assert result.validation_type == ValidationType.ROW_COUNT
        assert result.passed is True
        assert result.legacy_count == 1000
        assert result.modern_count == 1000
        assert result.discrepancy == 0
        assert result.details["message"] == "Contagem corresponde"

    def test_validation_result_creation_failure(self):
        """Verifica criação de resultado de validação com falha."""
        result = ValidationResult(
            table_name="orders",
            validation_type=ValidationType.REFERENTIAL_INTEGRITY,
            passed=False,
            legacy_count=None,
            modern_count=None,
            discrepancy=5,
            details={
                "orphaned_records": 5,
                "foreign_key_column": "user_id",
                "referenced_table": "users",
            },
        )

        assert result.table_name == "orders"
        assert result.passed is False
        assert result.discrepancy == 5
        assert result.details["orphaned_records"] == 5


class TestDataValidatorInitialization:
    """Testes para inicialização do Data Validator."""

    def test_data_validator_initialization_default(self):
        """Verifica inicialização com valores padrão."""
        validator = DataValidator()

        assert validator.row_count_tolerance == 0
        assert validator.distribution_tolerance == 0.05
        assert validator.max_sample_size == 10000

    def test_data_validator_initialization_custom(self):
        """Verifica inicialização com valores customizados."""
        validator = DataValidator(
            row_count_tolerance=10,
            distribution_tolerance=0.03,
            max_sample_size=5000,
        )

        assert validator.row_count_tolerance == 10
        assert validator.distribution_tolerance == 0.03
        assert validator.max_sample_size == 5000


class TestValidateRowCounts:
    """Testes para validação de contagem de linhas."""

    @pytest.mark.asyncio
    async def test_validate_row_counts_all_match(self):
        """Verifica validação quando todas as contagens correspondem."""
        # Mock SchemaMapping
        schema_mapping = SchemaMapping(
            legacy_connection_id="postgres-legacy",
            nhm_target="feature-store",
            tables=[
                TableMapping(
                    source_schema="public",
                    source_table="users",
                    target_table="nhm_users",
                    fields=[
                        FieldMapping(
                            source_field="id",
                            target_field="id",
                            data_type="uuid",
                            nullable=False,
                            is_primary_key=True,
                        )
                    ],
                ),
                TableMapping(
                    source_schema="public",
                    source_table="orders",
                    target_table="nhm_orders",
                    fields=[
                        FieldMapping(
                            source_field="id",
                            target_field="id",
                            data_type="uuid",
                            nullable=False,
                            is_primary_key=True,
                        )
                    ],
                    source_filter="deleted_at IS NULL",
                ),
            ],
        )

        # Mock PostgreSQL clients
        legacy_client = AsyncMock()
        modern_client = AsyncMock()

        # Configurar retornos mock
        legacy_client.execute_query = AsyncMock(
            side_effect=[
                1000,  # COUNT(*) FROM users
                500,  # COUNT(*) FROM orders WHERE deleted_at IS NULL
            ]
        )
        modern_client.execute_query = AsyncMock(
            side_effect=[
                1000,  # COUNT(*) FROM nhm_users
                500,  # COUNT(*) FROM nhm_orders
            ]
        )

        validator = DataValidator()
        results = await validator.validate_row_counts(
            schema_mapping=schema_mapping,
            legacy_client=legacy_client,
            modern_client=modern_client,
        )

        assert len(results) == 2
        assert results[0].table_name == "users"
        assert results[0].passed is True
        assert results[0].legacy_count == 1000
        assert results[0].modern_count == 1000
        assert results[0].discrepancy == 0

        assert results[1].table_name == "orders"
        assert results[1].passed is True
        assert results[1].legacy_count == 500
        assert results[1].modern_count == 500

    @pytest.mark.asyncio
    async def test_validate_row_counts_with_discrepancy(self):
        """Verifica validação quando há discrepância na contagem."""
        schema_mapping = SchemaMapping(
            legacy_connection_id="postgres-legacy",
            nhm_target="feature-store",
            tables=[
                TableMapping(
                    source_schema="public",
                    source_table="products",
                    target_table="nhm_products",
                    fields=[
                        FieldMapping(
                            source_field="id",
                            target_field="id",
                            data_type="uuid",
                            nullable=False,
                            is_primary_key=True,
                        )
                    ],
                ),
            ],
        )

        legacy_client = AsyncMock()
        modern_client = AsyncMock()

        legacy_client.execute_query = AsyncMock(return_value=100)
        modern_client.execute_query = AsyncMock(return_value=95)

        validator = DataValidator()
        results = await validator.validate_row_counts(
            schema_mapping=schema_mapping,
            legacy_client=legacy_client,
            modern_client=modern_client,
        )

        assert len(results) == 1
        assert results[0].table_name == "products"
        assert results[0].passed is False
        assert results[0].legacy_count == 100
        assert results[0].modern_count == 95
        assert results[0].discrepancy == 5
        assert "faltando" in results[0].details["message"].lower()

    @pytest.mark.asyncio
    async def test_validate_row_counts_with_filter(self):
        """Verifica que filtro do SchemaMapping é aplicado."""
        schema_mapping = SchemaMapping(
            legacy_connection_id="postgres-legacy",
            nhm_target="feature-store",
            tables=[
                TableMapping(
                    source_schema="public",
                    source_table="orders",
                    target_table="nhm_orders",
                    fields=[],
                    source_filter="status != 'cancelled'",
                ),
            ],
        )

        legacy_client = AsyncMock()
        modern_client = AsyncMock()

        legacy_client.execute_query = AsyncMock(return_value=800)
        modern_client.execute_query = AsyncMock(return_value=800)

        validator = DataValidator()
        results = await validator.validate_row_counts(
            schema_mapping=schema_mapping,
            legacy_client=legacy_client,
            modern_client=modern_client,
        )

        # Verificar que a query legada incluiu o filtro
        assert legacy_client.execute_query.call_count == 1
        query_arg = legacy_client.execute_query.call_args[0][0]
        assert "status != 'cancelled'" in query_arg

        assert results[0].passed is True

    @pytest.mark.asyncio
    async def test_validate_row_counts_with_tolerance(self):
        """Verifica validação com tolerância configurada."""
        schema_mapping = SchemaMapping(
            legacy_connection_id="postgres-legacy",
            nhm_target="feature-store",
            tables=[
                TableMapping(
                    source_schema="public",
                    source_table="logs",
                    target_table="nhm_logs",
                    fields=[],
                ),
            ],
        )

        legacy_client = AsyncMock()
        modern_client = AsyncMock()

        legacy_client.execute_query = AsyncMock(return_value=10000)
        modern_client.execute_query = AsyncMock(return_value=9995)

        # Tolerância de 10 registros
        validator = DataValidator(row_count_tolerance=10)
        results = await validator.validate_row_counts(
            schema_mapping=schema_mapping,
            legacy_client=legacy_client,
            modern_client=modern_client,
        )

        # Discrepância de 5 está dentro da tolerância de 10
        assert results[0].passed is True
        assert results[0].discrepancy == 5


class TestValidateReferentialIntegrity:
    """Testes para validação de integridade referencial."""

    @pytest.mark.asyncio
    async def test_validate_referential_integrity_all_valid(self):
        """Verifica validação quando todas as FKs são válidas."""
        schema_mapping = SchemaMapping(
            legacy_connection_id="postgres-legacy",
            nhm_target="feature-store",
            tables=[
                TableMapping(
                    source_schema="public",
                    source_table="orders",
                    target_table="nhm_orders",
                    fields=[
                        FieldMapping(
                            source_field="user_id",
                            target_field="user_id",
                            data_type="uuid",
                            is_foreign_key=True,
                            foreign_key_reference="nhm_users.id",
                        )
                    ],
                ),
            ],
        )

        modern_client = AsyncMock()

        # Mock queries: verificar orfãos
        modern_client.execute_query = AsyncMock(
            side_effect=[
                [],  # Primeira verificação de orfãos (vazia = nenhum órfão)
            ]
        )

        validator = DataValidator()
        results = await validator.validate_referential_integrity(
            schema_mapping=schema_mapping,
            modern_client=modern_client,
        )

        assert len(results) == 1
        assert results[0].table_name == "orders"
        assert results[0].validation_type == ValidationType.REFERENTIAL_INTEGRITY
        assert results[0].passed is True
        # Quando passed=True, discrepancy é None (sem discrepância)
        assert results[0].discrepancy is None
        assert results[0].details["orphaned_count"] == 0

    @pytest.mark.asyncio
    async def test_validate_referential_integrity_with_orphans(self):
        """Verifica validação quando há registros órfãos."""
        schema_mapping = SchemaMapping(
            legacy_connection_id="postgres-legacy",
            nhm_target="feature-store",
            tables=[
                TableMapping(
                    source_schema="public",
                    source_table="order_items",
                    target_table="nhm_order_items",
                    fields=[
                        FieldMapping(
                            source_field="order_id",
                            target_field="order_id",
                            data_type="uuid",
                            is_foreign_key=True,
                            foreign_key_reference="nhm_orders.id",
                        )
                    ],
                ),
            ],
        )

        modern_client = AsyncMock()

        # Retornar 5 órfãos
        modern_client.execute_query = AsyncMock(
            return_value=[
                {"order_id": "orphan-1"},
                {"order_id": "orphan-2"},
                {"order_id": "orphan-3"},
                {"order_id": "orphan-4"},
                {"order_id": "orphan-5"},
            ]
        )

        validator = DataValidator()
        results = await validator.validate_referential_integrity(
            schema_mapping=schema_mapping,
            modern_client=modern_client,
        )

        assert len(results) == 1
        assert results[0].table_name == "order_items"
        assert results[0].passed is False
        assert results[0].discrepancy == 5
        assert results[0].details["orphaned_count"] == 5
        assert results[0].details["referenced_table"] == "public.nhm_orders"

    @pytest.mark.asyncio
    async def test_validate_referential_integrity_no_foreign_keys(self):
        """Verifica comportamento quando não há FKs."""
        schema_mapping = SchemaMapping(
            legacy_connection_id="postgres-legacy",
            nhm_target="feature-store",
            tables=[
                TableMapping(
                    source_schema="public",
                    source_table="logs",
                    target_table="nhm_logs",
                    fields=[
                        FieldMapping(
                            source_field="id",
                            target_field="id",
                            data_type="uuid",
                            is_primary_key=True,
                        )
                    ],
                ),
            ],
        )

        modern_client = AsyncMock()

        validator = DataValidator()
        results = await validator.validate_referential_integrity(
            schema_mapping=schema_mapping,
            modern_client=modern_client,
        )

        assert len(results) == 0
        # Não deve chamar execute_query se não há FKs
        assert modern_client.execute_query.call_count == 0

    @pytest.mark.asyncio
    async def test_validate_referential_integrity_multiple_fks(self):
        """Verifica validação com múltiplas FKs na mesma tabela."""
        schema_mapping = SchemaMapping(
            legacy_connection_id="postgres-legacy",
            nhm_target="feature-store",
            tables=[
                TableMapping(
                    source_schema="public",
                    source_table="order_items",
                    target_table="nhm_order_items",
                    fields=[
                        FieldMapping(
                            source_field="order_id",
                            target_field="order_id",
                            data_type="uuid",
                            is_foreign_key=True,
                            foreign_key_reference="nhm_orders.id",
                        ),
                        FieldMapping(
                            source_field="product_id",
                            target_field="product_id",
                            data_type="uuid",
                            is_foreign_key=True,
                            foreign_key_reference="nhm_products.id",
                        ),
                    ],
                ),
            ],
        )

        modern_client = AsyncMock()

        # Primeira FK válida, segunda com 3 órfãos
        modern_client.execute_query = AsyncMock(
            side_effect=[
                [],  # order_id - sem órfãos
                [  # product_id - com órfãos
                    {"product_id": "orphan-1"},
                    {"product_id": "orphan-2"},
                    {"product_id": "orphan-3"},
                ],
            ]
        )

        validator = DataValidator()
        results = await validator.validate_referential_integrity(
            schema_mapping=schema_mapping,
            modern_client=modern_client,
        )

        assert len(results) == 2
        # Primeira FK válida
        assert results[0].passed is True
        assert results[0].details["foreign_key_column"] == "order_id"
        # Segunda FK com órfãos
        assert results[1].passed is False
        assert results[1].discrepancy == 3
        assert results[1].details["foreign_key_column"] == "product_id"


class TestValidateValueDistribution:
    """Testes para validação de distribuição de valores."""

    @pytest.mark.asyncio
    async def test_validate_value_distribution_matching(self):
        """Verifica validação quando distribuições correspondem."""
        schema_mapping = SchemaMapping(
            legacy_connection_id="postgres-legacy",
            nhm_target="feature-store",
            tables=[
                TableMapping(
                    source_schema="public",
                    source_table="users",
                    target_table="nhm_users",
                    fields=[
                        FieldMapping(
                            source_field="status",
                            target_field="status",
                            data_type="varchar",
                        )
                    ],
                ),
            ],
        )

        legacy_client = AsyncMock()
        modern_client = AsyncMock()

        # Distribuição similar
        legacy_client.execute_query = AsyncMock(
            return_value=[
                {"value": "active", "count": 500},
                {"value": "inactive", "count": 300},
                {"value": "pending", "count": 200},
            ]
        )

        modern_client.execute_query = AsyncMock(
            return_value=[
                {"value": "active", "count": 502},  # +2
                {"value": "inactive", "count": 298},  # -2
                {"value": "pending", "count": 200},  # igual
            ]
        )

        validator = DataValidator()
        results = await validator.validate_value_distribution(
            schema_mapping=schema_mapping,
            legacy_client=legacy_client,
            modern_client=modern_client,
        )

        assert len(results) == 1
        assert results[0].table_name == "users"
        assert results[0].passed is True
        # A discrepância máxima é de 0.4% (2/500), dentro da tolerância de 5%

    @pytest.mark.asyncio
    async def test_validate_value_distribution_significant_discrepancy(self):
        """Verifica validação quando há discrepância significativa."""
        schema_mapping = SchemaMapping(
            legacy_connection_id="postgres-legacy",
            nhm_target="feature-store",
            tables=[
                TableMapping(
                    source_schema="public",
                    source_table="orders",
                    target_table="nhm_orders",
                    fields=[
                        FieldMapping(
                            source_field="status",
                            target_field="status",
                            data_type="varchar",
                        )
                    ],
                ),
            ],
        )

        legacy_client = AsyncMock()
        modern_client = AsyncMock()

        # Distribuição legada
        legacy_client.execute_query = AsyncMock(
            return_value=[
                {"value": "pending", "count": 100},
                {"value": "completed", "count": 800},
                {"value": "cancelled", "count": 100},
            ]
        )

        # Distribuição moderna com discrepância > 5%
        modern_client.execute_query = AsyncMock(
            return_value=[
                {"value": "pending", "count": 150},  # +50%
                {"value": "completed", "count": 700},  # -12.5%
                {"value": "cancelled", "count": 150},  # +50%
            ]
        )

        validator = DataValidator()
        results = await validator.validate_value_distribution(
            schema_mapping=schema_mapping,
            legacy_client=legacy_client,
            modern_client=modern_client,
        )

        assert len(results) == 1
        assert results[0].passed is False
        assert results[0].discrepancy > 0
        assert "discrepancies" in results[0].details

    @pytest.mark.asyncio
    async def test_validate_value_distribution_no_fields(self):
        """Verifica comportamento quando não há campos para validar."""
        schema_mapping = SchemaMapping(
            legacy_connection_id="postgres-legacy",
            nhm_target="feature-store",
            tables=[
                TableMapping(
                    source_schema="public",
                    source_table="logs",
                    target_table="nhm_logs",
                    fields=[
                        FieldMapping(
                            source_field="id",
                            target_field="id",
                            data_type="uuid",
                            is_primary_key=True,
                        )
                    ],
                ),
            ],
        )

        legacy_client = AsyncMock()
        modern_client = AsyncMock()

        validator = DataValidator()
        results = await validator.validate_value_distribution(
            schema_mapping=schema_mapping,
            legacy_client=legacy_client,
            modern_client=modern_client,
        )

        # Não há campos não-PK para validar distribuição
        assert len(results) == 0
        assert legacy_client.execute_query.call_count == 0

    @pytest.mark.asyncio
    async def test_validate_value_distribution_custom_tolerance(self):
        """Verifica validação com tolerância customizada."""
        schema_mapping = SchemaMapping(
            legacy_connection_id="postgres-legacy",
            nhm_target="feature-store",
            tables=[
                TableMapping(
                    source_schema="public",
                    source_table="products",
                    target_table="nhm_products",
                    fields=[
                        FieldMapping(
                            source_field="category",
                            target_field="category",
                            data_type="varchar",
                        )
                    ],
                ),
            ],
        )

        legacy_client = AsyncMock()
        modern_client = AsyncMock()

        legacy_client.execute_query = AsyncMock(
            return_value=[{"value": "electronics", "count": 100}]
        )

        # Discrepância de 10%
        modern_client.execute_query = AsyncMock(
            return_value=[{"value": "electronics", "count": 90}]
        )

        # Tolerância de 15% (maior que o padrão de 5%)
        validator = DataValidator(distribution_tolerance=0.15)
        results = await validator.validate_value_distribution(
            schema_mapping=schema_mapping,
            legacy_client=legacy_client,
            modern_client=modern_client,
        )

        # Com tolerância de 15%, 10% de discrepância é aceitável
        assert results[0].passed is True


class TestGenerateValidationReport:
    """Testes para geração de relatório de validação."""

    @pytest.mark.asyncio
    async def test_generate_validation_report_all_passed(self):
        """Verifica relatório quando todas as validações passam."""
        schema_mapping = SchemaMapping(
            legacy_connection_id="postgres-legacy",
            nhm_target="feature-store",
            tables=[
                TableMapping(
                    source_schema="public",
                    source_table="users",
                    target_table="nhm_users",
                    fields=[
                        FieldMapping(
                            source_field="id",
                            target_field="id",
                            data_type="uuid",
                            is_primary_key=True,
                        )
                    ],
                ),
            ],
        )

        legacy_client = AsyncMock()
        modern_client = AsyncMock()

        legacy_client.execute_query = AsyncMock(return_value=100)
        modern_client.execute_query = AsyncMock(return_value=100)

        validator = DataValidator()
        report = await validator.generate_validation_report(
            schema_mapping=schema_mapping,
            legacy_client=legacy_client,
            modern_client=modern_client,
        )

        assert report["overall_passed"] is True
        assert report["total_validations"] == 1
        assert report["passed_validations"] == 1
        assert report["failed_validations"] == 0
        assert len(report["results"]) == 1
        assert report["results"][0]["passed"] is True

    @pytest.mark.asyncio
    async def test_generate_validation_report_with_failures(self):
        """Verifica relatório quando há falhas."""
        schema_mapping = SchemaMapping(
            legacy_connection_id="postgres-legacy",
            nhm_target="feature-store",
            tables=[
                TableMapping(
                    source_schema="public",
                    source_table="orders",
                    target_table="nhm_orders",
                    fields=[
                        FieldMapping(
                            source_field="user_id",
                            target_field="user_id",
                            data_type="uuid",
                            is_foreign_key=True,
                            foreign_key_reference="nhm_users.id",
                        )
                    ],
                ),
            ],
        )

        legacy_client = AsyncMock()
        modern_client = AsyncMock()

        # Criar funções mock que retornam valores baseados na query
        async def legacy_mock_execute(query, params=None, fetch="all"):
            # Row count query - retorna 500
            return 500

        call_count = [0]

        async def modern_mock_execute(query, params=None, fetch="all"):
            call_count[0] += 1
            # Primeira chamada: row count (retorna 500)
            if call_count[0] == 1:
                return 500
            # Segunda chamada em diante: FK orfãos
            else:
                return [
                    {"user_id": "orphan-1"},
                    {"user_id": "orphan-2"},
                ]

        legacy_client.execute_query = legacy_mock_execute
        modern_client.execute_query = modern_mock_execute

        validator = DataValidator()
        report = await validator.generate_validation_report(
            schema_mapping=schema_mapping,
            legacy_client=legacy_client,
            modern_client=modern_client,
        )

        assert report["overall_passed"] is False
        assert report["total_validations"] == 2  # row_count + referential
        assert report["passed_validations"] == 1
        assert report["failed_validations"] == 1

    @pytest.mark.asyncio
    async def test_generate_validation_report_includes_summary(self):
        """Verifica que relatório inclui resumo por tipo."""
        schema_mapping = SchemaMapping(
            legacy_connection_id="postgres-legacy",
            nhm_target="feature-store",
            tables=[
                TableMapping(
                    source_schema="public",
                    source_table="users",
                    target_table="nhm_users",
                    fields=[
                        FieldMapping(
                            source_field="status",
                            target_field="status",
                            data_type="varchar",
                        )
                    ],
                ),
            ],
        )

        legacy_client = AsyncMock()
        modern_client = AsyncMock()

        legacy_call_count = [0]
        modern_call_count = [0]

        async def legacy_mock_execute(query, params=None, fetch="all"):
            legacy_call_count[0] += 1
            # Primeira chamada: row count
            if legacy_call_count[0] == 1:
                return 1000
            # Segunda chamada: value distribution
            else:
                return [{"value": "active", "count": 800}]

        async def modern_mock_execute(query, params=None, fetch="all"):
            modern_call_count[0] += 1
            # Primeira chamada: row count
            if modern_call_count[0] == 1:
                return 1000
            # Segunda chamada: value distribution
            else:
                return [{"value": "active", "count": 800}]

        legacy_client.execute_query = legacy_mock_execute
        modern_client.execute_query = modern_mock_execute

        validator = DataValidator()
        report = await validator.generate_validation_report(
            schema_mapping=schema_mapping,
            legacy_client=legacy_client,
            modern_client=modern_client,
        )

        assert "summary_by_type" in report
        assert "row_count" in report["summary_by_type"]
        assert "distribution" in report["summary_by_type"]


class TestGetDataValidator:
    """Testes para singleton get_data_validator."""

    def test_get_data_validator_singleton(self):
        """Verifica que get_data_validator retorna singleton."""
        validator1 = get_data_validator()
        validator2 = get_data_validator()

        assert validator1 is validator2

    def test_get_data_validator_reset(self):
        """Verifica reset do singleton para testes."""
        # Primeira chamada
        validator1 = get_data_validator()

        # Reset para teste
        from src.services import data_validator

        data_validator._data_validator = None

        # Nova instância
        validator2 = get_data_validator()

        # São objetos diferentes após reset
        assert validator1 is not validator2


class TestEdgeCases:
    """Testes para casos extremos e erro handling."""

    @pytest.mark.asyncio
    async def test_empty_schema_mapping(self):
        """Verifica comportamento com SchemaMapping vazio."""
        schema_mapping = SchemaMapping(
            legacy_connection_id="postgres-legacy",
            nhm_target="feature-store",
            tables=[],
        )

        legacy_client = AsyncMock()
        modern_client = AsyncMock()

        validator = DataValidator()
        report = await validator.generate_validation_report(
            schema_mapping=schema_mapping,
            legacy_client=legacy_client,
            modern_client=modern_client,
        )

        assert report["total_validations"] == 0
        assert report["overall_passed"] is True  # Vazio = sucesso
        assert len(report["results"]) == 0

    @pytest.mark.asyncio
    async def test_database_error_handling(self):
        """Verifica tratamento de erro de banco de dados."""
        schema_mapping = SchemaMapping(
            legacy_connection_id="postgres-legacy",
            nhm_target="feature-store",
            tables=[
                TableMapping(
                    source_schema="public",
                    source_table="users",
                    target_table="nhm_users",
                    fields=[],
                ),
            ],
        )

        legacy_client = AsyncMock()
        modern_client = AsyncMock()

        # Simular erro de conexão
        legacy_client.execute_query = AsyncMock(side_effect=Exception("Connection lost"))

        validator = DataValidator()

        with pytest.raises(DataValidationError, match="Erro ao validar contagem"):
            await validator.validate_row_counts(
                schema_mapping=schema_mapping,
                legacy_client=legacy_client,
                modern_client=modern_client,
            )
