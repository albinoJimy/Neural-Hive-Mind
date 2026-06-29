"""
Atividades Temporal para Data Migration Workflow.

Implementa as atividades chamadas pelo DataMigrationWorkflow:
- Analyze Legacy Schema
- Generate Schema Mapping
- Approve Mapping
- Create Snapshot
- Run Batch Migration
- Start CDC
- Validate Data
- Cleanup Snapshot
- Execute Rollback
"""

import uuid
from datetime import datetime, timezone

UTC = timezone.utc
from typing import Any, Optional

import httpx
import structlog
from temporalio import activity

logger = structlog.get_logger(__name__)

# =============================================================================
# Injeção de dependências (HTTP client + base_url do serviço data-migration)
# =============================================================================
# Espelha o padrão de fluxo_g_integration.set_fluxo_g_dependencies: o worker
# Temporal injeta um httpx.AsyncClient partilhado. Sem client configurado, as
# activities que dependem dele são FAIL-CLOSED (nunca assumem sucesso).

_http_client: Optional[httpx.AsyncClient] = None
_data_migration_base_url: str = "http://data-migration:8019"


def set_data_migration_dependencies(
    http_client: Optional[httpx.AsyncClient] = None,
    base_url: Optional[str] = None,
) -> None:
    """Injeta dependências para as activities de data migration.

    Args:
        http_client: Cliente httpx partilhado (injetado pelo worker).
        base_url: URL base do serviço data-migration (default 8019).
    """
    global _http_client, _data_migration_base_url
    _http_client = http_client
    if base_url:
        _data_migration_base_url = base_url


# =============================================================================
# Activity: Analyze Legacy Schema
# =============================================================================


@activity.defn
async def analyze_legacy_schema(
    legacy_connection_id: str,
    schema: str = "public",
    tables: Optional[list[str]] = None,
) -> dict[str, Any]:
    """
    Analisa schema do banco legado.

    Coleta metadados de tabelas e colunas do sistema legado para
    gerar o mapeamento de migração.

    Args:
        legacy_connection_id: ID da conexão com banco legado
        schema: Schema a analisar (padrão: public)
        tables: Lista de tabelas (None = todas)

    Returns:
        Dict com:
            - success: bool
            - schema_analysis: dict (se sucesso)
            - error: str (se falhou)
    """
    try:
        logger.info(
            "analyze_legacy_schema_started",
            legacy_connection_id=legacy_connection_id,
            schema=schema,
            tables=tables,
        )

        # Na implementação real, aqui seria:
        # 1. Conectar ao banco legado via PostgreSQL/MongoDB client
        # 2. Consultar information_schema para metadados
        # 3. Contar linhas para estimativa
        # 4. Detectar tipos de dados, constraints, etc

        # Simular análise bem-sucedida
        schema_analysis = {
            "legacy_connection_id": legacy_connection_id,
            "schema": schema,
            "tables": [
                {
                    "schema": schema,
                    "table": "users",
                    "columns": [
                        {
                            "name": "id",
                            "type": "INTEGER",
                            "nullable": False,
                            "is_primary_key": True,
                            "is_foreign_key": False,
                        },
                        {
                            "name": "username",
                            "type": "VARCHAR(50)",
                            "nullable": False,
                            "is_primary_key": False,
                            "is_foreign_key": False,
                        },
                        {
                            "name": "email",
                            "type": "VARCHAR(255)",
                            "nullable": True,
                            "is_primary_key": False,
                            "is_foreign_key": False,
                        },
                        {
                            "name": "created_at",
                            "type": "TIMESTAMP",
                            "nullable": True,
                            "is_primary_key": False,
                            "is_foreign_key": False,
                        },
                    ],
                    "row_estimate": 10000,
                    "indexes": ["PRIMARY KEY (id)", "UNIQUE (username)"],
                },
                {
                    "schema": schema,
                    "table": "orders",
                    "columns": [
                        {
                            "name": "id",
                            "type": "INTEGER",
                            "nullable": False,
                            "is_primary_key": True,
                            "is_foreign_key": False,
                        },
                        {
                            "name": "user_id",
                            "type": "INTEGER",
                            "nullable": False,
                            "is_primary_key": False,
                            "is_foreign_key": True,
                            "foreign_key_reference": "users(id)",
                        },
                        {
                            "name": "total",
                            "type": "DECIMAL(10,2)",
                            "nullable": False,
                            "is_primary_key": False,
                            "is_foreign_key": False,
                        },
                        {
                            "name": "status",
                            "type": "VARCHAR(20)",
                            "nullable": False,
                            "is_primary_key": False,
                            "is_foreign_key": False,
                        },
                    ],
                    "row_estimate": 50000,
                    "indexes": ["PRIMARY KEY (id)", "INDEX (user_id)"],
                },
            ],
            "analyzed_at": datetime.now(timezone.utc).isoformat(),
        }

        logger.info(
            "analyze_legacy_schema_completed",
            tables_count=len(schema_analysis["tables"]),
        )

        return {
            "success": True,
            "schema_analysis": schema_analysis,
        }

    except Exception as e:
        logger.exception("analyze_legacy_schema_failed")
        return {
            "success": False,
            "error": str(e),
        }


