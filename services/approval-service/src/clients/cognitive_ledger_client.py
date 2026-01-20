"""
Cliente para consultar o Ledger Cognitivo (specialist_opinions).

Permite buscar opinion_ids associados a um plan_id para integracao
com o sistema de feedback ML.
"""

import structlog
from typing import List, Dict, Any, Optional
from motor.motor_asyncio import AsyncIOMotorClient

from src.config.settings import Settings

logger = structlog.get_logger()


class CognitiveLedgerClient:
    """Cliente async para consultar ledger cognitivo."""

    def __init__(self, settings: Settings):
        """
        Inicializa cliente do ledger cognitivo.

        Args:
            settings: Configuracoes do approval service
        """
        self.settings = settings
        self.client: Optional[AsyncIOMotorClient] = None
        self.db = None
        self.opinions_collection = None

    async def initialize(self):
        """Inicializa cliente MongoDB para ledger."""
        self.client = AsyncIOMotorClient(
            self.settings.mongodb_uri,
            maxPoolSize=self.settings.mongodb_max_pool_size,
            serverSelectionTimeoutMS=self.settings.mongodb_timeout_ms
        )

        self.db = self.client[self.settings.mongodb_database]
        self.opinions_collection = self.db[self.settings.mongodb_opinions_collection]

        # Verificar conectividade
        await self.client.admin.command('ping')

        logger.info(
            'CognitiveLedgerClient inicializado',
            collection=self.settings.mongodb_opinions_collection
        )

    async def get_opinions_by_plan_id(self, plan_id: str) -> List[Dict[str, Any]]:
        """
        Busca todas as opinioes de specialists para um plan_id.

        Args:
            plan_id: ID do plano cognitivo

        Returns:
            Lista de documentos de opiniao com opinion_id, specialist_type, etc.
        """
        try:
            cursor = self.opinions_collection.find(
                {'plan_id': plan_id},
                {
                    '_id': 0,
                    'opinion_id': 1,
                    'specialist_type': 1,
                    'plan_id': 1,
                    'recommendation': 1,
                    'confidence_score': 1
                }
            )

            opinions = await cursor.to_list(length=None)

            logger.debug(
                'Opinioes recuperadas do ledger',
                plan_id=plan_id,
                count=len(opinions)
            )

            return opinions

        except Exception as e:
            logger.error(
                'Erro ao buscar opinioes do ledger',
                plan_id=plan_id,
                error=str(e)
            )
            raise

    async def close(self):
        """Fecha cliente MongoDB."""
        if self.client:
            self.client.close()
            logger.info('CognitiveLedgerClient fechado')
