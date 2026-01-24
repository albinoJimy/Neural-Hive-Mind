"""
Cliente MongoDB simples para persistência de DLQ no Worker Agents.

Responsável por armazenar tickets falhos para análise forense.
"""
from datetime import datetime
from typing import Optional, Dict, Any

import structlog

logger = structlog.get_logger()


class MongoDBClient:
    """Cliente MongoDB para persistência de tickets DLQ."""

    def __init__(self, config):
        """
        Inicializa o cliente MongoDB.

        Args:
            config: Configurações do worker-agents (WorkerAgentSettings)
        """
        self.config = config
        self.client = None
        self.db = None
        self.dlq_collection = None

    async def initialize(self):
        """Inicializar cliente MongoDB e criar índices."""
        from motor.motor_asyncio import AsyncIOMotorClient

        mongodb_uri = self.config.mongodb_uri
        max_pool_size = getattr(self.config, 'mongodb_max_pool_size', 10)
        server_timeout = getattr(self.config, 'mongodb_server_selection_timeout_ms', 5000)

        self.client = AsyncIOMotorClient(
            mongodb_uri,
            maxPoolSize=max_pool_size,
            serverSelectionTimeoutMS=server_timeout,
            retryWrites=True,
            w='majority'
        )

        self.db = self.client[self.config.mongodb_database]
        self.dlq_collection = self.db[self.config.mongodb_dlq_collection]

        # Criar índices para DLQ
        await self._create_indexes()

        # Verificar conectividade
        await self.client.admin.command('ping')

        logger.info(
            'mongodb_client_initialized',
            database=self.config.mongodb_database,
            collection=self.config.mongodb_dlq_collection
        )

    async def _create_indexes(self):
        """Criar índices necessários para a coleção DLQ."""
        # Índice único para ticket_id
        await self.dlq_collection.create_index('ticket_id')
        await self.dlq_collection.create_index('processed_at')
        await self.dlq_collection.create_index('task_type')
        await self.dlq_collection.create_index([('processed_at', -1)])

        logger.debug('mongodb_dlq_indexes_created')

    async def save_dlq_message(self, dlq_message: Dict[str, Any]) -> bool:
        """
        Persistir mensagem DLQ no MongoDB.

        Args:
            dlq_message: Mensagem DLQ com metadata

        Returns:
            bool: True se persistido com sucesso, False caso contrário
        """
        try:
            document = {
                **dlq_message,
                'processed_at': datetime.now(),
                'processed_at_ms': int(datetime.now().timestamp() * 1000)
            }

            await self.dlq_collection.insert_one(document)

            logger.info(
                'dlq_message_persisted',
                ticket_id=dlq_message.get('ticket_id')
            )
            return True

        except Exception as e:
            logger.error(
                'dlq_persistence_failed',
                ticket_id=dlq_message.get('ticket_id'),
                error=str(e)
            )
            return False

    async def close(self):
        """Fechar cliente MongoDB."""
        if self.client:
            self.client.close()
            logger.info('mongodb_client_closed')
