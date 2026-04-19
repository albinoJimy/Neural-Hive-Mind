"""
API Router para Data Migration System.

Expõe endpoints REST para gerenciar jobs de migração de dados:
- POST /api/v1/migrations - Criar novo job
- GET /api/v1/migrations/{job_id} - Obter status
- GET /api/v1/migrations - Listar jobs (com paginação)
- POST /api/v1/migrations/{job_id}/start - Iniciar migração
- POST /api/v1/migrations/{job_id}/pause - Pausar migração
- POST /api/v1/migrations/{job_id}/resume - Retomar migração
- POST /api/v1/migrations/{job_id}/rollback - Executar rollback
- POST /api/v1/migrations/{job_id}/approve - Aprovar próxima fase
- POST /api/v1/migrations/{job_id}/validate - Validar dados migrados
- GET /api/v1/migrations/{job_id}/schema - Obter schema mapping
"""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator

from src.db.mongodb import get_mongodb_client
from src.db.postgresql import PostgreSQLClient
from src.models.migration import (
    MigrationJob,
    MigrationStatus,
    SchemaMapping,
)
from src.services.data_validator import get_data_validator
from src.services.migration_orchestrator import (
    MigrationOrchestratorError,
    PhaseTransitionError,
    clear_migration_orchestrator,
    get_migration_orchestrator,
)

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["migrations"])


# ========== Request/Response Models ==========


class MigrationCreateRequest(BaseModel):
    """Request para criar nova migração."""

    legacy_db_url: str = Field(..., description="URL de conexão com banco legado (PostgreSQL)")
    modern_db_url: str = Field(..., description="URL de conexão com banco moderno (PostgreSQL)")
    tables: List[str] = Field(..., description="Lista de tabelas a migrar", min_length=1)
    batch_size: int = Field(default=1000, ge=1, le=10000, description="Tamanho do lote")
    auto_approve: bool = Field(default=False, description="Aprovar fases automaticamente")

    @field_validator("legacy_db_url", "modern_db_url")
    @classmethod
    def validate_db_url(cls, v: str) -> str:
        """Valida formato da URL do banco."""
        if not v.startswith(("postgresql://", "postgres://")):
            raise ValueError("URL deve começar com postgresql:// ou postgres://")
        return v


class MigrationCreateResponse(BaseModel):
    """Response para criação de migração."""

    job_id: str
    status: str
    message: str
    created_at: datetime


class MigrationStatusResponse(BaseModel):
    """Response com status da migração."""

    job_id: str
    status: MigrationStatus
    progress: float = Field(..., ge=0.0, le=100.0)
    current_phase: str
    tables_completed: int
    total_tables: int
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    rows_migrated: int = 0
    total_rows: Optional[int] = None
    rows_failed: int = 0
    error_message: Optional[str] = None
    eta_seconds: Optional[int] = None


class MigrationListResponse(BaseModel):
    """Response para listagem de migrações."""

    jobs: List[Dict[str, Any]]
    total: int
    limit: int
    offset: int


class MigrationStartRequest(BaseModel):
    """Request para iniciar migração."""

    auto_approve: bool = Field(default=False, description="Aprovar fases automaticamente")
    database_config: Optional[Dict[str, Any]] = Field(
        None, description="Configurações adicionais do banco para CDC"
    )


class MigrationActionResponse(BaseModel):
    """Response genérico para ações de migração."""

    job_id: str
    action: str
    success: bool
    message: str


class MigrationApproveRequest(BaseModel):
    """Request para aprovar fase."""

    approved_by: str = Field(..., description="Usuário ou serviço aprovando")


class ValidationResultResponse(BaseModel):
    """Response para validação."""

    job_id: str
    overall_passed: bool
    total_validations: int
    passed_validations: int
    failed_validations: int
    results: List[Dict[str, Any]]


# ========== Endpoints ==========