# =============================================================================
# Activity: Generate Schema Mapping
# =============================================================================


@activity.defn
async def generate_schema_mapping(
    schema_analysis: dict[str, Any],
    target_service: str,
) -> dict[str, Any]:
    """
    Gera mapeamento de schema legado → novo.

    Args:
        schema_analysis: Análise do schema legado
        target_service: Serviço NHM de destino

    Returns:
        Dict com:
            - success: bool
            - schema_mapping: dict (se sucesso)
            - error: str (se falhou)
    """
    try:
        logger.info(
            "generate_schema_mapping_started",
            target_service=target_service,
        )

        # Gerar mapeamento baseado na análise
        tables_mapping = []

        for table in schema_analysis.get("tables", []):
            fields_mapping = []

            for col in table.get("columns", []):
                field_mapping = {
                    "source_field": col["name"],
                    "target_field": col["name"],  # Por padrão, mantém nome
                    "data_type": col["type"],
                    "nullable": col["nullable"],
                    "is_primary_key": col.get("is_primary_key", False),
                    "is_foreign_key": col.get("is_foreign_key", False),
                    "foreign_key_reference": col.get("foreign_key_reference"),
                }

                # Adicionar transformações específicas
                if col["type"] == "TIMESTAMP":
                    field_mapping["transform"] = "CAST_TIMESTAMP_UTC"

                fields_mapping.append(field_mapping)

            table_mapping = {
                "source_schema": table.get("schema", "public"),
                "source_table": table["table"],
                "target_table": table["table"],  # Por padrão, mantém nome
                "target_schema": "public",
                "fields": fields_mapping,
                "estimated_rows": table.get("row_estimate", 0),
            }

            tables_mapping.append(table_mapping)

        schema_mapping = {
            "legacy_connection_id": schema_analysis.get("legacy_connection_id"),
            "nhm_target": target_service,
            "tables": tables_mapping,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "version": 1,
        }

        logger.info(
            "generate_schema_mapping_completed",
            tables_count=len(tables_mapping),
        )

        return {
            "success": True,
            "schema_mapping": schema_mapping,
        }

    except Exception as e:
        logger.exception("generate_schema_mapping_failed")
        return {
            "success": False,
            "error": str(e),
        }


# =============================================================================
# Activity: Approve Mapping
# =============================================================================


