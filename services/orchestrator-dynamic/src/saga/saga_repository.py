"""
Repository para persistencia de estado de Saga.

Gerencia o estado de Sagas no MongoDB com operacoes CRUD
e queries especializadas.
"""
import asyncio
from datetime import UTC, datetime

import structlog

from .saga_state import SagaConcurrentModificationError, SagaState, SagaStatus

logger = structlog.get_logger()


class SagaRepository:
    """
    Repository para persistencia de estado de Saga.

    Responsavel por salvar e recuperar estados de Saga do MongoDB.
    """

    # Nome da colecao no MongoDB
    COLLECTION_NAME = "sagas"

    def __init__(self, mongodb_client):
        """
        Inicializa o repository.

        Args:
            mongodb_client: MongoDBClient inicializado
        """
        self._client = mongodb_client
        self._collection = None

    async def initialize(self) -> None:
        """
        Inicializa a colecao e cria indices.

        Deve ser chamado apos o MongoDBClient estar conectado.
        """
        db = self._client.db
        self._collection = db[self.COLLECTION_NAME]

        # Criar indices
        await self._create_indexes()

        logger.info("saga_repository_initialized", collection=self.COLLECTION_NAME)

    async def _create_indexes(self) -> None:
        """Cria indexes na colecao de sagas."""
        if self._collection is None:
            return

        indexes = [
            # Index unico para saga_id
            {"keys": [("saga_id", 1)], "name": "saga_id_1", "unique": True},
            # Index para queries por workflow
            {"keys": [("workflow_id", 1)], "name": "workflow_id_1"},
            # Index para queries por status
            {"keys": [("status", 1)], "name": "status_1"},
            # Index composto para workflow + status
            {"keys": [("workflow_id", 1), ("status", 1)], "name": "workflow_id_1_status_1"},
            # Index temporal para queries de sagas antigas
            {"keys": [("created_at", -1)], "name": "created_at_-1"},
            # Index para queries por plan_id
            {"keys": [("plan_id", 1)], "name": "plan_id_1"},
            # Index para queries por intent_id
            {"keys": [("intent_id", 1)], "name": "intent_id_1"},
        ]

        for index_def in indexes:
            try:
                await self._collection.create_index(
                    index_def["keys"],
                    name=index_def["name"],
                    unique=index_def.get("unique", False),
                    background=True,
                )
            except Exception as e:
                logger.warning(
                    "saga_repository_index_creation_failed", index=index_def["name"], error=str(e)
                )

    async def save(self, saga: SagaState, timeout_ms: int = 5000) -> bool:
        """
        Salva ou atualiza uma Saga com optimistic locking.

        Usa upsert para criar nova saga ou atualizar existente.
        O optimistic locking garante que modificacoes concorrentes
        sao detectadas e rejeitadas.

        Args:
            saga: Estado da Saga a salvar
            timeout_ms: Timeout em milissegundos (default 5000ms)

        Returns:
            True se salvo com sucesso

        Raises:
            SagaConcurrentModificationError: Se a Saga foi modificada
                por outro processo desde a leitura
        """
        if self._collection is None:
            logger.warning("saga_repository_not_initialized", saga_id=saga.saga_id)
            return False

        try:
            doc = saga.model_dump()

            # Para upsert (nova saga), nao usamos version check
            # Para update, usamos optimistic locking com version
            if saga.version == 0:
                # Nova saga - upsert sem version check
                result = await asyncio.wait_for(
                    self._collection.update_one(
                        {"saga_id": saga.saga_id}, {"$set": doc}, upsert=True
                    ),
                    timeout=timeout_ms / 1000.0,
                )

                logger.info(
                    "saga_saved",
                    saga_id=saga.saga_id,
                    status=saga.status.value,
                    upserted=result.upserted_id is not None,
                )

                return True
            # Saga existente - optimistic locking com version
            result = await asyncio.wait_for(
                self._collection.update_one(
                    {"saga_id": saga.saga_id, "version": saga.version},
                    {"$set": {**doc, "version": saga.version + 1}},
                ),
                timeout=timeout_ms / 1000.0,
            )

            if result.matched_count == 0:
                # Nenhum documento matched - versao nao coincide
                # ou saga nao existe mais
                logger.error(
                    "saga_concurrent_modification",
                    saga_id=saga.saga_id,
                    expected_version=saga.version,
                    error="Saga was modified by another process or does not exist",
                )
                raise SagaConcurrentModificationError(
                    f"Saga {saga.saga_id} was modified by another process. "
                    f"Expected version {saga.version}"
                )

            logger.info(
                "saga_saved",
                saga_id=saga.saga_id,
                status=saga.status.value,
                version=saga.version + 1,
            )

            # Atualizar a versao localmente para refletir o incremento
            saga.version += 1

            return True

        except TimeoutError:
            logger.exception("saga_save_timeout", saga_id=saga.saga_id, timeout_ms=timeout_ms)
            return False
        except SagaConcurrentModificationError:
            # Re-raise para que o caller possa tratar
            raise
        except Exception as e:
            logger.exception("saga_save_failed", saga_id=saga.saga_id, error=str(e))
            return False

    async def find_by_id(self, saga_id: str) -> SagaState | None:
        """
        Busca uma Saga por ID.

        Args:
            saga_id: ID da Saga

        Returns:
            Estado da Saga ou None se nao encontrada
        """
        if self._collection is None:
            logger.warning("saga_repository_not_initialized")
            return None

        try:
            doc = await self._collection.find_one({"saga_id": saga_id})

            if doc:
                # Remover _id do MongoDB
                doc.pop("_id", None)
                return SagaState(**doc)

            return None

        except Exception as e:
            logger.exception("saga_find_by_id_failed", saga_id=saga_id, error=str(e))
            return None

    async def find_by_workflow(self, workflow_id: str) -> SagaState | None:
        """
        Busca uma Saga associada a um workflow.

        Args:
            workflow_id: ID do workflow Temporal

        Returns:
            Estado da Saga ou None se nao encontrada
        """
        if self._collection is None:
            logger.warning("saga_repository_not_initialized")
            return None

        try:
            doc = await self._collection.find_one({"workflow_id": workflow_id})

            if doc:
                doc.pop("_id", None)
                return SagaState(**doc)

            return None

        except Exception as e:
            logger.exception("saga_find_by_workflow_failed", workflow_id=workflow_id, error=str(e))
            return None

    async def find_by_status(self, status: SagaStatus, limit: int = 100) -> list[SagaState]:
        """
        Busca Sagas por status.

        Args:
            status: Status das Sagas
            limit: Numero maximo de resultados

        Returns:
            Lista de Sagas com o status especificado
        """
        if self._collection is None:
            logger.warning("saga_repository_not_initialized")
            return []

        try:
            cursor = (
                self._collection.find({"status": status.value}).sort("created_at", -1).limit(limit)
            )

            docs = await cursor.to_list(length=limit)

            sagas = [SagaState(**{k: v for k, v in doc.items() if k != "_id"}) for doc in docs]

            logger.debug("sagas_found_by_status", status=status.value, count=len(sagas))

            return sagas

        except Exception as e:
            logger.exception("saga_find_by_status_failed", status=status.value, error=str(e))
            return []

    async def find_pending_sagas(
        self, older_than_ms: int | None = None, limit: int = 100, timeout_ms: int = 5000
    ) -> list[SagaState]:
        """
        Busca Sagas pendentes para reprocessamento.

        Args:
            older_than_ms: Buscar sagas mais antigas que X millis
            limit: Numero maximo de resultados
            timeout_ms: Timeout em milissegundos (default 5000ms)

        Returns:
            Lista de Sagas pendentes
        """
        if self._collection is None:
            logger.warning("saga_repository_not_initialized")
            return []

        try:
            query = {"status": SagaStatus.PENDING.value}

            if older_than_ms:
                cutoff = int(datetime.now(UTC).timestamp() * 1000) - older_than_ms
                query["created_at"] = {"$lt": cutoff}

            cursor = await asyncio.wait_for(
                self._collection.find(query)
                .sort("created_at", 1)
                .limit(limit)
                .to_list(length=limit),
                timeout=timeout_ms / 1000.0,
            )

            docs = cursor

            sagas = [SagaState(**{k: v for k, v in doc.items() if k != "_id"}) for doc in docs]

            logger.debug("pending_sagas_found", count=len(sagas))

            return sagas

        except TimeoutError:
            logger.exception("pending_sagas_search_timeout", timeout_ms=timeout_ms)
            return []
        except Exception as e:
            logger.exception("pending_sagas_search_failed", error=str(e))
            return []

    async def find_failed_sagas(self, can_retry: bool = True, limit: int = 100) -> list[SagaState]:
        """
        Busca Sagas falhadas.

        Args:
            can_retry: Se True, retorna apenas sagas que podem ser retentadas
            limit: Numero maximo de resultados

        Returns:
            Lista de Sagas falhadas
        """
        if self._collection is None:
            logger.warning("saga_repository_not_initialized")
            return []

        try:
            query = {"status": SagaStatus.FAILED.value}

            if can_retry:
                # Apenas sagas com retry_count < max_retries
                query["$expr"] = {"$lt": ["$retry_count", "$max_retries"]}

            cursor = self._collection.find(query).sort("failed_at", -1).limit(limit)

            docs = await cursor.to_list(length=limit)

            sagas = [SagaState(**{k: v for k, v in doc.items() if k != "_id"}) for doc in docs]

            logger.debug("failed_sagas_found", count=len(sagas))

            return sagas

        except Exception as e:
            logger.exception("failed_sagas_search_failed", error=str(e))
            return []

    async def update_status(self, saga_id: str, status: SagaStatus, timeout_ms: int = 5000) -> bool:
        """
        Atualiza apenas o status de uma Saga.

        Args:
            saga_id: ID da Saga
            status: Novo status
            timeout_ms: Timeout em milissegundos (default 5000ms)

        Returns:
            True se atualizado com sucesso
        """
        if self._collection is None:
            return False

        try:
            update_data = {"status": status.value}

            # Adicionar timestamp baseado no status
            now = int(datetime.now(UTC).timestamp() * 1000)
            if status == SagaStatus.STARTED:
                update_data["started_at"] = now
            elif status == SagaStatus.COMPLETED:
                update_data["completed_at"] = now
            elif status == SagaStatus.COMPENSATED:
                update_data["compensated_at"] = now
            elif status == SagaStatus.FAILED:
                update_data["failed_at"] = now

            result = await asyncio.wait_for(
                self._collection.update_one({"saga_id": saga_id}, {"$set": update_data}),
                timeout=timeout_ms / 1000.0,
            )

            if result.matched_count == 0:
                logger.warning("saga_not_found_for_status_update", saga_id=saga_id)
                return False

            logger.debug("saga_status_updated", saga_id=saga_id, status=status.value)

            return True

        except TimeoutError:
            logger.exception("saga_status_update_timeout", saga_id=saga_id, timeout_ms=timeout_ms)
            return False
        except Exception as e:
            logger.exception("saga_status_update_failed", saga_id=saga_id, error=str(e))
            return False

    async def delete(self, saga_id: str) -> bool:
        """
        Remove uma Saga do repositório.

        Args:
            saga_id: ID da Saga a remover

        Returns:
            True se removida com sucesso
        """
        if self._collection is None:
            return False

        try:
            result = await self._collection.delete_one({"saga_id": saga_id})

            if result.deleted_count == 0:
                logger.warning("saga_not_found_for_deletion", saga_id=saga_id)
                return False

            logger.info("saga_deleted", saga_id=saga_id)

            return True

        except Exception as e:
            logger.exception("saga_deletion_failed", saga_id=saga_id, error=str(e))
            return False

    async def count_by_status(self) -> dict:
        """
        Conta Sagas agrupadas por status.

        Returns:
            Dicionario com contagem por status
        """
        if self._collection is None:
            return {}

        try:
            pipeline = [{"$group": {"_id": "$status", "count": {"$sum": 1}}}]

            cursor = self._collection.aggregate(pipeline)
            docs = await cursor.to_list(length=20)

            counts = {doc["_id"]: doc["count"] for doc in docs}

            logger.debug("saga_counts_by_status", counts=counts)

            return counts

        except Exception as e:
            logger.exception("saga_count_by_status_failed", error=str(e))
            return {}