@router.post(
    "/migrations",
    response_model=MigrationCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_migration(
    request: MigrationCreateRequest,
    background_tasks: BackgroundTasks,
    mongodb_client=Depends(get_mongodb_client),
):
    """
    Cria um novo job de migração.

    Args:
        request: Dados para criação da migração
        background_tasks: FastAPI BackgroundTasks
        mongodb_client: Cliente MongoDB injetado

    Returns:
        MigrationCreateResponse com job_id criado
    """
    from src.services.schema_mapper import get_schema_mapper

    job_id = str(uuid.uuid4())

    logger.info(
        "creating_migration_job",
        job_id=job_id,
        tables=request.tables,
        batch_size=request.batch_size,
    )

    try:
        # Conectar aos bancos para analisar schema
        legacy_client = PostgreSQLClient(dsn=request.legacy_db_url)
        await legacy_client.connect()

        modern_client = PostgreSQLClient(dsn=request.modern_db_url)
        await modern_client.connect()

        try:
            # Analisar schema legado
            schema_mapper = get_schema_mapper()
            analyzed_schema = await schema_mapper.analyze_legacy_schema(
                postgres_client=legacy_client,
                schema="public",
                tables=request.tables,
            )

            # Gerar mapeamento de schema
            schema_mapping = await schema_mapper.generate_schema_mapping(
                legacy_schema=analyzed_schema,
                legacy_connection_id=job_id,  # Usar job_id como connection_id
                nhm_target="modern",
            )

            # Salvar schema mapping no MongoDB
            mapping_dict = schema_mapping.model_dump()
            mapping_dict["_id"] = f"mapping-{job_id}"
            mapping_dict["legacy_connection_id"] = job_id
            await mongodb_client.insert_schema_mapping(mapping_dict)

            # Criar job de migração
            migration_job = MigrationJob(
                job_id=job_id,
                schema_mapping_id=f"mapping-{job_id}",
                batch_size=request.batch_size,
                total_rows=sum(t.get("row_count", 0) for t in analyzed_schema.get("tables", [])),
                status=MigrationStatus.PENDING,
            )

            job_dict = migration_job.model_dump()
            job_dict["schema_mapping_id"] = f"mapping-{job_id}"
            await mongodb_client.insert_migration_job(job_dict)

            logger.info(
                "migration_job_created",
                job_id=job_id,
                table_count=len(request.tables),
            )

            return MigrationCreateResponse(
                job_id=job_id,
                status=migration_job.status,
                message="Migration job created successfully",
                created_at=migration_job.created_at,
            )

        finally:
            await legacy_client.disconnect()
            await modern_client.disconnect()

    except Exception as e:
        logger.error("migration_creation_failed", job_id=job_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create migration: {e}",
        )


@router.get("/migrations/{job_id}", response_model=MigrationStatusResponse)
async def get_migration_status(
    job_id: str,
    mongodb_client=Depends(get_mongodb_client),
):
    """
    Obtém status detalhado de uma migração.

    Args:
        job_id: ID do job de migração
        mongodb_client: Cliente MongoDB injetado

    Returns:
        MigrationStatusResponse com status atual
    """
    job_dict = await mongodb_client.find_migration_job_by_id(job_id)

    if not job_dict:
        logger.warning("migration_job_not_found", job_id=job_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Migration job {job_id} not found",
        )

    # Buscar schema mapping para contar tabelas
    schema_mapping_id = job_dict.get("schema_mapping_id")
    total_tables = 0
    if schema_mapping_id:
        mapping = await mongodb_client.find_schema_mapping_by_id(schema_mapping_id)
        if mapping:
            total_tables = len(mapping.get("tables", []))

    # Calcular tabelas completas baseado no progresso
    tables_completed = 0
    if job_dict.get("status") in ["completed", "cdc_running", "validating"]:
        tables_completed = total_tables
    elif job_dict.get("status") == "batch_migrating":
        # Estimar baseado no progresso
        progress = job_dict.get("progress_percentage", 0)
        tables_completed = int((progress / 100) * total_tables) if total_tables > 0 else 0

    return MigrationStatusResponse(
        job_id=job_id,
        status=MigrationStatus(job_dict.get("status", "pending")),
        progress=job_dict.get("progress_percentage", 0.0),
        current_phase=_get_current_phase(job_dict.get("status", "pending")),
        tables_completed=tables_completed,
        total_tables=total_tables,
        started_at=_parse_datetime(job_dict.get("started_at")),
        completed_at=_parse_datetime(job_dict.get("completed_at")),
        rows_migrated=job_dict.get("rows_migrated", 0),
        total_rows=job_dict.get("total_rows"),
        rows_failed=job_dict.get("rows_failed", 0),
        error_message=job_dict.get("error_message"),
    )


@router.get("/migrations", response_model=MigrationListResponse)
async def list_migrations(
    status_filter: Optional[MigrationStatus] = Query(None, description="Filtrar por status"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    mongodb_client=Depends(get_mongodb_client),
):
    """
    Lista jobs de migração com paginação.

    Args:
        status_filter: Status para filtrar
        limit: Limite de resultados
        offset: Offset para paginação
        mongodb_client: Cliente MongoDB injetado

    Returns:
        MigrationListResponse com lista de jobs
    """
    if status_filter:
        jobs = await mongodb_client.list_migration_jobs_by_status(
            status=status_filter.value, limit=limit
        )
        total = await mongodb_client.count_migration_jobs_by_status(status=status_filter.value)
    else:
        # Buscar todos (usando status=None para indicar todos)
        # Implementação simples: buscar de cada status e combinar
        all_jobs = []
        for s in MigrationStatus:
            status_jobs = await mongodb_client.list_migration_jobs_by_status(
                status=s.value, limit=limit + offset
            )
            all_jobs.extend(status_jobs)

        # Ordenar por created_at descendente
        all_jobs.sort(key=lambda x: x.get("created_at", ""), reverse=True)

        # Aplicar paginação
        jobs = all_jobs[offset : offset + limit]
        total = len(all_jobs)

    return MigrationListResponse(
        jobs=jobs,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/migrations/{job_id}/start", response_model=MigrationActionResponse)
async def start_migration(
    job_id: str,
    request: MigrationStartRequest,
    background_tasks: BackgroundTasks,
    mongodb_client=Depends(get_mongodb_client),
):
    """
    Inicia ou retoma uma migração.

    Args:
        job_id: ID do job de migração
        request: Configurações para início
        background_tasks: FastAPI BackgroundTasks
        mongodb_client: Cliente MongoDB injetado

    Returns:
        MigrationActionResponse confirmando início
    """
    job_dict = await mongodb_client.find_migration_job_by_id(job_id)

    if not job_dict:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Migration job {job_id} not found",
        )

    # Buscar schema mapping
    schema_mapping_id = job_dict.get("schema_mapping_id")
    mapping_dict = await mongodb_client.find_schema_mapping_by_id(schema_mapping_id)

    if not mapping_dict:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Schema mapping {schema_mapping_id} not found",
        )

    # Executar migração em background
    background_tasks.add_task(
        _execute_migration_task,
        job_id=job_id,
        job_dict=job_dict,
        mapping_dict=mapping_dict,
        auto_approve=request.auto_approve,
        database_config=request.database_config,
    )

    logger.info("migration_started_in_background", job_id=job_id)

    return MigrationActionResponse(
        job_id=job_id,
        action="start",
        success=True,
        message="Migration started in background",
    )


@router.post("/migrations/{job_id}/pause", response_model=MigrationActionResponse)
async def pause_migration(
    job_id: str,
    mongodb_client=Depends(get_mongodb_client),
):
    """
    Pausa uma migração em andamento.

    Args:
        job_id: ID do job de migração
        mongodb_client: Cliente MongoDB injetado

    Returns:
        MigrationActionResponse confirmando pausa
    """
    job_dict = await mongodb_client.find_migration_job_by_id(job_id)

    if not job_dict:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Migration job {job_id} not found",
        )

    job_status = job_dict.get("status")
    if job_status not in ["batch_migrating", "cdc_running", "validating"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot pause migration from status {job_status}",
        )

    try:
        orchestrator = get_migration_orchestrator(job_id)

        # Converter dict para MigrationJob
        migration_job = MigrationJob(**job_dict)

        await orchestrator.pause_migration(migration_job=migration_job)

        # Atualizar no MongoDB
        await mongodb_client.update_migration_job_status(
            job_id=job_id,
            status=job_status,  # Mantém status, apenas marca pausa interna
        )

        logger.info("migration_paused", job_id=job_id)

        return MigrationActionResponse(
            job_id=job_id,
            action="pause",
            success=True,
            message="Migration paused successfully",
        )

    except PhaseTransitionError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error("migration_pause_failed", job_id=job_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to pause migration: {e}",
        )


