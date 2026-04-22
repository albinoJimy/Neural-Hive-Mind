"""Cliente Neo4j para operações de grafo."""

from typing import Any, Dict, List, Optional

import structlog
from neo4j import AsyncGraphDatabase

from knowledge_graph_rag.config.settings import get_settings

logger = structlog.get_logger()
settings = get_settings()


class Neo4jClient:
    """Cliente para Neo4j."""

    def __init__(
        self,
        uri: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
        database: Optional[str] = None,
    ):
        """Inicializa o cliente Neo4j.

        Args:
            uri: URI de conexão Neo4j
            user: Utilizador
            password: Password
            database: Nome da database
        """
        self.uri = uri or settings.neo4j_uri
        self.user = user or settings.neo4j_user
        self.password = password or settings.neo4j_password
        self.database = database or settings.neo4j_database
        self.driver = None

    async def connect(self):
        """Estabelece conexão com Neo4j."""
        self.driver = AsyncGraphDatabase.driver(self.uri, auth=(self.user, self.password))
        logger.info("neo4j_connected", uri=self.uri)

    async def close(self):
        """Fecha conexão com Neo4j."""
        if self.driver:
            await self.driver.close()
            logger.info("neo4j_closed")

    async def execute_query(
        self, query: str, parameters: Dict[str, Any] = None
    ) -> List[Dict[str, Any]]:
        """Executa query Cypher.

        Args:
            query: Query Cypher
            parameters: Parâmetros da query

        Returns:
            Lista de resultados
        """
        async with self.driver.session(database=self.database) as session:
            result = await session.run(query, parameters or {})
            records = await result.data()
            return [dict(record) for record in records]

    async def find_similar_architectures(
        self, requirements: List[str], limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Encontra arquiteturas similares baseado em requisitos.

        Args:
            requirements: Lista de requisitos
            limit: Limite de resultados

        Returns:
            Lista de arquiteturas similares com scores
        """
        # Construir query para encontrar arquiteturas com componentes similares
        query = """
        MATCH (a:ArchitecturePlan)-[:HAS_COMPONENT]->(c:Component)
        WHERE ANY(req IN $requirements WHERE c.stack CONTAINS req OR c.name CONTAINS req)
        RETURN a.plan_id AS plan_id,
               a.architecture_type AS architecture_type,
               COUNT(DISTINCT c) AS matched_components,
               SIZE((a)-[:HAS_COMPONENT]->()) AS total_components,
               COUNT(DISTINCT c) * 1.0 / SIZE((a)-[:HAS_COMPONENT]->()) AS similarity
        ORDER BY similarity DESC
        LIMIT $limit
        """

        results = await self.execute_query(query, {"requirements": requirements, "limit": limit})

        logger.info("similar_architectures_found", count=len(results))

        return results

    async def get_connections_context(self, node_id: str, depth: int = 2) -> List[Dict[str, Any]]:
        """Obtém contexto de conexões de um nó.

        Args:
            node_id: ID do nó
            depth: Profundidade da busca

        Returns:
            Lista de conexões
        """
        query = (
            """
        MATCH path = (n {id: $node_id})-[*1.."""
            + str(depth)
            + """]-(connected)
        RETURN n.id AS from_id,
               connected.id AS to_id,
               [(n)-[r]-(connected) | type(r)][0] AS connection_type,
               [(n)-[r]-(connected) | r.description][0] AS description
        LIMIT 100
        """
        )

        results = await self.execute_query(query, {"node_id": node_id, "depth": depth})

        return results

    async def get_component_templates(self, component_type: str) -> List[Dict[str, Any]]:
        """Obtém templates para um tipo de componente.

        Args:
            component_type: Tipo do componente

        Returns:
            Lista de templates
        """
        query = """
        MATCH (t:Template)-[:FOR_TYPE]->(type:ComponentType {name: $type})
        RETURN t.id AS template_id,
               t.name AS template_name,
               t.description AS description,
               t.stack AS stack
        """

        results = await self.execute_query(query, {"type": component_type})

        return results

    async def create_architecture_node(
        self, plan_id: str, architecture_type: str, components: List[Dict[str, Any]]
    ) -> str:
        """Cria nó de arquitetura no grafo.

        Args:
            plan_id: ID do plano
            architecture_type: Tipo de arquitetura
            components: Lista de componentes

        Returns:
            ID do nó criado
        """
        query = """
        CREATE (a:ArchitecturePlan {
            plan_id: $plan_id,
            architecture_type: $architecture_type,
            created_at: datetime()
        })
        WITH a
        UNWIND $components AS comp
        CREATE (c:Component {
            id: comp.id,
            name: comp.name,
            stack: comp.stack
        })
        CREATE (a)-[:HAS_COMPONENT]->(c)
        RETURN a.plan_id AS plan_id
        """

        await self.execute_query(
            query,
            {"plan_id": plan_id, "architecture_type": architecture_type, "components": components},
        )

        logger.info("architecture_node_created", plan_id=plan_id)

        return plan_id
