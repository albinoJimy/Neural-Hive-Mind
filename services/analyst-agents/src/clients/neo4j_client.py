import structlog
from neo4j import AsyncGraphDatabase
from typing import List, Dict, Optional

logger = structlog.get_logger()


class Neo4jClient:
    def __init__(self, uri: str, user: str, password: str, database: str):
        self.uri = uri
        self.user = user
        self.password = password
        self.database = database
        self.driver = None

    async def initialize(self):
        """Conectar ao Neo4j"""
        try:
            self.driver = AsyncGraphDatabase.driver(self.uri, auth=(self.user, self.password))
            await self.driver.verify_connectivity()
            logger.info('neo4j_client_initialized', uri=self.uri)
        except Exception as e:
            logger.error('neo4j_client_initialization_failed', error=str(e))
            raise

    async def close(self):
        """Fechar conexão"""
        if self.driver:
            await self.driver.close()
            logger.info('neo4j_client_closed')

    async def query_patterns(self, cypher_query: str, parameters: dict = None) -> List[dict]:
        """Executar consulta Cypher customizada"""
        try:
            async with self.driver.session(database=self.database) as session:
                result = await session.run(cypher_query, parameters or {})
                records = await result.data()
                return records
        except Exception as e:
            logger.error('neo4j_query_failed', error=str(e))
            return []

    async def find_related_entities(self, entity_id: str, relationship_type: str = None, depth: int = 2) -> List[dict]:
        """Encontrar entidades relacionadas"""
        rel_filter = f'[:{relationship_type}*1..{depth}]' if relationship_type else f'[*1..{depth}]'
        query = f"""
        MATCH (source {{entity_id: $entity_id}})-{rel_filter}-(related)
        RETURN DISTINCT related
        LIMIT 100
        """
        return await self.query_patterns(query, {'entity_id': entity_id})

    async def analyze_intent_flow(self, intent_id: str) -> List[dict]:
        """Analisar fluxo completo de uma intenção"""
        query = """
        MATCH path = (i:Intent {intent_id: $intent_id})-[:GENERATED]->(p:Plan)
                    -[:RESULTED_IN]->(d:Decision)-[:EXECUTED_AS]->(e:Execution)
        RETURN path
        """
        return await self.query_patterns(query, {'intent_id': intent_id})

    async def find_bottlenecks(self, threshold: float = 1000.0) -> List[dict]:
        """Identificar gargalos no grafo de execução"""
        query = """
        MATCH (n)-[r]->(m)
        WHERE r.duration > $threshold
        RETURN n, r, m
        ORDER BY r.duration DESC
        LIMIT 50
        """
        return await self.query_patterns(query, {'threshold': threshold})

    async def get_entity_centrality(self, entity_type: str, limit: int = 10) -> List[dict]:
        """Calcular centralidade de entidades"""
        query = f"""
        MATCH (n:{entity_type})
        WITH n, size((n)--()) as degree
        RETURN n, degree
        ORDER BY degree DESC
        LIMIT $limit
        """
        return await self.query_patterns(query, {'limit': limit})

    async def find_causal_chains(self, source_entity: str, target_entity: str, max_depth: int = 5) -> List[dict]:
        """Encontrar cadeias causais entre entidades"""
        query = """
        MATCH path = shortestPath(
            (source {entity_id: $source})-[*1..$max_depth]->(target {entity_id: $target})
        )
        RETURN path
        """
        return await self.query_patterns(query, {
            'source': source_entity,
            'target': target_entity,
            'max_depth': max_depth
        })
