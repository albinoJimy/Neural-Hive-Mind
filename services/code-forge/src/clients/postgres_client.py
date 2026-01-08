"""
Cliente PostgreSQL para persistir metadados de pipelines.

Utiliza SQLAlchemy async com asyncpg para operações assíncronas.
"""

import asyncio
import time
from typing import Optional, Dict, Any, List, TYPE_CHECKING
from datetime import datetime
import structlog
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession, AsyncEngine
from sqlalchemy import select, update, func, Column, String, Integer, TIMESTAMP, JSON, Boolean, Text
from sqlalchemy.orm import declarative_base
from sqlalchemy.exc import SQLAlchemyError

from ..models.artifact import PipelineResult, CodeForgeArtifact, PipelineStatus

if TYPE_CHECKING:
    from ..observability.metrics import CodeForgeMetrics

logger = structlog.get_logger()

Base = declarative_base()


class PipelineResultORM(Base):
    """Modelo ORM para resultados de pipeline."""

    __tablename__ = 'pipeline_results'

    pipeline_id = Column(String(64), primary_key=True)
    ticket_id = Column(String(64), index=True, nullable=False)
    plan_id = Column(String(64), index=True, nullable=False)
    intent_id = Column(String(64), nullable=False)
    decision_id = Column(String(64), nullable=False)
    correlation_id = Column(String(64), nullable=True)
    trace_id = Column(String(64), nullable=True)
    span_id = Column(String(64), nullable=True)
    status = Column(String(32), index=True, nullable=False)
    artifacts = Column(JSON, nullable=False, default=list)
    pipeline_stages = Column(JSON, nullable=False, default=list)
    total_duration_ms = Column(Integer, nullable=False, default=0)
    approval_required = Column(Boolean, nullable=False, default=False)
    approval_reason = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    git_mr_url = Column(String(512), nullable=True)
    metadata = Column(JSON, nullable=False, default=dict)
    created_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)
    completed_at = Column(TIMESTAMP, nullable=True)
    schema_version = Column(Integer, nullable=False, default=1)

    @classmethod
    def from_pydantic(cls, result: PipelineResult) -> 'PipelineResultORM':
        """Converte PipelineResult Pydantic para ORM."""
        return cls(
            pipeline_id=result.pipeline_id,
            ticket_id=result.ticket_id,
            plan_id=result.plan_id,
            intent_id=result.intent_id,
            decision_id=result.decision_id,
            correlation_id=result.correlation_id,
            trace_id=result.trace_id,
            span_id=result.span_id,
            status=result.status.value if isinstance(result.status, PipelineStatus) else result.status,
            artifacts=[a.dict() for a in result.artifacts],
            pipeline_stages=[s.dict() for s in result.pipeline_stages],
            total_duration_ms=result.total_duration_ms,
            approval_required=result.approval_required,
            approval_reason=result.approval_reason,
            error_message=result.error_message,
            git_mr_url=result.git_mr_url,
            metadata=result.metadata,
            created_at=result.created_at,
            completed_at=result.completed_at,
            schema_version=result.schema_version,
        )

    def to_pydantic(self) -> PipelineResult:
        """Converte ORM para PipelineResult Pydantic."""
        from ..models.artifact import CodeForgeArtifact, PipelineStage

        return PipelineResult(
            pipeline_id=self.pipeline_id,
            ticket_id=self.ticket_id,
            plan_id=self.plan_id,
            intent_id=self.intent_id,
            decision_id=self.decision_id,
            correlation_id=self.correlation_id,
            trace_id=self.trace_id,
            span_id=self.span_id,
            status=PipelineStatus(self.status),
            artifacts=[CodeForgeArtifact(**a) for a in (self.artifacts or [])],
            pipeline_stages=[PipelineStage(**s) for s in (self.pipeline_stages or [])],
            total_duration_ms=self.total_duration_ms,
            approval_required=self.approval_required,
            approval_reason=self.approval_reason,
            error_message=self.error_message,
            git_mr_url=self.git_mr_url,
            metadata=self.metadata or {},
            created_at=self.created_at,
            completed_at=self.completed_at,
            schema_version=self.schema_version,
        )