@router.post("/migrations/{job_id}/resume", response_model=MigrationActionResponse)
async def resume_migration(
    job_id: str,
    mongodb_client=Depends(get_mongodb_client),
):
    """
    Retoma uma migração pausada.

    Args:
        job_id: ID do job de migração
        mongodb_client: Cliente MongoDB injetado

    Returns:
        MigrationActionResponse confirmando retomada
    """
    job_dict = await mongodb_client.find_migration_job_by_id(job_id)

    if not job_dict:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Migration job {job_id} not found",
        )

    try:
        orchestrator = get_migration_orchestrator(job_id)
        migration_job = MigrationJob(**job_dict)

        await orchestrator.resume_migration(migration_job=migration_job)

        logger.info("migration_resumed", job_id=job_id)

        return MigrationActionResponse(
            job_id=job_id,
            action="resume",
            success=True,
            message="Migration resumed successfully",
        )

    except PhaseTransitionError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error("migration_resume_failed", job_id=job_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to resume migration: {e}",
        )


@router.post("/migrations/{job_id}/rollback", response_model=MigrationActionResponse)
async def rollback_migration(
    job_id: str,
    mongodb_client=Depends(get_mongodb_client),
):
    """
    Executa rollback de uma migração.

    Args:
        job_id: ID do job de migração
        mongodb_client: Cliente MongoDB injetado

    Returns:
        MigrationActionResponse com estatísticas do rollback
    """
    job_dict = await mongodb_client.find_migration_job_by_id(job_id)

    if not job_dict:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Migration job {job_id} not found",
        )

    try:
        orchestrator = get_migration_orchestrator(job_id)
        migration_job = MigrationJob(**job_dict)

        rollback_stats = await orchestrator.rollback_migration(migration_job=migration_job)

        # Atualizar status no MongoDB
        await mongodb_client.update_migration_job_status(
            job_id=job_id,
            status="rolled_back",
        )

        logger.info("migration_rolled_back", job_id=job_id, stats=rollback_stats)

        return MigrationActionResponse(
            job_id=job_id,
            action="rollback",
            success=True,
            message=f"Rollback completed: {rollback_stats.get('rows_restored', 0)} rows restored",
        )

    except MigrationOrchestratorError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error("migration_rollback_failed", job_id=job_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to rollback migration: {e}",
        )


