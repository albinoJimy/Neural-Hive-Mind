"""
Data Validator Service para Data Migration System.

Implementa validações de integridade de dados usando análise SQL
para garantir qualidade da migração de dados legados → modernos.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

import structlog
from pydantic import BaseModel

from src.models.migration import SchemaMapping

logger = structlog.get_logger()


class ValidationType(str, Enum):
    """Tipos de validação suportados."""

    ROW_COUNT = "row_count"
    REFERENTIAL_INTEGRITY = "referential"
    DISTRIBUTION = "distribution"


class DataValidationError(Exception):
    """Exceção base para erros do Data Validator."""


class ValidationResult(BaseModel):
    """Resultado de uma validação individual."""

    table_name: str
    validation_type: ValidationType
    passed: bool
    legacy_count: Optional[int] = None
    modern_count: Optional[int] = None
    discrepancy: Optional[int] = None
    details: Dict[str, Any] = {}

    model_config = {"use_enum_values": True}


class DataValidator:
    """
    Serviço de validação de dados para migração.

    Valida contagem de linhas, integridade referencial e
    distribuição de valores entre bancos legado e moderno.
    """

    def __init__(
        self,
        row_count_tolerance: int = 0,
        distribution_tolerance: float = 0.05,  # 5%
        max_sample_size: int = 10000,
    ):
        """
        Inicializa Data Validator.

        Args:
            row_count_tolerance: Tolerância para discrepância de contagem (absoluto)
            distribution_tolerance: Tolerância para discrepância de distribuição (0-1)
            max_sample_size: Tamanho máximo da amostra para distribuição
        """
        self.row_count_tolerance = row_count_tolerance
        self.distribution_tolerance = distribution_tolerance
        self.max_sample_size = max_sample_size

    async def validate_row_counts(
        self,
        schema_mapping: SchemaMapping,
        legacy_client,
        modern_client,
    ) -> List[ValidationResult]:
        """
        Valida contagem de linhas entre legado e moderno.

        Args:
            schema_mapping: Mapeamento de schema
            legacy_client: Cliente PostgreSQL do legado
            modern_client: Cliente PostgreSQL do moderno

        Returns:
            Lista de ValidationResult

        Raises:
            DataValidationError: Se falhar validação
        """
        results = []

        for table_mapping in schema_mapping.tables:
            try:
                # Construir query legada
                source_filter = table_mapping.source_filter or ""
                if source_filter:
                    legacy_query = f"SELECT COUNT(*) FROM {table_mapping.source_schema}.{table_mapping.source_table} WHERE {source_filter}"
                else:
                    legacy_query = f"SELECT COUNT(*) FROM {table_mapping.source_schema}.{table_mapping.source_table}"

                # Query moderna
                modern_query = f"SELECT COUNT(*) FROM {table_mapping.target_schema}.{table_mapping.target_table}"

                # Executar queries
                legacy_result = await legacy_client.execute_query(legacy_query, fetch="val")
                modern_result = await modern_client.execute_query(modern_query, fetch="val")

                # Converter para int se necessário
                # Handle diferentes tipos de retorno (int direto, lista, dict)
                def to_int(value):
                    """Converte valor para int, lidando com diferentes tipos."""
                    if value is None:
                        return 0
                    if isinstance(value, int):
                        return value
                    if isinstance(value, (float, str)):
                        return int(value)
                    if isinstance(value, list) and len(value) > 0:
                        return to_int(value[0])
                    if isinstance(value, dict):
                        return to_int(value.get("count", value.get("count", 0)))
                    return 0

                legacy_count = to_int(legacy_result)
                modern_count = to_int(modern_result)

                # Calcular discrepância
                discrepancy = abs(legacy_count - modern_count)
                passed = discrepancy <= self.row_count_tolerance

                result = ValidationResult(
                    table_name=table_mapping.source_table,
                    validation_type=ValidationType.ROW_COUNT,
                    passed=passed,
                    legacy_count=legacy_count,
                    modern_count=modern_count,
                    discrepancy=discrepancy,
                    details={
                        "source_filter": source_filter,
                        "message": (
                            "Contagem corresponde"
                            if passed
                            else f"{discrepancy} registros {'faltando' if modern_count < legacy_count else 'excedentes'}"
                        ),
                    },
                )

                results.append(result)

                logger.info(
                    "row_count_validated",
                    table=table_mapping.source_table,
                    legacy_count=legacy_count,
                    modern_count=modern_count,
                    passed=passed,
                )

            except Exception as e:
                logger.error(
                    "row_count_validation_failed",
                    table=table_mapping.source_table,
                    error=str(e),
                )
                raise DataValidationError(
                    f"Erro ao validar contagem para {table_mapping.source_table}: {e}"
                ) from e

        return results

    async def validate_referential_integrity(
        self,
        schema_mapping: SchemaMapping,
        modern_client,
    ) -> List[ValidationResult]:
        """
        Valida integridade referencial no banco moderno.

        Para cada FK mapeada, verifica se existem registros órfãos
        (filhos sem pais válidos).

        Args:
            schema_mapping: Mapeamento de schema
            modern_client: Cliente PostgreSQL do moderno

        Returns:
            Lista de ValidationResult
        """
        results = []

        for table_mapping in schema_mapping.tables:
            # Encontrar campos que são FKs
            foreign_keys = [
                field
                for field in table_mapping.fields
                if field.is_foreign_key and field.foreign_key_reference
            ]

            for fk_field in foreign_keys:
                try:
                    # Parse referência FK (formato: schema.table.column ou table.column)
                    ref_parts = fk_field.foreign_key_reference.split(".")
                    if len(ref_parts) == 3:
                        ref_schema, ref_table, ref_column = ref_parts
                    elif len(ref_parts) == 2:
                        ref_table, ref_column = ref_parts
                        ref_schema = table_mapping.target_schema
                    else:
                        logger.warning(
                            "invalid_fk_reference",
                            field=fk_field.target_field,
                            reference=fk_field.foreign_key_reference,
                        )
                        continue

                    # Query para encontrar órfãos
                    orphan_query = f"""
                        SELECT child.{fk_field.target_field}
                        FROM {table_mapping.target_schema}.{table_mapping.target_table} AS child
                        LEFT JOIN {ref_schema}.{ref_table} AS parent
                            ON child.{fk_field.target_field} = parent.{ref_column}
                        WHERE child.{fk_field.target_field} IS NOT NULL
                            AND parent.{ref_column} IS NULL
                        LIMIT {self.max_sample_size}
                    """

                    orphans = await modern_client.execute_query(orphan_query)
                    orphan_count = len(orphans)

                    result = ValidationResult(
                        table_name=table_mapping.source_table,
                        validation_type=ValidationType.REFERENTIAL_INTEGRITY,
                        passed=(orphan_count == 0),
                        legacy_count=None,
                        modern_count=None,
                        discrepancy=orphan_count if orphan_count > 0 else None,
                        details={
                            "foreign_key_column": fk_field.target_field,
                            "referenced_table": f"{ref_schema}.{ref_table}",
                            "referenced_column": ref_column,
                            "orphaned_count": orphan_count,
                            "sample_limit": (
                                self.max_sample_size
                                if orphan_count >= self.max_sample_size
                                else None
                            ),
                        },
                    )

                    results.append(result)

                    logger.info(
                        "referential_integrity_validated",
                        table=table_mapping.source_table,
                        fk_column=fk_field.target_field,
                        orphan_count=orphan_count,
                        passed=(orphan_count == 0),
                    )

                except Exception as e:
                    logger.error(
                        "referential_validation_failed",
                        table=table_mapping.source_table,
                        fk_field=fk_field.target_field,
                        error=str(e),
                    )
                    raise DataValidationError(
                        f"Erro ao validar FK {fk_field.target_field}: {e}"
                    ) from e

        return results

    async def validate_value_distribution(
        self,
        schema_mapping: SchemaMapping,
        legacy_client,
        modern_client,
    ) -> List[ValidationResult]:
        """
        Valida distribuição de valores entre legado e moderno.

        Compara distribuição de colunas importantes (não PK, não FK)
        para detectar discrepâncias significativas.

        Args:
            schema_mapping: Mapeamento de schema
            legacy_client: Cliente PostgreSQL do legado
            modern_client: Cliente PostgreSQL do moderno

        Returns:
            Lista de ValidationResult
        """
        results = []

        for table_mapping in schema_mapping.tables:
            # Encontrar campos para validar (não PK, não FK, tipos simples)
            columns_to_validate = [
                field
                for field in table_mapping.fields
                if not field.is_primary_key
                and not field.is_foreign_key
                and field.data_type.lower()
                in [
                    "varchar",
                    "text",
                    "character varying",
                    "integer",
                    "bigint",
                    "smallint",
                    "boolean",
                ]
            ]

            if not columns_to_validate:
                continue

            for field in columns_to_validate:
                try:
                    # Query para distribuição legada
                    source_filter = table_mapping.source_filter or ""
                    where_clause = f" WHERE {source_filter}" if source_filter else ""

                    legacy_dist_query = f"""
                        SELECT {field.source_field} AS value, COUNT(*) AS count
                        FROM {table_mapping.source_schema}.{table_mapping.source_table}
                        {where_clause}
                        GROUP BY {field.source_field}
                        ORDER BY count DESC
                        LIMIT 100
                    """

                    # Query para distribuição moderna
                    modern_dist_query = f"""
                        SELECT {field.target_field} AS value, COUNT(*) AS count
                        FROM {table_mapping.target_schema}.{table_mapping.target_table}
                        GROUP BY {field.target_field}
                        ORDER BY count DESC
                        LIMIT 100
                    """

                    legacy_dist = await legacy_client.execute_query(legacy_dist_query)
                    modern_dist = await modern_client.execute_query(modern_dist_query)

                    # Converter para dict para comparação
                    legacy_counts = {row["value"]: row["count"] for row in legacy_dist}
                    modern_counts = {row["value"]: row["count"] for row in modern_dist}

                    # Calcular totais
                    legacy_total = sum(legacy_counts.values()) if legacy_counts else 1
                    modern_total = sum(modern_counts.values()) if modern_counts else 1

                    # Encontrar discrepâncias
                    discrepancies = []
                    max_discrepancy_pct = 0.0

                    all_values = set(legacy_counts.keys()) | set(modern_counts.keys())

                    for value in all_values:
                        legacy_count = legacy_counts.get(value, 0)
                        modern_count = modern_counts.get(value, 0)

                        if legacy_total > 0 and modern_total > 0:
                            legacy_pct = (legacy_count / legacy_total) * 100
                            modern_pct = (modern_count / modern_total) * 100
                            discrepancy_pct = abs(legacy_pct - modern_pct)

                            if discrepancy_pct > (self.distribution_tolerance * 100):
                                discrepancies.append(
                                    {
                                        "value": value,
                                        "legacy_pct": round(legacy_pct, 2),
                                        "modern_pct": round(modern_pct, 2),
                                        "discrepancy_pct": round(discrepancy_pct, 2),
                                    }
                                )

                            max_discrepancy_pct = max(max_discrepancy_pct, discrepancy_pct)

                    passed = max_discrepancy_pct <= (self.distribution_tolerance * 100)

                    result = ValidationResult(
                        table_name=table_mapping.source_table,
                        validation_type=ValidationType.DISTRIBUTION,
                        passed=passed,
                        legacy_count=legacy_total,
                        modern_count=modern_total,
                        discrepancy=len(discrepancies) if discrepancies else None,
                        details={
                            "column": field.target_field,
                            "max_discrepancy_pct": round(max_discrepancy_pct, 2),
                            "discrepancies": discrepancies[:20],  # Limitar para não sobrecarregar
                            "tolerance_pct": round(self.distribution_tolerance * 100, 2),
                        },
                    )

                    results.append(result)

                    logger.info(
                        "value_distribution_validated",
                        table=table_mapping.source_table,
                        column=field.target_field,
                        passed=passed,
                        max_discrepancy_pct=max_discrepancy_pct,
                    )

                except Exception as e:
                    logger.error(
                        "distribution_validation_failed",
                        table=table_mapping.source_table,
                        column=field.target_field,
                        error=str(e),
                    )
                    raise DataValidationError(
                        f"Erro ao validar distribuição de {field.target_field}: {e}"
                    ) from e

        return results

    async def generate_validation_report(
        self,
        schema_mapping: SchemaMapping,
        legacy_client,
        modern_client,
    ) -> Dict[str, Any]:
        """
        Gera relatório completo de validação.

        Executa todos os tipos de validação e consolida resultados.

        Args:
            schema_mapping: Mapeamento de schema
            legacy_client: Cliente PostgreSQL do legado
            modern_client: Cliente PostgreSQL do moderno

        Returns:
            Dicionário com relatório completo
        """
        logger.info(
            "starting_validation",
            table_count=len(schema_mapping.tables),
            nhm_target=schema_mapping.nhm_target,
        )

        start_time = datetime.now(timezone.utc)

        # Executar todas as validações
        row_count_results = await self.validate_row_counts(
            schema_mapping=schema_mapping,
            legacy_client=legacy_client,
            modern_client=modern_client,
        )

        referential_results = await self.validate_referential_integrity(
            schema_mapping=schema_mapping,
            modern_client=modern_client,
        )

        distribution_results = await self.validate_value_distribution(
            schema_mapping=schema_mapping,
            legacy_client=legacy_client,
            modern_client=modern_client,
        )

        # Consolidar resultados
        all_results = row_count_results + referential_results + distribution_results

        # Calcular estatísticas
        total_validations = len(all_results)
        passed_validations = sum(1 for r in all_results if r.passed)
        failed_validations = total_validations - passed_validations

        # Agrupar por tipo
        summary_by_type = {
            "row_count": {
                "total": len(row_count_results),
                "passed": sum(1 for r in row_count_results if r.passed),
                "failed": sum(1 for r in row_count_results if not r.passed),
            },
            "referential": {
                "total": len(referential_results),
                "passed": sum(1 for r in referential_results if r.passed),
                "failed": sum(1 for r in referential_results if not r.passed),
            },
            "distribution": {
                "total": len(distribution_results),
                "passed": sum(1 for r in distribution_results if r.passed),
                "failed": sum(1 for r in distribution_results if not r.passed),
            },
        }

        elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()

        report = {
            "overall_passed": failed_validations == 0,
            "total_validations": total_validations,
            "passed_validations": passed_validations,
            "failed_validations": failed_validations,
            "summary_by_type": summary_by_type,
            "results": [
                {
                    "table": r.table_name,
                    "type": r.validation_type,
                    "passed": r.passed,
                    "legacy_count": r.legacy_count,
                    "modern_count": r.modern_count,
                    "discrepancy": r.discrepancy,
                    "details": r.details,
                }
                for r in all_results
            ],
            "metadata": {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "elapsed_seconds": round(elapsed, 2),
                "schema_mapping_id": id(schema_mapping),
                "nhm_target": schema_mapping.nhm_target,
            },
        }

        logger.info(
            "validation_completed",
            overall_passed=report["overall_passed"],
            total_validations=total_validations,
            passed_validations=passed_validations,
            failed_validations=failed_validations,
            elapsed_seconds=elapsed,
        )

        return report


# Singleton instance
_data_validator: Optional[DataValidator] = None


def get_data_validator() -> DataValidator:
    """
    Retorna singleton do Data Validator.

    Returns:
        Instância de DataValidator
    """
    global _data_validator
    if _data_validator is None:
        _data_validator = DataValidator()
    return _data_validator
