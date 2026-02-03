"""Cliente MongoDB para audit trail de tickets."""
import asyncio
import logging
from typing import Optional, List, Dict
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection
from datetime import datetime

from ..config.settings import TicketServiceSettings
from ..models import ExecutionTicket

logger = logging.getLogger(__name__)


class MongoDBClient:
    """Cliente MongoDB para audit trail e histórico."""

    def __init__(self, settings: TicketServiceSettings):
        """Inicializa cliente MongoDB."""
        self.settings = settings
        self.client: Optional[AsyncIOMotorClient] = None
        self.db = None
        self.tickets_collection: Optional[AsyncIOMotorCollection] = None
        self.audit_collection: Optional[AsyncIOMotorCollection] = None

    async def start(self, max_retries: int = 5, initial_delay: float = 1.0):
        """Estabelece conexão com MongoDB com retry logic.

        Args:
            max_retries: Número máximo de tentativas de conexão
            initial_delay: Delay inicial entre retries (exponential backoff)
        """
        for attempt in range(max_retries):
            try:
                logger.info(
                    "connecting_to_mongodb",
                    extra={
                        "uri": self.settings.mongodb_uri.split('@')[-1] if '@' in self.settings.mongodb_uri else self.settings.mongodb_uri,
                        "database": self.settings.mongodb_database,
                        "attempt": attempt + 1,
                        "max_retries": max_retries
                    }
                )

                await self._connect_internal()

                logger.info("mongodb_connected", extra={"database": self.settings.mongodb_database})
                return

            except Exception as e:
                delay = initial_delay * (2 ** attempt)  # Exponential backoff
                logger.warning(
                    "mongodb_connection_failed",
                    extra={
                        "error": str(e),
                        "attempt": attempt + 1,
                        "max_retries": max_retries,
                        "retry_in_seconds": delay
                    }
                )

                if attempt < max_retries - 1:
                    await asyncio.sleep(delay)
                else:
                    logger.error("mongodb_connection_exhausted_retries", extra={"max_retries": max_retries})
                    raise

    async def connect(self):
        """Estabelece conexão com MongoDB (backward compatibility)."""
        await self.start()

    async def _connect_internal(self):
        """Método interno de conexão."""
        self.client = AsyncIOMotorClient(
            self.settings.mongodb_uri,
            maxPoolSize=100,
            serverSelectionTimeoutMS=5000,
            retryWrites=True,
            w='majority'
        )

        self.db = self.client[self.settings.mongodb_database]
        self.tickets_collection = self.db[self.settings.mongodb_collection_tickets]
        self.audit_collection = self.db[self.settings.mongodb_collection_audit]

        # Criar índices (em background para não bloquear)
        await self._create_indexes()

        # Ping para verificar
        await self.client.admin.command('ping')

    async def _create_indexes(self):
        """Cria índices necessários de forma não-bloqueante."""
        # Índices para tickets (background=True evita bloqueio durante startup)
        await self.tickets_collection.create_index('ticket_id', unique=True, background=True)
        await self.tickets_collection.create_index('plan_id', background=True)
        await self.tickets_collection.create_index('intent_id', background=True)
        await self.tickets_collection.create_index('status', background=True)
        await self.tickets_collection.create_index([('status', 1), ('created_at', -1)], background=True)

        # Índices para audit log
        await self.audit_collection.create_index('ticket_id', background=True)
        await self.audit_collection.create_index('timestamp', background=True)
        await self.audit_collection.create_index([('ticket_id', 1), ('timestamp', -1)], background=True)

        logger.info("mongodb_indexes_created")

    async def disconnect(self):
        """Fecha conexão."""
        if self.client:
            self.client.close()
            logger.info("MongoDB client disconnected")

    async def health_check(self) -> bool:
        """Verifica saúde da conexão."""
        try:
            await self.client.admin.command('ping')
            return True
        except Exception as e:
            logger.error(f"MongoDB health check failed: {e}")
            return False

    async def save_ticket_audit(self, ticket: ExecutionTicket):
        """Salva snapshot completo do ticket para auditoria."""
        document = ticket.to_avro_dict()
        document['_audit_timestamp'] = datetime.utcnow()

        await self.tickets_collection.update_one(
            {'ticket_id': ticket.ticket_id},
            {'$set': document},
            upsert=True
        )
        logger.debug(f"Ticket audit saved", extra={"ticket_id": ticket.ticket_id})

    async def log_status_change(
        self,
        ticket_id: str,
        old_status: str,
        new_status: str,
        changed_by: str,
        metadata: dict
    ):
        """Registra mudança de status no audit log."""
        log_entry = {
            'ticket_id': ticket_id,
            'old_status': old_status,
            'new_status': new_status,
            'changed_by': changed_by,
            'timestamp': datetime.utcnow(),
            'metadata': metadata
        }

        await self.audit_collection.insert_one(log_entry)
        logger.debug(f"Status change logged", extra={"ticket_id": ticket_id, "status": f"{old_status}->{new_status}"})

    async def get_ticket_history(self, ticket_id: str) -> List[dict]:
        """Obtém histórico completo de um ticket."""
        cursor = self.audit_collection.find(
            {'ticket_id': ticket_id}
        ).sort('timestamp', -1)

        return await cursor.to_list(length=None)

    async def get_ticket_stats_by_status(self) -> dict:
        """Estatísticas agregadas por status."""
        pipeline = [
            {'$group': {
                '_id': '$status',
                'count': {'$sum': 1}
            }}
        ]

        results = await self.tickets_collection.aggregate(pipeline).to_list(length=None)
        return {item['_id']: item['count'] for item in results}


# Singleton instance
_mongodb_client: Optional[MongoDBClient] = None


async def get_mongodb_client(auto_connect: bool = False) -> MongoDBClient:
    """Retorna singleton do MongoDB client.

    Args:
        auto_connect: Se True, conecta automaticamente (para compatibilidade).
                     Se False, retorna cliente sem conectar (padrão).
    """
    global _mongodb_client
    if _mongodb_client is None:
        from ..config import get_settings
        settings = get_settings()
        _mongodb_client = MongoDBClient(settings)
        if auto_connect:
            await _mongodb_client.connect()
    return _mongodb_client
