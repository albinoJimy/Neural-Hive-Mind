"""
Semantic Parser - Converts Intent Envelopes to intermediate representation

Parses intents, maps entities to ontology, and enriches with historical context.
"""

import structlog
import hashlib
from datetime import datetime
from typing import Dict, Any, List, Optional, TYPE_CHECKING

from src.clients.neo4j_client import Neo4jClient
from src.clients.mongodb_client import MongoDBClient
from src.clients.redis_client import RedisClient

if TYPE_CHECKING:
    from src.services.nlp_processor import NLPProcessor

logger = structlog.get_logger()


class SemanticParser:
    """Parser that extracts objectives, entities, and constraints"""

    def __init__(
        self,
        neo4j_client: Neo4jClient,
        mongodb_client: MongoDBClient,
        redis_client: RedisClient,
        nlp_processor: Optional['NLPProcessor'] = None
    ):
        self.neo4j = neo4j_client
        self.mongodb = mongodb_client
        self.redis = redis_client
        self.nlp_processor = nlp_processor

    async def parse(self, intent_envelope: Dict) -> Dict[str, Any]:
        """
        Parseia intent e gera representação intermediária

        Lida gracefully com constraints nulo ou ausente.

        Args:
            intent_envelope: Dict do Intent Envelope

        Returns:
            Dict da representação intermediária
        """
        intent = intent_envelope.get('intent', {})
        # Garantir que constraints nunca seja None
        constraints = intent_envelope.get('constraints') or {}

        # Garantir domínio com fallback consistente com persistência e seed
        domain = intent.get('domain') or 'unknown'

        # Extract objectives
        objectives = await self._extract_objectives(intent.get('text', ''))

        # Map entities to ontology
        entities = intent.get('entities', [])

        # Enriquecer entidades com extração NLP avançada
        if self.nlp_processor and self.nlp_processor.is_ready():
            nlp_entities = await self._extract_entities_advanced(intent.get('text', ''))
            # Merge com entidades existentes (evitar duplicatas)
            existing_values = {e.get('value', '').lower() for e in entities}
            for nlp_entity in nlp_entities:
                if nlp_entity['value'].lower() not in existing_values:
                    entities.append(nlp_entity)

        mapped_entities = await self._map_entities_to_ontology(entities)

        # Extract constraints
        extracted_constraints = self._extract_constraints(constraints)

        # Enrich with historical context
        historical_context = await self._enrich_with_history(
            intent_envelope.get('id'),
            domain,
            intent.get('text', '')
        )

        # Identify known patterns
        known_patterns = await self._identify_patterns(
            domain,
            objectives
        )

        intermediate_representation = {
            'intent_id': intent_envelope.get('id'),
            'domain': domain,
            'objectives': objectives,
            'entities': mapped_entities,
            'constraints': extracted_constraints,
            'historical_context': historical_context,
            'known_patterns': known_patterns,
            'original_confidence': intent_envelope.get('confidence'),
            'metadata': {
                'priority': extracted_constraints.get('priority', 'normal'),
                'security_level': extracted_constraints.get('security_level', 'internal'),
                'deadline': extracted_constraints.get('deadline')
            }
        }

        # Cache enriched context
        await self.redis.cache_enriched_context(
            intent_envelope.get('id'),
            intermediate_representation,
            ttl=300
        )

        # Log com informação sobre contexto histórico
        num_similar = len(historical_context.get('similar_intents', []))
        logger.info(
            'Intent parsed e enriquecido com contexto historico',
            intent_id=intent_envelope.get('id'),
            objectives=objectives,
            num_entities=len(mapped_entities),
            num_similar_intents=num_similar
        )

        return intermediate_representation

    async def _extract_objectives(self, text: str) -> List[str]:
        """Extrai objectives principais do texto usando NLP ou fallback heurístico"""
        if self.nlp_processor and self.nlp_processor.is_ready():
            # Usar NLP processor para extração avançada (com cache)
            objectives = await self.nlp_processor.extract_objectives_async(text)

            # Garantir pelo menos um objective (fallback para 'query')
            if not objectives:
                objectives = ['query']

            logger.debug(
                'Objectives extraídos via NLP',
                objectives=objectives,
                text_preview=text[:100]
            )

            return objectives
        else:
            # Fallback para extração heurística (backward compatibility)
            objectives = []
            text_lower = text.lower()

            if 'criar' in text_lower or 'create' in text_lower:
                objectives.append('create')
            if 'atualizar' in text_lower or 'update' in text_lower:
                objectives.append('update')
            if 'deletar' in text_lower or 'delete' in text_lower:
                objectives.append('delete')
            if 'consultar' in text_lower or 'query' in text_lower or 'buscar' in text_lower:
                objectives.append('query')
            if 'transformar' in text_lower or 'transform' in text_lower:
                objectives.append('transform')

            # Default to query if no objectives found
            if not objectives:
                objectives.append('query')

            return objectives

    async def _extract_entities_advanced(self, text: str) -> List[Dict]:
        """Extrai entidades usando NLP avançado (com cache)"""
        if self.nlp_processor and self.nlp_processor.is_ready():
            return await self.nlp_processor.extract_entities_advanced_async(text)
        else:
            return []

    async def _map_entities_to_ontology(self, entities: List[Dict]) -> List[Dict]:
        """Map entities to canonical ontology"""
        mapped = []

        for entity in entities:
            entity_type = entity.get('type')

            # Query ontology (with cache)
            cache_key = f'ontology:{entity_type}'
            ontology_def = await self.redis.get_cached_query(cache_key)

            if not ontology_def:
                ontology_def = await self.neo4j.query_ontology(entity_type)
                await self.redis.cache_query_result(cache_key, ontology_def, ttl=3600)

            mapped.append({
                'original_type': entity_type,
                'canonical_type': ontology_def.get('canonical_type', entity_type),
                'value': entity.get('value'),
                'confidence': entity.get('confidence', 1.0),
                'properties': ontology_def.get('properties', {})
            })

        return mapped

    def _extract_constraints(self, constraints: Dict) -> Dict:
        """
        Extrai e normaliza constraints com valores padrão

        Lida gracefully com constraints None ou vazio, retornando sempre
        um dict válido com valores padrão.

        Args:
            constraints: Dict de constraints (pode ser None)

        Returns:
            Dict normalizado de constraints
        """
        # Garantir que constraints seja um dict válido
        if not constraints or not isinstance(constraints, dict):
            constraints = {}

        return {
            'priority': constraints.get('priority', 'normal'),
            'deadline': constraints.get('deadline'),
            'max_retries': constraints.get('max_retries', 3),
            'timeout_ms': constraints.get('timeout_ms', 30000),
            'required_capabilities': constraints.get('required_capabilities', []),
            'security_level': constraints.get('security_level', 'internal')
        }

    async def _enrich_with_history(
        self,
        intent_id: str,
        domain: str,
        text: str
    ) -> Dict:
        """Enrich with historical context from Knowledge Graph"""
        # Query similar intents (with cache)
        cache_key = f'neo4j:similar:{hashlib.md5(text.encode()).hexdigest()}'

        logger.debug(
            'Buscando similar intents no Neo4j',
            intent_id=intent_id,
            domain=domain,
            text_preview=text[:100] if text else '',
            cache_key=cache_key
        )

        similar_intents = await self.redis.get_cached_query(cache_key)

        if not similar_intents:
            similar_intents = await self.neo4j.query_similar_intents(
                text,
                domain,
                limit=5
            )
            await self.redis.cache_query_result(cache_key, similar_intents, ttl=600)

        # Log resultado da busca de similar intents
        if not similar_intents:
            logger.warning(
                'Nenhum similar intent encontrado no Neo4j',
                intent_id=intent_id,
                domain=domain,
                sugestao='Verifique se Neo4j possui dados historicos (execute seed_neo4j_intents.py)'
            )
        else:
            similar_ids = [s.get('id') for s in similar_intents[:2]]
            logger.info(
                'Similar intents encontrados',
                intent_id=intent_id,
                count=len(similar_intents),
                similar_ids=similar_ids
            )

        # Get operational context (if exists)
        operational_context = await self.mongodb.get_operational_context(intent_id)

        logger.debug(
            'Contexto historico enriquecido',
            intent_id=intent_id,
            has_operational_context=operational_context is not None,
            num_similar_intents=len(similar_intents) if similar_intents else 0
        )

        return {
            'similar_intents': similar_intents,
            'operational_context': operational_context,
            'enrichment_timestamp': datetime.utcnow().isoformat()
        }

    async def _identify_patterns(self, domain: str, objectives: List[str]) -> List[Dict]:
        """Identify known patterns for reuse"""
        # MVP: Return empty (no predefined patterns)
        # Future: Query Knowledge Graph for templates
        return []
