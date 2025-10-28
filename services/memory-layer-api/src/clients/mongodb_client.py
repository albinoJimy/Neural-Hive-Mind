"""
MongoDB Client para contexto operacional e dados de médio prazo

Fornece interface assíncrona ao MongoDB para armazenamento de contexto e ledger.
"""

import structlog
from datetime import datetime, timedelta
from typing import Dict, Optional, List, Any
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import DuplicateKeyError


logger = structlog.get_logger()


class MongoDBClient:
    """Cliente MongoDB assíncrono para operações de contexto e armazenamento"""

    def __init__(self, uri: str, database: str, max_pool_size: int = 50, timeout_ms: int = 5000):
        """
        Inicializa o cliente MongoDB

        Args:
            uri: URI de conexão do MongoDB
            database: Nome do banco de dados
            max_pool_size: Tamanho máximo do pool de conexões
            timeout_ms: Timeout em milissegundos
        """
        self.uri = uri
        self.database_name = database
        self.max_pool_size = max_pool_size
        self.timeout_ms = timeout_ms
        self.client: Optional[AsyncIOMotorClient] = None
        self.db = None

    async def initialize(self):
        """Inicializa o cliente MongoDB"""
        self.client = AsyncIOMotorClient(
            self.uri,
            maxPoolSize=self.max_pool_size,
            serverSelectionTimeoutMS=self.timeout_ms,
            retryWrites=True,
            w='majority'  # Write concern para durabilidade
        )

        self.db = self.client[self.database_name]

        # Verifica conectividade
        await self.client.admin.command('ping')

        logger.info(
            'MongoDB client inicializado',
            uri=self.uri,
            database=self.database_name
        )

    async def find_one(self, collection: str, filter: Dict) -> Optional[Dict]:
        """
        Busca um documento

        Args:
            collection: Nome da coleção
            filter: Filtro de busca

        Returns:
            Documento encontrado ou None
        """
        try:
            return await self.db[collection].find_one(filter)
        except Exception as e:
            logger.error('Erro ao buscar documento', collection=collection, error=str(e))
            return None

    async def find(
        self,
        collection: str,
        filter: Dict,
        limit: int = 100,
        skip: int = 0,
        sort: Optional[List[tuple]] = None
    ) -> List[Dict]:
        """
        Busca múltiplos documentos

        Args:
            collection: Nome da coleção
            filter: Filtro de busca
            limit: Limite de resultados
            skip: Número de documentos a pular
            sort: Lista de tuplas (campo, direção) para ordenação

        Returns:
            Lista de documentos
        """
        try:
            cursor = self.db[collection].find(filter).limit(limit).skip(skip)
            if sort:
                cursor = cursor.sort(sort)
            return await cursor.to_list(length=limit)
        except Exception as e:
            logger.error('Erro ao buscar documentos', collection=collection, error=str(e))
            return []

    async def insert_one(self, collection: str, document: Dict) -> Optional[str]:
        """
        Insere um documento

        Args:
            collection: Nome da coleção
            document: Documento a inserir

        Returns:
            ID do documento inserido ou None
        """
        try:
            result = await self.db[collection].insert_one(document)
            logger.debug('Documento inserido', collection=collection, id=str(result.inserted_id))
            return str(result.inserted_id)
        except Exception as e:
            logger.error('Erro ao inserir documento', collection=collection, error=str(e))
            return None

    async def insert_many(self, collection: str, documents: List[Dict]) -> int:
        """
        Insere múltiplos documentos

        Args:
            collection: Nome da coleção
            documents: Lista de documentos a inserir

        Returns:
            Número de documentos inseridos
        """
        try:
            result = await self.db[collection].insert_many(documents)
            count = len(result.inserted_ids)
            logger.debug('Documentos inseridos', collection=collection, count=count)
            return count
        except Exception as e:
            logger.error('Erro ao inserir documentos', collection=collection, error=str(e))
            return 0

    async def update_one(
        self,
        collection: str,
        filter: Dict,
        update: Dict,
        upsert: bool = False
    ) -> bool:
        """
        Atualiza um documento

        Args:
            collection: Nome da coleção
            filter: Filtro para encontrar o documento
            update: Operações de atualização
            upsert: Se True, insere se não existir

        Returns:
            True se atualizado com sucesso
        """
        try:
            result = await self.db[collection].update_one(filter, update, upsert=upsert)
            logger.debug(
                'Documento atualizado',
                collection=collection,
                matched=result.matched_count,
                modified=result.modified_count
            )
            return result.modified_count > 0 or (upsert and result.upserted_id is not None)
        except Exception as e:
            logger.error('Erro ao atualizar documento', collection=collection, error=str(e))
            return False

    async def update_many(
        self,
        collection: str,
        filter: Dict,
        update: Dict
    ) -> int:
        """
        Atualiza múltiplos documentos

        Args:
            collection: Nome da coleção
            filter: Filtro para encontrar documentos
            update: Operações de atualização

        Returns:
            Número de documentos modificados
        """
        try:
            result = await self.db[collection].update_many(filter, update)
            logger.debug('Documentos atualizados', collection=collection, count=result.modified_count)
            return result.modified_count
        except Exception as e:
            logger.error('Erro ao atualizar documentos', collection=collection, error=str(e))
            return 0

    async def delete_one(self, collection: str, filter: Dict) -> bool:
        """
        Remove um documento

        Args:
            collection: Nome da coleção
            filter: Filtro para encontrar o documento

        Returns:
            True se removido com sucesso
        """
        try:
            result = await self.db[collection].delete_one(filter)
            logger.debug('Documento removido', collection=collection, count=result.deleted_count)
            return result.deleted_count > 0
        except Exception as e:
            logger.error('Erro ao remover documento', collection=collection, error=str(e))
            return False

    async def delete_many(self, collection: str, filter: Dict) -> int:
        """
        Remove múltiplos documentos

        Args:
            collection: Nome da coleção
            filter: Filtro para encontrar documentos

        Returns:
            Número de documentos removidos
        """
        try:
            result = await self.db[collection].delete_many(filter)
            logger.debug('Documentos removidos', collection=collection, count=result.deleted_count)
            return result.deleted_count
        except Exception as e:
            logger.error('Erro ao remover documentos', collection=collection, error=str(e))
            return 0

    async def count_documents(self, collection: str, filter: Dict) -> int:
        """
        Conta documentos que correspondem ao filtro

        Args:
            collection: Nome da coleção
            filter: Filtro de contagem

        Returns:
            Número de documentos
        """
        try:
            return await self.db[collection].count_documents(filter)
        except Exception as e:
            logger.error('Erro ao contar documentos', collection=collection, error=str(e))
            return 0

    async def aggregate(self, collection: str, pipeline: List[Dict]) -> List[Dict]:
        """
        Executa pipeline de agregação

        Args:
            collection: Nome da coleção
            pipeline: Pipeline de agregação

        Returns:
            Resultados da agregação
        """
        try:
            cursor = self.db[collection].aggregate(pipeline)
            return await cursor.to_list(length=None)
        except Exception as e:
            logger.error('Erro na agregação', collection=collection, error=str(e))
            return []

    async def create_index(self, collection: str, keys: List[tuple], unique: bool = False):
        """
        Cria índice na coleção

        Args:
            collection: Nome da coleção
            keys: Lista de tuplas (campo, direção)
            unique: Se True, cria índice único
        """
        try:
            await self.db[collection].create_index(keys, unique=unique)
            logger.debug('Índice criado', collection=collection, keys=keys, unique=unique)
        except Exception as e:
            logger.error('Erro ao criar índice', collection=collection, error=str(e))

    async def close(self):
        """Fecha conexão com MongoDB"""
        if self.client:
            self.client.close()
            logger.info('MongoDB client fechado')
