"""
Neo4j Client for Knowledge Graph queries

Provides async interface to Neo4j for semantic enrichment and historical context.
"""

import structlog
from typing import List, Dict, Optional
from neo4j import AsyncGraphDatabase
from tenacity import retry, stop_after_attempt, wait_exponential

from src.config.settings import Settings

logger = structlog.get_logger()


class Neo4jClient:
    """Async Neo4j client for Knowledge Graph operations"""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.driver = None

    async def initialize(self):
        """Initialize Neo4j driver with connection pool"""
        self.driver = AsyncGraphDatabase.driver(
            self.settings.neo4j_uri,
            auth=(self.settings.neo4j_user, self.settings.neo4j_password),
            max_connection_pool_size=self.settings.neo4j_max_connection_pool_size,
            connection_timeout=self.settings.neo4j_connection_timeout,
            encrypted=self.settings.environment == 'production'
        )

        # Verify connectivity
        await self.driver.verify_connectivity()

        logger.info(
            'Neo4j client inicializado',
            uri=self.settings.neo4j_uri,
            database=self.settings.neo4j_database
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10)
    )
    async def query_similar_intents(
        self,
        intent_text: str,
        domain: str,
        limit: int = 5
    ) -> List[Dict]:
        """
        Query for similar intents in historical data

        Args:
            intent_text: Intent text to search for
            domain: Intent domain
            limit: Maximum number of results

        Returns:
            List of similar intent records
        """
        keywords = self._extract_keywords(intent_text)

        query = '''
        MATCH (i:Intent {domain: $domain})
        WHERE i.text CONTAINS $keywords
        RETURN i.id AS id, i.text AS text, i.outcome AS outcome,
               i.timestamp AS timestamp
        ORDER BY i.timestamp DESC
        LIMIT $limit
        '''

        async with self.driver.session(
            database=self.settings.neo4j_database
        ) as session:
            try:
                result = await session.run(
                    query,
                    domain=domain,
                    keywords=keywords,
                    limit=limit,
                    timeout=self.settings.neo4j_query_timeout / 1000.0
                )
                records = await result.data()

                logger.debug(
                    'Similar intents queried',
                    domain=domain,
                    count=len(records)
                )

                return records

            except Exception as e:
                logger.error(
                    'Error querying similar intents',
                    domain=domain,
                    error=str(e)
                )
                return []

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10)
    )
    async def query_ontology(self, entity_type: str) -> Dict:
        """
        Query ontology for entity type definition

        Args:
            entity_type: Type of entity

        Returns:
            Ontology definition
        """
        query = '''
        MATCH (o:Ontology {type: $entity_type})
        RETURN o.canonical_type AS canonical_type,
               o.properties AS properties,
               o.constraints AS constraints
        LIMIT 1
        '''

        async with self.driver.session(
            database=self.settings.neo4j_database
        ) as session:
            try:
                result = await session.run(
                    query,
                    entity_type=entity_type,
                    timeout=self.settings.neo4j_query_timeout / 1000.0
                )
                record = await result.single()

                if record:
                    return {
                        'canonical_type': record['canonical_type'],
                        'properties': record['properties'] or {},
                        'constraints': record['constraints'] or {}
                    }
                else:
                    # Return default if not found
                    return {
                        'canonical_type': entity_type,
                        'properties': {},
                        'constraints': {}
                    }

            except Exception as e:
                logger.error(
                    'Error querying ontology',
                    entity_type=entity_type,
                    error=str(e)
                )
                return {
                    'canonical_type': entity_type,
                    'properties': {},
                    'constraints': {}
                }

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10)
    )
    async def query_causal_relationships(self, intent_id: str) -> List[Dict]:
        """
        Query causal relationships for an intent

        Args:
            intent_id: Intent identifier

        Returns:
            List of causal relationships
        """
        query = '''
        MATCH (i:Intent {id: $intent_id})-[r:CAUSES|DEPENDS_ON]->(related)
        RETURN type(r) AS relationship_type,
               related.id AS related_id,
               related.type AS related_type
        LIMIT 20
        '''

        async with self.driver.session(
            database=self.settings.neo4j_database
        ) as session:
            try:
                result = await session.run(
                    query,
                    intent_id=intent_id,
                    timeout=self.settings.neo4j_query_timeout / 1000.0
                )
                records = await result.data()

                logger.debug(
                    'Causal relationships queried',
                    intent_id=intent_id,
                    count=len(records)
                )

                return records

            except Exception as e:
                logger.error(
                    'Error querying causal relationships',
                    intent_id=intent_id,
                    error=str(e)
                )
                return []

    def _extract_keywords(self, text: str) -> str:
        """
        Extract keywords from text for search

        Args:
            text: Input text

        Returns:
            Space-separated keywords
        """
        # Simple keyword extraction (MVP)
        # TODO: Use NLP for better extraction
        words = text.lower().split()

        # Filter out common stop words
        stop_words = {'o', 'a', 'de', 'para', 'com', 'em', 'um', 'uma'}
        keywords = [w for w in words if w not in stop_words and len(w) > 2]

        return ' '.join(keywords[:5])  # Top 5 keywords

    async def close(self):
        """Close Neo4j driver"""
        if self.driver:
            await self.driver.close()
            logger.info('Neo4j client fechado')