class ArtifactMetadataORM(Base):
    """Modelo ORM para metadados de artefatos."""

    __tablename__ = 'artifact_metadata'

    artifact_id = Column(String(64), primary_key=True)
    ticket_id = Column(String(64), index=True, nullable=False)
    plan_id = Column(String(64), index=True, nullable=False)
    intent_id = Column(String(64), nullable=False)
    decision_id = Column(String(64), nullable=False)
    artifact_type = Column(String(32), index=True, nullable=False)
    language = Column(String(32), nullable=True)
    template_id = Column(String(64), nullable=True)
    confidence_score = Column(Integer, nullable=False, default=0)  # Stored as int (0-100)
    generation_method = Column(String(32), nullable=False)
    content_uri = Column(String(512), nullable=False)
    content_hash = Column(String(128), nullable=False)
    sbom_uri = Column(String(512), nullable=True)
    signature = Column(Text, nullable=True)
    validation_results = Column(JSON, nullable=False, default=list)
    metadata = Column(JSON, nullable=False, default=dict)
    created_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)

    @classmethod
    def from_pydantic(cls, artifact: CodeForgeArtifact) -> 'ArtifactMetadataORM':
        """Converte CodeForgeArtifact Pydantic para ORM."""
        return cls(
            artifact_id=artifact.artifact_id,
            ticket_id=artifact.ticket_id,
            plan_id=artifact.plan_id,
            intent_id=artifact.intent_id,
            decision_id=artifact.decision_id,
            artifact_type=artifact.artifact_type.value if hasattr(artifact.artifact_type, 'value') else artifact.artifact_type,
            language=artifact.language,
            template_id=artifact.template_id,
            confidence_score=int(artifact.confidence_score * 100),
            generation_method=artifact.generation_method.value if hasattr(artifact.generation_method, 'value') else artifact.generation_method,
            content_uri=artifact.content_uri,
            content_hash=artifact.content_hash,
            sbom_uri=artifact.sbom_uri,
            signature=artifact.signature,
            validation_results=[vr.dict() for vr in artifact.validation_results],
            metadata=artifact.metadata,
            created_at=artifact.created_at,
        )


