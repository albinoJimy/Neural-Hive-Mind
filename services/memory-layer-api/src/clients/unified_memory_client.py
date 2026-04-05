"""
Unified Memory Client - Orchestrates access to 4 memory layers
"""
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import structlog
from prometheus_client import Counter

logger = structlog.get_logger(__name__)

# Métricas Prometheus
CLICKHOUSE_FALLBACK_TRIGGERED = Counter(
    "memory_clickhouse_fallback_triggered_total",
    "Total de vezes que fallback foi ativado para ClickHouse",
    ["operation", "table"],
)


class UnifiedMemoryClient:
    """Unified client with intelligent routing across memory layers"""

    def __init__(
        self,
        redis_client,
        mongodb_client,
        neo4j_client,
        clickhouse_client,
        settings,
        kafka_producer=None,
        fallback_buffer=None,
    ):
        self.redis = redis_client
        self.mongodb = mongodb_client
        self.neo4j = neo4j_client
        self.clickhouse = clickhouse_client
        self.settings = settings
        self.kafka_producer = kafka_producer
        self.fallback_buffer = fallback_buffer

    async def query(
        self,
        query_type: str,
        entity_id: str,
        time_range: Optional[Tuple[datetime, datetime]] = None,
        use_cache: bool = True,
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
        start_time = datetime.now(timezone.utc)

        try:
            # Route based on query type
            if query_type == "semantic":
                result = await self._query_semantic_data(entity_id)
                source_layer = "neo4j"
                cache_hit = False
            elif query_type == "lineage":
                result = await self._query_lineage_data(entity_id)
                source_layer = "mongodb+neo4j"
                cache_hit = False
            elif query_type == "historical":
                if not time_range:
                    time_range = (
                        datetime.now(timezone.utc) - timedelta(days=30),
                        datetime.now(timezone.utc),
                    )
                result = await self._query_cold_data(entity_id, time_range)
                source_layer = "clickhouse"
                cache_hit = False
            else:  # context or default
                # Try hot -> warm -> cold cascade
                result, source_layer, cache_hit = await self._query_with_cascade(
                    entity_id, time_range, use_cache
                )

            # Calculate latency
            latency_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)

            return {
                "query_id": query_id,
                "entity_id": entity_id,
                "data": result,
                "source_layer": source_layer,
                "cache_hit": cache_hit,
                "latency_ms": latency_ms,
                "metadata": {
                    "query_type": query_type,
                    "time_range": str(time_range) if time_range else None,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            }
        except Exception as e:
            logger.error("Query failed", error=str(e), query_type=query_type, entity_id=entity_id)
            raise

    async def _query_with_cascade(
        self, entity_id: str, time_range: Optional[Tuple[datetime, datetime]], use_cache: bool
    ) -> Tuple[Dict, str, bool]:
        """Query with hot -> warm -> cold cascade"""
        # Determine if data is hot (recent)
        is_hot = self._is_hot_data(time_range)

        # Try Redis first if hot and cache enabled
        if is_hot and use_cache:
            hot_data = await self._query_hot_data(entity_id)
            if hot_data:
                logger.debug("Cache hit (Redis)", entity_id=entity_id)
                return hot_data, "redis", True

        # Try MongoDB (warm)
        if not time_range or self._is_warm_data(time_range):
            warm_data = await self._query_warm_data(entity_id, time_range)
            if warm_data:
                # Cache in Redis for future queries
                if use_cache:
                    await self._cache_in_redis(entity_id, warm_data)
                logger.debug("Found in MongoDB", entity_id=entity_id)
                return warm_data, "mongodb", False

        # Fallback to ClickHouse (cold)
        if time_range:
            cold_data = await self._query_cold_data(entity_id, time_range)
            if cold_data:
                logger.debug("Found in ClickHouse", entity_id=entity_id)
                return cold_data, "clickhouse", False

        # Not found in any layer
        logger.warning("Entity not found in any layer", entity_id=entity_id)
        return {}, "none", False

    def _is_hot_data(self, time_range: Optional[Tuple[datetime, datetime]]) -> bool:
        """Check if data qualifies as hot (< 5 min)"""
        if not time_range:
            return True
        start, end = time_range
        age = datetime.now(timezone.utc) - end
        return age.total_seconds() < self.settings.hot_data_threshold_seconds

    def _is_warm_data(self, time_range: Tuple[datetime, datetime]) -> bool:
        """Check if data qualifies as warm (< 30 days)"""
        start, end = time_range
        age = datetime.now(timezone.utc) - end
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
        self, entity_id: str, time_range: Optional[Tuple[datetime, datetime]]
    ) -> Optional[Dict]:
        """Query MongoDB (operational context)"""
        try:
            query_filter = {"entity_id": entity_id}
            if time_range:
                start, end = time_range
                query_filter["created_at"] = {"$gte": start, "$lte": end}

            result = await self.mongodb.find_one(
                collection=self.settings.mongodb_context_collection, filter=query_filter
            )
            return result
        except Exception as e:
            logger.warning("MongoDB query failed", error=str(e), entity_id=entity_id)
            return None

    async def _query_cold_data(
        self, entity_id: str, time_range: Tuple[datetime, datetime]
    ) -> List[Dict]:
        """Query ClickHouse (historical analytics)"""
        try:
            start, end = time_range
            plans = await self.clickhouse.query_historical_plans(
                start_date=start, end_date=end, limit=100
            )
            # Filter by entity_id (plan_id or intent_id)
            filtered = [p for p in plans if p[0] == entity_id or p[1] == entity_id]
            return filtered
        except Exception as e:
            logger.warning("ClickHouse query failed", error=str(e), entity_id=entity_id)
            # Tenta buscar dados drenados no MongoDB se ClickHouse falhar
            return await self._query_drained_fallback(entity_id, time_range)

    async def _query_drained_fallback(
        self, entity_id: str, time_range: Tuple[datetime, datetime]
    ) -> List[Dict]:
        """
        Query dados drenados para MongoDB quando ClickHouse falha.

        Args:
            entity_id: ID da entidade
            time_range: Intervalo de tempo

        Returns:
            Lista de planos drenados
        """
        try:
            from src.services.fallback_drainer import FallbackDrainer

            query_filter = {
                "table": "cognitive_plans_history",
                "drained": False,
            }

            # Adiciona filtro por entity_id se disponível
            # Busca em rows que contêm o entity_id (plan_id ou intent_id)
            start, end = time_range

            # Busca documentos recentes do buffer drenado
            documents = await self.mongodb.find(
                collection=FallbackDrainer.DRAINED_COLLECTION,
                filter=query_filter,
                limit=100,
            )

            # Filtra por entity_id e time_range
            filtered = []
            for doc in documents:
                rows = doc.get("rows", [])
                for row in rows:
                    # row é uma lista: [plan_id, intent_id, domain, ...]
                    if len(row) >= 2 and (row[0] == entity_id or row[1] == entity_id):
                        filtered.append(row)
                        break

            if filtered:
                logger.info(
                    "Returned data from drained fallback",
                    entity_id=entity_id,
                    count=len(filtered),
                )

            return filtered

        except Exception as e:
            logger.warning(
                "Drained fallback query failed", error=str(e), entity_id=entity_id
            )
            return []

    async def _query_semantic_data(
        self, entity_id: str, relationship_type: Optional[str] = None
    ) -> List[Dict]:
        """Query Neo4j (Knowledge Graph)"""
        try:
            query = """
                MATCH (e {id: $entity_id})-[r]->(related)
                RETURN e, type(r) as relationship, related
                LIMIT 100
            """
            result = await self.neo4j.run_query(query, {"entity_id": entity_id})
            return result
        except Exception as e:
            logger.warning("Neo4j query failed", error=str(e), entity_id=entity_id)
            return []

    async def _query_lineage_data(self, entity_id: str) -> Dict:
        """Query lineage combining MongoDB + Neo4j"""
        try:
            # Get metadata from MongoDB
            lineage_meta = await self.mongodb.find_one(
                collection=self.settings.mongodb_lineage_collection, filter={"entity_id": entity_id}
            )

            # Get graph from Neo4j
            query = """
                MATCH path = (e {id: $entity_id})-[:DERIVED_FROM*1..3]-(related)
                RETURN path
            """
            lineage_graph = await self.neo4j.run_query(query, {"entity_id": entity_id})

            return {"entity_id": entity_id, "metadata": lineage_meta or {}, "graph": lineage_graph}
        except Exception as e:
            logger.error("Lineage query failed", error=str(e), entity_id=entity_id)
            return {}

    async def _cache_in_redis(self, entity_id: str, data: Dict):
        """Cache data in Redis with TTL"""
        try:
            cache_key = f"context:{entity_id}"
            await self.redis.set(cache_key, data, ttl=self.settings.redis_default_ttl)
            logger.debug("Cached in Redis", entity_id=entity_id)
        except Exception as e:
            logger.warning("Redis caching failed", error=str(e))

    async def save(
        self, data: Dict[str, Any], data_type: str, ttl_override: Optional[int] = None
    ) -> str:
        """
        Save data to multiple layers

        Strategy:
        - Always write to Redis (hot cache) with short TTL
        - Write to MongoDB (operational) with 30-day TTL
        - Publish Kafka event for async ClickHouse ingestion
        - Update Neo4j if semantic relations exist
        """
        entity_id = data.get("entity_id") or str(uuid.uuid4())
        data["entity_id"] = entity_id
        data["created_at"] = datetime.now(timezone.utc)

        try:
            # 1. Cache in Redis
            if self.settings.enable_cache:
                ttl = ttl_override or self.settings.redis_default_ttl
                await self.redis.set(f"context:{entity_id}", data, ttl=ttl)
                logger.debug("Saved to Redis", entity_id=entity_id)

            # 2. Save to MongoDB
            await self.mongodb.insert_one(
                collection=self.settings.mongodb_context_collection, document=data
            )
            logger.debug("Saved to MongoDB", entity_id=entity_id)

            # 3. Publica evento Kafka para sincronização assíncrona com ClickHouse
            if self.kafka_producer and self.settings.enable_realtime_sync:
                await self._publish_sync_event(entity_id, data_type, data)

            # 4. Update Neo4j if semantic data
            if data.get("relationships"):
                await self._update_semantic_graph(entity_id, data["relationships"])

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
                await self.neo4j.run_query(
                    query,
                    {
                        "entity_id": entity_id,
                        "target_id": rel["target_id"],
                        "rel_type": rel.get("type", "RELATED_TO"),
                    },
                )
            logger.debug("Updated semantic graph", entity_id=entity_id)
        except Exception as e:
            logger.warning("Semantic graph update failed", error=str(e))

    async def _publish_sync_event(self, entity_id: str, data_type: str, data: Dict):
        """
        Publica evento de sincronização no Kafka para ingestão assíncrona no ClickHouse.

        Args:
            entity_id: Identificador da entidade
            data_type: Tipo de dado (context, lineage, etc)
            data: Dados a serem sincronizados
        """
        try:
            sync_event = {
                "event_id": str(uuid.uuid4()),
                "entity_id": entity_id,
                "data_type": data_type,
                "operation": "INSERT",
                "collection": self.settings.mongodb_context_collection,
                "timestamp": int(datetime.now(timezone.utc).timestamp() * 1000),
                "data": json.dumps(data, default=str),
                "metadata": json.dumps({"source": "unified_memory_client"}),
            }
            await self.kafka_producer.publish_sync_event(sync_event)
            logger.debug(
                "Evento de sincronização publicado", entity_id=entity_id, data_type=data_type
            )
        except Exception as e:
            # Fail-open: não bloqueia operação principal se Kafka falhar
            logger.warning(
                "Falha ao publicar evento de sincronização",
                error=str(e),
                entity_id=entity_id,
                data_type=data_type,
            )

    async def get_lineage(self, entity_id: str, depth: int = 3) -> Dict[str, Any]:
        """Get data lineage tree"""
        return await self._query_lineage_data(entity_id)

    async def get_quality_stats(
        self,
        data_type: Optional[str] = None,
        time_range: Optional[Tuple[datetime, datetime]] = None,
    ) -> Dict[str, Any]:
        """Get quality statistics from MongoDB"""
        try:
            query_filter = {}
            if data_type:
                query_filter["data_type"] = data_type
            if time_range:
                start, end = time_range
                query_filter["timestamp"] = {"$gte": start, "$lte": end}

            stats = await self.mongodb.find(
                collection=self.settings.mongodb_quality_collection, filter=query_filter, limit=100
            )
            return {"stats": stats}
        except Exception as e:
            logger.error("Quality stats query failed", error=str(e))
            return {"stats": []}

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
                    filter={"entity_id": {"$regex": pattern.replace("*", ".*")}},
                    update={"$set": {"stale": True, "stale_at": datetime.now(timezone.utc)}},
                )
                logger.info("Cascade invalidation completed", pattern=pattern)

        except Exception as e:
            logger.error("Cache invalidation failed", error=str(e), pattern=pattern)
            raise

    # ========================================
    # Métodos para ClickHouse com Fallback
    # ========================================

    async def insert_clickhouse_with_fallback(
        self,
        table: str,
        rows: List[List[Any]],
        column_names: List[str],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Insere dados no ClickHouse com fallback automático para buffer.

        Args:
            table: Nome da tabela ClickHouse
            rows: Linhas a serem inseridas
            column_names: Nomes das colunas
            metadata: Metadados adicionais

        Returns:
            True se inserido com sucesso ou enviado para buffer
        """
        if not self.clickhouse:
            # ClickHouse não configurado, usa buffer direto
            return await self._send_to_fallback_buffer(table, rows, column_names, metadata)

        try:
            # Tenta inserir no ClickHouse
            await self.clickhouse.insert_batch(table, rows, column_names)
            logger.debug("Inserted into ClickHouse", table=table, row_count=len(rows))
            return True

        except Exception as e:
            # Fallback para buffer
            CLICKHOUSE_FALLBACK_TRIGGERED.labels(
                operation="insert_batch", table=table
            ).inc()
            logger.warning(
                "ClickHouse insert failed, using fallback buffer",
                error=str(e),
                table=table,
                row_count=len(rows),
            )
            return await self._send_to_fallback_buffer(table, rows, column_names, metadata)

    async def _send_to_fallback_buffer(
        self,
        table: str,
        rows: List[List[Any]],
        column_names: List[str],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Envia dados para o buffer de fallback.

        Args:
            table: Nome da tabela ClickHouse
            rows: Linhas a serem bufferizadas
            column_names: Nomes das colunas
            metadata: Metadados adicionais

        Returns:
            True se adicionado ao buffer
        """
        if not self.fallback_buffer:
            logger.warning(
                "No fallback buffer available, data will be lost",
                table=table,
                row_count=len(rows),
            )
            return False

        try:
            success = await self.fallback_buffer.add_event(
                table=table,
                rows=rows,
                column_names=column_names,
                metadata=metadata,
            )
            if success:
                logger.info(
                    "Data sent to fallback buffer",
                    table=table,
                    row_count=len(rows),
                )
            return success
        except Exception as e:
            logger.error(
                "Failed to send to fallback buffer",
                error=str(e),
                table=table,
            )
            return False

    async def insert_cognitive_plan_history(self, plan: Dict[str, Any]) -> bool:
        """
        Insere plano cognitivo no histórico ClickHouse com fallback.

        Args:
            plan: Dicionário com dados do plano

        Returns:
            True se inserido ou bufferizado
        """
        try:
            rows = [[
                plan.get("plan_id"),
                plan.get("intent_id"),
                plan.get("domain"),
                plan.get("created_at", datetime.now(timezone.utc)),
                plan.get("risk_score", 0.0),
                plan.get("complexity_score", 0.0),
                str(plan.get("plan_data", {})),
                str(plan.get("metadata", {})),
            ]]

            return await self.insert_clickhouse_with_fallback(
                table="cognitive_plans_history",
                rows=rows,
                column_names=[
                    "plan_id",
                    "intent_id",
                    "domain",
                    "created_at",
                    "risk_score",
                    "complexity_score",
                    "plan_data",
                    "metadata",
                ],
                metadata={"source": "cognitive_plan"},
            )
        except Exception as e:
            logger.error("Failed to insert cognitive plan history", error=str(e))
            return False

    async def insert_consensus_decision_history(self, decision: Dict[str, Any]) -> bool:
        """
        Insere decisão de consenso no histórico ClickHouse com fallback.

        Args:
            decision: Dicionário com dados da decisão

        Returns:
            True se inserido ou bufferizado
        """
        try:
            rows = [[
                decision.get("decision_id"),
                decision.get("plan_id"),
                decision.get("aggregated_confidence", 0.0),
                decision.get("consensus_type"),
                decision.get("created_at", datetime.now(timezone.utc)),
                str(decision.get("decision_data", {})),
                str(decision.get("metadata", {})),
            ]]

            return await self.insert_clickhouse_with_fallback(
                table="consensus_decisions_history",
                rows=rows,
                column_names=[
                    "decision_id",
                    "plan_id",
                    "aggregated_confidence",
                    "consensus_type",
                    "created_at",
                    "decision_data",
                    "metadata",
                ],
                metadata={"source": "consensus_decision"},
            )
        except Exception as e:
            logger.error("Failed to insert consensus decision history", error=str(e))
            return False

    async def insert_specialist_opinion_history(self, opinion: Dict[str, Any]) -> bool:
        """
        Insere opinião de especialista no histórico ClickHouse com fallback.

        Args:
            opinion: Dicionário com dados da opinião

        Returns:
            True se inserido ou bufferizado
        """
        try:
            rows = [[
                opinion.get("opinion_id"),
                opinion.get("specialist_type"),
                opinion.get("plan_id"),
                opinion.get("confidence_score", 0.0),
                opinion.get("created_at", datetime.now(timezone.utc)),
                str(opinion.get("opinion_data", {})),
                str(opinion.get("metadata", {})),
            ]]

            return await self.insert_clickhouse_with_fallback(
                table="specialist_opinions_history",
                rows=rows,
                column_names=[
                    "opinion_id",
                    "specialist_type",
                    "plan_id",
                    "confidence_score",
                    "created_at",
                    "opinion_data",
                    "metadata",
                ],
                metadata={"source": "specialist_opinion"},
            )
        except Exception as e:
            logger.error("Failed to insert specialist opinion history", error=str(e))
            return False