@router.post("/migrations/{job_id}/approve", response_model=MigrationActionResponse)
async def approve_migration_phase(
    job_id: str,
    request: MigrationApproveRequest,
    mongodb_client=Depends(get_mongodb_client),
):
    """
    Aprova a próxima fase da migração (gate humano).

    Args:
        job_id: ID do job de migração
        request: Dados de aprovação
        mongodb_client: Cliente MongoDB injetado

    Returns:
        MigrationActionResponse confirmando aprovação
    """
    job_dict = await mongodb_client.find_migration_job_by_id(job_id)

    if not job_dict:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Migration job {job_id} not found",
        )

    job_status = job_dict.get("status")
    if job_status != "mapping":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot approve from status {job_status}, only 'mapping' requires approval",
        )

    try:
        # Buscar schema mapping
        schema_mapping_id = job_dict.get("schema_mapping_id")
        mapping_dict = await mongodb_client.find_schema_mapping_by_id(schema_mapping_id)

        if not mapping_dict:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Schema mapping {schema_mapping_id} not found",
            )

        orchestrator = get_migration_orchestrator(job_id)
        migration_job = MigrationJob(**job_dict)
        schema_mapping = SchemaMapping(**mapping_dict)

        await orchestrator.approve_next_phase(
            migration_job=migration_job,
            schema_mapping=schema_mapping,
            approved_by=request.approved_by,
        )

        # Atualizar status no MongoDB
        await mongodb_client.update_migration_job_status(
            job_id=job_id,
            status="mapping_approved",
        )

        logger.info(
            "migration_phase_approved",
            job_id=job_id,
            approved_by=request.approved_by,
        )

        return MigrationActionResponse(
            job_id=job_id,
            action="approve",
            success=True,
            message="Migration phase approved successfully",
        )

    except PhaseTransitionError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error("migration_approval_failed", job_id=job_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to approve migration: {e}",
        )


