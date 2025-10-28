"""
Neo4j Client para grafo de conhecimento e dados semânticos

Fornece interface assíncrona ao Neo4j para queries em grafo de conhecimento.
"""

import structlog
from typing import List, Dict, Optional
from neo4j import AsyncGraphDatabase
from tenacity import retry, stop_after_attempt, wait_exponential


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
            'Neo4j client inicializado',
            uri=self.uri,
            database=self.database
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10)
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
                    'Query executada',
                    count=len(records)
                )

                return records

            except Exception as e:
                logger.error(
                    'Erro ao executar query',
                    error=str(e)
                )
                raise

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10)
    )
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
                    'Query de escrita executada',
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
                    'Erro ao executar query de escrita',
                    error=str(e)
                )
                raise

    async def find_node(
        self,
        label: str,
        properties: Dict,
        limit: int = 1
    ) -> List[Dict]:
        """
        Busca nós por label e propriedades

        Args:
            label: Label do nó
            properties: Propriedades para filtrar
            limit: Limite de resultados

        Returns:
            Lista de nós encontrados
        """
        where_clauses = [f"n.{key} = ${key}" for key in properties.keys()]
        where_str = " AND ".join(where_clauses) if where_clauses else "true"

        query = f"""
        MATCH (n:{label})
        WHERE {where_str}
        RETURN n
        LIMIT {limit}
        """

        try:
            results = await self.execute_query(query, properties)
            return [record['n'] for record in results]
        except Exception as e:
            logger.error('Erro ao buscar nó', label=label, error=str(e))
            return []

    async def create_node(self, label: str, properties: Dict) -> Optional[Dict]:
        """
        Cria um nó

        Args:
            label: Label do nó
            properties: Propriedades do nó

        Returns:
            Nó criado ou None
        """
        props_str = ", ".join([f"{key}: ${key}" for key in properties.keys()])
        query = f"CREATE (n:{label} {{{props_str}}}) RETURN n"

        try:
            results = await self.execute_query(query, properties)
            if results:
                logger.debug('Nó criado', label=label)
                return results[0]['n']
            return None
        except Exception as e:
            logger.error('Erro ao criar nó', label=label, error=str(e))
            return None

    async def create_relationship(
        self,
        from_label: str,
        from_properties: Dict,
        to_label: str,
        to_properties: Dict,
        relationship_type: str,
        relationship_properties: Optional[Dict] = None
    ) -> bool:
        """
        Cria relacionamento entre nós

        Args:
            from_label: Label do nó de origem
            from_properties: Propriedades do nó de origem
            to_label: Label do nó de destino
            to_properties: Propriedades do nó de destino
            relationship_type: Tipo do relacionamento
            relationship_properties: Propriedades do relacionamento

        Returns:
            True se criado com sucesso
        """
        from_where = " AND ".join([f"from.{k} = $from_{k}" for k in from_properties.keys()])
        to_where = " AND ".join([f"to.{k} = $to_{k}" for k in to_properties.keys()])

        rel_props = ""
        if relationship_properties:
            props_str = ", ".join([f"{k}: $rel_{k}" for k in relationship_properties.keys()])
            rel_props = f" {{{props_str}}}"

        query = f"""
        MATCH (from:{from_label})
        WHERE {from_where}
        MATCH (to:{to_label})
        WHERE {to_where}
        CREATE (from)-[r:{relationship_type}{rel_props}]->(to)
        RETURN r
        """

        parameters = {}
        for k, v in from_properties.items():
            parameters[f"from_{k}"] = v
        for k, v in to_properties.items():
            parameters[f"to_{k}"] = v
        if relationship_properties:
            for k, v in relationship_properties.items():
                parameters[f"rel_{k}"] = v

        try:
            results = await self.execute_query(query, parameters)
            if results:
                logger.debug('Relacionamento criado', type=relationship_type)
                return True
            return False
        except Exception as e:
            logger.error('Erro ao criar relacionamento', type=relationship_type, error=str(e))
            return False

    async def get_lineage(
        self,
        entity_id: str,
        depth: int = 3,
        direction: str = 'both'
    ) -> List[Dict]:
        """
        Obtém linhagem de dados de uma entidade

        Args:
            entity_id: ID da entidade
            depth: Profundidade da busca
            direction: Direção ('upstream', 'downstream', 'both')

        Returns:
            Lista de nós e relacionamentos na linhagem
        """
        if direction == 'upstream':
            pattern = f"(e)<-[*1..{depth}]-(related)"
        elif direction == 'downstream':
            pattern = f"(e)-[*1..{depth}]->(related)"
        else:  # both
            pattern = f"(e)-[*1..{depth}]-(related)"

        query = f"""
        MATCH {pattern}
        WHERE e.id = $entity_id
        RETURN DISTINCT related
        LIMIT 100
        """

        try:
            results = await self.execute_query(query, {'entity_id': entity_id})
            return [record['related'] for record in results]
        except Exception as e:
            logger.error('Erro ao buscar linhagem', entity_id=entity_id, error=str(e))
            return []

    async def close(self):
        """Fecha conexão com Neo4j"""
        if self.driver:
            await self.driver.close()
            logger.info('Neo4j client fechado')