@activity.defn
async def approve_mapping(
    schema_mapping: dict[str, Any],
    auto_approve: bool = True,
    approved_by: str = "system",
) -> dict[str, Any]:
    """
    Aprova mapeamento de schema (gate humano).

    Args:
        schema_mapping: Mapeamento de schema
        auto_approve: Se True, aprova automaticamente
        approved_by: Usuário ou serviço aprovando

    Returns:
        Dict com:
            - approved: bool
            - approved_by: str
            - approved_at: str (ISO datetime)
            - status: str (pending_approval se não auto_approve)
    """
    try:
        logger.info(
            "approve_mapping_started",
            auto_approve=auto_approve,
            approved_by=approved_by,
        )

        if not auto_approve:
            # Não aprovar automaticamente - aguardar aprovação humana
            return {
                "approved": False,
                "status": "pending_approval",
                "message": "Aguardando aprovação humana",
            }

        # Aprovação automática
        logger.info("mapping_approved_auto", approved_by=approved_by)

        return {
            "approved": True,
            "approved_by": approved_by,
            "approved_at": datetime.now(timezone.utc).isoformat(),
            "status": "approved",
        }

    except Exception as e:
        logger.exception("approve_mapping_failed")
        return {
            "approved": False,
            "error": str(e),
        }


# =============================================================================
# Activity: Create Snapshot
# =============================================================================


@activity.defn
async def create_snapshot(
    job_id: str,
    table_mappings: list[dict[str, Any]],
    strategy: str = "s3",
) -> dict[str, Any]:
    """
    Cria snapshot para rollback.

    Args:
        job_id: ID do job de migração
        table_mappings: Lista de mapeamentos de tabelas
        strategy: Estratégia de snapshot (s3, shadow, etc)

    Returns:
        Dict com:
            - success: bool
            - snapshot_id: str
            - strategy: str
            - error: str (se falhou)
    """
    try:
        logger.info(
            "create_snapshot_started",
            job_id=job_id,
            strategy=strategy,
            tables_count=len(table_mappings),
        )

        # Gerar ID do snapshot
        snapshot_id = f"snap_{job_id[:8]}_{uuid.uuid4().hex[:8]}"

        # Na implementação real:
        # - strategy="s3": Exportar dados para S3/MinIO
        # - strategy="shadow": Criar tabelas shadow

        logger.info("snapshot_created", snapshot_id=snapshot_id)

        return {
            "success": True,
            "snapshot_id": snapshot_id,
            "strategy": strategy,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "tables_snapshotted": len(table_mappings),
        }

    except Exception as e:
        logger.exception("create_snapshot_failed")
        return {
            "success": False,
            "error": str(e),
        }


# =============================================================================
# Activity: Run Batch Migration
# =============================================================================


@activity.defn
async def run_batch_migration(
    job_id: str,
    schema_mapping: dict[str, Any],
    batch_size: int = 1000,
    max_parallel: int = 5,
) -> dict[str, Any]:
    """
    Executa migração batch de dados históricos.

    Args:
        job_id: ID do job de migração
        schema_mapping: Mapeamento de schema
        batch_size: Tamanho do lote
        max_parallel: Máximo de migrações em paralelo

    Returns:
        Dict com:
            - success: bool
            - rows_migrated: int
            - total_rows: int
            - progress_percentage: float
            - tables_processed: int
            - error: str (se falhou)
    """
    try:
        logger.info(
            "run_batch_migration_started",
            job_id=job_id,
            batch_size=batch_size,
            max_parallel=max_parallel,
        )

        tables = schema_mapping.get("tables", [])
        total_rows = sum(t.get("estimated_rows", 0) for t in tables)

        # Na implementação real, executar migração batch
        # Por ora, simular migração bem-sucedida
        rows_migrated = total_rows  # Simular 100%
        tables_processed = len(tables)
        progress_percentage = 100.0 if total_rows > 0 else 0.0

        logger.info(
            "batch_migration_completed",
            rows_migrated=rows_migrated,
            tables_processed=tables_processed,
        )

        return {
            "success": True,
            "rows_migrated": rows_migrated,
            "total_rows": total_rows,
            "progress_percentage": progress_percentage,
            "tables_processed": tables_processed,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }

    except Exception as e:
        logger.exception("run_batch_migration_failed")
        return {
            "success": False,
            "error": str(e),
        }


# =============================================================================
# Activity: Start CDC
# =============================================================================


