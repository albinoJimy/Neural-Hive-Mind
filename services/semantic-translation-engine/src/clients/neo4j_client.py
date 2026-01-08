"""
Neo4j Client for Knowledge Graph queries

Provides async interface to Neo4j for semantic enrichment and historical context.
"""

import structlog
from typing import List, Dict, Optional, TYPE_CHECKING
from neo4j import AsyncGraphDatabase
from tenacity import retry, stop_after_attempt, wait_exponential

from src.config.settings import Settings

if TYPE_CHECKING:
    from src.services.nlp_processor import NLPProcessor

logger = structlog.get_logger()


class Neo4jClient:
    """Async Neo4j client for Knowledge Graph operations"""

    def __init__(
        self,
        settings: Settings,
        nlp_processor: Optional['NLPProcessor'] = None
    ):
        self.settings = settings
        self.driver = None
        self.nlp_processor = nlp_processor

    async def initialize(self):
        """Initialize Neo4j driver with connection pool"""
        logger.info(
            'Tentando conectar ao Neo4j',
            uri=self.settings.neo4j_uri,
            database=self.settings.neo4j_database,
            pool_size=self.settings.neo4j_max_connection_pool_size,
            timeout=self.settings.neo4j_connection_timeout
        )

        self.driver = AsyncGraphDatabase.driver(
            self.settings.neo4j_uri,
            auth=(self.settings.neo4j_user, self.settings.neo4j_password),
            max_connection_pool_size=self.settings.neo4j_max_connection_pool_size,
            connection_timeout=self.settings.neo4j_connection_timeout,
            encrypted=self.settings.environment == 'production'
        )

        # Verify connectivity
        try:
            await self.driver.verify_connectivity()
            logger.info(
                'Neo4j client inicializado com sucesso',
                uri=self.settings.neo4j_uri,
                database=self.settings.neo4j_database,
                pool_size=self.settings.neo4j_max_connection_pool_size,
                timeout=self.settings.neo4j_connection_timeout
            )
        except Exception as e:
            logger.error(
                'Falha ao verificar conectividade Neo4j',
                uri=self.settings.neo4j_uri,
                timeout=self.settings.neo4j_connection_timeout,
                error=str(e),
                error_type=type(e).__name__
            )
            raise

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
        import time
        keywords = await self._extract_keywords_async(intent_text)

        logger.debug(
            'Buscando similar intents no Neo4j',
            intent_text_preview=intent_text[:100] if intent_text else '',
            domain=domain,
            limit=limit,
            keywords=keywords
        )

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
                start_time = time.time()
                result = await session.run(
                    query,
                    domain=domain,
                    keywords=keywords,
                    limit=limit,
                    timeout=self.settings.neo4j_query_timeout / 1000.0
                )
                records = await result.data()
                duration_ms = (time.time() - start_time) * 1000

                logger.debug(
                    'Similar intents queried',
                    domain=domain,
                    count=len(records),
                    keywords=keywords,
                    duration_ms=round(duration_ms, 2),
                    empty_result=len(records) == 0
                )

                return records

            except Exception as e:
                logger.error(
                    'Error querying similar intents',
                    domain=domain,
                    keywords=keywords,
                    error=str(e),
                    error_type=type(e).__name__,
                    sugestao='Verifique conectividade com Neo4j e se existem Intent nodes'
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
        logger.debug(
            'Buscando ontologia no Neo4j',
            entity_type=entity_type
        )

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
                    logger.debug(
                        'Ontologia não encontrada no Neo4j - usando default',
                        entity_type=entity_type
                    )
                    return {
                        'canonical_type': entity_type,
                        'properties': {},
                        'constraints': {}
                    }

            except Exception as e:
                logger.error(
                    'Error querying ontology',
                    entity_type=entity_type,
                    error=str(e),
                    error_type=type(e).__name__
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
        logger.debug(
            'Buscando relacionamentos causais no Neo4j',
            intent_id=intent_id
        )

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
                    error=str(e),
                    error_type=type(e).__name__
                )
                return []

    async def persist_intent_to_graph(
        self,
        intent_envelope: Dict,
        cognitive_plan_id: str,
        outcome: str
    ) -> bool:
        """
        Persiste intent no grafo de conhecimento Neo4j (best-effort)

        Esta operação é opcional e não deve bloquear o fluxo principal.
        Não usa @retry pois exceções são capturadas e convertidas em False,
        e o orquestrador já trata falhas de forma graceful.

        Args:
            intent_envelope: Dict do Intent Envelope
            cognitive_plan_id: ID do plano cognitivo gerado
            outcome: Resultado do processamento ('success' ou 'error')

        Returns:
            True se persistido com sucesso, False em caso de erro
        """
        intent_id = intent_envelope.get('id')
        intent = intent_envelope.get('intent', {})
        text = self._sanitize_text_for_cypher(intent.get('text', ''))
        domain = intent.get('domain', 'unknown')
        confidence = intent_envelope.get('confidence', 0.0)
        timestamp = intent_envelope.get('timestamp')
        entities = intent.get('entities', [])
        keywords = await self._extract_keywords_async(intent.get('text', ''))

        logger.debug(
            'Persistindo intent no grafo Neo4j',
            intent_id=intent_id,
            domain=domain,
            plan_id=cognitive_plan_id,
            num_entities=len(entities)
        )

        # Query para criar/atualizar Intent node
        query = '''
        MERGE (i:Intent {id: $intent_id})
        SET i.text = $text,
            i.domain = $domain,
            i.confidence = $confidence,
            i.timestamp = $timestamp,
            i.outcome = $outcome,
            i.plan_id = $plan_id,
            i.keywords = $keywords,
            i.updated_at = datetime()
        RETURN i.id AS id
        '''

        async with self.driver.session(
            database=self.settings.neo4j_database
        ) as session:
            try:
                result = await session.run(
                    query,
                    intent_id=intent_id,
                    text=text,
                    domain=domain,
                    confidence=confidence,
                    timestamp=timestamp,
                    outcome=outcome,
                    plan_id=cognitive_plan_id,
                    keywords=keywords,
                    timeout=self.settings.neo4j_query_timeout / 1000.0
                )
                await result.consume()

                # Persistir entities se existirem
                if entities:
                    await self._persist_intent_entities(session, intent_id, entities)

                logger.info(
                    'Intent persistido no grafo Neo4j',
                    intent_id=intent_id,
                    domain=domain,
                    num_entities=len(entities),
                    keywords=keywords
                )

                return True

            except Exception as e:
                logger.error(
                    'Erro ao persistir intent no Neo4j',
                    intent_id=intent_id,
                    error=str(e),
                    error_type=type(e).__name__
                )
                return False

    async def _persist_intent_entities(
        self,
        session,
        intent_id: str,
        entities: List[Dict]
    ):
        """
        Persiste entities do intent e cria relacionamentos

        Args:
            session: Neo4j session
            intent_id: ID do intent
            entities: Lista de entities do intent
        """
        query = '''
        MATCH (i:Intent {id: $intent_id})
        MERGE (e:Entity {type: $entity_type, value: $entity_value})
        MERGE (i)-[:CONTAINS]->(e)
        '''

        for entity in entities:
            try:
                await session.run(
                    query,
                    intent_id=intent_id,
                    entity_type=entity.get('type', 'unknown'),
                    entity_value=self._sanitize_text_for_cypher(
                        str(entity.get('value', ''))
                    ),
                    timeout=self.settings.neo4j_query_timeout / 1000.0
                )
            except Exception as e:
                logger.warning(
                    'Erro ao persistir entity no Neo4j',
                    intent_id=intent_id,
                    entity_type=entity.get('type'),
                    error=str(e)
                )

    def _sanitize_text_for_cypher(self, text: str) -> str:
        """
        Prepara texto para uso em queries Cypher

        O driver Neo4j faz escaping automático de parâmetros, então apenas
        truncamos textos muito longos para evitar problemas de performance.

        Args:
            text: Texto de entrada

        Returns:
            Texto truncado se necessário
        """
        if not text:
            return ''

        # Truncar texto longo (max 5000 chars) para evitar problemas de performance
        if len(text) > 5000:
            return text[:5000] + '...'

        return text

    async def _extract_keywords_async(self, text: str) -> str:
        """
        Extrai keywords do texto usando NLP ou fallback heurístico (com cache)

        Args:
            text: Texto de entrada

        Returns:
            Keywords separadas por espaço
        """
        if self.nlp_processor and self.nlp_processor.is_ready():
            # Usar NLP processor para extração avançada (com cache)
            keywords = await self.nlp_processor.extract_keywords_async(text, max_keywords=5)
            return ' '.join(keywords)
        else:
            # Fallback para extração simples (backward compatibility)
            return self._extract_keywords_sync(text)

    def _extract_keywords_sync(self, text: str) -> str:
        """
        Extrai keywords do texto usando fallback heurístico (síncrono)

        Args:
            text: Texto de entrada

        Returns:
            Keywords separadas por espaço
        """
        words = text.lower().split()
        stop_words = {'o', 'a', 'de', 'para', 'com', 'em', 'um', 'uma'}
        keywords = [w for w in words if w not in stop_words and len(w) > 2]
        return ' '.join(keywords[:5])

    def _extract_keywords(self, text: str) -> str:
        """
        Extrai keywords do texto usando NLP ou fallback heurístico (versão síncrona)

        Args:
            text: Texto de entrada

        Returns:
            Keywords separadas por espaço
        """
        if self.nlp_processor and self.nlp_processor.is_ready():
            # Usar NLP processor para extração avançada (sem cache em modo síncrono)
            keywords = self.nlp_processor.extract_keywords(text, max_keywords=5)
            return ' '.join(keywords)
        else:
            # Fallback para extração simples (backward compatibility)
            return self._extract_keywords_sync(text)

    async def close(self):
        """Close Neo4j driver"""
        if self.driver:
            await self.driver.close()
            logger.info('Neo4j client fechado')