class PostgresClient:
    """Cliente PostgreSQL async para gerenciar metadados de pipelines."""

    def __init__(
        self,
        url: str,
        pool_size: int = 10,
        max_overflow: int = 20,
        metrics: Optional['CodeForgeMetrics'] = None
    ):
        """
        Inicializa cliente PostgreSQL.

        Args:
            url: URL de conexão (formato: postgresql://user:pass@host:port/db
                 ou postgresql+asyncpg://user:pass@host:port/db)
            pool_size: Tamanho do pool de conexões
            max_overflow: Conexões extras permitidas além do pool
            metrics: Instância de CodeForgeMetrics para instrumentação
        """
        # Garante que usa driver asyncpg
        if url.startswith('postgresql://'):
            url = url.replace('postgresql://', 'postgresql+asyncpg://', 1)

        self.url = url
        self.pool_size = pool_size
        self.max_overflow = max_overflow
        self.engine: Optional[AsyncEngine] = None
        self.session_factory: Optional[async_sessionmaker] = None
        self.metrics = metrics

    async def start(self, max_retries: int = 5, initial_delay: float = 1.0):
        """
        Inicia conexão com PostgreSQL com retry logic.

        Args:
            max_retries: Número máximo de tentativas
            initial_delay: Delay inicial entre tentativas (exponential backoff)
        """
        for attempt in range(max_retries):
            try:
                logger.info(
                    'postgres_connecting',
                    attempt=attempt + 1,
                    max_retries=max_retries
                )

                self.engine = create_async_engine(
                    self.url,
                    pool_size=self.pool_size,
                    max_overflow=self.max_overflow,
                    echo=False
                )

                self.session_factory = async_sessionmaker(
                    self.engine,
                    class_=AsyncSession,
                    expire_on_commit=False
                )

                # Cria tabelas se não existirem
                async with self.engine.begin() as conn:
                    await conn.run_sync(Base.metadata.create_all)

                # Testa conexão
                async with self.session_factory() as session:
                    await session.execute(select(func.count()).select_from(PipelineResultORM))

                logger.info('postgres_client_started', pool_size=self.pool_size)
                return

            except Exception as e:
                delay = initial_delay * (2 ** attempt)
                logger.warning(
                    'postgres_connection_failed',
                    error=str(e),
                    attempt=attempt + 1,
                    retry_in_seconds=delay
                )

                if attempt < max_retries - 1:
                    await asyncio.sleep(delay)
                else:
                    logger.error('postgres_connection_exhausted_retries')
                    raise

    async def stop(self):
        """Fecha conexão com PostgreSQL."""
        if self.engine:
            await self.engine.dispose()
            self.engine = None
            self.session_factory = None
            logger.info('postgres_client_stopped')

    async def save_pipeline(self, pipeline_result: PipelineResult):
        """
        Salva resultado de pipeline.

        Args:
            pipeline_result: Resultado do pipeline a salvar
        """
        if not self.session_factory:
            raise RuntimeError('PostgreSQL client not started')

        start_time = time.perf_counter()
        try:
            async with self.session_factory() as session:
                orm_obj = PipelineResultORM.from_pydantic(pipeline_result)

                # Usa merge para upsert
                await session.merge(orm_obj)
                await session.commit()

            logger.info('pipeline_saved', pipeline_id=pipeline_result.pipeline_id)

            if self.metrics:
                duration = time.perf_counter() - start_time
                self.metrics.postgres_operations_total.labels(operation='save_pipeline', status='success').inc()
                self.metrics.postgres_operation_duration_seconds.labels(operation='save_pipeline').observe(duration)

        except SQLAlchemyError as e:
            if self.metrics:
                self.metrics.postgres_operations_total.labels(operation='save_pipeline', status='failure').inc()
            logger.error('save_pipeline_failed', pipeline_id=pipeline_result.pipeline_id, error=str(e))
            raise

    async def get_pipeline(self, pipeline_id: str) -> Optional[PipelineResult]:
        """
        Busca pipeline por ID.

        Args:
            pipeline_id: ID do pipeline

        Returns:
            PipelineResult ou None se não encontrado
        """
        if not self.session_factory:
            raise RuntimeError('PostgreSQL client not started')

        start_time = time.perf_counter()
        try:
            async with self.session_factory() as session:
                result = await session.execute(
                    select(PipelineResultORM).where(PipelineResultORM.pipeline_id == pipeline_id)
                )
                orm_obj = result.scalar_one_or_none()

                if self.metrics:
                    duration = time.perf_counter() - start_time
                    self.metrics.postgres_operations_total.labels(operation='get_pipeline', status='success').inc()
                    self.metrics.postgres_operation_duration_seconds.labels(operation='get_pipeline').observe(duration)

                if orm_obj:
                    return orm_obj.to_pydantic()
                return None

        except SQLAlchemyError as e:
            if self.metrics:
                self.metrics.postgres_operations_total.labels(operation='get_pipeline', status='failure').inc()
            logger.error('get_pipeline_failed', pipeline_id=pipeline_id, error=str(e))
            return None

    async def list_pipelines(
        self,
        filters: Dict[str, Any],
        offset: int = 0,
        limit: int = 100
    ) -> List[PipelineResult]:
        """
        Lista pipelines com filtros.

        Args:
            filters: Dicionário de filtros (ticket_id, plan_id, status)
            offset: Número de registros a pular
            limit: Número máximo de registros a retornar

        Returns:
            Lista de PipelineResult
        """
        if not self.session_factory:
            raise RuntimeError('PostgreSQL client not started')

        try:
            async with self.session_factory() as session:
                query = select(PipelineResultORM)

                # Aplica filtros
                if 'ticket_id' in filters:
                    query = query.where(PipelineResultORM.ticket_id == filters['ticket_id'])
                if 'plan_id' in filters:
                    query = query.where(PipelineResultORM.plan_id == filters['plan_id'])
                if 'status' in filters:
                    status_value = filters['status']
                    if isinstance(status_value, PipelineStatus):
                        status_value = status_value.value
                    query = query.where(PipelineResultORM.status == status_value)
                if 'intent_id' in filters:
                    query = query.where(PipelineResultORM.intent_id == filters['intent_id'])

                query = query.order_by(PipelineResultORM.created_at.desc())
                query = query.offset(offset).limit(limit)

                result = await session.execute(query)
                orm_objs = result.scalars().all()

                return [obj.to_pydantic() for obj in orm_objs]

        except SQLAlchemyError as e:
            logger.error('list_pipelines_failed', error=str(e))
            return []

    async def update_pipeline_status(
        self,
        pipeline_id: str,
        status: PipelineStatus,
        error_message: Optional[str] = None,
        completed_at: Optional[datetime] = None
    ) -> bool:
        """
        Atualiza status de um pipeline.

        Args:
            pipeline_id: ID do pipeline
            status: Novo status
            error_message: Mensagem de erro opcional
            completed_at: Timestamp de conclusão opcional

        Returns:
            True se atualizado com sucesso
        """
        if not self.session_factory:
            raise RuntimeError('PostgreSQL client not started')

        try:
            async with self.session_factory() as session:
                values = {'status': status.value}
                if error_message:
                    values['error_message'] = error_message
                if completed_at:
                    values['completed_at'] = completed_at

                stmt = (
                    update(PipelineResultORM)
                    .where(PipelineResultORM.pipeline_id == pipeline_id)
                    .values(**values)
                )
                result = await session.execute(stmt)
                await session.commit()

                updated = result.rowcount > 0
                logger.info('pipeline_status_updated', pipeline_id=pipeline_id, status=status.value, updated=updated)
                return updated

        except SQLAlchemyError as e:
            logger.error('update_pipeline_status_failed', pipeline_id=pipeline_id, error=str(e))
            return False

    async def save_artifact_metadata(self, artifact: CodeForgeArtifact):
        """
        Salva metadados de artefato.

        Args:
            artifact: Artefato a salvar
        """
        if not self.session_factory:
            raise RuntimeError('PostgreSQL client not started')

        try:
            async with self.session_factory() as session:
                orm_obj = ArtifactMetadataORM.from_pydantic(artifact)
                await session.merge(orm_obj)
                await session.commit()

            logger.info('artifact_metadata_saved', artifact_id=artifact.artifact_id)

        except SQLAlchemyError as e:
            logger.error('save_artifact_metadata_failed', artifact_id=artifact.artifact_id, error=str(e))
            raise

    async def get_pipeline_statistics(self, filters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Retorna estatísticas agregadas de pipelines.

        Args:
            filters: Filtros opcionais (ticket_id, plan_id, etc)

        Returns:
            Dicionário com estatísticas
        """
        if not self.session_factory:
            raise RuntimeError('PostgreSQL client not started')

        try:
            async with self.session_factory() as session:
                # Query base para contagem total
                total_query = select(func.count()).select_from(PipelineResultORM)

                # Query para duração média
                avg_duration_query = select(func.avg(PipelineResultORM.total_duration_ms)).select_from(PipelineResultORM)

                # Aplica filtros se fornecidos
                if filters:
                    if 'ticket_id' in filters:
                        total_query = total_query.where(PipelineResultORM.ticket_id == filters['ticket_id'])
                        avg_duration_query = avg_duration_query.where(PipelineResultORM.ticket_id == filters['ticket_id'])

                total_result = await session.execute(total_query)
                total = total_result.scalar() or 0

                avg_duration_result = await session.execute(avg_duration_query)
                avg_duration = avg_duration_result.scalar() or 0

                # Contagem por status
                status_counts = {}
                for status in PipelineStatus:
                    status_query = select(func.count()).select_from(PipelineResultORM).where(
                        PipelineResultORM.status == status.value
                    )
                    result = await session.execute(status_query)
                    status_counts[status.value] = result.scalar() or 0

                return {
                    'total_pipelines': total,
                    'average_duration_ms': float(avg_duration),
                    'status_counts': status_counts,
                }

        except SQLAlchemyError as e:
            logger.error('get_pipeline_statistics_failed', error=str(e))
            return {}

    async def health_check(self) -> bool:
        """
        Verifica saúde da conexão.

        Returns:
            True se conexão está saudável
        """
        if not self.session_factory:
            return False

        start_time = time.perf_counter()
        try:
            async with self.session_factory() as session:
                await session.execute(select(func.count()).select_from(PipelineResultORM))
            if self.metrics:
                duration = time.perf_counter() - start_time
                self.metrics.postgres_operations_total.labels(operation='health_check', status='success').inc()
                self.metrics.postgres_operation_duration_seconds.labels(operation='health_check').observe(duration)
            return True
        except Exception as e:
            if self.metrics:
                self.metrics.postgres_operations_total.labels(operation='health_check', status='failure').inc()
            logger.warning('postgres_health_check_failed', error=str(e))
            return False
