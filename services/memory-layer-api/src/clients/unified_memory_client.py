"""
Unified Memory Client - Orchestrates access to 4 memory layers
"""
import structlog
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Tuple, List
import uuid

logger = structlog.get_logger(__name__)


class UnifiedMemoryClient:
    """Unified client with intelligent routing across memory layers"""

    def __init__(self, redis_client, mongodb_client, neo4j_client, clickhouse_client, settings):
        self.redis = redis_client
        self.mongodb = mongodb_client
        self.neo4j = neo4j_client
        self.clickhouse = clickhouse_client
        self.settings = settings

    async def query(
        self,
        query_type: str,
        entity_id: str,
        time_range: Optional[Tuple[datetime, datetime]] = None,
        use_cache: bool = True
    ) -> Dict[str, Any]:
        """
        Intelligent query routing based on query_type and time_range

        Routing logic:
        - time_range None or recent (< 5 min) → Redis first
        - time_range < 30 days → MongoDB
        - time_range > 30 days → ClickHouse
        - query_type == 'semantic' → Neo4j
        - query_type == 'lineage' → MongoDB + Neo4j
        """
        query_id = str(uuid.uuid4())
        start_time = datetime.utcnow()

        try:
            # Route based on query type
            if query_type == 'semantic':
                result = await self._query_semantic_data(entity_id)
                source_layer = 'neo4j'
                cache_hit = False
            elif query_type == 'lineage':
                result = await self._query_lineage_data(entity_id)
                source_layer = 'mongodb+neo4j'
                cache_hit = False
            elif query_type == 'historical':
                if not time_range:
                    time_range = (datetime.utcnow() - timedelta(days=30), datetime.utcnow())
                result = await self._query_cold_data(entity_id, time_range)
                source_layer = 'clickhouse'
                cache_hit = False
            else:  # context or default
                # Try hot -> warm -> cold cascade
                result, source_layer, cache_hit = await self._query_with_cascade(
                    entity_id, time_range, use_cache
                )

            # Calculate latency
            latency_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)

            return {
                'query_id': query_id,
                'entity_id': entity_id,
                'data': result,
                'source_layer': source_layer,
                'cache_hit': cache_hit,
                'latency_ms': latency_ms,
                'metadata': {
                    'query_type': query_type,
                    'time_range': str(time_range) if time_range else None,
                    'timestamp': datetime.utcnow().isoformat()
                }
            }
        except Exception as e:
            logger.error("Query failed", error=str(e), query_type=query_type, entity_id=entity_id)
            raise

    async def _query_with_cascade(
        self,
        entity_id: str,
        time_range: Optional[Tuple[datetime, datetime]],
        use_cache: bool
    ) -> Tuple[Dict, str, bool]:
        """Query with hot -> warm -> cold cascade"""
        # Determine if data is hot (recent)
        is_hot = self._is_hot_data(time_range)

        # Try Redis first if hot and cache enabled
        if is_hot and use_cache:
            hot_data = await self._query_hot_data(entity_id)
            if hot_data:
                logger.debug("Cache hit (Redis)", entity_id=entity_id)
                return hot_data, 'redis', True

        # Try MongoDB (warm)
        if not time_range or self._is_warm_data(time_range):
            warm_data = await self._query_warm_data(entity_id, time_range)
            if warm_data:
                # Cache in Redis for future queries
                if use_cache:
                    await self._cache_in_redis(entity_id, warm_data)
                logger.debug("Found in MongoDB", entity_id=entity_id)
                return warm_data, 'mongodb', False

        # Fallback to ClickHouse (cold)
        if time_range:
            cold_data = await self._query_cold_data(entity_id, time_range)
            if cold_data:
                logger.debug("Found in ClickHouse", entity_id=entity_id)
                return cold_data, 'clickhouse', False

        # Not found in any layer
        logger.warning("Entity not found in any layer", entity_id=entity_id)
        return {}, 'none', False

    def _is_hot_data(self, time_range: Optional[Tuple[datetime, datetime]]) -> bool:
        """Check if data qualifies as hot (< 5 min)"""
        if not time_range:
            return True
        start, end = time_range
        age = datetime.utcnow() - end
        return age.total_seconds() < self.settings.hot_data_threshold_seconds

    def _is_warm_data(self, time_range: Tuple[datetime, datetime]) -> bool:
        """Check if data qualifies as warm (< 30 days)"""
        start, end = time_range
        age = datetime.utcnow() - end
        return age.days < self.settings.warm_data_threshold_days

    async def _query_hot_data(self, entity_id: str) -> Optional[Dict]:
        """Query Redis (hot cache)"""
        try:
            cache_key = f"context:{entity_id}"
            cached = await self.redis.get(cache_key)
            return cached if cached else None
        except Exception as e:
            logger.warning("Redis query failed", error=str(e), entity_id=entity_id)
            return None

    async def _query_warm_data(
        self,
        entity_id: str,
        time_range: Optional[Tuple[datetime, datetime]]
    ) -> Optional[Dict]:
        """Query MongoDB (operational context)"""
        try:
            query_filter = {'entity_id': entity_id}
            if time_range:
                start, end = time_range
                query_filter['created_at'] = {'$gte': start, '$lte': end}

            result = await self.mongodb.find_one(
                collection=self.settings.mongodb_context_collection,
                filter=query_filter
            )
            return result
        except Exception as e:
            logger.warning("MongoDB query failed", error=str(e), entity_id=entity_id)
            return None

    async def _query_cold_data(
        self,
        entity_id: str,
        time_range: Tuple[datetime, datetime]
    ) -> List[Dict]:
        """Query ClickHouse (historical analytics)"""
        try:
            start, end = time_range
            plans = await self.clickhouse.query_historical_plans(
                start_date=start,
                end_date=end,
                limit=100
            )
            # Filter by entity_id (plan_id or intent_id)
            filtered = [p for p in plans if p[0] == entity_id or p[1] == entity_id]
            return filtered
        except Exception as e:
            logger.warning("ClickHouse query failed", error=str(e), entity_id=entity_id)
            return []

    async def _query_semantic_data(
        self,
        entity_id: str,
        relationship_type: Optional[str] = None
    ) -> List[Dict]:
        """Query Neo4j (Knowledge Graph)"""
        try:
            query = """
                MATCH (e {id: $entity_id})-[r]->(related)
                RETURN e, type(r) as relationship, related
                LIMIT 100
            """
            result = await self.neo4j.run_query(query, {'entity_id': entity_id})
            return result
        except Exception as e:
            logger.warning("Neo4j query failed", error=str(e), entity_id=entity_id)
            return []

    async def _query_lineage_data(self, entity_id: str) -> Dict:
        """Query lineage combining MongoDB + Neo4j"""
        try:
            # Get metadata from MongoDB
            lineage_meta = await self.mongodb.find_one(
                collection=self.settings.mongodb_lineage_collection,
                filter={'entity_id': entity_id}
            )

            # Get graph from Neo4j
            query = """
                MATCH path = (e {id: $entity_id})-[:DERIVED_FROM*1..3]-(related)
                RETURN path
            """
            lineage_graph = await self.neo4j.run_query(query, {'entity_id': entity_id})

            return {
                'entity_id': entity_id,
                'metadata': lineage_meta or {},
                'graph': lineage_graph
            }
        except Exception as e:
            logger.error("Lineage query failed", error=str(e), entity_id=entity_id)
            return {}

    async def _cache_in_redis(self, entity_id: str, data: Dict):
        """Cache data in Redis with TTL"""
        try:
            cache_key = f"context:{entity_id}"
            await self.redis.set(
                cache_key,
                data,
                ttl=self.settings.redis_default_ttl
            )
            logger.debug("Cached in Redis", entity_id=entity_id)
        except Exception as e:
            logger.warning("Redis caching failed", error=str(e))

    async def save(
        self,
        data: Dict[str, Any],
        data_type: str,
        ttl_override: Optional[int] = None
    ) -> str:
        """
        Save data to multiple layers

        Strategy:
        - Always write to Redis (hot cache) with short TTL
        - Write to MongoDB (operational) with 30-day TTL
        - Publish Kafka event for async ClickHouse ingestion
        - Update Neo4j if semantic relations exist
        """
        entity_id = data.get('entity_id') or str(uuid.uuid4())
        data['entity_id'] = entity_id
        data['created_at'] = datetime.utcnow()

        try:
            # 1. Cache in Redis
            if self.settings.enable_cache:
                ttl = ttl_override or self.settings.redis_default_ttl
                await self.redis.set(f"context:{entity_id}", data, ttl=ttl)
                logger.debug("Saved to Redis", entity_id=entity_id)

            # 2. Save to MongoDB
            await self.mongodb.insert_one(
                collection=self.settings.mongodb_context_collection,
                document=data
            )
            logger.debug("Saved to MongoDB", entity_id=entity_id)

            # 3. TODO: Publish Kafka event for ClickHouse sync
            # await self._publish_sync_event(entity_id, data_type, data)

            # 4. Update Neo4j if semantic data
            if data.get('relationships'):
                await self._update_semantic_graph(entity_id, data['relationships'])

            logger.info("Data saved to memory layers", entity_id=entity_id, data_type=data_type)
            return entity_id

        except Exception as e:
            logger.error("Save failed", error=str(e), entity_id=entity_id)
            raise

    async def _update_semantic_graph(self, entity_id: str, relationships: List[Dict]):
        """Update Neo4j semantic graph"""
        try:
            for rel in relationships:
                query = """
                    MERGE (source {id: $entity_id})
                    MERGE (target {id: $target_id})
                    MERGE (source)-[r:RELATED_TO]->(target)
                    SET r.type = $rel_type
                """
                await self.neo4j.run_query(query, {
                    'entity_id': entity_id,
                    'target_id': rel['target_id'],
                    'rel_type': rel.get('type', 'RELATED_TO')
                })
            logger.debug("Updated semantic graph", entity_id=entity_id)
        except Exception as e:
            logger.warning("Semantic graph update failed", error=str(e))

    async def get_lineage(self, entity_id: str, depth: int = 3) -> Dict[str, Any]:
        """Get data lineage tree"""
        return await self._query_lineage_data(entity_id)

    async def get_quality_stats(
        self,
        data_type: Optional[str] = None,
        time_range: Optional[Tuple[datetime, datetime]] = None
    ) -> Dict[str, Any]:
        """Get quality statistics from MongoDB"""
        try:
            query_filter = {}
            if data_type:
                query_filter['data_type'] = data_type
            if time_range:
                start, end = time_range
                query_filter['timestamp'] = {'$gte': start, '$lte': end}

            stats = await self.mongodb.find(
                collection=self.settings.mongodb_quality_collection,
                filter=query_filter,
                limit=100
            )
            return {'stats': stats}
        except Exception as e:
            logger.error("Quality stats query failed", error=str(e))
            return {'stats': []}

    async def invalidate_cache(self, pattern: str, cascade: bool = False):
        """Invalidate Redis cache by pattern"""
        try:
            # Redis pattern-based deletion
            await self.redis.delete_pattern(pattern)
            logger.info("Cache invalidated", pattern=pattern)

            # If cascade, mark MongoDB data as stale
            if cascade:
                await self.mongodb.update_many(
                    collection=self.settings.mongodb_context_collection,
                    filter={'entity_id': {'$regex': pattern.replace('*', '.*')}},
                    update={'$set': {'stale': True, 'stale_at': datetime.utcnow()}}
                )
                logger.info("Cascade invalidation completed", pattern=pattern)

        except Exception as e:
            logger.error("Cache invalidation failed", error=str(e), pattern=pattern)
            raise