@activity.defn
async def start_cdc(
    job_id: str,
    schema_mapping: dict[str, Any],
    database_config: dict[str, Any],
) -> dict[str, Any]:
    """
    Inicia pipeline CDC para captura de mudanças em tempo real.

    Args:
        job_id: ID do job de migração
        schema_mapping: Mapeamento de schema
        database_config: Configuração do banco legado

    Returns:
        Dict com:
            - success: bool
            - connector_id: str
            - status: str
            - error: str (se falhou)
    """
    try:
        logger.info(
            "start_cdc_started",
            job_id=job_id,
            database_config_keys=list(database_config.keys()),
        )

        # Gerar ID do connector
        connector_id = f"cdc_{job_id[:8]}_{uuid.uuid4().hex[:8]}"

        # Na implementação real:
        # - Criar connector Debezium
        # - Configurar tópicos Kafka
        # - Iniciar consumo de eventos CDC

        logger.info("cdc_started", connector_id=connector_id)

        return {
            "success": True,
            "connector_id": connector_id,
            "status": "running",
            "started_at": datetime.now(timezone.utc).isoformat(),
        }

    except Exception as e:
        logger.exception("start_cdc_failed")
        return {
            "success": False,
            "error": str(e),
        }


# =============================================================================
# Activity: Validate Data
# =============================================================================


@activity.defn
async def validate_data(
    job_id: str,
    schema_mapping: dict[str, Any],
) -> dict[str, Any]:
    """
    Valida dados migrados via o serviço data-migration (gate FAIL-CLOSED).

    Chama `POST {base_url}/api/v1/migrations/{job_id}/validate`, que executa a
    validação REAL (contagem de linhas origem vs destino + integridade) no
    serviço data-migration:8019, e mapeia a resposta para o contrato consumido
    pelo gate interno do DataMigrationWorkflow.

    FAIL-CLOSED — o sucesso só é afirmado quando o serviço devolve
    `overall_passed=True` explicitamente. Qualquer ambiguidade (http client não
    configurado, erro/timeout de rede, status não-2xx, JSON sem o campo de
    validação) → `success=False` com `overall_passed=False`. Nunca se assume
    sucesso por defeito.

    Args:
        job_id: ID do job de migração
        schema_mapping: Mapeamento de schema (usado só para fallback de nomes)

    Returns:
        Dict com:
            - success: bool
            - validation_report: dict (overall_passed + table_results reais)
            - error: str (se falhou)
    """
    logger.info("validate_data_started", job_id=job_id)

    # Fail-closed: sem HTTP client injetado não há como validar de verdade.
    if _http_client is None:
        logger.error("validate_data_no_http_client", job_id=job_id)
        return _validation_failed(
            "HTTP client não configurado para validação (fail-closed)"
        )

    url = f"{_data_migration_base_url}/api/v1/migrations/{job_id}/validate"

    try:
        response = await _http_client.post(url, timeout=60.0)
    except Exception as e:
        # Erro/timeout de rede → fail-closed.
        logger.error("validate_data_http_error", job_id=job_id, error=str(e))
        return _validation_failed(f"Falha ao chamar /validate: {e}")

    if not 200 <= response.status_code < 300:
        logger.error(
            "validate_data_non_2xx",
            job_id=job_id,
            status_code=response.status_code,
        )
        return _validation_failed(f"/validate devolveu status {response.status_code}")

    try:
        data = response.json()
    except Exception as e:
        logger.error("validate_data_invalid_json", job_id=job_id, error=str(e))
        return _validation_failed(f"/validate devolveu JSON inválido: {e}")

    # O campo de validação é obrigatório; ausência → fail-closed.
    if not isinstance(data, dict) or "overall_passed" not in data:
        logger.error("validate_data_missing_field", job_id=job_id)
        return _validation_failed(
            "/validate não devolveu o campo overall_passed (fail-closed)"
        )

    overall_passed = bool(data.get("overall_passed"))

    # Mapear os resultados REAIS por tabela (counts vindos do serviço, não
    # estimados). O serviço devolve `results` no formato ValidationResultResponse.
    table_results = []
    for r in data.get("results", []):
        table_results.append(
            {
                "table": r.get("table"),
                "validation_type": r.get("type"),
                "row_count_match": bool(r.get("passed")),
                "legacy_rows": r.get("legacy_count"),
                "target_rows": r.get("modern_count"),
                "discrepancy": r.get("discrepancy"),
            }
        )

    validation_report = {
        "overall_passed": overall_passed,
        "tables_validated": data.get("total_validations", len(table_results)),
        "passed_validations": data.get("passed_validations"),
        "failed_validations": data.get("failed_validations"),
        "table_results": table_results,
        "validated_at": datetime.now(timezone.utc).isoformat(),
    }

    logger.info(
        "data_validation_completed",
        job_id=job_id,
        overall_passed=overall_passed,
    )

    if not overall_passed:
        # Validação REAL reprovou (divergência de contagem / integridade) →
        # success=False para o gate disparar rollback.
        validation_report["reason"] = "Validação de dados reprovada (counts divergem)"
        return {
            "success": False,
            "validation_report": validation_report,
            "error": validation_report["reason"],
        }

    return {
        "success": True,
        "validation_report": validation_report,
    }


