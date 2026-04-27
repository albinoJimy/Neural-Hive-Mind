"""
ScoutLedger - Persistência de explorações no MongoDB.

Responsável por:
- Salvar e recuperar explorações
- Atualizar status de explorações
- Listar e consultar explorações
- Cleanup de explorações antigas
- Estatísticas agregadas
"""

from datetime import datetime, timezone, timedelta
from typing import Any, Optional

import structlog

logger = structlog.get_logger()


class ScoutLedger:
    """Ledger para persistência de explorações dos scouts."""

    def __init__(
        self,
        mongo_client,
        collection_name: str = "scout_explorations",
        database_name: str = "scout_agents",
    ):
        """
        Inicializa o ScoutLedger.

        Args:
            mongo_client: Cliente MongoDB (motor/nested)
            collection_name: Nome da coleção
            database_name: Nome do banco de dados
        """
        self.mongo_client = mongo_client
        self.collection_name = collection_name
        self.database_name = database_name
        self._test_collection = None  # Apenas para testes

    def _get_collection(self):
        """Retorna a coleção MongoDB."""
        # Para testes, usa a collection mockada se disponível
        if self._test_collection is not None:
            return self._test_collection
        return self.mongo_client[self.database_name][self.collection_name]

    async def save_exploration(self, exploration_data: dict[str, Any]) -> dict[str, Any]:
        """
        Salva ou atualiza uma exploração.

        Args:
            exploration_data: Dados da exploração

        Returns:
            Dict com dados salvos incluindo _id
        """
        collection = self._get_collection()
        exploration_id = exploration_data.get("exploration_id")

        # Adicionar timestamps
        now = datetime.now(timezone.utc)
        if "created_at" not in exploration_data:
            exploration_data["created_at"] = now
        exploration_data["updated_at"] = now

        # Upsert baseado em exploration_id
        if exploration_id:
            result = await collection.update_one(
                {"exploration_id": exploration_id}, {"$set": exploration_data}, upsert=True
            )

            # Se foi upsert (novo documento)
            if result.upserted_id:
                exploration_data["_id"] = result.upserted_id
        else:
            # Insert novo sem exploration_id pré-definido
            result = await collection.insert_one(exploration_data)
            exploration_data["_id"] = result.inserted_id

        logger.info(
            "exploration_saved",
            exploration_id=exploration_id,
            status=exploration_data.get("status"),
        )

        return exploration_data

    async def get_exploration(self, exploration_id: str) -> Optional[dict[str, Any]]:
        """
        Recupera uma exploração por ID.

        Args:
            exploration_id: ID da exploração

        Returns:
            Dict da exploração ou None se não encontrado
        """
        collection = self._get_collection()

        doc = await collection.find_one({"exploration_id": exploration_id})

        if doc:
            # Converter ObjectId para string
            if "_id" in doc:
                doc["_id"] = str(doc["_id"])

        return doc

    async def list_explorations(
        self,
        plan_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
        skip: int = 0,
    ) -> list[dict[str, Any]]:
        """
        Lista explorações com filtros opcionais.

        Args:
            plan_id: Filtrar por plan_id
            status: Filtrar por status
            limit: Máximo de resultados
            skip: Quantos resultados pular

        Returns:
            Lista de explorações
        """
        collection = self._get_collection()

        # Construir filtro
        filter_query = {}
        if plan_id:
            filter_query["plan_id"] = plan_id
        if status:
            filter_query["status"] = status

        # Executar query
        cursor = collection.find(filter_query)

        if skip:
            cursor = cursor.skip(skip)
        if limit:
            cursor = cursor.limit(limit)

        # Ordenar por created_at decrescente
        cursor = cursor.sort("created_at", -1)

        docs = await cursor.to_list(length=limit)

        # Converter ObjectIds
        for doc in docs:
            if "_id" in doc:
                doc["_id"] = str(doc["_id"])

        return docs

    async def update_exploration_status(
        self,
        exploration_id: str,
        status: str,
        results: Optional[dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> bool:
        """
        Atualiza status de uma exploração.

        Args:
            exploration_id: ID da exploração
            status: Novo status
            results: Resultados opcionais
            error: Mensagem de erro (se falha)

        Returns:
            True se atualizou, False se não encontrou
        """
        collection = self._get_collection()

        update_data = {"status": status, "updated_at": datetime.now(timezone.utc)}

        if status == "completed":
            update_data["completed_at"] = datetime.now(timezone.utc)
        elif status in ["failed", "error"]:
            update_data["failed_at"] = datetime.now(timezone.utc)

        if results:
            update_data["results"] = results

        if error:
            update_data["error"] = error

        result = await collection.update_one(
            {"exploration_id": exploration_id}, {"$set": update_data}
        )

        updated = result.modified_count > 0

        if updated:
            logger.info("exploration_status_updated", exploration_id=exploration_id, status=status)

        return updated

    async def delete_exploration(self, exploration_id: str) -> bool:
        """
        Deleta uma exploração.

        Args:
            exploration_id: ID da exploração

        Returns:
            True se deletou, False se não encontrou
        """
        collection = self._get_collection()

        result = await collection.delete_one({"exploration_id": exploration_id})

        deleted = result.deleted_count > 0

        if deleted:
            logger.info("exploration_deleted", exploration_id=exploration_id)

        return deleted

    async def get_exploration_stats(self, plan_id: Optional[str] = None) -> dict[str, Any]:
        """
        Retorna estatísticas de explorações.

        Args:
            plan_id: Filtrar stats por plan_id

        Returns:
            Dict com estatísticas
        """
        collection = self._get_collection()

        # Pipeline de agregação
        pipeline = []

        # Filtrar por plan_id se especificado
        if plan_id:
            pipeline.append({"$match": {"plan_id": plan_id}})

        # Agrupar por status
        pipeline.append({"$group": {"_id": "$status", "count": {"$sum": 1}}})

        cursor = collection.aggregate(pipeline)
        status_counts = await cursor.to_list(length=10)

        # Construir resultado
        by_status = {}
        total = 0
        for doc in status_counts:
            status = doc["_id"] or "unknown"
            count = doc["count"]
            by_status[status] = count
            total += count

        result = {"total": total, "by_status": by_status}

        if plan_id:
            result["plan_id"] = plan_id

        return result

    async def cleanup_old_explorations(
        self, days_older_than: int = 30, status: Optional[str] = None
    ) -> int:
        """
        Remove explorações antigas.

        Args:
            days_older_than: Dias de antiguidade
            status: Filtrar por status (opcional)

        Returns:
            Número de documentos deletados
        """
        collection = self._get_collection()

        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_older_than)

        filter_query = {"created_at": {"$lt": cutoff_date}}

        # Se status especificado, apenas limpa aqueles
        if status:
            filter_query["status"] = status

        result = await collection.delete_many(filter_query)

        logger.info(
            "old_explorations_cleaned",
            count=result.deleted_count,
            days_older_than=days_older_than,
            status=status,
        )

        return result.deleted_count

    async def query_explorations(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        scouts_deployed: Optional[list[str]] = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """
        Consulta explorações com filtros complexos.

        Args:
            start_date: Data inicial
            end_date: Data final
            scouts_deployed: Scouts utilizados
            limit: Máximo de resultados

        Returns:
            Lista de explorações
        """
        collection = self._get_collection()

        filter_query = {}

        # Filtro de intervalo de datas
        if start_date or end_date:
            date_filter = {}
            if start_date:
                date_filter["$gte"] = start_date
            if end_date:
                date_filter["$lte"] = end_date
            filter_query["created_at"] = date_filter

        # Filtro de scouts
        if scouts_deployed:
            filter_query["scouts_deployed"] = {"$in": scouts_deployed}

        cursor = collection.find(filter_query)

        if limit:
            cursor = cursor.limit(limit)

        cursor = cursor.sort("created_at", -1)

        docs = await cursor.to_list(length=limit)

        for doc in docs:
            if "_id" in doc:
                doc["_id"] = str(doc["_id"])

        return docs
