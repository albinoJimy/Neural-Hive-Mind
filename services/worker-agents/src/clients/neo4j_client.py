"""
Neo4j Client para queries de grafo no Worker Agents.

Fornece interface assíncrona ao Neo4j para queries em grafo de conhecimento.
Reutilizado de memory-layer-api para compatibilidade.
"""
import structlog
from typing import List, Dict, Optional


logger = structlog.get_logger()


class Neo4jClient:
    """Cliente Neo4j assíncrono para operações em grafo de conhecimento"""

    def __init__(
        self,
        uri: str,
        user: str,
        password: str,
        database: str = 'neo4j',
        max_connection_pool_size: int = 50,
        connection_timeout: int = 30,
        encrypted: bool = False
    ):
        """
        Inicializa o cliente Neo4j

        Args:
            uri: URI de conexão do Neo4j
            user: Usuário do Neo4j
            password: Senha do Neo4j
            database: Nome do banco de dados
            max_connection_pool_size: Tamanho máximo do pool
            connection_timeout: Timeout de conexão em segundos
            encrypted: Se True, usa conexão criptografada
        """
        self.uri = uri
        self.user = user
        self.password = password
        self.database = database
        self.max_connection_pool_size = max_connection_pool_size
        self.connection_timeout = connection_timeout
        self.encrypted = encrypted
        self.driver = None

    async def initialize(self):
        """Inicializa o driver Neo4j com pool de conexões"""
        from neo4j import AsyncGraphDatabase

        self.driver = AsyncGraphDatabase.driver(
            self.uri,
            auth=(self.user, self.password),
            max_connection_pool_size=self.max_connection_pool_size,
            connection_timeout=self.connection_timeout,
            encrypted=self.encrypted
        )

        # Verifica conectividade
        await self.driver.verify_connectivity()

        logger.info(
            'neo4j_client_initialized',
            uri=self.uri,
            database=self.database
        )

    async def execute_query(
        self,
        query: str,
        parameters: Optional[Dict] = None,
        timeout: Optional[float] = None
    ) -> List[Dict]:
        """
        Executa query Cypher

        Args:
            query: Query Cypher a executar
            parameters: Parâmetros da query
            timeout: Timeout em segundos

        Returns:
            Lista de resultados
        """
        if parameters is None:
            parameters = {}

        async with self.driver.session(database=self.database) as session:
            try:
                result = await session.run(query, parameters, timeout=timeout)
                records = await result.data()

                logger.debug(
                    'neo4j_query_executed',
                    count=len(records)
                )

                return records

            except Exception as e:
                logger.error(
                    'neo4j_query_error',
                    error=str(e)
                )
                raise

    async def execute_write(
        self,
        query: str,
        parameters: Optional[Dict] = None
    ) -> Dict:
        """
        Executa query de escrita

        Args:
            query: Query Cypher de escrita
            parameters: Parâmetros da query

        Returns:
            Resultado da escrita
        """
        if parameters is None:
            parameters = {}

        async with self.driver.session(database=self.database) as session:
            try:
                result = await session.run(query, parameters)
                summary = await result.consume()

                logger.debug(
                    'neo4j_write_executed',
                    nodes_created=summary.counters.nodes_created,
                    relationships_created=summary.counters.relationships_created
                )

                return {
                    'nodes_created': summary.counters.nodes_created,
                    'nodes_deleted': summary.counters.nodes_deleted,
                    'relationships_created': summary.counters.relationships_created,
                    'relationships_deleted': summary.counters.relationships_deleted,
                    'properties_set': summary.counters.properties_set
                }

            except Exception as e:
                logger.error(
                    'neo4j_write_error',
                    error=str(e)
                )
                raise

    async def close(self):
        """Fecha conexão com Neo4j"""
        if self.driver:
            await self.driver.close()
            logger.info('neo4j_client_closed')