@router.post(
    "/migrations/{job_id}/validate",
    response_model=ValidationResultResponse,
)
async def validate_migration(
    job_id: str,
    mongodb_client=Depends(get_mongodb_client),
):
    """
    Valida os dados migrados.

    Args:
        job_id: ID do job de migração
        mongodb_client: Cliente MongoDB injetado

    Returns:
        ValidationResultResponse com relatório de validação
    """
    job_dict = await mongodb_client.find_migration_job_by_id(job_id)

    if not job_dict:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Migration job {job_id} not found",
        )

    # Buscar schema mapping
    schema_mapping_id = job_dict.get("schema_mapping_id")
    mapping_dict = await mongodb_client.find_schema_mapping_by_id(schema_mapping_id)

    if not mapping_dict:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Schema mapping {schema_mapping_id} not found",
        )

    try:
        # Obter URLs dos bancos do job (estariam em metadata)
        legacy_url = job_dict.get("metadata", {}).get("legacy_db_url")
        modern_url = job_dict.get("metadata", {}).get("modern_db_url")

        if not legacy_url or not modern_url:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Database connection URLs not found in job metadata",
            )

        # Conectar aos bancos
        legacy_client = PostgreSQLClient(dsn=legacy_url)
        await legacy_client.connect()

        modern_client = PostgreSQLClient(dsn=modern_url)
        await modern_client.connect()

        try:
            schema_mapping = SchemaMapping(**mapping_dict)
            validator = get_data_validator()

            report = await validator.generate_validation_report(
                schema_mapping=schema_mapping,
                legacy_client=legacy_client,
                modern_client=modern_client,
            )

            logger.info(
                "migration_validation_completed",
                job_id=job_id,
                overall_passed=report.get("overall_passed"),
            )

            return ValidationResultResponse(
                job_id=job_id,
                overall_passed=report["overall_passed"],
                total_validations=report["total_validations"],
                passed_validations=report["passed_validations"],
                failed_validations=report["failed_validations"],
                results=report["results"],
            )

        finally:
            await legacy_client.disconnect()
            await modern_client.disconnect()

    except Exception as e:
        logger.error("migration_validation_failed", job_id=job_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to validate migration: {e}",
        )


@router.get("/migrations/{job_id}/schema")
async def get_schema_mapping(
    job_id: str,
    mongodb_client=Depends(get_mongodb_client),
):
    """
    Obtém o mapeamento de schema de uma migração.

    Args:
        job_id: ID do job de migração
        mongodb_client: Cliente MongoDB injetado

    Returns:
        Schema mapping completo
    """
    job_dict = await mongodb_client.find_migration_job_by_id(job_id)

    if not job_dict:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Migration job {job_id} not found",
        )

    schema_mapping_id = job_dict.get("schema_mapping_id")
    mapping_dict = await mongodb_client.find_schema_mapping_by_id(schema_mapping_id)

    if not mapping_dict:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Schema mapping {schema_mapping_id} not found",
        )

    # Remover campos internos do MongoDB
    mapping_dict.pop("_id", None)

    return mapping_dict


