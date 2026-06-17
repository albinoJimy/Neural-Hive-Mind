"""Serviço de audit logging para MongoDB (INV-13)."""

import uuid
from datetime import datetime, timezone

import structlog
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ASCENDING, DESCENDING
from pymongo.errors import PyMongoError

from src.config.settings import get_settings

logger = structlog.get_logger(__name__)


class PIIAuditLogger:
    """
    Logger de auditoria para operações PII (INV-13).

    Registra todas as operações de mascaramento/desmascaramento em MongoDB.
    Logs são imutáveis e retidos por 90 dias (TTL index).
    """

    def __init__(self):
        """Inicializa audit logger."""
        settings = get_settings()
        self.enabled = True
        self._client: AsyncIOMotorClient | None = None
        self._collection = None
        self.mongodb_uri = settings.MONGODB_URI
        self.database_name = settings.MONGODB_DATABASE
        self.collection_name = settings.PII_AUDIT_LOG_COLLECTION

    async def initialize(self):
        """Inicializa conexão MongoDB e cria índices."""
        try:
            self._client = AsyncIOMotorClient(self.mongodb_uri)
            db = self._client[self.database_name]
            self._collection = db[self.collection_name]

            # Criar índices
            await self._create_indexes()

            logger.info(
                "pii_audit_logger_initialized",
                collection=self.collection_name,
                database=self.database_name,
            )
        except Exception as e:
            logger.error("pii_audit_logger_init_failed", error=str(e))
            self.enabled = False
            raise

    async def close(self):
        """Fecha conexão MongoDB."""
        if self._client:
            self._client.close()

    async def log_mask_operation(
        self,
        text_hash: str,
        pii_types_found: list[str],
        strategy: str,
        masked_text_hash: str,
        requestor_id: str,
        tenant_id: str | None = None,
        user_id: str | None = None,
        correlation_id: str | None = None,
        mask_id: str | None = None,
    ):
        """
        Registra operação de mascaramento (INV-13).

        Args:
            text_hash: Hash do texto original (SHA-256)
            pii_types_found: Tipos de PII encontrados
            strategy: Estratégia de mascaramento utilizada
            masked_text_hash: Hash do texto mascarado
            requestor_id: ID do solicitante
            tenant_id: ID do tenant (opcional)
            user_id: ID do usuário (opcional)
            correlation_id: ID de correlação (opcional)
            mask_id: ID do mascaramento para unmask reversível (opcional)
        """
        if not self.enabled or not self._collection:
            return

        try:
            document = {
                "audit_id": str(uuid.uuid4()),
                "timestamp": datetime.now(timezone.utc),
                "operation": "mask",
                "text_hash": text_hash,
                "pii_types_found": pii_types_found,
                "strategy": strategy,
                "masked_text_hash": masked_text_hash,
                "requestor_id": requestor_id,
            }

            # Campos opcionais
            if tenant_id:
                document["tenant_id"] = tenant_id
            if user_id:
                document["user_id"] = user_id
            if correlation_id:
                document["correlation_id"] = correlation_id
            if mask_id:
                document["mask_id"] = mask_id

            await self._collection.insert_one(document)

            logger.debug(
                "pii_mask_operation_logged",
                audit_id=document["audit_id"],
                pii_count=len(pii_types_found),
            )
        except PyMongoError as e:
            logger.error("pii_mask_log_failed", error=str(e))

    async def log_unmask_operation(
        self,
        mask_id: str,
        pii_type: str,
        success: bool,
        requestor_id: str,
        tenant_id: str | None = None,
        user_id: str | None = None,
        correlation_id: str | None = None,
        error_message: str | None = None,
    ):
        """
        Registra operação de desmascaramento (INV-13).

        Args:
            mask_id: ID do mascaramento
            pii_type: Tipo de PII
            success: Se operação foi bem-sucedida
            requestor_id: ID do solicitante
            tenant_id: ID do tenant (opcional)
            user_id: ID do usuário (opcional)
            correlation_id: ID de correlação (opcional)
            error_message: Mensagem de erro (se falhou)
        """
        if not self.enabled or not self._collection:
            return

        try:
            document = {
                "audit_id": str(uuid.uuid4()),
                "timestamp": datetime.now(timezone.utc),
                "operation": "unmask",
                "mask_id": mask_id,
                "pii_type": pii_type,
                "success": success,
                "requestor_id": requestor_id,
            }

            # Campos opcionais
            if tenant_id:
                document["tenant_id"] = tenant_id
            if user_id:
                document["user_id"] = user_id
            if correlation_id:
                document["correlation_id"] = correlation_id
            if error_message:
                document["error_message"] = error_message

            await self._collection.insert_one(document)

            logger.debug(
                "pii_unmask_operation_logged",
                audit_id=document["audit_id"],
                success=success,
            )
        except PyMongoError as e:
            logger.error("pii_unmask_log_failed", error=str(e))

    async def log_detect_operation(
        self,
        text_hash: str,
        pii_types_found: list[str],
        requestor_id: str,
        tenant_id: str | None = None,
        user_id: str | None = None,
        correlation_id: str | None = None,
    ):
        """
        Registra operação de detecção (INV-13).

        Args:
            text_hash: Hash do texto analisado
            pii_types_found: Tipos de PII encontrados
            requestor_id: ID do solicitante
            tenant_id: ID do tenant (opcional)
            user_id: ID do usuário (opcional)
            correlation_id: ID de correlação (opcional)
        """
        if not self.enabled or not self._collection:
            return

        try:
            document = {
                "audit_id": str(uuid.uuid4()),
                "timestamp": datetime.now(timezone.utc),
                "operation": "detect",
                "text_hash": text_hash,
                "pii_types_found": pii_types_found,
                "requestor_id": requestor_id,
            }

            # Campos opcionais
            if tenant_id:
                document["tenant_id"] = tenant_id
            if user_id:
                document["user_id"] = user_id
            if correlation_id:
                document["correlation_id"] = correlation_id

            await self._collection.insert_one(document)

            logger.debug(
                "pii_detect_operation_logged",
                audit_id=document["audit_id"],
                pii_count=len(pii_types_found),
            )
        except PyMongoError as e:
            logger.error("pii_detect_log_failed", error=str(e))

    async def _create_indexes(self):
        """Cria índices otimizados para collection de audit log."""
        if self._collection is None:
            return

        settings = get_settings()
        ttl_seconds = settings.AUDIT_LOG_RETENTION_DAYS * 24 * 3600

        indexes = [
            # Timestamp para queries temporais e TTL
            [("timestamp", DESCENDING)],
            # Operation type para filtros
            [("operation", ASCENDING), ("timestamp", DESCENDING)],
            # Requestor para auditoria por usuário
            [("requestor_id", ASCENDING), ("timestamp", DESCENDING)],
            # Tenant para multi-tenancy
            [("tenant_id", ASCENDING), ("timestamp", DESCENDING)],
            # Mask ID para tracking de unmask
            [("mask_id", ASCENDING)],
            # Correlation ID para tracing
            [("correlation_id", ASCENDING)],
        ]

        # TTL index para retenção automática (90 dias)
        ttl_index = [("timestamp", ASCENDING)]

        for index_def in indexes:
            try:
                await self._collection.create_index(index_def)
            except Exception as e:
                logger.warning("index_creation_failed", index=str(index_def), error=str(e))

        # Criar TTL index
        try:
            await self._collection.create_index(ttl_index, expireAfterSeconds=ttl_seconds)
            logger.info("ttl_index_created", ttl_seconds=ttl_seconds)
        except Exception as e:
            logger.warning("ttl_index_creation_failed", error=str(e))

    async def get_audit_summary(
        self,
        start_date: datetime,
        end_date: datetime,
        tenant_id: str | None = None,
    ) -> dict:
        """
        Retorna resumo de auditoria para período.

        Args:
            start_date: Data inicial
            end_date: Data final
            tenant_id: Filtro por tenant (opcional)

        Returns:
            Estatísticas de auditoria
        """
        if not self.enabled or not self._collection:
            return {}

        try:
            match_filter = {
                "timestamp": {"$gte": start_date, "$lte": end_date},
            }

            if tenant_id:
                match_filter["tenant_id"] = tenant_id

            pipeline = [
                {"$match": match_filter},
                {"$group": {"_id": "$operation", "count": {"$sum": 1}}},
            ]

            results = await self._collection.aggregate(pipeline).to_list(length=100)

            summary = {
                "period": {
                    "start": start_date.isoformat(),
                    "end": end_date.isoformat(),
                },
                "operations_by_type": {r["_id"]: r["count"] for r in results},
                "total_operations": sum(r["count"] for r in results),
            }

            return summary
        except PyMongoError as e:
            logger.error("audit_summary_failed", error=str(e))
            return {}


# Singleton
_audit_logger: PIIAuditLogger | None = None


def get_audit_logger() -> PIIAuditLogger:
    """Retorna instância singleton do audit logger."""
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = PIIAuditLogger()
    return _audit_logger
