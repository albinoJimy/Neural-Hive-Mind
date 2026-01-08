"""
Cliente MongoDB para armazenar artefatos intermediários e logs.

Fornece interface assíncrona ao MongoDB via Motor para armazenamento de artefatos e logs de pipeline.
"""

import time
from typing import Optional, Dict, Any, List, TYPE_CHECKING
from datetime import datetime
import structlog
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import DuplicateKeyError, ConnectionFailure, OperationFailure

if TYPE_CHECKING:
    from ..observability.metrics import CodeForgeMetrics

logger = structlog.get_logger()


class MongoDBClient:
    """Cliente MongoDB assíncrono para armazenamento de artefatos e logs"""

    def __init__(
        self,
        url: str,
        db_name: str,
        max_pool_size: int = 50,
        server_selection_timeout_ms: int = 5000,
        metrics: Optional['CodeForgeMetrics'] = None
    ):
        """
        Inicializa o cliente MongoDB.

        Args:
            url: URI de conexão do MongoDB
            db_name: Nome do banco de dados
            max_pool_size: Tamanho máximo do pool de conexões
            server_selection_timeout_ms: Timeout de seleção do servidor em ms
            metrics: Instância de CodeForgeMetrics para instrumentação
        """
        self.url = url
        self.db_name = db_name
        self.max_pool_size = max_pool_size
        self.server_selection_timeout_ms = server_selection_timeout_ms
        self.client: Optional[AsyncIOMotorClient] = None
        self.db = None
        self.metrics = metrics

    async def start(self):
        """Inicia conexão com MongoDB e cria índices necessários."""
        try:
            self.client = AsyncIOMotorClient(
                self.url,
                maxPoolSize=self.max_pool_size,
                serverSelectionTimeoutMS=self.server_selection_timeout_ms,
                retryWrites=True,
                w='majority'
            )

            self.db = self.client[self.db_name]

            # Valida conexão
            await self.client.admin.command('ping')

            # Cria índices necessários
            await self._create_indexes()

            logger.info(
                'mongodb_client_started',
                db=self.db_name,
                max_pool_size=self.max_pool_size
            )

        except ConnectionFailure as e:
            logger.error('mongodb_connection_failed', error=str(e))
            raise
        except Exception as e:
            logger.error('mongodb_start_failed', error=str(e))
            raise

    async def _create_indexes(self):
        """Cria índices para otimizar consultas."""
        try:
            # Índice único para artifact_id
            await self.db.artifacts.create_index(
                [('artifact_id', 1)],
                unique=True
            )

            # Índice para buscar por ticket_id
            await self.db.artifacts.create_index([('ticket_id', 1)])

            # Índice para pipeline_logs
            await self.db.pipeline_logs.create_index(
                [('pipeline_id', 1), ('created_at', -1)]
            )

            logger.debug('mongodb_indexes_created')

        except Exception as e:
            logger.warning('mongodb_index_creation_failed', error=str(e))

    async def stop(self):
        """Fecha conexão com MongoDB."""
        if self.client:
            self.client.close()
            self.client = None
            self.db = None
            logger.info('mongodb_client_stopped')

    async def save_artifact_content(self, artifact_id: str, content: str, metadata: Optional[Dict[str, Any]] = None):
        """
        Salva conteúdo de artefato.

        Args:
            artifact_id: ID do artefato
            content: Conteúdo a salvar
            metadata: Metadados adicionais opcionais
        """
        if not self.db:
            raise RuntimeError('MongoDB client not started')

        start_time = time.perf_counter()
        try:
            document = {
                'artifact_id': artifact_id,
                'content': content,
                'created_at': datetime.utcnow(),
            }

            if metadata:
                document['metadata'] = metadata

            # Usa upsert para atualizar se já existir
            await self.db.artifacts.update_one(
                {'artifact_id': artifact_id},
                {'$set': document},
                upsert=True
            )

            logger.info('artifact_content_saved', artifact_id=artifact_id)

            if self.metrics:
                duration = time.perf_counter() - start_time
                self.metrics.mongodb_operations_total.labels(operation='save_artifact', status='success').inc()
                self.metrics.mongodb_operation_duration_seconds.labels(operation='save_artifact').observe(duration)

        except DuplicateKeyError:
            # Fallback para update se houver race condition
            await self.db.artifacts.update_one(
                {'artifact_id': artifact_id},
                {'$set': {'content': content, 'updated_at': datetime.utcnow()}}
            )
            logger.info('artifact_content_updated', artifact_id=artifact_id)

            if self.metrics:
                duration = time.perf_counter() - start_time
                self.metrics.mongodb_operations_total.labels(operation='save_artifact', status='success').inc()
                self.metrics.mongodb_operation_duration_seconds.labels(operation='save_artifact').observe(duration)

        except Exception as e:
            if self.metrics:
                self.metrics.mongodb_operations_total.labels(operation='save_artifact', status='failure').inc()
            logger.error('save_artifact_content_failed', artifact_id=artifact_id, error=str(e))
            raise

    async def get_artifact_content(self, artifact_id: str) -> Optional[str]:
        """
        Recupera conteúdo de artefato.

        Args:
            artifact_id: ID do artefato

        Returns:
            Conteúdo do artefato ou None se não encontrado
        """
        if not self.db:
            raise RuntimeError('MongoDB client not started')

        start_time = time.perf_counter()
        try:
            doc = await self.db.artifacts.find_one({'artifact_id': artifact_id})

            if self.metrics:
                duration = time.perf_counter() - start_time
                self.metrics.mongodb_operations_total.labels(operation='get_artifact', status='success').inc()
                self.metrics.mongodb_operation_duration_seconds.labels(operation='get_artifact').observe(duration)

            if doc:
                logger.debug('artifact_content_found', artifact_id=artifact_id)
                return doc.get('content')

            logger.debug('artifact_content_not_found', artifact_id=artifact_id)
            return None

        except Exception as e:
            if self.metrics:
                self.metrics.mongodb_operations_total.labels(operation='get_artifact', status='failure').inc()
            logger.error('get_artifact_content_failed', artifact_id=artifact_id, error=str(e))
            return None

    async def delete_artifact(self, artifact_id: str) -> bool:
        """
        Remove artefato.

        Args:
            artifact_id: ID do artefato

        Returns:
            True se removido com sucesso
        """
        if not self.db:
            raise RuntimeError('MongoDB client not started')

        try:
            result = await self.db.artifacts.delete_one({'artifact_id': artifact_id})
            deleted = result.deleted_count > 0
            logger.info('artifact_deleted', artifact_id=artifact_id, deleted=deleted)
            return deleted

        except Exception as e:
            logger.error('delete_artifact_failed', artifact_id=artifact_id, error=str(e))
            return False

    async def save_pipeline_logs(self, pipeline_id: str, logs: List[Dict[str, Any]]):
        """
        Salva logs detalhados de pipeline.

        Args:
            pipeline_id: ID do pipeline
            logs: Lista de entradas de log
        """
        if not self.db:
            raise RuntimeError('MongoDB client not started')

        start_time = time.perf_counter()
        try:
            document = {
                'pipeline_id': pipeline_id,
                'logs': logs,
                'created_at': datetime.utcnow(),
            }

            await self.db.pipeline_logs.insert_one(document)
            logger.info('pipeline_logs_saved', pipeline_id=pipeline_id, log_count=len(logs))

            if self.metrics:
                duration = time.perf_counter() - start_time
                self.metrics.mongodb_operations_total.labels(operation='save_logs', status='success').inc()
                self.metrics.mongodb_operation_duration_seconds.labels(operation='save_logs').observe(duration)

        except Exception as e:
            if self.metrics:
                self.metrics.mongodb_operations_total.labels(operation='save_logs', status='failure').inc()
            logger.error('save_pipeline_logs_failed', pipeline_id=pipeline_id, error=str(e))
            raise

    async def get_pipeline_logs(self, pipeline_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Recupera logs de pipeline.

        Args:
            pipeline_id: ID do pipeline
            limit: Número máximo de documentos de log a retornar

        Returns:
            Lista de documentos de log
        """
        if not self.db:
            raise RuntimeError('MongoDB client not started')

        try:
            cursor = self.db.pipeline_logs.find(
                {'pipeline_id': pipeline_id}
            ).sort('created_at', -1).limit(limit)

            logs = await cursor.to_list(length=limit)
            logger.debug('pipeline_logs_retrieved', pipeline_id=pipeline_id, count=len(logs))
            return logs

        except Exception as e:
            logger.error('get_pipeline_logs_failed', pipeline_id=pipeline_id, error=str(e))
            return []

    async def append_pipeline_log(self, pipeline_id: str, log_entry: Dict[str, Any]):
        """
        Adiciona entrada de log a um pipeline existente ou cria novo.

        Args:
            pipeline_id: ID do pipeline
            log_entry: Entrada de log a adicionar
        """
        if not self.db:
            raise RuntimeError('MongoDB client not started')

        try:
            log_entry['timestamp'] = datetime.utcnow()

            await self.db.pipeline_logs.update_one(
                {'pipeline_id': pipeline_id},
                {
                    '$push': {'logs': log_entry},
                    '$setOnInsert': {'created_at': datetime.utcnow()}
                },
                upsert=True
            )

            logger.debug('pipeline_log_appended', pipeline_id=pipeline_id)

        except Exception as e:
            logger.error('append_pipeline_log_failed', pipeline_id=pipeline_id, error=str(e))
            raise

    async def health_check(self) -> bool:
        """
        Verifica saúde da conexão com MongoDB.

        Returns:
            True se conexão está saudável
        """
        if not self.client:
            return False

        start_time = time.perf_counter()
        try:
            await self.client.admin.command('ping')
            if self.metrics:
                duration = time.perf_counter() - start_time
                self.metrics.mongodb_operations_total.labels(operation='health_check', status='success').inc()
                self.metrics.mongodb_operation_duration_seconds.labels(operation='health_check').observe(duration)
            return True
        except Exception as e:
            if self.metrics:
                self.metrics.mongodb_operations_total.labels(operation='health_check', status='failure').inc()
            logger.warning('mongodb_health_check_failed', error=str(e))
            return False