# ========== Funções Auxiliares ==========


def _get_current_phase(status: str) -> str:
    """Retorna nome da fase baseado no status."""
    phase_map = {
        "pending": "Aguardando início",
        "analyzing": "Analisando schema",
        "mapping": "Gerando mapeamento",
        "mapping_approved": "Mapeamento aprovado",
        "snapshot_created": "Snapshot criado",
        "batch_migrating": "Migrando dados históricos",
        "cdc_running": "CDC em execução",
        "validating": "Validando dados",
        "completed": "Concluído",
        "failed": "Falhou",
        "rolled_back": "Rollback executado",
    }
    return phase_map.get(status, status)


def _parse_datetime(dt_str: Optional[str]) -> Optional[datetime]:
    """Parse de datetime string para datetime."""
    if not dt_str:
        return None
    if isinstance(dt_str, datetime):
        return dt_str
    try:
        return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


async def _execute_migration_task(
    job_id: str,
    job_dict: Dict[str, Any],
    mapping_dict: Dict[str, Any],
    auto_approve: bool = False,
    database_config: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Executa migração em background.

    Args:
        job_id: ID do job
        job_dict: Dicionário com dados do job
        mapping_dict: Dicionário com dados do schema mapping
        auto_approve: Se True, aprova fases automaticamente
        database_config: Configurações adicionais do banco
    """
    from src.db.mongodb import get_mongodb_client

    mongodb_client = await get_mongodb_client()

    try:
        # Obter URLs dos bancos
        legacy_url = job_dict.get("metadata", {}).get("legacy_db_url")
        modern_url = job_dict.get("metadata", {}).get("modern_db_url")

        if not legacy_url or not modern_url:
            logger.error("migration_task_missing_db_urls", job_id=job_id)
            await mongodb_client.update_migration_job_status(
                job_id=job_id,
                status="failed",
                error_message="Database URLs not found",
            )
            return

        # Conectar aos bancos
        legacy_client = PostgreSQLClient(dsn=legacy_url)
        await legacy_client.connect()

        modern_client = PostgreSQLClient(dsn=modern_url)
        await modern_client.connect()

        try:
            orchestrator = get_migration_orchestrator(job_id)
            migration_job = MigrationJob(**job_dict)
            schema_mapping = SchemaMapping(**mapping_dict)

            # Executar migração
            updated_job = await orchestrator.start_migration(
                migration_job=migration_job,
                schema_mapping=schema_mapping,
                legacy_client=legacy_client,
                target_client=modern_client,
                auto_approve=auto_approve,
                database_config=database_config,
            )

            # Atualizar status no MongoDB
            await mongodb_client.update_migration_job_status(
                job_id=job_id,
                status=updated_job.status,
                progress_data={
                    "rows_migrated": updated_job.rows_migrated,
                    "progress_percentage": updated_job.progress_percentage,
                },
            )

            logger.info(
                "migration_task_completed",
                job_id=job_id,
                final_status=updated_job.status,
            )

        finally:
            await legacy_client.disconnect()
            await modern_client.disconnect()
            # Limpar orchestrator
            clear_migration_orchestrator(job_id)

    except Exception as e:
        logger.error("migration_task_failed", job_id=job_id, error=str(e))
        await mongodb_client.update_migration_job_status(
            job_id=job_id,
            status="failed",
            error_message=str(e),
        )


@router.get("/migrations/{job_id}/cdc/reconnection-stats")
async def get_cdc_reconnection_stats(job_id: str) -> Dict[str, Any]:
    """
    Obtém estatísticas de reconexão do CDC (BUG-H-001).

    Args:
        job_id: ID do job de migração

    Returns:
        Dicionário com estatísticas de reconexão Kafka
    """
    from src.services import get_cdc_pipeline

    try:
        cdc_pipeline = get_cdc_pipeline(job_id)
        return cdc_pipeline.get_reconnection_stats()
    except Exception as e:
        logger.error("cdc_reconnection_stats_error", job_id=job_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao obter stats de reconexão: {e}",
        ) from e