def _validation_failed(reason: str) -> dict[str, Any]:
    """Constrói o resultado fail-closed de validação (success=False).

    O gate interno do DataMigrationWorkflow exige `success=False` E
    `validation_report.overall_passed=False` para acionar rollback; garantimos
    ambos aqui.
    """
    return {
        "success": False,
        "validation_report": {
            "overall_passed": False,
            "reason": reason,
        },
        "error": reason,
    }


# =============================================================================
# Activity: Cleanup Snapshot
# =============================================================================


@activity.defn
async def cleanup_snapshot(snapshot_id: str) -> dict[str, Any]:
    """
    Limpa snapshot após migração bem-sucedida.

    Args:
        snapshot_id: ID do snapshot a limpar

    Returns:
        Dict com:
            - success: bool
            - snapshot_id: str
            - error: str (se falhou)
    """
    try:
        logger.info("cleanup_snapshot_started", snapshot_id=snapshot_id)

        # Na implementação real, remover snapshot do S3/MinIO
        # ou dropar tabelas shadow

        logger.info("snapshot_cleaned", snapshot_id=snapshot_id)

        return {
            "success": True,
            "snapshot_id": snapshot_id,
            "cleaned_at": datetime.now(timezone.utc).isoformat(),
        }

    except Exception as e:
        logger.exception("cleanup_snapshot_failed")
        return {
            "success": False,
            "error": str(e),
        }


# =============================================================================
# Activity: Execute Rollback
# =============================================================================


@activity.defn
async def execute_rollback(
    job_id: str,
    snapshot_id: Optional[str],
    phase: str,
    reason: Optional[str] = None,
) -> dict[str, Any]:
    """
    Executa rollback da migração.

    Args:
        job_id: ID do job de migração
        snapshot_id: ID do snapshot (se existir)
        phase: Fase onde ocorreu o erro
        reason: Motivo do rollback

    Returns:
        Dict com:
            - success: bool
            - snapshot_id: str
            - phase: str
            - reason: str
            - tables_restored: int (se sucesso)
            - error: str (se falhou)
    """
    try:
        logger.error(
            "execute_rollback_started",
            job_id=job_id,
            snapshot_id=snapshot_id,
            phase=phase,
            reason=reason,
        )

        if not snapshot_id:
            logger.warning("rollback_without_snapshot", job_id=job_id)
            return {
                "success": False,
                "error": "Nenhum snapshot disponível para rollback",
            }

        # Na implementação real:
        # - Restaurar dados do snapshot S3/MinIO
        # - Parar connector CDC
        # - Limpar dados parciais

        tables_restored = 0  # Simulado

        logger.info(
            "rollback_completed",
            snapshot_id=snapshot_id,
            tables_restored=tables_restored,
        )

        return {
            "success": True,
            "snapshot_id": snapshot_id,
            "phase": phase,
            "reason": reason,
            "tables_restored": tables_restored,
            "rolled_back_at": datetime.now(timezone.utc).isoformat(),
        }

    except Exception as e:
        logger.exception("execute_rollback_failed")
        return {
            "success": False,
            "error": str(e),
        }
