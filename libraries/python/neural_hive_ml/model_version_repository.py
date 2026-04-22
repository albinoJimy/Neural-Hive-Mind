"""ModelVersionRepository - MongoDB Model Versions History."""

import logging
from datetime import UTC, datetime
from typing import Any, Optional

from motor.motor_asyncio import AsyncIOMotorDatabase

logger = logging.getLogger(__name__)


class ModelVersionRepository:
    """
    Repositório MongoDB para histórico de versões de modelos.

    Gerencia versões de modelos de aprovação com metadados,
    drift metrics e histórico de promoções.
    """

    def __init__(self, db: AsyncIOMotorDatabase):
        """
        Inicializa o repositório.

        Args:
            db: Database Motor (MongoDB async)
        """
        self.db = db
        self.collection = db.model_versions
        logger.info("ModelVersionRepository inicializado")

    async def create(
        self,
        version: str,
        mlflow_run_id: str,
        stage: str,
        f1_score: float,
        accuracy: float,
        precision: float,
        recall: float,
        n_samples: int,
        feature_importance: Optional[dict[str, float]] = None,
        drift_metrics: Optional[dict[str, Any]] = None,
        created_at: Optional[datetime] = None,
        promoted_at: Optional[datetime] = None,
        promoted_by: Optional[str] = None,
        is_active: bool = False,
    ) -> dict[str, Any]:
        """
        Cria novo registro de versão de modelo.

        Args:
            version: Versão do modelo (ex: "v9")
            mlflow_run_id: ID do run MLflow
            stage: Estágio (staging, production, archived)
            f1_score: F1-score do modelo
            accuracy: Acurácia do modelo
            precision: Precisão do modelo
            recall: Recall do modelo
            n_samples: Número de amostras usadas no treino
            feature_importance: Importância das features
            drift_metrics: Métricas de drift (opcional)
            created_at: Data de criação (default: agora)
            promoted_at: Data de promoção (opcional)
            promoted_by: Quem promoveu (system, manual, canary)
            is_active: Se está ativo em produção

        Returns:
            Documento criado
        """
        doc = {
            "version": version,
            "mlflow_run_id": mlflow_run_id,
            "stage": stage,
            "is_active": is_active,
            "f1_score": f1_score,
            "accuracy": accuracy,
            "precision": precision,
            "recall": recall,
            "n_samples": n_samples,
            "feature_importance": feature_importance or {},
            "drift_metrics": drift_metrics or {},
            "created_at": created_at or datetime.now(UTC),
            "promoted_at": promoted_at,
            "promoted_by": promoted_by,
        }

        result = await self.collection.insert_one(doc)
        doc["_id"] = str(result.inserted_id)
        logger.info(f"ModelVersion criado: {version}")
        return doc

    async def get_by_id(self, model_id: str) -> Optional[dict[str, Any]]:
        """
        Busca versão por ID.

        Args:
            model_id: ID do documento MongoDB

        Returns:
            Documento ou None se não encontrado
        """
        doc = await self.collection.find_one({"_id": model_id})
        return doc

    async def get_by_version(self, version: str) -> Optional[dict[str, Any]]:
        """
        Busca versão por número da versão.

        Args:
            version: Versão do modelo (ex: "v9")

        Returns:
            Documento ou None se não encontrado
        """
        doc = await self.collection.find_one({"version": version})
        return doc

    async def get_active_model(self) -> Optional[dict[str, Any]]:
        """
        Busca modelo ativo em produção.

        Returns:
            Documento do modelo ativo ou None
        """
        doc = await self.collection.find_one(
            {"stage": "production", "is_active": True}, sort=[("created_at", -1)]
        )
        return doc

    async def list_models(
        self,
        stage: Optional[str] = None,
        is_active: Optional[bool] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """
        Lista versões de modelos com filtros.

        Args:
            stage: Filtra por estágio
            is_active: Filtra por ativo
            limit: Limite de resultados
            offset: Offset para paginação

        Returns:
            Lista de documentos
        """
        query = {}
        if stage:
            query["stage"] = stage
        if is_active is not None:
            query["is_active"] = is_active

        cursor = self.collection.find(query)
        if offset > 0:
            cursor = cursor.skip(offset)
        if limit > 0:
            cursor = cursor.limit(limit)
        docs = await cursor.to_list(length=limit)
        return docs

    async def update(self, version: str, **kwargs) -> bool:
        """
        Atualiza versão de modelo.

        Args:
            version: Versão do modelo
            **kwargs: Campos a atualizar

        Returns:
            True se atualizou, False se não encontrou
        """
        result = await self.collection.update_one({"version": version}, {"$set": kwargs})
        return result.modified_count > 0

    async def update_drift_metrics(self, version: str, drift_metrics: dict[str, Any]) -> bool:
        """
        Atualiza métricas de drift de um modelo.

        Args:
            version: Versão do modelo
            drift_metrics: Métricas de drift

        Returns:
            True se atualizou, False se não encontrou
        """
        result = await self.collection.update_one(
            {"version": version}, {"$set": {"drift_metrics": drift_metrics}}
        )
        if result.modified_count > 0:
            logger.info(f"Drift metrics atualizadas para {version}")
        return result.modified_count > 0

    async def promote_model(
        self,
        version: str,
        stage: str,
        promoted_at: Optional[datetime] = None,
        promoted_by: str = "manual",
        archive_current: bool = True,
    ) -> bool:
        """
        Promove modelo para estágio específico.

        Args:
            version: Versão do modelo
            stage: Estágio de destino
            promoted_at: Data da promoção
            promoted_by: Quem promoveu
            archive_current: Se True, arquiva modelo atual em production

        Returns:
            True se sucesso, False caso contrário
        """
        # Se promovendo para production, arquivar atual
        if archive_current and stage == "production":
            current = await self.get_active_model()
            if current and current["version"] != version:
                await self.collection.update_one(
                    {"version": current["version"]},
                    {"$set": {"is_active": False, "stage": "archived"}},
                )
                logger.info(f"Modelo {current['version']} arquivado")

        # Promover nova versão
        result = await self.collection.update_one(
            {"version": version},
            {
                "$set": {
                    "stage": stage,
                    "is_active": (stage == "production"),
                    "promoted_at": promoted_at or datetime.now(UTC),
                    "promoted_by": promoted_by,
                }
            },
        )

        if result.modified_count > 0:
            logger.info(f"Modelo {version} promovido para {stage}")
        return result.modified_count > 0

    async def deactivate_model(self, version: str) -> bool:
        """
        Desativa modelo.

        Args:
            version: Versão do modelo

        Returns:
            True se sucesso, False caso contrário
        """
        result = await self.collection.update_one(
            {"version": version}, {"$set": {"is_active": False}}
        )
        return result.modified_count > 0

    async def delete(self, version: str) -> bool:
        """
        Deleta versão de modelo.

        Args:
            version: Versão do modelo

        Returns:
            True se deletou, False se não encontrou
        """
        result = await self.collection.delete_one({"version": version})
        if result.deleted_count > 0:
            logger.info(f"ModelVersion {version} deletado")
        return result.deleted_count > 0

    async def get_model_history(self, limit: int = 10, offset: int = 0) -> list[dict[str, Any]]:
        """
        Busca histórico de versões de modelos.

        Args:
            limit: Limite de resultados
            offset: Offset para paginação

        Returns:
            Lista de versões ordenadas por created_at (antiga primeiro)
        """
        cursor = self.collection.find().sort("created_at", 1)
        if offset > 0:
            cursor = cursor.skip(offset)
        if limit > 0:
            cursor = cursor.limit(limit)
        docs = await cursor.to_list(length=limit)
        return docs

    async def count_models_by_stage(self) -> dict[str, int]:
        """
        Conta modelos por estágio.

        Returns:
            Dicionário com contagem por estágio
        """
        pipeline = [{"$group": {"_id": "$stage", "count": {"$sum": 1}}}]
        cursor = self.collection.aggregate(pipeline)
        docs = await cursor.to_list(length=10)

        return {doc["_id"]: doc["count"] for doc in docs}

    async def get_latest_by_stage(self, stage: str) -> Optional[dict[str, Any]]:
        """
        Busca versão mais recente de um estágio.

        Args:
            stage: Estágio para buscar

        Returns:
            Documento mais recente do estágio ou None
        """
        doc = await self.collection.find_one({"stage": stage}, sort=[("created_at", -1)])
        return doc
